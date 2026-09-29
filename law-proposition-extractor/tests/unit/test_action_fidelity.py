"""Structured action-fidelity evaluation (legal-action invariants)."""

from __future__ import annotations

from copy import deepcopy

import pytest

from law_proposition_extractor_pipeline.live_proposition_calibration.paths import run_dir
from law_proposition_extractor_pipeline.live_proposition_calibration.recheck_article_49a_action_fidelity import (
    recheck_article_49a_action_fidelity,
)
from law_proposition_extractor_pipeline.proposition_fidelity.action_fidelity import (
    ActionExpectation,
    evaluate_legacy_action_fidelity,
    evaluate_structured_action_fidelity,
    predicate_forms,
)
from law_proposition_extractor_pipeline.proposition_fidelity.dimensions import evaluate_role_dimensions
from law_proposition_extractor_pipeline.proposition_fidelity.fixtures import (
    ExpectedProposition,
    load_proposition_fidelity_cases,
)
from law_proposition_extractor_pipeline.proposition_fidelity.matching import RoleMatch
from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

_LIVE_RUN = "live-pf-20260715T155907Z"

_MIX_PROHIBITION = ActionExpectation(
    predicates=("mix",),
    polarity="negative",
    legal_effect="prohibition",
    voice="either",
    required_object_markers=("catches", "other catch"),
)


def _prop(
    text: str,
    *,
    effect: str = "prohibition",
    action: str | None = None,
    subject: str = "United Kingdom fishing vessel operator",
    evidence: str | None = None,
    label: str = "",
) -> dict:
    return {
        "id": "p2",
        "fragment_locator": "article:49a:paragraph:1",
        "legal_effect_type": effect,
        "legal_subject": subject,
        "action": action if action is not None else text,
        "proposition_text": text,
        "extraction_debug_meta": {
            "evidence_quote": evidence if evidence is not None else text,
            "display_label": label,
            "completeness_status": "complete",
        },
    }


def _eval_structured(
    prop: dict,
    *,
    expectation: ActionExpectation = _MIX_PROHIBITION,
    operative: str | None = None,
    heading: str | None = None,
):
    return evaluate_structured_action_fidelity(
        expectation=expectation,
        prop=prop,
        operative_text=operative or str(prop.get("proposition_text") or ""),
        heading_text=heading,
        evidence=str(
            (prop.get("extraction_debug_meta") or {}).get("evidence_quote") or ""
        ),
        label_text=str(
            (prop.get("extraction_debug_meta") or {}).get("display_label") or ""
        ),
    )


@pytest.mark.parametrize(
    "text",
    [
        "Those catches shall not be mixed with any other catches.",
        "Those catches must not be mixed with any other catches.",
        "An operator must not mix those catches with any other catches.",
        "An operator shall not mix those catches with any other catches.",
        "An operator is prohibited from mixing those catches with any other catches.",
    ],
)
def test_positive_mix_prohibition_surface_equivalence(text: str) -> None:
    result = _eval_structured(_prop(text))
    assert result.status == "pass", result.detail
    assert result.audit is not None
    assert result.audit["expected_predicates"] == ["mix"]
    assert result.audit["detected_predicates"] == ["mix"]
    assert result.audit["expected_polarity"] == "negative"
    assert result.audit["detected_polarity"] == "negative"
    assert result.audit["expected_legal_effect"] == "prohibition"
    assert result.audit["actual_legal_effect"] == "prohibition"
    assert "catches" in result.audit["matched_object_markers"]
    assert result.audit["accepted_surface_basis"], "equivalence basis must be auditable"


@pytest.mark.parametrize(
    "text,effect",
    [
        ("Those catches should not mix with any other catches.", "prohibition"),
        ("Those catches need not mix with any other catches.", "prohibition"),
        ("Those catches are not required to mix with any other catches.", "prohibition"),
        ("Those catches do not have to mix with any other catches.", "prohibition"),
        ("Those catches may not mix with any other catches.", "prohibition"),
        ("Those catches may mix with any other catches.", "permission"),
        ("Those catches must mix with any other catches.", "obligation"),
        ("Those catches must not store with any other catches.", "prohibition"),
        ("Those catches must not identify with any other catches.", "prohibition"),
        ("An operator must not mix.", "prohibition"),  # material object missing
    ],
)
def test_negative_mix_prohibition_not_equivalent(text: str, effect: str) -> None:
    result = _eval_structured(_prop(text, effect=effect))
    assert result.status == "fail", result.detail


def test_heading_only_action_evidence_rejected() -> None:
    heading = "Prohibition on mixing sub-MCRS catches"
    prop = _prop(
        "United Kingdom fishing vessels retain catches below MCRS on board.",
        action="retain catches",
        effect="prohibition",
        evidence="United Kingdom fishing vessels retain catches below MCRS on board.",
        label=heading,
    )
    # Inject mix only via heading/label path — action/text/evidence lack mix.
    result = evaluate_structured_action_fidelity(
        expectation=_MIX_PROHIBITION,
        prop=prop,
        operative_text="United Kingdom fishing vessels retain catches below MCRS on board.",
        heading_text=heading,
        evidence=str(prop["extraction_debug_meta"]["evidence_quote"]),
        label_text=heading,
    )
    assert result.status == "fail"
    assert "predicate" in result.detail.lower() or "grounded" in result.detail.lower()


def test_label_only_action_evidence_rejected() -> None:
    label = "must not mix catches with other catches"
    prop = _prop(
        "Catches retained on board remain identifiable.",
        action="remain identifiable",
        evidence="Catches retained on board remain identifiable.",
        label=label,
    )
    result = evaluate_structured_action_fidelity(
        expectation=_MIX_PROHIBITION,
        prop=prop,
        operative_text="Catches retained on board remain identifiable.",
        heading_text=None,
        evidence="Catches retained on board remain identifiable.",
        label_text=label,
    )
    assert result.status == "fail"


def test_passive_with_reversed_roles_fails_object_markers() -> None:
    # Other fishery products are the grammatical subject; catches become the mix-with
    # object — material "catches" patient role for the prohibition is lost.
    text = (
        "Any other fishery products shall not be mixed with those catches on board."
    )
    exp = ActionExpectation(
        predicates=("mix",),
        polarity="negative",
        legal_effect="prohibition",
        voice="either",
        required_object_markers=("catches",),
        required_actor_markers=("United Kingdom fishing vessel",),
    )
    prop = _prop(
        text,
        subject="Any other fishery products",
    )
    result = evaluate_structured_action_fidelity(
        expectation=exp,
        prop=prop,
        operative_text=text,
        heading_text=None,
        evidence=text,
    )
    assert result.status == "fail"
    assert "actor" in result.detail.lower()


def test_obligation_classification_rejects_prohibition_expectation() -> None:
    text = "Those catches shall not be mixed with any other catches."
    result = _eval_structured(_prop(text, effect="obligation"))
    assert result.status == "fail"
    assert "effect" in result.detail.lower()


def test_predicate_inflections_recognized() -> None:
    assert predicate_forms("mix") == frozenset({"mix", "mixes", "mixed", "mixing"})
    assert "spreading" in predicate_forms("spread")
    assert "measured" in predicate_forms("measure")
    assert "recorded" in predicate_forms("record")
    assert "retained" in predicate_forms("retain")
    assert "inspected" in predicate_forms("inspect")
    assert "identified" in predicate_forms("identify")
    assert "monitored" in predicate_forms("monitor")


def test_legacy_required_action_still_works() -> None:
    prop = {
        "action": "must not spread organic manure within 10 metres of surface water",
        "proposition_text": (
            "An occupier of a holding must not spread organic manure within "
            "10 metres of surface water."
        ),
        "legal_effect_type": "prohibition",
    }
    result = evaluate_legacy_action_fidelity(
        required_action="must not spread",
        prop=prop,
    )
    assert result.status == "pass"
    assert result.audit is not None
    assert result.audit["evaluation_mode"] == "legacy_required_action"


def test_article_49a_p2_gold_uses_structured_expectation() -> None:
    case = next(c for c in load_proposition_fidelity_cases() if c.case_id == "article_49a")
    p2 = next(g for g in case.gold if g.role == "prohibited-mixing-rule")
    assert p2.action_expectation is not None
    assert p2.action_expectation.predicates == ("mix",)
    assert p2.action_expectation.polarity == "negative"
    assert p2.action_expectation.legal_effect == "prohibition"
    assert p2.required_action is None


def test_unrelated_benchmark_predicates_remain_distinguishable() -> None:
    verbs = [
        "spread",
        "measure",
        "record",
        "retain",
        "inspect",
        "identify",
        "mix",
        "monitor",
    ]
    forms = {v: predicate_forms(v) for v in verbs}
    for a in verbs:
        for b in verbs:
            if a == b:
                continue
            # Canonical stems must not collapse into one shared form set.
            assert forms[a] != forms[b]
            assert a not in forms[b] or a == b


# --- mutations ---


def test_mutation_p2_predicate_mix_to_store() -> None:
    text = "Those catches must not store with any other catches."
    assert _eval_structured(_prop(text)).status == "fail"


def test_mutation_negative_polarity_removed() -> None:
    text = "Those catches must mix with any other catches."
    # Even if misclassified as prohibition, polarity fails.
    assert _eval_structured(_prop(text, effect="prohibition")).status == "fail"


def test_mutation_prohibition_changed_to_obligation() -> None:
    text = "Those catches shall not be mixed with any other catches."
    assert _eval_structured(_prop(text, effect="obligation")).status == "fail"


def test_mutation_object_catches_removed() -> None:
    text = "Products must not be mixed with any other fishery products."
    assert _eval_structured(_prop(text)).status == "fail"


def test_mutation_heading_used_as_action_evidence() -> None:
    test_heading_only_action_evidence_rejected()


def test_mutation_label_used_as_action_evidence() -> None:
    test_label_only_action_evidence_rejected()


def test_mutation_need_not_mix_accepted() -> None:
    text = "Those catches need not be mixed with any other catches."
    assert _eval_structured(_prop(text)).status == "fail"


def test_mutation_should_not_mix_accepted() -> None:
    text = "Those catches should not mix with any other catches."
    assert _eval_structured(_prop(text)).status == "fail"


def test_mutation_voice_normalization_reverses_actor_object() -> None:
    test_passive_with_reversed_roles_fails_object_markers()


def test_mutation_legacy_simple_action_contracts_stop_working() -> None:
    case = next(
        c for c in load_proposition_fidelity_cases() if c.case_id == "uk_regulation_12_spread"
    )
    expected = case.gold[0]
    assert expected.action_expectation is None
    assert expected.required_action == "must not spread"
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
        "extraction_debug_meta": {
            "evidence_quote": (
                "An occupier of a holding must not spread organic manure within "
                "10 metres of surface water."
            ),
            "completeness_status": "complete",
        },
    }
    dims = evaluate_role_dimensions(
        case=case,
        expected=expected,
        match=RoleMatch(role=expected.role, proposition_id="prop-1", status="matched"),
        prop=prop,
        operative_text=prop["proposition_text"],
        heading_text=case.heading_text,
        all_matched_props=[prop],
    )
    action = next(d for d in dims if d.dimension == "action_fidelity")
    assert action.status == "pass"
    assert action.audit and action.audit["evaluation_mode"] == "legacy_required_action"


def test_mutation_evaluator_omits_equivalence_basis() -> None:
    result = _eval_structured(
        _prop("Those catches shall not be mixed with any other catches.")
    )
    assert result.status == "pass"
    assert result.audit is not None
    assert result.audit.get("accepted_surface_basis")


def test_mutation_unrelated_benchmark_actions_collapse() -> None:
    test_unrelated_benchmark_predicates_remain_distinguishable()


def _live_run_available() -> bool:
    return (judit_root() / "calibration/proposition_fidelity" / _LIVE_RUN).is_dir()


@pytest.mark.skipif(not _live_run_available(), reason="live calibration artifacts absent")
def test_article_49a_saved_output_action_fidelity_recheck() -> None:
    payload = recheck_article_49a_action_fidelity(_LIVE_RUN, write_result=True)
    assert payload["model_calls_made"] == 0
    assert payload["historical_artifacts_modified"] is False
    out = run_dir(_LIVE_RUN) / "article_49a_action_fidelity_recheck.json"
    assert out.is_file()
    for row in payload["repetitions"]:
        hist = row["p2"]["historical_action_fidelity"]
        recheck = row["p2"]["recheck_action_fidelity"]
        assert hist is not None
        assert hist.get("status") == "fail"
        assert recheck["status"] == "pass"
        assert recheck["audit"]["detected_predicates"] == ["mix"]
        assert recheck["audit"]["detected_polarity"] == "negative"
        assert recheck["audit"]["actual_legal_effect"] == "prohibition"
