"""Run divergence comparison on two existing proposition datasets (no source re-extraction)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .proposition_dataset import (
    attach_dataset_comparison_run_record,
    attach_proposition_dataset_metadata,
    build_registry_comparison_config,
    coerce_bundle_for_replay,
    merge_export_bundles_for_dataset_comparison,
)
from .runner import build_bundle_from_case


def run_proposition_dataset_comparison(
    *,
    left_bundle: dict[str, Any],
    right_bundle: dict[str, Any],
    comparison_run_id: str | None,
    topic_name: str | None,
    use_llm: bool,
    divergence_reasoning: str | None,
    extraction_mode: str | None,
    extraction_fallback: str | None,
    proposition_index: int,
    source_cache_dir: str | None,
    derived_cache_dir: str | None,
    pairing_settings: dict[str, Any] | None,
    comparison_jurisdiction_a: str | None = None,
    comparison_jurisdiction_b: str | None = None,
) -> dict[str, Any]:
    attach_proposition_dataset_metadata(left_bundle)
    attach_proposition_dataset_metadata(right_bundle)
    merged = merge_export_bundles_for_dataset_comparison(
        coerce_bundle_for_replay(left_bundle),
        coerce_bundle_for_replay(right_bundle),
    )

    pairing_extra = dict(pairing_settings) if pairing_settings else {}
    prop_idx = int(pairing_extra.pop("proposition_index", proposition_index))
    comparison_cfg = build_registry_comparison_config(
        case_sources=list(merged.get("source_records") or []),
        proposition_index=prop_idx,
        comparison_jurisdiction_a=comparison_jurisdiction_a,
        comparison_jurisdiction_b=comparison_jurisdiction_b,
        analysis_scope="selected_sources",
        analysis_mode="divergence",
    )
    comparison_cfg.update(pairing_extra)

    new_id = comparison_run_id or f"cmp-dataset-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    topic_raw = merged.get("topic")
    topic = topic_raw if isinstance(topic_raw, dict) else {}
    case_data: dict[str, Any] = {
        "run_id": new_id,
        "run_notes": "Dataset comparison run (no proposition re-extraction).",
        "analysis_mode": "divergence",
        "analysis_scope": "selected_sources",
        "topic": {
            "name": str(topic.get("name") or "Dataset comparison"),
            "description": str(topic.get("description") or ""),
            "subject_tags": list(topic.get("subject_tags") or []),
        },
        "cluster": {
            "name": topic_name
            or (
                f"Compare {comparison_cfg.get('jurisdiction_a', '?')}/"
                f"{comparison_cfg.get('jurisdiction_b', '?')}"
            ),
            "description": "Divergence run over two exported proposition datasets.",
        },
        "comparison": comparison_cfg,
        "skip_proposition_extraction": True,
        "extraction": {},
        "sources": list(merged.get("source_records") or []),
    }
    div_raw = divergence_reasoning if divergence_reasoning is not None else "none"
    bundle = build_bundle_from_case(
        case_data=case_data,
        use_llm=use_llm,
        extraction_mode=extraction_mode or "heuristic",
        extraction_fallback=extraction_fallback or "fallback",
        divergence_reasoning=div_raw,
        source_cache_dir=source_cache_dir,
        derived_cache_dir=derived_cache_dir,
        intake_bundle=merged,
    )
    findings = bundle.get("divergence_findings") or []
    fids = [str(f.get("id")) for f in findings if isinstance(f, dict) and f.get("id")]
    attach_dataset_comparison_run_record(
        bundle,
        left_bundle=left_bundle,
        right_bundle=right_bundle,
        pairing_settings=dict(comparison_cfg),
        divergence_reasoning_settings={"divergence_reasoning": div_raw, "use_llm": use_llm},
        finding_ids=fids,
    )
    return bundle
