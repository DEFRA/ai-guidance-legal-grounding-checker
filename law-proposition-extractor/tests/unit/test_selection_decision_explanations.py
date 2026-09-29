"""Selection DecisionExplanation emission tests."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import SourceFragment, SourceRecord
from law_proposition_extractor_pipeline.heuristics.registry import get_heuristic, require_heuristic
from law_proposition_extractor_pipeline.heuristics.selection_explanations import (
    build_decision_explanations_artifact,
    build_selection_decision_explanations,
)
from law_proposition_extractor_pipeline.runner import (
    _build_extraction_selection_decisions,
    _is_non_operative_fragment,
)
from law_proposition_extractor_pipeline.structural_child_extraction_preference import (
    SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
    FragmentSelectionDecision,
)
from law_proposition_extractor_pipeline.structural_extraction_frontier import (
    DIAGNOSTIC_UNRESOLVED_OVERLAP,
    SKIP_REASON_COVERED_BY_REQUIRED_ANCESTOR,
    apply_required_ancestor_extraction_frontier,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)


def _load_49a_fragments() -> list[SourceFragment]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    source_id = str(payload["source_record_id"])
    snapshot_id = str(payload["source_snapshot_id"])
    fragments: list[SourceFragment] = []
    for row in payload["fragments"]:
        fragments.append(
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
    return fragments


def _source(source_id: str = "src-control-regulation-demo") -> SourceRecord:
    return SourceRecord(
        id=source_id,
        title="Demo",
        jurisdiction="UK",
        citation="DEMO",
        kind="regulation",
        authoritative_text="unused",
        authoritative_locator="document:full",
        current_snapshot_id="snap-src-control-regulation-demo-v1",
    )


def _cfg(**overrides: object) -> dict:
    base = {
        "required_locators": {
            "article:49a:paragraph:1",
            "article:49a:paragraph:2",
            "article:49a:paragraph:3",
        },
        "include_annexes": False,
        "focus_terms": ["norwegian pout", "boarfish"],
        "min_fragment_chars": 40,
    }
    base.update(overrides)
    return base


def _explanations_for(
    decisions: list[FragmentSelectionDecision],
    cfg: dict | None = None,
):
    return build_selection_decision_explanations(
        decisions,
        extraction_selection_cfg=cfg or _cfg(),
        is_non_operative_fragment=_is_non_operative_fragment,
    )


def test_required_locator_and_frontier_explanations_from_49a_shaped() -> None:
    fragments = _load_49a_fragments()
    source = _source()
    jobs = [(source, frag) for frag in fragments]
    decisions = _build_extraction_selection_decisions(
        jobs,
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(),
        fragment_selection_mode="required_plus_focus",
    )
    explanations = _explanations_for(decisions)
    by_rule = {}
    for expl in explanations:
        for ev in expl.evidence:
            if ev.kind == "source_locator" and ev.value:
                by_rule.setdefault(expl.rule_id, []).append((ev.value, expl.outcome))

    assert any(
        loc == "article:49a:paragraph:1" and outcome == "selected_for_extraction"
        for loc, outcome in by_rule.get("selection.required_locator", [])
    )
    parent = [
        e
        for e in explanations
        if e.rule_id == "selection.prefer_required_children"
        and any(
            ev.value == "article:49a" and ev.label == "Parent locator"
            for ev in e.evidence
        )
    ]
    assert len(parent) == 1
    assert parent[0].outcome == "not_selected_for_extraction"
    assert any(
        ev.value == SKIP_REASON_COVERED_BY_SELECTED_CHILDREN
        for ev in parent[0].evidence
        if ev.kind == "coverage_basis"
    )
    assert {alt.value for alt in parent[0].alternatives} >= {
        "article:49a:paragraph:1",
        "article:49a:paragraph:2",
        "article:49a:paragraph:3",
    }

    # Subparagraph a may be focus-selected then suppressed by required ancestor
    # depending on fixture text; if present, assert the contract.
    ancestor_suppress = [
        e
        for e in explanations
        if e.rule_id == "selection.prefer_required_ancestor"
        and any(
            ev.value == "article:49a:paragraph:2:subparagraph:a"
            for ev in e.evidence
            if ev.kind == "source_locator"
        )
    ]
    if ancestor_suppress:
        expl = ancestor_suppress[0]
        assert expl.outcome == "not_selected_for_extraction"
        assert any(
            ev.value == "article:49a:paragraph:2"
            for ev in expl.evidence
            if ev.label == "Preferred ancestor locator"
        )
        assert any(ev.kind == "original_selection_reason" for ev in expl.evidence)
        assert any(ev.kind == "coverage_basis" for ev in expl.evidence)
        matched = {
            ev.value for ev in expl.evidence if ev.kind == "matched_focus_term"
        }
        assert matched == {"boarfish", "norwegian pout"}
        assert expl.metadata.get("focus_match_evidence_available") is True


def test_emitted_rule_ids_and_versions_match_registry() -> None:
    fragments = _load_49a_fragments()
    source = _source()
    jobs = [(source, frag) for frag in fragments]
    decisions = _build_extraction_selection_decisions(
        jobs,
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(),
        fragment_selection_mode="required_plus_focus",
    )
    for expl in _explanations_for(decisions):
        assert get_heuristic(expl.rule_id) is not None
        assert expl.rule_version == require_heuristic(expl.rule_id).version


def test_focus_term_selection_emits_rule() -> None:
    frag = SourceFragment(
        id="frag-focus",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:10:paragraph:1",
        fragment_type="paragraph",
        fragment_text="Measures for norwegian pout and related stocks.",
        fragment_hash="h1",
        order_index=1,
    )
    source = _source("src-1")
    decisions = _build_extraction_selection_decisions(
        [(source, frag)],
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(
            required_locators=set(),
            focus_terms=["norwegian pout"],
        ),
        fragment_selection_mode="required_plus_focus",
    )
    explanations = _explanations_for(
        decisions,
        _cfg(required_locators=set(), focus_terms=["norwegian pout"]),
    )
    assert any(e.rule_id == "selection.focus_term_match" for e in explanations)
    focus = next(e for e in explanations if e.rule_id == "selection.focus_term_match")
    assert any(ev.kind == "matched_focus_term" for ev in focus.evidence)
    assert decisions[0].matched_focus_terms == ("norwegian pout",)
    assert focus.metadata.get("focus_match_evidence_available") is True


def test_ordinary_exclusions() -> None:
    source = _source("src-1")
    non_op = SourceFragment(
        id="frag-recital",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="recital:1",
        fragment_type="recital",
        fragment_text=(
            "Whereas the union should act with sufficient length to exceed "
            "the minimum fragment character threshold for this test."
        ),
        fragment_hash="h1",
        order_index=1,
    )
    short = SourceFragment(
        id="frag-short",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:2",
        fragment_type="article",
        fragment_text="Short",
        fragment_hash="h2",
        order_index=2,
    )
    other = SourceFragment(
        id="frag-other",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:3",
        fragment_type="article",
        fragment_text="A sufficiently long operative fragment without focus terms present here.",
        fragment_hash="h3",
        order_index=3,
    )
    cfg_excl = _cfg(
        required_locators=set(),
        focus_terms=["zzzz"],
        min_fragment_chars=40,
    )
    decisions = _build_extraction_selection_decisions(
        [(source, non_op), (source, short), (source, other)],
        ext_mode="frontier",
        extraction_selection_cfg=cfg_excl,
        fragment_selection_mode="all_operative",
    )
    explanations = _explanations_for(decisions, cfg_excl)
    rules = {e.rule_id for e in explanations}
    assert "selection.skip_non_operative" in rules
    assert "selection.skip_too_short" in rules
    # no_focus_match noise should not be emitted
    assert not any(
        e.outcome == "not_selected_for_extraction"
        and e.rule_id not in {
            "selection.skip_non_operative",
            "selection.skip_too_short",
            "selection.skip_required_only_mode",
            "selection.prefer_required_children",
            "selection.prefer_required_ancestor",
        }
        for e in explanations
    )


def test_required_only_mode_exclusion() -> None:
    source = _source("src-1")
    frag = SourceFragment(
        id="frag-x",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:9",
        fragment_type="article",
        fragment_text="norwegian pout appears here with enough length.",
        fragment_hash="h1",
        order_index=1,
    )
    cfg = _cfg(required_locators={"article:1"}, focus_terms=["norwegian pout"])
    decisions = _build_extraction_selection_decisions(
        [(source, frag)],
        ext_mode="frontier",
        extraction_selection_cfg=cfg,
        fragment_selection_mode="required_only",
    )
    explanations = _explanations_for(decisions, cfg)
    assert any(e.rule_id == "selection.skip_required_only_mode" for e in explanations)


def test_unresolved_overlap_diagnostic() -> None:
    parent = SourceFragment(
        id="frag-p",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:5",
        fragment_type="article",
        fragment_text="Parent body containing child text alpha.",
        fragment_hash="hp",
        order_index=1,
    )
    child = SourceFragment(
        id="frag-c",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:5:paragraph:1",
        fragment_type="paragraph",
        fragment_text="child text alpha",
        fragment_hash="hc",
        parent_fragment_id="frag-p",
        order_index=2,
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
            selection_reason="required_locator",
            skip_reason=None,
            fragment_locator=child.locator,
            fragment_type=child.fragment_type,
            fragment_text_length=len(child.fragment_text),
        ),
    ]
    after = apply_required_ancestor_extraction_frontier(decisions)
    assert any(
        DIAGNOSTIC_UNRESOLVED_OVERLAP in d.selection_diagnostics for d in after
    )
    explanations = _explanations_for(after)
    diag = [e for e in explanations if e.rule_id == "selection.structural_overlap_unresolved"]
    assert diag
    assert all(e.decision_type.value == "diagnose" for e in diag)
    # Selection unchanged
    assert all(d.selected for d in after)


def test_no_contradictory_final_decisions_per_fragment() -> None:
    fragments = _load_49a_fragments()
    source = _source()
    jobs = [(source, frag) for frag in fragments]
    decisions = _build_extraction_selection_decisions(
        jobs,
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(),
        fragment_selection_mode="required_plus_focus",
    )
    explanations = _explanations_for(decisions)
    # For each subject, at most one select/suppress/exclude (diagnose may coexist)
    by_subject: dict[str, list] = {}
    for expl in explanations:
        if expl.decision_type.value == "diagnose":
            continue
        by_subject.setdefault(expl.subject_id, []).append(expl)
    for subject_id, rows in by_subject.items():
        outcomes = {(r.decision_type.value, r.outcome) for r in rows}
        assert len(outcomes) == 1, f"Contradictory finals for {subject_id}: {outcomes}"


def test_input_order_does_not_change_explanations() -> None:
    fragments = _load_49a_fragments()
    source = _source()
    jobs = [(source, frag) for frag in fragments]
    decisions = _build_extraction_selection_decisions(
        jobs,
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(),
        fragment_selection_mode="required_plus_focus",
    )
    a = [e.id for e in _explanations_for(decisions)]
    b = [e.id for e in _explanations_for(list(reversed(decisions)))]
    assert a == b


def test_cross_snapshot_children_never_preferred() -> None:
    parent = SourceFragment(
        id="frag-p",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:7",
        fragment_type="article",
        fragment_text="Parent covering child alpha completely here.",
        fragment_hash="hp",
        order_index=1,
    )
    child_other = SourceFragment(
        id="frag-c",
        source_record_id="src-1",
        source_snapshot_id="snap-OTHER",
        locator="article:7:paragraph:1",
        fragment_type="paragraph",
        fragment_text="child alpha",
        fragment_hash="hc",
        parent_fragment_id="frag-p",
        order_index=2,
    )
    decisions = [
        FragmentSelectionDecision(
            source_record_id="src-1",
            fragment=parent,
            selected=False,
            selection_reason="skipped_structural_children_preferred",
            skip_reason=SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
            fragment_locator=parent.locator,
            fragment_type=parent.fragment_type,
            fragment_text_length=len(parent.fragment_text),
        ),
        FragmentSelectionDecision(
            source_record_id="src-1",
            fragment=child_other,
            selected=True,
            selection_reason="required_locator",
            skip_reason=None,
            fragment_locator=child_other.locator,
            fragment_type=child_other.fragment_type,
            fragment_text_length=len(child_other.fragment_text),
        ),
    ]
    explanations = _explanations_for(decisions)
    parent_expl = [
        e for e in explanations if e.rule_id == "selection.prefer_required_children"
    ]
    assert parent_expl
    for expl in parent_expl:
        for alt in expl.alternatives:
            assert alt.id != "frag-c"


def test_artifact_wrapper_shape() -> None:
    fragments = _load_49a_fragments()
    source = _source()
    jobs = [(source, frag) for frag in fragments]
    decisions = _build_extraction_selection_decisions(
        jobs,
        ext_mode="frontier",
        extraction_selection_cfg=_cfg(),
        fragment_selection_mode="required_plus_focus",
    )
    explanations = _explanations_for(decisions)
    artifact = build_decision_explanations_artifact(run_id="run-demo", decisions=explanations)
    assert artifact["schema_version"] == "1"
    assert artifact["run_id"] == "run-demo"
    assert artifact["metadata"]["registry_version"] == "1"
    assert "referenced_rules" in artifact["metadata"]
    assert isinstance(artifact["decisions"], list)
