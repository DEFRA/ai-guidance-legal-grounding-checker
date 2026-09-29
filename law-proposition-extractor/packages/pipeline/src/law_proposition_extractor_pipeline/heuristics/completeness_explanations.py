"""Emit decision explanations for composed structured-list completeness reconciliation."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from law_proposition_extractor_domain import (
    DecisionEvidence,
    DecisionExplanation,
    DecisionInput,
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    HeuristicMethod,
    Proposition,
)

from law_proposition_extractor_pipeline.composed_structured_list_completeness import (
    FACT_RECONCILE_COMPOSED_STRUCTURED_LIST,
)

from .registry import RULE_RECONCILE_COMPOSED_STRUCTURED_LIST, require_heuristic
from .selection_explanations import (
    _material_identity,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

_STAGE_ORDER = {
    DecisionStage.PROVENANCE.value: 0,
    DecisionStage.SELECTION.value: 1,
    DecisionStage.EXTRACTION.value: 2,
    DecisionStage.COMPLETENESS.value: 3,
    DecisionStage.CLASSIFICATION.value: 4,
    DecisionStage.GROUPING.value: 5,
    DecisionStage.RELATIONSHIP.value: 6,
    DecisionStage.EFFECTIVE_LAW.value: 7,
    DecisionStage.SOURCE_EFFECT.value: 8,
    DecisionStage.REVIEW.value: 9,
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


def bind_completeness_reconciliation_decision_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    propositions: Sequence[Proposition | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach final proposition IDs onto captured facts (no heuristic rerun)."""
    by_cand = _prop_by_candidate_id(propositions)
    bound: list[dict[str, Any]] = []
    for raw in facts:
        fact = dict(raw)
        cand = str(fact.get("candidate_id") or fact.get("retained_candidate_id") or "").strip()
        if cand and cand in by_cand:
            fact["proposition_id"] = by_cand[cand]
            fact["retained_proposition_id"] = by_cand[cand]
        bound.append(fact)
    return bound


def build_completeness_reconciliation_decision_explanations(
    facts: Sequence[Mapping[str, Any]],
) -> list[DecisionExplanation]:
    """Map completeness-reconciliation facts to DecisionExplanation records."""
    explanations: list[DecisionExplanation] = []
    seen: set[str] = set()
    for fact in facts:
        if str(fact.get("fact_kind") or "") != FACT_RECONCILE_COMPOSED_STRUCTURED_LIST:
            continue
        expl = _explain_reconcile(fact)
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


def _explain_reconcile(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_RECONCILE_COMPOSED_STRUCTURED_LIST)
    prop_id = str(fact.get("proposition_id") or fact.get("retained_proposition_id") or "").strip()
    cand = str(fact.get("candidate_id") or fact.get("retained_candidate_id") or "").strip()
    subject_id = prop_id or cand or "unknown"
    subject_kind = (
        DecisionSubjectKind.PROPOSITION if prop_id else DecisionSubjectKind.EXTRACTION_CANDIDATE
    )
    path = str(fact.get("structured_list_path") or "")
    model_status = str(fact.get("model_completeness_status") or "")
    final_status = str(fact.get("reconciled_completeness_status") or "complete")
    basis = str(fact.get("reconciliation_basis") or "")
    effect = str(fact.get("legal_effect") or "")
    outcome = str(fact.get("outcome") or "reconciled_context_dependent_to_complete")
    stem_ids = [str(x) for x in (fact.get("composed_stem_identifiers") or [])]

    evidence = [
        DecisionEvidence(
            kind="model_completeness_status",
            label="Model completeness status",
            value=model_status,
        ),
        DecisionEvidence(
            kind="reconciled_completeness_status",
            label="Reconciled completeness status",
            value=final_status,
        ),
        DecisionEvidence(
            kind="reconciliation_basis",
            label="Reconciliation basis",
            value=basis,
        ),
        DecisionEvidence(
            kind="structured_list_path",
            label="Structured-list path",
            value=path,
        ),
        DecisionEvidence(
            kind="legal_effect",
            label="Legal effect",
            value=effect,
        ),
        DecisionEvidence(
            kind="composed_stem_identifiers",
            label="Composed stem identifiers",
            value="; ".join(stem_ids),
        ),
        DecisionEvidence(
            kind="safe_override_reason",
            label="Why the override was safe",
            value=str(fact.get("safe_override_reason") or ""),
        ),
    ]
    if fact.get("model_reason"):
        evidence.append(
            DecisionEvidence(
                kind="model_reason",
                label="Original model reason",
                value=str(fact.get("model_reason")),
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
        RULE_RECONCILE_COMPOSED_STRUCTURED_LIST,
        subject_id,
        path,
        model_status,
        final_status,
        basis,
        effect,
        str(fact.get("source_record_id") or ""),
        str(fact.get("source_snapshot_id") or ""),
        str(fact.get("source_fragment_id") or ""),
        outcome,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.COMPLETENESS.value,
        decision_type=DecisionType.ASSESS.value,
        subject_kind=subject_kind.value,
        subject_id=subject_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )
    summary = (
        "Law Proposition Extractor marked this proposition complete after composition because its "
        "governing list stems and terminal condition were incorporated into the "
        "retained legal claim and no unresolved material context remained."
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.COMPLETENESS,
        decision_type=DecisionType.ASSESS,
        subject_kind=subject_kind,
        subject_id=subject_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="extraction_candidate" if not prop_id else "proposition",
                    label="Reconciled proposition" if prop_id else "Reconciled candidate",
                    value=subject_id,
                    id=subject_id,
                ),
                DecisionInput(
                    kind="structured_list_path",
                    label="Structured-list path",
                    value=path,
                ),
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        diagnostics=["completeness_reconciled_composed_structured_list"],
        code_references=list(rule.code_references),
        metadata={
            "model_completeness_status": model_status,
            "reconciled_completeness_status": final_status,
            "reconciliation_rule": rule.rule_id,
            "reconciliation_basis": basis,
            "structured_list_path": path,
            "legal_effect": effect,
            "proposition_id": prop_id or None,
            "candidate_id": cand or None,
            "diagnostic_code": "completeness_reconciled_composed_structured_list",
        },
    )
