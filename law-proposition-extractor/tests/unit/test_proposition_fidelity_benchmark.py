"""Offline multi-instrument proposition-fidelity benchmark (Law Proposition Extractor-only)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from law_proposition_extractor_domain import Cluster, SourceRecord, Topic
from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    identify_article_49a_propositions,
    run_article_49a_acceptance_pipeline,
)
from law_proposition_extractor_pipeline.extract import (
    EXTRACTION_PROMPT_VERSION,
    _v2_model_prompt,
    _validate_v2_items,
)
from law_proposition_extractor_pipeline.proposition_fidelity.dimensions import heading_only_candidate_rejected
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import (
    REPORT_RELATIVE,
    load_proposition_fidelity_cases,
    validate_manifest_inventory,
)
from law_proposition_extractor_pipeline.proposition_fidelity.matching import match_roles_for_case
from law_proposition_extractor_pipeline.proposition_fidelity.report import (
    check_benchmark_report,
    render_benchmark_report,
    write_benchmark_report,
)
from law_proposition_extractor_pipeline.proposition_fidelity.results import PropositionFidelityBenchmarkResult
from law_proposition_extractor_pipeline.proposition_fidelity.runner import (
    evaluate_case,
    run_dry_fragment_case,
    run_proposition_fidelity_benchmark,
)
from law_proposition_extractor_pipeline.source_structure_audit import structural_rows_to_fragments
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root
from law_proposition_extractor_pipeline.source_structure_inspector import assert_no_path_leaks
from law_proposition_extractor_pipeline.sources.adapters import _build_legislation_structural_fragments
from law_proposition_extractor_pipeline.structural_headings import resolve_structural_heading_contexts
from xml.etree import ElementTree


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------


def test_manifest_loads_and_validates() -> None:
    errors = validate_manifest_inventory()
    assert errors == [], errors
    cases = load_proposition_fidelity_cases()
    assert 5 <= len(cases) <= 8
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))
    assert "article_49a" in ids
    assert "uk_regulation_12_spread" in ids
    assert "wsi_regulation_36_4" in ids


def test_every_source_and_response_fixture_exists() -> None:
    for case in load_proposition_fidelity_cases():
        assert case.source_path.is_file(), case.source_fixture_relative
        roles = [g.role for g in case.gold]
        assert len(roles) == len(set(roles)), case.case_id
        if case.runner == "dry_fragment":
            assert case.response_path is not None and case.response_path.is_file()


def test_result_and_report_serialization_deterministic(tmp_path: Path) -> None:
    # Dry-only subset for speed: full suite covered by check command / baseline run.
    cases = [c for c in load_proposition_fidelity_cases() if c.runner == "dry_fragment"]
    results_a = [evaluate_case(c, work_dir=tmp_path / "a" / c.case_id).to_dict() for c in cases]
    results_b = [evaluate_case(c, work_dir=tmp_path / "b" / c.case_id).to_dict() for c in cases]
    assert json.dumps(results_a, sort_keys=True) == json.dumps(results_b, sort_keys=True)
    text = json.dumps(results_a, sort_keys=True)
    assert_no_path_leaks(text, label="pf-results")


def test_full_benchmark_deterministic_and_offline(tmp_path: Path) -> None:
    a = run_proposition_fidelity_benchmark(work_dir=tmp_path / "run-a")
    b = run_proposition_fidelity_benchmark(work_dir=tmp_path / "run-b")

    def _stable(payload: dict) -> dict:
        out = dict(payload)
        out.pop("runtime_seconds", None)
        return out

    assert json.dumps(_stable(a.to_dict()), sort_keys=True) == json.dumps(
        _stable(b.to_dict()), sort_keys=True
    )
    assert_no_path_leaks(json.dumps(_stable(a.to_dict()), sort_keys=True), label="pf-bench")
    report = render_benchmark_report(a)
    assert report == render_benchmark_report(b)
    assert_no_path_leaks(report, label="pf-report")
    assert "BEGIN GENERATED: proposition-fidelity-benchmark" in report


def test_check_mode_leaves_working_tree_unchanged() -> None:
    root = judit_root()
    before = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    )
    # check_benchmark_report runs the suite and compares; must not write.
    try:
        check_benchmark_report(root=root)
    except AssertionError as exc:
        # Report may not exist yet during first authoring — skip tree check only if missing
        if "Missing proposition-fidelity report" in str(exc):
            pytest.skip("report not yet committed")
        raise
    after = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=root, text=True
    )
    assert before == after


def test_no_absolute_paths_in_report_body(tmp_path: Path) -> None:
    result = run_proposition_fidelity_benchmark(work_dir=tmp_path)
    body = render_benchmark_report(result)
    assert_no_path_leaks(body, label="pf-report-body")


# ---------------------------------------------------------------------------
# Role matching
# ---------------------------------------------------------------------------


def test_article_49a_six_roles_resolve(tmp_path: Path) -> None:
    result = run_article_49a_acceptance_pipeline(work_dir=tmp_path, export=True)
    roles = identify_article_49a_propositions(result.bundle)
    assert set(roles) == {"P1", "P2", "E1", "E2", "E3", "P3"}
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    props = [
        p
        for p in result.bundle["propositions"]
        if str(p.get("fragment_locator") or "").startswith("article:49a")
    ]
    matches, unexpected = match_roles_for_case(
        case, props, article_49a_bundle=result.bundle
    )
    assert all(m.status == "matched" for m in matches)
    assert unexpected == []
    assert {m.role for m in matches} == {g.role for g in case.gold}


def test_ambiguous_role_match_reported_not_silently_selected() -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    twin = {
        "id": "prop-a",
        "fragment_locator": "regulation:12",
        "legal_effect_type": "prohibition",
        "legal_subject": "An occupier of a holding",
        "action": "must not spread organic manure within 10 metres of surface water",
        "proposition_text": "An occupier of a holding must not spread organic manure within 10 metres of surface water.",
        "conditions": [],
        "extraction_debug_meta": {
            "evidence_quote": "An occupier of a holding must not spread organic manure within 10 metres of surface water."
        },
    }
    twin_b = dict(twin)
    twin_b["id"] = "prop-b"
    twin_b["proposition_text"] = (
        "An occupier of a holding must not spread organic manure within "
        "10 metres of any ditch or surface water."
    )
    matches, _ = match_roles_for_case(case, [twin, twin_b])
    assert matches[0].status == "ambiguous"
    assert set(matches[0].competing_candidate_ids) == {"prop-a", "prop-b"}


def test_missing_and_unexpected_roles_reported(tmp_path: Path) -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_13_control")
    matches, unexpected = match_roles_for_case(case, [])
    assert matches[0].status == "missing"
    props, _ = run_dry_fragment_case(case)
    extra = {
        "id": "prop-extra-unexpected",
        "fragment_locator": "regulation:99",
        "legal_effect_type": "obligation",
        "legal_subject": "A greenhouse operator",
        "action": "must paint the roof green",
        "proposition_text": "Invented sibling rule about greenhouses.",
        "conditions": [],
        "extraction_debug_meta": {"evidence_quote": "Invented sibling rule about greenhouses."},
    }
    matches2, unexpected2 = match_roles_for_case(case, props + [extra])
    assert matches2[0].status == "matched"
    assert any(p["id"] == "prop-extra-unexpected" for p in unexpected2)


def test_opaque_id_change_does_not_break_semantic_matching(tmp_path: Path) -> None:
    result = run_article_49a_acceptance_pipeline(work_dir=tmp_path, export=True)
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    props = [
        dict(p)
        for p in result.bundle["propositions"]
        if str(p.get("fragment_locator") or "").startswith("article:49a")
    ]
    for idx, prop in enumerate(props):
        prop["id"] = f"mutated-opaque-{idx}"
    bundle = dict(result.bundle)
    bundle["propositions"] = props + [
        p
        for p in result.bundle["propositions"]
        if not str(p.get("fragment_locator") or "").startswith("article:49a")
    ]
    matches, unexpected = match_roles_for_case(case, props, article_49a_bundle=bundle)
    assert all(m.status == "matched" for m in matches)
    assert unexpected == []


# ---------------------------------------------------------------------------
# Fidelity dimensions / structural context
# ---------------------------------------------------------------------------


def test_actor_action_threshold_and_effect_dims_on_uk_headed(tmp_path: Path) -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    result = evaluate_case(case, work_dir=tmp_path)
    role = result.role_results[0]
    by_dim = {d.dimension: d for d in role.dimension_results}
    assert by_dim["actor_fidelity"].status == "pass"
    assert by_dim["action_fidelity"].status == "pass"
    assert by_dim["threshold_fidelity"].status == "pass"
    assert by_dim["legal_effect_fidelity"].status == "pass"
    assert by_dim["evidence_fidelity"].status == "pass"


def test_heading_only_proposition_and_evidence_fail() -> None:
    heading = "Spreading controls near surface water"
    operative = (
        "An occupier of a holding must not spread organic manure within 10 metres of surface water."
    )
    assert heading_only_candidate_rejected(heading, operative) is True
    accepted, errors, issues = _validate_v2_items(
        [
            {
                "proposition_text": heading,
                "evidence_text": heading,
                "reason": "heading-only",
            }
        ],
        operative,
        limit=4,
    )
    assert accepted == []
    assert errors or issues


def test_prompt_v3_heading_block_for_uk_headed_case() -> None:
    assert EXTRACTION_PROMPT_VERSION == "v3"
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    assert case.response is not None and case.response.reflects_prompt_v3 is True
    root = ElementTree.fromstring(case.source_path.read_text(encoding="utf-8"))
    rows, _ = _build_legislation_structural_fragments(
        root=root, source_url="https://www.legislation.gov.uk/offline/fixture/data.xml"
    )
    fragments = structural_rows_to_fragments(rows)
    by_id = {f.id: f for f in fragments}
    frag = next(f for f in fragments if f.locator == case.source_locator)
    contexts = resolve_structural_heading_contexts(frag, by_id)
    assert contexts
    source = SourceRecord(
        id="src",
        title="t",
        jurisdiction="UK",
        citation="c",
        kind="regulation",
        authoritative_text=frag.fragment_text,
        metadata={
            "structural_heading_contexts": [
                {
                    "kind": c.kind.value if hasattr(c.kind, "value") else c.kind,
                    "number_label": c.number_label,
                    "heading_text": c.heading_text,
                    "owner_locator": c.owner_locator,
                }
                for c in contexts
            ]
        },
    )
    prompt = _v2_model_prompt(
        source,
        Topic(id="t", name="Topic"),
        Cluster(id="c", topic_id="t", name="Cluster"),
        extraction_mode="frontier",
    )
    assert "Structural legislative context" in prompt
    assert "Spreading controls near surface water" in prompt
    assert "Operative source text:" in prompt
    op_idx = prompt.index("Operative source text:")
    assert "Spreading controls near surface water" not in prompt[op_idx:]


def test_unheaded_provisions_remain_valid(tmp_path: Path) -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_13_control")
    assert case.heading_present is False
    result = evaluate_case(case, work_dir=tmp_path)
    assert result.produced_count == 1
    assert result.missing_roles == []
    assert result.case_status in {"pass", "warning"}
    # Unheaded cases still produce a valid dry extraction through production parsers.
    assert any("prompt_version_production=" in d for d in result.diagnostics) or any(
        "unheaded" in d.lower() for d in result.diagnostics
    )


def test_control_case_exactly_one_proposition(tmp_path: Path) -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_13_control")
    result = evaluate_case(case, work_dir=tmp_path)
    assert result.produced_count == 1
    assert not any(
        d.status == "fail" and d.dimension == "no_false_split" for d in result.dimension_results
    )


def test_compound_obligation_and_prohibition_remain_separate(tmp_path: Path) -> None:
    case = next(
        c for c in load_proposition_fidelity_cases() if c.case_id == "uk_compound_spread_and_measure"
    )
    result = evaluate_case(case, work_dir=tmp_path)
    assert set(result.matched_roles) == {
        "organic-manure-spread-prohibition",
        "distance-measurement-restatement",
    }
    effects = {
        r.role: next(
            (
                d.actual or ""
                for d in r.dimension_results
                if d.dimension == "legal_effect_fidelity"
            ),
            "",
        )
        for r in result.role_results
    }
    # Ensure we matched two distinct props
    ids = {r.proposition_id for r in result.role_results}
    assert len(ids) == 2


def test_wsi_recordkeeping_and_schedule_cases(tmp_path: Path) -> None:
    for case_id in ("wsi_regulation_36_4", "wsi_schedule_inspection_power"):
        case = next(c for c in load_proposition_fidelity_cases() if c.case_id == case_id)
        result = evaluate_case(case, work_dir=tmp_path / case_id)
        assert result.missing_roles == []
        assert result.produced_count >= 1


def test_article_49a_acceptance_remains_passing_via_benchmark(tmp_path: Path) -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    result = evaluate_case(case, work_dir=tmp_path)
    assert result.missing_roles == []
    assert result.unexpected_propositions == []
    assert len(result.matched_roles) == 6


def test_report_path_constant() -> None:
    assert REPORT_RELATIVE.as_posix() == "docs/explainability/proposition-fidelity-benchmark.md"
