"""Focus-match evidence captured at selection time (not recomputed later)."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from law_proposition_extractor_domain import SourceFragment, SourceRecord
from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
    build_selection_decision_explanations,
    decision_explanation_id,
)
from law_proposition_extractor_pipeline.runner import (
    _build_extraction_selection_decisions,
    _focus_match_strength,
    _is_non_operative_fragment,
)
from law_proposition_extractor_pipeline.structural_child_extraction_preference import (
    FOCUS_MATCH_BASIS_MULTIWORD_TERM,
    SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
    FocusMatchResult,
    FragmentSelectionDecision,
    apply_structural_child_extraction_preference,
)
from law_proposition_extractor_pipeline.structural_extraction_frontier import (
    SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR,
    apply_required_ancestor_extraction_frontier,
)


def _source(source_id: str = "src-1") -> SourceRecord:
    return SourceRecord(
        id=source_id,
        title="Demo",
        jurisdiction="UK",
        citation="DEMO",
        kind="regulation",
        authoritative_text="unused",
        authoritative_locator="document:full",
        current_snapshot_id="snap-1",
    )


def _frag(
    *,
    frag_id: str,
    locator: str,
    text: str,
    parent_id: str | None = None,
    order: int = 1,
    fragment_type: str = "paragraph",
) -> SourceFragment:
    return SourceFragment(
        id=frag_id,
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator=locator,
        fragment_type=fragment_type,
        fragment_text=text,
        fragment_hash=f"hash-{frag_id}",
        parent_fragment_id=parent_id,
        order_index=order,
    )


def _cfg(**overrides: object) -> dict:
    base = {
        "required_locators": set(),
        "include_annexes": False,
        "focus_terms": ["norwegian pout", "boarfish"],
        "min_fragment_chars": 40,
    }
    base.update(overrides)
    return base


def test_focus_selected_fragment_stores_matched_term() -> None:
    frag = _frag(
        frag_id="f1",
        locator="article:10:paragraph:1",
        text="Measures for norwegian pout and related stocks with enough length.",
    )
    decisions = _build_extraction_selection_decisions(
        [(_source(), frag)],
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(focus_terms=["norwegian pout"]),
        fragment_selection_mode="required_plus_focus",
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.selected is True
    assert d.selection_reason == "focus_term_match"
    assert d.matched_focus_terms == ("norwegian pout",)
    assert d.focus_match_strength == 1
    assert d.focus_match_basis == FOCUS_MATCH_BASIS_MULTIWORD_TERM


def test_multiple_matched_terms_stored_deterministically() -> None:
    frag = _frag(
        frag_id="f1",
        locator="article:10:paragraph:1",
        text="Catches of norwegian pout and boarfish appear together here.",
    )
    decisions = _build_extraction_selection_decisions(
        [(_source(), frag)],
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(focus_terms=["norwegian pout", "boarfish"]),
        fragment_selection_mode="required_plus_focus",
    )
    d = decisions[0]
    assert d.matched_focus_terms == ("boarfish", "norwegian pout")
    assert d.focus_match_strength == 2


def test_match_term_order_independent_of_focus_term_input_order() -> None:
    text = "Catches of norwegian pout and boarfish appear together here."
    frag = _frag(frag_id="f1", locator="article:10", text=text)
    a = _build_extraction_selection_decisions(
        [(_source(), frag)],
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(focus_terms=["norwegian pout", "boarfish"]),
        fragment_selection_mode="required_plus_focus",
    )[0]
    b = _build_extraction_selection_decisions(
        [(_source(), frag)],
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(focus_terms=["boarfish", "norwegian pout"]),
        fragment_selection_mode="required_plus_focus",
    )[0]
    assert a.matched_focus_terms == b.matched_focus_terms == ("boarfish", "norwegian pout")
    assert a.focus_match_strength == b.focus_match_strength
    assert a.focus_match_basis == b.focus_match_basis


def test_focus_match_result_retains_strength_and_basis() -> None:
    result = _focus_match_strength(
        "norwegian pout and boarfish",
        ["boarfish", "norwegian pout"],
    )
    assert isinstance(result, FocusMatchResult)
    assert result.strong is True
    assert result.strength == 2
    assert result.matched_terms == ("boarfish", "norwegian pout")
    assert result.basis == FOCUS_MATCH_BASIS_MULTIWORD_TERM


def test_focus_then_required_ancestor_suppression_retains_evidence() -> None:
    parent = _frag(
        frag_id="fp",
        locator="article:49a:paragraph:2",
        text=(
            "Paragraph 1 shall not apply: (a) where catches contain norwegian pout "
            "and boarfish among other species listed here for coverage"
        ),
        order=1,
    )
    child = _frag(
        frag_id="fc",
        locator="article:49a:paragraph:2:subparagraph:a",
        text="where catches contain norwegian pout and boarfish among other species",
        parent_id="fp",
        order=2,
    )
    decisions = _build_extraction_selection_decisions(
        [(_source(), parent), (_source(), child)],
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(
            required_locators={"article:49a:paragraph:2"},
            focus_terms=["norwegian pout", "boarfish"],
        ),
        fragment_selection_mode="required_plus_focus",
    )
    by_loc = {d.fragment_locator: d for d in decisions}
    suppressed = by_loc["article:49a:paragraph:2:subparagraph:a"]
    assert suppressed.selected is False
    assert suppressed.skip_reason == SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR
    assert suppressed.original_selection_reason == "focus_term_match"
    assert suppressed.matched_focus_terms == ("boarfish", "norwegian pout")
    assert suppressed.focus_match_strength == 2
    assert suppressed.focus_match_basis == FOCUS_MATCH_BASIS_MULTIWORD_TERM


def test_focus_parent_suppressed_by_children_retains_evidence() -> None:
    parent = _frag(
        frag_id="fp",
        locator="article:10",
        text="Parent covering child alpha with norwegian pout and boarfish present.",
        order=1,
        fragment_type="article",
    )
    child = _frag(
        frag_id="fc",
        locator="article:10:paragraph:1",
        text="Parent covering child alpha with norwegian pout and boarfish present.",
        parent_id="fp",
        order=2,
    )
    # Force both selected via focus, then apply child preference only.
    base = [
        FragmentSelectionDecision(
            source_record_id="src-1",
            fragment=parent,
            selected=True,
            selection_reason="focus_term_match",
            skip_reason=None,
            fragment_locator=parent.locator,
            fragment_type=parent.fragment_type,
            fragment_text_length=len(parent.fragment_text),
            matched_focus_terms=("boarfish", "norwegian pout"),
            focus_match_strength=2,
            focus_match_basis=FOCUS_MATCH_BASIS_MULTIWORD_TERM,
        ),
        FragmentSelectionDecision(
            source_record_id="src-1",
            fragment=child,
            selected=True,
            selection_reason="focus_term_match",
            skip_reason=None,
            fragment_locator=child.locator,
            fragment_type=child.fragment_type,
            fragment_text_length=len(child.fragment_text),
            matched_focus_terms=("boarfish", "norwegian pout"),
            focus_match_strength=2,
            focus_match_basis=FOCUS_MATCH_BASIS_MULTIWORD_TERM,
        ),
    ]
    after = apply_structural_child_extraction_preference(
        base, is_non_operative_fragment=_is_non_operative_fragment
    )
    parent_d = next(d for d in after if d.fragment_locator == "article:10")
    assert parent_d.selected is False
    assert parent_d.skip_reason == SKIP_REASON_COVERED_BY_SELECTED_CHILDREN
    assert parent_d.original_selection_reason == "focus_term_match"
    assert parent_d.matched_focus_terms == ("boarfish", "norwegian pout")


def test_required_locator_has_no_fabricated_focus_evidence() -> None:
    frag = _frag(
        frag_id="f1",
        locator="article:49a:paragraph:1",
        text="All catches of norwegian pout and boarfish shall be segregated.",
    )
    decisions = _build_extraction_selection_decisions(
        [(_source(), frag)],
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(
            required_locators={"article:49a:paragraph:1"},
            focus_terms=["norwegian pout", "boarfish"],
        ),
        fragment_selection_mode="required_plus_focus",
    )
    d = decisions[0]
    assert d.selection_reason == "required_locator"
    assert d.matched_focus_terms is None
    assert d.focus_match_strength is None
    assert d.focus_match_basis is None


def test_non_focus_exclusion_has_no_fabricated_focus_evidence() -> None:
    frag = _frag(
        frag_id="f1",
        locator="recital:1",
        text=(
            "Whereas the union should act with sufficient length to exceed "
            "the minimum fragment character threshold for this test."
        ),
        fragment_type="recital",
    )
    decisions = _build_extraction_selection_decisions(
        [(_source(), frag)],
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(focus_terms=["zzzz"]),
        fragment_selection_mode="all_operative",
    )
    d = decisions[0]
    assert d.skip_reason == "non_operative"
    assert d.matched_focus_terms is None
    assert d.focus_match_strength is None


def test_explanation_emission_does_not_call_focus_matcher(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> FocusMatchResult:
        raise AssertionError("focus matcher must not run during explanation emission")

    monkeypatch.setattr("law_proposition_extractor_pipeline.runner._focus_match_strength", boom)

    decision = FragmentSelectionDecision(
        source_record_id="src-1",
        fragment=_frag(
            frag_id="f1",
            locator="article:10",
            text="text intentionally empty of terms after capture",
        ),
        selected=True,
        selection_reason="focus_term_match",
        skip_reason=None,
        fragment_locator="article:10",
        fragment_type="paragraph",
        fragment_text_length=10,
        matched_focus_terms=("norwegian pout",),
        focus_match_strength=1,
        focus_match_basis=FOCUS_MATCH_BASIS_MULTIWORD_TERM,
    )
    explanations = build_selection_decision_explanations(
        [decision],
        extraction_selection_cfg=_cfg(focus_terms=["norwegian pout"]),
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    focus = next(e for e in explanations if e.rule_id == "selection.focus_term_match")
    assert any(
        ev.kind == "matched_focus_term" and ev.value == "norwegian pout"
        for ev in focus.evidence
    )


def test_legacy_focus_decision_without_captured_terms_emits_limited_explanation() -> None:
    decision = FragmentSelectionDecision(
        source_record_id="src-1",
        fragment=_frag(
            frag_id="f1",
            locator="article:10",
            text="Measures for norwegian pout with enough length here.",
        ),
        selected=True,
        selection_reason="focus_term_match",
        skip_reason=None,
        fragment_locator="article:10",
        fragment_type="paragraph",
        fragment_text_length=50,
        # Legacy: no captured evidence
        matched_focus_terms=None,
        focus_match_strength=None,
        focus_match_basis=None,
    )
    explanations = build_selection_decision_explanations(
        [decision],
        extraction_selection_cfg=_cfg(focus_terms=["norwegian pout"]),
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    focus = next(e for e in explanations if e.rule_id == "selection.focus_term_match")
    assert "not retained" in focus.summary
    assert focus.metadata.get("focus_match_evidence_available") is False
    assert not any(ev.kind == "matched_focus_term" for ev in focus.evidence)


def test_changing_captured_term_changes_decision_id() -> None:
    base = FragmentSelectionDecision(
        source_record_id="src-1",
        fragment=_frag(frag_id="f1", locator="article:10", text="x" * 50),
        selected=True,
        selection_reason="focus_term_match",
        skip_reason=None,
        fragment_locator="article:10",
        fragment_type="paragraph",
        fragment_text_length=50,
        matched_focus_terms=("norwegian pout",),
        focus_match_strength=1,
        focus_match_basis=FOCUS_MATCH_BASIS_MULTIWORD_TERM,
    )
    other = replace(base, matched_focus_terms=("boarfish",))
    a = build_selection_decision_explanations(
        [base], extraction_selection_cfg=_cfg(), is_non_operative_fragment=_is_non_operative_fragment
    )[0]
    b = build_selection_decision_explanations(
        [other], extraction_selection_cfg=_cfg(), is_non_operative_fragment=_is_non_operative_fragment
    )[0]
    assert a.id != b.id


def test_reordering_equivalent_matched_terms_does_not_change_decision_id() -> None:
    base = FragmentSelectionDecision(
        source_record_id="src-1",
        fragment=_frag(frag_id="f1", locator="article:10", text="x" * 50),
        selected=True,
        selection_reason="focus_term_match",
        skip_reason=None,
        fragment_locator="article:10",
        fragment_type="paragraph",
        fragment_text_length=50,
        matched_focus_terms=("boarfish", "norwegian pout"),
        focus_match_strength=2,
        focus_match_basis=FOCUS_MATCH_BASIS_MULTIWORD_TERM,
    )
    reordered = replace(base, matched_focus_terms=("norwegian pout", "boarfish"))
    a = build_selection_decision_explanations(
        [base], extraction_selection_cfg=_cfg(), is_non_operative_fragment=_is_non_operative_fragment
    )[0]
    b = build_selection_decision_explanations(
        [reordered],
        extraction_selection_cfg=_cfg(),
        is_non_operative_fragment=_is_non_operative_fragment,
    )[0]
    assert a.id == b.id
    # Also assert material identity helper order-independence via decision_explanation_id
    assert a.id.startswith("decision:")
    assert decision_explanation_id(
        stage="selection",
        decision_type="select",
        subject_kind="source_fragment",
        subject_id="f1",
        rule_id="selection.focus_term_match",
        rule_version="1",
        outcome="selected_for_extraction",
        material_input_identity="x",
    ).startswith("decision:")


def test_serialization_round_trips_captured_evidence() -> None:
    decision = FragmentSelectionDecision(
        source_record_id="src-1",
        fragment=_frag(frag_id="f1", locator="article:10", text="x" * 50),
        selected=True,
        selection_reason="focus_term_match",
        skip_reason=None,
        fragment_locator="article:10",
        fragment_type="paragraph",
        fragment_text_length=50,
        matched_focus_terms=("boarfish", "norwegian pout"),
        focus_match_strength=2,
        focus_match_basis=FOCUS_MATCH_BASIS_MULTIWORD_TERM,
    )
    payload = asdict(decision)
    # SourceFragment is nested; rebuild decision from audit fields alone.
    restored = FragmentSelectionDecision(
        source_record_id=payload["source_record_id"],
        fragment=decision.fragment,
        selected=payload["selected"],
        selection_reason=payload["selection_reason"],
        skip_reason=payload["skip_reason"],
        fragment_locator=payload["fragment_locator"],
        fragment_type=payload["fragment_type"],
        fragment_text_length=payload["fragment_text_length"],
        matched_focus_terms=tuple(payload["matched_focus_terms"]),
        focus_match_strength=payload["focus_match_strength"],
        focus_match_basis=payload["focus_match_basis"],
    )
    assert restored.matched_focus_terms == ("boarfish", "norwegian pout")
    assert restored.focus_match_strength == 2
    assert restored.focus_match_basis == FOCUS_MATCH_BASIS_MULTIWORD_TERM


def test_older_serialized_decisions_without_focus_fields_remain_valid() -> None:
    # Construct without the new fields (defaults).
    decision = FragmentSelectionDecision(
        source_record_id="src-1",
        fragment=_frag(frag_id="f1", locator="article:10", text="x" * 50),
        selected=True,
        selection_reason="required_locator",
        skip_reason=None,
        fragment_locator="article:10",
        fragment_type="paragraph",
        fragment_text_length=50,
    )
    assert decision.matched_focus_terms is None
    assert decision.focus_match_strength is None
    assert decision.focus_match_basis is None
    explanations = build_selection_decision_explanations(
        [decision],
        extraction_selection_cfg=_cfg(required_locators={"article:10"}),
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    assert any(e.rule_id == "selection.required_locator" for e in explanations)


def test_ancestor_frontier_replace_preserves_focus_evidence() -> None:
    parent = _frag(
        frag_id="fp",
        locator="article:5:paragraph:1",
        text="Ancestor body containing the child text with norwegian pout and boarfish",
        order=1,
    )
    child = _frag(
        frag_id="fc",
        locator="article:5:paragraph:1:subparagraph:a",
        text="child text with norwegian pout and boarfish",
        parent_id="fp",
        order=2,
    )
    decisions = [
        FragmentSelectionDecision(
            source_record_id="src-1",
            fragment=parent,
            selected=True,
            selection_reason="required_locator",
            skip_reason=None,
            fragment_locator=parent.locator,
            fragment_type=parent.fragment_type,
            fragment_text_length=len(parent.fragment_text),
        ),
        FragmentSelectionDecision(
            source_record_id="src-1",
            fragment=child,
            selected=True,
            selection_reason="focus_term_match",
            skip_reason=None,
            fragment_locator=child.locator,
            fragment_type=child.fragment_type,
            fragment_text_length=len(child.fragment_text),
            matched_focus_terms=("boarfish", "norwegian pout"),
            focus_match_strength=2,
            focus_match_basis=FOCUS_MATCH_BASIS_MULTIWORD_TERM,
        ),
    ]
    after = apply_required_ancestor_extraction_frontier(decisions)
    child_d = next(
        d for d in after if d.fragment_locator == "article:5:paragraph:1:subparagraph:a"
    )
    assert child_d.selected is False
    assert child_d.matched_focus_terms == ("boarfish", "norwegian pout")
    assert child_d.focus_match_strength == 2
