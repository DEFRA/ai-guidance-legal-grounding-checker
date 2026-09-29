"""Targeted single-fragment re-extraction and merge into an existing export bundle."""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import Proposition, SourceFragment, SourceRecord
from law_proposition_extractor_llm import JuditLLMClient

from .extraction_debug import resolve_debug_extraction_context
from .export import export_bundle
from .extract import (
    EXTRACTION_PROMPT_VERSION_V2,
    EXTRACTION_SCHEMA_VERSION_V2,
    assign_proposition_extraction_debug,
    extract_propositions_from_source,
)
from .linting import load_exported_bundle
from .fragment_anchor_coverage import summarize_npp_reg2_definition_anchors
from .proposition_normalisation import normalise_extracted_propositions

FRAGMENT_REPAIR_COMMAND = "repair-fragment"

NPP_2015_SOURCE_ID = "lex-120b4f9c395b3f94"

_REG2_LOCATOR_RE = re.compile(r"^regulation\s*:?\s*2\b", re.IGNORECASE)


def normalize_fragment_locator(locator: str | None) -> str:
    return str(locator or "").strip().lower()


def locator_matches_regulation_2(locator: str | None) -> bool:
    normalized = normalize_fragment_locator(locator)
    if normalized == "regulation:2":
        return True
    return bool(_REG2_LOCATOR_RE.match(normalized.replace(":", " ")) or _REG2_LOCATOR_RE.match(normalized))


def proposition_search_haystack(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("proposition_text") or ""),
        str(row.get("label") or ""),
        str(row.get("short_name") or ""),
        str(row.get("legal_subject") or ""),
        str(row.get("action") or ""),
    ]
    meta = row.get("extraction_debug_meta")
    if isinstance(meta, dict):
        eq = str(meta.get("evidence_quote") or "")
        if eq and len(eq) <= 160:
            parts.append(eq)
    notes = str(row.get("notes") or "")
    if notes:
        parts.append(notes)
    return " ".join(parts)


def npp_reg2_proposition_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("source_record_id") or "") != NPP_2015_SOURCE_ID:
            continue
        if locator_matches_regulation_2(str(row.get("fragment_locator") or "")):
            out.append(row)
            continue
        if locator_matches_regulation_2(str(row.get("article_reference") or "")):
            out.append(row)
    return out


def proposition_belongs_to_fragment(
    row: dict[str, Any],
    *,
    source_record_id: str,
    source_fragment_id: str | None,
    fragment_locator: str,
) -> bool:
    if str(row.get("source_record_id") or "") != source_record_id:
        return False
    frag_id = str(row.get("source_fragment_id") or "").strip() or None
    if source_fragment_id and frag_id == source_fragment_id:
        return True
    row_loc = str(row.get("fragment_locator") or "").strip()
    if row_loc and normalize_fragment_locator(row_loc) == normalize_fragment_locator(fragment_locator):
        return True
    if source_fragment_id and not frag_id:
        article = str(row.get("article_reference") or "")
        if locator_matches_regulation_2(fragment_locator) and locator_matches_regulation_2(article):
            return True
    return False


def _bundle_sources_and_fragments(
    bundle: dict[str, Any],
) -> tuple[dict[str, SourceRecord], dict[str, SourceFragment]]:
    sources = {
        str(row["id"]): SourceRecord.model_validate(row)
        for row in (bundle.get("source_records") or [])
        if isinstance(row, dict) and row.get("id")
    }
    fragments = {
        str(row["id"]): SourceFragment.model_validate(row)
        for row in (bundle.get("source_fragments") or [])
        if isinstance(row, dict) and row.get("id")
    }
    return sources, fragments


def _stamp_fragment_repair_provenance(
    props: list[Proposition],
    *,
    export_dir: str,
    source_record_id: str,
    fragment_locator: str,
    source_fragment_id: str | None,
    extraction_mode: str,
    max_propositions: int,
    command: str = FRAGMENT_REPAIR_COMMAND,
    repaired_at: str,
) -> None:
    provenance = {
        "extraction_mode": "fragment_repair",
        "repair_command": command,
        "repair_source_export_dir": export_dir,
        "repaired_source_record_id": source_record_id,
        "repaired_fragment_locator": fragment_locator,
        "repaired_source_fragment_id": source_fragment_id,
        "repaired_at": repaired_at,
        "fragment_repair_extraction_mode": extraction_mode,
        "fragment_repair_max_propositions": max_propositions,
        "schema_version": EXTRACTION_SCHEMA_VERSION_V2,
    }
    for prop in props:
        existing = dict(getattr(prop, "extraction_debug_meta", None) or {})
        merged = {**existing, **provenance}
        assign_proposition_extraction_debug(prop, merged)


def _finalize_repaired_propositions(
    *,
    props: list[Proposition],
    bundle: dict[str, Any],
    run_id: str,
) -> list[Proposition]:
    from .runner import _build_proposition_records

    sources, fragments = _bundle_sources_and_fragments(bundle)
    return _build_proposition_records(
        propositions=props,
        run_id=run_id,
        source_by_id=sources,
        source_fragment_by_id=fragments,
    )


def _rebuild_bundle_after_fragment_merge(
    bundle: dict[str, Any],
    *,
    propositions: list[Proposition],
    removed_proposition_ids: set[str],
    source_record_id: str,
    source_fragment_id: str | None,
    fragment_locator: str,
    extraction_outcome_traces: list[dict[str, Any]],
    new_proposition_count: int,
    repair_metadata: dict[str, Any],
) -> dict[str, Any]:
    from .runner import _build_proposition_inventory

    updated = copy.deepcopy(bundle)
    updated["propositions"] = [p.model_dump(mode="json") for p in propositions]
    updated["proposition_inventory"] = _build_proposition_inventory(propositions)

    scope_links = [
        row
        for row in (updated.get("proposition_scope_links") or [])
        if isinstance(row, dict) and str(row.get("proposition_id") or "") not in removed_proposition_ids
    ]
    updated["proposition_scope_links"] = scope_links

    traces = [
        row
        for row in (updated.get("proposition_extraction_traces") or [])
        if isinstance(row, dict) and str(row.get("proposition_id") or "") not in removed_proposition_ids
    ]
    updated["proposition_extraction_traces"] = traces

    review_decisions = [
        row
        for row in (updated.get("review_decisions") or [])
        if isinstance(row, dict)
        and str(row.get("target_id") or "") not in removed_proposition_ids
    ]
    updated["review_decisions"] = review_decisions

    job_updated = False
    for job in updated.get("proposition_extraction_jobs") or []:
        if not isinstance(job, dict):
            continue
        if str(job.get("source_record_id") or "") != source_record_id:
            continue
        job_frag = str(job.get("source_fragment_id") or "").strip() or None
        job_loc = normalize_fragment_locator(str(job.get("fragment_locator") or ""))
        if source_fragment_id and job_frag != source_fragment_id:
            continue
        if not source_fragment_id and job_loc != normalize_fragment_locator(fragment_locator):
            continue
        job["proposition_count"] = new_proposition_count
        job["repairable"] = False
        job["repair_reason"] = None
        job["errors"] = []
        job["warnings"] = list(job.get("warnings") or [])
        job["fragment_repair_applied"] = True
        job["fragment_repair_metadata"] = dict(repair_metadata)
        job_updated = True

    if extraction_outcome_traces:
        existing = [
            row for row in (updated.get("extraction_llm_call_traces") or []) if isinstance(row, dict)
        ]
        updated["extraction_llm_call_traces"] = existing + extraction_outcome_traces

    existing_meta = updated.get("fragment_repair_metadata")
    if isinstance(existing_meta, list):
        updated["fragment_repair_metadata"] = [*existing_meta, repair_metadata]
    elif isinstance(existing_meta, dict):
        updated["fragment_repair_metadata"] = [existing_meta, repair_metadata]
    else:
        updated["fragment_repair_metadata"] = [repair_metadata]

    if not job_updated:
        updated.setdefault("proposition_extraction_jobs", []).append(
            {
                "source_record_id": source_record_id,
                "source_fragment_id": source_fragment_id,
                "fragment_locator": fragment_locator,
                "proposition_count": new_proposition_count,
                "fragment_repair_applied": True,
                "fragment_repair_metadata": dict(repair_metadata),
            }
        )

    return updated


def merge_fragment_repair_into_bundle(
    *,
    bundle: dict[str, Any],
    source_record_id: str,
    source_fragment_id: str | None,
    fragment_locator: str,
    new_propositions: list[Proposition],
    repair_metadata: dict[str, Any],
    extraction_outcome_traces: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kept_rows: list[dict[str, Any]] = []
    removed_ids: set[str] = set()
    for row in bundle.get("propositions") or []:
        if not isinstance(row, dict):
            continue
        if proposition_belongs_to_fragment(
            row,
            source_record_id=source_record_id,
            source_fragment_id=source_fragment_id,
            fragment_locator=fragment_locator,
        ):
            pid = str(row.get("id") or "")
            if pid:
                removed_ids.add(pid)
            continue
        kept_rows.append(row)

    merged_props = [Proposition.model_validate(row) for row in kept_rows]
    merged_props.extend(new_propositions)
    return _rebuild_bundle_after_fragment_merge(
        bundle,
        propositions=merged_props,
        removed_proposition_ids=removed_ids,
        source_record_id=source_record_id,
        source_fragment_id=source_fragment_id,
        fragment_locator=fragment_locator,
        extraction_outcome_traces=list(extraction_outcome_traces or []),
        new_proposition_count=len(new_propositions),
        repair_metadata=repair_metadata,
    )


def run_fragment_repair_pipeline(
    *,
    export_dir: Path,
    output_dir: Path,
    source_id: str,
    locator: str,
    extraction_mode: Literal["local", "frontier"] = "frontier",
    max_propositions: int = 12,
    retry_empty_extraction: bool = True,
    extraction_output_mode: str | None = None,
    allow_output_mode_fallback: bool = False,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Re-extract one fragment and merge results back into a copy of the export."""
    root = Path(export_dir).expanduser().resolve()
    out_dir = Path(output_dir).expanduser().resolve()
    from .extraction_json_repair import _enrich_bundle_from_export_files

    base_bundle = _enrich_bundle_from_export_files(
        load_exported_bundle(root),
        root,
    )
    inv_path = root / "proposition_inventory.json"
    if not base_bundle.get("proposition_inventory") and inv_path.is_file():
        try:
            base_bundle["proposition_inventory"] = json.loads(inv_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    work, frag, _fragment_text, topic, cluster = resolve_debug_extraction_context(
        root, source_id=source_id, locator=locator
    )
    source_fragment_id = frag.id if frag is not None else None

    if not use_llm:
        raise ValueError("fragment repair requires LLM extraction (--use-llm)")

    client = JuditLLMClient()
    outcome = extract_propositions_from_source(
        work,
        topic,
        cluster,
        llm_client=client,
        limit=max_propositions,
        extraction_mode=extraction_mode,
        extraction_fallback="fail_closed",
        prompt_version=EXTRACTION_PROMPT_VERSION_V2,
        retry_empty_extraction=retry_empty_extraction,
        extraction_output_mode=extraction_output_mode,  # type: ignore[arg-type]
        allow_output_mode_fallback=allow_output_mode_fallback,
    )
    if not outcome.propositions:
        errors = outcome.validation_errors or [outcome.failure_reason or "no propositions extracted"]
        raise ValueError(f"fragment repair extraction failed: {'; '.join(str(e) for e in errors[:3])}")

    raw_props = [p.model_copy(deep=True) for p in outcome.propositions]
    if frag is not None:
        for prop in raw_props:
            prop.source_fragment_id = frag.id
            if not prop.fragment_locator or prop.fragment_locator == "document:full":
                prop.fragment_locator = frag.locator
            if not prop.source_snapshot_id:
                prop.source_snapshot_id = frag.source_snapshot_id
    elif work.current_snapshot_id:
        for prop in raw_props:
            if not prop.source_snapshot_id:
                prop.source_snapshot_id = work.current_snapshot_id

    sources, _fragments = _bundle_sources_and_fragments(base_bundle)
    normalised = normalise_extracted_propositions(
        raw_props,
        source_by_id={source_id: sources.get(source_id) or work},
    )

    repaired_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _stamp_fragment_repair_provenance(
        normalised,
        export_dir=str(root),
        source_record_id=source_id,
        fragment_locator=locator,
        source_fragment_id=source_fragment_id,
        extraction_mode=extraction_mode,
        max_propositions=max_propositions,
        repaired_at=repaired_at,
    )

    sources, fragments = _bundle_sources_and_fragments(base_bundle)
    from .export_proposition_hygiene import apply_export_proposition_hygiene

    hygiene_stats = apply_export_proposition_hygiene(
        normalised,
        source_by_id=sources,
        fragment_by_id=fragments,
    )
    run_existing = base_bundle.get("run") if isinstance(base_bundle.get("run"), dict) else {}
    base_run_id = str(run_existing.get("id") or "run-unknown")
    new_run_id = f"{base_run_id}-frag-repaired-{uuid.uuid4().hex[:8]}"
    finalized = _finalize_repaired_propositions(
        props=normalised,
        bundle=base_bundle,
        run_id=new_run_id,
    )

    before_count = len(base_bundle.get("propositions") or [])
    removed_count = sum(
        1
        for row in base_bundle.get("propositions") or []
        if isinstance(row, dict)
        and proposition_belongs_to_fragment(
            row,
            source_record_id=source_id,
            source_fragment_id=source_fragment_id,
            fragment_locator=locator,
        )
    )

    repair_metadata = {
        "repaired_from_run_id": run_existing.get("id"),
        "repaired_from_export_dir": str(root),
        "repaired_at": repaired_at,
        "repair_command": FRAGMENT_REPAIR_COMMAND,
        "source_record_id": source_id,
        "source_fragment_id": source_fragment_id,
        "fragment_locator": locator,
        "extraction_mode": extraction_mode,
        "max_propositions": max_propositions,
        "removed_proposition_count": removed_count,
        "added_proposition_count": len(finalized),
        "proposition_count_before": before_count,
        "proposition_count_after": before_count - removed_count + len(finalized),
        **hygiene_stats,
    }

    merged_bundle = merge_fragment_repair_into_bundle(
        bundle=base_bundle,
        source_record_id=source_id,
        source_fragment_id=source_fragment_id,
        fragment_locator=locator,
        new_propositions=finalized,
        repair_metadata=repair_metadata,
        extraction_outcome_traces=list(outcome.extraction_llm_call_traces or []),
    )

    if isinstance(merged_bundle.get("run"), dict):
        merged_bundle["run"] = dict(merged_bundle["run"])
        merged_bundle["run"]["id"] = new_run_id

    anchor_summary = summarize_npp_reg2_definition_anchors(merged_bundle.get("propositions") or [])
    repair_metadata["npp_reg2_definition_anchors"] = anchor_summary
    if isinstance(merged_bundle.get("fragment_repair_metadata"), list):
        merged_bundle["fragment_repair_metadata"][-1] = repair_metadata

    out_dir.mkdir(parents=True, exist_ok=True)
    export_bundle(merged_bundle, output_dir=str(out_dir.resolve()))
    merged_bundle["fragment_repair_summary"] = repair_metadata
    return merged_bundle
