"""Emit legal-rule-group DecisionExplanation records from construction facts.

Facts are captured in ``build_legal_rule_groups`` when a group is created and
turned into DecisionExplanation records without rerunning grouping.
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

from .registry import RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP, require_heuristic
from .selection_explanations import (
    _material_identity,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

FACT_CREATE_SHARED_FRAGMENT_RULE_GROUP = "create_shared_fragment_rule_group"


def build_grouping_decision_explanations(
    facts: Sequence[Mapping[str, Any]],
) -> list[DecisionExplanation]:
    """Map captured grouping decision facts to DecisionExplanation records."""
    explanations: list[DecisionExplanation] = []
    seen: set[str] = set()

    def _add(expl: DecisionExplanation) -> None:
        if expl.id in seen:
            return
        seen.add(expl.id)
        explanations.append(expl)

    for fact in facts:
        kind = str(fact.get("fact_kind") or "")
        if kind == FACT_CREATE_SHARED_FRAGMENT_RULE_GROUP:
            _add(_explain_create_group(fact))

    return sorted(
        explanations,
        key=lambda e: (e.subject_id, e.rule_id, e.id),
    )


def _explain_create_group(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_CREATE_SHARED_FRAGMENT_RULE_GROUP)
    group_id = str(fact.get("group_id") or "").strip()
    source_record_id = str(fact.get("source_record_id") or "").strip()
    source_snapshot_id = str(fact.get("source_snapshot_id") or "").strip()
    source_fragment_id = str(fact.get("source_fragment_id") or "").strip()
    canonical_locator = str(fact.get("canonical_locator") or "").strip()
    group_basis = str(fact.get("group_basis") or "shared_source_fragment").strip()
    member_ids = [
        str(mid).strip()
        for mid in (fact.get("member_proposition_ids") or [])
        if str(mid).strip()
    ]
    member_count = int(fact.get("member_count") or len(member_ids))
    min_members = int(fact.get("minimum_member_count") or 2)
    outcome = "group_created"

    evidence = [
        DecisionEvidence(
            kind="source_record_id",
            label="Source record",
            value=source_record_id,
            id=source_record_id or None,
        ),
        DecisionEvidence(
            kind="source_snapshot_id",
            label="Source snapshot",
            value=source_snapshot_id,
            id=source_snapshot_id or None,
        ),
        DecisionEvidence(
            kind="source_fragment_id",
            label="Source fragment",
            value=source_fragment_id,
            id=source_fragment_id or None,
        ),
        DecisionEvidence(
            kind="canonical_locator",
            label="Source locator",
            value=canonical_locator,
        ),
        DecisionEvidence(
            kind="group_basis",
            label="Grouping basis",
            value=group_basis,
        ),
        DecisionEvidence(
            kind="minimum_member_count",
            label="Minimum member count",
            value=str(min_members),
        ),
        DecisionEvidence(
            kind="member_count",
            label="Member count",
            value=str(member_count),
        ),
        DecisionEvidence(
            kind="member_order_basis",
            label="Member order",
            value="deterministic_source_order",
        ),
        DecisionEvidence(
            kind="group_id",
            label="Legal rule group",
            value=group_id,
            id=group_id or None,
        ),
    ]
    for mid in member_ids:
        evidence.append(
            DecisionEvidence(
                kind="member_proposition_id",
                label="Group member",
                value=mid,
                id=mid,
            )
        )

    inputs = [
        DecisionInput(
            kind="source_fragment",
            label="Source fragment",
            value=source_fragment_id,
            id=source_fragment_id or None,
        ),
        DecisionInput(
            kind="canonical_locator",
            label="Canonical locator",
            value=canonical_locator,
        ),
    ]
    for mid in member_ids:
        inputs.append(
            DecisionInput(
                kind="member_proposition",
                label="Member proposition",
                value=mid,
                id=mid,
            )
        )

    material = _material_identity(
        rule.rule_id,
        rule.version,
        group_id,
        source_record_id,
        source_snapshot_id,
        source_fragment_id,
        ",".join(member_ids),
        outcome,
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.GROUPING.value,
        decision_type=DecisionType.GROUP.value,
        subject_kind=DecisionSubjectKind.LEGAL_RULE_GROUP.value,
        subject_id=group_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=outcome,
        material_input_identity=material,
    )
    locator_label = canonical_locator or "the shared source fragment"
    if member_count == 2:
        count_phrase = "these two propositions"
    else:
        count_phrase = f"these {member_count} propositions"
    summary = (
        f"Law Proposition Extractor grouped {count_phrase} because they were extracted from the "
        f"same source fragment ({locator_label}) and together represent the "
        "rules stated by that fragment. Grouping is structural (shared source "
        "fragment), not a claim that the propositions are inseparable in every "
        "legal context."
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.GROUPING,
        decision_type=DecisionType.GROUP,
        subject_kind=DecisionSubjectKind.LEGAL_RULE_GROUP,
        subject_id=group_id,
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
            "source_record_id": source_record_id,
            "source_snapshot_id": source_snapshot_id,
            "source_fragment_id": source_fragment_id,
            "canonical_locator": canonical_locator,
            "member_proposition_ids": list(member_ids),
            "member_count": member_count,
            "group_basis": group_basis,
            "minimum_member_count": min_members,
        },
    )
