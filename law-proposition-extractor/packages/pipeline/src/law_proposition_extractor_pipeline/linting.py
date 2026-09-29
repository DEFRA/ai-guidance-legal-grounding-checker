import json
from itertools import combinations
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .effective_views import (
    SUPPORTED_EFFECTIVE_ARTIFACT_TYPES,
    find_original_artifact_in_bundle,
    validate_replacement_merged,
)
from .pipeline_reviews import categorisation_artifact_id, resolve_current_pipeline_review_decision
from .proposition_export_uniqueness import (
    find_duplicate_proposition_ids,
    find_duplicate_proposition_keys,
    find_duplicate_proposition_version_ids,
)
from .source_fragment_hierarchy import validate_source_fragment_hierarchy

# Legacy LLM extraction tags only — not proposition_tier / legal_effect_type.
ALLOWED_PROPOSITION_CATEGORIES = {
    "obligation",
    "institutional",
    "documentary",
    "conditional",
    "oversight",
    "record_keeping",
    "reporting",
}

ALLOWED_SOURCE_ROLES = {
    "base_act",
    "amendment",
    "delegated_act",
    "implementing_act",
    "guidance",
    "explanatory_material",
    "certificate_model",
    "annex",
    "corrigendum",
    "case_file",
    "unknown",
}

ALLOWED_ANALYSIS_RELATIONSHIPS = {
    "analysis_target",
    "modifies_target",
    "implements_target",
    "explains_target",
    "evidences_target",
    "contextual_source",
    "unknown",
}

ALLOWED_TARGET_LINK_TYPES = {
    "is_target",
    "amends",
    "implements",
    "supplements",
    "corrects",
    "explains",
    "evidences",
    "contains_annex_to",
    "references",
    "contextual",
    "unknown",
}

ALLOWED_CATEGORISATION_METHODS = {"deterministic", "llm", "manual", "fallback"}
ALLOWED_CATEGORISATION_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_FRAGMENT_TYPES = {
    "article",
    "regulation",
    "rule",
    "section",
    "recital",
    "annex",
    "schedule",
    "part",
    "chapter",
    "title",
    "division",
    "document",
    "chunk",
    "heading",
    "paragraph",
    "table",
    "unknown",
}
ALLOWED_PROPOSITION_EXTRACTION_METHODS = {
    "heuristic",
    "llm",
    "manual",
    "imported",
    "fallback",
}

ALLOWED_SCOPE_LINK_METHODS = {"deterministic", "llm", "manual", "fallback"}
ALLOWED_SCOPE_RELEVANCE = {"direct", "indirect", "contextual"}
ALLOWED_SCOPE_INHERITANCE = {"explicit", "inherited", "inferred", "none"}
ALLOWED_SCOPE_CONFIDENCE = {"high", "medium", "low"}

# Deterministic exporter states strongest field in signals.evidence_field; direct applicability
# should be grounded in proposition text or source excerpt (not citation/title/context alone).
_DIRECT_SCOPE_ACCEPT_EVIDENCE_FIELDS = frozenset(
    {
        "proposition_text",
        "source_fragment_text",
        "legal_subject",
        "affected_subjects",
        "required_documents",
        "conditions",
    }
)


def _should_warn_proposition_scope_link_low_confidence(link: dict[str, Any]) -> bool:
    """Emit actionable low-confidence lint only for direct applicability (matches UI primary rows).

    Suppress noise from contextual links, parent inherited scopes, and non-direct links shown
    only after 'Show all scopes' (see apps/web structured-proposition-ui scope chips).
    """
    confidence = str(link.get("confidence", "")).strip().lower()
    if confidence != "low":
        return False
    relevance = str(link.get("relevance", "")).strip().lower()
    inheritance = str(link.get("inheritance", "")).strip().lower()
    if relevance == "direct":
        return True
    if relevance == "contextual":
        return False
    if inheritance == "inherited":
        return False
    return False


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def load_exported_bundle(export_dir: str | Path) -> dict[str, Any]:
    root = Path(export_dir)
    if not root.exists():
        raise ValueError(f"Export directory does not exist: {root}")
    if root.is_file():
        hint = (
            "You passed a file path, not an exported bundle directory. "
            "Run `law-proposition-extractor-run-case export` (or your pipeline export step) and pass the output folder "
            "(e.g. dist/static-report), which contains run.json, propositions.json, and related artifacts. "
            "A Law Proposition Extractor case.json alone is not a valid --export-dir."
        )
        if root.name == "case.json" or root.suffix.lower() == ".json":
            raise ValueError(f"{hint} Received: {root}")
        raise ValueError(f"Expected a directory, got file: {root}. {hint}")
    if not root.is_dir():
        raise ValueError(f"Export path is not a directory: {root}")
    topic = _read_json(root / "topic.json", None)
    clusters = _read_json(root / "clusters.json", None)
    narrative: dict[str, Any] | None = None
    run_id = ""
    run_blob = _read_json(root / "run.json", {})
    if isinstance(run_blob, dict):
        run_id = str(run_blob.get("id") or "")
    if run_id:
        narrative_path = (
            root / "runs" / run_id / "artifacts" / f"artifact-{run_id}-narrative.json"
        )
        if narrative_path.exists():
            loaded = _read_json(narrative_path, None)
            if isinstance(loaded, dict):
                narrative = loaded
    if narrative is None and (root / "narrative.md").exists():
        md_lines = (root / "narrative.md").read_text(encoding="utf-8").splitlines()
        title = md_lines[0].lstrip("# ").strip() if md_lines else "Narrative"
        sections = [ln[2:].strip() for ln in md_lines if ln.startswith("- ")]
        summary = ""
        for ln in md_lines[1:]:
            if ln.startswith("- "):
                break
            if ln.strip():
                summary = ln.strip()
                break
        narrative = {
            "title": title,
            "summary": summary or title,
            "sections": sections,
        }

    payload: dict[str, Any] = {
        "run": run_blob if isinstance(run_blob, dict) else {},
        "topic": topic if isinstance(topic, dict) else {},
        "clusters": clusters if isinstance(clusters, list) else [],
        "narrative": narrative
        if isinstance(narrative, dict)
        else {"title": "Narrative", "summary": "", "sections": []},
        "source_records": _read_json(root / "sources.json", []),
        "source_snapshots": _read_json(root / "source_snapshots.json", []),
        "source_fragments": _read_json(root / "source_fragments.json", []),
        "source_parse_traces": _read_json(root / "source_parse_traces.json", []),
        "source_fetch_metadata": _read_json(root / "source_fetch_metadata.json", []),
        "source_fetch_attempts": _read_json(root / "source_fetch_attempts.json", []),
        "source_target_links": _read_json(root / "source_target_links.json", []),
        "source_inventory": _read_json(root / "source_inventory.json", {}),
        "source_categorisation_rationales": _read_json(
            root / "source_categorisation_rationales.json", []
        ),
        "propositions": _read_json(root / "propositions.json", []),
        "proposition_extraction_traces": _read_json(
            root / "proposition_extraction_traces.json", []
        ),
        "proposition_extraction_jobs": _read_json(root / "proposition_extraction_jobs.json", []),
        "divergence_observations": _read_json(root / "divergence_observations.json", []),
        "divergence_assessments": _read_json(root / "divergence_assessments.json", []),
        "divergence_findings": _read_json(root / "divergence_findings.json", []),
        "run_artifacts": _read_json(root / "run_artifacts.json", []),
        "legal_scopes": _read_json(root / "legal_scopes.json", []),
        "proposition_scope_links": _read_json(root / "proposition_scope_links.json", []),
        "scope_inventory": _read_json(root / "scope_inventory.json", {}),
        "scope_review_candidates": _read_json(root / "scope_review_candidates.json", []),
    }
    pca_path = root / "proposition_completeness_assessments.json"
    if pca_path.exists():
        pca = _read_json(pca_path, [])
        if isinstance(pca, list):
            payload["proposition_completeness_assessments"] = pca
    pexf_path = root / "proposition_extraction_failures.json"
    if pexf_path.exists():
        payload["proposition_extraction_failures"] = _read_json(pexf_path, [])
    llm_path = root / "extraction_llm_call_traces.json"
    if llm_path.exists():
        payload["extraction_llm_call_traces"] = _read_json(llm_path, [])
    chunk_path = root / "proposition_extraction_chunk_statuses.json"
    if chunk_path.exists():
        payload["proposition_extraction_chunk_statuses"] = _read_json(chunk_path, [])
    inspection_path = root / "extraction_inspection_summary.json"
    if inspection_path.exists():
        payload["extraction_inspection_summary"] = _read_json(inspection_path, {})
    pci_path = root / "pipeline_case_inputs.json"
    if pci_path.exists():
        payload["pipeline_case_inputs"] = _read_json(pci_path, {})
    pd_path = root / "proposition_dataset.json"
    if pd_path.exists():
        pd_blob = _read_json(pd_path, {})
        if isinstance(pd_blob, dict):
            payload["proposition_dataset"] = pd_blob
    dcr_path = root / "dataset_comparison_run.json"
    if dcr_path.exists():
        dcr_blob = _read_json(dcr_path, {})
        if isinstance(dcr_blob, dict):
            payload["dataset_comparison_run"] = dcr_blob
    quality = _read_json(root / "run_quality_summary.json", None)
    if isinstance(quality, dict):
        payload["run_quality_summary"] = quality
    root_manifest = _read_json(root / "manifest.json", {})
    if isinstance(root_manifest, dict) and "has_proposition_extraction_traces" in root_manifest:
        payload["has_proposition_extraction_traces"] = root_manifest.get(
            "has_proposition_extraction_traces"
        )
    if isinstance(root_manifest, dict) and "has_proposition_extraction_jobs" in root_manifest:
        payload["has_proposition_extraction_jobs"] = root_manifest.get(
            "has_proposition_extraction_jobs"
        )
    prd = _read_json(root / "pipeline_review_decisions.json", [])
    if isinstance(prd, list):
        payload["pipeline_review_decisions"] = prd
    sfc_path = root / "source_family_candidates.json"
    if sfc_path.exists():
        sfc = _read_json(sfc_path, [])
        if isinstance(sfc, list):
            payload["source_family_candidates"] = sfc
    prel_path = root / "proposition-relationships.json"
    if prel_path.exists():
        prel = _read_json(prel_path, {})
        if isinstance(prel, dict):
            payload["proposition_relationships"] = prel
    law_path = root / "effective_law_statements.json"
    if law_path.exists():
        law = _read_json(law_path, {})
        if isinstance(law, dict):
            payload["effective_law_statements"] = law
    bcands_path = root / "proposition_matcher_law_candidates.json"
    if not bcands_path.is_file():
        bcands_path = root / "beatrice_law_candidates.json"  # COMPAT_LEGACY_NAME
    if bcands_path.exists():
        bcands = _read_json(bcands_path, {})
        if isinstance(bcands, dict):
            payload["proposition_matcher_law_candidates"] = bcands
    lrg_path = root / "legal_rule_groups.json"
    if lrg_path.exists():
        lrg = _read_json(lrg_path, {})
        if isinstance(lrg, dict):
            payload["legal_rule_groups"] = lrg
    lrr_path = root / "legal_rule_relationships.json"
    if lrr_path.exists():
        lrr = _read_json(lrr_path, {})
        if isinstance(lrr, dict):
            payload["legal_rule_relationships"] = lrr
    sle_path = root / "source_legal_effects.json"
    if sle_path.exists():
        sle = _read_json(sle_path, {})
        if isinstance(sle, dict):
            payload["source_legal_effects"] = sle
    dexp_path = root / "decision_explanations.json"
    if dexp_path.exists():
        dexp = _read_json(dexp_path, {})
        if isinstance(dexp, dict):
            payload["decision_explanations"] = dexp
    return payload


def merge_export_root_mirror_into_run_bundle(
    bundle: dict[str, Any],
    *,
    operations_export_root: str | Path,
) -> dict[str, Any]:
    """
    Per-run dirs only carry a subset of JSON; the export root mirrors list-shaped artifacts.

    When ``run.json`` at the export root matches this bundle's ``run.id``, copy missing non-empty
    fields from the root so extraction repair / quality see traces and propositions.
    """
    root = Path(operations_export_root)
    run_blob = bundle.get("run")
    run_id = str((run_blob or {}).get("id") or "") if isinstance(run_blob, dict) else ""
    root_run = _read_json(root / "run.json", None)
    root_id = str((root_run or {}).get("id") or "") if isinstance(root_run, dict) else ""
    if not run_id or not root_id or root_id != run_id:
        return bundle
    mirror = load_exported_bundle(root)
    for key, mval in mirror.items():
        if key == "run" or mval in (None, [], {}):
            continue
        pval = bundle.get(key)
        if isinstance(mval, list):
            if not isinstance(pval, list) or len(pval) == 0:
                bundle[key] = mval
        elif isinstance(mval, dict):
            if not isinstance(pval, dict) or len(pval) == 0:
                bundle[key] = mval
    return bundle


def lint_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    source_records = bundle.get("source_records")
    if not isinstance(source_records, list):
        source_records = []
    source_snapshots = bundle.get("source_snapshots")
    if not isinstance(source_snapshots, list):
        source_snapshots = []
    source_fragments = bundle.get("source_fragments")
    if not isinstance(source_fragments, list):
        source_fragments = []
    source_parse_traces = bundle.get("source_parse_traces")
    if not isinstance(source_parse_traces, list):
        source_parse_traces = []
    proposition_extraction_traces = bundle.get("proposition_extraction_traces")
    if not isinstance(proposition_extraction_traces, list):
        proposition_extraction_traces = []
    propositions = bundle.get("propositions")
    if not isinstance(propositions, list):
        propositions = []
    source_inventory = bundle.get("source_inventory")
    if not isinstance(source_inventory, dict):
        source_inventory = {}
    inventory_rows = source_inventory.get("rows")
    if not isinstance(inventory_rows, list):
        inventory_rows = []
    fetch_metadata = bundle.get("source_fetch_metadata")
    if not isinstance(fetch_metadata, list):
        fetch_metadata = []
    source_fetch_attempts = bundle.get("source_fetch_attempts")
    if not isinstance(source_fetch_attempts, list):
        source_fetch_attempts = []
    source_target_links = bundle.get("source_target_links")
    if not isinstance(source_target_links, list):
        source_target_links = []
    source_categorisation_rationales = bundle.get("source_categorisation_rationales")
    if not isinstance(source_categorisation_rationales, list):
        source_categorisation_rationales = []
    run_artifacts = bundle.get("run_artifacts")
    if not isinstance(run_artifacts, list):
        run_artifacts = []
    divergence_observations = bundle.get("divergence_observations")
    if not isinstance(divergence_observations, list):
        divergence_observations = []
    pipeline_raw = bundle.get("pipeline_review_decisions")
    pipeline_decisions: list[dict[str, Any]] = (
        [d for d in pipeline_raw if isinstance(d, dict)]
        if isinstance(pipeline_raw, list)
        else []
    )
    legal_scopes = bundle.get("legal_scopes")
    if not isinstance(legal_scopes, list):
        legal_scopes = []
    proposition_scope_links = bundle.get("proposition_scope_links")
    if not isinstance(proposition_scope_links, list):
        proposition_scope_links = []
    scope_review_candidates_bundle = bundle.get("scope_review_candidates")
    if not isinstance(scope_review_candidates_bundle, list):
        scope_review_candidates_bundle = []

    prop_dicts = [p for p in propositions if isinstance(p, dict)]
    for dup in find_duplicate_proposition_ids(prop_dicts):
        errors.append(
            f"duplicate proposition id: {dup['id']} ({dup['count']} rows)"
        )
    for dup in find_duplicate_proposition_keys(prop_dicts):
        errors.append(
            f"duplicate proposition_key within source {dup['source_record_id']}: "
            f"{dup['proposition_key']} ({dup['count']} rows)"
        )
    for dup in find_duplicate_proposition_version_ids(prop_dicts):
        errors.append(
            f"duplicate proposition_version_id: {dup['proposition_version_id']} "
            f"({dup['count']} rows)"
        )

    for d in pipeline_decisions:
        if str(d.get("decision", "")).strip().lower() != "overridden":
            continue
        rep = d.get("replacement_value")
        if rep is None:
            continue
        at = str(d.get("artifact_type", "")).strip()
        aid = str(d.get("artifact_id", "")).strip()
        if at not in SUPPORTED_EFFECTIVE_ARTIFACT_TYPES:
            errors.append(f"pipeline_review override uses unsupported artifact_type: {at!r}")
            continue
        orig = find_original_artifact_in_bundle(bundle, artifact_type=at, artifact_id=aid)
        if orig is None:
            errors.append(
                f"pipeline_review_decision override references missing artifact {at} id={aid!r}"
            )
            continue
        try:
            validate_replacement_merged(artifact_type=at, original=orig, replacement_value=rep)
        except (ValueError, ValidationError) as exc:
            errors.append(f"invalid override replacement_value for {at} {aid}: {exc}")

    source_ids = {str(item.get("id", "")) for item in source_records if isinstance(item, dict)}
    source_snapshot_ids = {
        str(item.get("current_snapshot_id", ""))
        for item in source_records
        if isinstance(item, dict)
    }
    source_snapshot_ids.update(
        str(item.get("id", "")) for item in source_snapshots if isinstance(item, dict)
    )
    source_snapshot_ids = {item for item in source_snapshot_ids if item}
    source_fragment_ids = {
        str(item.get("id", "")) for item in source_fragments if isinstance(item, dict)
    }
    source_fragment_ids = {item for item in source_fragment_ids if item}
    fragment_ids_seen: set[str] = set()
    duplicate_fragment_ids: set[str] = set()
    fragment_snapshot_ids_with_rows: set[str] = set()
    fragment_count_by_snapshot_id: dict[str, int] = {}
    for fragment in source_fragments:
        if not isinstance(fragment, dict):
            continue
        fragment_id = str(fragment.get("id", "")).strip()
        if fragment_id:
            if fragment_id in fragment_ids_seen:
                duplicate_fragment_ids.add(fragment_id)
            fragment_ids_seen.add(fragment_id)
        snapshot_id = str(fragment.get("source_snapshot_id", "")).strip()
        if snapshot_id:
            fragment_snapshot_ids_with_rows.add(snapshot_id)
            fragment_count_by_snapshot_id[snapshot_id] = (
                fragment_count_by_snapshot_id.get(snapshot_id, 0) + 1
            )
    parse_trace_by_snapshot_id: dict[str, list[dict[str, Any]]] = {}
    for parse_trace in source_parse_traces:
        if not isinstance(parse_trace, dict):
            continue
        snapshot_id = str(parse_trace.get("source_snapshot_id", "")).strip()
        if not snapshot_id:
            continue
        parse_trace_by_snapshot_id.setdefault(snapshot_id, []).append(parse_trace)
    fetch_by_source = {
        str(item.get("source_record_id", "")): item
        for item in fetch_metadata
        if isinstance(item, dict)
    }
    rationale_by_source = {
        str(item.get("source_record_id", "")): item
        for item in source_categorisation_rationales
        if isinstance(item, dict)
    }
    rationale_by_row = {
        str(item.get("source_inventory_row_id", "")): item
        for item in source_categorisation_rationales
        if isinstance(item, dict)
    }
    target_link_by_source = {
        str(item.get("source_record_id", "")): item
        for item in source_target_links
        if isinstance(item, dict)
    }
    attempts_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in source_fetch_attempts:
        if not isinstance(item, dict):
            continue
        source_record_id = str(item.get("source_record_id", ""))
        attempts_by_source.setdefault(source_record_id, []).append(item)

    for artifact in run_artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("id", "artifact-unknown"))
        content_hash = str(artifact.get("content_hash", "")).strip()
        if not content_hash or content_hash == "not-computed":
            errors.append(f"run_artifact missing content_hash: {artifact_id}")

    for proposition in propositions:
        if not isinstance(proposition, dict):
            continue
        proposition_id = str(proposition.get("id", "proposition-unknown"))
        source_record_id = str(
            proposition.get("source_record_id") or proposition.get("source_document_id") or ""
        )
        source_snapshot_id = str(proposition.get("source_snapshot_id", ""))
        if not source_record_id:
            errors.append(f"proposition missing source_record_id: {proposition_id}")
        if source_record_id and source_record_id not in source_ids:
            errors.append(f"orphan proposition source_record_id={source_record_id}: {proposition_id}")
        if not source_snapshot_id:
            errors.append(f"proposition missing source_snapshot_id: {proposition_id}")
        if source_snapshot_id and source_snapshot_ids and source_snapshot_id not in source_snapshot_ids:
            errors.append(
                f"proposition source_snapshot_id not found in source records: {proposition_id}"
            )
        source_fragment_id = str(proposition.get("source_fragment_id", "")).strip()
        if source_fragment_id and source_fragment_id not in source_fragment_ids:
            errors.append(
                "proposition references missing source fragment: "
                f"{proposition_id} ({source_fragment_id})"
            )
        if source_fragment_id and source_snapshot_id:
            fragment = next(
                (
                    item
                    for item in source_fragments
                    if isinstance(item, dict) and str(item.get("id", "")) == source_fragment_id
                ),
                None,
            )
            if (
                isinstance(fragment, dict)
                and str(fragment.get("source_snapshot_id", "")).strip() != source_snapshot_id
            ):
                errors.append(
                    "proposition references mismatched fragment/snapshot: "
                    f"{proposition_id} ({source_fragment_id})"
                )

        categories = proposition.get("categories", [])
        if isinstance(categories, list):
            for category in categories:
                category_value = str(category)
                if category_value not in ALLOWED_PROPOSITION_CATEGORIES:
                    errors.append(
                        f"invalid proposition category={category_value}: {proposition_id}"
                    )

    prop_ids_for_traces = {
        str(p.get("id", ""))
        for p in propositions
        if isinstance(p, dict) and str(p.get("id", "")).strip()
    }
    enforce_proposition_extraction_traces = bool(
        bundle.get("has_proposition_extraction_traces")
    ) or len(proposition_extraction_traces) > 0
    if propositions and not enforce_proposition_extraction_traces:
        warnings.append(
            "proposition_extraction_traces missing or empty; skipping extraction trace checks "
            "(legacy bundle)"
        )
    trace_by_proposition_id: dict[str, dict[str, Any]] = {}
    for trace in proposition_extraction_traces:
        if not isinstance(trace, dict):
            continue
        pid = str(trace.get("proposition_id", "")).strip()
        if pid:
            trace_by_proposition_id[pid] = trace

    if propositions and enforce_proposition_extraction_traces:
        trace_id_counts: dict[str, int] = {}
        for trace in proposition_extraction_traces:
            if not isinstance(trace, dict):
                continue
            tid = str(trace.get("id", "")).strip()
            if tid:
                trace_id_counts[tid] = trace_id_counts.get(tid, 0) + 1
        for tid, count in trace_id_counts.items():
            if count > 1:
                errors.append(f"duplicate extraction trace id: {tid}")

        for proposition_id in prop_ids_for_traces:
            if proposition_id not in trace_by_proposition_id:
                errors.append(f"proposition missing extraction trace: {proposition_id}")
        for proposition_id, trace in trace_by_proposition_id.items():
            trace_pk = str(trace.get("id", "proposition-extraction-trace-unknown"))
            if proposition_id not in prop_ids_for_traces:
                errors.append(
                    f"extraction trace references missing proposition: {trace_pk} ({proposition_id})"
                )
            method = str(trace.get("extraction_method", "")).strip()
            if method and method not in ALLOWED_PROPOSITION_EXTRACTION_METHODS:
                errors.append(
                    f"extraction trace invalid extraction_method={method}: {trace_pk}"
                )
            if method == "fallback" and not str(trace.get("reason", "")).strip():
                errors.append(f"extraction trace fallback without reason: {trace_pk}")
            confidence = str(trace.get("confidence", "")).strip()
            if confidence == "low":
                warnings.append(f"extraction trace low confidence: {trace_pk}")
                tid_g = str(trace.get("id", "")).strip()
                if tid_g and resolve_current_pipeline_review_decision(
                    pipeline_decisions,
                    artifact_type="proposition_extraction_trace",
                    artifact_id=tid_g,
                ) is None:
                    warnings.append(
                        "low-confidence extraction trace without pipeline_review_decision: "
                        f"{tid_g}"
                    )
            if not str(trace.get("evidence_text", "")).strip():
                warnings.append(f"extraction trace missing evidence_text: {trace_pk}")
            if not str(trace.get("evidence_locator", "")).strip():
                warnings.append(f"extraction trace missing evidence_locator: {trace_pk}")
            src_rec = str(trace.get("source_record_id", "")).strip()
            if src_rec and source_ids and src_rec not in source_ids:
                errors.append(f"extraction trace source_record_id not found: {trace_pk}")
            snap_id = str(trace.get("source_snapshot_id", "")).strip()
            if snap_id and source_snapshot_ids and snap_id not in source_snapshot_ids:
                errors.append(f"extraction trace source_snapshot_id not found: {trace_pk}")
            frag_id = str(trace.get("source_fragment_id", "")).strip()
            if frag_id and frag_id not in source_fragment_ids:
                errors.append(f"extraction trace source_fragment_id not found: {trace_pk}")
            if frag_id and snap_id:
                matched_fragment = next(
                    (
                        item
                        for item in source_fragments
                        if isinstance(item, dict) and str(item.get("id", "")).strip() == frag_id
                    ),
                    None,
                )
                if (
                    isinstance(matched_fragment, dict)
                    and str(matched_fragment.get("source_snapshot_id", "")).strip() != snap_id
                ):
                    errors.append(
                        "extraction trace references mismatched fragment/snapshot: "
                        f"{trace_pk} ({frag_id})"
                    )

    if not inventory_rows:
        errors.append("source_inventory rows are missing")

    for source in source_records:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id", ""))
        if source_id and source_id not in fetch_by_source:
            warnings.append(f"source_fetch_metadata missing for source_record_id={source_id}")
        source_attempts = attempts_by_source.get(source_id, [])
        is_fetched_source = bool(str(source.get("source_url", "")).strip())
        if is_fetched_source and not source_attempts:
            errors.append(f"fetched source has no fetch attempt: {source_id}")
    for snapshot in source_snapshots:
        if not isinstance(snapshot, dict):
            continue
        source_record_id = str(snapshot.get("source_record_id", ""))
        parser_name = str(snapshot.get("parser_name", "")).strip()
        parser_version = str(snapshot.get("parser_version", "")).strip()
        if (not parser_name or not parser_version) and source_record_id:
            warnings.append(f"snapshot parser metadata missing for source_record_id={source_record_id}")

    for fragment in source_fragments:
        if not isinstance(fragment, dict):
            continue
        fragment_id = str(fragment.get("id", "fragment-unknown")).strip() or "fragment-unknown"
        source_record_id = str(fragment.get("source_record_id", "")).strip()
        source_snapshot_id = str(fragment.get("source_snapshot_id", "")).strip()
        text_hash = str(fragment.get("text_hash") or fragment.get("fragment_hash") or "").strip()
        fragment_type = str(fragment.get("fragment_type", "")).strip().lower() or "unknown"
        locator = str(fragment.get("locator", "")).strip()
        if not source_record_id:
            errors.append(f"source fragment has no source_record_id: {fragment_id}")
        elif source_ids and source_record_id not in source_ids:
            errors.append(f"source fragment source_record_id not found: {fragment_id}")
        if not source_snapshot_id:
            errors.append(f"source fragment has no source_snapshot_id: {fragment_id}")
        elif source_snapshot_ids and source_snapshot_id not in source_snapshot_ids:
            errors.append(f"source fragment source_snapshot_id not found: {fragment_id}")
        if not text_hash:
            errors.append(f"source fragment has no text hash: {fragment_id}")
        if fragment_type not in ALLOWED_FRAGMENT_TYPES:
            warnings.append(f"source fragment fragment_type unknown: {fragment_id}")
        if fragment_type == "unknown":
            warnings.append(f"source fragment fragment_type unknown: {fragment_id}")
        if not locator:
            warnings.append(f"source fragment locator missing: {fragment_id}")

    for fragment_id in sorted(duplicate_fragment_ids):
        warnings.append(f"duplicate source fragment id exists: {fragment_id}")

    # Non-blocking: older malformed parentage remains loadable.
    for diag in validate_source_fragment_hierarchy(
        [fragment for fragment in source_fragments if isinstance(fragment, dict)]
    ):
        code = str(diag.get("code") or "").strip()
        if code not in {
            "source_fragment_parent_not_structural_ancestor",
            "source_fragment_parent_cycle",
            "source_fragment_parent_missing",
            "source_fragment_parent_scope_mismatch",
        }:
            continue
        fragment_id = str(diag.get("fragment_id") or "").strip() or "fragment-unknown"
        parent_id = str(diag.get("parent_fragment_id") or "").strip()
        locator = str(diag.get("locator") or "").strip()
        parts = [code, fragment_id]
        if parent_id:
            parts.append(parent_id)
        if locator:
            parts.append(locator)
        warnings.append(": ".join(parts))

    for snapshot_id in sorted(fragment_snapshot_ids_with_rows):
        parse_traces = parse_trace_by_snapshot_id.get(snapshot_id, [])
        if not parse_traces:
            warnings.append(f"parse trace missing for snapshot with fragments: {snapshot_id}")
            continue
        if any(str(item.get("status", "")).strip() == "failed" for item in parse_traces) and (
            fragment_count_by_snapshot_id.get(snapshot_id, 0) > 0
        ):
            warnings.append(f"parse trace status failed but fragments exist: {snapshot_id}")

    for source_record_id, source_attempts in attempts_by_source.items():
        for attempt in source_attempts:
            status = str(attempt.get("status", "")).strip()
            if status in {"success", "cache_hit"} and not str(
                attempt.get("content_hash", "")
            ).strip():
                errors.append(
                    "successful fetch/cache_hit has no content_hash: "
                    f"{source_record_id}"
                )
            if status in {"success", "cache_hit"} and not str(
                attempt.get("raw_artifact_uri", "")
            ).strip():
                warnings.append(
                    "successful fetch/cache_hit has no raw_artifact_uri: "
                    f"{source_record_id}"
                )

    hash_to_sources: dict[str, set[str]] = {}
    for source in source_records:
        if not isinstance(source, dict):
            continue
        source_hash = str(source.get("content_hash", "")).strip()
        source_id = str(source.get("id", "")).strip()
        if not source_hash or not source_id:
            continue
        hash_to_sources.setdefault(source_hash, set()).add(source_id)
    for source_hash, source_ids in hash_to_sources.items():
        if len(source_ids) <= 1:
            continue
        citations = {
            str(source.get("citation", "")).strip().lower()
            for source in source_records
            if isinstance(source, dict) and str(source.get("id", "")).strip() in source_ids
        }
        citations = {item for item in citations if item}
        if len(citations) > 1:
            warnings.append(
                "duplicate content_hash appears under multiple sources: "
                f"{source_hash} ({', '.join(sorted(source_ids))})"
            )

        rec_by_id = {
            str(s.get("id", "")).strip(): s
            for s in source_records
            if isinstance(s, dict) and str(s.get("id", "")).strip()
        }
        for sid_a, sid_b in combinations(sorted(source_ids), 2):
            ra = rec_by_id.get(sid_a)
            rb = rec_by_id.get(sid_b)
            if not isinstance(ra, dict) or not isinstance(rb, dict):
                continue
            snap_a = str(ra.get("current_snapshot_id", "")).strip()
            snap_b = str(rb.get("current_snapshot_id", "")).strip()
            if snap_a and snap_a == snap_b:
                warnings.append(
                    "distinct source_records share content_hash and identical current_snapshot_id "
                    "(unexpected snapshot identity collapse): "
                    f"snapshot_id={snap_a} sources={sid_a}, {sid_b}, content_hash={source_hash}"
                )

    for rationale in source_categorisation_rationales:
        if not isinstance(rationale, dict):
            continue
        source_record_id = str(rationale.get("source_record_id", "source-unknown"))
        method = str(rationale.get("method", "")).strip()
        if method and method not in ALLOWED_CATEGORISATION_METHODS:
            errors.append(
                f"source categorisation rationale has invalid method={method}: {source_record_id}"
            )
        confidence = str(rationale.get("confidence", "")).strip()
        if confidence and confidence not in ALLOWED_CATEGORISATION_CONFIDENCE:
            errors.append(
                "source categorisation rationale has invalid confidence="
                f"{confidence}: {source_record_id}"
            )
        if confidence == "low":
            warnings.append(f"source categorisation confidence low: {source_record_id}")
            aid = categorisation_artifact_id(rationale)
            if resolve_current_pipeline_review_decision(
                pipeline_decisions,
                artifact_type="source_categorisation_rationale",
                artifact_id=aid,
            ) is None:
                warnings.append(
                    "low-confidence categorisation without pipeline_review_decision: "
                    f"{aid}"
                )
        if method == "fallback":
            reason = str(rationale.get("reason", "")).strip()
            evidence = rationale.get("evidence")
            evidence_list = evidence if isinstance(evidence, list) else []
            if not reason:
                errors.append(f"source categorisation fallback missing reason: {source_record_id}")
            if not evidence_list:
                errors.append(f"source categorisation fallback missing evidence: {source_record_id}")

    for target_link in source_target_links:
        if not isinstance(target_link, dict):
            continue
        source_record_id = str(target_link.get("source_record_id", "source-unknown"))
        link_type = str(target_link.get("link_type", "")).strip()
        if link_type and link_type not in ALLOWED_TARGET_LINK_TYPES:
            errors.append(f"source target link has invalid link_type={link_type}: {source_record_id}")
        confidence = str(target_link.get("confidence", "")).strip()
        if confidence and confidence not in ALLOWED_CATEGORISATION_CONFIDENCE:
            errors.append(
                f"source target link has invalid confidence={confidence}: {source_record_id}"
            )
        if link_type == "unknown":
            warnings.append(f"source target link unknown: {source_record_id}")
        if confidence == "low":
            warnings.append(f"source target link confidence low: {source_record_id}")
            lid = str(target_link.get("id", "")).strip()
            if lid and resolve_current_pipeline_review_decision(
                pipeline_decisions,
                artifact_type="source_target_link",
                artifact_id=lid,
            ) is None:
                warnings.append(
                    "low-confidence source target link without pipeline_review_decision: "
                    f"{lid}"
                )
        reason = str(target_link.get("reason", "")).strip()
        evidence = target_link.get("evidence")
        evidence_list = evidence if isinstance(evidence, list) else []
        if link_type == "unknown" and not reason:
            errors.append(f"unknown source target link missing reason: {source_record_id}")
        if link_type == "unknown" and not evidence_list:
            errors.append(f"unknown source target link missing evidence: {source_record_id}")

        lid = str(target_link.get("id", "")).strip()
        if lid:
            cur_link = resolve_current_pipeline_review_decision(
                pipeline_decisions,
                artifact_type="source_target_link",
                artifact_id=lid,
            )
            if cur_link and str(cur_link.get("decision", "")).strip().lower() == "rejected":
                src = str(target_link.get("source_record_id", "")).strip()
                used = any(
                    isinstance(r, dict) and str(r.get("source_record_id", "")).strip() == src
                    for r in inventory_rows
                )
                if used:
                    warnings.append(
                        "effective view incomplete: rejected source_target_link "
                        f"{lid} still referenced by source_inventory for source_record_id={src}"
                    )

    for row in inventory_rows:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id", "source-inventory-row-unknown"))
        if not str(row.get("content_hash", "")).strip():
            errors.append(f"source_inventory row missing content_hash: {row_id}")
        if not str(row.get("source_record_id", "")).strip():
            errors.append(f"source_inventory row missing source_record_id: {row_id}")
        source_role = str(row.get("source_role", "")).strip()
        if source_role and source_role not in ALLOWED_SOURCE_ROLES:
            errors.append(f"source_inventory invalid source_role={source_role}: {row_id}")
        relationship = str(row.get("relationship_to_analysis", "")).strip()
        if relationship and relationship not in ALLOWED_ANALYSIS_RELATIONSHIPS:
            errors.append(
                "source_inventory invalid relationship_to_analysis="
                f"{relationship}: {row_id}"
            )
        rationale = rationale_by_row.get(row_id) or rationale_by_source.get(
            str(row.get("source_record_id", ""))
        )
        source_target_link = target_link_by_source.get(str(row.get("source_record_id", "")))
        if source_target_link is None:
            errors.append(f"source_inventory row missing source_target_link: {row_id}")
        if source_target_link is not None and str(source_target_link.get("link_type", "")) == "unknown":
            warnings.append(f"source_inventory row has unknown target link: {row_id}")
        if (source_role or relationship) and rationale is None:
            errors.append(f"source_inventory row has role/relationship without rationale: {row_id}")
        if source_target_link is not None:
            link_type = str(source_target_link.get("link_type", ""))
            link_reason = str(source_target_link.get("reason", "")).strip()
            link_evidence = source_target_link.get("evidence")
            link_evidence_list = link_evidence if isinstance(link_evidence, list) else []
            is_non_target_legal_source = source_role in {
                "base_act",
                "amendment",
                "delegated_act",
                "implementing_act",
                "certificate_model",
                "annex",
                "corrigendum",
            }
            if (
                is_non_target_legal_source
                and link_type == "unknown"
                and (not link_reason or not link_evidence_list)
            ):
                errors.append(
                    "non-target legal source has unknown link without reason/evidence: "
                    f"{row_id}"
                )
        if source_role == "unknown":
            warnings.append(f"source_inventory role unknown: {row_id}")
        if relationship == "unknown":
            warnings.append(f"source_inventory relationship unknown: {row_id}")
        if not str(row.get("source_url", "")).strip():
            warnings.append(f"source_inventory row missing optional source_url: {row_id}")
        if not str(row.get("version_id", "")).strip() and not row.get("consolidation_date"):
            warnings.append(
                f"source_inventory row missing optional version/consolidation date: {row_id}"
            )

    for observation in divergence_observations:
        if not isinstance(observation, dict):
            continue
        observation_id = str(observation.get("id", "observation-unknown"))
        divergence_type = str(observation.get("divergence_type", "unknown"))
        if divergence_type == "none":
            continue
        if not str(observation.get("primary_source_fragment_id", "")).strip():
            errors.append(f"divergence observation missing primary evidence: {observation_id}")
        if not str(observation.get("comparator_source_fragment_id", "")).strip():
            errors.append(f"divergence observation missing comparator evidence: {observation_id}")

    for trace in proposition_extraction_traces:
        if not isinstance(trace, dict):
            continue
        tid = str(trace.get("id", "")).strip()
        if not tid:
            continue
        cur_trace = resolve_current_pipeline_review_decision(
            pipeline_decisions,
            artifact_type="proposition_extraction_trace",
            artifact_id=tid,
        )
        if not cur_trace or str(cur_trace.get("decision")) != "rejected":
            continue
        pid = str(trace.get("proposition_id", "")).strip()
        if not pid:
            continue
        prop_dec = resolve_current_pipeline_review_decision(
            pipeline_decisions,
            artifact_type="proposition",
            artifact_id=pid,
        )
        if prop_dec and str(prop_dec.get("decision")) in ("approved", "overridden"):
            continue
        warnings.append(
            "effective view incomplete: rejected proposition_extraction_trace still used by "
            f"proposition without approved/override: trace={tid} proposition={pid}"
        )

    completeness_raw = bundle.get("proposition_completeness_assessments")
    completeness_assessments: list[dict[str, Any]] = (
        [a for a in completeness_raw if isinstance(a, dict)]
        if isinstance(completeness_raw, list)
        else []
    )
    seen_fragmentary_warnings: set[tuple[str, str]] = set()
    props_by_id_for_completeness = {
        str(p.get("id", "")).strip(): p
        for p in propositions
        if isinstance(p, dict) and str(p.get("id", "")).strip()
    }
    for assess in completeness_assessments:
        aid = str(assess.get("proposition_id", "")).strip()
        sugg = str(assess.get("suggested_display_statement") or "").strip()
        if sugg:
            prop_row = props_by_id_for_completeness.get(aid)
            raw_txt = (
                str(prop_row.get("proposition_text", "")).strip()
                if isinstance(prop_row, dict)
                else ""
            )
            if not raw_txt:
                errors.append(
                    "proposition_completeness suggested_display_statement present but raw "
                    f"proposition_text missing for proposition_id={aid!r}"
                )
        if str(assess.get("status", "")) == "fragmentary":
            if not aid:
                continue
            pdec = resolve_current_pipeline_review_decision(
                pipeline_decisions,
                artifact_type="proposition",
                artifact_id=aid,
            )
            if pdec is None:
                warn_key = (aid, "fragmentary proposition has no pipeline_review_decision")
                if warn_key not in seen_fragmentary_warnings:
                    warnings.append(
                        f"fragmentary proposition has no pipeline_review_decision: {aid}"
                    )
                    seen_fragmentary_warnings.add(warn_key)
        if str(assess.get("status", "")) == "context_dependent":
            if not sugg:
                warnings.append(
                    "context_dependent proposition has no suggested_display_statement: "
                    f"{aid or assess.get('id', 'unknown')!r}"
                )

    proposition_ids_all = {
        str(item.get("id", "")).strip()
        for item in propositions
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    scope_records_by_id = {
        str(s.get("id", "")).strip(): s
        for s in legal_scopes
        if isinstance(s, dict) and str(s.get("id", "")).strip()
    }

    if proposition_scope_links and not legal_scopes:
        errors.append(
            "proposition_scope_links present without legal_scopes taxonomy (cannot validate scope_id)"
        )

    scope_link_quality_cover: set[tuple[str, str]] = set()
    for cand in scope_review_candidates_bundle:
        if not isinstance(cand, dict):
            continue
        sig_raw = cand.get("signals")
        if not isinstance(sig_raw, dict):
            continue
        if str(sig_raw.get("review_subtype", "")).strip() != "scope_link_quality":
            continue
        cpid = str(sig_raw.get("proposition_id", "")).strip()
        cid = str(sig_raw.get("canonical_scope_id", "")).strip()
        if cpid and cid:
            scope_link_quality_cover.add((cpid, cid))

    for link in proposition_scope_links:
        if not isinstance(link, dict):
            continue
        lid = str(link.get("id", "proposition-scope-link-unknown")).strip()
        sid = str(link.get("scope_id", "")).strip()
        pid = str(link.get("proposition_id", "")).strip()
        method = str(link.get("method", "")).strip()
        relevance = str(link.get("relevance", "")).strip()
        inheritance = str(link.get("inheritance", "")).strip()
        confidence = str(link.get("confidence", "")).strip()

        if sid and sid not in scope_records_by_id:
            errors.append(f"proposition_scope_link references invalid scope_id: {lid}: {sid}")
        if pid and pid not in proposition_ids_all:
            errors.append(f"proposition_scope_link references missing proposition: {lid}: {pid}")

        if method and method not in ALLOWED_SCOPE_LINK_METHODS:
            errors.append(f"proposition_scope_link invalid method={method}: {lid}")
        if relevance and relevance not in ALLOWED_SCOPE_RELEVANCE:
            errors.append(f"proposition_scope_link invalid relevance={relevance}: {lid}")
        if inheritance and inheritance not in ALLOWED_SCOPE_INHERITANCE:
            errors.append(f"proposition_scope_link invalid inheritance={inheritance}: {lid}")
        if confidence and confidence not in ALLOWED_SCOPE_CONFIDENCE:
            errors.append(f"proposition_scope_link invalid confidence={confidence}: {lid}")

        scope_rec = scope_records_by_id.get(sid)
        if scope_rec is not None and str(scope_rec.get("status", "")).strip() == "deprecated":
            warnings.append(f"proposition_scope_link targets deprecated scope: {lid}: {sid}")

        if _should_warn_proposition_scope_link_low_confidence(link):
            warnings.append(f"proposition_scope_link confidence low: {lid}")

        if method == "fallback":
            reason = str(link.get("reason", "")).strip()
            evidence = link.get("evidence")
            evlist = evidence if isinstance(evidence, list) else []
            if not reason:
                errors.append(f"proposition_scope_link fallback missing reason: {lid}")
            if not evlist:
                errors.append(f"proposition_scope_link fallback missing evidence: {lid}")

        if method == "deterministic":
            sig_ln = link.get("signals")
            ev_field = ""
            if isinstance(sig_ln, dict):
                raw_ef = sig_ln.get("evidence_field")
                if isinstance(raw_ef, str):
                    ev_field = raw_ef.strip()
            if relevance == "direct":
                if ev_field and ev_field not in _DIRECT_SCOPE_ACCEPT_EVIDENCE_FIELDS:
                    warnings.append(
                        "proposition_scope_link direct applicability without grounded evidence "
                        "(proposition_text/source_fragment_text/legal_subject/affected_subjects/"
                        "required_documents/conditions; check signals.evidence_field): "
                        f"{lid}: field={ev_field!r}"
                    )
            elif (
                relevance == "contextual"
                and confidence == "low"
                and inheritance == "explicit"
            ):
                if pid and sid and (pid, sid) not in scope_link_quality_cover:
                    warnings.append(
                        "proposition_scope_link contextual/low explicit link without paired "
                        f"scope_link_quality scope_review_candidates entry (review coverage gap): "
                        f"{lid}"
                    )

    lrr_payload = bundle.get("legal_rule_relationships")
    if isinstance(lrr_payload, dict):
        lrr_diags = lrr_payload.get("diagnostics")
        if isinstance(lrr_diags, list):
            for diag in lrr_diags:
                if not isinstance(diag, dict):
                    continue
                code = str(diag.get("code") or "").strip()
                if code not in {
                    "typed_relationship_target_ambiguous",
                    "typed_relationship_target_group_missing",
                    "typed_relationship_reference_not_uniquely_associated",
                }:
                    continue
                source_id = str(diag.get("source_id") or "").strip() or "unknown"
                rel_type = str(diag.get("relationship_type") or "").strip()
                ref = str(diag.get("referenced_locator") or "").strip()
                parts = [code, source_id]
                if rel_type:
                    parts.append(rel_type)
                if ref:
                    parts.append(ref)
                warnings.append(": ".join(parts) if len(parts) == 2 else f"{parts[0]}: {': '.join(parts[1:])}")

    law_payload = bundle.get("effective_law_statements")
    if isinstance(law_payload, dict):
        law_diags = law_payload.get("diagnostics")
        if isinstance(law_diags, list):
            for diag in law_diags:
                if not isinstance(diag, dict):
                    continue
                code = str(diag.get("code") or "").strip()
                if code not in {
                    "effective_law_relationship_source_missing",
                    "effective_law_relationship_target_missing",
                    "effective_law_relationship_group_missing",
                    "effective_law_relationship_group_member_missing",
                    "effective_law_relationship_source_scope_mismatch",
                }:
                    continue
                rel_id = str(diag.get("relationship_id") or "").strip()
                source_id = str(diag.get("source_id") or "").strip()
                target_id = str(diag.get("target_id") or "").strip()
                member_id = str(diag.get("member_id") or "").strip()
                parts = [code]
                if rel_id:
                    parts.append(rel_id)
                if source_id:
                    parts.append(source_id)
                if target_id:
                    parts.append(target_id)
                if member_id:
                    parts.append(member_id)
                warnings.append(": ".join(parts) if len(parts) == 1 else f"{parts[0]}: {': '.join(parts[1:])}")

    return {
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


def lint_export_dir(
    export_dir: str | Path,
    *,
    include_run_quality_summary: bool = True,
) -> dict[str, Any]:
    from .run_quality import build_run_quality_summary

    bundle = load_exported_bundle(export_dir=export_dir)
    lint_report = lint_bundle(bundle)
    result: dict[str, Any] = {
        "export_dir": str(Path(export_dir)),
        "run_id": bundle.get("run", {}).get("id"),
        **lint_report,
    }
    if include_run_quality_summary:
        result["run_quality_summary"] = build_run_quality_summary(
            bundle,
            lint_report=lint_report,
        )
    return result
