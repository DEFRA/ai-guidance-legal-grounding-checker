from law_proposition_extractor_domain import DivergenceAssessment, ReviewStatus
from law_proposition_extractor_pipeline.reviews import apply_review_to_assessment
from law_proposition_extractor_pipeline.runner import apply_assessment_review_decision, run_case_file


def test_apply_review_to_assessment_accept_with_edits() -> None:
    assessment = DivergenceAssessment(
        id="div-001",
        proposition_id="prop-001",
        comparator_proposition_id="prop-002",
        jurisdiction_a="EU",
        jurisdiction_b="UK",
        rationale="Original rationale.",
    )

    updated, decision = apply_review_to_assessment(
        assessment=assessment,
        new_status=ReviewStatus.ACCEPTED_WITH_EDITS,
        reviewer="reviewer:alice",
        note="Adjusted rationale for legal precision.",
        edited_fields={"rationale": "Edited rationale."},
    )

    assert updated.review_status == ReviewStatus.ACCEPTED_WITH_EDITS
    assert updated.rationale == "Edited rationale."
    assert decision.previous_status == ReviewStatus.PROPOSED
    assert decision.new_status == ReviewStatus.ACCEPTED_WITH_EDITS
    assert decision.reviewer == "reviewer:alice"
    assert decision.edited_fields == {"rationale": "Edited rationale."}


def test_apply_review_to_assessment_rejects_invalid_transition() -> None:
    assessment = DivergenceAssessment(
        id="div-001",
        proposition_id="prop-001",
        comparator_proposition_id="prop-002",
        jurisdiction_a="EU",
        jurisdiction_b="UK",
        review_status=ReviewStatus.ACCEPTED,
    )

    try:
        apply_review_to_assessment(
            assessment=assessment,
            new_status=ReviewStatus.REJECTED,
            reviewer="reviewer:alice",
            note="Too weak.",
        )
        raise AssertionError("Expected invalid transition to raise ValueError.")
    except ValueError as error:
        assert "Invalid review transition" in str(error)


def test_apply_assessment_review_decision_updates_bundle_and_trace() -> None:
    bundle = run_case_file("data/demo/example_case.json", use_llm=False)
    assessment_id = bundle["divergence_assessments"][0]["id"]
    updated = apply_assessment_review_decision(
        bundle=bundle,
        assessment_id=assessment_id,
        new_status=ReviewStatus.ACCEPTED_WITH_EDITS.value,
        reviewer="reviewer:alice",
        note="Approved with narrowed rationale.",
        edited_fields={"rationale": "Narrowed rationale."},
    )

    edited_assessment = next(
        item for item in updated["divergence_assessments"] if item["id"] == assessment_id
    )
    decision = updated["review_decisions"][-1]
    trace = updated["stage_traces"][-1]

    assert edited_assessment["review_status"] == ReviewStatus.ACCEPTED_WITH_EDITS.value
    assert edited_assessment["rationale"] == "Narrowed rationale."
    assert decision["target_type"] == "divergence_assessment"
    assert decision["new_status"] == ReviewStatus.ACCEPTED_WITH_EDITS.value
    assert trace["stage_name"] == "human review transition"
    assert trace["outputs"]["review_decision_id"] == decision["id"]
