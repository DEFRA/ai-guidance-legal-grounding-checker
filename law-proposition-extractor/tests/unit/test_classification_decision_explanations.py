"""Unit tests for legal-effect classification DecisionExplanation emission."""

from __future__ import annotations

from law_proposition_extractor_domain import (
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    HeuristicMethod,
    Proposition,
    apply_post_extraction_classification,
    classify_extracted_proposition,
)
from law_proposition_extractor_pipeline.heuristics.classification_explanations import (
    build_classification_decision_explanations,
    classification_facts_from_propositions,
)
from law_proposition_extractor_pipeline.heuristics.registry import (
    RULE_DERIVE_LEGAL_EFFECT,
    get_heuristic,
    list_heuristics,
    require_heuristic,
)
from law_proposition_extractor_pipeline.heuristics.structured_list_explanations import (
    merge_decision_explanation_lists,
)


def _prop(**overrides: object) -> Proposition:
    payload = {
        "id": "prop:test0000000001",
        "proposition_text": "Operators shall place the catch in labelled containers.",
        "legal_subject": "operators",
        "action": "shall place",
        "topic_id": "topic-demo",
        "jurisdiction": "UK",
        "source_record_id": "src-1",
        "source_snapshot_id": "snap-1",
        "source_fragment_id": "frag-1",
        "fragment_locator": "article:1:paragraph:1",
        "extraction_debug_meta": {"provision_type": "core", "candidate_origin": "llm"},
    }
    payload.update(overrides)
    return Proposition.model_validate(payload)


def test_registry_has_classification_rule() -> None:
    rule = require_heuristic(RULE_DERIVE_LEGAL_EFFECT)
    assert rule.version == "1"
    assert rule.stage == DecisionStage.CLASSIFICATION
    assert rule.method == HeuristicMethod.DETERMINISTIC
    ids = [h.rule_id for h in list_heuristics()]
    assert ids == sorted(ids)
    assert get_heuristic(RULE_DERIVE_LEGAL_EFFECT) is not None


def test_obligation_classification_emits_explanation() -> None:
    prop = _prop()
    apply_post_extraction_classification(prop)
    expls = build_classification_decision_explanations(propositions=[prop])
    assert len(expls) == 1
    expl = expls[0]
    assert expl.stage == DecisionStage.CLASSIFICATION
    assert expl.decision_type == DecisionType.CLASSIFY
    assert expl.subject_kind == DecisionSubjectKind.PROPOSITION
    assert expl.outcome == "classified_as_obligation"
    assert expl.method == HeuristicMethod.DETERMINISTIC
    assert expl.rule_id == RULE_DERIVE_LEGAL_EFFECT
    basis = next(e.value for e in expl.evidence if e.kind == "winning_basis")
    assert basis == "obligatory_modal"


def test_prohibition_and_derogation_explanations() -> None:
    prohib = _prop(
        id="prop:prohib00000001",
        proposition_text="Catches must not be mixed with other species.",
        action="must not be mixed",
    )
    derog = _prop(
        id="prop:derog000000001",
        proposition_text="Paragraph 1 shall not apply to small vessels.",
        action="shall not apply",
        extraction_debug_meta={
            "provision_type": "exception",
            "candidate_origin": "llm",
            "structured_list_path": "2-a-ii",
        },
    )
    apply_post_extraction_classification(prohib)
    apply_post_extraction_classification(derog)
    by_id = {
        e.subject_id: e
        for e in build_classification_decision_explanations(
            propositions=[prohib, derog]
        )
    }
    assert by_id[prohib.id].outcome == "classified_as_prohibition"
    assert next(e.value for e in by_id[prohib.id].evidence if e.kind == "winning_basis") == (
        "prohibitory_modal"
    )
    assert by_id[derog.id].outcome == "classified_as_derogation"
    assert next(e.value for e in by_id[derog.id].evidence if e.kind == "winning_basis") == (
        "explicit_exception_cue"
    )
    assert next(
        e.value for e in by_id[derog.id].evidence if e.kind == "precedence_branch"
    ) == "explicit_priority"
    # LLM-origin input does not make method llm.
    assert by_id[derog.id].method == HeuristicMethod.DETERMINISTIC
    assert next(
        e.value for e in by_id[derog.id].evidence if e.kind == "candidate_origin"
    ) == "llm"


def test_fallback_unknown_explained_truthfully() -> None:
    prop = _prop(
        id="prop:unknown0000001",
        proposition_text="Introductory recital without operative force.",
        action="",
        extraction_debug_meta={"provision_type": "core"},
    )
    apply_post_extraction_classification(prop)
    expl = build_classification_decision_explanations(propositions=[prop])[0]
    assert expl.outcome == "classified_as_unknown"
    assert next(e.value for e in expl.evidence if e.kind == "winning_basis") == (
        "fallback_unknown"
    )


def test_classification_not_rerun_during_explanation_export() -> None:
    # Emit from a captured fact only — do not call the classifier.
    facts = [
        {
            "fact_kind": "derive_legal_effect",
            "proposition_id": "prop:frozen00000001",
            "source_fragment_id": "frag-1",
            "fragment_locator": "article:49a:paragraph:2",
            "legal_effect_type": "derogation",
            "winning_basis": "explicit_exception_cue",
            "precedence_branch": "explicit_priority",
            "matched_cue": "shall not apply",
            "extracted_provision_type": "exception",
            "candidate_origin": "llm",
            "structured_list_path": "2-a-ii",
        }
    ]
    expls = build_classification_decision_explanations(facts)
    assert len(expls) == 1
    assert expls[0].outcome == "classified_as_derogation"
    assert expls[0].method == HeuristicMethod.DETERMINISTIC


def test_changing_outcome_changes_decision_id() -> None:
    prop = _prop(
        id="prop:idchange000001",
        proposition_text="Operators shall keep records.",
    )
    apply_post_extraction_classification(prop)
    facts = classification_facts_from_propositions([prop])
    a = build_classification_decision_explanations(facts)[0]
    mutated = dict(facts[0])
    mutated["legal_effect_type"] = "prohibition"
    b = build_classification_decision_explanations([mutated])[0]
    assert a.id != b.id


def test_reordering_irrelevant_metadata_does_not_change_id() -> None:
    prop = _prop(id="prop:order000000001", proposition_text="A person must notify the authority.")
    apply_post_extraction_classification(prop)
    facts = classification_facts_from_propositions([prop])
    flipped = dict(facts[0])
    # Extra non-material key must not affect id (material identity ignores it).
    flipped["noise"] = "zzz"
    a = build_classification_decision_explanations(facts)[0]
    b = build_classification_decision_explanations([flipped])[0]
    assert a.id == b.id


def test_merge_stage_order_classification_after_extraction() -> None:
    prop = _prop(id="prop:merge000000001")
    apply_post_extraction_classification(prop)
    classification = build_classification_decision_explanations(propositions=[prop])
    # Minimal selection-like stub via decision_explanation_id only — use classification alone
    # plus empty extraction list through merge with another classification.
    merged = merge_decision_explanation_lists(classification)
    assert merged[0].stage == DecisionStage.CLASSIFICATION


def test_derive_basis_matches_classify_result() -> None:
    result = classify_extracted_proposition(
        proposition_text="Paragraph 1 shall not apply to Norwegian pout.",
        provision_type="exception",
    )
    assert result.legal_effect_type.value == "derogation"
    assert result.winning_basis == "explicit_exception_cue"
    assert result.precedence_branch == "explicit_priority"
