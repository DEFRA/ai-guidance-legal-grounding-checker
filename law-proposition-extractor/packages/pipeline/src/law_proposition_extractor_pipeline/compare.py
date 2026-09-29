from typing import Literal

from law_proposition_extractor_domain import ConfidenceLevel, DivergenceAssessment, DivergenceType, Proposition
from law_proposition_extractor_llm import JuditLLMClient

from .intake import slugify


def compare_propositions(
    proposition_a: Proposition,
    proposition_b: Proposition,
    llm_client: JuditLLMClient | None = None,
    *,
    divergence_reasoning: Literal["none", "frontier"] = "none",
) -> DivergenceAssessment:
    divergence_type = _infer_divergence_type(proposition_a, proposition_b)
    divergence_exists = divergence_type != DivergenceType.NONE

    rationale = _build_rationale(proposition_a, proposition_b, divergence_type)
    operational_impact = _build_operational_impact(proposition_a, proposition_b, divergence_type)

    if llm_client and divergence_reasoning == "frontier":
        try:
            prompt = f"""
Compare these two legal propositions and explain the divergence in 2 short sentences.

Jurisdiction A: {proposition_a.jurisdiction}
Text A: {proposition_a.proposition_text}

Jurisdiction B: {proposition_b.jurisdiction}
Text B: {proposition_b.proposition_text}

Predicted divergence type: {divergence_type.value}
""".strip()
            llm_rationale = llm_client.reason_text(prompt)
            if llm_rationale.strip():
                rationale = llm_rationale.strip()
        except Exception:
            pass

    return DivergenceAssessment(
        id=f"div-{slugify(proposition_a.id + '-' + proposition_b.id)}",
        finding_id=f"finding-{proposition_a.id}-{proposition_b.id}",
        proposition_id=proposition_a.id,
        comparator_proposition_id=proposition_b.id,
        jurisdiction_a=proposition_a.jurisdiction,
        jurisdiction_b=proposition_b.jurisdiction,
        common_ancestor="Shared baseline identified outside this demo slice.",
        divergence_exists=divergence_exists,
        divergence_type=divergence_type,
        affected_subjects=sorted(
            set(proposition_a.affected_subjects + proposition_b.affected_subjects)
        ),
        operational_impact=operational_impact,
        confidence=_infer_confidence(proposition_a, proposition_b, divergence_type),
        rationale=rationale,
        sources_checked=[proposition_a.source_record_id, proposition_b.source_record_id],
    )


def _infer_divergence_type(
    proposition_a: Proposition,
    proposition_b: Proposition,
) -> DivergenceType:
    if proposition_a.proposition_text.strip() == proposition_b.proposition_text.strip():
        return DivergenceType.NONE

    if (
        proposition_a.authority != proposition_b.authority
        and proposition_a.action == proposition_b.action
    ):
        return DivergenceType.INSTITUTIONAL

    if set(proposition_a.required_documents) != set(proposition_b.required_documents):
        return DivergenceType.ANNEX_MODEL_CERTIFICATE

    if proposition_a.conditions != proposition_b.conditions:
        return DivergenceType.PROCEDURAL

    if proposition_a.legal_subject != proposition_b.legal_subject:
        return DivergenceType.DEFINITIONAL

    if proposition_a.action != proposition_b.action:
        return DivergenceType.TEXTUAL

    return DivergenceType.STRUCTURAL


def _infer_confidence(
    proposition_a: Proposition,
    proposition_b: Proposition,
    divergence_type: DivergenceType,
) -> ConfidenceLevel:
    if divergence_type == DivergenceType.NONE:
        return ConfidenceLevel.HIGH

    if proposition_a.authority != proposition_b.authority:
        return ConfidenceLevel.HIGH

    if (
        proposition_a.action != proposition_b.action
        or proposition_a.conditions != proposition_b.conditions
    ):
        return ConfidenceLevel.MEDIUM

    return ConfidenceLevel.MEDIUM


def _build_rationale(
    proposition_a: Proposition,
    proposition_b: Proposition,
    divergence_type: DivergenceType,
) -> str:
    if divergence_type == DivergenceType.NONE:
        return "The two propositions are materially aligned on the current comparison."
    if divergence_type == DivergenceType.INSTITUTIONAL:
        return (
            f"The propositions preserve a similar action, but the decision-maker differs: "
            f"{proposition_a.authority or 'unspecified'} "
            f"vs {proposition_b.authority or 'unspecified'}."
        )
    if divergence_type == DivergenceType.PROCEDURAL:
        return "The core proposition is similar, but the conditions for compliance differ."
    if divergence_type == DivergenceType.ANNEX_MODEL_CERTIFICATE:
        return "The propositions differ in the documentary or record-keeping requirements."
    if divergence_type == DivergenceType.DEFINITIONAL:
        return "The propositions target different legal subjects or regulated actors."
    if divergence_type == DivergenceType.TEXTUAL:
        return "The wording differs in a way that appears capable of affecting legal effect."
    return (
        "The propositions differ in surrounding legal machinery rather than a simple "
        "like-for-like wording change."
    )


def _build_operational_impact(
    proposition_a: Proposition,
    proposition_b: Proposition,
    divergence_type: DivergenceType,
) -> str:
    if divergence_type == DivergenceType.NONE:
        return "No immediate operational difference identified in this comparison slice."
    if divergence_type == DivergenceType.INSTITUTIONAL:
        return (
            "An operator may need to engage a different authority or administrative "
            "pathway in each jurisdiction."
        )
    if divergence_type == DivergenceType.PROCEDURAL:
        return "The compliance pathway differs because the triggering conditions are not the same."
    if divergence_type == DivergenceType.ANNEX_MODEL_CERTIFICATE:
        return "The supporting documents or records required for compliance differ."
    if divergence_type == DivergenceType.DEFINITIONAL:
        return "The scope of who is regulated differs between the two propositions."
    if divergence_type == DivergenceType.TEXTUAL:
        return "Different wording may change what a regulated party must actually do."
    return "The practical workflow may differ even where the high-level rule appears related."
