"""Emit effective-law typed-context DecisionExplanation records.

Facts are captured while typed required-context entries are constructed and
while generic locator duplicates are suppressed. Explanations are built from
those facts without rerunning effective-law composition.
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
)

from .registry import (
    RULE_ATTACH_APPLICABLE_EXCEPTION,
    RULE_ATTACH_EXCEPTION_TARGET,
    RULE_ATTACH_TRIGGER_CONDITION,
    RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR,
    require_heuristic,
)
from .selection_explanations import (
    _material_identity,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

FACT_ATTACH_APPLICABLE_EXCEPTION = "attach_applicable_exception"
FACT_ATTACH_EXCEPTION_TARGET = "attach_exception_target"
FACT_ATTACH_TRIGGER_CONDITION = "attach_trigger_condition"
FACT_PREFER_TYPED_OVER_GENERIC = "prefer_typed_context_over_generic_locator"

_ATTACH_RULES = {
    FACT_ATTACH_APPLICABLE_EXCEPTION: (
        RULE_ATTACH_APPLICABLE_EXCEPTION,
        "applicable_exception_attached",
        "applicable_exception",
    ),
    FACT_ATTACH_EXCEPTION_TARGET: (
        RULE_ATTACH_EXCEPTION_TARGET,
        "exception_target_attached",
        "exception_target",
    ),
    FACT_ATTACH_TRIGGER_CONDITION: (
        RULE_ATTACH_TRIGGER_CONDITION,
        "trigger_condition_attached",
        "trigger_condition",
    ),
}


def bind_effective_law_decision_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    statements: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Bind receiving proposition ids to final effective-law statement ids."""
    prop_to_stmt: dict[str, str] = {}
    for stmt in statements or []:
        if not isinstance(stmt, Mapping):
            continue
        stmt_id = str(stmt.get("id") or "").strip()
        if not stmt_id:
            continue
        for pid in stmt.get("source_proposition_ids") or []:
            text = str(pid or "").strip()
            if text and text not in prop_to_stmt:
                prop_to_stmt[text] = stmt_id

    bound: list[dict[str, Any]] = []
    for fact in facts:
        row = dict(fact)
        receiving_prop = str(row.get("receiving_proposition_id") or "").strip()
        existing_stmt = str(row.get("effective_law_statement_id") or "").strip()
        if not existing_stmt and receiving_prop:
            mapped = prop_to_stmt.get(receiving_prop)
            if mapped:
                row["effective_law_statement_id"] = mapped
        bound.append(row)
    return bound


def build_effective_law_decision_explanations(
    facts: Sequence[Mapping[str, Any]],
) -> list[DecisionExplanation]:
    """Map captured effective-law decision facts to DecisionExplanation records."""
    explanations: list[DecisionExplanation] = []
    seen: set[str] = set()

    def _add(expl: DecisionExplanation) -> None:
        if expl.id in seen:
            return
        seen.add(expl.id)
        explanations.append(expl)

    for fact in facts:
        kind = str(fact.get("fact_kind") or "")
        if kind in _ATTACH_RULES:
            _add(_explain_attach(fact, *_ATTACH_RULES[kind]))
        elif kind == FACT_PREFER_TYPED_OVER_GENERIC:
            _add(_explain_prefer_typed(fact))

    return sorted(
        explanations,
        key=lambda e: (e.subject_id, e.rule_id, e.id),
    )


def _ordered_members(fact: Mapping[str, Any]) -> list[str]:
    return [
        str(mid).strip()
        for mid in (fact.get("ordered_group_members") or fact.get("group_member_ids") or [])
        if str(mid).strip()
    ]


def _explain_attach(
    fact: Mapping[str, Any],
    rule_id: str,
    outcome: str,
    context_kind: str,
) -> DecisionExplanation:
    rule = require_heuristic(rule_id)
    stmt_id = str(
        fact.get("effective_law_statement_id")
        or fact.get("receiving_statement_id")
        or ""
    ).strip()
    receiving_prop = str(fact.get("receiving_proposition_id") or "").strip()
    context_prop = str(fact.get("context_proposition_id") or "").strip()
    context_locator = str(fact.get("context_proposition_locator") or "").strip()
    rel_id = str(fact.get("legal_rule_relationship_id") or fact.get("relationship_id") or "").strip()
    rel_type = str(fact.get("relationship_type") or "").strip()
    rel_source = str(fact.get("relationship_source_proposition_id") or "").strip()
    target_kind = str(fact.get("relationship_target_kind") or "").strip()
    target_id = str(fact.get("relationship_target_id") or "").strip()
    group_id = str(fact.get("legal_rule_group_id") or "").strip()
    inherited = bool(fact.get("inherited_via_group"))
    expansion_direction = str(fact.get("expansion_direction") or "").strip()
    role_basis = str(fact.get("role_assignment_basis") or "").strip()
    source_record_id = str(fact.get("source_record_id") or "").strip()
    source_snapshot_id = str(fact.get("source_snapshot_id") or "").strip()
    members = _ordered_members(fact)
    subject_id = stmt_id or receiving_prop

    evidence = [
        DecisionEvidence(
            kind="effective_law_statement_id",
            label="Receiving statement",
            value=subject_id,
            id=subject_id or None,
        ),
        DecisionEvidence(
            kind="receiving_proposition_id",
            label="Receiving proposition",
            value=receiving_prop,
            id=receiving_prop or None,
        ),
        DecisionEvidence(
            kind="context_kind",
            label="Context kind",
            value=context_kind,
        ),
        DecisionEvidence(
            kind="context_proposition_id",
            label="Context proposition",
            value=context_prop,
            id=context_prop or None,
        ),
        DecisionEvidence(
            kind="legal_rule_relationship_id",
            label="Typed relationship",
            value=rel_id,
            id=rel_id or None,
        ),
        DecisionEvidence(
            kind="relationship_type",
            label="Relationship type",
            value=rel_type,
        ),
        DecisionEvidence(
            kind="inherited_via_group",
            label="Inherited via group",
            value="true" if inherited else "false",
        ),
    ]
    if context_locator:
        evidence.append(
            DecisionEvidence(
                kind="context_proposition_locator",
                label="Context proposition locator",
                value=context_locator,
            )
        )
    if rel_source:
        evidence.append(
            DecisionEvidence(
                kind="relationship_source_proposition_id",
                label="Relationship source",
                value=rel_source,
                id=rel_source,
            )
        )
    if target_kind:
        evidence.append(
            DecisionEvidence(
                kind="relationship_target_kind",
                label="Relationship target kind",
                value=target_kind,
            )
        )
    if target_id:
        evidence.append(
            DecisionEvidence(
                kind="relationship_target_id",
                label="Relationship target",
                value=target_id,
                id=target_id,
            )
        )
    if group_id:
        evidence.append(
            DecisionEvidence(
                kind="legal_rule_group_id",
                label="Expanded group",
                value=group_id,
                id=group_id,
            )
        )
    for mid in members:
        evidence.append(
            DecisionEvidence(
                kind="group_member_proposition_id",
                label="Group member",
                value=mid,
                id=mid,
            )
        )
    if expansion_direction:
        evidence.append(
            DecisionEvidence(
                kind="expansion_direction",
                label="Expansion direction",
                value=expansion_direction,
            )
        )
    if role_basis:
        evidence.append(
            DecisionEvidence(
                kind="role_assignment_basis",
                label="Role assignment basis",
                value=role_basis,
            )
        )
    if source_record_id:
        evidence.append(
            DecisionEvidence(
                kind="source_record_id",
                label="Source record",
                value=source_record_id,
                id=source_record_id,
            )
        )
    if source_snapshot_id:
        evidence.append(
            DecisionEvidence(
                kind="source_snapshot_id",
                label="Source snapshot",
                value=source_snapshot_id,
                id=source_snapshot_id,
            )
        )

    inputs = [
        DecisionInput(
            kind="effective_law_statement",
            label="Receiving statement",
            value=subject_id,
            id=subject_id or None,
        ),
        DecisionInput(
            kind="legal_rule_relationship",
            label="Typed relationship",
            value=rel_id,
            id=rel_id or None,
        ),
        DecisionInput(
            kind="context_proposition",
            label="Context proposition",
            value=context_prop,
            id=context_prop or None,
        ),
    ]

    material = _material_identity(
        rule.rule_id,
        rule.version,
        subject_id,
        context_kind,
        context_prop,
        rel_id,
        group_id if inherited else "",
        outcome,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.EFFECTIVE_LAW.value,
        decision_type=DecisionType.ATTACH.value,
        subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT.value,
        subject_id=subject_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )

    if context_kind == "applicable_exception":
        if inherited and group_id:
            summary = (
                f"Law Proposition Extractor attached {context_prop} as an applicable exception on "
                f"{receiving_prop} because an exception_to relationship targeted "
                f"group {group_id}; the effective-law composer expanded that "
                "group to its member rules. This is group-inherited context, "
                "not a newly inferred direct relationship."
            )
        else:
            summary = (
                f"Law Proposition Extractor attached {context_prop} as an applicable exception on "
                f"{receiving_prop} from a persisted exception_to relationship."
            )
    elif context_kind == "exception_target":
        if inherited and group_id:
            summary = (
                f"Law Proposition Extractor attached {context_prop} as an exception target on "
                f"{receiving_prop} because it is a member of group {group_id} "
                "targeted by the exception_to relationship. This projects that "
                "existing relationship into reviewer-facing context."
            )
        else:
            summary = (
                f"Law Proposition Extractor attached {context_prop} as an exception target on "
                f"{receiving_prop} from a persisted exception_to relationship."
            )
    else:
        summary = (
            f"Law Proposition Extractor attached {context_prop} as a trigger condition on "
            f"{receiving_prop} by expanding the triggered_by target"
            + (f" group {group_id}" if group_id else "")
            + ". Current triggered_by projection is source-only, so the "
            "receiving obligation is not projected backwards onto the trigger "
            "propositions."
        )

    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.EFFECTIVE_LAW,
        decision_type=DecisionType.ATTACH,
        subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT,
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
            "effective_law_statement_id": subject_id,
            "receiving_proposition_id": receiving_prop,
            "context_kind": context_kind,
            "context_proposition_id": context_prop,
            "legal_rule_relationship_id": rel_id,
            "legal_rule_group_id": group_id or None,
            "inherited_via_group": inherited,
            "expansion_direction": expansion_direction or None,
            "relationship_type": rel_type,
        },
    )


def _explain_prefer_typed(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_PREFER_TYPED_CONTEXT_OVER_GENERIC_LOCATOR)
    stmt_id = str(
        fact.get("effective_law_statement_id")
        or fact.get("receiving_statement_id")
        or ""
    ).strip()
    receiving_prop = str(fact.get("receiving_proposition_id") or "").strip()
    generic_locator = str(fact.get("generic_locator") or "").strip()
    generic_kind = str(fact.get("generic_context_kind") or "referenced_locator").strip()
    generic_prop_ids = [
        str(pid).strip()
        for pid in (fact.get("generic_target_proposition_ids") or [])
        if str(pid).strip()
    ]
    typed_rel_id = str(fact.get("typed_relationship_id") or "").strip()
    typed_kind = str(fact.get("typed_context_kind") or "").strip()
    equivalence = str(
        fact.get("equivalence_reason")
        or "generic_locator_targets_already_covered_by_typed_context"
    ).strip()
    outcome = "generic_locator_context_suppressed"
    subject_id = stmt_id or receiving_prop

    evidence = [
        DecisionEvidence(
            kind="effective_law_statement_id",
            label="Receiving statement",
            value=subject_id,
            id=subject_id or None,
        ),
        DecisionEvidence(
            kind="receiving_proposition_id",
            label="Receiving proposition",
            value=receiving_prop,
            id=receiving_prop or None,
        ),
        DecisionEvidence(
            kind="generic_locator",
            label="Generic locator candidate",
            value=generic_locator,
        ),
        DecisionEvidence(
            kind="generic_context_kind",
            label="Generic context kind",
            value=generic_kind,
        ),
        DecisionEvidence(
            kind="typed_relationship_id",
            label="Typed relationship",
            value=typed_rel_id,
            id=typed_rel_id or None,
        ),
        DecisionEvidence(
            kind="typed_context_kind",
            label="Typed context kind",
            value=typed_kind,
        ),
        DecisionEvidence(
            kind="equivalence_reason",
            label="Equivalence reason",
            value=equivalence,
        ),
        DecisionEvidence(
            kind="suppression_outcome",
            label="Suppression outcome",
            value=outcome,
        ),
    ]
    for pid in generic_prop_ids:
        evidence.append(
            DecisionEvidence(
                kind="generic_target_proposition_id",
                label="Generic target proposition",
                value=pid,
                id=pid,
            )
        )

    inputs = [
        DecisionInput(
            kind="effective_law_statement",
            label="Receiving statement",
            value=subject_id,
            id=subject_id or None,
        ),
        DecisionInput(
            kind="generic_locator",
            label="Generic locator",
            value=generic_locator,
        ),
        DecisionInput(
            kind="typed_relationship",
            label="Typed relationship",
            value=typed_rel_id,
            id=typed_rel_id or None,
        ),
    ]

    material = _material_identity(
        rule.rule_id,
        rule.version,
        subject_id,
        generic_locator.lower(),
        ",".join(sorted(generic_prop_ids)),
        typed_rel_id,
        typed_kind,
        outcome,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.EFFECTIVE_LAW.value,
        decision_type=DecisionType.SUPPRESS.value,
        subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT.value,
        subject_id=subject_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )
    summary = (
        f"Law Proposition Extractor omitted generic locator context {generic_locator!r} on "
        f"{receiving_prop} because typed {typed_kind} context from relationship "
        f"{typed_rel_id} already represents the same legal connection. "
        "Unrelated ordinary references are not removed by this rule."
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.EFFECTIVE_LAW,
        decision_type=DecisionType.SUPPRESS,
        subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT,
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
            "effective_law_statement_id": subject_id,
            "receiving_proposition_id": receiving_prop,
            "generic_locator": generic_locator,
            "typed_relationship_id": typed_rel_id,
            "typed_context_kind": typed_kind,
            "context_kind": typed_kind,
            "legal_rule_relationship_id": typed_rel_id,
        },
    )
