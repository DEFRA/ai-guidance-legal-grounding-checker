"""Equine corpus builder: discovery merge, coverage rows, guidance readiness (fixtures)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from law_proposition_extractor_api.main import app
from law_proposition_extractor_api.settings import settings
from law_proposition_extractor_pipeline.equine_corpus_workflow import (
    build_coverage_summary,
    build_proposition_coverage_rows,
    build_source_coverage_rows,
    merge_source_family_candidates,
    prepare_case_data_for_equine_corpus,
    run_equine_corpus_export,
)
from law_proposition_extractor_pipeline.runner import build_bundle_from_case


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_direct_equine_fixture_included(tmp_path: Path) -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law_fixtures.json"
    case_data, _c, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
        derived_cache_dir=str(tmp_path / "derived-cache-direct"),
    )
    rows = build_source_coverage_rows(bundle)
    direct = next(r for r in rows if r["source_id"] == "fixture-equine-direct")
    assert direct["included_in_corpus"] is True
    assert direct["equine_relevance"] == "direct"


def test_merge_discovery_inserts_fixture_candidates() -> None:
    cfg = json.loads((REPO_ROOT / "examples" / "corpus_equine_law_fixtures.json").read_text(encoding="utf-8"))
    case = json.loads((REPO_ROOT / "examples" / "equine_corpus_fixture_case.json").read_text(encoding="utf-8"))
    merged = merge_source_family_candidates(case_data=case, corpus_cfg=cfg)
    assert len(merged) >= 3
    titles = {str(x.get("title", "")) for x in merged}
    assert any("2016/429" in t for t in titles)


def test_bovine_only_source_excluded_with_reason() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law_fixtures.json"
    case_data, _corpus_cfg, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    rows = build_source_coverage_rows(bundle)
    bov = next(r for r in rows if r["source_id"] == "fixture-bovine-only-excluded")
    assert bov["included_in_corpus"] is False
    assert "bovidae" in str(bov["inclusion_reason"]).lower() or "excluded" in str(
        bov["inclusion_reason"]
    ).lower()
    assert bov["equine_relevance"] == "none"
    assert bov["extraction_status"] == "excluded"


def test_equidae_synonym_source_has_equine_scope_on_propositions(tmp_path: Path) -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law_fixtures.json"
    case_data, _c, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
        derived_cache_dir=str(tmp_path / "derived-cache-equidae"),
    )
    props = bundle.get("propositions") or []
    syn_props = [p for p in props if p.get("source_record_id") == "fixture-equidae-synonym"]
    assert syn_props, "expected heuristic extraction for equidae fixture"
    rows = build_proposition_coverage_rows(bundle)
    syn_rows = [r for r in rows if r["source_id"] == "fixture-equidae-synonym"]
    assert syn_rows
    linked = any(
        any(sl.get("scope_id") == "equine" for sl in (r.get("scope_links") or []))
        for r in syn_rows
    )
    assert linked, "equidae text should link to equine scope via taxonomy"


def test_contextual_source_marked_contextual_in_coverage() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law_fixtures.json"
    case_data, _c, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    rows = build_source_coverage_rows(bundle)
    ctx = next(r for r in rows if r["source_id"] == "fixture-contextual-movement")
    assert ctx["equine_relevance"] == "contextual"
    assert ctx["relationship_to_target"] == "contextual"


def test_guidance_ready_false_when_low_confidence_or_proposed() -> None:
    bundle = {
        "propositions": [
            {
                "id": "p1",
                "proposition_key": "k1",
                "source_record_id": "s1",
                "fragment_locator": "article:1",
                "review_status": "proposed",
            }
        ],
        "proposition_extraction_traces": [
            {
                "proposition_id": "p1",
                "confidence": "medium",
            }
        ],
        "proposition_completeness_assessments": [
            {"proposition_id": "p1", "status": "complete"}
        ],
        "proposition_scope_links": [],
        "source_family_candidates": [],
        "proposition_extraction_failures": [],
        "sources": [{"id": "s1", "title": "t", "citation": "c"}],
        "source_records": [{"id": "s1", "title": "t", "citation": "c"}],
    }
    rows = build_proposition_coverage_rows(bundle)
    assert len(rows) == 1
    assert rows[0]["guidance_ready"] is False
    assert "confidence" in rows[0]["reason_if_not_guidance_ready"].lower()


def test_coverage_summary_separates_fixtures_and_legal_counts() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law_fixtures.json"
    case_data, _c, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    src_rows = build_source_coverage_rows(bundle)
    prop_rows = build_proposition_coverage_rows(bundle)
    cand_n = len(bundle.get("source_family_candidates") or [])
    summary = build_coverage_summary(
        source_rows=src_rows,
        proposition_rows=prop_rows,
        source_family_candidate_count=cand_n,
    )
    assert summary["developer_validation_fixtures"] == 4
    assert summary["included_legal_sources"] == 0
    pending_rows = sum(
        1
        for r in src_rows
        if "Discovery candidate only" in str(r.get("inclusion_reason") or "")
    )
    assert summary["pending_legal_candidates"] == pending_rows
    assert summary["pending_legal_candidates"] >= 8


def test_sfc_base_discovery_row_has_title_and_celex() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law_fixtures.json"
    case_data, _c, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    src_rows = build_source_coverage_rows(bundle)
    base = next(r for r in src_rows if r["source_id"] == "sfc-2016-429-base")
    assert "2016/429" in str(base.get("title") or "")
    assert base.get("celex") == "32016R0429"


def test_run_equine_corpus_export_writes_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "export"
    bundle, summary = run_equine_corpus_export(
        corpus_config_path=REPO_ROOT / "examples" / "corpus_equine_law_fixtures.json",
        output_dir=str(out),
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    assert (out / "equine_source_coverage.json").is_file()
    assert (out / "equine_proposition_coverage.json").is_file()
    assert (out / "equine_corpus_readiness.json").is_file()
    assert (out / "equine_source_coverage.csv").is_file()
    assert summary["coverage_status"] == "pending_review"
    assert summary["included_legal_sources"] == summary["sources_included_rows"]
    assert "guidance_ready_propositions" in summary
    assert "lint_warnings_by_quality_gate" in summary
    assert "extraction_trace_fallback_method_count" in summary
    assert bundle.get("run")


def test_prepare_equine_law_legal_case_curated_sources() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law.json"
    case_data, corpus_cfg, _p = prepare_case_data_for_equine_corpus(cfg_path)
    assert corpus_cfg["corpus_id"] == "equine_law"
    assert corpus_cfg["source_family_focus_celex"][:2] == ["32016R0429", "32015R0262"]
    assert case_data["extraction"]["focus_scopes"] == ["equine", "equidae", "equid", "horse"]
    assert case_data["extraction"]["max_propositions_per_source"] == 12
    assert len(case_data["sources"]) == 6
    assert all(not str(s["id"]).startswith("fixture-") for s in case_data["sources"])


def test_corpus_config_extraction_selection_fields_propagate_to_runner_inputs() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_passport_eu_2015_262_v0_1.json"
    case_data, _corpus_cfg, _p = prepare_case_data_for_equine_corpus(cfg_path)
    extraction_cfg = case_data.get("extraction") or {}
    assert extraction_cfg.get("include_annexes") is True
    assert extraction_cfg.get("fragment_selection_mode") == "required_only"
    assert "passport" in (extraction_cfg.get("focus_terms") or [])
    assert "article:4" in (extraction_cfg.get("required_fragment_locators") or [])
    assert "annex:i" in (extraction_cfg.get("required_fragment_locators") or [])

    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    pipeline_inputs = bundle.get("pipeline_case_inputs") or {}
    extraction_inputs = pipeline_inputs.get("extraction") or {}
    assert extraction_inputs.get("include_annexes") is True
    assert extraction_inputs.get("fragment_selection_mode") == "required_only"
    assert "passport" in (extraction_inputs.get("focus_terms") or [])
    assert "article:4" in (extraction_inputs.get("required_fragment_locators") or [])
    assert "annex:i" in (extraction_inputs.get("required_fragment_locators") or [])


def test_prepare_equine_corpus_merges_nested_extraction_over_top_level(tmp_path: Path) -> None:
    corpus_cfg = {
        "corpus_id": "equine_law",
        "focus_scopes": ["horse"],
        "focus_terms": ["passport"],
        "include_annexes": True,
        "required_fragment_locators": ["article:4"],
        "max_propositions_per_source": 8,
        "extraction_mode": "frontier",
        "extraction_fallback": "mark_needs_review",
        "model_error_policy": "continue_with_fallback",
        "source_case_path": str(REPO_ROOT / "examples" / "equine_passport_eu_2015_262_case.json"),
        "extraction": {
            "focus_terms": ["database", "transponder"],
            "include_annexes": False,
            "required_fragment_locators": ["annex:i"],
            "max_propositions_per_source": 3,
            "model_error_policy": "stop_repairable",
            "extraction_mode": "local",
            "extraction_fallback": "fallback",
        },
    }
    cfg_path = tmp_path / "nested-corpus-config.json"
    cfg_path.write_text(json.dumps(corpus_cfg), encoding="utf-8")

    case_data, _corpus_cfg, _p = prepare_case_data_for_equine_corpus(cfg_path)
    extraction_cfg = case_data.get("extraction") or {}
    assert extraction_cfg.get("focus_scopes") == ["horse"]
    assert extraction_cfg.get("focus_terms") == ["database", "transponder"]
    assert extraction_cfg.get("include_annexes") is False
    assert extraction_cfg.get("required_fragment_locators") == ["annex:i"]
    assert extraction_cfg.get("max_propositions_per_source") == 3
    assert extraction_cfg.get("model_error_policy") == "stop_repairable"
    assert extraction_cfg.get("mode") == "local"
    assert extraction_cfg.get("fallback_policy") == "fallback"


def test_run_equine_corpus_export_cli_overrides_focus_scope_and_limit(tmp_path: Path) -> None:
    out = tmp_path / "export"
    bundle, _summary = run_equine_corpus_export(
        corpus_config_path=REPO_ROOT / "examples" / "corpus_equine_passport_eu_2015_262_v0_1.json",
        output_dir=str(out),
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
        focus_scopes=["override-horse"],
        max_propositions_per_source=2,
    )
    extraction_inputs = (bundle.get("pipeline_case_inputs") or {}).get("extraction") or {}
    assert extraction_inputs.get("focus_scopes") == ["override-horse"]
    assert extraction_inputs.get("max_propositions_per_source") == 2


def test_stage_trace_includes_effective_extraction_selection_inputs() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_passport_eu_2015_262_v0_1.json"
    case_data, _corpus_cfg, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    traces = bundle.get("stage_traces") or []
    ext_trace = next(t for t in traces if t.get("stage_name") == "proposition extraction")
    inputs = ext_trace.get("inputs") or {}
    assert "article:4" in (inputs.get("effective_required_fragment_locators") or [])
    assert "passport" in (inputs.get("effective_focus_terms") or [])
    assert inputs.get("effective_include_annexes") is True
    assert inputs.get("effective_fragment_selection_mode") == "required_only"
    assert inputs.get("effective_focus_scopes") == ["equine", "equidae", "equid", "horse", "passport", "identification"]
    assert inputs.get("effective_model_error_policy") == "continue_repairable"
    assert inputs.get("effective_max_propositions_per_source") == 8
    assert isinstance(inputs.get("available_fragment_locators_count"), int)
    assert isinstance(inputs.get("available_fragment_locators_sample"), list)


def test_passport_required_only_emits_all_jobs_and_skips_non_required_with_clear_reason() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_passport_eu_2015_262_v0_1.json"
    case_data, _corpus_cfg, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    jobs = bundle.get("proposition_extraction_jobs") or []
    assert len(bundle.get("source_fragments") or []) == 48
    assert len(jobs) == 48
    selected = [j for j in jobs if j.get("selected_for_extraction") is True]
    skipped = [j for j in jobs if j.get("selected_for_extraction") is False]
    assert selected
    assert all(str(j.get("selection_reason") or "") == "required_locator" for j in selected)
    assert all(
        str(j.get("skip_reason") or "") == "skipped_not_required_in_required_only_mode" for j in skipped
    )
    trace = next(t for t in (bundle.get("stage_traces") or []) if t.get("stage_name") == "proposition extraction")
    outputs = trace.get("outputs") or {}
    assert outputs.get("selected_by_focus_term") == 0


def test_api_equine_corpus_coverage_endpoint(tmp_path: Path) -> None:
    prev = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        stub = {
            "corpus_id": "equine_law",
            "coverage_status": "pending_review",
            "generated_at": "2026-01-01T00:00:00Z",
            "disclaimer": "test",
            "summary": {},
            "sources": [],
        }
        (tmp_path / "equine_source_coverage.json").write_text(
            json.dumps(stub), encoding="utf-8"
        )
        (tmp_path / "equine_proposition_coverage.json").write_text(
            json.dumps({**stub, "propositions": []}), encoding="utf-8"
        )
        client = TestClient(app)
        res = client.get("/ops/corpus-coverage/equine")
        assert res.status_code == 200
        payload = res.json()
        assert "source_coverage" in payload
    finally:
        settings.operations_export_dir = prev


def test_prepare_equine_law_merge_adds_passport_family_candidates_without_new_sources() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law.json"
    case_data, _c, _p = prepare_case_data_for_equine_corpus(cfg_path)
    assert len(case_data["sources"]) == 6
    cands = case_data.get("source_family_candidates") or []
    ids = {str(c["id"]) for c in cands if isinstance(c, dict) and c.get("id")}
    assert "sfc-2015-262-eu-implementing" in ids
    assert "sfc-2015-262-corr-02" in ids
    assert {"sfc-2015-262-annex-I", "sfc-2015-262-annex-II"}.issubset(ids)
    d2035 = next(c for c in cands if isinstance(c, dict) and c["id"] == "sfc-2019-2035-delegated")
    i963 = next(c for c in cands if isinstance(c, dict) and c["id"] == "sfc-2021-963-implementing")
    assert d2035.get("inclusion_status") == "required_for_scope"
    assert i963.get("inclusion_status") == "required_for_scope"


def test_equine_law_bundle_included_counts_ignore_discovery_rows() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law.json"
    case_data, _c, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    merged_n = len(bundle.get("source_family_candidates") or [])
    assert merged_n > 18
    records = bundle.get("sources") or bundle.get("source_records") or []
    assert len(records) == 6
    rows = build_source_coverage_rows(bundle)
    summary = build_coverage_summary(
        source_rows=rows,
        proposition_rows=build_proposition_coverage_rows(bundle),
        source_family_candidate_count=merged_n,
        bundle=bundle,
    )
    assert summary["pending_legal_candidates"] >= merged_n // 2
    assert summary["included_legal_sources"] == 6


def test_source_coverage_passport_candidates_carry_lineage_columns() -> None:
    cfg_path = REPO_ROOT / "examples" / "corpus_equine_law.json"
    case_data, _c, _p = prepare_case_data_for_equine_corpus(cfg_path)
    bundle = build_bundle_from_case(
        case_data,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    rows = build_source_coverage_rows(bundle)
    row262 = next(r for r in rows if r["source_id"] == "sfc-2015-262-eu-implementing")
    assert row262["equine_law_group"] == "equine_passport_identification"
    assert row262["equine_instrument_lineage"] == "retained_historical_baseline"
    assert row262["included_in_corpus"] is False
    corr_row = next(r for r in rows if r["source_id"] == "sfc-2015-262-corr-02")
    assert "32015R0262R(02)" in str(corr_row.get("celex") or "")
    assert corr_row["equine_portfolio_status"] == "related_fragment:corrigendum_only"

