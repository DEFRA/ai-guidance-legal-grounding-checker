"""Emit decision explanations for dependent-qualification suppression."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from law_proposition_extractor_domain import (
    DecisionAlternative,
    DecisionEvidence,
    DecisionExplanation,
    DecisionInput,
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    HeuristicMethod,
    Proposition,
    SuppressedDecisionItem,
)

from .registry import RULE_SUPPRESS_DEPENDENT_QUALIFICATION, require_heuristic
from .selection_explanations import (
    _material_identity,
    _sorted_alternatives,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

FACT_SUPPRESS_DEPENDENT_QUALIFICATION = "suppress_dependent_qualification"

_STAGE_ORDER = {
    DecisionStage.PROVENANCE.value: 0,
    DecisionStage.SELECTION.value: 1,
    DecisionStage.EXTRACTION.value: 2,
    DecisionStage.CLASSIFICATION.value: 3,
    DecisionStage.GROUPING.value: 4,
    DecisionStage.RELATIONSHIP.value: 5,
    DecisionStage.EFFECTIVE_LAW.value: 6,
    DecisionStage.SOURCE_EFFECT.value: 7,
    DecisionStage.REVIEW.value: 8,
}


def _prop_by_candidate_id(
    propositions: Sequence[Proposition | Mapping[str, Any]],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for prop in propositions:
        if isinstance(prop, Proposition):
            pid = str(prop.id or "")
            meta = prop.extraction_debug_meta if isinstance(prop.extraction_debug_meta, dict) else {}
        else:
            pid = str(prop.get("id") or "")
            meta = prop.get("extraction_debug_meta")
            meta = meta if isinstance(meta, dict) else {}
        cand = str(meta.get("extraction_candidate_id") or "").strip()
        if pid and cand:
            out[cand] = pid
    return out


def bind_dependent_qualification_decision_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    propositions: Sequence[Proposition | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach final proposition IDs onto captured facts (no heuristic rerun)."""
    by_cand = _prop_by_candidate_id(propositions)
    bound: list[dict[str, Any]] = []
    for raw in facts:
        fact = dict(raw)
        retained_cand = str(fact.get("retained_candidate_id") or "").strip()
        if retained_cand and retained_cand in by_cand:
            fact["retained_proposition_id"] = by_cand[retained_cand]
        bound.append(fact)
    return bound


def build_dependent_qualification_decision_explanations(
    facts: Sequence[Mapping[str, Any]],
) -> list[DecisionExplanation]:
    """Map dependent-qualification facts to DecisionExplanation records."""
    explanations: list[DecisionExplanation] = []
    seen: set[str] = set()
    for fact in facts:
        if str(fact.get("fact_kind") or "") != FACT_SUPPRESS_DEPENDENT_QUALIFICATION:
            continue
        expl = _explain_suppress(fact)
        if expl.id in seen:
            continue
        seen.add(expl.id)
        explanations.append(expl)
    return sorted(
        explanations,
        key=lambda e: (
            _STAGE_ORDER.get(e.stage.value if hasattr(e.stage, "value") else str(e.stage), 99),
            e.subject_kind.value if hasattr(e.subject_kind, "value") else str(e.subject_kind),
            e.subject_id,
            e.rule_id,
            e.id,
        ),
    )


def _explain_suppress(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_SUPPRESS_DEPENDENT_QUALIFICATION)
    retained_prop = str(fact.get("retained_proposition_id") or "").strip()
    retained_cand = str(fact.get("retained_candidate_id") or "").strip()
    suppressed_cand = str(fact.get("suppressed_candidate_id") or "").strip()
    basis = str(fact.get("preserved_measurement_basis") or "")
    evidence_rel = str(fact.get("evidence_relationship") or "")
    dependency = str(fact.get("dependency_basis") or "")
    outcome = str(fact.get("outcome") or "suppressed_as_dependent_qualification")
    evidence = [
        DecisionEvidence(
            kind="dependency_basis",
            label="Dependency basis",
            value=dependency,
        ),
        DecisionEvidence(
            kind="evidence_relationship",
            label="Evidence relationship",
            value=evidence_rel,
        ),
        DecisionEvidence(
            kind="preserved_measurement_basis",
            label="Preserved measurement basis",
            value=basis,
        ),
        DecisionEvidence(
            kind="preserved_thresholds",
            label="Preserved thresholds",
            value="; ".join(str(x) for x in (fact.get("preserved_thresholds") or [])),
        ),
        DecisionEvidence(
            kind="retained_candidate_id",
            label="Retained candidate",
            value=retained_cand,
            id=retained_cand,
        ),
        DecisionEvidence(
            kind="suppressed_candidate_id",
            label="Suppressed candidate",
            value=suppressed_cand,
            id=suppressed_cand,
        ),
    ]
    if retained_prop:
        evidence.append(
            DecisionEvidence(
                kind="retained_proposition_id",
                label="Retained proposition",
                value=retained_prop,
                id=retained_prop,
            )
        )
    if fact.get("source_fragment_id"):
        evidence.append(
            DecisionEvidence(
                kind="source_fragment_id",
                label="Source fragment",
                value=str(fact["source_fragment_id"]),
            )
        )
    material = _material_identity(
        RULE_SUPPRESS_DEPENDENT_QUALIFICATION,
        suppressed_cand,
        retained_cand,
        retained_prop,
        evidence_rel,
        dependency,
        basis,
        str(fact.get("source_record_id") or ""),
        str(fact.get("source_snapshot_id") or ""),
        str(fact.get("source_fragment_id") or ""),
        outcome,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.EXTRACTION.value,
        decision_type=DecisionType.SUPPRESS.value,
        subject_kind=DecisionSubjectKind.EXTRACTION_CANDIDATE.value,
        subject_id=suppressed_cand,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )
    summary = (
        "This candidate described only how a condition in the retained rule is "
        "measured. It was not retained as a separate proposition because it had "
        "no independent legal effect and its content was preserved in the "
        "governing proposition."
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.EXTRACTION,
        decision_type=DecisionType.SUPPRESS,
        subject_kind=DecisionSubjectKind.EXTRACTION_CANDIDATE,
        subject_id=suppressed_cand,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="extraction_candidate",
                    label="Suppressed candidate",
                    value=suppressed_cand,
                    id=suppressed_cand,
                ),
                DecisionInput(
                    kind="extraction_candidate",
                    label="Retained governing candidate",
                    value=retained_cand,
                    id=retained_cand,
                ),
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=_sorted_alternatives(
            [
                DecisionAlternative(
                    kind="extraction_candidate",
                    id=retained_cand,
                    label="Governing operative proposition",
                    value=retained_cand,
                    role="retained_governor",
                )
            ]
        ),
        suppressed_items=[
            SuppressedDecisionItem(
                kind="extraction_candidate",
                id=suppressed_cand,
                reason=dependency or "dependent_measurement_qualification",
                label="Suppressed dependent measurement qualification",
            )
        ],
        diagnostics=["dependent_qualification_measurement_suppressed"],
        code_references=list(rule.code_references),
        metadata={
            "retained_candidate_id": retained_cand,
            "retained_proposition_id": retained_prop or None,
            "evidence_relationship": evidence_rel,
            "dependency_basis": dependency,
            "preserved_measurement_basis": basis,
            "diagnostic_code": "dependent_qualification_measurement_suppressed",
        },
    )
