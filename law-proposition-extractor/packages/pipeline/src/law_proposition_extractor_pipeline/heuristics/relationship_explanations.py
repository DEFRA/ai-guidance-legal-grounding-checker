"""Emit typed legal-relationship DecisionExplanation records.

Facts are captured at the inference site in ``legal_rule_relationships`` and
turned into DecisionExplanation records without rerunning cue detection or
target selection.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from law_proposition_extractor_domain import (
    DecisionEvidence,
    DecisionExplanation,
    DecisionInput,
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    HeuristicMethod,
)

from .registry import (
    RULE_INFER_EXCEPTION_TO,
    RULE_INFER_TRIGGERED_BY,
    RULE_INFERENCE_UNRESOLVED,
    RULE_PREFER_GROUP_TARGET,
    require_heuristic,
)
from .selection_explanations import (
    _material_identity,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

FACT_INFER_EXCEPTION = "infer_exception_to"
FACT_INFER_TRIGGER = "infer_triggered_by"
FACT_PREFER_GROUP = "prefer_group_target"
FACT_INFERENCE_UNRESOLVED = "inference_unresolved"

_DIAG_OUTCOME = {
    "typed_relationship_cue_reference_parse_failed": "cue_reference_parse_failed",
    "typed_relationship_reference_not_uniquely_associated": "reference_not_uniquely_associated",
    "typed_relationship_cue_reference_no_matching_target": "cue_reference_no_matching_target",
    "typed_relationship_target_ambiguous": "target_ambiguous",
    "typed_relationship_target_group_missing": "target_group_missing",
}


def relationship_candidate_id(
    *,
    source_proposition_id: str,
    relationship_type: str,
    cue_text: str,
    reference_text: str,
    canonical_locator: str,
    diagnostic_code: str = "",
) -> str:
    """Deterministic candidate id when no final relationship exists."""
    parts = (
        str(source_proposition_id).strip(),
        str(relationship_type).strip(),
        str(cue_text).strip().lower(),
        str(reference_text).strip().lower(),
        str(canonical_locator).strip().lower(),
        str(diagnostic_code).strip(),
    )
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"relcand:{digest}"


def build_relationship_decision_explanations(
    facts: Sequence[Mapping[str, Any]],
) -> list[DecisionExplanation]:
    """Map captured relationship decision facts to DecisionExplanation records."""
    explanations: list[DecisionExplanation] = []
    seen: set[str] = set()

    def _add(expl: DecisionExplanation) -> None:
        if expl.id in seen:
            return
        seen.add(expl.id)
        explanations.append(expl)

    for fact in facts:
        kind = str(fact.get("fact_kind") or "")
        if kind == FACT_INFER_EXCEPTION:
            _add(_explain_infer(fact, RULE_INFER_EXCEPTION_TO, "inferred_exception_to"))
        elif kind == FACT_INFER_TRIGGER:
            _add(_explain_infer(fact, RULE_INFER_TRIGGERED_BY, "inferred_triggered_by"))
        elif kind == FACT_PREFER_GROUP:
            _add(_explain_prefer_group(fact))
        elif kind == FACT_INFERENCE_UNRESOLVED:
            _add(_explain_unresolved(fact))

    return sorted(
        explanations,
        key=lambda e: (
            e.subject_id,
            e.rule_id,
            e.id,
        ),
    )


def _unselected_ordinary_refs(fact: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in fact.get("unselected_ordinary_references") or []:
        if isinstance(item, Mapping):
            text = str(item.get("reference_text") or item.get("value") or "").strip()
            reason = str(item.get("reason") or "outside_typed_relationship_cue").strip()
            if text:
                rows.append({"reference_text": text, "reason": reason})
        else:
            text = str(item or "").strip()
            if text:
                rows.append(
                    {
                        "reference_text": text,
                        "reason": "outside_typed_relationship_cue",
                    }
                )
    return sorted(rows, key=lambda r: (r["reference_text"].lower(), r["reason"]))


def _explain_infer(
    fact: Mapping[str, Any],
    rule_id: str,
    outcome: str,
) -> DecisionExplanation:
    rule = require_heuristic(rule_id)
    rel_id = str(fact.get("relationship_id") or "").strip()
    source_id = str(fact.get("source_proposition_id") or "").strip()
    rel_type = str(fact.get("relationship_type") or "").strip()
    cue_text = str(fact.get("cue_text") or "").strip()
    cue_basis = str(fact.get("cue_basis") or fact.get("inference_basis") or "").strip()
    reference_text = str(fact.get("reference_text") or "").strip()
    canonical = str(fact.get("canonical_target_locator") or "").strip()
    resolution_basis = str(fact.get("resolution_basis") or "").strip()
    matched_ref = str(fact.get("matched_resolved_reference") or "").strip()
    frag_id = str(fact.get("source_fragment_id") or "").strip()
    confidence = str(fact.get("confidence") or "").strip()
    subject_id = rel_id or str(fact.get("candidate_id") or "")

    evidence = [
        DecisionEvidence(
            kind="relationship_type",
            label="Relationship type",
            value=rel_type,
        ),
        DecisionEvidence(
            kind="cue_text",
            label="Cue text",
            value=cue_text[:200],
        ),
        DecisionEvidence(
            kind="cue_basis",
            label="Cue basis",
            value=cue_basis,
        ),
        DecisionEvidence(
            kind="cue_bound_reference",
            label="Cue-bound reference",
            value=reference_text,
        ),
        DecisionEvidence(
            kind="canonical_target_locator",
            label="Canonical target locator",
            value=canonical,
        ),
    ]
    if matched_ref:
        evidence.append(
            DecisionEvidence(
                kind="matched_resolved_reference",
                label="Matched resolved reference",
                value=matched_ref,
            )
        )
    if resolution_basis:
        evidence.append(
            DecisionEvidence(
                kind="resolution_basis",
                label="Resolution basis",
                value=resolution_basis,
            )
        )
    if source_id:
        evidence.append(
            DecisionEvidence(
                kind="source_proposition_id",
                label="Source proposition",
                value=source_id,
                id=source_id,
            )
        )
    if frag_id:
        evidence.append(
            DecisionEvidence(
                kind="source_fragment_id",
                label="Source fragment",
                value=frag_id,
                id=frag_id,
            )
        )
    if confidence:
        evidence.append(
            DecisionEvidence(kind="confidence", label="Confidence", value=confidence)
        )
    if rel_id:
        evidence.append(
            DecisionEvidence(
                kind="relationship_id",
                label="Relationship",
                value=rel_id,
                id=rel_id,
            )
        )
    for ref in _unselected_ordinary_refs(fact):
        evidence.append(
            DecisionEvidence(
                kind="unselected_ordinary_reference",
                label="Unselected ordinary reference",
                value=ref["reference_text"],
            )
        )
        evidence.append(
            DecisionEvidence(
                kind="unselected_ordinary_reference_reason",
                label="Unselected reason",
                value=ref["reason"],
            )
        )
    for target in sorted(
        str(t) for t in (fact.get("available_resolved_targets") or []) if str(t).strip()
    ):
        evidence.append(
            DecisionEvidence(
                kind="available_resolved_target",
                label="Available resolved target",
                value=target,
            )
        )

    inputs = [
        DecisionInput(
            kind="source_proposition",
            label="Source proposition",
            value=source_id,
            id=source_id or None,
        ),
        DecisionInput(kind="cue_bound_reference", label="Cue reference", value=reference_text),
        DecisionInput(
            kind="canonical_target_locator",
            label="Canonical locator",
            value=canonical,
        ),
    ]

    material = _material_identity(
        rule_id,
        rel_id or subject_id,
        source_id,
        rel_type,
        canonical,
        cue_basis,
        cue_text.lower(),
        reference_text.lower(),
        outcome,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.RELATIONSHIP.value,
        decision_type=DecisionType.INFER.value,
        subject_kind=DecisionSubjectKind.LEGAL_RULE_RELATIONSHIP.value,
        subject_id=subject_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )
    cue_label = "exception" if "exception" in outcome else "trigger"
    summary = (
        f"Law Proposition Extractor inferred {rel_type} from a supported {cue_label} cue "
        f'("{cue_text[:80]}"). The cue-bound reference {reference_text!r} '
        f"resolved to {canonical}."
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.RELATIONSHIP,
        decision_type=DecisionType.INFER,
        subject_kind=DecisionSubjectKind.LEGAL_RULE_RELATIONSHIP,
        subject_id=subject_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(inputs),
        evidence=_sorted_evidence(evidence),
        confidence=confidence or None,
        diagnostics=[],
        code_references=list(rule.code_references),
        metadata={
            "relationship_type": rel_type,
            "canonical_target_locator": canonical,
            "cue_basis": cue_basis,
            "source_proposition_id": source_id,
        },
    )


def _explain_prefer_group(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_PREFER_GROUP_TARGET)
    rel_id = str(fact.get("relationship_id") or "").strip()
    target_kind = str(fact.get("target_kind") or "").strip()
    target_id = str(fact.get("target_id") or "").strip()
    canonical = str(fact.get("canonical_target_locator") or "").strip()
    source_record = str(fact.get("source_record_id") or "").strip()
    source_snapshot = str(fact.get("source_snapshot_id") or "").strip()
    members = sorted(
        str(m) for m in (fact.get("member_proposition_ids") or []) if str(m).strip()
    )
    outcome = (
        "targeted_legal_rule_group"
        if target_kind == "legal_rule_group"
        else "targeted_unique_proposition"
    )
    subject_id = rel_id or str(fact.get("candidate_id") or "")

    evidence = [
        DecisionEvidence(
            kind="canonical_target_locator",
            label="Canonical target locator",
            value=canonical,
        ),
        DecisionEvidence(
            kind="target_kind",
            label="Target kind",
            value=target_kind,
        ),
        DecisionEvidence(
            kind="target_id",
            label="Target id",
            value=target_id,
            id=target_id or None,
        ),
        DecisionEvidence(
            kind="source_record_id",
            label="Source record scope",
            value=source_record,
        ),
        DecisionEvidence(
            kind="source_snapshot_id",
            label="Source snapshot scope",
            value=source_snapshot,
        ),
    ]
    if fact.get("target_fragment_id"):
        evidence.append(
            DecisionEvidence(
                kind="target_fragment_id",
                label="Target fragment",
                value=str(fact["target_fragment_id"]),
                id=str(fact["target_fragment_id"]),
            )
        )
    for mid in members:
        evidence.append(
            DecisionEvidence(
                kind="group_member_proposition_id",
                label="Group member proposition",
                value=mid,
                id=mid,
            )
        )
    if rel_id:
        evidence.append(
            DecisionEvidence(
                kind="relationship_id",
                label="Relationship",
                value=rel_id,
                id=rel_id,
            )
        )
    if fact.get("selection_basis"):
        evidence.append(
            DecisionEvidence(
                kind="selection_basis",
                label="Target selection basis",
                value=str(fact["selection_basis"]),
            )
        )

    inputs = [
        DecisionInput(
            kind="canonical_target_locator",
            label="Canonical locator",
            value=canonical,
        ),
        DecisionInput(kind="target_kind", label="Target kind", value=target_kind),
        DecisionInput(
            kind="target_id", label="Target id", value=target_id, id=target_id or None
        ),
    ]

    material = _material_identity(
        RULE_PREFER_GROUP_TARGET,
        rel_id or subject_id,
        target_kind,
        target_id,
        source_record,
        source_snapshot,
        canonical,
        outcome,
        *members,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.RELATIONSHIP.value,
        decision_type=DecisionType.TARGET.value,
        subject_kind=DecisionSubjectKind.LEGAL_RULE_RELATIONSHIP.value,
        subject_id=subject_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )
    if target_kind == "legal_rule_group":
        member_bit = ", ".join(members) if members else "(none recorded)"
        summary = (
            f"Law Proposition Extractor targeted LegalRuleGroup {target_id} for {canonical} so "
            f"downstream context is inherited by its member propositions "
            f"({member_bit})."
        )
    else:
        summary = (
            f"No unique LegalRuleGroup was available for {canonical}; Law Proposition Extractor "
            f"targeted the unique retained proposition {target_id}."
        )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.RELATIONSHIP,
        decision_type=DecisionType.TARGET,
        subject_kind=DecisionSubjectKind.LEGAL_RULE_RELATIONSHIP,
        subject_id=subject_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(inputs),
        evidence=_sorted_evidence(evidence),
        diagnostics=[],
        code_references=list(rule.code_references),
        metadata={
            "target_kind": target_kind,
            "target_id": target_id,
            "member_proposition_ids": members,
            "canonical_target_locator": canonical,
        },
    )


def _explain_unresolved(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_INFERENCE_UNRESOLVED)
    diagnostic = str(fact.get("diagnostic_code") or "").strip()
    outcome = _DIAG_OUTCOME.get(diagnostic, diagnostic or "inference_unresolved")
    source_id = str(fact.get("source_proposition_id") or "").strip()
    rel_type = str(fact.get("relationship_type") or "").strip()
    cue_text = str(fact.get("cue_text") or "").strip()
    reference_text = str(fact.get("reference_text") or "").strip()
    canonical = str(fact.get("canonical_target_locator") or "").strip()
    candidate_id = str(fact.get("candidate_id") or "").strip()
    if not candidate_id:
        candidate_id = relationship_candidate_id(
            source_proposition_id=source_id,
            relationship_type=rel_type,
            cue_text=cue_text,
            reference_text=reference_text,
            canonical_locator=canonical,
            diagnostic_code=diagnostic,
        )

    evidence = [
        DecisionEvidence(
            kind="diagnostic_code",
            label="Diagnostic code",
            value=diagnostic,
        ),
        DecisionEvidence(
            kind="relationship_type",
            label="Attempted relationship type",
            value=rel_type,
        ),
        DecisionEvidence(
            kind="inference_succeeded",
            label="Relationship claimed",
            value="false",
        ),
    ]
    if cue_text:
        evidence.append(
            DecisionEvidence(kind="cue_text", label="Cue text", value=cue_text[:200])
        )
    if reference_text:
        evidence.append(
            DecisionEvidence(
                kind="cue_bound_reference",
                label="Cue-bound reference",
                value=reference_text,
            )
        )
    if canonical:
        evidence.append(
            DecisionEvidence(
                kind="canonical_target_locator",
                label="Canonical cue locator",
                value=canonical,
            )
        )
    if source_id:
        evidence.append(
            DecisionEvidence(
                kind="source_proposition_id",
                label="Source proposition",
                value=source_id,
                id=source_id,
            )
        )
    if fact.get("detail"):
        evidence.append(
            DecisionEvidence(
                kind="diagnostic_detail",
                label="Detail",
                value=str(fact["detail"]),
            )
        )

    material = _material_identity(
        RULE_INFERENCE_UNRESOLVED,
        candidate_id,
        source_id,
        rel_type,
        diagnostic,
        canonical,
        cue_text.lower(),
        reference_text.lower(),
        outcome,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.RELATIONSHIP.value,
        decision_type=DecisionType.DIAGNOSE.value,
        subject_kind=DecisionSubjectKind.LEGAL_RULE_RELATIONSHIP.value,
        subject_id=candidate_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )
    summary = (
        f"Law Proposition Extractor detected a typed-relationship cue for {rel_type} but could not "
        f"safely complete inference ({outcome}). No relationship was emitted."
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.RELATIONSHIP,
        decision_type=DecisionType.DIAGNOSE,
        subject_kind=DecisionSubjectKind.LEGAL_RULE_RELATIONSHIP,
        subject_id=candidate_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="source_proposition",
                    label="Source proposition",
                    value=source_id,
                    id=source_id or None,
                )
            ]
        ),
        evidence=_sorted_evidence(evidence),
        diagnostics=[diagnostic] if diagnostic else [],
        code_references=list(rule.code_references),
        metadata={
            "relationship_claimed": False,
            "diagnostic_code": diagnostic,
            "source_proposition_id": source_id,
        },
    )
