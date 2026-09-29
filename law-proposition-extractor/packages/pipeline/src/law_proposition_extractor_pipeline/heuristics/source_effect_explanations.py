"""Emit source_effect-stage DecisionExplanation records from captured facts.

Parse/outstanding/consumption facts come from retained effect inventories and
reconciliation. Relevance facts come from capture_source_effect_relevance_facts.
Builders never re-parse CLML or re-match relevance.
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

from law_proposition_extractor_pipeline.source_effect_relevance import (
    FACT_EXCLUDE_UNRELATED,
    FACT_INHERIT_ANCESTOR,
    FACT_LINK_EXACT,
)

from .registry import (
    RULE_ASSESS_INDEPENDENT_CONSUMPTION,
    RULE_CLASSIFY_OUTSTANDING_STATUS,
    RULE_EXCLUDE_UNRELATED_FRAGMENT,
    RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR,
    RULE_LINK_EXACT_FRAGMENT,
    RULE_PARSE_AUTHORITY_ANNOTATION,
    require_heuristic,
)
from .selection_explanations import (
    _material_identity,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

FACT_PARSE = "parse_authority_annotation"
FACT_OUTSTANDING = "classify_outstanding_status"
FACT_CONSUMPTION = "assess_independent_consumption"

_CONSUMPTION_SUMMARIES = {
    "consumed_in_current_run": (
        "The affecting instrument was matched to a separate source record "
        "and snapshot consumed in this run. Independent consumption does not "
        "prove Law Proposition Extractor applied or verified the effect."
    ),
    "present_in_source_register_but_not_consumed": (
        "The instrument was identified in the run's source register but no "
        "snapshot was independently consumed."
    ),
    "not_matched": (
        "Law Proposition Extractor attempted a run-scoped identity match but found no matching "
        "consumed source. This does not mean the instrument does not exist."
    ),
    "not_assessed": (
        "The available identifiers or run inventory were insufficient to "
        "assess independent consumption; matching was not completed."
    ),
}

_OUTSTANDING_SUMMARIES = {
    "source_reports_present": (
        "The consumed source contains authority metadata reporting unapplied "
        "or outstanding effects. This is source-reported status, not a Law Proposition Extractor "
        "determination that the full amendment history is incomplete."
    ),
    "source_reports_none": (
        "The consumed source explicitly reports no outstanding unapplied "
        "effects in its UnappliedEffects metadata."
    ),
    "source_status_unknown": (
        "Outstanding-effects status was not established from the consumed "
        "source metadata (for example no UnappliedEffects block). This is "
        "unknown — not none — and revised manifestation does not imply none."
    ),
}


def collect_parse_and_outstanding_facts(
    *,
    effects_artifact: Mapping[str, Any] | None,
    snapshots: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Project parse + outstanding facts from retained inventories (no XML)."""
    facts: list[dict[str, Any]] = []
    if not isinstance(effects_artifact, Mapping):
        # Fall back to per-snapshot inventories.
        for snap in snapshots or []:
            if not isinstance(snap, Mapping):
                continue
            meta = snap.get("metadata")
            if not isinstance(meta, Mapping):
                continue
            inv = meta.get("source_legal_effects")
            if not isinstance(inv, Mapping):
                continue
            facts.extend(_facts_from_inventory(inv, snap_id=str(snap.get("id") or "")))
        return facts
    return _facts_from_inventory(effects_artifact, snap_id="")


def _facts_from_inventory(inv: Mapping[str, Any], *, snap_id: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    # Prefer pre-captured facts when present.
    meta = inv.get("metadata")
    if isinstance(meta, Mapping):
        captured = meta.get("decision_facts")
        if isinstance(captured, list) and captured:
            for row in captured:
                if isinstance(row, Mapping):
                    facts.append(dict(row))
            return facts

    for effect in inv.get("effects") or []:
        if not isinstance(effect, Mapping):
            continue
        effect_id = str(effect.get("id") or "").strip()
        if not effect_id:
            continue
        category = effect.get("effect_category")
        if hasattr(category, "value"):
            category = category.value
        facts.append(
            {
                "fact_kind": FACT_PARSE,
                "outcome": "authority_annotation_retained",
                "effect_id": effect_id,
                "source_snapshot_id": str(effect.get("source_snapshot_id") or snap_id or ""),
                "source_record_id": effect.get("source_record_id"),
                "annotation_id": effect.get("annotation_id"),
                "annotation_label": effect.get("annotation_label"),
                "effect_category": category,
                "affecting_instrument_uri": effect.get("affecting_instrument_uri"),
                "affecting_instrument_citation": effect.get("affecting_instrument_citation"),
                "affecting_instrument_title": effect.get("affecting_instrument_title"),
                "affected_locator": effect.get("affected_locator"),
                "effect_status": (
                    effect.get("effect_status").value
                    if hasattr(effect.get("effect_status"), "value")
                    else effect.get("effect_status")
                ),
                "source_representation_status": (
                    effect.get("source_representation_status").value
                    if hasattr(effect.get("source_representation_status"), "value")
                    else effect.get("source_representation_status")
                ),
                "parsing_basis": "clml_authority_annotation",
            }
        )

    outstanding = str(inv.get("outstanding_effects_status") or "source_status_unknown")
    # One outstanding fact per distinct snapshot in the inventory.
    snap_ids = sorted(
        {
            str(e.get("source_snapshot_id") or "").strip()
            for e in (inv.get("effects") or [])
            if isinstance(e, Mapping) and str(e.get("source_snapshot_id") or "").strip()
        }
        | ({snap_id} if snap_id else set())
    )
    if not snap_ids:
        snap_ids = [snap_id or ""]
    for sid in snap_ids:
        facts.append(
            {
                "fact_kind": FACT_OUTSTANDING,
                "outcome": outstanding,
                "source_snapshot_id": sid or None,
                "outstanding_effects_status": outstanding,
                "derivation": "authority_unapplied_effects_metadata",
            }
        )
    return facts


def collect_consumption_decision_facts(
    effects_artifact: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    if not isinstance(effects_artifact, Mapping):
        return facts
    for effect in effects_artifact.get("effects") or []:
        if not isinstance(effect, Mapping):
            continue
        effect_id = str(effect.get("id") or "").strip()
        if not effect_id:
            continue
        status = str(effect.get("independent_consumption_status") or "not_assessed")
        facts.append(
            {
                "fact_kind": FACT_CONSUMPTION,
                "outcome": status,
                "effect_id": effect_id,
                "source_snapshot_id": effect.get("source_snapshot_id"),
                "annotation_id": effect.get("annotation_id"),
                "annotation_label": effect.get("annotation_label"),
                "independent_consumption_status": status,
                "consumption_match_basis": effect.get("consumption_match_basis"),
                "matched_source_record_id": effect.get("matched_source_record_id"),
                "matched_source_snapshot_ids": list(
                    effect.get("matched_source_snapshot_ids") or []
                ),
                "matched_instrument_identity": effect.get("matched_instrument_identity"),
                "affecting_instrument_uri": effect.get("affecting_instrument_uri"),
                "affecting_instrument_citation": effect.get("affecting_instrument_citation"),
            }
        )
    return facts


def build_source_effect_decision_explanations(
    facts: Sequence[Mapping[str, Any]],
) -> list[DecisionExplanation]:
    explanations: list[DecisionExplanation] = []
    seen: set[str] = set()

    def _add(expl: DecisionExplanation) -> None:
        if expl.id in seen:
            return
        seen.add(expl.id)
        explanations.append(expl)

    for fact in facts:
        kind = str(fact.get("fact_kind") or "")
        if kind == FACT_PARSE:
            _add(_explain_parse(fact))
        elif kind == FACT_OUTSTANDING:
            _add(_explain_outstanding(fact))
        elif kind == FACT_CONSUMPTION:
            _add(_explain_consumption(fact))
        elif kind == FACT_LINK_EXACT:
            _add(_explain_link_exact(fact))
        elif kind == FACT_INHERIT_ANCESTOR:
            _add(_explain_inherit(fact))
        elif kind == FACT_EXCLUDE_UNRELATED:
            _add(_explain_exclude(fact))

    return sorted(
        explanations,
        key=lambda e: (e.stage.value, e.subject_id, e.rule_id, e.id),
    )


def _category_str(fact: Mapping[str, Any]) -> str:
    raw = fact.get("effect_category")
    if hasattr(raw, "value"):
        return str(raw.value)
    return str(raw or "unknown")


def _explain_parse(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_PARSE_AUTHORITY_ANNOTATION)
    effect_id = str(fact.get("effect_id") or "").strip()
    snap_id = str(fact.get("source_snapshot_id") or "").strip()
    annotation_id = str(fact.get("annotation_id") or "")
    label = str(fact.get("annotation_label") or "") or annotation_id or effect_id
    category = _category_str(fact)
    outcome = str(fact.get("outcome") or "authority_annotation_retained")

    evidence = [
        DecisionEvidence(kind="effect_id", label="Source legal effect", value=effect_id, id=effect_id),
        DecisionEvidence(kind="source_snapshot_id", label="Source snapshot", value=snap_id, id=snap_id or None),
        DecisionEvidence(kind="annotation_id", label="Authority annotation ID", value=annotation_id or "(none)"),
        DecisionEvidence(kind="annotation_label", label="Displayed label", value=label),
        DecisionEvidence(kind="effect_category", label="Category", value=category),
        DecisionEvidence(
            kind="affected_locator",
            label="Affected source locator",
            value=str(fact.get("affected_locator") or "(unresolved)"),
        ),
        DecisionEvidence(
            kind="parsing_basis",
            label="Parsing basis",
            value=str(fact.get("parsing_basis") or "clml_authority_annotation"),
        ),
    ]
    for key, title in (
        ("affecting_instrument_citation", "Affecting instrument citation"),
        ("affecting_instrument_uri", "Affecting instrument URI"),
        ("affecting_instrument_title", "Affecting instrument title"),
        ("effect_status", "Authority effect status"),
    ):
        if fact.get(key):
            evidence.append(DecisionEvidence(kind=key, label=title, value=str(fact.get(key))))

    summary = (
        f"Law Proposition Extractor retained authority annotation {label} ({category}) from the "
        f"consumed source snapshot. This is deterministic parsing of "
        f"authority-provided metadata — not independent legal analysis, not "
        f"confirmation that the effect is correctly applied, and not "
        f"confirmation that the affecting instrument was consumed."
    )

    material = _material_identity(
        effect_id,
        snap_id,
        category,
        annotation_id,
        str(fact.get("affecting_instrument_uri") or ""),
        str(fact.get("affecting_instrument_citation") or ""),
        outcome,
    )
    return DecisionExplanation(
        id=decision_explanation_id(
            stage=DecisionStage.SOURCE_EFFECT.value,
            decision_type=DecisionType.CLASSIFY.value,
            subject_kind=DecisionSubjectKind.SOURCE_LEGAL_EFFECT.value,
            subject_id=effect_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            material_input_identity=material,
        ),
        stage=DecisionStage.SOURCE_EFFECT,
        decision_type=DecisionType.CLASSIFY,
        subject_kind=DecisionSubjectKind.SOURCE_LEGAL_EFFECT,
        subject_id=effect_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="source_legal_effect",
                    label="Source legal effect",
                    value=effect_id,
                    id=effect_id,
                )
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        confidence=None,
        diagnostics=[],
        code_references=list(rule.code_references),
        trace_references=[],
        model_alias=None,
        prompt_version=None,
        metadata={
            "annotation_id": annotation_id,
            "annotation_label": label,
            "effect_category": category,
            "source_snapshot_id": snap_id,
        },
    )


def _explain_outstanding(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_CLASSIFY_OUTSTANDING_STATUS)
    status = str(
        fact.get("outstanding_effects_status") or fact.get("outcome") or "source_status_unknown"
    )
    snap_id = str(fact.get("source_snapshot_id") or "").strip()
    subject_id = snap_id or "source_legal_effects"
    outcome = status
    summary = _OUTSTANDING_SUMMARIES.get(status, _OUTSTANDING_SUMMARIES["source_status_unknown"])

    evidence = [
        DecisionEvidence(
            kind="outstanding_effects_status",
            label="Outstanding-effects status",
            value=status,
        ),
        DecisionEvidence(
            kind="derivation",
            label="Derivation",
            value=str(fact.get("derivation") or "authority_unapplied_effects_metadata"),
        ),
    ]
    if snap_id:
        evidence.append(
            DecisionEvidence(
                kind="source_snapshot_id",
                label="Source snapshot",
                value=snap_id,
                id=snap_id,
            )
        )

    material = _material_identity(subject_id, status, outcome)
    return DecisionExplanation(
        id=decision_explanation_id(
            stage=DecisionStage.SOURCE_EFFECT.value,
            decision_type=DecisionType.CLASSIFY.value,
            subject_kind=DecisionSubjectKind.SOURCE_SNAPSHOT.value,
            subject_id=subject_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            material_input_identity=material,
        ),
        stage=DecisionStage.SOURCE_EFFECT,
        decision_type=DecisionType.CLASSIFY,
        subject_kind=DecisionSubjectKind.SOURCE_SNAPSHOT,
        subject_id=subject_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="source_snapshot",
                    label="Source snapshot",
                    value=subject_id,
                    id=snap_id or None,
                )
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        confidence=None,
        diagnostics=[],
        code_references=list(rule.code_references),
        trace_references=[],
        model_alias=None,
        prompt_version=None,
        metadata={"outstanding_effects_status": status},
    )


def _explain_consumption(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_ASSESS_INDEPENDENT_CONSUMPTION)
    effect_id = str(fact.get("effect_id") or "").strip()
    status = str(
        fact.get("independent_consumption_status") or fact.get("outcome") or "not_assessed"
    )
    outcome = status
    basis = str(fact.get("consumption_match_basis") or "")
    summary = _CONSUMPTION_SUMMARIES.get(status, _CONSUMPTION_SUMMARIES["not_assessed"])

    evidence = [
        DecisionEvidence(kind="effect_id", label="Source legal effect", value=effect_id, id=effect_id),
        DecisionEvidence(
            kind="independent_consumption_status",
            label="Independent-consumption status",
            value=status,
        ),
    ]
    if basis:
        evidence.append(
            DecisionEvidence(kind="consumption_match_basis", label="Match basis", value=basis)
        )
    if fact.get("matched_instrument_identity"):
        evidence.append(
            DecisionEvidence(
                kind="matched_instrument_identity",
                label="Matched instrument identity",
                value=str(fact.get("matched_instrument_identity")),
            )
        )
    if fact.get("matched_source_record_id"):
        evidence.append(
            DecisionEvidence(
                kind="matched_source_record_id",
                label="Matched source record",
                value=str(fact.get("matched_source_record_id")),
                id=str(fact.get("matched_source_record_id")),
            )
        )
    for key, title in (
        ("affecting_instrument_citation", "Affecting instrument citation"),
        ("affecting_instrument_uri", "Affecting instrument URI"),
    ):
        if fact.get(key):
            evidence.append(DecisionEvidence(kind=key, label=title, value=str(fact.get(key))))

    material = _material_identity(
        effect_id,
        status,
        basis,
        str(fact.get("matched_instrument_identity") or ""),
        str(fact.get("affecting_instrument_uri") or ""),
        str(fact.get("affecting_instrument_citation") or ""),
        outcome,
    )
    return DecisionExplanation(
        id=decision_explanation_id(
            stage=DecisionStage.SOURCE_EFFECT.value,
            decision_type=DecisionType.ASSESS.value,
            subject_kind=DecisionSubjectKind.SOURCE_LEGAL_EFFECT.value,
            subject_id=effect_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            material_input_identity=material,
        ),
        stage=DecisionStage.SOURCE_EFFECT,
        decision_type=DecisionType.ASSESS,
        subject_kind=DecisionSubjectKind.SOURCE_LEGAL_EFFECT,
        subject_id=effect_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="source_legal_effect",
                    label="Source legal effect",
                    value=effect_id,
                    id=effect_id,
                )
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        confidence=None,
        diagnostics=[],
        code_references=list(rule.code_references),
        trace_references=[],
        model_alias=None,
        prompt_version=None,
        metadata={
            "independent_consumption_status": status,
            "consumption_match_basis": basis or None,
            "source_snapshot_id": fact.get("source_snapshot_id"),
        },
    )


def _explain_link_exact(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_LINK_EXACT_FRAGMENT)
    stmt_id = str(fact.get("effective_law_statement_id") or "").strip()
    effect_id = str(fact.get("effect_id") or "").strip()
    outcome = str(fact.get("outcome") or "source_effect_relevant")
    label = str(fact.get("annotation_label") or fact.get("annotation_id") or effect_id)
    locator = str(fact.get("linked_locator") or fact.get("affected_locator") or "")

    evidence = [
        DecisionEvidence(
            kind="effective_law_statement_id",
            label="Receiving statement",
            value=stmt_id,
            id=stmt_id,
        ),
        DecisionEvidence(kind="effect_id", label="Source legal effect", value=effect_id, id=effect_id),
        DecisionEvidence(
            kind="relevance_basis",
            label="Relevance basis",
            value="exact_fragment",
        ),
        DecisionEvidence(
            kind="linked_fragment_id",
            label="Linked fragment",
            value=str(fact.get("linked_fragment_id") or ""),
            id=str(fact.get("linked_fragment_id") or "") or None,
        ),
        DecisionEvidence(
            kind="linked_locator",
            label="Linked locator",
            value=locator or "(none)",
        ),
        DecisionEvidence(
            kind="source_snapshot_id",
            label="Source snapshot",
            value=str(fact.get("source_snapshot_id") or ""),
            id=str(fact.get("source_snapshot_id") or "") or None,
        ),
    ]
    if fact.get("effect_link_id"):
        evidence.append(
            DecisionEvidence(
                kind="effect_link_id",
                label="Effect link",
                value=str(fact.get("effect_link_id")),
                id=str(fact.get("effect_link_id")),
            )
        )

    summary = (
        f"Source annotation {label} is linked directly to {locator or 'this fragment'}, "
        f"so it is shown for this statement. Exact-fragment relevance is not inheritance "
        f"and does not prove Law Proposition Extractor independently applied or verified the affecting instrument."
    )

    material = _material_identity(
        stmt_id,
        effect_id,
        "exact_fragment",
        str(fact.get("linked_fragment_id") or ""),
        locator,
        outcome,
    )
    return DecisionExplanation(
        id=decision_explanation_id(
            stage=DecisionStage.SOURCE_EFFECT.value,
            decision_type=DecisionType.LINK.value,
            subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT.value,
            subject_id=stmt_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            material_input_identity=material,
        ),
        stage=DecisionStage.SOURCE_EFFECT,
        decision_type=DecisionType.LINK,
        subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT,
        subject_id=stmt_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="effective_law_statement",
                    label="Receiving statement",
                    value=stmt_id,
                    id=stmt_id,
                ),
                DecisionInput(
                    kind="source_legal_effect",
                    label="Source legal effect",
                    value=effect_id,
                    id=effect_id,
                ),
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        confidence=None,
        diagnostics=[],
        code_references=list(rule.code_references),
        trace_references=[],
        model_alias=None,
        prompt_version=None,
        metadata={
            "effect_id": effect_id,
            "relevance_basis": "exact_fragment",
            "annotation_label": label,
            "source_snapshot_id": fact.get("source_snapshot_id"),
        },
    )


def _explain_inherit(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_INHERIT_FROM_STRUCTURAL_ANCESTOR)
    stmt_id = str(fact.get("effective_law_statement_id") or "").strip()
    effect_id = str(fact.get("effect_id") or "").strip()
    outcome = str(fact.get("outcome") or "source_effect_relevant")
    label = str(fact.get("annotation_label") or fact.get("annotation_id") or effect_id)
    ancestor = str(fact.get("ancestor_locator") or "")
    descendant = str(fact.get("descendant_locator") or "")

    evidence = [
        DecisionEvidence(
            kind="effective_law_statement_id",
            label="Receiving statement",
            value=stmt_id,
            id=stmt_id,
        ),
        DecisionEvidence(kind="effect_id", label="Source legal effect", value=effect_id, id=effect_id),
        DecisionEvidence(
            kind="relevance_basis",
            label="Relevance basis",
            value="structural_ancestor",
        ),
        DecisionEvidence(
            kind="ancestor_fragment_id",
            label="Ancestor fragment",
            value=str(fact.get("ancestor_fragment_id") or ""),
            id=str(fact.get("ancestor_fragment_id") or "") or None,
        ),
        DecisionEvidence(
            kind="ancestor_locator",
            label="Ancestor locator",
            value=ancestor or "(none)",
        ),
        DecisionEvidence(
            kind="descendant_fragment_id",
            label="Descendant fragment",
            value=str(fact.get("descendant_fragment_id") or ""),
            id=str(fact.get("descendant_fragment_id") or "") or None,
        ),
        DecisionEvidence(
            kind="descendant_locator",
            label="Descendant locator",
            value=descendant or "(none)",
        ),
        DecisionEvidence(
            kind="source_snapshot_id",
            label="Source snapshot",
            value=str(fact.get("source_snapshot_id") or ""),
            id=str(fact.get("source_snapshot_id") or "") or None,
        ),
    ]
    path = fact.get("validated_parent_path") or []
    if isinstance(path, list) and path:
        evidence.append(
            DecisionEvidence(
                kind="validated_parent_path",
                label="Validated parent path",
                value=" → ".join(str(p) for p in path),
            )
        )

    summary = (
        f"This annotation ({label}) is attached to {ancestor or 'an ancestor provision'} "
        f"as a whole, so it is also shown for propositions extracted from "
        f"{descendant or 'descendant paragraphs'} within that structure. "
        f"This does not mean the effect necessarily modifies every proposition identically, "
        f"and it does not prove Law Proposition Extractor independently applied or verified the affecting instrument."
    )

    material = _material_identity(
        stmt_id,
        effect_id,
        "structural_ancestor",
        str(fact.get("ancestor_fragment_id") or ""),
        ancestor,
        descendant,
        outcome,
    )
    return DecisionExplanation(
        id=decision_explanation_id(
            stage=DecisionStage.SOURCE_EFFECT.value,
            decision_type=DecisionType.INHERIT.value,
            subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT.value,
            subject_id=stmt_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            material_input_identity=material,
        ),
        stage=DecisionStage.SOURCE_EFFECT,
        decision_type=DecisionType.INHERIT,
        subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT,
        subject_id=stmt_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="effective_law_statement",
                    label="Receiving statement",
                    value=stmt_id,
                    id=stmt_id,
                ),
                DecisionInput(
                    kind="source_legal_effect",
                    label="Source legal effect",
                    value=effect_id,
                    id=effect_id,
                ),
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        confidence=None,
        diagnostics=[],
        code_references=list(rule.code_references),
        trace_references=[],
        model_alias=None,
        prompt_version=None,
        metadata={
            "effect_id": effect_id,
            "relevance_basis": "structural_ancestor",
            "annotation_label": label,
            "ancestor_locator": ancestor,
            "source_snapshot_id": fact.get("source_snapshot_id"),
        },
    )


def _explain_exclude(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_EXCLUDE_UNRELATED_FRAGMENT)
    stmt_id = str(fact.get("effective_law_statement_id") or "").strip()
    effect_id = str(fact.get("effect_id") or "").strip()
    outcome = str(fact.get("outcome") or "source_effect_excluded")
    effect_root = str(fact.get("effect_root_provision") or fact.get("effect_fragment_locator") or "")
    receiving_root = str(fact.get("receiving_root_provision") or "")
    reason = str(fact.get("reason") or "")

    evidence = [
        DecisionEvidence(
            kind="effective_law_statement_id",
            label="Receiving statement",
            value=stmt_id,
            id=stmt_id,
        ),
        DecisionEvidence(kind="effect_id", label="Source legal effect", value=effect_id, id=effect_id),
        DecisionEvidence(
            kind="relevance_basis",
            label="Relevance basis",
            value="unrelated_fragment",
        ),
        DecisionEvidence(
            kind="effect_fragment_locator",
            label="Effect provision locator",
            value=str(fact.get("effect_fragment_locator") or effect_root),
        ),
        DecisionEvidence(
            kind="receiving_locator",
            label="Receiving locator",
            value=str(fact.get("receiving_locator") or ""),
        ),
        DecisionEvidence(
            kind="structural_boundary",
            label="Structural boundary",
            value=reason
            or f"{effect_root} is not a structural ancestor of {receiving_root}",
        ),
        DecisionEvidence(
            kind="source_snapshot_id",
            label="Source snapshot",
            value=str(fact.get("source_snapshot_id") or ""),
            id=str(fact.get("source_snapshot_id") or "") or None,
        ),
    ]

    summary = (
        f"{effect_root or 'The effect provision'} is not a structural ancestor of "
        f"{receiving_root or 'the receiving provision'}. Therefore this source "
        f"annotation is not relevant to propositions from that branch."
    )

    material = _material_identity(
        stmt_id,
        effect_id,
        "unrelated_fragment",
        effect_root,
        receiving_root,
        outcome,
    )
    return DecisionExplanation(
        id=decision_explanation_id(
            stage=DecisionStage.SOURCE_EFFECT.value,
            decision_type=DecisionType.EXCLUDE.value,
            subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT.value,
            subject_id=stmt_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            material_input_identity=material,
        ),
        stage=DecisionStage.SOURCE_EFFECT,
        decision_type=DecisionType.EXCLUDE,
        subject_kind=DecisionSubjectKind.EFFECTIVE_LAW_STATEMENT,
        subject_id=stmt_id,
        outcome=outcome,
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=summary,
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="effective_law_statement",
                    label="Receiving statement",
                    value=stmt_id,
                    id=stmt_id,
                ),
                DecisionInput(
                    kind="source_legal_effect",
                    label="Source legal effect",
                    value=effect_id,
                    id=effect_id,
                ),
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        confidence=None,
        diagnostics=[],
        code_references=list(rule.code_references),
        trace_references=[],
        model_alias=None,
        prompt_version=None,
        metadata={
            "effect_id": effect_id,
            "relevance_basis": "unrelated_fragment",
            "effect_root_provision": effect_root,
            "receiving_root_provision": receiving_root,
            "source_snapshot_id": fact.get("source_snapshot_id"),
        },
    )
