"""Required-ancestor extraction frontier (Article 49a focus-descendant overlap)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import SourceFragment, SourceRecord
from law_proposition_extractor_pipeline.runner import (
    _build_extraction_selection_decisions,
    _is_non_operative_fragment,
)
from law_proposition_extractor_pipeline.structural_child_extraction_preference import (
    SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED,
    SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
    FragmentSelectionDecision,
    apply_structural_child_extraction_preference,
)
from law_proposition_extractor_pipeline.structural_extraction_frontier import (
    COVERAGE_BASIS_STRUCTURED_LIST,
    COVERAGE_BASIS_TEXT_CONTAINED,
    DIAGNOSTIC_UNRESOLVED_OVERLAP,
    SELECTION_REASON_REQUIRED_ANCESTOR_PREFERRED,
    SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR,
    apply_required_ancestor_extraction_frontier,
    descendant_text_contained_in_ancestor,
    establish_ancestor_coverage,
)
from law_proposition_extractor_pipeline.structured_list_decomposition import draft_structured_list_leaves

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _fragments_from_rows(
    rows: list[dict],
    *,
    source_id: str,
    snapshot_id: str,
) -> list[SourceFragment]:
    out: list[SourceFragment] = []
    for row in rows:
        out.append(
            SourceFragment(
                id=str(row["id"]),
                source_record_id=source_id,
                source_snapshot_id=snapshot_id,
                locator=str(row["locator"]),
                fragment_type=str(row.get("fragment_type") or "article"),
                fragment_text=str(row["fragment_text"]),
                fragment_hash=f"hash-{row['id']}",
                parent_fragment_id=row.get("parent_fragment_id"),
                order_index=row.get("order_index"),
            )
        )
    return out


def _load_49a_fragments() -> list[SourceFragment]:
    payload = _load_fixture()
    return _fragments_from_rows(
        payload["fragments"],
        source_id=str(payload["source_record_id"]),
        snapshot_id=str(payload["source_snapshot_id"]),
    )


def _source_record(source_id: str = "src-control-regulation-demo") -> SourceRecord:
    return SourceRecord(
        id=source_id,
        title="Demo control regulation",
        jurisdiction="UK",
        citation="DEMO/1224",
        kind="regulation",
        authoritative_text="unused",
        authoritative_locator="document:full",
        current_snapshot_id="snap-src-control-regulation-demo-v1",
    )


def _decision_for(
    fragment: SourceFragment,
    *,
    selected: bool,
    reason: str = "focus_term_match",
    skip_reason: str | None = None,
) -> FragmentSelectionDecision:
    return FragmentSelectionDecision(
        source_record_id=fragment.source_record_id,
        fragment=fragment,
        selected=selected,
        selection_reason=reason if selected else (reason or "skipped_no_focus_match"),
        skip_reason=None if selected else (skip_reason or "no_focus_match"),
        fragment_locator=fragment.locator,
        fragment_type=fragment.fragment_type,
        fragment_text_length=len(fragment.fragment_text),
    )


def test_subparagraph_a_text_is_contained_in_paragraph_2() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    assert (
        descendant_text_contained_in_ancestor(
            by_loc["article:49a:paragraph:2"].fragment_text,
            by_loc["article:49a:paragraph:2:subparagraph:a"].fragment_text,
        )
        is True
    )


def test_paragraph_2_structured_list_paths_cover_subparagraph_a() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    p2 = by_loc["article:49a:paragraph:2"]
    drafts = draft_structured_list_leaves(p2.fragment_text, p2.locator)
    assert sorted(d.path_key for d in drafts) == ["2-a-i", "2-a-ii", "2-b"]
    basis = establish_ancestor_coverage(
        p2,
        by_loc["article:49a:paragraph:2:subparagraph:a"],
    )
    assert basis in {COVERAGE_BASIS_STRUCTURED_LIST, COVERAGE_BASIS_TEXT_CONTAINED}


def test_article_49a_selection_frontier_via_runner_path() -> None:
    fragments = _load_49a_fragments()
    by_loc = {f.locator: f for f in fragments}
    source = _source_record()
    # Shuffled order: subparagraph before required paragraphs and article parent.
    jobs = [
        (source, by_loc["article:49a:paragraph:2:subparagraph:a"]),
        (source, by_loc["article:49a:paragraph:2:subparagraph:b"]),
        (source, by_loc["article:49a"]),
        (source, by_loc["article:49a:paragraph:3"]),
        (source, by_loc["article:49a:paragraph:1"]),
        (source, by_loc["article:49a:paragraph:2"]),
        (source, by_loc["document:full"]),
        (source, by_loc["article:49a:paragraph:2:subparagraph:a:item:i"]),
        (source, by_loc["article:49a:paragraph:2:subparagraph:a:item:ii"]),
    ]
    decisions = _build_extraction_selection_decisions(
        jobs,
        ext_mode="frontier",
        extraction_selection_cfg={
            "required_locators": {
                "article:49a:paragraph:1",
                "article:49a:paragraph:2",
                "article:49a:paragraph:3",
            },
            "include_annexes": False,
            "focus_terms": ["norwegian pout", "boarfish"],
            "min_fragment_chars": 40,
        },
        fragment_selection_mode="required_plus_focus",
    )
    by_decision = {d.fragment_locator: d for d in decisions}

    assert by_decision["article:49a"].selected is False
    assert (
        by_decision["article:49a"].selection_reason
        == SELECTION_REASON_STRUCTURAL_CHILDREN_PREFERRED
    )
    assert by_decision["article:49a"].skip_reason == SKIP_REASON_COVERED_BY_SELECTED_CHILDREN

    assert by_decision["article:49a:paragraph:1"].selected is True
    assert by_decision["article:49a:paragraph:2"].selected is True
    assert by_decision["article:49a:paragraph:3"].selected is True
    assert by_decision["article:49a:paragraph:1"].selection_reason == "required_locator"
    assert by_decision["article:49a:paragraph:2"].selection_reason == "required_locator"
    assert by_decision["article:49a:paragraph:3"].selection_reason == "required_locator"

    suba = by_decision["article:49a:paragraph:2:subparagraph:a"]
    assert suba.selected is False
    assert suba.selection_reason == SELECTION_REASON_REQUIRED_ANCESTOR_PREFERRED
    assert suba.skip_reason == SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR
    assert suba.original_selection_reason == "focus_term_match"
    assert suba.preferred_ancestor_locator == "article:49a:paragraph:2"
    assert suba.preferred_ancestor_fragment_id == by_loc["article:49a:paragraph:2"].id
    assert suba.matched_focus_terms == ("boarfish", "norwegian pout")
    assert suba.focus_match_strength == 2
    assert suba.focus_match_basis == "multiword_term"
    assert suba.coverage_basis in {
        COVERAGE_BASIS_STRUCTURED_LIST,
        COVERAGE_BASIS_TEXT_CONTAINED,
    }
    # Remains in decision set / source_fragments analogue.
    assert "article:49a:paragraph:2:subparagraph:a" in by_decision

    selected = {
        d.fragment_locator for d in decisions if d.selected and d.fragment is not None
    }
    assert selected == {
        "article:49a:paragraph:1",
        "article:49a:paragraph:2",
        "article:49a:paragraph:3",
    }


def test_focus_descendant_remains_when_ancestor_not_selected() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    preferred = apply_required_ancestor_extraction_frontier(
        [
            _decision_for(by_loc["article:77:paragraph:1"], selected=False),
            _decision_for(
                by_loc["article:77:paragraph:1:subparagraph:a"],
                selected=True,
                reason="focus_term_match",
            ),
        ]
    )
    leaf = next(
        d
        for d in preferred
        if d.fragment_locator == "article:77:paragraph:1:subparagraph:a"
    )
    assert leaf.selected is True
    assert leaf.selection_reason == "focus_term_match"


def test_required_descendant_not_suppressed_under_required_ancestor() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    preferred = apply_required_ancestor_extraction_frontier(
        [
            _decision_for(
                by_loc["article:81:paragraph:1"],
                selected=True,
                reason="required_locator",
            ),
            _decision_for(
                by_loc["article:81:paragraph:1:subparagraph:a"],
                selected=True,
                reason="required_locator",
            ),
        ]
    )
    child = next(
        d
        for d in preferred
        if d.fragment_locator == "article:81:paragraph:1:subparagraph:a"
    )
    parent = next(
        d for d in preferred if d.fragment_locator == "article:81:paragraph:1"
    )
    assert child.selected is True
    assert parent.selected is True
    assert DIAGNOSTIC_UNRESOLVED_OVERLAP in child.selection_diagnostics
    assert DIAGNOSTIC_UNRESOLVED_OVERLAP in parent.selection_diagnostics


def test_unique_descendant_text_not_suppressed() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    preferred = apply_required_ancestor_extraction_frontier(
        [
            _decision_for(
                by_loc["article:80:paragraph:1"],
                selected=True,
                reason="required_locator",
            ),
            _decision_for(
                by_loc["article:80:paragraph:1:subparagraph:a"],
                selected=True,
                reason="focus_term_match",
            ),
        ]
    )
    child = next(
        d
        for d in preferred
        if d.fragment_locator == "article:80:paragraph:1:subparagraph:a"
    )
    assert child.selected is True
    assert child.selection_reason == "focus_term_match"


def test_similar_unrelated_fragment_not_compared_via_text_alone() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    preferred = apply_required_ancestor_extraction_frontier(
        [
            _decision_for(
                by_loc["article:49a:paragraph:2"],
                selected=True,
                reason="required_locator",
            ),
            _decision_for(
                by_loc["article:82:paragraph:1"],
                selected=True,
                reason="focus_term_match",
            ),
        ]
    )
    similar = next(d for d in preferred if d.fragment_locator == "article:82:paragraph:1")
    assert similar.selected is True


def test_cross_source_same_locator_never_compared() -> None:
    payload = _load_fixture()
    main = _load_49a_fragments()
    other = _fragments_from_rows(
        payload["other_instrument"]["fragments"],
        source_id=str(payload["other_instrument"]["source_record_id"]),
        snapshot_id=str(payload["other_instrument"]["source_snapshot_id"]),
    )
    by_main = {f.locator: f for f in main}
    by_other = {f.locator: f for f in other}
    preferred = apply_required_ancestor_extraction_frontier(
        [
            _decision_for(
                by_main["article:49a:paragraph:2"],
                selected=True,
                reason="required_locator",
            ),
            _decision_for(
                by_other["article:49a:paragraph:2:subparagraph:a"],
                selected=True,
                reason="focus_term_match",
            ),
        ]
    )
    other_suba = next(
        d
        for d in preferred
        if d.fragment_locator == "article:49a:paragraph:2:subparagraph:a"
    )
    assert other_suba.selected is True
    assert other_suba.source_record_id == payload["other_instrument"]["source_record_id"]


def test_cross_snapshot_same_source_never_compared() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    p2 = by_loc["article:49a:paragraph:2"]
    suba = by_loc["article:49a:paragraph:2:subparagraph:a"]
    other_snap_suba = SourceFragment(
        id="frag-other-snap-suba",
        source_record_id=suba.source_record_id,
        source_snapshot_id="snap-other-v2",
        locator=suba.locator,
        fragment_type=suba.fragment_type,
        fragment_text=suba.fragment_text,
        fragment_hash="hash-other-snap",
        parent_fragment_id=p2.id,
        order_index=9999,
    )
    preferred = apply_required_ancestor_extraction_frontier(
        [
            _decision_for(p2, selected=True, reason="required_locator"),
            _decision_for(other_snap_suba, selected=True, reason="focus_term_match"),
        ]
    )
    leaf = next(d for d in preferred if d.fragment is other_snap_suba)
    assert leaf.selected is True


def test_uncertain_hierarchy_does_not_suppress() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    p2 = by_loc["article:49a:paragraph:2"]
    # Same text as subparagraph (a) but broken parent link.
    orphan = SourceFragment(
        id="frag-broken-parent-suba",
        source_record_id=p2.source_record_id,
        source_snapshot_id=p2.source_snapshot_id,
        locator="article:49a:paragraph:2:subparagraph:a",
        fragment_type="article",
        fragment_text=by_loc["article:49a:paragraph:2:subparagraph:a"].fragment_text,
        fragment_hash="hash-broken",
        parent_fragment_id="frag-missing-parent",
        order_index=1,
    )
    preferred = apply_required_ancestor_extraction_frontier(
        [
            _decision_for(p2, selected=True, reason="required_locator"),
            _decision_for(orphan, selected=True, reason="focus_term_match"),
        ]
    )
    leaf = next(d for d in preferred if d.fragment is orphan)
    assert leaf.selected is True


def test_frontier_deterministic_regardless_of_input_order() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    operative = [
        by_loc["article:49a"],
        by_loc["article:49a:paragraph:1"],
        by_loc["article:49a:paragraph:2"],
        by_loc["article:49a:paragraph:2:subparagraph:a"],
        by_loc["article:49a:paragraph:3"],
    ]
    orders = [
        operative,
        list(reversed(operative)),
        [operative[3], operative[0], operative[4], operative[1], operative[2]],
    ]
    outcomes: list[tuple[bool, str, str | None, str | None]] = []
    for order in orders:
        base = [
            _decision_for(
                f,
                selected=True,
                reason=(
                    "required_locator"
                    if "paragraph:" in f.locator and "subparagraph" not in f.locator
                    else "focus_term_match"
                ),
            )
            for f in order
        ]
        after_children = apply_structural_child_extraction_preference(
            base,
            is_non_operative_fragment=_is_non_operative_fragment,
        )
        preferred = apply_required_ancestor_extraction_frontier(after_children)
        suba = next(
            d
            for d in preferred
            if d.fragment_locator == "article:49a:paragraph:2:subparagraph:a"
        )
        outcomes.append(
            (
                suba.selected,
                suba.selection_reason,
                suba.skip_reason,
                suba.preferred_ancestor_locator,
            )
        )
    assert len(set(outcomes)) == 1
    assert outcomes[0] == (
        False,
        SELECTION_REASON_REQUIRED_ANCESTOR_PREFERRED,
        SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR,
        "article:49a:paragraph:2",
    )


def test_exported_article_49a_propositions_exclude_suppressed_subparagraph() -> None:
    payload = _load_fixture()
    exported = payload["exported_propositions"]
    a49 = [
        row
        for row in exported
        if str(row["fragment_locator"]).startswith("article:49a")
    ]
    assert len(a49) == 6
    assert {row["source_fragment_id"] for row in a49} == {
        "frag-demo-49a-p1",
        "frag-demo-49a-p2",
        "frag-demo-49a-p3",
    }
    assert "frag-demo-49a-p2-suba" not in {row["source_fragment_id"] for row in a49}

    p1 = [r for r in a49 if r["source_fragment_id"] == "frag-demo-49a-p1"]
    p2 = [r for r in a49 if r["source_fragment_id"] == "frag-demo-49a-p2"]
    p3 = [r for r in a49 if r["source_fragment_id"] == "frag-demo-49a-p3"]
    assert len(p1) == 2
    assert len(p2) == 3
    assert len(p3) == 1
    paths = [
        (r.get("extraction_debug_meta") or {}).get("structured_list_path")
        for r in p2
    ]
    assert paths == ["2-a-i", "2-a-ii", "2-b"]
    assert "2-a-ii" in paths
    article_14_props = [
        r
        for r in p2
        if "Article 14" in str(r.get("proposition_text") or "")
        or "article 14" in [str(x).lower() for x in (r.get("explicit_cross_reference_targets") or [])]
    ]
    assert len(article_14_props) == 1
    assert (article_14_props[0].get("extraction_debug_meta") or {}).get(
        "structured_list_path"
    ) == "2-b"

    suppressed = payload["suppressed_propositions"]
    assert any(
        r["source_fragment_id"] == "frag-demo-49a-p2-suba" for r in suppressed
    )


def test_parent_suppression_still_coexists_with_frontier() -> None:
    by_loc = {f.locator: f for f in _load_49a_fragments()}
    base = [
        _decision_for(by_loc["article:49a"], selected=True, reason="focus_term_match"),
        _decision_for(
            by_loc["article:49a:paragraph:1"], selected=True, reason="required_locator"
        ),
        _decision_for(
            by_loc["article:49a:paragraph:2"], selected=True, reason="required_locator"
        ),
        _decision_for(
            by_loc["article:49a:paragraph:2:subparagraph:a"],
            selected=True,
            reason="focus_term_match",
        ),
        _decision_for(
            by_loc["article:49a:paragraph:3"], selected=True, reason="required_locator"
        ),
    ]
    after_children = apply_structural_child_extraction_preference(
        base,
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    preferred = apply_required_ancestor_extraction_frontier(after_children)
    by_decision = {d.fragment_locator: d for d in preferred}
    assert by_decision["article:49a"].selected is False
    assert by_decision["article:49a"].skip_reason == SKIP_REASON_COVERED_BY_SELECTED_CHILDREN
    assert by_decision["article:49a:paragraph:2:subparagraph:a"].selected is False
    assert (
        by_decision["article:49a:paragraph:2:subparagraph:a"].skip_reason
        == SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR
    )
