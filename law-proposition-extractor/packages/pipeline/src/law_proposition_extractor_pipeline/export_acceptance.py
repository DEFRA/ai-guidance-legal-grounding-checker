"""Post-extraction repair orchestration and export acceptance reporting."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import Proposition, SourceFragment, SourceRecord, apply_relationship_keys
from law_proposition_extractor_domain.enums import LegalEffectType, PropositionTier
from law_proposition_extractor_domain.proposition_classification import (
    classify_application_scope_kind,
    derive_territorial_application,
)
from law_proposition_extractor_domain.proposition_notes import (
    EXTRACTION_META_PREFIX,
    assign_proposition_extraction_debug,
    resolve_extraction_meta_for_proposition,
)

from .extraction_provider_failure import (
    BENCHMARK_VERDICT_INCOMPLETE,
    assess_extraction_benchmark_completeness,
)
from .export import export_bundle
from .export_proposition_hygiene import apply_export_proposition_hygiene
from .extraction_fragment_repair import run_fragment_repair_pipeline
from .fragment_anchor_coverage import (
    fragments_needing_llm_repair,
    summarize_export_fragment_anchor_coverage,
)
from .extraction_json_repair import (
    _enrich_bundle_from_export_files,
    apply_json_repairs_to_bundle,
    attempt_json_repair_for_candidate,
    list_json_repair_candidates,
)
from .fresh_extraction_verification import (
    FreshExtractionVerificationReport,
    build_fresh_extraction_verification,
    write_fresh_extraction_verification,
)
from .linting import load_exported_bundle
from .normalised_proposition_review import (
    build_review_from_export_dir,
    write_normalised_proposition_review,
)
from .proposition_normalisation import normalise_extracted_propositions
from .proposition_quality_gates import (
    DANGEROUS_LEGACY_KEY_PREFIX,
    PropositionQualityReport,
    run_proposition_quality_gates,
    write_normalisation_quality_artifacts,
)

ACCEPTANCE_MD_FILENAME = "EXPORT_ACCEPTANCE.md"
ACCEPTANCE_JSON_FILENAME = "export_acceptance.json"

RepairMode = Literal["deterministic", "llm", "both"]
AcceptanceStatus = Literal["accepted", "accepted_with_warnings", "needs_review", "failed"]
IssueKind = Literal["hard_repairable", "soft_repairable", "needs_human_review"]

UNKNOWN_CLASSIFICATION_RATE_THRESHOLD = 0.01
MISSING_EVIDENCE_ACCEPTED_WITH_WARNINGS_MAX = 20
UNRESOLVED_VALIDATION_WARNING_THRESHOLD = 25

_EVIDENCE_ALTERNATE_META_KEYS = (
    "verbatim_evidence",
    "evidence",
    "source_quote",
    "excerpt",
    "raw_evidence",
    "source_excerpt",
)

_UK_WIDE_TERRITORIES = frozenset({"United Kingdom", "Great Britain", "UK"})


@dataclass(frozen=True)
class RepairableIssue:
    issue_id: str
    kind: IssueKind
    check_id: str
    message: str
    proposition_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "kind": self.kind,
            "check_id": self.check_id,
            "message": self.message,
            "proposition_id": self.proposition_id,
            "details": self.details,
        }


@dataclass
class RepairPassStats:
    pass_name: str
    attempted: int = 0
    succeeded: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_name": self.pass_name,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "details": self.details,
        }


@dataclass
class ExportAcceptanceReport:
    export_path: str
    generated_at: str
    source_count: int
    proposition_count: int
    verification_errors: int
    warning_count: int
    repairs_attempted: int
    repairs_succeeded: int
    remaining_hard_failures: list[str]
    remaining_human_review_warnings: list[str]
    acceptance_status: AcceptanceStatus
    remaining_acceptance_warnings: list[str] = field(default_factory=list)
    repair_passes: list[RepairPassStats] = field(default_factory=list)
    issues_before: list[RepairableIssue] = field(default_factory=list)
    issues_after: list[RepairableIssue] = field(default_factory=list)
    verification_initial: dict[str, Any] = field(default_factory=dict)
    verification_final: dict[str, Any] = field(default_factory=dict)
    normalisation_quality: dict[str, Any] = field(default_factory=dict)
    npp_reg2_anchors: dict[str, Any] = field(default_factory=dict)
    source_coverage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_path": self.export_path,
            "generated_at": self.generated_at,
            "source_count": self.source_count,
            "proposition_count": self.proposition_count,
            "verification_errors": self.verification_errors,
            "warning_count": self.warning_count,
            "repairs_attempted": self.repairs_attempted,
            "repairs_succeeded": self.repairs_succeeded,
            "remaining_hard_failures": self.remaining_hard_failures,
            "remaining_human_review_warnings": self.remaining_human_review_warnings,
            "remaining_acceptance_warnings": self.remaining_acceptance_warnings,
            "acceptance_status": self.acceptance_status,
            "repair_passes": [p.to_dict() for p in self.repair_passes],
            "issues_before": [i.to_dict() for i in self.issues_before],
            "issues_after": [i.to_dict() for i in self.issues_after],
            "verification_initial": self.verification_initial,
            "verification_final": self.verification_final,
            "normalisation_quality": self.normalisation_quality,
            "npp_reg2_anchors": self.npp_reg2_anchors,
            "source_coverage": self.source_coverage,
        }


def _utc_now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _str_field(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _is_unknown_tier_or_effect(row: dict[str, Any]) -> bool:
    tier = _str_field(row, "proposition_tier")
    effect = _str_field(row, "legal_effect_type")
    return tier.lower() == PropositionTier.UNKNOWN.value or effect.lower() == LegalEffectType.UNKNOWN.value


def _coerce_source_record(row: dict[str, Any]) -> SourceRecord:
    enriched = dict(row)
    enriched.setdefault("jurisdiction", "UK")
    enriched.setdefault("citation", str(enriched.get("title") or enriched.get("id") or ""))
    enriched.setdefault("kind", "regulation")
    return SourceRecord.model_validate(enriched)


def _bundle_sources_and_fragments(
    bundle: dict[str, Any],
) -> tuple[dict[str, SourceRecord], dict[str, SourceFragment]]:
    sources = {
        str(row["id"]): _coerce_source_record(row)
        for row in (bundle.get("source_records") or bundle.get("sources") or [])
        if isinstance(row, dict) and row.get("id")
    }
    fragments = {
        str(row["id"]): SourceFragment.model_validate(row)
        for row in (bundle.get("source_fragments") or [])
        if isinstance(row, dict) and row.get("id")
    }
    return sources, fragments


def _default_topic_cluster_ids(bundle: dict[str, Any]) -> tuple[str, str]:
    topic_raw = bundle.get("topic") if isinstance(bundle.get("topic"), dict) else {}
    cluster_raw = (
        (bundle.get("clusters") or [None])[0]
        if isinstance(bundle.get("clusters"), list) and bundle.get("clusters")
        else {}
    )
    topic_id = str((topic_raw or {}).get("id") or "topic-export-acceptance")
    cluster_id = str((cluster_raw or {}).get("id") or "cluster-export-acceptance")
    return topic_id, cluster_id


def _load_proposition_rows(bundle: dict[str, Any], export_dir: Path | None) -> list[dict[str, Any]]:
    in_memory = [row for row in (bundle.get("propositions") or []) if isinstance(row, dict)]
    if in_memory:
        return in_memory
    if export_dir is not None:
        path = export_dir / "propositions.json"
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [row for row in raw if isinstance(row, dict)]
    return []


def _propositions_from_bundle(
    bundle: dict[str, Any],
    *,
    export_dir: Path | None = None,
) -> list[Proposition]:
    topic_id, cluster_id = _default_topic_cluster_ids(bundle)
    props: list[Proposition] = []
    for row in _load_proposition_rows(bundle, export_dir):
        enriched = dict(row)
        enriched.setdefault("topic_id", topic_id)
        enriched.setdefault("cluster_id", cluster_id)
        enriched.setdefault("legal_subject", "")
        enriched.setdefault("action", "")
        props.append(Proposition.model_validate(enriched))
    return props


def _write_propositions_to_bundle(bundle: dict[str, Any], propositions: list[Proposition]) -> None:
    bundle["propositions"] = [p.model_dump(mode="json") for p in propositions]


def _source_count(bundle: dict[str, Any]) -> int:
    sources = bundle.get("source_records") or bundle.get("sources") or []
    return len([s for s in sources if isinstance(s, dict)])


def _looks_conceptual_application_scope(prop: Proposition) -> bool:
    kind = classify_application_scope_kind(
        proposition_text=str(getattr(prop, "proposition_text", "") or ""),
        action=str(getattr(prop, "action", "") or ""),
        label=str(getattr(prop, "label", "") or ""),
        object_text=str(getattr(prop, "object_text", "") or ""),
        legal_subject=str(getattr(prop, "legal_subject", "") or ""),
        affected_subjects=list(getattr(prop, "affected_subjects", None) or []),
    )
    return kind in {"subject_object", "conditional"}


def backfill_evidence_from_alternate_meta(prop: Proposition) -> bool:
    meta = dict(prop.extraction_debug_meta or {})
    if str(meta.get("evidence_quote") or "").strip():
        return False
    for key in _EVIDENCE_ALTERNATE_META_KEYS:
        val = str(meta.get(key) or "").strip()
        if not val:
            continue
        meta["evidence_quote"] = val
        meta["evidence_repair_provenance"] = f"copied_from_{key}"
        assign_proposition_extraction_debug(prop, meta)
        return True
    notes_meta = resolve_extraction_meta_for_proposition(notes=str(prop.notes or ""))
    if isinstance(notes_meta, dict):
        val = str(notes_meta.get("evidence_quote") or "").strip()
        if val:
            meta["evidence_quote"] = val
            meta["evidence_repair_provenance"] = "copied_from_notes_meta"
            assign_proposition_extraction_debug(prop, meta)
            return True
    return False


def repair_debug_leakage_in_review_notes(prop: Proposition) -> bool:
    notes = str(prop.review_notes or "")
    if EXTRACTION_META_PREFIX not in notes:
        return False
    cleaned = notes.split(EXTRACTION_META_PREFIX, 1)[0].strip()
    prop.review_notes = cleaned or None
    meta = dict(prop.extraction_debug_meta or {})
    meta["debug_leakage_repair"] = "stripped_from_review_notes"
    assign_proposition_extraction_debug(prop, meta)
    return True


def repair_dangerous_legacy_relationship_key(prop: Proposition) -> bool:
    key = str(prop.cross_reference_key or "").strip()
    if not key.startswith(DANGEROUS_LEGACY_KEY_PREFIX):
        return False
    apply_relationship_keys(prop)
    repaired = not str(prop.cross_reference_key or "").startswith(DANGEROUS_LEGACY_KEY_PREFIX)
    if repaired:
        meta = dict(prop.extraction_debug_meta or {})
        meta["relationship_key_repair"] = "json_repair"
        assign_proposition_extraction_debug(prop, meta)
    return repaired


def repair_application_scope_territory(
    prop: Proposition,
    *,
    source: SourceRecord | None,
    instrument_extent: list[str],
) -> bool:
    effect = prop.legal_effect_type
    if effect is not LegalEffectType.APPLICATION_SCOPE and str(effect) != LegalEffectType.APPLICATION_SCOPE.value:
        return False
    if list(prop.territorial_application or []):
        return False

    places = derive_territorial_application(
        legal_effect_type=LegalEffectType.APPLICATION_SCOPE,
        proposition_text=str(getattr(prop, "proposition_text", "") or ""),
        action=str(getattr(prop, "action", "") or ""),
        affected_subjects=list(getattr(prop, "affected_subjects", None) or []),
        label=str(getattr(prop, "label", "") or ""),
        object_text=str(getattr(prop, "object_text", "") or ""),
        legal_subject=str(getattr(prop, "legal_subject", "") or ""),
        fragment_locator=str(getattr(prop, "fragment_locator", "") or ""),
        source_locator=str(getattr(prop, "source_locator", "") or ""),
        categories=list(getattr(prop, "categories", None) or []),
    )
    if places:
        prop.territorial_application = places
        meta = dict(prop.extraction_debug_meta or {})
        meta["territory_repair_provenance"] = "derived_from_proposition_text"
        meta["application_scope_kind"] = "territorial"
        assign_proposition_extraction_debug(prop, meta)
        return True

    source_extent = list(instrument_extent or [])
    if not source_extent and source is not None:
        from law_proposition_extractor_domain.proposition_jurisdiction import extent_from_source_metadata

        meta = getattr(source, "metadata", None)
        if isinstance(meta, dict):
            source_extent = extent_from_source_metadata(meta)

    if len(source_extent) != 1:
        return False
    territory = source_extent[0]
    if territory in _UK_WIDE_TERRITORIES:
        return False
    if _looks_conceptual_application_scope(prop):
        return False

    prop.territorial_application = [territory]
    meta = dict(prop.extraction_debug_meta or {})
    meta["territory_repair_provenance"] = "inherited_instrument_extent"
    meta["application_scope_kind"] = "territorial"
    assign_proposition_extraction_debug(prop, meta)
    return True


def detect_repairable_issues(
    *,
    bundle: dict[str, Any],
    export_dir: Path | None = None,
    verification: FreshExtractionVerificationReport | None = None,
    quality: PropositionQualityReport | None = None,
) -> list[RepairableIssue]:
    """Classify export issues into hard/soft repairable vs human review."""
    issues: list[RepairableIssue] = []
    root = Path(export_dir) if export_dir is not None else None

    completeness = assess_extraction_benchmark_completeness(bundle)
    if completeness.get("incomplete"):
        failed_jobs = completeness.get("extraction_job_failure_count")
        zero_sources = completeness.get("sources_with_zero_propositions") or []
        issues.append(
            RepairableIssue(
                issue_id="incomplete_extraction",
                kind="hard_repairable",
                check_id="incomplete_extraction",
                message=(
                    f"benchmark_verdict={completeness.get('benchmark_verdict', BENCHMARK_VERDICT_INCOMPLETE)}; "
                    f"failure_reason={completeness.get('failure_reason')}; "
                    f"failed_extraction_jobs={failed_jobs}; "
                    f"sources_with_zero_propositions={zero_sources}"
                ),
                details=dict(completeness),
            )
        )

    if verification is None and root is not None:
        verification = build_fresh_extraction_verification(root)

    if verification is not None:
        for finding in verification.findings:
            if finding.check_id in {
                "duplicate_proposition_id",
                "duplicate_proposition_key",
                "duplicate_proposition_version_id",
            }:
                issues.append(
                    RepairableIssue(
                        issue_id=finding.check_id,
                        kind="needs_human_review",
                        check_id=finding.check_id,
                        message=finding.message,
                        proposition_id=finding.proposition_id,
                        details=dict(finding.details),
                    )
                )
                continue
            if finding.severity == "error":
                kind: IssueKind = "hard_repairable"
                if finding.check_id in {
                    "missing_proposition_tier",
                    "missing_legal_effect_type",
                }:
                    kind = "soft_repairable"
                issues.append(
                    RepairableIssue(
                        issue_id=finding.check_id,
                        kind=kind,
                        check_id=finding.check_id,
                        message=finding.message,
                        proposition_id=finding.proposition_id,
                        details=dict(finding.details),
                    )
                )
            elif finding.check_id in {
                "missing_evidence_quote",
                "unknown_proposition_tier",
                "unknown_legal_effect_type",
                "categories_only_obligation_signal",
            }:
                issues.append(
                    RepairableIssue(
                        issue_id=finding.check_id,
                        kind="soft_repairable",
                        check_id=finding.check_id,
                        message=finding.message,
                        proposition_id=finding.proposition_id,
                        details=dict(finding.details),
                    )
                )

    props = bundle.get("propositions") or []
    for row in props:
        if not isinstance(row, dict):
            continue
        pid = _str_field(row, "id") or None
        label = _str_field(row, "label")
        if label.lower().startswith("definition:") and _is_unknown_tier_or_effect(row):
            issues.append(
                RepairableIssue(
                    issue_id="unknown_definition_row",
                    kind="soft_repairable",
                    check_id="unknown_definition_row",
                    message="definition-labelled row still classified as unknown",
                    proposition_id=pid,
                )
            )

    candidates = list_json_repair_candidates(bundle)
    for candidate in candidates:
        issues.append(
            RepairableIssue(
                issue_id="json_parse_failure",
                kind="hard_repairable",
                check_id="json_parse_failure",
                message="failed extraction chunk has raw model output for JSON repair",
                details={
                    "source_record_id": candidate.source_record_id,
                    "source_fragment_id": candidate.source_fragment_id,
                    "fragment_locator": candidate.fragment_locator,
                },
            )
        )

    anchor_coverage = summarize_export_fragment_anchor_coverage(bundle, propositions=props)
    for frag in anchor_coverage.get("fragments_with_missing_anchors") or []:
        if not isinstance(frag, dict):
            continue
        locator = str(frag.get("fragment_locator") or "")
        for missing in frag.get("missing") or []:
            if not isinstance(missing, dict):
                continue
            severity = str(missing.get("severity") or "important")
            if severity == "diagnostic":
                continue
            label = str(missing.get("label") or missing.get("anchor_id") or "anchor")
            issues.append(
                RepairableIssue(
                    issue_id=f"missing_anchor_{label}",
                    kind="needs_human_review" if severity == "critical" else "soft_repairable",
                    check_id="missing_fragment_anchor",
                    message=f"dense fragment {locator!r} missing {severity} anchor: {label}",
                    details={"fragment_locator": locator, "anchor": missing, "severity": severity},
                )
            )

    if quality is not None:
        for finding in quality.findings:
            if finding.check_id == "scope_application_conflict":
                issues.append(
                    RepairableIssue(
                        issue_id=finding.check_id,
                        kind="soft_repairable",
                        check_id=finding.check_id,
                        message=finding.message,
                        proposition_id=finding.proposition_id,
                    )
                )
            elif finding.check_id == "generic_label_still_present":
                issues.append(
                    RepairableIssue(
                        issue_id=finding.check_id,
                        kind="soft_repairable",
                        check_id=finding.check_id,
                        message=finding.message,
                        proposition_id=finding.proposition_id,
                    )
                )

    return issues


def apply_json_repair_pass(bundle: dict[str, Any]) -> RepairPassStats:
    stats = RepairPassStats(pass_name="json_repair")
    candidates = list_json_repair_candidates(bundle)
    stats.attempted = len(candidates)
    if not candidates:
        return stats

    outcomes = []
    validated_rows_by_key: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    repair_methods_by_key: dict[tuple[str, str | None], str] = {}
    for candidate in candidates:
        outcome = attempt_json_repair_for_candidate(bundle=bundle, candidate=candidate)
        outcomes.append(outcome)
        if outcome.repaired:
            stats.succeeded += 1
            key = candidate.job_key()
            validated_rows_by_key[key] = list(outcome.validated_rows)
            repair_methods_by_key[key] = outcome.repair_method or "json_repair"

    if stats.succeeded:
        merged = apply_json_repairs_to_bundle(
            bundle=bundle,
            outcomes=outcomes,
            validated_rows_by_key=validated_rows_by_key,
            repair_methods_by_key=repair_methods_by_key,
        )
        bundle.clear()
        bundle.update(merged)
    stats.details = {"candidates": len(candidates), "repaired_chunks": stats.succeeded}
    return stats


def apply_classifier_and_relationship_pass(
    bundle: dict[str, Any],
) -> RepairPassStats:
    stats = RepairPassStats(pass_name="classifier_repair")
    sources, _fragments = _bundle_sources_and_fragments(bundle)
    props = _propositions_from_bundle(bundle, export_dir=None)
    stats.attempted = len(props)
    before_unknown = sum(1 for p in props if _prop_is_unknown(p))
    normalise_extracted_propositions(props, source_by_id=sources)
    after_unknown = sum(1 for p in props if _prop_is_unknown(p))
    stats.succeeded = max(0, before_unknown - after_unknown)
    _write_propositions_to_bundle(bundle, props)
    stats.details = {
        "unknown_before": before_unknown,
        "unknown_after": after_unknown,
    }
    return stats


def _prop_is_unknown(prop: Proposition) -> bool:
    return (
        prop.proposition_tier == PropositionTier.UNKNOWN
        or prop.legal_effect_type == LegalEffectType.UNKNOWN
    )


def apply_evidence_repair_pass(bundle: dict[str, Any]) -> RepairPassStats:
    stats = RepairPassStats(pass_name="evidence_repair")
    sources, fragments = _bundle_sources_and_fragments(bundle)
    props = _propositions_from_bundle(bundle)
    for prop in props:
        meta = resolve_extraction_meta_for_proposition(
            notes=str(prop.notes or ""),
            extraction_debug_meta=prop.extraction_debug_meta,
        )
        if isinstance(meta, dict) and str(meta.get("evidence_quote") or "").strip():
            continue
        stats.attempted += 1
        if backfill_evidence_from_alternate_meta(prop):
            stats.succeeded += 1
            continue
        hygiene = apply_export_proposition_hygiene(
            [prop],
            source_by_id=sources,
            fragment_by_id=fragments,
        )
        if int(hygiene.get("evidence_backfilled") or 0) > 0:
            stats.succeeded += 1
        elif not str((prop.extraction_debug_meta or {}).get("evidence_quote") or "").strip():
            meta = dict(prop.extraction_debug_meta or {})
            meta["evidence_repair_provenance"] = "still_missing_after_repair"
            assign_proposition_extraction_debug(prop, meta)
    _write_propositions_to_bundle(bundle, props)
    return stats


def apply_territory_repair_pass(bundle: dict[str, Any]) -> RepairPassStats:
    from law_proposition_extractor_domain.proposition_jurisdiction import build_instrument_extent_by_source

    stats = RepairPassStats(pass_name="territory_repair")
    sources, _fragments = _bundle_sources_and_fragments(bundle)
    props = _propositions_from_bundle(bundle)
    extent_by_source = build_instrument_extent_by_source(props)
    for prop in props:
        if prop.legal_effect_type != LegalEffectType.APPLICATION_SCOPE:
            continue
        if list(prop.territorial_application or []):
            continue
        stats.attempted += 1
        source = sources.get(str(prop.source_record_id or ""))
        if repair_application_scope_territory(
            prop,
            source=source,
            instrument_extent=extent_by_source.get(str(prop.source_record_id or ""), []),
        ):
            stats.succeeded += 1
    _write_propositions_to_bundle(bundle, props)
    return stats


def apply_metadata_hygiene_pass(bundle: dict[str, Any]) -> RepairPassStats:
    stats = RepairPassStats(pass_name="metadata_hygiene")
    props = _propositions_from_bundle(bundle)
    for prop in props:
        stats.attempted += 1
        changed = False
        if repair_debug_leakage_in_review_notes(prop):
            changed = True
        if repair_dangerous_legacy_relationship_key(prop):
            changed = True
        if changed:
            stats.succeeded += 1
    _write_propositions_to_bundle(bundle, props)
    return stats


def apply_deterministic_repair_passes(
    bundle: dict[str, Any],
    *,
    max_attempts: int = 2,
) -> list[RepairPassStats]:
    """Run safe deterministic repair passes with re-normalisation between rounds."""
    all_stats: list[RepairPassStats] = []
    passes = (
        apply_json_repair_pass,
        apply_classifier_and_relationship_pass,
        apply_evidence_repair_pass,
        apply_territory_repair_pass,
        apply_metadata_hygiene_pass,
        apply_classifier_and_relationship_pass,
    )
    for _attempt in range(max(1, max_attempts)):
        round_changed = False
        for pass_fn in passes:
            stats = pass_fn(bundle)
            all_stats.append(stats)
            if stats.succeeded > 0:
                round_changed = True
        if not round_changed:
            break
    return all_stats


def apply_coverage_llm_repair(
    export_dir: Path,
    *,
    bundle: dict[str, Any],
    repair_mode: RepairMode,
    max_propositions: int = 16,
    use_llm: bool = True,
) -> tuple[dict[str, Any], RepairPassStats]:
    """Targeted fragment repair for dense fragments with missing anchors."""
    stats = RepairPassStats(pass_name="coverage_repair")
    summary_before = summarize_export_fragment_anchor_coverage(bundle)
    to_repair = fragments_needing_llm_repair(summary_before)
    stats.details = {
        "fragments_needing_repair": len(to_repair),
        "missing_anchor_count_before": summary_before.get("missing_anchor_count", 0),
    }
    if not to_repair:
        return {}, stats
    if repair_mode not in {"llm", "both"}:
        stats.details["skipped"] = "repair_mode_excludes_llm"
        return {}, stats
    if not use_llm:
        stats.details["skipped"] = "use_llm_disabled"
        return {}, stats

    stats.attempted = len(to_repair)
    current_bundle: dict[str, Any] = bundle
    repaired = 0
    for frag in to_repair:
        sid = str(frag.get("source_record_id") or "").strip()
        locator = str(frag.get("fragment_locator") or "regulation:2")
        if not sid:
            continue
        try:
            current_bundle = run_fragment_repair_pipeline(
                export_dir=export_dir,
                output_dir=export_dir,
                source_id=sid,
                locator=locator,
                extraction_mode="frontier",
                max_propositions=max_propositions,
                use_llm=True,
            )
            repaired += 1
        except (ValueError, OSError) as exc:
            stats.details.setdefault("errors", []).append(
                {"source_record_id": sid, "fragment_locator": locator, "error": str(exc)}
            )

    summary_after = summarize_export_fragment_anchor_coverage(current_bundle)
    stats.succeeded = repaired
    stats.details["missing_anchor_count_after"] = summary_after.get("missing_anchor_count", 0)
    stats.details["fragment_anchor_coverage_after"] = summary_after
    return current_bundle, stats


def compute_acceptance_status(
    *,
    proposition_count: int,
    verification: FreshExtractionVerificationReport,
    quality: PropositionQualityReport,
    issues_after: list[RepairableIssue],
    anchor_summary: dict[str, Any],
) -> tuple[AcceptanceStatus, list[str], list[str], list[str]]:
    hard_failures: list[str] = []
    human_review: list[str] = []
    acceptance_warnings: list[str] = []

    if proposition_count == 0:
        hard_failures.append("no_propositions")

    if any(i.check_id == "incomplete_extraction" for i in issues_after):
        hard_failures.append(BENCHMARK_VERDICT_INCOMPLETE)

    source_cov = verification.source_coverage
    if source_cov is not None and source_cov.sources_with_zero_propositions:
        if BENCHMARK_VERDICT_INCOMPLETE not in hard_failures:
            hard_failures.append(BENCHMARK_VERDICT_INCOMPLETE)

    error_findings = [f for f in verification.findings if f.severity == "error"]
    duplicate_only_errors = bool(error_findings) and all(
        f.check_id.startswith("duplicate_") for f in error_findings
    )
    if duplicate_only_errors:
        for finding in error_findings:
            human_review.append(finding.message)
    elif verification.hard_failure or verification.error_count > 0:
        hard_failures.append("verification_errors")

    json_unrepaired = [i for i in issues_after if i.check_id == "json_parse_failure"]
    if json_unrepaired:
        hard_failures.append("unrepaired_json_parse_failures")

    dangerous = quality.error_count and any(
        f.check_id == "dangerous_legacy_relationship_key" for f in quality.findings
    )
    leakage = any(f.check_id == "debug_leakage" for f in quality.findings)
    if dangerous:
        hard_failures.append("dangerous_legacy_relationship_keys")
    if leakage:
        hard_failures.append("debug_metadata_leakage")

    unknown_count = verification.counts.get("unknown_tier", 0) + verification.counts.get(
        "unknown_effect", 0
    )
    unknown_rate = (unknown_count / (2 * proposition_count)) if proposition_count else 1.0
    if unknown_rate > UNKNOWN_CLASSIFICATION_RATE_THRESHOLD:
        human_review.append(
            f"unknown_classifications_above_threshold ({unknown_rate:.2%})"
        )

    missing_evidence = int(verification.evidence_health.get("missing_evidence_quote_count") or 0)

    for issue in issues_after:
        if issue.kind != "needs_human_review" or issue.message in human_review:
            continue
        if issue.check_id == "missing_fragment_anchor":
            continue
        human_review.append(issue.message)

    missing_critical = int(anchor_summary.get("missing_critical_count") or 0)
    missing_important = int(anchor_summary.get("missing_important_count") or 0)
    missing_diagnostic = int(anchor_summary.get("missing_diagnostic_count") or 0)

    if missing_critical > 0:
        human_review.append(f"dense_fragment_critical_anchors_missing ({missing_critical})")
    if missing_important > 0:
        acceptance_warnings.append(
            f"dense_fragment_important_anchors_missing ({missing_important})"
        )
    if missing_diagnostic > 0:
        acceptance_warnings.append(
            f"dense_fragment_diagnostic_anchors_missing ({missing_diagnostic})"
        )
    npp = anchor_summary.get("npp_reg2") if isinstance(anchor_summary.get("npp_reg2"), dict) else {}
    if int(npp.get("reg2_proposition_count") or anchor_summary.get("reg2_proposition_count") or 0) > 0:
        for name, info in (npp.get("anchors") or anchor_summary.get("anchors") or {}).items():
            if isinstance(info, dict) and not info.get("present"):
                human_review.append(f"missing_definition_anchor:{name}")

    if missing_evidence > 0:
        unmarked = _count_evidence_missing_without_provenance(verification.export_dir)
        if unmarked:
            human_review.append(
                f"evidence_missing_without_provenance ({unmarked})"
            )

    if verification.warning_count > UNRESOLVED_VALIDATION_WARNING_THRESHOLD:
        human_review.append(
            f"validation_warnings_above_threshold ({verification.warning_count})"
        )

    if source_cov is not None:
        for low in source_cov.sources_with_low_proposition_count:
            sid = str(low.get("source_record_id") or "")
            current = low.get("proposition_count")
            baseline = low.get("baseline_proposition_count")
            human_review.append(
                f"source_low_proposition_count:{sid} ({current}/{baseline})"
            )

    if hard_failures:
        return "failed", hard_failures, human_review, acceptance_warnings

    if human_review:
        return "needs_review", hard_failures, human_review, acceptance_warnings

    if verification.warning_count > 0 or quality.warning_count > 0 or acceptance_warnings:
        if missing_evidence <= MISSING_EVIDENCE_ACCEPTED_WITH_WARNINGS_MAX:
            return "accepted_with_warnings", hard_failures, human_review, acceptance_warnings
        return "needs_review", hard_failures, human_review + [
            f"missing_evidence_quotes ({missing_evidence})"
        ], acceptance_warnings

    return "accepted", hard_failures, human_review, acceptance_warnings


def _count_evidence_missing_without_provenance(export_dir: str) -> int:
    path = Path(export_dir) / "propositions.json"
    if not path.is_file():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        return 0
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        meta = resolve_extraction_meta_for_proposition(
            notes=_str_field(row, "notes") or None,
            extraction_debug_meta=row.get("extraction_debug_meta")
            if isinstance(row.get("extraction_debug_meta"), dict)
            else None,
        )
        quote = str((meta or {}).get("evidence_quote") or "").strip()
        if quote:
            continue
        provenance = str((meta or {}).get("evidence_repair_provenance") or "").strip()
        if not provenance:
            count += 1
    return count


def load_slurry_export_propositions_from_bundle_rows(export_dir: str) -> list[dict[str, Any]]:
    path = Path(export_dir) / "propositions.json"
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


def render_export_acceptance_md(report: ExportAcceptanceReport) -> str:
    lines = [
        "# Export acceptance",
        "",
        f"**Generated:** {report.generated_at}",
        f"**Export:** `{report.export_path}`",
        f"**Status:** `{report.acceptance_status}`",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"| --- | ---: |",
        f"| Sources | {report.source_count} |",
        f"| Propositions | {report.proposition_count} |",
        f"| Verification errors | {report.verification_errors} |",
        f"| Warnings | {report.warning_count} |",
        f"| Repairs attempted | {report.repairs_attempted} |",
        f"| Repairs succeeded | {report.repairs_succeeded} |",
        "",
    ]
    if report.source_coverage:
        cov = report.source_coverage
        lines.extend(
            [
                "## Source coverage",
                "",
                f"| Metric | Value |",
                f"| --- | ---: |",
                f"| Expected sources | {cov.get('expected_source_count', 0)} |",
                f"| Sources with propositions | {cov.get('sources_with_propositions', 0)} |",
                f"| Sources with zero propositions | {len(cov.get('sources_with_zero_propositions') or [])} |",
                "",
            ]
        )
        props_by_source = cov.get("propositions_by_source")
        if isinstance(props_by_source, dict) and props_by_source:
            lines.extend(["### Propositions by source", ""])
            for title, count in props_by_source.items():
                lines.append(f"- {title}: {count}")
            lines.append("")
        compliance_by_source = cov.get("compliance_relevant_by_source")
        if isinstance(compliance_by_source, dict) and compliance_by_source:
            lines.extend(["### Compliance-relevant by source", ""])
            for title, count in compliance_by_source.items():
                lines.append(f"- {title}: {count}")
            lines.append("")
    if report.remaining_hard_failures:
        lines.extend(["## Remaining hard failures", ""])
        for item in report.remaining_hard_failures:
            lines.append(f"- {item}")
        lines.append("")
    if report.remaining_human_review_warnings:
        lines.extend(["## Human review", ""])
        for item in report.remaining_human_review_warnings:
            lines.append(f"- {item}")
        lines.append("")
    anchor_cov = report.npp_reg2_anchors if isinstance(report.npp_reg2_anchors, dict) else {}
    if anchor_cov:
        missing_by = anchor_cov.get("missing_by_severity") if isinstance(anchor_cov.get("missing_by_severity"), dict) else {}
        lines.extend(
            [
                "## Anchor coverage",
                "",
                "| Severity | Missing |",
                "| --- | ---: |",
                f"| Critical | {missing_by.get('critical', anchor_cov.get('missing_critical_count', 0))} |",
                f"| Important | {missing_by.get('important', anchor_cov.get('missing_important_count', 0))} |",
                f"| Diagnostic | {missing_by.get('diagnostic', anchor_cov.get('missing_diagnostic_count', 0))} |",
                "",
            ]
        )
        top_critical = anchor_cov.get("top_fragments_missing_critical") or []
        if top_critical:
            lines.extend(["### Top fragments — missing critical anchors", ""])
            for item in top_critical:
                if not isinstance(item, dict):
                    continue
                loc = item.get("fragment_locator", "?")
                count = item.get("missing_count", 0)
                sample = ", ".join(item.get("sample_missing") or [])
                lines.append(f"- `{loc}` ({count}): {sample}")
            lines.append("")
        top_important = anchor_cov.get("top_fragments_missing_important") or []
        if top_important:
            lines.extend(["### Top fragments — missing important anchors", ""])
            for item in top_important:
                if not isinstance(item, dict):
                    continue
                loc = item.get("fragment_locator", "?")
                count = item.get("missing_count", 0)
                sample = ", ".join(item.get("sample_missing") or [])
                lines.append(f"- `{loc}` ({count}): {sample}")
            lines.append("")
        noise = anchor_cov.get("diagnostic_table_noise_summary")
        if isinstance(noise, dict) and any(
            int(noise.get(k) or 0) > 0
            for k in ("livestock_category_missing", "numeric_table_cell_missing", "schedule_table_noise_count")
        ):
            lines.extend(
                [
                    "### Diagnostic table noise (report only)",
                    "",
                    f"- Livestock category tokens missing: {noise.get('livestock_category_missing', 0)}",
                    f"- Numeric table cells missing: {noise.get('numeric_table_cell_missing', 0)}",
                    f"- Schedule/table duplicate noise: {noise.get('schedule_table_noise_count', 0)}",
                    "",
                ]
            )
    if report.remaining_acceptance_warnings:
        lines.extend(["## Acceptance warnings", ""])
        for item in report.remaining_acceptance_warnings:
            lines.append(f"- {item}")
        lines.append("")
    if report.repair_passes:
        lines.extend(["## Repair passes", "", "| Pass | Attempted | Succeeded |", "| --- | ---: | ---: |"])
        for p in report.repair_passes:
            lines.append(f"| {p.pass_name} | {p.attempted} | {p.succeeded} |")
        lines.append("")
    return "\n".join(lines)


def write_export_acceptance_artifacts(
    export_dir: str | Path,
    report: ExportAcceptanceReport,
) -> tuple[Path, Path]:
    root = Path(export_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / ACCEPTANCE_JSON_FILENAME
    md_path = root / ACCEPTANCE_MD_FILENAME
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_export_acceptance_md(report), encoding="utf-8")
    return md_path, json_path


def acceptance_exit_code(report: ExportAcceptanceReport, *, strict: bool = False) -> int:
    if report.acceptance_status == "failed":
        return 1
    if strict and report.acceptance_status != "accepted":
        return 1
    return 0


def run_export_acceptance_workflow(
    *,
    export_dir: str | Path,
    output_dir: str | Path | None = None,
    bundle: dict[str, Any] | None = None,
    auto_repair: bool = True,
    acceptance_report: bool = True,
    repair_mode: RepairMode = "deterministic",
    max_repair_attempts: int = 2,
    strict_acceptance: bool = False,
    use_llm_coverage: bool = True,
) -> ExportAcceptanceReport:
    """Orchestrate normalisation, quality gates, repair passes, verification, and acceptance."""
    work_dir = Path(output_dir or export_dir).expanduser().resolve()
    source_dir = Path(export_dir).expanduser().resolve()
    in_place = work_dir == source_dir

    if bundle is None:
        if not (source_dir / "propositions.json").is_file():
            raise FileNotFoundError(f"No propositions.json in {source_dir}")
        bundle = _enrich_bundle_from_export_files(load_exported_bundle(source_dir), source_dir)
    else:
        bundle = copy.deepcopy(bundle)

    if not in_place:
        work_dir.mkdir(parents=True, exist_ok=True)

    props = _propositions_from_bundle(bundle, export_dir=source_dir)
    sources, fragments = _bundle_sources_and_fragments(bundle)
    if auto_repair:
        normalise_extracted_propositions(props, source_by_id=sources)
        _write_propositions_to_bundle(bundle, props)

    quality_initial = run_proposition_quality_gates(props, newly_normalised=auto_repair)
    verification_initial = build_fresh_extraction_verification(
        source_dir if in_place else work_dir,
        propositions=[p.model_dump(mode="json") for p in props],
    )
    issues_before = detect_repairable_issues(
        bundle=bundle,
        verification=verification_initial,
        quality=quality_initial,
    )

    repair_passes: list[RepairPassStats] = []
    repairs_attempted = 0
    repairs_succeeded = 0

    if auto_repair and repair_mode in {"deterministic", "both"}:
        repair_passes.extend(
            apply_deterministic_repair_passes(bundle, max_attempts=max_repair_attempts)
        )

    export_bundle(bundle, output_dir=str(work_dir))

    if auto_repair and repair_mode in {"llm", "both"} and use_llm_coverage:
        llm_bundle, coverage_stats = apply_coverage_llm_repair(
            work_dir,
            bundle=bundle,
            repair_mode=repair_mode,
            use_llm=use_llm_coverage,
        )
        repair_passes.append(coverage_stats)
        if llm_bundle:
            bundle = llm_bundle

    for stats in repair_passes:
        repairs_attempted += stats.attempted
        repairs_succeeded += stats.succeeded

    props = _propositions_from_bundle(bundle, export_dir=work_dir)
    if auto_repair:
        normalise_extracted_propositions(props, source_by_id=sources)
        _write_propositions_to_bundle(bundle, props)

    quality_final = run_proposition_quality_gates(props, newly_normalised=auto_repair)
    write_normalisation_quality_artifacts(work_dir, quality_final)

    export_bundle(bundle, output_dir=str(work_dir))

    verification_final = build_fresh_extraction_verification(work_dir)
    write_fresh_extraction_verification(work_dir, verification_final)

    review = build_review_from_export_dir(
        work_dir,
        propositions=[p.model_dump(mode="json") for p in props],
        normalise=False,
    )
    write_normalised_proposition_review(work_dir, review)

    issues_after = detect_repairable_issues(
        bundle=bundle,
        export_dir=work_dir,
        verification=verification_final,
        quality=quality_final,
    )
    props_rows = bundle.get("propositions") or []
    anchor_summary = summarize_export_fragment_anchor_coverage(bundle, propositions=props_rows)

    status, hard_failures, human_review, acceptance_warnings = compute_acceptance_status(
        proposition_count=len(props),
        verification=verification_final,
        quality=quality_final,
        issues_after=issues_after,
        anchor_summary=anchor_summary,
    )

    report = ExportAcceptanceReport(
        export_path=str(work_dir),
        generated_at=_utc_now_iso_z(),
        source_count=_source_count(bundle),
        proposition_count=len(props),
        verification_errors=verification_final.error_count,
        warning_count=verification_final.warning_count + quality_final.warning_count,
        repairs_attempted=repairs_attempted,
        repairs_succeeded=repairs_succeeded,
        remaining_hard_failures=hard_failures,
        remaining_human_review_warnings=human_review,
        remaining_acceptance_warnings=acceptance_warnings,
        acceptance_status=status,
        repair_passes=repair_passes,
        issues_before=issues_before,
        issues_after=issues_after,
        verification_initial={
            "error_count": verification_initial.error_count,
            "warning_count": verification_initial.warning_count,
            "hard_failure": verification_initial.hard_failure,
        },
        verification_final=verification_final.to_dict(),
        normalisation_quality=quality_final.to_dict(),
        npp_reg2_anchors=anchor_summary,
        source_coverage=(
            verification_final.source_coverage.to_dict()
            if verification_final.source_coverage is not None
            else {}
        ),
    )

    if acceptance_report:
        write_export_acceptance_artifacts(work_dir, report)

    return report


def print_acceptance_console_summary(report: ExportAcceptanceReport) -> None:
    print(f"Export acceptance: {report.acceptance_status.upper()}")
    print(f"  export: {report.export_path}")
    print(f"  propositions: {report.proposition_count}")
    print(f"  verification errors: {report.verification_errors}")
    print(f"  repairs: {report.repairs_succeeded}/{report.repairs_attempted}")
    if report.remaining_hard_failures:
        print(f"  hard failures: {', '.join(report.remaining_hard_failures)}")
    if report.remaining_human_review_warnings:
        print(f"  human review: {len(report.remaining_human_review_warnings)} item(s)")
