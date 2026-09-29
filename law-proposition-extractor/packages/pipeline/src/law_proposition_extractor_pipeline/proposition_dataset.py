"""Proposition dataset metadata and merging exports for dataset-level comparison."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from law_proposition_extractor_domain import (
    JurisdictionScope,
    PropositionDatasetComparisonRun,
    PropositionDatasetMetadata,
)

from .intake import content_hash


def canonical_jurisdiction_label(raw: str) -> str:
    u = str(raw or "").strip().upper()
    if u in {"EU", "E.U.", "EUROPEAN UNION"}:
        return "EU"
    if u in {"UK", "U.K.", "GB", "UNITED KINGDOM", "GBR"}:
        return "UK"
    return u or "unknown"


def infer_jurisdiction_scope_from_source_dicts(sources: list[dict[str, Any]]) -> JurisdictionScope:
    labels: set[str] = set()
    for row in sources:
        if not isinstance(row, dict):
            continue
        lab = canonical_jurisdiction_label(str(row.get("jurisdiction", "") or ""))
        if lab and lab != "unknown":
            labels.add(lab)
    if labels == {"EU"}:
        return "EU"
    if labels == {"UK"}:
        return "UK"
    if len(labels) > 1:
        return "mixed"
    return "unknown"


def build_proposition_dataset_metadata(bundle: dict[str, Any]) -> PropositionDatasetMetadata:
    run_raw = bundle.get("run")
    run = run_raw if isinstance(run_raw, dict) else {}
    run_id = str(run.get("id") or "")
    sources = list(bundle.get("source_records") or bundle.get("sources") or [])
    if not isinstance(sources, list):
        sources = []
    source_ids = [str(s.get("id")) for s in sources if isinstance(s, dict) and s.get("id")]
    js: JurisdictionScope = infer_jurisdiction_scope_from_source_dicts(
        [s for s in sources if isinstance(s, dict)]
    )
    pci = bundle.get("pipeline_case_inputs")
    extraction_settings: dict[str, Any] = {}
    analysis_scope: str | None = None
    if isinstance(pci, dict):
        ext = pci.get("extraction")
        if isinstance(ext, dict):
            extraction_settings = dict(ext)
        extraction_settings["analysis_mode"] = pci.get("analysis_mode")
        asc = pci.get("analysis_scope")
        if isinstance(asc, str) and asc.strip():
            analysis_scope = asc.strip().lower()
            extraction_settings["analysis_scope"] = analysis_scope

    rq = bundle.get("run_quality_summary")
    quality_status = "unknown"
    if isinstance(rq, dict) and rq.get("status"):
        quality_status = str(rq.get("status"))

    corpus_id: str | None = None
    md_corpora = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    if isinstance(md_corpora, dict):
        cid = md_corpora.get("corpus_id")
        if isinstance(cid, str) and cid.strip():
            corpus_id = cid.strip()

    created_at: datetime | None = None
    cat = run.get("created_at")
    if isinstance(cat, str) and cat.strip():
        try:
            created_at = datetime.fromisoformat(cat.replace("Z", "+00:00"))
        except ValueError:
            created_at = None
    if created_at is None:
        created_at = datetime.now(UTC)

    dataset_id = f"pd:{run_id}" if run_id else f"pd:{content_hash(json.dumps(source_ids, sort_keys=True))[:12]}"

    return PropositionDatasetMetadata(
        dataset_id=dataset_id,
        run_id=run_id,
        jurisdiction_scope=js,
        source_ids=source_ids,
        corpus_id=corpus_id,
        extraction_settings=extraction_settings,
        created_at=created_at,
        quality_status=quality_status,
    )


def attach_proposition_dataset_metadata(bundle: dict[str, Any]) -> None:
    """Attach ``proposition_dataset`` to a bundle dict (mutates in place)."""
    meta = build_proposition_dataset_metadata(bundle)
    bundle["proposition_dataset"] = meta.model_dump(mode="json")


def _id_set(rows: list[Any], key: str = "id") -> set[str]:
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and row.get(key):
            out.add(str(row[key]))
    return out


def merge_export_bundles_for_dataset_comparison(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    """Concatenate two export-shaped bundles. Requires disjoint source/proposition ids."""
    lsources = list(left.get("source_records") or left.get("sources") or [])
    rsources = list(right.get("source_records") or right.get("sources") or [])
    overlap_src = _id_set(lsources) & _id_set(rsources)
    if overlap_src:
        raise ValueError(
            "Cannot merge bundles: overlapping source_record ids: "
            + ", ".join(sorted(overlap_src)[:12])
        )

    lprops = list(left.get("propositions") or [])
    rprops = list(right.get("propositions") or [])
    overlap_prop = _id_set(lprops) & _id_set(rprops)
    if overlap_prop:
        raise ValueError(
            "Cannot merge bundles: overlapping proposition ids: "
            + ", ".join(sorted(overlap_prop)[:12])
        )

    def cat(key: str) -> list[Any]:
        a = left.get(key)
        b = right.get(key)
        la = list(a) if isinstance(a, list) else []
        lb = list(b) if isinstance(b, list) else []
        return la + lb

    merged: dict[str, Any] = {
        "topic": left.get("topic") or right.get("topic"),
        "clusters": cat("clusters"),
        "run": left.get("run"),
        "source_records": lsources + rsources,
        "sources": lsources + rsources,
        "source_snapshots": cat("source_snapshots"),
        "source_fragments": cat("source_fragments"),
        "source_parse_traces": cat("source_parse_traces"),
        "source_fetch_metadata": cat("source_fetch_metadata"),
        "source_fetch_attempts": cat("source_fetch_attempts"),
        "propositions": lprops + rprops,
        "proposition_extraction_traces": cat("proposition_extraction_traces"),
        "proposition_scope_links": cat("proposition_scope_links"),
        "legal_scopes": _dedupe_legal_scopes(cat("legal_scopes")),
        "divergence_assessments": [],
        "divergence_findings": [],
        "divergence_observations": [],
        "review_decisions": cat("review_decisions"),
        "merged_from": {
            "left_run_id": str((left.get("run") or {}).get("id") or ""),
            "right_run_id": str((right.get("run") or {}).get("id") or ""),
        },
    }
    return merged


def _dedupe_legal_scopes(rows: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(row)
    return out


def attach_dataset_comparison_run_record(
    bundle: dict[str, Any],
    *,
    left_bundle: dict[str, Any],
    right_bundle: dict[str, Any],
    pairing_settings: dict[str, Any],
    divergence_reasoning_settings: dict[str, Any],
    finding_ids: list[str],
) -> None:
    run_raw = bundle.get("run")
    rid = str((run_raw or {}).get("id") or "") if isinstance(run_raw, dict) else ""
    left_ds = left_bundle.get("proposition_dataset") or {}
    right_ds = right_bundle.get("proposition_dataset") or {}
    left_run = left_bundle.get("run") or {}
    right_run = right_bundle.get("run") or {}
    rec = PropositionDatasetComparisonRun(
        comparison_run_id=rid,
        left_dataset_id=str(left_ds.get("dataset_id") or ""),
        right_dataset_id=str(right_ds.get("dataset_id") or ""),
        left_source_run_id=str(left_run.get("id") or ""),
        right_source_run_id=str(right_run.get("id") or ""),
        pairing_settings=dict(pairing_settings),
        divergence_reasoning_settings=dict(divergence_reasoning_settings),
        output_finding_ids=list(finding_ids),
    )
    bundle["dataset_comparison_run"] = rec.model_dump(mode="json")


def coerce_bundle_for_replay(bundle: dict[str, Any]) -> dict[str, Any]:
    """Ensure lists are plain dicts suitable for ``hydrate_intake_from_export_bundle``."""
    out = dict(bundle)
    for key in (
        "source_records",
        "sources",
        "source_snapshots",
        "source_fragments",
        "propositions",
    ):
        raw = out.get(key)
        if isinstance(raw, list):
            cleaned: list[Any] = []
            for item in raw:
                if isinstance(item, dict):
                    cleaned.append(item)
                elif hasattr(item, "model_dump"):
                    cleaned.append(item.model_dump(mode="json"))
            out[key] = cleaned
    return out


def filter_registry_case_sources_by_scope(
    case_sources: list[dict[str, Any]],
    analysis_scope: str,
) -> list[dict[str, Any]]:
    s = analysis_scope.strip().lower()
    if s in {"", "selected_sources"}:
        return list(case_sources)
    out: list[dict[str, Any]] = []
    for row in case_sources:
        if not isinstance(row, dict):
            continue
        lab = canonical_jurisdiction_label(str(row.get("jurisdiction", "") or ""))
        if s == "eu" and lab == "EU":
            out.append(row)
        elif s == "uk" and lab == "UK":
            out.append(row)
        elif s == "eu_uk" and lab in {"EU", "UK"}:
            out.append(row)
    return out


def validate_registry_divergence_inputs(
    *,
    case_sources: list[dict[str, Any]],
    analysis_scope: str,
    analysis_mode: str,
    comparison_jurisdiction_a: str | None,
    comparison_jurisdiction_b: str | None,
) -> None:
    mode = analysis_mode.strip().lower()
    scope = analysis_scope.strip().lower()
    if mode not in {"divergence", "compare"}:
        return
    labels = {
        canonical_jurisdiction_label(str(s.get("jurisdiction", "") or ""))
        for s in case_sources
        if isinstance(s, dict)
    }
    labels.discard("unknown")
    if scope == "eu_uk" and ("EU" not in labels or "UK" not in labels):
        raise ValueError(
            "analysis_scope eu_uk with divergence requires at least one EU source and one UK source "
            "in the current selection (after filters)."
        )
    if scope == "selected_sources" and len(labels) > 1:
        if not (comparison_jurisdiction_a and comparison_jurisdiction_b):
            raise ValueError(
                "Divergence with analysis_scope selected_sources and multiple jurisdictions requires "
                "explicit comparison_jurisdiction_a and comparison_jurisdiction_b (no silent defaults)."
            )


def build_registry_comparison_config(
    *,
    case_sources: list[dict[str, Any]],
    proposition_index: int,
    comparison_jurisdiction_a: str | None,
    comparison_jurisdiction_b: str | None,
    analysis_scope: str,
    analysis_mode: str,
) -> dict[str, Any]:
    cfg: dict[str, Any] = {"proposition_index": proposition_index}
    labels = sorted(
        {
            canonical_jurisdiction_label(str(s.get("jurisdiction", "") or ""))
            for s in case_sources
            if isinstance(s, dict)
        }
        - {"unknown"}
    )
    ja = (
        canonical_jurisdiction_label(comparison_jurisdiction_a)
        if comparison_jurisdiction_a
        else None
    )
    jb = (
        canonical_jurisdiction_label(comparison_jurisdiction_b)
        if comparison_jurisdiction_b
        else None
    )
    mode = analysis_mode.strip().lower()
    scope = analysis_scope.strip().lower()

    if mode in {"divergence", "compare"}:
        if ja and jb:
            cfg["jurisdiction_a"] = ja
            cfg["jurisdiction_b"] = jb
        elif scope == "eu_uk":
            cfg["jurisdiction_a"] = "EU"
            cfg["jurisdiction_b"] = "UK"
        elif "EU" in labels and "UK" in labels:
            cfg["jurisdiction_a"] = "EU"
            cfg["jurisdiction_b"] = "UK"
        elif len(labels) >= 2:
            cfg["jurisdiction_a"] = labels[0]
            cfg["jurisdiction_b"] = labels[1]
        elif len(labels) == 1:
            cfg["jurisdiction_a"] = labels[0]
            cfg["jurisdiction_b"] = labels[0]
        return cfg

    if "EU" in labels and "UK" in labels:
        cfg["jurisdiction_a"] = "EU"
        cfg["jurisdiction_b"] = "UK"
    elif len(labels) >= 2:
        cfg["jurisdiction_a"] = labels[0]
        cfg["jurisdiction_b"] = labels[1]
    elif len(labels) == 1:
        j0 = labels[0]
        cfg["jurisdiction_a"] = j0
        cfg["jurisdiction_b"] = j0
    return cfg
