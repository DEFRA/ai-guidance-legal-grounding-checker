"""Equine (generic corpus) builder: discovery merge, export, and coverage artifacts."""

from __future__ import annotations

import copy
import csv
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain.enums import ReviewStatus

from .equine_source_universe import build_universe_readiness_snapshot
from .export import export_bundle
from .file_input import load_case_file
from .linting import lint_bundle
from .run_quality import build_run_quality_summary
from .runner import build_bundle_from_case
from .sources.source_family_discovery import discover_related_for_registry_entry

EQUINE_SCOPE_ID = "equine"

EquineRelevance = Literal["direct", "indirect", "contextual", "none", "unknown"]

_RELEVANCE_RANK: dict[str, int] = {
    "direct": 5,
    "indirect": 4,
    "contextual": 3,
    "none": 2,
    "unknown": 1,
}

_COVERAGE_DISCLAIMER = (
    "Coverage status is based on automated extraction and scope-linking signals. "
    "Pending human review — not a claim of complete equine law. Source text and "
    "evidence quotes in the bundle remain authoritative."
)


def _is_developer_fixture_row(row: dict[str, Any]) -> bool:
    return str(row.get("source_id") or "").startswith("fixture-")


def _is_discovery_candidate_row(row: dict[str, Any]) -> bool:
    return "Discovery candidate only" in str(row.get("inclusion_reason") or "")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_corpus_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Corpus config must be a JSON object.")
    if str(raw.get("corpus_id") or "").strip() != "equine_law":
        raise ValueError("corpus_id must be 'equine_law' for this workflow entrypoint.")
    scopes = raw.get("focus_scopes")
    if not isinstance(scopes, list) or not all(str(s).strip() for s in scopes):
        raise ValueError("focus_scopes must be a non-empty list of strings.")
    case_path = str(raw.get("source_case_path") or "").strip()
    if not case_path:
        raise ValueError("source_case_path is required.")
    return raw


def resolve_case_path(case_path: str) -> Path:
    candidate = Path(case_path)
    if candidate.is_absolute():
        return candidate
    return (Path.cwd() / candidate).resolve()


def _coerce_registry_entry(entry: dict[str, Any]) -> dict[str, Any]:
    rid = str(entry.get("registry_id") or "corpus-seed").strip()
    ref = entry.get("reference")
    if not isinstance(ref, dict):
        raise ValueError("Each seed_registry_entries item needs a reference object.")
    return {"registry_id": rid, "reference": ref}


def _lint_warnings_by_gate(warnings: list[Any]) -> dict[str, int]:
    gates: dict[str, int] = defaultdict(int)
    for w in warnings:
        ws = str(w)
        gate = ws.split(":", 1)[0].strip() if ":" in ws else "general"
        gates[gate] += 1
    return dict(sorted(gates.items()))


def merge_source_family_candidates(
    *,
    case_data: dict[str, Any],
    corpus_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_existing = case_data.get("source_family_candidates")
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(raw_existing, list):
        for row in raw_existing:
            if isinstance(row, dict) and row.get("id"):
                rid = str(row["id"])
                if rid not in seen:
                    merged.append(row)
                    seen.add(rid)
    disco = corpus_cfg.get("related_source_discovery")
    if not isinstance(disco, dict) or not disco.get("enabled"):
        return merged
    seeds = disco.get("seed_registry_entries")
    if not isinstance(seeds, list):
        return merged
    for seed in seeds:
        if not isinstance(seed, dict):
            continue
        entry = _coerce_registry_entry(seed)
        bundle = discover_related_for_registry_entry(entry)
        for row in bundle.get("candidates") or []:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("id") or "")
            if cid and cid not in seen:
                merged.append(row)
                seen.add(cid)
    return merged


def _normalize_equine_relevance(value: str) -> EquineRelevance:
    v = value.strip().lower()
    if v in {"direct", "indirect", "contextual", "none", "unknown"}:
        return v  # type: ignore[return-value]
    return "unknown"


def _pick_relevance(a: EquineRelevance, b: EquineRelevance) -> EquineRelevance:
    return a if _RELEVANCE_RANK[a] >= _RELEVANCE_RANK[b] else b


def _proposition_trace_map(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in bundle.get("proposition_extraction_traces") or []:
        if isinstance(row, dict):
            pid = str(row.get("proposition_id") or "")
            if pid:
                out[pid] = row
    return out


def _completeness_map(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in bundle.get("proposition_completeness_assessments") or []:
        if isinstance(row, dict):
            pid = str(row.get("proposition_id") or "")
            if pid:
                out[pid] = row
    return out


def _scope_links_for_propositions(bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_prop: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bundle.get("proposition_scope_links") or []:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("proposition_id") or "")
        if pid:
            by_prop[pid].append(row)
    return by_prop


def _equine_relevance_for_proposition(links: list[dict[str, Any]]) -> EquineRelevance:
    rel: EquineRelevance = "unknown"
    for link in links:
        if str(link.get("scope_id") or "") != EQUINE_SCOPE_ID:
            continue
        r = _normalize_equine_relevance(str(link.get("relevance") or "unknown"))
        rel = _pick_relevance(rel, r)
    return rel


def _source_row_from_metadata(src: dict[str, Any]) -> tuple[EquineRelevance | None, bool | None, str]:
    md = src.get("metadata")
    if not isinstance(md, dict):
        return None, None, ""
    ec = md.get("equine_corpus")
    if not isinstance(ec, dict):
        return None, None, ""
    er = ec.get("equine_relevance")
    rel: EquineRelevance | None = (
        _normalize_equine_relevance(str(er)) if er is not None and str(er).strip() else None
    )
    inc = ec.get("included_in_corpus")
    included: bool | None = bool(inc) if isinstance(inc, bool) else None
    reason = str(ec.get("exclusion_reason") or ec.get("inclusion_reason") or "")
    return rel, included, reason


def _failed_sources(bundle: dict[str, Any]) -> set[str]:
    failed: set[str] = set()
    for row in bundle.get("proposition_extraction_failures") or []:
        if isinstance(row, dict):
            sid = str(row.get("source_record_id") or "")
            if sid:
                failed.add(sid)
    return failed


def _equine_discovery_fields(meta: dict[str, Any]) -> dict[str, str]:
    nested = meta.get("equine_law_discovery") if isinstance(meta.get("equine_law_discovery"), dict) else {}
    return {
        "equine_law_group": str(nested.get("family") or "").strip(),
        "equine_instrument_lineage": str(nested.get("lineage") or "").strip(),
    }


def build_source_coverage_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    sources = bundle.get("source_records", bundle.get("sources", [])) or []
    if not isinstance(sources, list):
        return []
    props = bundle.get("propositions") or []
    prop_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if isinstance(props, list):
        for p in props:
            if isinstance(p, dict):
                sid = str(p.get("source_record_id") or "")
                if sid:
                    prop_by_source[sid].append(p)

    links_by_prop = _scope_links_for_propositions(bundle)
    failed_sources = _failed_sources(bundle)
    reviewed_statuses = {
        ReviewStatus.ACCEPTED.value,
        ReviewStatus.ACCEPTED_WITH_EDITS.value,
        ReviewStatus.REJECTED.value,
        ReviewStatus.NEEDS_MORE_SOURCES.value,
        ReviewStatus.SUPERSEDED.value,
    }

    rows: list[dict[str, Any]] = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        sid = str(src.get("id") or "")
        title = str(src.get("title") or "")
        citation = str(src.get("citation") or "")
        md_rel, md_inc, md_reason = _source_row_from_metadata(src)
        relevances: list[EquineRelevance] = []
        if md_rel is not None:
            relevances.append(md_rel)
        if md_inc is not False:
            for p in prop_by_source.get(sid, []):
                pid = str(p.get("id") or "")
                er = _equine_relevance_for_proposition(links_by_prop.get(pid, []))
                if er != "unknown":
                    relevances.append(er)
        equine_relevance: EquineRelevance = "unknown"
        for r in relevances:
            equine_relevance = _pick_relevance(equine_relevance, r)
        if not relevances:
            equine_relevance = md_rel or "unknown"
        if md_inc is False:
            equine_relevance = md_rel or "none"

        included_in_corpus = True
        inclusion_reason = "Ingested as pipeline source for this run."
        if md_inc is False:
            included_in_corpus = False
            inclusion_reason = md_reason or "Marked excluded in source metadata (equine_corpus)."
        elif equine_relevance == "none" and not prop_by_source.get(sid):
            included_in_corpus = False
            inclusion_reason = "No equine-linked propositions and metadata suggests non-equine scope."

        prop_count = len(prop_by_source.get(sid, []))
        reviewed_count = sum(
            1
            for p in prop_by_source.get(sid, [])
            if str(p.get("review_status") or "") in reviewed_statuses
        )

        extraction_status: str
        if not included_in_corpus:
            extraction_status = "excluded"
        elif sid in failed_sources:
            extraction_status = "failed"
        elif prop_count > 0:
            extraction_status = "extracted"
        else:
            extraction_status = "not_started"

        if (
            extraction_status == "extracted"
            and prop_count > 0
            and reviewed_count == prop_count
        ):
            extraction_status = "reviewed"

        meta = src.get("metadata") if isinstance(src.get("metadata"), dict) else {}
        ec_meta = meta.get("equine_corpus") if isinstance(meta.get("equine_corpus"), dict) else {}
        esu = meta.get("equine_source_universe") if isinstance(meta.get("equine_source_universe"), dict) else {}
        edisc = _equine_discovery_fields(meta)
        group_v = edisc["equine_law_group"] or str(ec_meta.get("equine_law_group") or "")
        lineage_v = edisc["equine_instrument_lineage"] or str(ec_meta.get("equine_instrument_lineage") or "")
        source_role = str(ec_meta.get("source_role") or esu.get("analysis_role") or "ingested")
        relationship = str(ec_meta.get("relationship_to_target") or "unknown")
        gaps: list[str] = []
        if prop_count == 0 and included_in_corpus and sid not in failed_sources:
            gaps.append("No propositions extracted; check extraction mode and source text.")
        if equine_relevance == "unknown" and included_in_corpus:
            gaps.append("Equine relevance unknown; confirm scope links or manual tagging.")

        celex_v = ""
        eli_v = ""
        url_v = ""
        cand_confidence = ""
        if isinstance(meta, dict):
            celex_v = str(ec_meta.get("celex") or meta.get("celex") or "")
            eli_v = str(ec_meta.get("eli") or meta.get("eli") or "")
            url_v = str(ec_meta.get("url") or meta.get("url") or "")
            cand_confidence = str(ec_meta.get("confidence") or "")

        rows.append(
            {
                "source_id": sid,
                "title": title,
                "citation": citation,
                "celex": celex_v,
                "eli": eli_v,
                "url": url_v,
                "confidence": cand_confidence,
                "source_role": source_role,
                "relationship_to_target": relationship,
                "equine_relevance": equine_relevance,
                "included_in_corpus": included_in_corpus,
                "inclusion_reason": inclusion_reason,
                "extraction_status": extraction_status,
                "proposition_count": prop_count,
                "reviewed_proposition_count": reviewed_count,
                "gaps_or_notes": "; ".join(gaps),
                "equine_law_group": group_v,
                "equine_instrument_lineage": lineage_v,
                "corpus_candidate_inclusion_status": "",
                "equine_portfolio_status": "included_legal_source" if included_in_corpus else "excluded_or_out_of_scope",
            }
        )

    for cand in bundle.get("source_family_candidates") or []:
        if not isinstance(cand, dict):
            continue
        cid = str(cand.get("id") or cand.get("candidate_source_id") or "")
        c_meta = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else {}
        edisc = _equine_discovery_fields(c_meta)
        lineage = edisc["equine_instrument_lineage"]
        portfolio = "pending_discovery_candidate"
        if lineage == "retained_historical_baseline":
            portfolio = "retained_historical_baseline"
        elif lineage == "current_operative_eu":
            portfolio = "current_operative_eu_candidate"
        elif lineage in {"corrigendum_only", "annex_fragment"}:
            portfolio = f"related_fragment:{lineage}"
        elif lineage == "guidance_only":
            portfolio = "guidance_context_only"
        esu_c = c_meta.get("equine_source_universe") if isinstance(c_meta.get("equine_source_universe"), dict) else {}
        cand_role = str(cand.get("source_role") or "unknown")
        if esu_c.get("analysis_role"):
            cand_role = str(esu_c["analysis_role"])
        rows.append(
            {
                "source_id": cid or str(cand.get("title") or "candidate"),
                "title": str(cand.get("title") or ""),
                "citation": str(cand.get("citation") or cand.get("celex") or ""),
                "celex": str(cand.get("celex") or ""),
                "eli": str(cand.get("eli") or ""),
                "url": str(cand.get("url") or ""),
                "confidence": str(cand.get("confidence") or ""),
                "source_role": cand_role,
                "relationship_to_target": str(cand.get("relationship_to_target") or "unknown"),
                "equine_relevance": "unknown",
                "included_in_corpus": False,
                "inclusion_reason": "Discovery candidate only — register and ingest to analyse.",
                "extraction_status": "not_started",
                "proposition_count": 0,
                "reviewed_proposition_count": 0,
                "gaps_or_notes": str(cand.get("reason") or ""),
                "equine_law_group": edisc["equine_law_group"],
                "equine_instrument_lineage": lineage,
                "corpus_candidate_inclusion_status": str(cand.get("inclusion_status") or ""),
                "equine_portfolio_status": portfolio,
            }
        )
    return rows


def _guidance_ready_for_proposition(
    *,
    review_status: str,
    trace_confidence: str,
    completeness_status: str | None,
) -> tuple[bool, str]:
    reasons: list[str] = []
    if trace_confidence != "high":
        reasons.append(f"extraction confidence is {trace_confidence!r}, not high")
    if review_status not in {
        ReviewStatus.ACCEPTED.value,
        ReviewStatus.ACCEPTED_WITH_EDITS.value,
    }:
        reasons.append(f"review_status is {review_status!r} (needs accepted decision)")
    if completeness_status == "fragmentary":
        reasons.append("completeness is fragmentary")
    if reasons:
        return False, "; ".join(reasons)
    return True, ""


def build_proposition_coverage_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    props = bundle.get("propositions") or []
    if not isinstance(props, list):
        return []
    traces = _proposition_trace_map(bundle)
    completeness = _completeness_map(bundle)
    links_by_prop = _scope_links_for_propositions(bundle)
    rows: list[dict[str, Any]] = []
    for p in props:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "")
        trace = traces.get(pid, {})
        conf = str(trace.get("confidence") or "medium")
        rev = str(p.get("review_status") or ReviewStatus.PROPOSED.value)
        ca = completeness.get(pid, {})
        cstat = str(ca.get("status")) if ca.get("status") else None
        links = links_by_prop.get(pid, [])
        scope_links = [
            {
                "scope_id": str(x.get("scope_id") or ""),
                "relevance": str(x.get("relevance") or ""),
                "confidence": str(x.get("confidence") or ""),
            }
            for x in links
        ]
        ready, why_not = _guidance_ready_for_proposition(
            review_status=rev,
            trace_confidence=conf,
            completeness_status=cstat,
        )
        rows.append(
            {
                "proposition_id": pid,
                "proposition_key": p.get("proposition_key"),
                "source_id": str(p.get("source_record_id") or ""),
                "article_locator": p.get("fragment_locator") or p.get("article_reference"),
                "scope_links": scope_links,
                "completeness_status": cstat,
                "extraction_confidence": conf,
                "review_status": rev,
                "guidance_ready": ready,
                "reason_if_not_guidance_ready": why_not if not ready else "",
            }
        )
    return rows


def build_coverage_summary(
    *,
    source_rows: list[dict[str, Any]],
    proposition_rows: list[dict[str, Any]],
    source_family_candidate_count: int,
    bundle: dict[str, Any] | None = None,
    lint_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    included_sources = sum(
        1
        for r in source_rows
        if r.get("included_in_corpus")
        and not _is_discovery_candidate_row(r)
        and not _is_developer_fixture_row(r)
        and str(r.get("extraction_status") or "") != "excluded"
    )

    pending_legal_candidates = sum(
        1 for r in source_rows if not _is_developer_fixture_row(r) and _is_discovery_candidate_row(r)
    )

    excluded_legal_candidates = sum(
        1
        for r in source_rows
        if not _is_developer_fixture_row(r) and str(r.get("extraction_status") or "") == "excluded"
    )

    developer_validation_fixtures = sum(1 for r in source_rows if _is_developer_fixture_row(r))

    guidance_ready_n = sum(1 for pr in proposition_rows if pr.get("guidance_ready") is True)
    propositions_total = len(proposition_rows)

    direct = sum(
        1
        for pr in proposition_rows
        if any(
            isinstance(sl, dict)
            and str(sl.get("scope_id")) == EQUINE_SCOPE_ID
            and str(sl.get("relevance") or "") == "direct"
            for sl in pr.get("scope_links") or []
        )
    )
    indirect = sum(
        1
        for pr in proposition_rows
        if any(
            isinstance(sl, dict)
            and str(sl.get("scope_id")) == EQUINE_SCOPE_ID
            and str(sl.get("relevance") or "") == "indirect"
            for sl in pr.get("scope_links") or []
        )
    )
    contextual = sum(
        1
        for pr in proposition_rows
        if any(
            isinstance(sl, dict)
            and str(sl.get("scope_id")) == EQUINE_SCOPE_ID
            and str(sl.get("relevance") or "") == "contextual"
            for sl in pr.get("scope_links") or []
        )
    )
    unreviewed = sum(
        1
        for pr in proposition_rows
        if str(pr.get("review_status") or "") == ReviewStatus.PROPOSED.value
    )
    gaps: list[str] = []
    for sr in source_rows:
        if str(sr.get("gaps_or_notes") or "").strip():
            gaps.append(f"{sr.get('source_id')}: {sr.get('gaps_or_notes')}")
    for pr in proposition_rows:
        if not pr.get("guidance_ready") and str(pr.get("reason_if_not_guidance_ready") or "").strip():
            gaps.append(f"{pr.get('proposition_id')}: {pr.get('reason_if_not_guidance_ready')}")
    if bundle is not None:
        missing_required = bundle.get("missing_required_fragment_locators") or []
        if isinstance(missing_required, list):
            for locator in missing_required:
                loc = str(locator).strip()
                if loc:
                    gaps.append(f"required_fragment_locator_missing: {loc}")

    return {
        "coverage_status": "pending_review",
        "sources_discovered_candidates": source_family_candidate_count,
        "sources_included_rows": included_sources,
        "included_legal_sources": included_sources,
        "pending_legal_candidates": pending_legal_candidates,
        "excluded_legal_candidates": excluded_legal_candidates,
        "developer_validation_fixtures": developer_validation_fixtures,
        "guidance_ready_propositions": guidance_ready_n,
        "propositions_total": propositions_total,
        "propositions_direct_equine_scope": direct,
        "propositions_indirect_equine_scope": indirect,
        "propositions_contextual_equine_scope": contextual,
        "propositions_unreviewed": unreviewed,
        "gaps_needing_manual_review": gaps[:50],
        **(_bundle_trace_quality(bundle)),
        **(_lint_quality_embed(lint_report, bundle)),
    }


def _bundle_trace_quality(bundle: dict[str, Any] | None) -> dict[str, Any]:
    if bundle is None:
        return {}
    traces = bundle.get("proposition_extraction_traces") or []
    if not isinstance(traces, list):
        return {}
    fb_n = sum(1 for t in traces if isinstance(t, dict) and str(t.get("method") or "") == "fallback")
    low_n = sum(
        1 for t in traces if isinstance(t, dict) and str(t.get("confidence") or "").lower() == "low"
    )
    return {
        "extraction_trace_fallback_method_count": fb_n,
        "extraction_trace_low_confidence_count": low_n,
    }


def _lint_quality_embed(
    lint_report: dict[str, Any] | None,
    bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    if lint_report is None:
        return {}
    warns = list(lint_report.get("warnings") or [])
    out: dict[str, Any] = {
        "lint_ok": bool(lint_report.get("ok")),
        "lint_warning_total": int(lint_report.get("warning_count") or 0),
        "lint_error_total": int(lint_report.get("error_count") or 0),
        "lint_warnings_message_bucket": _lint_warnings_by_gate(warns),
    }
    if bundle is not None:
        rq = build_run_quality_summary(bundle, lint_report=lint_report)
        gates = rq.get("gate_results") or []
        out["lint_warnings_by_quality_gate"] = {
            str(g["gate_id"]): int(g.get("warning_count") or 0)
            for g in gates
            if isinstance(g, dict) and int(g.get("warning_count") or 0) > 0
        }
    return out


def write_equine_coverage_artifacts(
    output_dir: str | Path,
    *,
    corpus_id: str,
    source_rows: list[dict[str, Any]],
    proposition_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    source_universe_snapshot: dict[str, Any] | None = None,
) -> None:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    gen_at = utc_now_iso()
    base_meta = {
        "corpus_id": corpus_id,
        "coverage_status": "pending_review",
        "generated_at": gen_at,
        "disclaimer": _COVERAGE_DISCLAIMER,
        "summary": summary,
    }
    src_payload = {**base_meta, "sources": source_rows}
    (root / "equine_source_coverage.json").write_text(
        json.dumps(src_payload, indent=2), encoding="utf-8"
    )
    prop_payload = {**base_meta, "propositions": proposition_rows}
    (root / "equine_proposition_coverage.json").write_text(
        json.dumps(prop_payload, indent=2), encoding="utf-8"
    )
    if source_rows:
        csv_path = root / "equine_source_coverage.csv"
        fieldnames = sorted({key for row in source_rows for key in row.keys()})
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(source_rows)
    readiness = {
        "corpus_id": corpus_id,
        "coverage_status": "pending_review",
        "generated_at": gen_at,
        "disclaimer": _COVERAGE_DISCLAIMER,
        "summary": summary,
    }
    if source_universe_snapshot:
        readiness["source_universe"] = source_universe_snapshot
    (root / "equine_corpus_readiness.json").write_text(
        json.dumps(readiness, indent=2), encoding="utf-8"
    )


def prepare_case_data_for_equine_corpus(
    corpus_config_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    cfg_path = Path(corpus_config_path)
    corpus_cfg = load_corpus_config(cfg_path)
    case_path = resolve_case_path(str(corpus_cfg["source_case_path"]))
    case_data = copy.deepcopy(load_case_file(case_path))
    note = (
        f"Corpus workflow ({corpus_cfg['corpus_id']}): coverage status pending review; "
        "not a claim of complete equine law."
    )
    prev = str(case_data.get("run_notes") or "").strip()
    case_data["run_notes"] = f"{prev}\n{note}".strip() if prev else note
    cx = dict(case_data.get("extraction") or {})
    top_level_defaults: dict[str, Any] = {}
    top_level_defaults["focus_scopes"] = list(corpus_cfg["focus_scopes"])

    mp = corpus_cfg.get("max_propositions_per_source")
    if isinstance(mp, int) and mp > 0:
        top_level_defaults["max_propositions_per_source"] = mp
    elif isinstance(mp, str) and mp.strip().isdigit():
        v = int(mp.strip())
        if v > 0:
            top_level_defaults["max_propositions_per_source"] = v

    em = corpus_cfg.get("extraction_mode")
    if isinstance(em, str) and em.strip():
        top_level_defaults["mode"] = em.strip()

    fb = corpus_cfg.get("extraction_fallback")
    if isinstance(fb, str) and fb.strip():
        top_level_defaults["fallback_policy"] = fb.strip()

    div = corpus_cfg.get("divergence_reasoning")
    if isinstance(div, str) and div.strip():
        top_level_defaults["divergence_reasoning"] = div.strip()

    mep = corpus_cfg.get("model_error_policy")
    if isinstance(mep, str) and mep.strip():
        top_level_defaults["model_error_policy"] = mep.strip()

    include_annexes = corpus_cfg.get("include_annexes")
    if isinstance(include_annexes, bool):
        top_level_defaults["include_annexes"] = include_annexes

    focus_terms = corpus_cfg.get("focus_terms")
    if isinstance(focus_terms, list):
        top_level_defaults["focus_terms"] = [str(x).strip() for x in focus_terms if str(x).strip()]

    required_locators = corpus_cfg.get("required_fragment_locators")
    if isinstance(required_locators, list):
        top_level_defaults["required_fragment_locators"] = [
            str(x).strip() for x in required_locators if str(x).strip()
        ]
    selection_mode = corpus_cfg.get("fragment_selection_mode")
    if isinstance(selection_mode, str) and selection_mode.strip():
        top_level_defaults["fragment_selection_mode"] = selection_mode.strip()

    nested_cfg = corpus_cfg.get("extraction")
    nested_overrides = dict(nested_cfg) if isinstance(nested_cfg, dict) else {}
    nested_mode = nested_overrides.pop("extraction_mode", None)
    if isinstance(nested_mode, str) and nested_mode.strip():
        nested_overrides["mode"] = nested_mode.strip()
    nested_fallback = nested_overrides.pop("extraction_fallback", None)
    if isinstance(nested_fallback, str) and nested_fallback.strip():
        nested_overrides["fallback_policy"] = nested_fallback.strip()

    cx.update(top_level_defaults)
    cx.update(nested_overrides)
    case_data["extraction"] = cx
    merged = merge_source_family_candidates(case_data=case_data, corpus_cfg=corpus_cfg)
    if merged:
        case_data["source_family_candidates"] = merged
    return case_data, corpus_cfg, case_path


def _source_universe_snapshot_for_export(
    *,
    corpus_cfg: dict[str, Any],
    case_data: dict[str, Any],
) -> dict[str, Any] | None:
    """Staged-universe bookkeeping when corpus config or case references ``equine_source_universe.json``."""
    up = str(corpus_cfg.get("equine_source_universe_path") or "").strip()
    cpid_cfg = str(corpus_cfg.get("corpus_profile_id") or "").strip()
    cpid_case = str(case_data.get("corpus_profile_id") or "").strip()
    profile_id = cpid_cfg or cpid_case
    ref = case_data.get("equine_source_universe_ref")
    path_s = up
    if not path_s and isinstance(ref, dict) and ref.get("path"):
        path_s = str(ref["path"])
    if not path_s or not profile_id:
        return None
    analysed = len(case_data.get("sources") or [])
    try:
        return build_universe_readiness_snapshot(
            universe_path=resolve_case_path(path_s),
            profile_id=profile_id,
            analysed_legislation_source_count=analysed,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def run_equine_corpus_export(
    *,
    corpus_config_path: str | Path,
    output_dir: str,
    use_llm: bool = False,
    extraction_mode: str | None = None,
    extraction_execution_mode: str | None = None,
    extraction_fallback: str | None = None,
    divergence_reasoning: str | None = None,
    source_cache_dir: str | None = None,
    derived_cache_dir: str | None = None,
    progress: Any | None = None,
    focus_scopes: list[str] | None = None,
    max_propositions_per_source: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_data, corpus_cfg, _case_path = prepare_case_data_for_equine_corpus(corpus_config_path)
    cx = dict(case_data.get("extraction") or {})
    if focus_scopes is not None:
        scopes = [str(s).strip() for s in focus_scopes if str(s).strip()]
        if scopes:
            cx["focus_scopes"] = scopes
    if max_propositions_per_source is not None:
        cx["max_propositions_per_source"] = int(max_propositions_per_source)
    case_data["extraction"] = cx
    bundle = build_bundle_from_case(
        case_data,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        extraction_execution_mode=extraction_execution_mode,
        extraction_fallback=extraction_fallback,
        divergence_reasoning=divergence_reasoning,
        source_cache_dir=source_cache_dir,
        derived_cache_dir=derived_cache_dir,
        progress=progress,
    )
    if progress is not None:
        progress.stage("Export bundle", detail=str(output_dir))
    export_bundle(bundle, output_dir=output_dir)
    lint_report = lint_bundle(bundle)
    rq = bundle.get("run_quality_summary") if isinstance(bundle.get("run_quality_summary"), dict) else {}
    if progress is not None:
        progress.stage(
            "Lint / quality summary",
            detail=f"status={rq.get('status')}, warnings={rq.get('warning_count', 0)}",
        )
    src_rows = build_source_coverage_rows(bundle)
    prop_rows = build_proposition_coverage_rows(bundle)
    summary = build_coverage_summary(
        source_rows=src_rows,
        proposition_rows=prop_rows,
        source_family_candidate_count=len(bundle.get("source_family_candidates") or []),
        bundle=bundle,
        lint_report=lint_report,
    )
    uni_snap = _source_universe_snapshot_for_export(corpus_cfg=corpus_cfg, case_data=case_data)
    write_equine_coverage_artifacts(
        output_dir,
        corpus_id=str(corpus_cfg["corpus_id"]),
        source_rows=src_rows,
        proposition_rows=prop_rows,
        summary=summary,
        source_universe_snapshot=uni_snap,
    )
    return bundle, summary
