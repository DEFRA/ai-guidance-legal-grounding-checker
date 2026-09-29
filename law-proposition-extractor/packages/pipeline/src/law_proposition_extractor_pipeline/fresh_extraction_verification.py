"""Deterministic verification for fresh one-source Law Proposition Extractor extraction exports (no LLM)."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import LegalEffectType, PropositionTier, is_generic_display_label
from law_proposition_extractor_domain.proposition_notes import EXTRACTION_META_PREFIX, resolve_extraction_meta_for_proposition
from law_proposition_extractor_domain.proposition_relationship_keys import build_relationship_keys

from .proposition_quality_gates import (
    DANGEROUS_LEGACY_KEY_PREFIX,
    check_proposition,
    load_normalisation_quality_payload,
)
from .extraction_fragment_repair import NPP_2015_SOURCE_ID
from .fragment_anchor_coverage import summarize_export_fragment_anchor_coverage
from .export_source_coverage import ExportSourceCoverageSummary, assess_export_source_coverage
from .proposition_export_uniqueness import (
    find_duplicate_proposition_ids,
    find_duplicate_proposition_keys,
    find_duplicate_proposition_version_ids,
)
from .slurry_normalisation_acceptance import load_slurry_export_propositions

VERIFICATION_MD_FILENAME = "FRESH_EXTRACTION_VERIFICATION.md"
VERIFICATION_JSON_FILENAME = "fresh_extraction_verification.json"

_PROMPT_LAB_ANCHORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("regulation 8", re.compile(r"^regulation\s+8\b", re.IGNORECASE)),
    ("regulation 17", re.compile(r"^regulation\s+17\b", re.IGNORECASE)),
    ("Schedule 1", re.compile(r"schedule\s+1\b", re.IGNORECASE)),
    ("regulation 36", re.compile(r"^regulation\s+36\b", re.IGNORECASE)),
    ("regulation 6", re.compile(r"^regulation\s+6\b", re.IGNORECASE)),
)

_NUMERIC_TABLE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:kg|hectare|hectares|tonnes?|metres?|m)\b",
    re.IGNORECASE,
)

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class VerificationFinding:
    check_id: str
    severity: Severity
    message: str
    proposition_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "message": self.message,
            "proposition_id": self.proposition_id,
            "details": self.details,
        }


@dataclass
class PromptLabAnchorSummary:
    anchor: str
    proposition_count: int
    legal_effect_types: list[str]
    compliance_relevant_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor,
            "proposition_count": self.proposition_count,
            "legal_effect_types": self.legal_effect_types,
            "compliance_relevant_count": self.compliance_relevant_count,
        }


@dataclass
class FreshExtractionVerificationReport:
    export_dir: str
    generated_at: str
    proposition_count: int
    error_count: int
    warning_count: int
    hard_failure: bool
    export_presence: dict[str, Any]
    counts: dict[str, Any]
    prompt_lab_anchors: list[PromptLabAnchorSummary]
    findings: list[VerificationFinding] = field(default_factory=list)
    evidence_health: dict[str, Any] = field(default_factory=dict)
    trace_health: dict[str, Any] = field(default_factory=dict)
    source_coverage: ExportSourceCoverageSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "export_dir": self.export_dir,
            "generated_at": self.generated_at,
            "proposition_count": self.proposition_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "hard_failure": self.hard_failure,
            "export_presence": self.export_presence,
            "counts": self.counts,
            "prompt_lab_anchors": [a.to_dict() for a in self.prompt_lab_anchors],
            "evidence_health": self.evidence_health,
            "trace_health": self.trace_health,
            "source_coverage": self.source_coverage.to_dict() if self.source_coverage else {},
            "findings": [f.to_dict() for f in self.findings],
        }


def _utc_now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _str_field(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _bool_field(row: dict[str, Any], key: str) -> bool | None:
    val = row.get(key)
    if val is True or val is False:
        return val
    return None


def _categories(row: dict[str, Any]) -> list[str]:
    raw = row.get("categories")
    if not isinstance(raw, list):
        return []
    return [str(c) for c in raw]


def _locator(row: dict[str, Any]) -> str:
    return _str_field(row, "fragment_locator") or _str_field(row, "article_reference")


def _is_missing_classification(value: str) -> bool:
    return not value.strip()


def _is_unknown_classification(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized == PropositionTier.UNKNOWN.value


def _semantic_key_applicable(row: dict[str, Any]) -> bool:
    bundle = build_relationship_keys(row)
    return bundle.semantically_linkable


def _notes_contain_meta(text: str) -> bool:
    return EXTRACTION_META_PREFIX in text


def _categories_only_obligation_signal(row: dict[str, Any]) -> bool:
    cats = _categories(row)
    if "obligation" not in cats:
        return False
    tier = _str_field(row, "proposition_tier")
    effect = _str_field(row, "legal_effect_type")
    if _is_missing_classification(tier) and _is_missing_classification(effect):
        return True
    if _is_unknown_classification(tier) and _is_unknown_classification(effect):
        compliance = _bool_field(row, "is_compliance_relevant")
        return compliance is True
    return False


def _looks_table_or_numeric(row: dict[str, Any]) -> bool:
    locator = _locator(row).lower()
    text = _str_field(row, "proposition_text")
    if "schedule" in locator and re.search(r"table|paragraph", locator):
        return True
    return bool(_NUMERIC_TABLE_RE.search(text))


def _load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_manifest(export_dir: Path) -> dict[str, Any]:
    raw = _load_json(export_dir / "manifest.json")
    return raw if isinstance(raw, dict) else {}


def _export_presence_checks(export_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    props_path = export_dir / "propositions.json"
    model_path = export_dir / "MODEL.md"
    norm_json = export_dir / "normalisation_quality.json"
    norm_md = export_dir / "NORMALISATION_QUALITY.md"
    traces_path = export_dir / "proposition_extraction_traces.json"

    expects_norm = bool(manifest.get("proposition_count")) or norm_json.is_file()
    expects_traces = bool(manifest.get("has_proposition_extraction_traces")) or traces_path.is_file()

    return {
        "propositions_json": props_path.is_file(),
        "model_md": model_path.is_file(),
        "normalisation_quality_expected": expects_norm,
        "normalisation_quality_json": norm_json.is_file(),
        "normalisation_quality_md": norm_md.is_file(),
        "extraction_traces_expected": expects_traces,
        "proposition_extraction_traces_json": traces_path.is_file(),
        "manifest_json": (export_dir / "manifest.json").is_file(),
    }


def _build_counts(rows: list[dict[str, Any]], sources_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_source: Counter[str] = Counter()
    by_tier: Counter[str] = Counter()
    by_effect: Counter[str] = Counter()
    compliance_relevant = 0
    comparison_anchor = 0
    unknown_tier = 0
    unknown_effect = 0
    application_scope = 0
    cross_reference = 0
    definition = 0
    table_or_numeric = 0

    for row in rows:
        sid = _str_field(row, "source_record_id") or "unknown"
        title = str((sources_by_id.get(sid) or {}).get("title") or sid)
        by_source[title] += 1
        tier = _str_field(row, "proposition_tier") or "missing"
        effect = _str_field(row, "legal_effect_type") or "missing"
        by_tier[tier] += 1
        by_effect[effect] += 1
        if _is_unknown_classification(tier):
            unknown_tier += 1
        if _is_unknown_classification(effect):
            unknown_effect += 1
        if _bool_field(row, "is_compliance_relevant") is True:
            compliance_relevant += 1
        if _bool_field(row, "is_comparison_anchor") is True:
            comparison_anchor += 1
        if effect == LegalEffectType.APPLICATION_SCOPE.value:
            application_scope += 1
        if effect == LegalEffectType.CROSS_REFERENCE.value:
            cross_reference += 1
        if effect == LegalEffectType.DEFINITION.value:
            definition += 1
        if _looks_table_or_numeric(row):
            table_or_numeric += 1

    return {
        "total": len(rows),
        "by_source": dict(sorted(by_source.items())),
        "by_proposition_tier": dict(sorted(by_tier.items())),
        "by_legal_effect_type": dict(sorted(by_effect.items())),
        "compliance_relevant": compliance_relevant,
        "comparison_anchor": comparison_anchor,
        "unknown_tier": unknown_tier,
        "unknown_effect": unknown_effect,
        "application_scope": application_scope,
        "cross_reference": cross_reference,
        "definition": definition,
        "table_or_numeric_looking": table_or_numeric,
    }


def _prompt_lab_anchor_summaries(rows: list[dict[str, Any]]) -> list[PromptLabAnchorSummary]:
    npp_rows = [r for r in rows if _str_field(r, "source_record_id") == NPP_2015_SOURCE_ID]
    if not npp_rows:
        npp_rows = rows
    summaries: list[PromptLabAnchorSummary] = []
    for label, pattern in _PROMPT_LAB_ANCHORS:
        matched = [r for r in npp_rows if pattern.search(_locator(r))]
        effects = sorted({_str_field(r, "legal_effect_type") or "missing" for r in matched})
        compliance = sum(1 for r in matched if _bool_field(r, "is_compliance_relevant") is True)
        summaries.append(
            PromptLabAnchorSummary(
                anchor=label,
                proposition_count=len(matched),
                legal_effect_types=effects,
                compliance_relevant_count=compliance,
            )
        )
    return summaries


def _trace_health(
    export_dir: Path,
    rows: list[dict[str, Any]],
    *,
    traces: list[dict[str, Any]] | None,
    jobs: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    traces = traces or []
    jobs = jobs or []
    trace_by_prop: dict[str, dict[str, Any]] = {}
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        pid = _str_field(trace, "proposition_id")
        if pid:
            trace_by_prop[pid] = trace

    missing_evidence: list[str] = []
    validation_errors: list[str] = []
    trace_warnings: list[str] = []
    low_confidence: list[str] = []
    repaired_json: list[str] = []

    for row in rows:
        pid = _str_field(row, "id")
        meta = resolve_extraction_meta_for_proposition(
            notes=_str_field(row, "notes") or None,
            extraction_debug_meta=row.get("extraction_debug_meta")
            if isinstance(row.get("extraction_debug_meta"), dict)
            else None,
        )
        quote = ""
        if isinstance(meta, dict):
            quote = _str_field(meta, "evidence_quote")
            val_errs = meta.get("validation_errors")
            if isinstance(val_errs, list) and val_errs:
                validation_errors.append(pid)
            warns = meta.get("trace_warnings")
            if isinstance(warns, list) and warns:
                trace_warnings.append(pid)
            confidence = _str_field(meta, "model_confidence").lower()
            if confidence == "low":
                low_confidence.append(pid)
            for key in ("json_repair_applied", "json_repair_method", "repair_method"):
                if meta.get(key):
                    repaired_json.append(pid)
                    break

        if not quote:
            missing_evidence.append(pid)

        trace = trace_by_prop.get(pid)
        if isinstance(trace, dict):
            if _str_field(trace, "confidence").lower() == "low" and pid not in low_confidence:
                low_confidence.append(pid)
            t_val = trace.get("validation_errors")
            if isinstance(t_val, list) and t_val and pid not in validation_errors:
                validation_errors.append(pid)
            t_warn = trace.get("warnings")
            if isinstance(t_warn, list) and t_warn and pid not in trace_warnings:
                trace_warnings.append(pid)
            signals = trace.get("signals")
            if isinstance(signals, dict):
                for key in ("json_repair_applied", "json_repair_method", "repair_method"):
                    if signals.get(key) and pid not in repaired_json:
                        repaired_json.append(pid)
                        break

    repaired_jobs = 0
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("json_repair_applied") or job.get("json_repair_method"):
            repaired_jobs += 1

    return {
        "missing_evidence_quote_count": len(missing_evidence),
        "missing_evidence_quote_ids": missing_evidence[:50],
        "validation_error_count": len(validation_errors),
        "validation_error_ids": validation_errors[:50],
        "trace_warning_count": len(trace_warnings),
        "trace_warning_ids": trace_warnings[:50],
        "low_confidence_count": len(low_confidence),
        "low_confidence_ids": low_confidence[:50],
        "repaired_json_proposition_count": len(repaired_json),
        "repaired_json_proposition_ids": repaired_json[:50],
        "repaired_json_job_count": repaired_jobs,
        "has_extraction_traces_file": (export_dir / "proposition_extraction_traces.json").is_file(),
    }


def _generic_label_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if is_generic_display_label(_str_field(row, "label")))


def build_fresh_extraction_verification(
    export_dir: str | Path,
    *,
    propositions: list[dict[str, Any]] | None = None,
    sources_by_id: dict[str, dict[str, Any]] | None = None,
) -> FreshExtractionVerificationReport:
    """Run all verification checks against an export directory."""
    root = Path(export_dir).resolve()
    manifest = _load_manifest(root)
    presence = _export_presence_checks(root, manifest)
    findings: list[VerificationFinding] = []

    if not presence["propositions_json"]:
        report = FreshExtractionVerificationReport(
            export_dir=str(root),
            generated_at=_utc_now_iso_z(),
            proposition_count=0,
            error_count=1,
            warning_count=0,
            hard_failure=True,
            export_presence=presence,
            counts={"total": 0},
            prompt_lab_anchors=[],
            findings=[
                VerificationFinding(
                    check_id="missing_propositions_json",
                    severity="error",
                    message="propositions.json is missing",
                )
            ],
        )
        return report

    rows = propositions if propositions is not None else load_slurry_export_propositions(root)
    if sources_by_id is None:
        from .normalised_proposition_review import load_export_sources

        sources_by_id = load_export_sources(root)

    if not rows:
        findings.append(
            VerificationFinding(
                check_id="no_propositions",
                severity="error",
                message="export contains zero propositions",
            )
        )

    for dup in find_duplicate_proposition_ids(rows):
        findings.append(
            VerificationFinding(
                check_id="duplicate_proposition_id",
                severity="error",
                message=f"duplicate proposition id {dup['id']} appears {dup['count']} times",
                details=dup,
            )
        )
    for dup in find_duplicate_proposition_keys(rows):
        findings.append(
            VerificationFinding(
                check_id="duplicate_proposition_key",
                severity=str(dup.get("severity") or "error"),
                message=(
                    f"duplicate proposition_key {dup['proposition_key']!r} "
                    f"within source {dup['source_record_id']!r} ({dup['count']} rows)"
                ),
                details=dup,
            )
        )
    for dup in find_duplicate_proposition_version_ids(rows):
        findings.append(
            VerificationFinding(
                check_id="duplicate_proposition_version_id",
                severity="error",
                message=(
                    f"duplicate proposition_version_id {dup['proposition_version_id']!r} "
                    f"({dup['count']} propositions)"
                ),
                details=dup,
            )
        )

    if not presence["model_md"]:
        findings.append(
            VerificationFinding(
                check_id="missing_model_md",
                severity="warning",
                message="MODEL.md is missing",
            )
        )
    if presence["normalisation_quality_expected"] and not presence["normalisation_quality_json"]:
        findings.append(
            VerificationFinding(
                check_id="missing_normalisation_quality",
                severity="warning",
                message="normalisation quality artifacts expected but normalisation_quality.json is missing",
            )
        )
    if presence["extraction_traces_expected"] and not presence["proposition_extraction_traces_json"]:
        findings.append(
            VerificationFinding(
                check_id="missing_extraction_traces",
                severity="warning",
                message="proposition_extraction_traces.json expected but missing",
            )
        )

    traces_raw = _load_json(root / "proposition_extraction_traces.json")
    traces = traces_raw if isinstance(traces_raw, list) else []
    jobs_raw = _load_json(root / "proposition_extraction_jobs.json")
    jobs = jobs_raw if isinstance(jobs_raw, list) else []

    for row in rows:
        pid = _str_field(row, "id") or "proposition-unknown"
        tier = _str_field(row, "proposition_tier")
        effect = _str_field(row, "legal_effect_type")

        if _is_missing_classification(tier):
            findings.append(
                VerificationFinding(
                    check_id="missing_proposition_tier",
                    severity="error",
                    message="proposition missing proposition_tier after normalisation",
                    proposition_id=pid,
                )
            )
        elif _is_unknown_classification(tier):
            findings.append(
                VerificationFinding(
                    check_id="unknown_proposition_tier",
                    severity="warning",
                    message="proposition_tier is unknown",
                    proposition_id=pid,
                    details={"proposition_tier": tier},
                )
            )

        if _is_missing_classification(effect):
            findings.append(
                VerificationFinding(
                    check_id="missing_legal_effect_type",
                    severity="error",
                    message="proposition missing legal_effect_type after normalisation",
                    proposition_id=pid,
                )
            )
        elif _is_unknown_classification(effect):
            findings.append(
                VerificationFinding(
                    check_id="unknown_legal_effect_type",
                    severity="warning",
                    message="legal_effect_type is unknown",
                    proposition_id=pid,
                    details={"legal_effect_type": effect},
                )
            )

        if not _str_field(row, "source_jurisdiction"):
            findings.append(
                VerificationFinding(
                    check_id="missing_source_jurisdiction",
                    severity="error",
                    message="source_jurisdiction is missing",
                    proposition_id=pid,
                )
            )

        for bool_key in ("is_compliance_relevant", "is_comparison_anchor"):
            if _bool_field(row, bool_key) is None:
                findings.append(
                    VerificationFinding(
                        check_id=f"missing_{bool_key}",
                        severity="error",
                        message=f"{bool_key} must be a boolean",
                        proposition_id=pid,
                    )
                )

        if "review_notes" not in row:
            findings.append(
                VerificationFinding(
                    check_id="missing_review_notes_field",
                    severity="warning",
                    message="review_notes field is absent",
                    proposition_id=pid,
                )
            )

        debug = row.get("extraction_debug_meta")
        if not isinstance(debug, dict) or not debug:
            findings.append(
                VerificationFinding(
                    check_id="missing_extraction_debug_meta",
                    severity="warning",
                    message="extraction_debug_meta is missing or empty",
                    proposition_id=pid,
                )
            )

        if _semantic_key_applicable(row) and not _str_field(row, "semantic_comparison_key"):
            findings.append(
                VerificationFinding(
                    check_id="missing_semantic_comparison_key",
                    severity="warning",
                    message="semantic_comparison_key expected but missing",
                    proposition_id=pid,
                    details={"legal_effect_type": effect},
                )
            )

        notes = _str_field(row, "notes")
        if _notes_contain_meta(notes):
            findings.append(
                VerificationFinding(
                    check_id="legacy_meta_in_notes",
                    severity="warning",
                    message="notes still contains judit_extraction_meta",
                    proposition_id=pid,
                )
            )

        review_notes = row.get("review_notes")
        if isinstance(review_notes, str) and _notes_contain_meta(review_notes):
            findings.append(
                VerificationFinding(
                    check_id="debug_leakage",
                    severity="error",
                    message="extraction debug metadata leaked into review_notes",
                    proposition_id=pid,
                )
            )

        xref = _str_field(row, "cross_reference_key")
        if xref.startswith(DANGEROUS_LEGACY_KEY_PREFIX):
            findings.append(
                VerificationFinding(
                    check_id="dangerous_legacy_relationship_key",
                    severity="error",
                    message="dangerous legacy cross_reference_key retained",
                    proposition_id=pid,
                    details={"cross_reference_key": xref},
                )
            )

        if _categories_only_obligation_signal(row):
            findings.append(
                VerificationFinding(
                    check_id="categories_only_obligation_signal",
                    severity="warning",
                    message="categories lists obligation but normalised tier/effect are unknown",
                    proposition_id=pid,
                    details={"categories": _categories(row)},
                )
            )

        for gate in check_proposition(row, newly_normalised=True):
            severity: Severity = "error" if gate.severity == "error" else "warning"
            if gate.check_id == "debug_leakage" and any(
                f.check_id == "debug_leakage" and f.proposition_id == pid for f in findings
            ):
                continue
            if gate.check_id == "dangerous_legacy_relationship_key" and any(
                f.check_id == "dangerous_legacy_relationship_key" and f.proposition_id == pid
                for f in findings
            ):
                continue
            findings.append(
                VerificationFinding(
                    check_id=gate.check_id,
                    severity=severity,
                    message=gate.message,
                    proposition_id=gate.proposition_id,
                    details=dict(gate.details),
                )
            )

    trace_health = _trace_health(root, rows, traces=traces, jobs=jobs)
    if trace_health["missing_evidence_quote_count"]:
        findings.append(
            VerificationFinding(
                check_id="missing_evidence_quote",
                severity="warning",
                message="one or more propositions lack evidence_quote in extraction metadata",
                details={
                    "count": trace_health["missing_evidence_quote_count"],
                    "sample_ids": trace_health["missing_evidence_quote_ids"][:10],
                },
            )
        )
    if trace_health["validation_error_count"]:
        findings.append(
            VerificationFinding(
                check_id="validation_errors",
                severity="warning",
                message="one or more propositions have validation errors in extraction metadata",
                details={
                    "count": trace_health["validation_error_count"],
                    "sample_ids": trace_health["validation_error_ids"][:10],
                },
            )
        )
    if trace_health["trace_warning_count"]:
        findings.append(
            VerificationFinding(
                check_id="trace_warnings",
                severity="warning",
                message="one or more propositions have trace warnings in extraction metadata",
                details={
                    "count": trace_health["trace_warning_count"],
                    "sample_ids": trace_health["trace_warning_ids"][:10],
                },
            )
        )
    if trace_health["low_confidence_count"]:
        findings.append(
            VerificationFinding(
                check_id="low_confidence",
                severity="warning",
                message="one or more propositions have low model confidence",
                details={
                    "count": trace_health["low_confidence_count"],
                    "sample_ids": trace_health["low_confidence_ids"][:10],
                },
            )
        )
    if trace_health["repaired_json_proposition_count"] or trace_health["repaired_json_job_count"]:
        findings.append(
            VerificationFinding(
                check_id="repaired_json",
                severity="warning",
                message="JSON repair was applied during extraction",
                details={
                    "proposition_count": trace_health["repaired_json_proposition_count"],
                    "job_count": trace_health["repaired_json_job_count"],
                    "sample_ids": trace_health["repaired_json_proposition_ids"][:10],
                },
            )
        )

    generic_labels = _generic_label_count(rows)
    if rows and generic_labels / len(rows) > 0.15:
        findings.append(
            VerificationFinding(
                check_id="high_generic_label_rate",
                severity="warning",
                message="unusually high rate of generic display labels",
                details={"generic_label_count": generic_labels, "total": len(rows)},
            )
        )

    norm_payload = load_normalisation_quality_payload(export_dir=root)
    counts = _build_counts(rows, sources_by_id or {})
    anchors = _prompt_lab_anchor_summaries(rows)
    source_coverage = assess_export_source_coverage(
        root,
        rows,
        sources_by_id=sources_by_id or {},
    )
    for sid in source_coverage.sources_with_zero_propositions:
        title = source_coverage.source_titles.get(sid, sid)
        findings.append(
            VerificationFinding(
                check_id="source_zero_propositions",
                severity="error",
                message=f"expected source {title!r} has zero propositions",
                details={"source_record_id": sid, "source_title": title},
            )
        )
    for sid in source_coverage.sources_with_zero_compliance_relevant:
        title = source_coverage.source_titles.get(sid, sid)
        findings.append(
            VerificationFinding(
                check_id="source_zero_compliance_relevant",
                severity="warning",
                message=f"source {title!r} has propositions but zero compliance-relevant rows",
                details={"source_record_id": sid, "source_title": title},
            )
        )
    for low in source_coverage.sources_with_low_proposition_count:
        findings.append(
            VerificationFinding(
                check_id="source_low_proposition_count",
                severity="warning",
                message=(
                    f"source {low.get('source_title')!r} has unexpectedly low proposition count "
                    f"({low.get('proposition_count')} vs baseline {low.get('baseline_proposition_count')})"
                ),
                details=low,
            )
        )

    if (root / "source_fragments.json").is_file() or any(
        _str_field(row, "source_record_id") == NPP_2015_SOURCE_ID for row in rows
    ):
        from .linting import load_exported_bundle

        try:
            bundle = load_exported_bundle(root)
            bundle["propositions"] = rows
            coverage = summarize_export_fragment_anchor_coverage(bundle, propositions=rows)
        except ValueError:
            coverage = {"npp_reg2": {"anchors": {}}, "missing_anchor_count": 0}

        npp = coverage.get("npp_reg2") if isinstance(coverage.get("npp_reg2"), dict) else {}
        missing = [
            label
            for label, detail in (npp.get("anchors") or {}).items()
            if isinstance(detail, dict) and not detail.get("present")
        ]
        if missing:
            findings.append(
                VerificationFinding(
                    check_id="npp_reg2_definition_anchors",
                    severity="warning",
                    message=(
                        "NPP 2015 regulation 2 missing expected definition anchors: "
                        + ", ".join(missing)
                    ),
                    details={
                        "reg2_proposition_count": npp.get("reg2_proposition_count"),
                        "anchors": npp.get("anchors"),
                        "fragment_anchor_coverage": coverage,
                    },
                )
            )
        elif int(coverage.get("missing_critical_count") or 0) > 0:
            findings.append(
                VerificationFinding(
                    check_id="dense_fragment_anchor_coverage",
                    severity="warning",
                    message=(
                        "dense fragment(s) missing critical legal anchors before acceptance "
                        f"({coverage.get('missing_critical_count')} critical, "
                        f"{coverage.get('missing_important_count', 0)} important, "
                        f"{coverage.get('missing_diagnostic_count', 0)} diagnostic)"
                    ),
                    details=coverage,
                )
            )
        elif int(coverage.get("missing_important_count") or 0) > 0:
            findings.append(
                VerificationFinding(
                    check_id="dense_fragment_anchor_coverage",
                    severity="warning",
                    message=(
                        "dense fragment(s) missing important legal anchors "
                        f"({coverage.get('missing_important_count')} important, "
                        f"{coverage.get('missing_diagnostic_count', 0)} diagnostic only)"
                    ),
                    details=coverage,
                )
            )
        elif int(coverage.get("missing_diagnostic_count") or 0) > 0:
            findings.append(
                VerificationFinding(
                    check_id="dense_fragment_diagnostic_anchors",
                    severity="warning",
                    message=(
                        "dense fragment(s) have diagnostic anchor gaps only "
                        f"({coverage.get('missing_diagnostic_count')} diagnostic — report only)"
                    ),
                    details={
                        "missing_diagnostic_count": coverage.get("missing_diagnostic_count"),
                        "diagnostic_table_noise_summary": coverage.get(
                            "diagnostic_table_noise_summary"
                        ),
                    },
                )
            )

    deduped: list[VerificationFinding] = []
    seen: set[tuple[str, str | None]] = set()
    for finding in findings:
        key = (finding.check_id, finding.proposition_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    findings = deduped

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    hard_failure = errors > 0 or not presence["propositions_json"] or counts["total"] == 0

    return FreshExtractionVerificationReport(
        export_dir=str(root),
        generated_at=_utc_now_iso_z(),
        proposition_count=len(rows),
        error_count=errors,
        warning_count=warnings,
        hard_failure=hard_failure,
        export_presence={**presence, "normalisation_quality_embedded": norm_payload is not None},
        counts=counts,
        prompt_lab_anchors=anchors,
        findings=findings,
        source_coverage=source_coverage,
        evidence_health={
            "missing_evidence_quote_count": trace_health["missing_evidence_quote_count"],
            "validation_error_count": trace_health["validation_error_count"],
            "trace_warning_count": trace_health["trace_warning_count"],
            "low_confidence_count": trace_health["low_confidence_count"],
            "repaired_json_proposition_count": trace_health["repaired_json_proposition_count"],
            "repaired_json_job_count": trace_health["repaired_json_job_count"],
        },
        trace_health=trace_health,
    )


def render_fresh_extraction_verification_md(report: FreshExtractionVerificationReport) -> str:
    """Human-readable verification summary."""
    status = "FAIL" if report.hard_failure else "PASS"
    lines = [
        "# Fresh extraction export verification",
        "",
        f"**Generated:** {report.generated_at}",
        f"**Export:** `{report.export_dir}`",
        f"**Status:** {status}",
        "",
        "## Summary",
        "",
        f"| Measure | Value |",
        f"| --- | ---: |",
        f"| Propositions | {report.proposition_count} |",
        f"| Errors | {report.error_count} |",
        f"| Warnings | {report.warning_count} |",
        "",
        "## Export presence",
        "",
        "| Artifact | Present |",
        "| --- | --- |",
    ]
    for key, present in sorted(report.export_presence.items()):
        if key.endswith("_expected"):
            continue
        lines.append(f"| `{key}` | {'yes' if present else 'no'} |")

    lines.extend(["", "## Counts", ""])
    for section_key in (
        "total",
        "compliance_relevant",
        "comparison_anchor",
        "unknown_tier",
        "unknown_effect",
        "application_scope",
        "cross_reference",
        "definition",
        "table_or_numeric_looking",
    ):
        lines.append(f"- **{section_key}:** {report.counts.get(section_key, 0)}")

    for hist_key in ("by_source", "by_proposition_tier", "by_legal_effect_type"):
        hist = report.counts.get(hist_key)
        if isinstance(hist, dict) and hist:
            lines.extend(["", f"### {hist_key}", ""])
            for name, count in hist.items():
                lines.append(f"- {name}: {count}")

    if report.source_coverage is not None:
        cov = report.source_coverage
        lines.extend(
            [
                "",
                "## Source coverage",
                "",
                f"- **expected source count:** {cov.expected_source_count}",
                f"- **sources with propositions:** {cov.sources_with_propositions}",
                f"- **sources with zero propositions:** {len(cov.sources_with_zero_propositions)}",
            ]
        )
        if cov.sources_with_zero_propositions:
            for sid in cov.sources_with_zero_propositions:
                lines.append(f"  - {cov.source_titles.get(sid, sid)} (`{sid}`)")
        if cov.propositions_by_source:
            lines.extend(["", "### Propositions by source", ""])
            for title, count in cov.propositions_by_source.items():
                lines.append(f"- {title}: {count}")
        if cov.compliance_relevant_by_source:
            lines.extend(["", "### Compliance-relevant by source", ""])
            for title, count in cov.compliance_relevant_by_source.items():
                lines.append(f"- {title}: {count}")

    lines.extend(["", "## Evidence / debug health", ""])
    for key, value in sorted(report.evidence_health.items()):
        lines.append(f"- **{key}:** {value}")

    if report.prompt_lab_anchors:
        lines.extend(
            [
                "",
                "## Prompt-lab anchors (NPP 2015 locators)",
                "",
                "| Locator | Propositions | Compliance-relevant | Effect types |",
                "| --- | ---: | ---: | --- |",
            ]
        )
        for anchor in report.prompt_lab_anchors:
            effects = ", ".join(anchor.legal_effect_types) if anchor.legal_effect_types else "—"
            lines.append(
                f"| {anchor.anchor} | {anchor.proposition_count} | "
                f"{anchor.compliance_relevant_count} | {effects} |"
            )

    if report.findings:
        lines.extend(["", "## Findings", ""])
        for finding in report.findings[:150]:
            pid = f" `{finding.proposition_id}`" if finding.proposition_id else ""
            lines.append(
                f"- **{finding.severity}**{pid} (`{finding.check_id}`): {finding.message}"
            )
        if len(report.findings) > 150:
            lines.append(f"- … and {len(report.findings) - 150} more (see JSON)")
    else:
        lines.append("")
        lines.append("No findings.")
    lines.append("")
    return "\n".join(lines)


def write_fresh_extraction_verification(
    export_dir: str | Path,
    report: FreshExtractionVerificationReport,
) -> tuple[Path, Path]:
    """Write FRESH_EXTRACTION_VERIFICATION.md and fresh_extraction_verification.json."""
    root = Path(export_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / VERIFICATION_JSON_FILENAME
    md_path = root / VERIFICATION_MD_FILENAME
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_fresh_extraction_verification_md(report), encoding="utf-8")
    return md_path, json_path


def verification_exit_code(report: FreshExtractionVerificationReport, *, strict: bool = False) -> int:
    if report.hard_failure:
        return 1
    if strict and report.warning_count > 0:
        return 1
    return 0


def print_verification_console_summary(report: FreshExtractionVerificationReport) -> None:
    status = "FAIL" if report.hard_failure else "PASS"
    print(f"Fresh extraction verification: {status}")
    print(f"  export: {report.export_dir}")
    print(f"  propositions: {report.proposition_count}")
    print(f"  errors: {report.error_count}")
    print(f"  warnings: {report.warning_count}")
    counts = report.counts
    print(
        "  compliance-relevant: "
        f"{counts.get('compliance_relevant', 0)} | comparison-anchor: {counts.get('comparison_anchor', 0)}"
    )
    print(
        "  unknown tier/effect: "
        f"{counts.get('unknown_tier', 0)}/{counts.get('unknown_effect', 0)}"
    )
    if report.source_coverage is not None:
        cov = report.source_coverage
        print(
            "  source coverage: "
            f"{cov.sources_with_propositions}/{cov.expected_source_count} sources with propositions"
        )
        if cov.sources_with_zero_propositions:
            print(f"  sources with zero propositions: {len(cov.sources_with_zero_propositions)}")
    if report.prompt_lab_anchors:
        print("  prompt-lab anchors:")
        for anchor in report.prompt_lab_anchors:
            print(
                f"    - {anchor.anchor}: {anchor.proposition_count} props, "
                f"{anchor.compliance_relevant_count} compliance-relevant"
            )
