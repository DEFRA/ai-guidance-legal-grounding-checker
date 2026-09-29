"""Emit provenance-stage DecisionExplanation records from captured facts.

Facts are captured at manifestation resolution (or projected from stored
snapshot fields). Explanation builders never re-parse CLML or re-resolve URLs.
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
    RULE_CLASSIFY_MANIFESTATION,
    RULE_PRESERVE_AS_OF_UNKNOWN,
    require_heuristic,
)
from .selection_explanations import (
    _material_identity,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

FACT_CLASSIFY_MANIFESTATION = "classify_manifestation"
FACT_PRESERVE_AS_OF_UNKNOWN = "preserve_as_of_unknown"


def _date_str(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    text = str(value).strip()
    return text


def manifestation_facts_from_snapshot(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project manifestation decision facts from a stored SourceSnapshot.

    Prefer facts captured at resolve time. Otherwise project from stored
    manifestation fields without re-parsing XML.
    """
    snap_id = str(snapshot.get("id") or "").strip()
    meta = snapshot.get("metadata")
    if isinstance(meta, Mapping):
        captured = meta.get("manifestation_decision_facts")
        if isinstance(captured, list) and captured:
            bound: list[dict[str, Any]] = []
            retrieved = _date_str(snapshot.get("retrieved_at")) or None
            for row in captured:
                if not isinstance(row, Mapping):
                    continue
                item = dict(row)
                if not item.get("source_snapshot_id"):
                    item["source_snapshot_id"] = snap_id
                if retrieved and not item.get("retrieved_at"):
                    item["retrieved_at"] = retrieved
                bound.append(item)
            return bound

    manifestation_type = str(snapshot.get("manifestation_type") or "unknown").strip() or "unknown"
    basis = str(snapshot.get("manifestation_basis") or "unavailable").strip() or "unavailable"
    requested_as_of = snapshot.get("requested_as_of_date")
    resolved_as_of = snapshot.get("resolved_as_of_date")
    revision = snapshot.get("source_revision_date")
    requested_url = None
    resolved_url = None
    evidence: list[Any] = list(snapshot.get("manifestation_evidence") or [])
    conflicts: list[str] = []
    if isinstance(meta, Mapping):
        man = meta.get("manifestation")
        if isinstance(man, Mapping):
            requested_url = man.get("requested_url")
            resolved_url = man.get("resolved_url")
            if man.get("evidence"):
                evidence = list(man.get("evidence") or [])
            if man.get("conflicts"):
                conflicts = [str(c) for c in (man.get("conflicts") or [])]
            if not evidence and snapshot.get("manifestation_evidence"):
                evidence = list(snapshot.get("manifestation_evidence") or [])

    facts: list[dict[str, Any]] = [
        {
            "fact_kind": FACT_CLASSIFY_MANIFESTATION,
            "source_snapshot_id": snap_id,
            "manifestation_type": manifestation_type,
            "manifestation_basis": basis,
            "outcome": f"classified_as_{manifestation_type}",
            "requested_manifestation": snapshot.get("requested_manifestation"),
            "resolved_manifestation": snapshot.get("resolved_manifestation"),
            "requested_as_of_date": _date_str(requested_as_of) or None,
            "resolved_as_of_date": _date_str(resolved_as_of) or None,
            "source_revision_date": _date_str(revision) or None,
            "retrieved_at": _date_str(snapshot.get("retrieved_at")) or None,
            "requested_url": requested_url or snapshot.get("source_url"),
            "resolved_url": resolved_url or snapshot.get("source_url"),
            "winning_evidence_basis": basis,
            "conflicts": conflicts,
            "evidence": evidence,
            "parser_version": "legislation_manifestation_v1",
        }
    ]
    if resolved_as_of is None and manifestation_type != "point_in_time":
        facts.append(
            {
                "fact_kind": FACT_PRESERVE_AS_OF_UNKNOWN,
                "source_snapshot_id": snap_id,
                "outcome": "legal_as_of_not_established",
                "manifestation_type": manifestation_type,
                "requested_as_of_date": None,
                "resolved_as_of_date": None,
                "source_revision_date": _date_str(revision) or None,
                "retrieved_at": _date_str(snapshot.get("retrieved_at")) or None,
                "requested_url": requested_url or snapshot.get("source_url"),
                "resolved_url": resolved_url or snapshot.get("source_url"),
                "note": (
                    "Retrieval and source revision dates are not treated "
                    "as the legal as-of date for this run."
                ),
            }
        )
    elif resolved_as_of is None and manifestation_type == "point_in_time":
        facts.append(
            {
                "fact_kind": FACT_PRESERVE_AS_OF_UNKNOWN,
                "source_snapshot_id": snap_id,
                "outcome": "legal_as_of_not_established",
                "manifestation_type": manifestation_type,
                "requested_as_of_date": _date_str(requested_as_of) or None,
                "resolved_as_of_date": None,
                "source_revision_date": _date_str(revision) or None,
                "retrieved_at": _date_str(snapshot.get("retrieved_at")) or None,
                "note": (
                    "Point-in-time manifestation lacked a resolved legal as-of "
                    "date; retrieval/revision were not substituted."
                ),
            }
        )
    return facts


def collect_manifestation_decision_facts(
    snapshots: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for snap in snapshots or []:
        if isinstance(snap, Mapping):
            facts.extend(manifestation_facts_from_snapshot(snap))
    return facts


def build_provenance_decision_explanations(
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
        if kind == FACT_CLASSIFY_MANIFESTATION:
            _add(_explain_classify_manifestation(fact))
        elif kind == FACT_PRESERVE_AS_OF_UNKNOWN:
            _add(_explain_preserve_as_of(fact))

    return sorted(
        explanations,
        key=lambda e: (e.subject_id, e.rule_id, e.id),
    )


def _explain_classify_manifestation(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_CLASSIFY_MANIFESTATION)
    snap_id = str(fact.get("source_snapshot_id") or "").strip()
    manifestation_type = str(fact.get("manifestation_type") or "unknown")
    basis = str(fact.get("manifestation_basis") or fact.get("winning_evidence_basis") or "unavailable")
    outcome = str(fact.get("outcome") or f"classified_as_{manifestation_type}")
    requested_as_of = fact.get("requested_as_of_date")
    resolved_as_of = fact.get("resolved_as_of_date")
    revision = fact.get("source_revision_date")
    conflicts = [str(c) for c in (fact.get("conflicts") or []) if str(c).strip()]

    evidence = [
        DecisionEvidence(
            kind="source_snapshot_id",
            label="Source snapshot",
            value=snap_id,
            id=snap_id or None,
        ),
        DecisionEvidence(
            kind="manifestation_type",
            label="Resolved manifestation",
            value=manifestation_type,
        ),
        DecisionEvidence(
            kind="winning_evidence_basis",
            label="Winning evidence basis",
            value=basis,
        ),
        DecisionEvidence(
            kind="requested_url",
            label="Requested URL",
            value=str(fact.get("requested_url") or "") or "(none)",
        ),
        DecisionEvidence(
            kind="resolved_url",
            label="Resolved URL",
            value=str(fact.get("resolved_url") or "") or "(none)",
        ),
        DecisionEvidence(
            kind="requested_as_of_date",
            label="Requested legal as-of",
            value=str(requested_as_of) if requested_as_of else "(not recorded)",
        ),
        DecisionEvidence(
            kind="resolved_as_of_date",
            label="Resolved legal as-of",
            value=str(resolved_as_of) if resolved_as_of else "(not recorded)",
        ),
        DecisionEvidence(
            kind="source_revision_date",
            label="Source revision date",
            value=str(revision) if revision else "(not recorded)",
        ),
    ]
    if fact.get("retrieved_at"):
        evidence.append(
            DecisionEvidence(
                kind="retrieved_at",
                label="Retrieval timestamp",
                value=str(fact.get("retrieved_at")),
            )
        )
    if fact.get("requested_manifestation"):
        evidence.append(
            DecisionEvidence(
                kind="requested_manifestation",
                label="Requested manifestation",
                value=str(fact.get("requested_manifestation")),
            )
        )
    if fact.get("parser_version"):
        evidence.append(
            DecisionEvidence(
                kind="parser_version",
                label="Parser version",
                value=str(fact.get("parser_version")),
            )
        )
    for item in fact.get("evidence") or []:
        if not isinstance(item, Mapping):
            continue
        evidence.append(
            DecisionEvidence(
                kind=str(item.get("kind") or "source_metadata"),
                label=str(item.get("field") or item.get("source_location") or "evidence"),
                value=str(item.get("value") or ""),
            )
        )
    for conflict in conflicts:
        evidence.append(
            DecisionEvidence(
                kind="conflict",
                label="Manifestation conflict",
                value=conflict,
            )
        )

    summary = (
        f"Law Proposition Extractor classified this consumed snapshot as {manifestation_type} "
        f"based on {basis.replace('_', ' ')}. "
        "This records how the authority labelled the text; it does not mean "
        "Law Proposition Extractor independently applied every amendment up to the source revision date."
    )
    if conflicts:
        summary += " Conflicting evidence was retained; classification remained conservative."

    material = _material_identity(
        snap_id,
        outcome,
        basis,
        str(requested_as_of or ""),
        str(resolved_as_of or ""),
        str(revision or ""),
    )
    return DecisionExplanation(
        id=decision_explanation_id(
            stage=DecisionStage.PROVENANCE.value,
            decision_type=DecisionType.CLASSIFY.value,
            subject_kind=DecisionSubjectKind.SOURCE_SNAPSHOT.value,
            subject_id=snap_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            material_input_identity=material,
        ),
        stage=DecisionStage.PROVENANCE,
        decision_type=DecisionType.CLASSIFY,
        subject_kind=DecisionSubjectKind.SOURCE_SNAPSHOT,
        subject_id=snap_id,
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
                    value=snap_id,
                    id=snap_id or None,
                )
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        confidence=None,
        diagnostics=conflicts,
        code_references=list(rule.code_references),
        trace_references=[],
        model_alias=None,
        prompt_version=None,
        metadata={
            "manifestation_type": manifestation_type,
            "manifestation_basis": basis,
            "requested_as_of_date": requested_as_of,
            "resolved_as_of_date": resolved_as_of,
            "source_revision_date": revision,
        },
    )


def _explain_preserve_as_of(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_PRESERVE_AS_OF_UNKNOWN)
    snap_id = str(fact.get("source_snapshot_id") or "").strip()
    outcome = str(fact.get("outcome") or "legal_as_of_not_established")
    revision = fact.get("source_revision_date")
    retrieved = fact.get("retrieved_at")

    evidence = [
        DecisionEvidence(
            kind="source_snapshot_id",
            label="Source snapshot",
            value=snap_id,
            id=snap_id or None,
        ),
        DecisionEvidence(
            kind="requested_as_of_date",
            label="Requested legal as-of",
            value="(not recorded)",
        ),
        DecisionEvidence(
            kind="resolved_as_of_date",
            label="Resolved legal as-of",
            value="(not recorded)",
        ),
        DecisionEvidence(
            kind="retrieved_at",
            label="Retrieval timestamp (operational)",
            value=str(retrieved) if retrieved else "(recorded separately when present)",
        ),
        DecisionEvidence(
            kind="source_revision_date",
            label="Source revision date (authority metadata)",
            value=str(revision) if revision else "(recorded separately when present)",
        ),
    ]

    summary = (
        "No legal as-of date was established by the consumed source request "
        "and metadata. Retrieval time is operational provenance and the source "
        "revision date is authority metadata; neither was treated as the legal "
        "as-of date for this run. This does not mean the text has no temporal "
        "legal meaning."
    )

    material = _material_identity(
        snap_id,
        outcome,
        str(fact.get("manifestation_type") or ""),
        str(revision or ""),
        str(retrieved or ""),
    )
    return DecisionExplanation(
        id=decision_explanation_id(
            stage=DecisionStage.PROVENANCE.value,
            decision_type=DecisionType.CLASSIFY.value,
            subject_kind=DecisionSubjectKind.SOURCE_SNAPSHOT.value,
            subject_id=snap_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            outcome=outcome,
            material_input_identity=material,
        ),
        stage=DecisionStage.PROVENANCE,
        decision_type=DecisionType.CLASSIFY,
        subject_kind=DecisionSubjectKind.SOURCE_SNAPSHOT,
        subject_id=snap_id,
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
                    value=snap_id,
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
        metadata={
            "legal_as_of_established": False,
            "manifestation_type": fact.get("manifestation_type"),
        },
    )
