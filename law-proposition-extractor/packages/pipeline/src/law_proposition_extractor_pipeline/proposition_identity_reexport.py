"""Re-apply proposition opaque ids from an existing export without LLM re-extraction."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import Proposition

from .export import export_bundle
from .linting import load_exported_bundle
from .proposition_export_uniqueness import (
    find_duplicate_proposition_ids,
    proposition_identity_match_key,
    reconstruct_staging_proposition_id,
)
from .runner import (
    _build_proposition_extraction_traces,
    _build_proposition_inventory,
    _build_proposition_records,
)


def _bundle_sources_and_fragments(
    bundle: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    sources = {
        str(s.get("id")): s
        for s in (bundle.get("source_records") or [])
        if isinstance(s, dict) and s.get("id")
    }
    fragments = {
        str(f.get("id")): f
        for f in (bundle.get("source_fragments") or [])
        if isinstance(f, dict) and f.get("id")
    }
    return sources, fragments


def _remap_prop_id(value: str, id_map: dict[str, str]) -> str:
    if value in id_map:
        return id_map[value]
    if value.startswith("prop:"):
        return id_map.get(value, value)
    if value.startswith("review-proposition-"):
        tail = value.removeprefix("review-proposition-")
        if tail in id_map:
            return f"review-proposition-{id_map[tail]}"
    if value.startswith("pca-"):
        tail = value.removeprefix("pca-")
        if tail in id_map:
            return f"pca-{id_map[tail]}"
    return value


def _remap_row_ids(row: dict[str, Any], id_map: dict[str, str], fields: tuple[str, ...]) -> None:
    for field in fields:
        if field not in row:
            continue
        raw = row.get(field)
        if isinstance(raw, str) and raw.strip():
            row[field] = _remap_prop_id(raw.strip(), id_map)
        elif isinstance(raw, list):
            row[field] = [
                _remap_prop_id(str(x), id_map) if str(x).startswith("prop:") else x for x in raw
            ]


def _remap_bundle_proposition_references(bundle: dict[str, Any], id_map: dict[str, str]) -> None:
    for link in bundle.get("proposition_scope_links") or []:
        if isinstance(link, dict):
            _remap_row_ids(link, id_map, ("proposition_id",))
    for trace in bundle.get("proposition_extraction_traces") or []:
        if isinstance(trace, dict):
            _remap_row_ids(trace, id_map, ("proposition_id",))
            tid = str(trace.get("id") or "")
            if tid.startswith("extract-trace:"):
                pid = str(trace.get("proposition_id") or "")
                if pid:
                    from .intake import content_hash

                    trace["id"] = f"extract-trace:{content_hash(f'proposition_extraction_trace|{pid}')[:16]}"
    for assess in bundle.get("proposition_completeness_assessments") or []:
        if isinstance(assess, dict):
            _remap_row_ids(assess, id_map, ("proposition_id", "id"))
    for decision in bundle.get("review_decisions") or []:
        if isinstance(decision, dict):
            _remap_row_ids(decision, id_map, ("target_id", "id"))
    for cand in bundle.get("scope_review_candidates") or []:
        if isinstance(cand, dict):
            _remap_row_ids(cand, id_map, ("proposition_id",))
    for prop in bundle.get("propositions") or []:
        if not isinstance(prop, dict):
            continue
        _remap_row_ids(
            prop,
            id_map,
            ("cross_reference_targets", "explicit_cross_reference_targets"),
        )


def reidentity_export_bundle(
    export_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """
    Rebuild opaque proposition ids (and dependent artifact references) from an export.

    Does not call the LLM; re-runs ``_build_proposition_records`` on existing rows.
    """
    root = Path(export_dir).resolve()
    out_dir = Path(output_dir).resolve()
    bundle = copy.deepcopy(load_exported_bundle(root))
    run_raw = bundle.get("run")
    run_id = "run-001"
    if isinstance(run_raw, dict) and run_raw.get("id"):
        run_id = str(run_raw["id"])

    old_rows = [p for p in (bundle.get("propositions") or []) if isinstance(p, dict)]
    id_map: dict[str, str] = {}
    staging_props: list[Proposition] = []
    for row in old_rows:
        old_id = str(row.get("id") or "").strip()
        payload = copy.deepcopy(row)
        payload["id"] = reconstruct_staging_proposition_id(payload)
        if str(payload.get("source_fragment_id") or "").strip():
            payload.pop("proposition_key", None)
            payload.pop("proposition_version_id", None)
        staging_props.append(Proposition.model_validate(payload))

    sources, fragments = _bundle_sources_and_fragments(bundle)
    rebuilt = _build_proposition_records(
        propositions=staging_props,
        run_id=run_id,
        source_by_id=sources,
        source_fragment_by_id=fragments,
    )

    new_by_key = {proposition_identity_match_key(p.model_dump(mode="json")): p for p in rebuilt}
    for row in old_rows:
        old_id = str(row.get("id") or "").strip()
        if not old_id:
            continue
        match_key = proposition_identity_match_key(row)
        new_prop = new_by_key.get(match_key)
        if new_prop is None:
            raise ValueError(
                f"could not match rebuilt proposition for {old_id!r} "
                f"(fragment={row.get('source_fragment_id')!r})"
            )
        id_map[old_id] = new_prop.id

    bundle["propositions"] = [p.model_dump(mode="json") for p in rebuilt]
    _remap_bundle_proposition_references(bundle, id_map)

    case_inputs = bundle.get("pipeline_case_inputs")
    extraction_prompt: dict[str, Any] = {}
    use_llm = True
    if isinstance(case_inputs, dict):
        extraction_prompt = case_inputs.get("extraction_prompt") or {}
        use_llm = bool(case_inputs.get("use_llm", True))

    bundle["proposition_extraction_traces"] = [
        t.model_dump(mode="json")
        for t in _build_proposition_extraction_traces(
            propositions=rebuilt,
            use_llm=use_llm,
            extraction_prompt=extraction_prompt if isinstance(extraction_prompt, dict) else {},
            extraction_strategy_version="v2",
            extraction_hook={},
            pipeline_version="reidentity",
        )
    ]
    bundle["proposition_inventory"] = _build_proposition_inventory(rebuilt)
    bundle["proposition_identity_reexport"] = {
        "source_export_dir": str(root),
        "remapped_proposition_count": len(id_map),
        "duplicate_ids_before": find_duplicate_proposition_ids(old_rows),
        "duplicate_ids_after": find_duplicate_proposition_ids(bundle["propositions"]),
        "id_map_sample": dict(list(id_map.items())[:20]),
    }

    export_bundle(bundle, output_dir=str(out_dir))
    return bundle
