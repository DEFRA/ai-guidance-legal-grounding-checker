"""Emit legal-effect classification DecisionExplanation records.

Facts are captured at classify time onto ``extraction_debug_meta.legal_effect_decision``
and turned into DecisionExplanation records after opaque proposition IDs exist.
The classifier is not rerun during explanation emission.
"""

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
    legal_effect_decision_from_proposition,
)

from .registry import RULE_DERIVE_LEGAL_EFFECT, require_heuristic
from .selection_explanations import (
    _material_identity,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

FACT_DERIVE_LEGAL_EFFECT = "derive_legal_effect"

_OUTCOME_BY_EFFECT = {
    "obligation": "classified_as_obligation",
    "prohibition": "classified_as_prohibition",
    "derogation": "classified_as_derogation",
    "permission": "classified_as_permission",
    "definition": "classified_as_definition",
    "cross_reference": "classified_as_cross_reference",
    "unknown": "classified_as_unknown",
}


def _as_mapping(row: Proposition | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        return row
    if hasattr(row, "model_dump"):
        dumped = row.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _outcome_for_effect(effect: str) -> str:
    key = str(effect or "").strip().lower()
    return _OUTCOME_BY_EFFECT.get(key, f"classified_as_{key or 'unknown'}")


def _summary_for(
    *,
    effect: str,
    winning_basis: str,
    matched_cue: str | None,
    provision_type: str,
    path: str,
) -> str:
    effect_l = effect or "unknown"
    basis = winning_basis or "fallback_unknown"
    cue_bit = f' Matching cue: "{matched_cue}".' if matched_cue else ""
    pt_bit = (
        f" Extracted provision_type was {provision_type!r}."
        if provision_type
        else ""
    )
    path_bit = f" Structured-list path {path}." if path else ""
    return (
        f"Law Proposition Extractor's deterministic legal-effect classifier assigned "
        f"legal_effect_type={effect_l} with winning basis {basis}.{cue_bit}"
        f"{pt_bit}{path_bit}"
    )


def classification_facts_from_propositions(
    propositions: Sequence[Proposition | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build explanation facts from immutable classify-time decisions on props."""
    facts: list[dict[str, Any]] = []
    for row in propositions:
        prop = _as_mapping(row)
        prop_id = str(prop.get("id") or "").strip()
        if not prop_id:
            continue
        decision = legal_effect_decision_from_proposition(row)
        if not decision:
            # Older props without a stored decision: skip (do not rerun classifier).
            continue
        effect = str(
            decision.get("legal_effect_type") or prop.get("legal_effect_type") or ""
        ).strip()
        facts.append(
            {
                "fact_kind": FACT_DERIVE_LEGAL_EFFECT,
                "proposition_id": prop_id,
                "source_fragment_id": str(prop.get("source_fragment_id") or ""),
                "fragment_locator": str(prop.get("fragment_locator") or ""),
                "legal_effect_type": effect,
                "winning_basis": str(decision.get("winning_basis") or ""),
                "precedence_branch": str(decision.get("precedence_branch") or ""),
                "matched_cue": decision.get("matched_cue"),
                "extracted_provision_type": str(
                    decision.get("extracted_provision_type") or ""
                ),
                "candidate_origin": str(decision.get("candidate_origin") or ""),
                "structured_list_path": str(
                    decision.get("structured_list_path") or ""
                ),
            }
        )
    return facts


def build_classification_decision_explanations(
    facts: Sequence[Mapping[str, Any]] | None = None,
    *,
    propositions: Sequence[Proposition | Mapping[str, Any]] | None = None,
) -> list[DecisionExplanation]:
    """Map captured classification facts to DecisionExplanation records."""
    rows = list(facts) if facts is not None else classification_facts_from_propositions(
        propositions or ()
    )
    explanations: list[DecisionExplanation] = []
    seen: set[str] = set()
    for fact in rows:
        if str(fact.get("fact_kind") or "") != FACT_DERIVE_LEGAL_EFFECT:
            continue
        expl = _explain_derive(fact)
        if expl.id in seen:
            continue
        seen.add(expl.id)
        explanations.append(expl)
    return sorted(
        explanations,
        key=lambda e: (e.subject_id, e.rule_id, e.id),
    )


def _explain_derive(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_DERIVE_LEGAL_EFFECT)
    prop_id = str(fact.get("proposition_id") or "").strip()
    effect = str(fact.get("legal_effect_type") or "").strip()
    winning_basis = str(fact.get("winning_basis") or "")
    precedence_branch = str(fact.get("precedence_branch") or "")
    matched_cue = fact.get("matched_cue")
    matched_cue_s = str(matched_cue).strip() if matched_cue else ""
    provision_type = str(fact.get("extracted_provision_type") or "")
    path = str(fact.get("structured_list_path") or "")
    origin = str(fact.get("candidate_origin") or "")
    frag_id = str(fact.get("source_fragment_id") or "")
    locator = str(fact.get("fragment_locator") or "")
    outcome = _outcome_for_effect(effect)

    evidence = [
        DecisionEvidence(
            kind="legal_effect_type",
            label="Legal effect type",
            value=effect,
        ),
        DecisionEvidence(
            kind="winning_basis",
            label="Winning classification basis",
            value=winning_basis,
        ),
        DecisionEvidence(
            kind="precedence_branch",
            label="Precedence branch",
            value=precedence_branch,
        ),
    ]
    if matched_cue_s:
        evidence.append(
            DecisionEvidence(
                kind="matched_cue",
                label="Matched deterministic cue",
                value=matched_cue_s[:160],
            )
        )
    if provision_type:
        evidence.append(
            DecisionEvidence(
                kind="extracted_provision_type",
                label="Extracted provision type",
                value=provision_type,
            )
        )
    if path:
        evidence.append(
            DecisionEvidence(
                kind="structured_list_path",
                label="Structured-list path",
                value=path,
            )
        )
    if origin:
        evidence.append(
            DecisionEvidence(
                kind="candidate_origin",
                label="Candidate origin",
                value=origin,
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
    if locator:
        evidence.append(
            DecisionEvidence(
                kind="fragment_locator",
                label="Fragment locator",
                value=locator.split(" (", 1)[0].strip(),
            )
        )

    inputs = [
        DecisionInput(kind="proposition", label="Proposition", value=prop_id, id=prop_id),
    ]
    if provision_type:
        inputs.append(
            DecisionInput(
                kind="extracted_provision_type",
                label="Provision type",
                value=provision_type,
            )
        )
    if path:
        inputs.append(
            DecisionInput(kind="structured_list_path", label="Path", value=path)
        )

    material = _material_identity(
        RULE_DERIVE_LEGAL_EFFECT,
        prop_id,
        effect,
        winning_basis,
        precedence_branch,
        matched_cue_s,
        provision_type,
        path,
        frag_id,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.CLASSIFICATION.value,
        decision_type=DecisionType.CLASSIFY.value,
        subject_kind=DecisionSubjectKind.PROPOSITION.value,
        subject_id=prop_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.CLASSIFICATION,
        decision_type=DecisionType.CLASSIFY,
        subject_kind=DecisionSubjectKind.PROPOSITION,
        subject_id=prop_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=_summary_for(
            effect=effect,
            winning_basis=winning_basis,
            matched_cue=matched_cue_s or None,
            provision_type=provision_type,
            path=path,
        ),
        inputs=_sorted_inputs(inputs),
        evidence=_sorted_evidence(evidence),
        diagnostics=[],
        code_references=list(rule.code_references),
        metadata={
            "winning_basis": winning_basis,
            "precedence_branch": precedence_branch,
            "legal_effect_type": effect,
            "structured_list_path": path or None,
            "candidate_origin": origin or None,
        },
    )
