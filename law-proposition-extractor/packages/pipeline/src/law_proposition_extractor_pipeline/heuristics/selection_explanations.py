"""Emit selection-stage DecisionExplanation records from final selection decisions.

Emission policy
---------------
Explanations are produced from **final** ``FragmentSelectionDecision`` records
after ordinary selection, structural-child preference, and required-ancestor
frontier preference. Intermediate selected states that are later suppressed are
not emitted as separate select explanations; the final suppress record retains
the original selection reason as evidence.

Material exclusions (named rules that blocked extraction after the fragment was
eligible under the configured mode):

- ``skipped_non_operative`` / ``non_operative``
- ``skipped_too_short`` / ``too_short``
- ``skipped_not_required_in_required_only_mode``

``skipped_no_focus_match`` is intentionally omitted (high noise).

Focus-term matched strings are read from evidence captured on
``FragmentSelectionDecision`` at ordinary selection time. Explanation emission
does not rerun the focus matcher.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from law_proposition_extractor_domain import (
    DecisionAlternative,
    DecisionEvidence,
    DecisionExplanation,
    DecisionExplanationsArtifact,
    DecisionInput,
    DecisionStage,
    DecisionSubjectKind,
    DecisionType,
    SourceFragment,
)

from law_proposition_extractor_pipeline.structural_child_extraction_preference import (
    SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED,
    SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
    FragmentSelectionDecision,
)
from law_proposition_extractor_pipeline.structural_extraction_frontier import (
    DIAGNOSTIC_UNRESOLVED_OVERLAP,
    SELECTION_REASON_REQUIRED_ANCESTOR_PREFERRED,
    SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR,
)

from .registry import (
    REGISTRY_VERSION,
    RULE_FOCUS_TERM_MATCH,
    RULE_PREFER_REQUIRED_ANCESTOR,
    RULE_PREFER_REQUIRED_CHILDREN,
    RULE_REQUIRED_LOCATOR,
    RULE_SKIP_NON_OPERATIVE,
    RULE_SKIP_REQUIRED_ONLY_MODE,
    RULE_SKIP_TOO_SHORT,
    RULE_STRUCTURAL_OVERLAP_UNRESOLVED,
    require_heuristic,
)


def decision_explanation_id(
    *,
    stage: str,
    decision_type: str,
    subject_kind: str,
    subject_id: str,
    rule_id: str,
    rule_version: str,
    outcome: str,
    material_input_identity: str,
) -> str:
    """Deterministic explanation id: ``decision:<sha256-hex-prefix>``.

    Does not include prose summaries, timestamps, or random UUIDs. Material input
    identity must be order-independent (caller sorts).
    """
    payload = "|".join(
        (
            str(stage),
            str(decision_type),
            str(subject_kind),
            str(subject_id),
            str(rule_id),
            str(rule_version),
            str(outcome),
            str(material_input_identity),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"decision:{digest}"


def _sorted_evidence(items: list[DecisionEvidence]) -> list[DecisionEvidence]:
    return sorted(
        items,
        key=lambda e: (
            str(e.kind or ""),
            str(e.label or ""),
            str(e.value or ""),
            str(e.id or ""),
        ),
    )


def _sorted_inputs(items: list[DecisionInput]) -> list[DecisionInput]:
    return sorted(
        items,
        key=lambda e: (
            str(e.kind or ""),
            str(e.label or ""),
            str(e.value or ""),
            str(e.id or ""),
        ),
    )


def _sorted_alternatives(items: list[DecisionAlternative]) -> list[DecisionAlternative]:
    return sorted(
        items,
        key=lambda e: (
            str(e.kind or ""),
            str(e.role or ""),
            str(e.id or ""),
            str(e.value or ""),
            str(e.label or ""),
        ),
    )


def _material_identity(*parts: str) -> str:
    return "\x1f".join(sorted(str(p) for p in parts if str(p)))


def _subject_id(decision: FragmentSelectionDecision) -> str:
    if decision.fragment is not None:
        return str(decision.fragment.id)
    return f"source:{decision.source_record_id}"


def _snapshot_id(decision: FragmentSelectionDecision) -> str | None:
    if decision.fragment is None:
        return None
    return str(decision.fragment.source_snapshot_id or "") or None


def _same_source_snapshot(a: SourceFragment, b: SourceFragment) -> bool:
    return (
        str(a.source_record_id) == str(b.source_record_id)
        and str(a.source_snapshot_id) == str(b.source_snapshot_id)
    )


def _captured_focus_terms(decision: FragmentSelectionDecision) -> tuple[str, ...] | None:
    """Return captured matched terms, or None when evidence was not retained."""
    terms = decision.matched_focus_terms
    if terms is None:
        return None
    # Sort for order-independent identity even if a caller mutated order.
    return tuple(sorted(str(t) for t in terms if str(t)))


def _focus_evidence_entries(
    decision: FragmentSelectionDecision,
) -> tuple[list[DecisionEvidence], tuple[str, ...] | None, bool]:
    """Build focus-match evidence from the decision record only (no rematch).

    Returns ``(evidence, matched_terms_or_none, evidence_available)``.
    """
    terms = _captured_focus_terms(decision)
    available = terms is not None
    evidence: list[DecisionEvidence] = []
    if decision.focus_match_strength is not None:
        evidence.append(
            DecisionEvidence(
                kind="match_strength",
                label="Focus match strength",
                value=str(decision.focus_match_strength),
            )
        )
    if decision.focus_match_basis:
        evidence.append(
            DecisionEvidence(
                kind="focus_match_basis",
                label="Focus match basis",
                value=str(decision.focus_match_basis),
            )
        )
    if terms:
        for term in terms:
            evidence.append(
                DecisionEvidence(
                    kind="matched_focus_term",
                    label="Matched focus term",
                    value=term,
                )
            )
    return evidence, terms, available


def _matched_required_locator(
    fragment_locator: str,
    required_locators: set[str],
) -> str | None:
    """Best-effort match using the same normalize rules as selection."""
    raw = str(fragment_locator or "").strip().lower()
    if not raw:
        return None
    base = raw.split("|chunk:", 1)[0].strip()
    m = re.match(r"^(article|annex):(.+)$", base)
    if m:
        kind, value = m.group(1), m.group(2).strip()
        if kind == "article" and value.isdigit():
            base = f"article:{int(value)}"
    for required in sorted(required_locators):
        req = str(required or "").strip().lower()
        if not req:
            continue
        req_base = req.split("|chunk:", 1)[0].strip()
        rm = re.match(r"^(article|annex):(.+)$", req_base)
        if rm:
            kind, value = rm.group(1), rm.group(2).strip()
            if kind == "article" and value.isdigit():
                req_base = f"article:{int(value)}"
        if base == req_base:
            return str(required)
    return None


def _make_explanation(
    *,
    rule_id: str,
    decision_type: DecisionType,
    subject_id: str,
    outcome: str,
    summary: str,
    material_input_identity: str,
    inputs: list[DecisionInput] | None = None,
    evidence: list[DecisionEvidence] | None = None,
    alternatives: list[DecisionAlternative] | None = None,
    diagnostics: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> DecisionExplanation:
    heuristic = require_heuristic(rule_id)
    method = heuristic.method
    rule_version = heuristic.version
    expl_id = decision_explanation_id(
        stage=DecisionStage.SELECTION.value,
        decision_type=decision_type.value,
        subject_kind=DecisionSubjectKind.SOURCE_FRAGMENT.value,
        subject_id=subject_id,
        rule_id=rule_id,
        rule_version=rule_version,
        outcome=outcome,
        material_input_identity=material_input_identity,
    )
    return DecisionExplanation(
        id=expl_id,
        stage=DecisionStage.SELECTION,
        decision_type=decision_type,
        subject_kind=DecisionSubjectKind.SOURCE_FRAGMENT,
        subject_id=subject_id,
        outcome=outcome,
        method=method,
        rule_id=rule_id,
        rule_version=rule_version,
        summary=summary,
        inputs=_sorted_inputs(list(inputs or [])),
        evidence=_sorted_evidence(list(evidence or [])),
        alternatives=_sorted_alternatives(list(alternatives or [])),
        suppressed_items=[],
        diagnostics=sorted(dict.fromkeys(diagnostics or [])),
        code_references=list(heuristic.code_references),
        trace_references=[],
        model_alias=None,
        prompt_version=None,
        metadata=dict(metadata or {}),
    )


def _selected_children_for_parent(
    parent: FragmentSelectionDecision,
    decisions: list[FragmentSelectionDecision],
    *,
    is_non_operative: Any,
) -> list[FragmentSelectionDecision]:
    parent_frag = parent.fragment
    if parent_frag is None:
        return []
    children: list[FragmentSelectionDecision] = []
    for decision in decisions:
        frag = decision.fragment
        if frag is None or not decision.selected:
            continue
        if str(frag.parent_fragment_id or "") != parent_frag.id:
            continue
        if not _same_source_snapshot(parent_frag, frag):
            continue
        if is_non_operative(str(decision.fragment_type or "unknown")):
            continue
        children.append(decision)
    children.sort(
        key=lambda d: (
            d.fragment.order_index is None if d.fragment else True,
            d.fragment.order_index if d.fragment and d.fragment.order_index is not None else 0,
            d.fragment.id if d.fragment else "",
        )
    )
    return children


def build_selection_decision_explanations(
    decisions: list[FragmentSelectionDecision],
    *,
    extraction_selection_cfg: dict[str, Any] | None = None,
    is_non_operative_fragment: Any | None = None,
) -> list[DecisionExplanation]:
    """Map final FragmentSelectionDecision records to DecisionExplanation list.

    Ordering of the returned list is deterministic (sorted by explanation id).
    Input decision order does not affect ids or membership.
    """
    cfg = extraction_selection_cfg or {}
    required_locators = {
        str(x).strip() for x in (cfg.get("required_locators") or []) if str(x).strip()
    }
    if is_non_operative_fragment is None:
        def is_non_operative_fragment(fragment_type: str) -> bool:
            return fragment_type in {"recital", "heading", "table", "unknown", "document"}

    explanations: list[DecisionExplanation] = []
    seen_ids: set[str] = set()

    def _add(expl: DecisionExplanation) -> None:
        if expl.id in seen_ids:
            return
        seen_ids.add(expl.id)
        explanations.append(expl)

    for decision in decisions:
        subject = _subject_id(decision)
        locator = str(decision.fragment_locator or "")
        snap = _snapshot_id(decision)

        # --- Diagnostic: unresolved overlap (may coexist with select) ---
        if DIAGNOSTIC_UNRESOLVED_OVERLAP in (decision.selection_diagnostics or ()):
            other_id = str(decision.preferred_ancestor_fragment_id or "")
            other_loc = str(decision.preferred_ancestor_locator or "")
            evidence = [
                DecisionEvidence(kind="source_locator", label="Fragment locator", value=locator),
                DecisionEvidence(
                    kind="diagnostic_code",
                    label="Diagnostic",
                    value=DIAGNOSTIC_UNRESOLVED_OVERLAP,
                ),
            ]
            if other_id:
                evidence.append(
                    DecisionEvidence(
                        kind="overlapping_fragment",
                        label="Related required fragment id",
                        value=other_id,
                        id=other_id,
                    )
                )
            if other_loc:
                evidence.append(
                    DecisionEvidence(
                        kind="source_locator",
                        label="Related required fragment locator",
                        value=other_loc,
                    )
                )
            if snap:
                evidence.append(
                    DecisionEvidence(kind="source_snapshot", label="Source snapshot", value=snap)
                )
            _add(
                _make_explanation(
                    rule_id=RULE_STRUCTURAL_OVERLAP_UNRESOLVED,
                    decision_type=DecisionType.DIAGNOSE,
                    subject_id=subject,
                    outcome="structural_overlap_unresolved",
                    summary=(
                        "Both this fragment and a nested or related required fragment "
                        "remain selected; neither could safely be suppressed because "
                        "coverage could not be resolved without discarding required "
                        "extraction units."
                    ),
                    material_input_identity=_material_identity(
                        subject, other_id, other_loc, DIAGNOSTIC_UNRESOLVED_OVERLAP
                    ),
                    evidence=evidence,
                    diagnostics=[DIAGNOSTIC_UNRESOLVED_OVERLAP],
                )
            )

        # --- Final suppress: parent covered by selected children ---
        if (
            not decision.selected
            and decision.skip_reason == SKIP_REASON_COVERED_BY_SELECTED_CHILDREN
        ) or (
            not decision.selected
            and decision.selection_reason == SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED
        ):
            children = _selected_children_for_parent(
                decision, decisions, is_non_operative=is_non_operative_fragment
            )
            child_alts = [
                DecisionAlternative(
                    kind="source_fragment",
                    id=str(c.fragment.id) if c.fragment else None,
                    value=str(c.fragment_locator or ""),
                    label="Preferred extraction child",
                    role="preferred_extraction_unit",
                )
                for c in children
            ]
            evidence = [
                DecisionEvidence(kind="source_locator", label="Parent locator", value=locator),
                DecisionEvidence(
                    kind="coverage_basis",
                    label="Coverage basis",
                    value=SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
                ),
                DecisionEvidence(
                    kind="skip_reason",
                    label="Skip reason",
                    value=str(decision.skip_reason or ""),
                ),
                DecisionEvidence(
                    kind="selection_reason",
                    label="Final selection reason",
                    value=str(decision.selection_reason or ""),
                ),
            ]
            if decision.original_selection_reason:
                evidence.append(
                    DecisionEvidence(
                        kind="original_selection_reason",
                        label="Original selection reason",
                        value=str(decision.original_selection_reason),
                    )
                )
            focus_ev, focus_terms_captured, focus_available = _focus_evidence_entries(decision)
            evidence.extend(focus_ev)
            inputs = [
                DecisionInput(
                    kind="source_fragment",
                    id=str(c.fragment.id) if c.fragment else None,
                    value=str(c.fragment_locator or ""),
                    label="Selected child",
                )
                for c in children
            ]
            child_locs = ",".join(sorted(str(c.fragment_locator or "") for c in children))
            material_parts = [
                subject,
                SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
                child_locs,
            ]
            if focus_terms_captured:
                material_parts.extend(focus_terms_captured)
            metadata: dict[str, Any] = {}
            if (
                decision.original_selection_reason == "focus_term_match"
                or decision.matched_focus_terms is not None
            ):
                metadata["focus_match_evidence_available"] = focus_available
            _add(
                _make_explanation(
                    rule_id=RULE_PREFER_REQUIRED_CHILDREN,
                    decision_type=DecisionType.SUPPRESS,
                    subject_id=subject,
                    outcome="not_selected_for_extraction",
                    summary=(
                        "This parent fragment was not extracted because its selected "
                        "structural children collectively covered its operative text."
                    ),
                    material_input_identity=_material_identity(*material_parts),
                    inputs=inputs,
                    evidence=evidence,
                    alternatives=child_alts,
                    metadata=metadata or None,
                )
            )
            continue

        # --- Final suppress: focus descendant covered by required ancestor ---
        if (
            not decision.selected
            and decision.skip_reason == SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR
        ) or (
            not decision.selected
            and decision.selection_reason == SELECTION_REASON_REQUIRED_ANCESTOR_PREFERRED
        ):
            anc_id = str(decision.preferred_ancestor_fragment_id or "")
            anc_loc = str(decision.preferred_ancestor_locator or "")
            coverage = str(decision.coverage_basis or "")
            evidence = [
                DecisionEvidence(kind="source_locator", label="Descendant locator", value=locator),
                DecisionEvidence(
                    kind="skip_reason",
                    label="Skip reason",
                    value=str(decision.skip_reason or ""),
                ),
                DecisionEvidence(
                    kind="selection_reason",
                    label="Final selection reason",
                    value=str(decision.selection_reason or ""),
                ),
            ]
            if decision.original_selection_reason:
                evidence.append(
                    DecisionEvidence(
                        kind="original_selection_reason",
                        label="Original selection reason",
                        value=str(decision.original_selection_reason),
                    )
                )
            if coverage:
                evidence.append(
                    DecisionEvidence(
                        kind="coverage_basis",
                        label="Coverage basis",
                        value=coverage,
                    )
                )
            if anc_id:
                evidence.append(
                    DecisionEvidence(
                        kind="preferred_ancestor",
                        label="Preferred ancestor fragment id",
                        value=anc_id,
                        id=anc_id,
                    )
                )
            if anc_loc:
                evidence.append(
                    DecisionEvidence(
                        kind="source_locator",
                        label="Preferred ancestor locator",
                        value=anc_loc,
                    )
                )
            focus_ev, focus_terms_captured, focus_available = _focus_evidence_entries(decision)
            evidence.extend(focus_ev)
            alternatives = []
            if anc_id or anc_loc:
                alternatives.append(
                    DecisionAlternative(
                        kind="source_fragment",
                        id=anc_id or None,
                        value=anc_loc or None,
                        label="Preferred required ancestor",
                        role="preferred_extraction_unit",
                    )
                )
            material_parts = [
                subject,
                anc_id,
                anc_loc,
                coverage,
                SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR,
            ]
            if focus_terms_captured:
                material_parts.extend(focus_terms_captured)
            metadata = {}
            if (
                decision.original_selection_reason == "focus_term_match"
                or decision.matched_focus_terms is not None
            ):
                metadata["focus_match_evidence_available"] = focus_available
            _add(
                _make_explanation(
                    rule_id=RULE_PREFER_REQUIRED_ANCESTOR,
                    decision_type=DecisionType.SUPPRESS,
                    subject_id=subject,
                    outcome="not_selected_for_extraction",
                    summary=(
                        "This focus-selected descendant was not extracted because its "
                        "explicitly required ancestor already covered its legal text "
                        "and structured-list terminals."
                    ),
                    material_input_identity=_material_identity(*material_parts),
                    evidence=evidence,
                    alternatives=alternatives,
                    metadata=metadata or None,
                )
            )
            continue

        # --- Selected ---
        if decision.selected:
            reason = str(decision.selection_reason or "")
            if reason == "required_locator":
                matched = _matched_required_locator(locator, required_locators)
                evidence = [
                    DecisionEvidence(kind="source_locator", label="Fragment locator", value=locator),
                    DecisionEvidence(
                        kind="source_fragment",
                        label="Source fragment id",
                        value=subject,
                        id=subject,
                    ),
                ]
                if matched:
                    evidence.append(
                        DecisionEvidence(
                            kind="required_locator",
                            label="Required locator that matched",
                            value=matched,
                        )
                    )
                if snap:
                    evidence.append(
                        DecisionEvidence(
                            kind="source_snapshot",
                            label="Source snapshot",
                            value=snap,
                        )
                    )
                _add(
                    _make_explanation(
                        rule_id=RULE_REQUIRED_LOCATOR,
                        decision_type=DecisionType.SELECT,
                        subject_id=subject,
                        outcome="selected_for_extraction",
                        summary=(
                            "This fragment was selected because its locator was "
                            "explicitly required by the run configuration."
                        ),
                        material_input_identity=_material_identity(
                            subject, locator, matched or "", "required_locator"
                        ),
                        evidence=evidence,
                    )
                )
            elif reason == "focus_term_match":
                focus_ev, focus_terms_captured, focus_available = _focus_evidence_entries(
                    decision
                )
                evidence = [
                    DecisionEvidence(kind="source_locator", label="Fragment locator", value=locator),
                    *focus_ev,
                ]
                if focus_available and focus_terms_captured:
                    summary = (
                        "This fragment was selected because its text strongly "
                        "matched configured focus terms."
                    )
                    material_terms = focus_terms_captured
                elif focus_available:
                    summary = (
                        "This fragment was selected by the focus-term rule. "
                        "The specific matched term was not retained in this "
                        "decision record."
                    )
                    material_terms = ()
                else:
                    summary = (
                        "This fragment was selected by the focus-term rule. "
                        "The specific matched term was not retained in this "
                        "decision record."
                    )
                    material_terms = ()
                _add(
                    _make_explanation(
                        rule_id=RULE_FOCUS_TERM_MATCH,
                        decision_type=DecisionType.SELECT,
                        subject_id=subject,
                        outcome="selected_for_extraction",
                        summary=summary,
                        material_input_identity=_material_identity(
                            subject, locator, "focus_term_match", *material_terms
                        ),
                        evidence=evidence,
                        metadata={"focus_match_evidence_available": focus_available},
                    )
                )
            # annex_included and other select reasons: deferred (not in this slice)
            continue

        # --- Material exclusions ---
        skip = str(decision.skip_reason or "")
        sel_reason = str(decision.selection_reason or "")
        if skip == "non_operative" or sel_reason == "skipped_non_operative":
            _add(
                _make_explanation(
                    rule_id=RULE_SKIP_NON_OPERATIVE,
                    decision_type=DecisionType.EXCLUDE,
                    subject_id=subject,
                    outcome="not_selected_for_extraction",
                    summary=(
                        "This fragment was not selected for extraction because it "
                        "is a non-operative fragment type."
                    ),
                    material_input_identity=_material_identity(
                        subject, locator, "non_operative", decision.fragment_type
                    ),
                    evidence=[
                        DecisionEvidence(
                            kind="source_locator", label="Fragment locator", value=locator
                        ),
                        DecisionEvidence(
                            kind="fragment_type",
                            label="Fragment type",
                            value=str(decision.fragment_type or ""),
                        ),
                        DecisionEvidence(
                            kind="skip_reason", label="Skip reason", value="non_operative"
                        ),
                    ],
                )
            )
        elif skip == "too_short" or sel_reason == "skipped_too_short":
            _add(
                _make_explanation(
                    rule_id=RULE_SKIP_TOO_SHORT,
                    decision_type=DecisionType.EXCLUDE,
                    subject_id=subject,
                    outcome="not_selected_for_extraction",
                    summary=(
                        "This fragment was not selected for extraction because its "
                        "text length is below the configured minimum."
                    ),
                    material_input_identity=_material_identity(
                        subject, locator, "too_short", str(decision.fragment_text_length)
                    ),
                    evidence=[
                        DecisionEvidence(
                            kind="source_locator", label="Fragment locator", value=locator
                        ),
                        DecisionEvidence(
                            kind="fragment_text_length",
                            label="Fragment text length",
                            value=str(decision.fragment_text_length),
                        ),
                        DecisionEvidence(
                            kind="skip_reason", label="Skip reason", value="too_short"
                        ),
                    ],
                )
            )
        elif (
            skip == "skipped_not_required_in_required_only_mode"
            or sel_reason == "skipped_not_required_in_required_only_mode"
        ):
            _add(
                _make_explanation(
                    rule_id=RULE_SKIP_REQUIRED_ONLY_MODE,
                    decision_type=DecisionType.EXCLUDE,
                    subject_id=subject,
                    outcome="not_selected_for_extraction",
                    summary=(
                        "This fragment was not selected for extraction because "
                        "required-only mode was configured and its locator was not "
                        "explicitly required."
                    ),
                    material_input_identity=_material_identity(
                        subject, locator, "skipped_not_required_in_required_only_mode"
                    ),
                    evidence=[
                        DecisionEvidence(
                            kind="source_locator", label="Fragment locator", value=locator
                        ),
                        DecisionEvidence(
                            kind="skip_reason",
                            label="Skip reason",
                            value="skipped_not_required_in_required_only_mode",
                        ),
                    ],
                )
            )

    return sorted(explanations, key=lambda e: e.id)


def build_decision_explanations_artifact(
    *,
    run_id: str,
    decisions: list[DecisionExplanation],
) -> dict[str, Any]:
    """Build the decision_explanations.json wrapper payload."""
    referenced = sorted({(d.rule_id, d.rule_version) for d in decisions})
    referenced_rules = [
        {
            "rule_id": rule_id,
            "rule_version": rule_version,
            "name": require_heuristic(rule_id).name,
            "method": require_heuristic(rule_id).method.value,
            "stage": require_heuristic(rule_id).stage.value,
        }
        for rule_id, rule_version in referenced
    ]
    artifact = DecisionExplanationsArtifact(
        schema_version="1",
        run_id=run_id,
        decisions=sorted(decisions, key=lambda d: d.id),
        metadata={
            "registry_version": REGISTRY_VERSION,
            "referenced_rules": referenced_rules,
            "decision_count": len(decisions),
            "notes": (
                "DecisionExplanation records for selection, structured-list "
                "extraction reconciliation, legal-effect classification, "
                "legal-rule grouping, typed legal-relationship inference, and "
                "effective-law typed-context expansion. Stage order for "
                "consumers: selection, extraction, classification, grouping, "
                "relationship, effective_law, provenance, source_effect, review. "
                "Preferred consumer order: provenance, selection, extraction, "
                "classification, grouping, relationship, effective_law, "
                "source_effect, review. Execution "
                "evidence, not LLM chain-of-thought. Older bundles without this "
                "artifact remain loadable."
            ),
        },
    )
    return artifact.model_dump(mode="json")


def attach_decision_explanations(
    bundle: dict[str, Any],
    *,
    decisions: list[DecisionExplanation] | None = None,
) -> None:
    """Attach ``decision_explanations`` onto an export bundle.

    If ``decisions`` is provided, those records are used. Otherwise an existing
    bundle payload is preserved, or an empty run-scoped artifact is written.
    """
    run = bundle.get("run")
    run_id = ""
    if isinstance(run, dict):
        run_id = str(run.get("id") or "")

    if decisions is not None:
        bundle["decision_explanations"] = build_decision_explanations_artifact(
            run_id=run_id,
            decisions=decisions,
        )
        return

    existing = bundle.get("decision_explanations")
    if isinstance(existing, dict) and "decisions" in existing:
        # Ensure schema wrapper fields for export consistency.
        existing.setdefault("schema_version", "1")
        existing.setdefault("run_id", run_id)
        meta = existing.setdefault("metadata", {})
        if isinstance(meta, dict):
            meta.setdefault("registry_version", REGISTRY_VERSION)
        bundle["decision_explanations"] = existing
        return

    bundle["decision_explanations"] = build_decision_explanations_artifact(
        run_id=run_id,
        decisions=[],
    )
