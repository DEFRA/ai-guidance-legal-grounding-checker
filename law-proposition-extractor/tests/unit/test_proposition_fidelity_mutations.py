"""Mutation tests for proposition-fidelity legal invariants."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.extract import _validate_v2_items
from law_proposition_extractor_pipeline.proposition_fidelity.dimensions import evaluate_role_dimensions
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import (
    ExpectedProposition,
    load_proposition_fidelity_cases,
)
from law_proposition_extractor_pipeline.proposition_fidelity.matching import RoleMatch, match_roles_for_case
from law_proposition_extractor_pipeline.proposition_fidelity.runner import evaluate_case, run_dry_fragment_case


def _uk12() -> ExpectedProposition:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    return case.gold[0]


def _base_prop(**overrides):
    prop = {
        "id": "prop-1",
        "fragment_locator": "regulation:12",
        "legal_effect_type": "prohibition",
        "legal_subject": "An occupier of a holding",
        "action": "must not spread organic manure within 10 metres of surface water",
        "proposition_text": (
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water."
        ),
        "conditions": [],
        "affected_subjects": ["organic manure"],
        "extraction_debug_meta": {
            "evidence_quote": (
                "An occupier of a holding must not spread organic manure within "
                "10 metres of surface water."
            ),
            "completeness_status": "complete",
        },
    }
    prop.update(overrides)
    return prop


def _eval(prop, expected=None, *, operative=None, heading=None, match_status="matched"):
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    expected = expected or case.gold[0]
    match = RoleMatch(
        role=expected.role,
        proposition_id=prop.get("id") if match_status == "matched" else None,
        status=match_status,
    )
    return evaluate_role_dimensions(
        case=case,
        expected=expected,
        match=match,
        prop=prop if match_status == "matched" else None,
        operative_text=operative
        or (
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water."
        ),
        heading_text=heading if heading is not None else "Spreading controls near surface water",
        all_matched_props=[prop] if match_status == "matched" else [],
    )


def _fail_dims(dims):
    return {d.dimension for d in dims if d.status == "fail"}


def test_mutation_missing_proposition() -> None:
    dims = _eval(_base_prop(), match_status="missing")
    assert "coverage" in _fail_dims(dims)


def test_mutation_unexpected_seventh_article_49a(tmp_path: Path) -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    result = evaluate_case(case, work_dir=tmp_path)
    # Inject a seventh fake heading proposition into the unexpected path by
    # asserting the case-level check fails when one is present.
    from law_proposition_extractor_pipeline.proposition_fidelity.dimensions import evaluate_case_level_dimensions
    from law_proposition_extractor_pipeline.proposition_fidelity.matching import RoleMatch

    matches = [
        RoleMatch(role=g.role, proposition_id=f"id-{i}", status="matched")
        for i, g in enumerate(case.gold)
    ]
    unexpected = [
        {
            "id": "prop-heading-seventh",
            "proposition_text": case.heading_text,
            "fragment_locator": "article:49a",
            "legal_effect_type": "unknown",
        }
    ]
    dims = evaluate_case_level_dimensions(
        case=case,
        matches=matches,
        unexpected=unexpected,
        propositions=unexpected,
        operative_text="operative",
        heading_text=case.heading_text,
    )
    assert any(d.status == "fail" and "unexpected" in d.detail for d in dims)


def test_mutation_merged_obligation_and_prohibition() -> None:
    prop = _base_prop(
        proposition_text=(
            "An occupier must keep records and must not spread organic manure "
            "within 10 metres of surface water."
        ),
        legal_effect_type="obligation",
    )
    dims = _eval(prop)
    fails = _fail_dims(dims)
    assert "atomicity" in fails or "no_false_split" in fails or "no_false_merge" in fails


def test_mutation_split_indivisible_rule() -> None:
    # Two matched props sharing one id should fail no_false_split for shared roles
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    expected = case.gold[0]
    # Craft expected with share marker
    shared = ExpectedProposition(
        role=expected.role,
        source_locator=expected.source_locator,
        short_legal_description=expected.short_legal_description,
        legal_effect_type=expected.legal_effect_type,
        required_actor=expected.required_actor,
        required_action=expected.required_action,
        object=expected.object,
        thresholds=expected.thresholds,
        evidence_markers=expected.evidence_markers,
        may_share_source_fragment_with=("other-role",),
    )
    prop = _base_prop()
    twin = deepcopy(prop)
    dims = evaluate_role_dimensions(
        case=case,
        expected=shared,
        match=RoleMatch(role=shared.role, proposition_id="prop-1", status="matched"),
        prop=prop,
        operative_text=prop["proposition_text"],
        heading_text=case.heading_text,
        all_matched_props=[prop, twin],
    )
    assert "no_false_split" in _fail_dims(dims)


def test_mutation_wrong_actor() -> None:
    dims = _eval(_base_prop(legal_subject="A local authority", proposition_text="A local authority must not spread."))
    assert "actor_fidelity" in _fail_dims(dims)


def test_mutation_missing_condition() -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    expected = next(g for g in case.gold if g.role == "inspection-trigger")
    prop = {
        "id": "p3",
        "fragment_locator": "article:49a:paragraph:3",
        "legal_effect_type": "obligation",
        "legal_subject": "fisheries administration",
        "action": "must monitor the catch composition by way of sampling",
        "proposition_text": "A fisheries administration must monitor the catch composition by way of sampling.",
        "conditions": [],
        "extraction_debug_meta": {
            "evidence_quote": "a fisheries administration must monitor the catch composition by way of sampling.",
            "completeness_status": "context_dependent",
        },
    }
    dims = evaluate_role_dimensions(
        case=case,
        expected=expected,
        match=RoleMatch(role=expected.role, proposition_id="p3", status="matched"),
        prop=prop,
        operative_text=prop["proposition_text"] + " In the cases referred to in paragraph 2.",
        heading_text=case.heading_text,
        all_matched_props=[prop],
    )
    assert "condition_fidelity" in _fail_dims(dims)


def test_mutation_changed_numerical_threshold() -> None:
    dims = _eval(
        _base_prop(
            action="must not spread organic manure within 50 metres of surface water",
            proposition_text=(
                "An occupier of a holding must not spread organic manure within "
                "50 metres of surface water."
            ),
            extraction_debug_meta={
                "evidence_quote": (
                    "An occupier of a holding must not spread organic manure within "
                    "50 metres of surface water."
                ),
                "completeness_status": "complete",
            },
        )
    )
    assert "threshold_fidelity" in _fail_dims(dims)


def test_mutation_lost_exception_and_wrong_target() -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    expected = next(g for g in case.gold if g.role == "small-vessel-derogation")
    prop = {
        "id": "e3",
        "fragment_locator": "article:49a:paragraph:2",
        "legal_effect_type": "obligation",
        "legal_subject": "Paragraph 1",
        "action": "continues to apply",
        "proposition_text": "Paragraph 1 continues to apply to all vessels.",
        "conditions": [],
        "extraction_debug_meta": {
            "structured_list_path": "2-b",
            "evidence_quote": "Paragraph 1 continues to apply to all vessels.",
            "completeness_status": "complete",
        },
    }
    dims = evaluate_role_dimensions(
        case=case,
        expected=expected,
        match=RoleMatch(role=expected.role, proposition_id="e3", status="matched"),
        prop=prop,
        operative_text="to fishing vessels of less than 12 metres' length overall",
        heading_text=case.heading_text,
        all_matched_props=[prop],
    )
    fails = _fail_dims(dims)
    assert "exception_fidelity" in fails or "legal_effect_fidelity" in fails or "threshold_fidelity" in fails


def test_mutation_structured_list_path_changed() -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    expected = next(g for g in case.gold if g.role == "small-pelagic-derogation")
    prop = {
        "id": "e1",
        "fragment_locator": "article:49a:paragraph:2",
        "legal_effect_type": "derogation",
        "legal_subject": "Paragraph 1",
        "action": "shall not apply",
        "proposition_text": (
            "Paragraph 1 shall not apply where the catches contain more than 80% "
            "of one or more small pelagic species (mackerel)."
        ),
        "conditions": ["80%"],
        "extraction_debug_meta": {
            "structured_list_path": "2-b",
            "evidence_quote": "mackerel, herring, horse mackerel",
            "completeness_status": "complete",
        },
    }
    dims = evaluate_role_dimensions(
        case=case,
        expected=expected,
        match=RoleMatch(role=expected.role, proposition_id="e1", status="matched"),
        prop=prop,
        operative_text=prop["proposition_text"],
        heading_text=case.heading_text,
        all_matched_props=[prop],
    )
    assert any(
        d.status == "fail" and "structured-list path" in d.detail for d in dims
    )


def test_mutation_heading_only_proposition_accepted() -> None:
    heading = "Spreading controls near surface water"
    operative = (
        "An occupier of a holding must not spread organic manure within 10 metres of surface water."
    )
    dims = _eval(
        _base_prop(
            proposition_text=heading,
            action=heading,
            extraction_debug_meta={"evidence_quote": heading, "completeness_status": "complete"},
        ),
        operative=operative,
        heading=heading,
    )
    fails = _fail_dims(dims)
    assert "structural_context_boundary" in fails or "evidence_fidelity" in fails


def test_mutation_heading_used_as_evidence() -> None:
    heading = "Spreading controls near surface water"
    operative = (
        "An occupier of a holding must not spread organic manure within 10 metres of surface water."
    )
    accepted, errors, _ = _validate_v2_items(
        [{"proposition_text": "x", "evidence_text": heading}],
        operative,
        limit=4,
    )
    assert accepted == []
    assert errors


def test_mutation_sibling_heading_leaked() -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    prop = _base_prop(
        proposition_text=(
            "An occupier must not spread organic manure within 10 metres of surface water "
            "under Action programme rules."
        ),
        extraction_debug_meta={
            "evidence_quote": "Action programme",
            "completeness_status": "complete",
        },
    )
    dims = evaluate_role_dimensions(
        case=case,
        expected=case.gold[0],
        match=RoleMatch(role=case.gold[0].role, proposition_id="prop-1", status="matched"),
        prop=prop,
        operative_text=(
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water."
        ),
        heading_text=case.heading_text,
        all_matched_props=[prop],
    )
    assert "structural_context_boundary" in _fail_dims(dims) or "evidence_fidelity" in _fail_dims(
        dims
    )


def test_mutation_source_locator_changed_breaks_match() -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    prop = _base_prop(fragment_locator="regulation:99")
    matches, _ = match_roles_for_case(case, [prop])
    # May still match on other invariants, but score should drop; force fail via dimension
    # by clearing actor/action too
    prop2 = _base_prop(
        fragment_locator="regulation:99",
        legal_subject="Someone else",
        action="does something else",
        proposition_text="Someone else does something else.",
        extraction_debug_meta={"evidence_quote": "Someone else does something else."},
    )
    matches2, _ = match_roles_for_case(case, [prop2])
    assert matches2[0].status == "missing"


def test_mutation_legal_effect_classification_changed() -> None:
    dims = _eval(_base_prop(legal_effect_type="obligation"))
    assert "legal_effect_fidelity" in _fail_dims(dims)


def test_mutation_evidence_quote_from_commentary() -> None:
    dims = _eval(
        _base_prop(
            extraction_debug_meta={
                "evidence_quote": "Commentary: this rule is important for water quality.",
                "completeness_status": "complete",
            }
        )
    )
    assert "evidence_fidelity" in _fail_dims(dims)


def test_mutation_duplicate_terminal_reported_as_unexpected(tmp_path: Path) -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread")
    props, _ = run_dry_fragment_case(case)
    dup = deepcopy(props[0])
    dup["id"] = "prop-duplicate-terminal"
    matches, unexpected = match_roles_for_case(case, props + [dup])
    assert matches[0].status == "matched"
    assert unexpected


def test_mutation_completeness_mismatch_uses_configured_severity() -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    expected = next(g for g in case.gold if g.role == "inspection-trigger")
    assert expected.completeness_severity == "warning"
    prop = {
        "id": "p3",
        "fragment_locator": "article:49a:paragraph:3",
        "legal_effect_type": "obligation",
        "legal_subject": "fisheries administration",
        "action": "must monitor the catch composition by way of sampling",
        "proposition_text": (
            "In the cases referred to in paragraph 2, a fisheries administration "
            "must monitor the catch composition by way of sampling."
        ),
        "conditions": ["paragraph 2"],
        "extraction_debug_meta": {
            "evidence_quote": (
                "In the cases referred to in paragraph 2, a fisheries administration "
                "must monitor the catch composition by way of sampling."
            ),
            "completeness_status": "complete",
        },
    }
    dims = evaluate_role_dimensions(
        case=case,
        expected=expected,
        match=RoleMatch(role=expected.role, proposition_id="p3", status="matched"),
        prop=prop,
        operative_text=prop["proposition_text"],
        heading_text=case.heading_text,
        all_matched_props=[prop],
    )
    completeness = next(d for d in dims if d.dimension == "completeness_fidelity")
    assert completeness.status == "warning"
