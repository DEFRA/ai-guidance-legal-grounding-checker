"""Law Discovery Law Proposition Extractor intake bundle loading, filtering, and case materialisation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .sources.search import _source_id_from_legislation_url

BUNDLE_SECTION_KEYS: tuple[str, ...] = (
    "principal_sources",
    "amending_sources",
    "commencement_sources",
    "correction_sources",
    "revocation_sources",
    "interpretive_sources",
    "guidance_sources",
    "form_sources",
    "contextual_sources",
    "rejected_sources",
)

SELECTABLE_SECTIONS: tuple[str, ...] = (
    "principal_sources",
    "amending_sources",
    "revocation_sources",
)

DEFAULT_INTAKE_BUNDLE_PATH = "source-bundle-law-proposition-extractor-intake.json"


class SourceBundleIntakeError(ValueError):
    """Invalid or unsupported Law Discovery source bundle for Law Proposition Extractor intake."""


class FullLawDiscoveryBundleRejectedError(SourceBundleIntakeError):
    """Full reviewed Law Discovery bundle passed without ``--allow-full-law-discovery-bundle``."""


@dataclass(frozen=True)
class IntakeBundleSelection:
    principal_only: bool = True
    include_amendments: bool = False
    include_revocations: bool = False
    max_sources: int | None = None
    allow_full_law_discovery_bundle: bool = False


@dataclass(frozen=True)
class IntakeBundlePlan:
    bundle_id: str
    category_id: str
    intake_kind: str | None
    filter_policy: dict[str, Any] | None
    excluded_counts: dict[str, int] | None
    section_counts: dict[str, int]
    selected_by_role: dict[str, int]
    selected_source_count: int
    estimated_extraction_batches_lower_bound: int
    selected_sections: list[str]
    log_lines: list[str] = field(default_factory=list)


def resolve_case_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path.cwd() / candidate


def load_source_bundle(path: str | Path) -> dict[str, Any]:
    resolved = resolve_case_path(path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SourceBundleIntakeError("Source bundle must be a JSON object.")
    if "principal_sources" not in payload:
        raise SourceBundleIntakeError(
            "Source bundle must contain a 'principal_sources' array (Law Discovery source bundle shape)."
        )
    if not isinstance(payload.get("principal_sources"), list):
        raise SourceBundleIntakeError("'principal_sources' must be an array.")
    return payload


def _bundle_metadata(bundle: dict[str, Any]) -> dict[str, Any]:
    meta = bundle.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _intake_metadata(bundle: dict[str, Any]) -> dict[str, Any]:
    intake = _bundle_metadata(bundle).get("intake")
    return intake if isinstance(intake, dict) else {}


def is_law_proposition_extractor_intake_bundle(bundle: dict[str, Any]) -> bool:
    return str(_intake_metadata(bundle).get("kind") or "") == "judit_intake"


def bundle_has_excluded_populations(bundle: dict[str, Any]) -> bool:
    contextual = bundle.get("contextual_sources")
    rejected = bundle.get("rejected_sources")
    return bool(contextual) or bool(rejected)


def is_full_ada_bundle(bundle: dict[str, Any]) -> bool:
    if is_law_proposition_extractor_intake_bundle(bundle):
        return False
    return bundle_has_excluded_populations(bundle)


def _section_counts(bundle: dict[str, Any]) -> dict[str, int]:
    counts = {key: len(bundle.get(key) or []) for key in BUNDLE_SECTION_KEYS}
    relationships = bundle.get("relationships")
    counts["relationships"] = len(relationships) if isinstance(relationships, list) else 0
    return counts


def _build_intake_log_lines(bundle: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    intake = _intake_metadata(bundle)
    kind = str(intake.get("kind") or "").strip()
    if kind:
        lines.append(f"Law Discovery intake kind: {kind}")
    filter_policy = intake.get("filter_policy")
    if isinstance(filter_policy, dict) and filter_policy:
        lines.append(f"Law Discovery filter policy: {json.dumps(filter_policy, sort_keys=True)}")
    excluded = intake.get("excluded_counts")
    if isinstance(excluded, dict) and excluded:
        lines.append(f"Law Discovery excluded counts: {json.dumps(excluded, sort_keys=True)}")
    return lines


def resolve_case_output_paths(output: str | Path) -> tuple[Path, Path]:
    """Resolve a Law Proposition Extractor case directory and the ``case.json`` path to write."""
    resolved = resolve_case_path(output)
    if resolved.suffix == ".json":
        return resolved.parent, resolved
    return resolved, resolved / "case.json"


def write_materialized_case(case_payload: dict[str, Any], output: str | Path) -> Path:
    case_dir, case_json = resolve_case_output_paths(output)
    case_dir.mkdir(parents=True, exist_ok=True)
    case_json.write_text(json.dumps(case_payload, indent=2) + "\n", encoding="utf-8")
    return case_json


def list_selected_source_titles(
    bundle: dict[str, Any],
    selection: IntakeBundleSelection,
) -> list[str]:
    sources, _ = select_case_sources(bundle, selection)
    return [str(s.get("title") or s.get("id") or "").strip() for s in sources if s.get("title") or s.get("id")]


def format_intake_summary_lines(
    bundle: dict[str, Any],
    plan: IntakeBundlePlan,
    *,
    selection: IntakeBundleSelection | None = None,
) -> list[str]:
    """Human-readable intake summary for CLI dry-run and pre-run banners."""
    counts = plan.section_counts
    lines = [
        f"category_id: {plan.category_id}",
        f"principal_sources: {counts.get('principal_sources', 0)}",
        f"amending_sources: {counts.get('amending_sources', 0)}",
        f"revocation_sources: {counts.get('revocation_sources', 0)}",
        f"contextual_sources: {counts.get('contextual_sources', 0)}",
        f"rejected_sources: {counts.get('rejected_sources', 0)}",
        f"relationships: {counts.get('relationships', 0)}",
    ]
    if plan.intake_kind:
        lines.append(f"intake.kind: {plan.intake_kind}")
    filter_policy = plan.filter_policy if isinstance(plan.filter_policy, dict) else {}
    for key in (
        "priority_policy",
        "exclude_jurisdictions",
        "max_principal_sources",
        "principal_only",
    ):
        if key in filter_policy:
            lines.append(f"{key}: {filter_policy[key]}")
    if filter_policy and not any(k in filter_policy for k in ("priority_policy", "principal_only")):
        lines.append(f"intake filter policy: {json.dumps(filter_policy, sort_keys=True)}")
    if selection is not None:
        lines.append(f"selected_sources: {plan.selected_source_count}")
        lines.append(f"selected_sections: {', '.join(plan.selected_sections)}")
        if selection.include_amendments or selection.include_revocations:
            lines.append(
                "selection flags: "
                f"principal_only={selection.principal_only}, "
                f"include_amendments={selection.include_amendments}, "
                f"include_revocations={selection.include_revocations}"
            )
    return lines


def resolve_selected_sections(selection: IntakeBundleSelection) -> list[str]:
    if selection.include_amendments or selection.include_revocations:
        sections = ["principal_sources"]
        if selection.include_amendments:
            sections.append("amending_sources")
        if selection.include_revocations:
            sections.append("revocation_sources")
        return sections
    if selection.principal_only:
        return ["principal_sources"]
    return ["principal_sources"]


def validate_bundle_for_ingestion(
    bundle: dict[str, Any],
    selection: IntakeBundleSelection,
) -> None:
    if bundle_has_excluded_populations(bundle) and not selection.allow_full_law_discovery_bundle:
        contextual_n = len(bundle.get("contextual_sources") or [])
        rejected_n = len(bundle.get("rejected_sources") or [])
        raise FullLawDiscoveryBundleRejectedError(
            "Full reviewed Law Discovery bundle detected "
            f"({contextual_n} contextual source(s), {rejected_n} rejected source(s)). "
            "Law Proposition Extractor expects an Law Discovery Law Proposition Extractor intake bundle (metadata.intake.kind=judit_intake) "
            "or pass --allow-full-law-discovery-bundle to acknowledge filtered ingestion."
        )
    if is_full_ada_bundle(bundle) and not selection.allow_full_law_discovery_bundle:
        raise FullLawDiscoveryBundleRejectedError(
            "Full reviewed Law Discovery bundle detected (missing metadata.intake.kind=judit_intake). "
            "Pass --allow-full-law-discovery-bundle to proceed with explicit source selection."
        )


def _primary_jurisdiction(entry: dict[str, Any]) -> str:
    extent = entry.get("jurisdiction_extent")
    if isinstance(extent, list) and extent:
        return str(extent[0])
    return "UK"


def ada_entry_to_case_source(
    entry: dict[str, Any],
    *,
    bundle_role: str,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    uri = str(entry.get("canonical_uri") or "").strip()
    authority_source_id = _source_id_from_legislation_url(uri)
    if not authority_source_id:
        source_id = str(entry.get("source_id") or "")
        raise SourceBundleIntakeError(
            f"Cannot resolve legislation.gov.uk authority_source_id for Law Discovery source {source_id!r} "
            f"from canonical_uri {uri!r}."
        )

    register_id = _bundle_metadata(bundle).get("source_register_id")
    ada_meta: dict[str, Any] = {
        "source_id": entry.get("source_id"),
        "bundle_role": bundle_role,
        "bundle_id": bundle.get("bundle_id"),
        "category_id": bundle.get("category_id"),
        "relationship_to_category": entry.get("relationship_to_category"),
        "review_status": entry.get("review_status"),
        "source_type": entry.get("source_type"),
        "canonical_uri": uri,
    }
    if register_id:
        ada_meta["source_register_id"] = register_id
    ai_triage = entry.get("ai_triage")
    if isinstance(ai_triage, dict):
        ada_meta["ai_triage"] = ai_triage

    citation = entry.get("citation")
    if not citation:
        parts = authority_source_id.split("/")
        citation = f"{parts[0].upper()} {parts[1]}/{parts[2]}" if len(parts) == 3 else authority_source_id

    return {
        "id": str(entry.get("source_id") or authority_source_id),
        "authority": "legislation_gov_uk",
        "authority_source_id": authority_source_id,
        "title": str(entry.get("title") or authority_source_id),
        "jurisdiction": _primary_jurisdiction(entry),
        "citation": str(citation),
        "kind": str(entry.get("source_type") or "instrument"),
        "provenance": "law_discovery.law_proposition_extractor_intake",
        "review_status": str(entry.get("review_status") or "accepted"),
        "metadata": {"ada_source_bundle": ada_meta},
    }


def select_case_sources(
    bundle: dict[str, Any],
    selection: IntakeBundleSelection,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    validate_bundle_for_ingestion(bundle, selection)
    selected_sections = resolve_selected_sections(selection)
    selected: list[dict[str, Any]] = []
    selected_by_role: dict[str, int] = {}

    for section in selected_sections:
        rows = bundle.get(section) or []
        if not isinstance(rows, list):
            raise SourceBundleIntakeError(f"{section} must be an array when present.")
        role = section.removesuffix("_sources")
        count = 0
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            selected.append(ada_entry_to_case_source(entry, bundle_role=role, bundle=bundle))
            count += 1
        selected_by_role[role] = count

    if selection.max_sources is not None:
        cap = max(int(selection.max_sources), 0)
        selected = selected[:cap]
        truncated = sum(selected_by_role.values()) - len(selected)
        if truncated > 0:
            selected_by_role = {"truncated_total": len(selected), "truncated_from": truncated}

    return selected, selected_by_role


def _category_label(category_id: str) -> str:
    return category_id.replace("_", " ").strip() or "Law Discovery category"


def materialize_case_from_intake_bundle(
    bundle: dict[str, Any],
    selection: IntakeBundleSelection,
) -> dict[str, Any]:
    sources, _selected_by_role = select_case_sources(bundle, selection)
    category_id = str(bundle.get("category_id") or "ada_category")
    label = _category_label(category_id)
    intake = _intake_metadata(bundle)
    return {
        "topic": {
            "name": label,
            "description": f"Law Discovery Law Proposition Extractor intake for category {category_id}.",
            "subject_tags": ["law-discovery", "law-proposition-extractor-intake", category_id],
        },
        "cluster": {
            "name": category_id,
            "description": f"Cluster scoped to Law Discovery category {category_id}.",
        },
        "sources": sources,
        "comparison": {"jurisdiction_a": "EU", "jurisdiction_b": "UK"},
        "ada_intake_ref": {
            "bundle_id": str(bundle.get("bundle_id") or ""),
            "category_id": category_id,
            "intake_kind": str(intake.get("kind") or ""),
            "source_register_id": _bundle_metadata(bundle).get("source_register_id"),
            "selection": {
                "principal_only": selection.principal_only,
                "include_amendments": selection.include_amendments,
                "include_revocations": selection.include_revocations,
                "max_sources": selection.max_sources,
            },
        },
    }


def plan_intake_bundle_dry_run(
    bundle: dict[str, Any],
    selection: IntakeBundleSelection,
    *,
    avg_fragments_per_source: int = 3,
) -> IntakeBundlePlan:
    sources, selected_by_role = select_case_sources(bundle, selection)
    intake = _intake_metadata(bundle)
    filter_policy = intake.get("filter_policy")
    excluded = intake.get("excluded_counts")
    selected_sections = resolve_selected_sections(selection)
    source_count = len(sources)
    est_batches = max(0, source_count * max(int(avg_fragments_per_source), 1))
    return IntakeBundlePlan(
        bundle_id=str(bundle.get("bundle_id") or ""),
        category_id=str(bundle.get("category_id") or ""),
        intake_kind=str(intake.get("kind") or "") or None,
        filter_policy=filter_policy if isinstance(filter_policy, dict) else None,
        excluded_counts=excluded if isinstance(excluded, dict) else None,
        section_counts=_section_counts(bundle),
        selected_by_role=selected_by_role,
        selected_source_count=source_count,
        estimated_extraction_batches_lower_bound=est_batches,
        selected_sections=selected_sections,
        log_lines=_build_intake_log_lines(bundle),
    )


def intake_plan_to_dict(plan: IntakeBundlePlan) -> dict[str, Any]:
    return {
        "bundle_id": plan.bundle_id,
        "category_id": plan.category_id,
        "intake_kind": plan.intake_kind,
        "filter_policy": plan.filter_policy,
        "excluded_counts": plan.excluded_counts,
        "section_counts": plan.section_counts,
        "selected_by_role": plan.selected_by_role,
        "selected_source_count": plan.selected_source_count,
        "selected_sections": plan.selected_sections,
        "estimated_extraction_batches_lower_bound": plan.estimated_extraction_batches_lower_bound,
        "log_lines": plan.log_lines,
    }


def detect_input_kind(payload: dict[str, Any]) -> Literal["judit_intake", "full_ada", "case", "unknown"]:
    if "topic" in payload and "cluster" in payload:
        return "case"
    if "principal_sources" in payload:
        if is_law_proposition_extractor_intake_bundle(payload):
            return "judit_intake"
        if is_full_ada_bundle(payload):
            return "full_ada"
        return "judit_intake" if not bundle_has_excluded_populations(payload) else "full_ada"
    return "unknown"
