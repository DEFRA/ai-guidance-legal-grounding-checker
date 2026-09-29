"""Emit structured-list DecisionExplanation records from reconciliation facts.

Emission policy
---------------
Decision facts are captured at the structured-list merge/reconcile site (not
reconstructed later). Retained composition decisions are bound to final opaque
proposition IDs after proposition construction — the heuristic is not rerun.

Method is always deterministic for these rules: LLM rows may supply candidate
content, but association, composition, and duplicate reconciliation are
deterministic.
"""

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
    DecisionTraceReference,
    HeuristicMethod,
    Proposition,
    SuppressedDecisionItem,
)

from .registry import (
    RULE_COMPOSE_TERMINAL_LEAF,
    RULE_PRESERVE_DISTINCT_TERMINAL_CLAIMS,
    RULE_REJECT_NON_TERMINAL_ROW,
    RULE_SUPPRESS_DUPLICATE_TERMINAL,
    require_heuristic,
)
from .selection_explanations import (
    _material_identity,
    _sorted_alternatives,
    _sorted_evidence,
    _sorted_inputs,
    decision_explanation_id,
)

FACT_COMPOSE = "compose_terminal_leaf"
FACT_SUPPRESS = "suppress_duplicate_terminal"
FACT_PRESERVE = "preserve_distinct_terminal_claims"
FACT_REJECT = "reject_non_terminal_row"

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


def _sorted_components(components: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    rows = [dict(c) for c in (components or []) if isinstance(c, Mapping)]
    role_rank = {"stem": 0, "branch": 1, "leaf": 2}
    return sorted(
        rows,
        key=lambda c: (
            role_rank.get(str(c.get("role") or ""), 9),
            str(c.get("locator_suffix") or ""),
            str(c.get("text") or "")[:64],
        ),
    )


def _component_roles(components: Sequence[Mapping[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"stem": [], "branch": [], "leaf": []}
    for c in _sorted_components(components):
        role = str(c.get("role") or "")
        if role in out:
            out[role].append(c)
    return out


def _path_label(path: str) -> str:
    return str(path or "").strip() or "(unknown)"


def _compose_summary(*, path: str, components: Sequence[Mapping[str, Any]] | None) -> str:
    roles = _component_roles(components)
    path_l = _path_label(path)
    has_stem = bool(roles["stem"])
    has_branch = bool(roles["branch"])
    has_leaf = bool(roles["leaf"])
    parts: list[str] = []
    if has_stem:
        parts.append("the governing stem")
    if has_branch:
        branch_suffix = str(roles["branch"][0].get("locator_suffix") or "")
        marker = branch_suffix.split(":")[-1].strip("()") if branch_suffix else ""
        parts.append(f"branch ({marker})" if marker else "the intermediate branch")
    if has_leaf:
        leaf_suffix = str(roles["leaf"][0].get("locator_suffix") or "")
        leaf_marker = leaf_suffix.split(":")[-1].strip("()") if leaf_suffix else ""
        parts.append(
            f"terminal point ({leaf_marker})" if leaf_marker else "the terminal leaf"
        )
    if not parts:
        joined = "its source components"
    elif len(parts) == 1:
        joined = parts[0]
    elif len(parts) == 2:
        joined = f"{parts[0]} and {parts[1]}"
    else:
        joined = f"{', '.join(parts[:-1])}, and {parts[-1]}"
    return (
        f"This proposition represents terminal path {path_l}. Law Proposition Extractor combined "
        f"{joined} so the rule can be read as one operative derogation."
    )


def _suppress_summary(*, path: str) -> str:
    return (
        f"This extraction candidate was suppressed because it duplicated another "
        f"candidate for terminal path {_path_label(path)}. The retained candidate "
        f"had the stronger canonical structured-list locator and tighter "
        f"source-aligned evidence."
    )


def _preserve_summary(*, path: str) -> str:
    return (
        f"Law Proposition Extractor could not safely establish that these candidates for terminal "
        f"path {_path_label(path)} expressed the same operative claim, so both "
        f"were retained for review."
    )


def _reject_summary(*, component_role: str, associated_paths: Sequence[str]) -> str:
    role = str(component_role or "non_terminal").replace("_", "-")
    paths = ", ".join(_path_label(p) for p in associated_paths) or "terminal propositions beneath it"
    if role == "branch":
        return (
            "This branch-only candidate was not retained as a standalone "
            f"proposition. Its legal context is incorporated into the terminal "
            f"propositions beneath the branch ({paths})."
        )
    if role == "stem":
        return (
            "This stem-only candidate was not retained as a standalone "
            f"proposition. Its legal context is incorporated into the terminal "
            f"propositions ({paths})."
        )
    return (
        f"This {role}-only candidate was not retained as a standalone "
        f"proposition. Its legal context is incorporated into {paths}."
    )


def _evidence_from_mapping(items: Sequence[Mapping[str, Any]] | None) -> list[DecisionEvidence]:
    out: list[DecisionEvidence] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        out.append(
            DecisionEvidence(
                kind=kind,
                label=str(item["label"]) if item.get("label") is not None else None,
                value=str(item["value"]) if item.get("value") is not None else None,
                id=str(item["id"]) if item.get("id") is not None else None,
            )
        )
    return out


def _inputs_from_mapping(items: Sequence[Mapping[str, Any]] | None) -> list[DecisionInput]:
    out: list[DecisionInput] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        out.append(
            DecisionInput(
                kind=kind,
                label=str(item["label"]) if item.get("label") is not None else None,
                value=str(item["value"]) if item.get("value") is not None else None,
                id=str(item["id"]) if item.get("id") is not None else None,
            )
        )
    return out


def _prop_by_candidate_id(
    propositions: Sequence[Proposition | Mapping[str, Any]],
) -> dict[str, str]:
    """Map extraction_candidate_id → final proposition id."""
    out: dict[str, str] = {}
    for prop in propositions:
        if isinstance(prop, Proposition):
            meta = prop.extraction_debug_meta if isinstance(prop.extraction_debug_meta, dict) else {}
            prop_id = str(prop.id)
        else:
            meta = prop.get("extraction_debug_meta") if isinstance(prop.get("extraction_debug_meta"), dict) else {}
            prop_id = str(prop.get("id") or "")
        cand = str((meta or {}).get("extraction_candidate_id") or "").strip()
        if cand and prop_id:
            out[cand] = prop_id
    return out


def bind_structured_list_decision_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    propositions: Sequence[Proposition | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach final proposition IDs onto captured facts (no heuristic rerun)."""
    by_cand = _prop_by_candidate_id(propositions)
    bound: list[dict[str, Any]] = []
    for raw in facts:
        fact = dict(raw)
        kind = str(fact.get("fact_kind") or "")
        retained_cand = str(fact.get("retained_candidate_id") or "").strip()
        if retained_cand and retained_cand in by_cand:
            fact["retained_proposition_id"] = by_cand[retained_cand]
        if kind == FACT_COMPOSE:
            cand = str(fact.get("candidate_id") or "").strip()
            if cand and cand in by_cand:
                fact["proposition_id"] = by_cand[cand]
                fact["retained_proposition_id"] = by_cand[cand]
        if kind == FACT_PRESERVE:
            mapped = [
                by_cand[cid]
                for cid in (fact.get("candidate_ids") or [])
                if isinstance(cid, str) and cid in by_cand
            ]
            if mapped:
                fact["retained_proposition_ids"] = mapped
        bound.append(fact)
    return bound


def build_structured_list_decision_explanations(
    facts: Sequence[Mapping[str, Any]],
) -> list[DecisionExplanation]:
    """Map captured structured-list decision facts to DecisionExplanation records."""
    explanations: list[DecisionExplanation] = []
    seen: set[str] = set()

    def _add(expl: DecisionExplanation) -> None:
        if expl.id in seen:
            return
        seen.add(expl.id)
        explanations.append(expl)

    for fact in facts:
        kind = str(fact.get("fact_kind") or "")
        if kind == FACT_COMPOSE:
            _add(_explain_compose(fact))
        elif kind == FACT_SUPPRESS:
            _add(_explain_suppress(fact))
        elif kind == FACT_PRESERVE:
            _add(_explain_preserve(fact))
        elif kind == FACT_REJECT:
            _add(_explain_reject(fact))

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


def _explain_compose(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_COMPOSE_TERMINAL_LEAF)
    path = str(fact.get("structured_list_path") or "")
    components = _sorted_components(fact.get("source_component_locators"))
    roles = _component_roles(components)
    prop_id = str(fact.get("proposition_id") or fact.get("retained_proposition_id") or "").strip()
    cand_id = str(fact.get("candidate_id") or "").strip()
    subject_id = prop_id or cand_id
    subject_kind = (
        DecisionSubjectKind.PROPOSITION if prop_id else DecisionSubjectKind.EXTRACTION_CANDIDATE
    )
    origin = str(fact.get("candidate_origin") or "llm")
    evidence = [
        DecisionEvidence(kind="structured_list_path", label="Structured-list path", value=path),
        DecisionEvidence(
            kind="composition_basis",
            label="Composition basis",
            value=str(fact.get("composition_basis") or "structured_list_leaf"),
        ),
        DecisionEvidence(kind="candidate_origin", label="Candidate origin", value=origin),
        DecisionEvidence(
            kind="retained_outcome",
            label="Retained outcome",
            value=str(fact.get("outcome") or "retained_as_terminal_proposition"),
        ),
    ]
    if fact.get("source_record_id"):
        evidence.append(
            DecisionEvidence(
                kind="source_record_id",
                label="Source record",
                value=str(fact["source_record_id"]),
            )
        )
    if fact.get("source_snapshot_id"):
        evidence.append(
            DecisionEvidence(
                kind="source_snapshot_id",
                label="Source snapshot",
                value=str(fact["source_snapshot_id"]),
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
    for role_name, items in roles.items():
        for item in items:
            evidence.append(
                DecisionEvidence(
                    kind=f"component_{role_name}",
                    label=f"{role_name.title()} component",
                    value=str(item.get("locator_suffix") or ""),
                    id=str(item.get("locator_suffix") or "") or None,
                )
            )
            # Short quote already retained by extraction — do not dump full paragraph.
            text = str(item.get("text") or "").strip()
            if text:
                evidence.append(
                    DecisionEvidence(
                        kind=f"component_{role_name}_quote",
                        label=f"{role_name.title()} quote",
                        value=text[:160],
                    )
                )
    for loc in components:
        evidence.append(
            DecisionEvidence(
                kind="source_component_locator",
                label="Source component locator",
                value=str(loc.get("locator_suffix") or ""),
            )
        )
    if cand_id:
        evidence.append(
            DecisionEvidence(
                kind="extraction_candidate_id",
                label="Extraction candidate",
                value=cand_id,
                id=cand_id,
            )
        )
    inputs = [
        DecisionInput(kind="structured_list_path", label="Path", value=path),
        DecisionInput(kind="candidate_origin", label="Origin", value=origin),
    ]
    if fact.get("base_locator"):
        inputs.append(
            DecisionInput(
                kind="base_locator",
                label="Fragment locator",
                value=str(fact["base_locator"]),
            )
        )
    traces: list[DecisionTraceReference] = []
    if fact.get("llm_call_trace_id"):
        traces.append(
            DecisionTraceReference(
                kind="llm_call_trace",
                id=str(fact["llm_call_trace_id"]),
                label="Frontier extraction call",
            )
        )
    material = _material_identity(
        RULE_COMPOSE_TERMINAL_LEAF,
        path,
        cand_id,
        prop_id,
        str(fact.get("source_record_id") or ""),
        str(fact.get("source_snapshot_id") or ""),
        str(fact.get("source_fragment_id") or ""),
        *(str(c.get("locator_suffix") or "") for c in components),
        str(fact.get("outcome") or "retained_as_terminal_proposition"),
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.EXTRACTION.value,
        decision_type=DecisionType.RETAIN.value,
        subject_kind=subject_kind.value,
        subject_id=subject_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome=str(fact.get("outcome") or "retained_as_terminal_proposition"),
        material_input_identity=material,
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.EXTRACTION,
        decision_type=DecisionType.RETAIN,
        subject_kind=subject_kind,
        subject_id=subject_id,
        outcome=str(fact.get("outcome") or "retained_as_terminal_proposition"),
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=_compose_summary(path=path, components=components),
        inputs=_sorted_inputs(inputs),
        evidence=_sorted_evidence(evidence),
        alternatives=[],
        suppressed_items=[],
        diagnostics=[],
        code_references=list(rule.code_references),
        trace_references=traces,
        prompt_version=str(fact["prompt_version"]) if fact.get("prompt_version") else None,
        model_alias=str(fact["model_alias"]) if fact.get("model_alias") else None,
        metadata={
            "structured_list_path": path,
            "candidate_origin": origin,
            "composition_basis": str(fact.get("composition_basis") or "structured_list_leaf"),
            "extraction_candidate_id": cand_id or None,
            "llm_content_proposed": origin in {"llm", "reconciled_llm_and_draft"},
            "structural_decision_method": "deterministic",
        },
    )


def _explain_suppress(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_SUPPRESS_DUPLICATE_TERMINAL)
    path = str(fact.get("structured_list_path") or "")
    suppressed_id = str(fact.get("suppressed_candidate_id") or "")
    retained_id = str(fact.get("retained_candidate_id") or "")
    retained_prop = str(fact.get("retained_proposition_id") or "").strip()
    basis = str(fact.get("duplicate_basis") or "")
    factors = [str(f) for f in (fact.get("winner_selection_factors") or []) if str(f)]
    evidence = [
        DecisionEvidence(kind="structured_list_path", label="Structured-list path", value=path),
        DecisionEvidence(
            kind="duplicate_basis",
            label="Duplicate basis",
            value=basis,
        ),
        DecisionEvidence(
            kind="retained_candidate_id",
            label="Retained candidate",
            value=retained_id,
            id=retained_id,
        ),
        DecisionEvidence(
            kind="suppressed_candidate_id",
            label="Suppressed candidate",
            value=suppressed_id,
            id=suppressed_id,
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
    for factor in sorted(set(factors)):
        evidence.append(
            DecisionEvidence(
                kind="winner_selection_factor",
                label="Winner selection factor",
                value=factor,
            )
        )
    evidence.extend(_evidence_from_mapping(fact.get("extra_evidence")))
    material = _material_identity(
        RULE_SUPPRESS_DUPLICATE_TERMINAL,
        path,
        retained_id,
        suppressed_id,
        basis,
        *sorted(factors),
        str(fact.get("source_record_id") or ""),
        str(fact.get("source_snapshot_id") or ""),
        str(fact.get("source_fragment_id") or ""),
        "suppressed_as_duplicate_terminal",
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.EXTRACTION.value,
        decision_type=DecisionType.SUPPRESS.value,
        subject_kind=DecisionSubjectKind.EXTRACTION_CANDIDATE.value,
        subject_id=suppressed_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome="suppressed_as_duplicate_terminal",
        material_input_identity=material,
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.EXTRACTION,
        decision_type=DecisionType.SUPPRESS,
        subject_kind=DecisionSubjectKind.EXTRACTION_CANDIDATE,
        subject_id=suppressed_id,
        outcome="suppressed_as_duplicate_terminal",
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=_suppress_summary(path=path),
        inputs=_sorted_inputs(
            [
                DecisionInput(kind="structured_list_path", label="Path", value=path),
                DecisionInput(
                    kind="extraction_candidate",
                    label="Suppressed candidate",
                    value=suppressed_id,
                    id=suppressed_id,
                ),
            ]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=_sorted_alternatives(
            [
                DecisionAlternative(
                    kind="extraction_candidate",
                    id=retained_id,
                    label="Retained duplicate winner",
                    value=retained_id,
                    role="retained_winner",
                )
            ]
        ),
        suppressed_items=[
            SuppressedDecisionItem(
                kind="extraction_candidate",
                id=suppressed_id,
                reason=basis or "duplicate_structured_list_terminal",
                label="Suppressed duplicate terminal candidate",
            )
        ],
        diagnostics=["structured_list_terminal_duplicate_suppressed"],
        code_references=list(rule.code_references),
        metadata={
            "structured_list_path": path,
            "duplicate_basis": basis,
            "winner_selection_factors": sorted(set(factors)),
            "retained_candidate_id": retained_id,
            "retained_proposition_id": retained_prop or None,
            "diagnostic_code": "structured_list_terminal_duplicate_suppressed",
        },
    )


def _explain_preserve(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_PRESERVE_DISTINCT_TERMINAL_CLAIMS)
    path = str(fact.get("structured_list_path") or "")
    candidate_ids = sorted(
        {str(c) for c in (fact.get("candidate_ids") or []) if str(c).strip()}
    )
    subject_id = candidate_ids[0] if candidate_ids else f"path:{path}"
    evidence = [
        DecisionEvidence(kind="structured_list_path", label="Structured-list path", value=path),
        DecisionEvidence(
            kind="preserve_reason",
            label="Preserve reason",
            value=str(
                fact.get("preserve_reason")
                or "safe_duplicate_suppression_not_established"
            ),
        ),
    ]
    for cid in candidate_ids:
        evidence.append(
            DecisionEvidence(
                kind="extraction_candidate_id",
                label="Retained candidate",
                value=cid,
                id=cid,
            )
        )
    for prop_id in fact.get("retained_proposition_ids") or []:
        evidence.append(
            DecisionEvidence(
                kind="retained_proposition_id",
                label="Retained proposition",
                value=str(prop_id),
                id=str(prop_id),
            )
        )
    alts = [
        DecisionAlternative(
            kind="extraction_candidate",
            id=cid,
            label="Preserved same-path candidate",
            value=cid,
            role="preserved_distinct_claim",
        )
        for cid in candidate_ids
    ]
    material = _material_identity(
        RULE_PRESERVE_DISTINCT_TERMINAL_CLAIMS,
        path,
        *candidate_ids,
        "retained_distinct_same_path_claims",
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.EXTRACTION.value,
        decision_type=DecisionType.DIAGNOSE.value,
        subject_kind=DecisionSubjectKind.EXTRACTION_CANDIDATE.value,
        subject_id=subject_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome="retained_distinct_same_path_claims",
        material_input_identity=material,
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.EXTRACTION,
        decision_type=DecisionType.DIAGNOSE,
        subject_kind=DecisionSubjectKind.EXTRACTION_CANDIDATE,
        subject_id=subject_id,
        outcome="retained_distinct_same_path_claims",
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=_preserve_summary(path=path),
        inputs=_sorted_inputs(
            [DecisionInput(kind="structured_list_path", label="Path", value=path)]
        ),
        evidence=_sorted_evidence(evidence),
        alternatives=_sorted_alternatives(alts),
        diagnostics=["structured_list_path_multiple_distinct_propositions"],
        code_references=list(rule.code_references),
        metadata={
            "structured_list_path": path,
            "candidate_ids": candidate_ids,
            "diagnostic_code": "structured_list_path_multiple_distinct_propositions",
        },
    )


def _explain_reject(fact: Mapping[str, Any]) -> DecisionExplanation:
    rule = require_heuristic(RULE_REJECT_NON_TERMINAL_ROW)
    cand_id = str(fact.get("candidate_id") or "")
    role = str(fact.get("component_role") or "non_terminal")
    paths = sorted({str(p) for p in (fact.get("associated_terminal_paths") or []) if str(p)})
    evidence = [
        DecisionEvidence(kind="component_role", label="Component role", value=role),
        DecisionEvidence(
            kind="rejection_reason",
            label="Rejection reason",
            value=str(fact.get("rejection_reason") or "represented_through_terminal_compositions"),
        ),
    ]
    for path in paths:
        evidence.append(
            DecisionEvidence(
                kind="associated_terminal_path",
                label="Associated terminal path",
                value=path,
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
        RULE_REJECT_NON_TERMINAL_ROW,
        cand_id,
        role,
        *paths,
        "not_retained_as_standalone_proposition",
    )
    expl_id = decision_explanation_id(
        stage=DecisionStage.EXTRACTION.value,
        decision_type=DecisionType.EXCLUDE.value,
        subject_kind=DecisionSubjectKind.EXTRACTION_CANDIDATE.value,
        subject_id=cand_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        outcome="not_retained_as_standalone_proposition",
        material_input_identity=material,
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.EXTRACTION,
        decision_type=DecisionType.EXCLUDE,
        subject_kind=DecisionSubjectKind.EXTRACTION_CANDIDATE,
        subject_id=cand_id,
        outcome="not_retained_as_standalone_proposition",
        method=HeuristicMethod.DETERMINISTIC,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        summary=_reject_summary(component_role=role, associated_paths=paths),
        inputs=_sorted_inputs(
            [
                DecisionInput(
                    kind="extraction_candidate",
                    label="Rejected candidate",
                    value=cand_id,
                    id=cand_id,
                )
            ]
        ),
        evidence=_sorted_evidence(evidence),
        diagnostics=[],
        code_references=list(rule.code_references),
        metadata={
            "component_role": role,
            "associated_terminal_paths": paths,
        },
    )


def merge_decision_explanation_lists(
    *groups: Sequence[DecisionExplanation],
) -> list[DecisionExplanation]:
    """Deterministic merge across stages; dedupe by explanation id."""
    seen: set[str] = set()
    merged: list[DecisionExplanation] = []
    for group in groups:
        for expl in group:
            if expl.id in seen:
                continue
            seen.add(expl.id)
            merged.append(expl)
    return sorted(
        merged,
        key=lambda e: (
            _STAGE_ORDER.get(e.stage.value if hasattr(e.stage, "value") else str(e.stage), 99),
            e.subject_kind.value if hasattr(e.subject_kind, "value") else str(e.subject_kind),
            e.subject_id,
            e.rule_id,
            e.id,
        ),
    )
