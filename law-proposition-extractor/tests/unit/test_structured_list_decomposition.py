"""Structured-list leaf decomposition (Article 49a-shaped + general)."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_domain import Cluster, ReviewStatus, SourceFragment, SourceRecord, Topic
from law_proposition_extractor_domain.proposition_classification import classify_extracted_proposition
from law_proposition_extractor_pipeline.extract import (
    _build_propositions_from_v2_rows,
    evidence_locates_verbatim_after_normalisation,
    extract_propositions,
)
from law_proposition_extractor_pipeline.fragment_anchor_coverage import check_structured_list_terminal_coverage
from law_proposition_extractor_pipeline.legal_rule_groups import build_legal_rule_groups
from law_proposition_extractor_pipeline.legal_rule_relationships import build_legal_rule_relationships
from law_proposition_extractor_pipeline.structural_child_extraction_preference import (
    SKIP_REASON_COVERED_BY_SELECTED_CHILDREN,
    FragmentSelectionDecision,
    apply_structural_child_extraction_preference,
)
from law_proposition_extractor_pipeline.structured_list_decomposition import (
    COMPOSITION_BASIS,
    COVERAGE_DIAGNOSTIC,
    draft_structured_list_leaves,
    draft_to_v2_row,
    fold_exceptions_for_row,
    leaf_components_traceable,
    merge_structured_leaf_rows,
    rows_include_standalone_derogation,
    unmatched_terminal_diagnostics,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)

P2_TEXT = (
    "(2) Paragraph 1 shall not apply: (a) where the catches contain more than 80% of one "
    "or more of the following species— (i)) mackerel, herring, horse mackerel, blue whiting, "
    "boarfish, anchovy, argentine, sardine, sprat (i.e. small pelagic fisheries); (ii)) "
    "capelin, sandeel, Norwegian pout (i.e. fisheries for industrial purposes); (b) to "
    "fishing vessels of less than 12 metres' length overall where catches below the minimum "
    "conservation reference size have been sorted, estimated and recorded in accordance with "
    "Article 14 of this Regulation."
)

P1_TEXT = (
    "(1) All catches below the applicable minimum conservation reference size retained on "
    "board a United Kingdom fishing vessel shall be placed in boxes, compartments or "
    "containers in such a way that they are identifiable from other boxes, compartments or "
    "containers. Those catches shall not be mixed with any other fishery products."
)


def _topic() -> Topic:
    return Topic(id="topic-fish", name="Fish control")


def _cluster() -> Cluster:
    return Cluster(id="cluster-fish", topic_id="topic-fish", name="Catch segregation")


def _source(*, text: str, locator: str, frag_id: str = "frag-x") -> SourceRecord:
    return SourceRecord(
        id="src-control-regulation-demo",
        title="Control regulation demo",
        jurisdiction="UK",
        citation="demo",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator=locator,
        current_snapshot_id="snap-src-control-regulation-demo-v1",
        review_status=ReviewStatus.PROPOSED,
        metadata={"extraction_fragment_id": frag_id},
    )


def test_paragraph_2_yields_three_derogation_leaves_in_source_order() -> None:
    drafts = draft_structured_list_leaves(P2_TEXT, "article:49a:paragraph:2")
    assert [d.marker_label for d in drafts] == ["(a)->(i)", "(a)->(ii)", "(b)"]
    assert [d.path_key for d in drafts] == ["2-a-i", "2-a-ii", "2-b"]
    assert all(d.is_derogation for d in drafts)

    props = extract_propositions(
        source=_source(text=P2_TEXT, locator="article:49a:paragraph:2", frag_id="frag-demo-49a-p2"),
        topic=_topic(),
        cluster=_cluster(),
        limit=10,
        llm_client=None,
    )
    assert len(props) == 3
    assert [p.fragment_locator for p in props] == [
        "article:49a:paragraph:2:list:2-a-i",
        "article:49a:paragraph:2:list:2-a-ii",
        "article:49a:paragraph:2:list:2-b",
    ]
    for p in props:
        assert "paragraph 1 shall not apply" in p.proposition_text.lower()
        meta = p.extraction_debug_meta or {}
        assert meta.get("provision_type") == "exception"
        assert meta.get("composition_basis") == COMPOSITION_BASIS
        assert meta.get("source_component_locators")
        effect = classify_extracted_proposition(
            proposition_text=p.proposition_text,
            extraction_meta=meta,
            provision_type=str(meta.get("provision_type") or ""),
        )
        assert effect.legal_effect_type.value == "derogation"


def test_a_leaves_inherit_branch_b_does_not() -> None:
    drafts = draft_structured_list_leaves(P2_TEXT, "article:49a:paragraph:2")
    a_i, a_ii, b = drafts
    assert "80%" in a_i.branch_context
    assert "80%" in a_ii.branch_context
    assert a_i.branch_context == a_ii.branch_context
    assert not b.branch_context
    assert "mackerel" in a_i.standalone_text.lower()
    assert "capelin" in a_ii.standalone_text.lower()
    assert "mackerel" not in a_ii.standalone_text.lower()
    assert "12 metres" in b.standalone_text.lower()
    assert "80%" not in b.standalone_text


def test_cross_refs_paragraph_1_and_article_14_only_on_b() -> None:
    drafts = draft_structured_list_leaves(P2_TEXT, "article:49a:paragraph:2")
    assert drafts[0].cross_reference_targets == ("paragraph 1",)
    assert drafts[1].cross_reference_targets == ("paragraph 1",)
    assert drafts[2].cross_reference_targets == ("paragraph 1", "article 14")


def test_no_stem_or_branch_only_proposition() -> None:
    props = extract_propositions(
        source=_source(text=P2_TEXT, locator="article:49a:paragraph:2"),
        topic=_topic(),
        cluster=_cluster(),
        limit=10,
        llm_client=None,
    )
    texts = [p.proposition_text.lower() for p in props]
    assert not any(t.strip() == "paragraph 1 shall not apply" for t in texts)
    assert not any(
        "80%" in t and "mackerel" not in t and "capelin" not in t and "12 metres" not in t
        for t in texts
    )


def test_paragraph_1_still_two_propositions() -> None:
    props = extract_propositions(
        source=_source(text=P1_TEXT, locator="article:49a:paragraph:1", frag_id="frag-demo-49a-p1"),
        topic=_topic(),
        cluster=_cluster(),
        limit=10,
        llm_client=None,
    )
    assert len(props) == 2
    joined = " ".join(p.proposition_text.lower() for p in props)
    assert "identifiable" in joined or "placed" in joined
    assert "mixed" in joined


def test_evidence_components_traceable_without_fabricating_contiguous_span() -> None:
    drafts = draft_structured_list_leaves(P2_TEXT, "article:49a:paragraph:2")
    for d in drafts:
        ok, details = leaf_components_traceable(
            d, P2_TEXT, locate_fn=evidence_locates_verbatim_after_normalisation
        )
        assert ok, details
        assert {c["role"] for c in details} >= {"stem", "leaf"}


def test_composed_evidence_passes_validation_via_components() -> None:
    from law_proposition_extractor_pipeline.extract import _validate_v2_items

    drafts = draft_structured_list_leaves(P2_TEXT, "article:49a:paragraph:2")
    rows = [
        draft_to_v2_row(d, source_locator=f"article:49a:paragraph:2:list:{d.path_key}")
        for d in drafts
    ]
    accepted, errors, _issues = _validate_v2_items(rows, P2_TEXT, limit=10)
    assert not errors
    assert len(accepted) == 3


def test_missing_terminal_produces_coverage_diagnostic() -> None:
    drafts = draft_structured_list_leaves(P2_TEXT, "article:49a:paragraph:2")
    diags = unmatched_terminal_diagnostics(
        expected=drafts,
        covered_path_keys=["2-a-i", "2-b"],
        fragment_locator="article:49a:paragraph:2",
    )
    assert len(diags) == 1
    assert diags[0]["code"] == COVERAGE_DIAGNOSTIC
    assert diags[0]["structured_list_path"] == "2-a-ii"

    props = extract_propositions(
        source=_source(text=P2_TEXT, locator="article:49a:paragraph:2"),
        topic=_topic(),
        cluster=_cluster(),
        limit=10,
        llm_client=None,
    )
    coverage = check_structured_list_terminal_coverage(
        fragment_text=P2_TEXT,
        fragment_locator="article:49a:paragraph:2",
        proposition_rows=[p.model_dump(mode="json") for p in props],
    )
    assert coverage["all_covered"] is True
    assert set(coverage["expected_terminals"]) == {"2-a-i", "2-a-ii", "2-b"}


def test_exceptions_fold_suppressed_when_standalone_derogations_exist() -> None:
    rows = [
        {
            "proposition_text": "Catches shall be kept identifiable.",
            "provision_type": "core",
            "exceptions": ["where paragraph 2 applies"],
            "conditions": [],
        },
        {
            "proposition_text": "Paragraph 1 shall not apply where catches are mostly pelagic.",
            "provision_type": "exception",
            "exceptions": [],
            "conditions": ["catches mostly pelagic"],
        },
    ]
    assert rows_include_standalone_derogation(rows) is True
    core_conds = fold_exceptions_for_row(
        row=rows[0], conditions=[], fragment_has_standalone_derogation=True
    )
    assert core_conds == []


def test_subordinate_exceptions_still_fold_without_standalone_derogation() -> None:
    row = {
        "proposition_text": "No person may spread slurry near water.",
        "provision_type": "core",
        "exceptions": ["where paragraph 26 applies"],
        "conditions": [],
    }
    assert rows_include_standalone_derogation([row]) is False
    conds = fold_exceptions_for_row(
        row=row, conditions=[], fragment_has_standalone_derogation=False
    )
    assert conds == ["exception: where paragraph 26 applies"]


def test_simple_non_nested_exception_still_extracts() -> None:
    text = "(2) Paragraph 1 shall not apply to shore-based establishments."
    drafts = draft_structured_list_leaves(text, "article:30:paragraph:2")
    assert drafts == []
    props = extract_propositions(
        source=_source(text=text, locator="article:30:paragraph:2"),
        topic=_topic(),
        cluster=_cluster(),
        limit=5,
        llm_client=None,
    )
    assert props
    assert any("shall not apply" in p.proposition_text.lower() for p in props)


def test_multiline_vehicle_list_yields_two_leaves() -> None:
    text = """A person must not—
(a) use a vehicle to—
(i) carry X
(ii) carry Y
(b) leave the vehicle unattended.
"""
    drafts = draft_structured_list_leaves(text, "regulation:1")
    assert len(drafts) >= 3
    markers = [d.marker_label for d in drafts]
    assert "(a)->(i)" in markers
    assert "(a)->(ii)" in markers
    assert "(b)" in markers
    a_i = next(d for d in drafts if d.marker_label == "(a)->(i)")
    a_ii = next(d for d in drafts if d.marker_label == "(a)->(ii)")
    assert "carry x" in a_i.standalone_text.lower()
    assert "carry y" in a_ii.standalone_text.lower()
    assert "use a vehicle" in a_i.branch_context.lower()


def test_merge_fills_missing_a_ii_from_partial_llm_rows() -> None:
    drafts = draft_structured_list_leaves(P2_TEXT, "article:49a:paragraph:2")
    partial = [
        {
            "proposition_text": "Paragraph 1 shall not apply where catches are mostly mackerel.",
            "provision_type": "exception",
            "source_locator": "article 49a, paragraph 2(a)(i)",
            "evidence_text": "mackerel, herring, horse mackerel",
            "conditions": [],
            "exceptions": [],
        },
        {
            "proposition_text": "Paragraph 1 shall not apply to vessels under 12 metres.",
            "provision_type": "exception",
            "source_locator": "article 49a, paragraph 2(b)",
            "evidence_text": "fishing vessels of less than 12 metres",
            "conditions": [],
            "exceptions": [],
        },
    ]
    merged, _diags, _facts = merge_structured_leaf_rows(
        existing_rows=partial,
        drafts=drafts,
        base_locator="article:49a:paragraph:2",
        limit=10,
    )
    paths = [
        str((r.get("_structured_list_meta") or {}).get("structured_list_path") or "")
        for r in merged
    ]
    assert "2-a-ii" in paths
    texts = " ".join(str(r.get("proposition_text") or "").lower() for r in merged)
    assert "capelin" in texts


def test_build_v2_rows_skips_opaque_exception_prefix_with_standalone() -> None:
    rows = [
        {
            "proposition_text": "Catches must be identifiable.",
            "subject": "catches",
            "rule": "must be identifiable",
            "object": "",
            "conditions": [],
            "exceptions": ["where paragraph 2(a) applies"],
            "source_locator": "article:49a:paragraph:1",
            "provision_type": "core",
        },
        {
            "proposition_text": "Paragraph 1 shall not apply where catches are pelagic.",
            "subject": "",
            "rule": "shall not apply",
            "object": "",
            "conditions": ["catches are pelagic"],
            "exceptions": [],
            "source_locator": "article:49a:paragraph:2:list:2-a-i",
            "provision_type": "exception",
        },
    ]
    props = _build_propositions_from_v2_rows(
        rows=rows,
        source=_source(text=P1_TEXT + " " + P2_TEXT, locator="article:49a"),
        topic=_topic(),
        cluster=_cluster(),
        limit=10,
    )
    assert not any(str(c).startswith("exception:") for c in props[0].conditions)


def test_fixture_groups_and_three_exception_to_edges() -> None:
    payload = json.loads(FIXTURE.read_text())
    source_id = payload["source_record_id"]
    snapshot_id = payload["source_snapshot_id"]
    other = payload["other_instrument"]

    frags: list[dict] = []
    for row in payload["fragments"]:
        frags.append(
            {
                **row,
                "source_record_id": source_id,
                "source_snapshot_id": snapshot_id,
            }
        )
    for row in other["fragments"]:
        frags.append(
            {
                **row,
                "source_record_id": other["source_record_id"],
                "source_snapshot_id": other["source_snapshot_id"],
            }
        )

    props: list[dict] = []
    for row in payload["exported_propositions"]:
        props.append(
            {
                "id": row["id"],
                "source_record_id": source_id,
                "source_snapshot_id": snapshot_id,
                "source_fragment_id": row["source_fragment_id"],
                "fragment_locator": row["fragment_locator"],
                "proposition_text": row["proposition_text"],
                "legal_effect_type": row["legal_effect_type"],
                "explicit_cross_reference_targets": row.get(
                    "explicit_cross_reference_targets", []
                ),
                "source_order": row.get("source_order", 0),
            }
        )
    for row in other["exported_propositions"]:
        props.append(
            {
                "id": row["id"],
                "source_record_id": other["source_record_id"],
                "source_snapshot_id": other["source_snapshot_id"],
                "source_fragment_id": row["source_fragment_id"],
                "fragment_locator": row["fragment_locator"],
                "proposition_text": row["proposition_text"],
                "legal_effect_type": row["legal_effect_type"],
                "explicit_cross_reference_targets": row.get(
                    "explicit_cross_reference_targets", []
                ),
                "source_order": row.get("source_order", 0),
            }
        )

    groups = build_legal_rule_groups(props, run_id="run-49a", source_fragments=frags)
    p2 = next(
        g
        for g in groups["groups"]
        if g["canonical_locator"] == "article:49a:paragraph:2"
        and g["source_record_id"] == source_id
    )
    assert p2["member_proposition_ids"] == [
        "prop-demo-49a-p2-pelagic",
        "prop-demo-49a-p2-industrial",
        "prop-demo-49a-p2-small-vessels",
    ]

    rels = build_legal_rule_relationships(
        props, run_id="run-49a", source_fragments=frags, legal_rule_groups=groups
    )
    exception_sources = {
        r["source_id"]
        for r in rels["relationships"]
        if r["relationship_type"] == "exception_to"
        and r["source_record_id"] == source_id
        and r["source_id"].startswith("prop-demo-49a-p2")
    }
    assert exception_sources == {
        "prop-demo-49a-p2-pelagic",
        "prop-demo-49a-p2-industrial",
        "prop-demo-49a-p2-small-vessels",
    }
    assert not any(
        r["relationship_type"] == "exception_to"
        and "14" in str(r.get("referenced_locator") or "")
        for r in rels["relationships"]
    )
    monitoring = next(
        r for r in rels["relationships"] if r["source_id"] == "prop-demo-49a-p3-monitoring"
    )
    assert monitoring["relationship_type"] == "triggered_by"


def test_output_deterministic_across_calls() -> None:
    source = _source(text=P2_TEXT, locator="article:49a:paragraph:2")
    a = extract_propositions(
        source=source, topic=_topic(), cluster=_cluster(), limit=10, llm_client=None
    )
    b = extract_propositions(
        source=source, topic=_topic(), cluster=_cluster(), limit=10, llm_client=None
    )
    assert [p.id for p in a] == [p.id for p in b]
    assert [p.proposition_text for p in a] == [p.proposition_text for p in b]


def test_structural_child_preference_still_suppresses_parent() -> None:
    from law_proposition_extractor_pipeline.runner import _is_non_operative_fragment

    payload = json.loads(FIXTURE.read_text())
    source_id = str(payload["source_record_id"])
    snapshot_id = str(payload["source_snapshot_id"])
    fragments = [
        SourceFragment(
            id=str(f["id"]),
            source_record_id=source_id,
            source_snapshot_id=snapshot_id,
            locator=str(f["locator"]),
            fragment_type=str(f["fragment_type"]),
            parent_fragment_id=f.get("parent_fragment_id"),
            order_index=int(f["order_index"]),
            fragment_text=str(f["fragment_text"]),
            fragment_hash=f"hash-{f['id']}",
        )
        for f in payload["fragments"]
        if str(f["locator"]).startswith("article:49a")
    ]
    by_loc = {f.locator: f for f in fragments}

    def decision(frag: SourceFragment, *, selected: bool) -> FragmentSelectionDecision:
        return FragmentSelectionDecision(
            source_record_id=frag.source_record_id,
            fragment=frag,
            selected=selected,
            selection_reason="focus_term_match" if selected else "skipped_no_focus_match",
            skip_reason=None if selected else "no_focus_match",
            fragment_locator=frag.locator,
            fragment_type=frag.fragment_type,
            fragment_text_length=len(frag.fragment_text),
        )

    preferred = apply_structural_child_extraction_preference(
        [
            decision(by_loc["article:49a"], selected=True),
            decision(by_loc["article:49a:paragraph:1"], selected=True),
            decision(by_loc["article:49a:paragraph:2"], selected=True),
            decision(by_loc["article:49a:paragraph:3"], selected=True),
        ],
        is_non_operative_fragment=_is_non_operative_fragment,
    )
    parent = next(d for d in preferred if d.fragment_locator == "article:49a")
    assert parent.selected is False
    assert parent.skip_reason == SKIP_REASON_COVERED_BY_SELECTED_CHILDREN
