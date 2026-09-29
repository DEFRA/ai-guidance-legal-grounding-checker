"""Multi-instrument structural-source fidelity contract (Law Proposition Extractor-only, offline)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from law_proposition_extractor_domain import Cluster, SourceRecord, Topic
from law_proposition_extractor_pipeline.extract import (
    EXTRACTION_PROMPT_VERSION,
    _v2_model_prompt,
    _validate_v2_items,
    evidence_locates_verbatim_after_normalisation,
)
from law_proposition_extractor_pipeline.source_structure_audit import (
    assert_hierarchy_sound,
    assert_no_heading_leak,
    audit_structural_fragments,
    heading_leaks_into_operative_text,
    structural_rows_to_fragments,
)
from law_proposition_extractor_pipeline.source_structure_fixtures import (
    REPORT_RELATIVE,
    fixture_by_id,
    judit_root,
    known_unrepresented_patterns,
    load_structural_source_fixtures,
)
from law_proposition_extractor_pipeline.source_structure_inspector import (
    assert_no_path_leaks,
    check_all_structural_fixtures,
    check_fixture_suite_report,
    inspect_structural_fixture,
    render_fixture_suite_report,
    render_inspect_markdown,
    render_structure_tree,
)
from law_proposition_extractor_pipeline.sources.adapters import _build_legislation_structural_fragments
from law_proposition_extractor_pipeline.structural_headings import (
    format_heading_contexts_for_prompt,
    resolve_structural_heading_contexts,
)
from xml.etree import ElementTree


def _rows(path: Path) -> list[dict]:
    root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
    rows, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="https://www.legislation.gov.uk/offline/fixture/data.xml",
    )
    return rows


# ---------------------------------------------------------------------------
# Inventory / inspector
# ---------------------------------------------------------------------------


def test_manifest_registers_representative_fixtures() -> None:
    fixtures = load_structural_source_fixtures()
    ids = {f.fixture_id for f in fixtures}
    assert "article_49a_eur_2009_1224" in ids
    assert "uk_regulation_headed" in ids
    assert "multi_provision_cross_heading" in ids
    assert "wsi_regulation_36_paragraphs" in ids
    for fixture in fixtures:
        assert fixture.path.is_file(), fixture.relative_path


def test_inspector_parses_every_registered_fixture_deterministically() -> None:
    results_a = [inspect_structural_fixture(f).to_dict() for f in load_structural_source_fixtures()]
    results_b = [inspect_structural_fixture(f).to_dict() for f in load_structural_source_fixtures()]
    assert json.dumps(results_a, sort_keys=True) == json.dumps(results_b, sort_keys=True)
    for payload in results_a:
        text = json.dumps(payload, sort_keys=True)
        assert_no_path_leaks(text, label=payload["fixture_id"])
        assert "<Legislation" not in text


def test_tree_and_markdown_output_deterministic_and_path_safe() -> None:
    fixture = fixture_by_id("article_49a_eur_2009_1224")
    result = inspect_structural_fixture(fixture)
    tree_a = render_structure_tree(result.audit)
    tree_b = render_structure_tree(result.audit)
    assert tree_a == tree_b
    assert "TITLE IV" in tree_a
    assert "Article 49a" in tree_a
    md = render_inspect_markdown(result)
    assert md == render_inspect_markdown(result)
    assert_no_path_leaks(md, label="markdown")
    assert_no_path_leaks(tree_a, label="tree")


def test_check_all_structural_fixtures_passes() -> None:
    results = check_all_structural_fixtures()
    assert len(results) == len(load_structural_source_fixtures())
    assert all(r.audit.passed for r in results)


def test_heading_counts_match_parsed_fragments() -> None:
    for fixture in load_structural_source_fixtures():
        result = inspect_structural_fixture(fixture)
        headed = sum(1 for r in result.audit.fragment_rows if r.direct_heading_text)
        assert result.audit.heading_count == headed


def test_unassigned_headings_reported_for_multi_provision_fixture() -> None:
    result = inspect_structural_fixture(fixture_by_id("multi_provision_cross_heading"))
    assert result.audit.unassigned_headings
    assert all(
        "multi_provision_group_title_unassigned" in u.diagnostic
        for u in result.audit.unassigned_headings
    )


# ---------------------------------------------------------------------------
# EU structure
# ---------------------------------------------------------------------------


def test_article_49a_1_14_and_title_iv_headings() -> None:
    result = inspect_structural_fixture(fixture_by_id("article_49a_eur_2009_1224"))
    by_loc = {r.locator: r for r in result.audit.fragment_rows}
    assert by_loc["article:49a"].number_label == "Article 49a"
    assert by_loc["article:49a"].direct_heading_text == (
        "Separate stowage of catches below the minimum conservation reference sizes"
    )
    assert by_loc["article:1"].direct_heading_text == "Subject matter"
    assert by_loc["article:14"].direct_heading_text == (
        "Completion and submission of the fishing logbook"
    )
    title = by_loc["title:iv"]
    assert title.number_label == "TITLE IV"
    assert title.direct_heading_text == "CONTROL OF FISHERIES"
    assert title.operative_text_preview == "TITLE IV"


def test_article_49a_paragraphs_inherit_correct_path_no_sibling_leak() -> None:
    result = inspect_structural_fixture(fixture_by_id("article_49a_eur_2009_1224"))
    by_loc = {r.locator: r for r in result.audit.fragment_rows}
    for locator in (
        "article:49a:paragraph:1",
        "article:49a:paragraph:2",
        "article:49a:paragraph:3",
    ):
        path = by_loc[locator].inherited_heading_path
        assert path[0].startswith("TITLE IV")
        assert "Article 49a — Separate stowage" in path[-1]
        joined = " | ".join(path)
        assert "Subject matter" not in joined
        assert "fishing logbook" not in joined


def test_addition_wrapped_heading_provenance_retained() -> None:
    rows = _rows(fixture_by_id("article_49a_eur_2009_1224").path)
    art = next(r for r in rows if r["locator"] == "article:49a")
    heading = art["structural_heading"]
    assert "O003001M119" in heading["change_ids"]
    assert "c000004" in heading["commentary_refs"]


def test_sibling_articles_parts_container_headings() -> None:
    result = inspect_structural_fixture(fixture_by_id("sibling_articles_parts"))
    by_loc = {r.locator: r for r in result.audit.fragment_rows}
    assert by_loc["part:1"].direct_heading_text == "Part 1 General provisions"
    assert by_loc["chapter:2"].direct_heading_text == "Chapter 2 Stowage"
    assert by_loc["article:1"].parent_locator == "part:1"
    assert by_loc["article:2"].parent_locator == "part:1"
    assert by_loc["article:49a"].parent_locator == "chapter:2"
    assert by_loc["article:50"].parent_locator == "chapter:2"
    # Articles lack group titles in this fixture — valid missing heading.
    assert by_loc["article:49a"].direct_heading_text is None


# ---------------------------------------------------------------------------
# UK-style structure
# ---------------------------------------------------------------------------


def test_uk_regulation_part_heading_and_paragraph_parentage() -> None:
    result = inspect_structural_fixture(fixture_by_id("uk_regulation_headed"))
    by_loc = {r.locator: r for r in result.audit.fragment_rows}
    assert by_loc["part:2"].number_label == "PART 2"
    assert by_loc["part:2"].direct_heading_text == "Action programme"
    assert by_loc["regulation:12"].direct_heading_text == (
        "Spreading controls near surface water"
    )
    assert by_loc["regulation:12:paragraph:1"].parent_locator == "regulation:12"
    assert by_loc["regulation:12:paragraph:2"].parent_locator == "regulation:12"
    assert by_loc["regulation:13"].direct_heading_text is None
    assert by_loc["schedule:1"].number_label == "SCHEDULE 1"
    assert by_loc["schedule:1"].direct_heading_text == (
        "Calculating nitrogen in organic manure"
    )
    assert "Calculating nitrogen" not in by_loc["schedule:1"].operative_text_preview
    # Instrument title must not become a regulation heading.
    assert all(
        (r.direct_heading_text or "") != "The Nitrate Pollution Prevention Regulations 2015"
        for r in result.audit.fragment_rows
    )


def test_wsi_regulation_36_parentage_and_missing_heading() -> None:
    result = inspect_structural_fixture(fixture_by_id("wsi_regulation_36_paragraphs"))
    by_loc = {r.locator: r for r in result.audit.fragment_rows}
    assert by_loc["regulation:36"].direct_heading_text is None
    assert by_loc["regulation:36:paragraph:4"].parent_locator == "regulation:36"
    assert by_loc["schedule:1:paragraph:3"].parent_locator == "schedule:1"


# ---------------------------------------------------------------------------
# Cross-heading safety
# ---------------------------------------------------------------------------


def test_single_provision_group_heading_assigned_safely() -> None:
    result = inspect_structural_fixture(fixture_by_id("single_provision_headed_group"))
    by_loc = {r.locator: r for r in result.audit.fragment_rows}
    assert by_loc["article:49a"].direct_heading_text.startswith("Separate stowage")
    assert not result.audit.unassigned_headings


def test_multi_provision_heading_unassigned_and_absent_from_prompt_context() -> None:
    result = inspect_structural_fixture(fixture_by_id("multi_provision_cross_heading"))
    by_loc = {r.locator: r for r in result.audit.fragment_rows}
    assert by_loc["article:10"].direct_heading_text is None
    assert by_loc["article:11"].direct_heading_text is None
    fragments = structural_rows_to_fragments(_rows(fixture_by_id("multi_provision_cross_heading").path))
    by_id = {f.id: f for f in fragments}
    for frag in fragments:
        contexts = resolve_structural_heading_contexts(frag, by_id)
        assert contexts == []
        assert "Shared cross-heading" not in format_heading_contexts_for_prompt(contexts)


# ---------------------------------------------------------------------------
# Operative boundary + prompt v3 response contract
# ---------------------------------------------------------------------------


def test_no_operative_heading_leaks_across_matrix() -> None:
    for fixture in load_structural_source_fixtures():
        result = inspect_structural_fixture(fixture)
        assert_no_heading_leak(result.audit)
        assert_hierarchy_sound(result.audit)


def test_heading_only_evidence_and_proposition_rejected() -> None:
    heading = (
        "Separate stowage of catches below the minimum conservation reference sizes"
    )
    operative = (
        "A fisheries administration must monitor the catch composition by way of sampling."
    )
    ok, _, _ = evidence_locates_verbatim_after_normalisation(heading, operative)
    assert ok is False

    accepted, errors, issues = _validate_v2_items(
        [
            {
                "proposition_text": heading,
                "evidence_text": heading,
                "reason": "heading-only",
            }
        ],
        operative,
        limit=4,
    )
    assert accepted == []
    assert errors
    assert any(i.get("reason_code") == "no_verbatim_normalized_span" for i in issues)

    # Operative evidence still accepted.
    accepted2, errors2, _ = _validate_v2_items(
        [
            {
                "proposition_text": "A fisheries administration must monitor catch composition.",
                "evidence_text": (
                    "A fisheries administration must monitor the catch composition "
                    "by way of sampling."
                ),
            }
        ],
        operative,
        limit=4,
    )
    assert len(accepted2) == 1
    assert errors2 == []


def test_prompt_v3_separates_heading_block_for_eu_and_uk() -> None:
    assert EXTRACTION_PROMPT_VERSION == "v3"
    cases = [
        (
            "article_49a_eur_2009_1224",
            "article:49a:paragraph:1",
            "TITLE IV — CONTROL OF FISHERIES",
            "Article 49a — Separate stowage",
        ),
        (
            "uk_regulation_headed",
            "regulation:12:paragraph:1",
            "PART 2 — Action programme",
            "Spreading controls near surface water",
        ),
        (
            "wsi_regulation_36_paragraphs",
            "regulation:36:paragraph:1",
            None,
            None,
        ),
    ]
    for fixture_id, locator, expect_a, expect_b in cases:
        rows = _rows(fixture_by_id(fixture_id).path)
        fragments = structural_rows_to_fragments(rows)
        by_id = {f.id: f for f in fragments}
        frag = next(f for f in fragments if f.locator == locator)
        contexts = resolve_structural_heading_contexts(frag, by_id)
        source = SourceRecord(
            id="src",
            title="t",
            jurisdiction="UK",
            citation="c",
            kind="regulation",
            authoritative_text=frag.fragment_text,
            metadata={
                "structural_heading_contexts": [
                    {
                        "kind": c.kind.value if hasattr(c.kind, "value") else c.kind,
                        "number_label": c.number_label,
                        "heading_text": c.heading_text,
                        "owner_locator": c.owner_locator,
                    }
                    for c in contexts
                ]
            },
        )
        prompt = _v2_model_prompt(
            source,
            Topic(id="t", name="Topic"),
            Cluster(id="c", topic_id="t", name="Cluster"),
            extraction_mode="frontier",
        )
        assert "Operative source text:" in prompt
        if expect_a is None:
            # Heading-less provision still produces a valid prompt.
            assert frag.fragment_text in prompt
            continue
        assert "Structural legislative context" in prompt
        assert "non-operative headings" in prompt
        assert expect_a in prompt
        if expect_b:
            assert expect_b in prompt
        operative_idx = prompt.index("Operative source text:")
        if contexts:
            heading_idx = prompt.index("Structural legislative context")
            assert heading_idx < operative_idx
            for ctx in contexts:
                if ctx.heading_text and len(ctx.heading_text) >= 12:
                    assert ctx.heading_text not in prompt[operative_idx:]


def test_label_using_heading_concept_does_not_inject_operative_content() -> None:
    """Display label may mention heading concepts; evidence must still be operative."""
    operative = "All catches below the applicable minimum conservation reference size shall be placed in boxes."
    accepted, errors, _ = _validate_v2_items(
        [
            {
                "proposition_text": "Separate stowage obligation for undersized catches",
                "evidence_text": operative,
            }
        ],
        operative,
        limit=4,
    )
    assert len(accepted) == 1
    assert errors == []
    assert accepted[0]["evidence_text"] == operative


# ---------------------------------------------------------------------------
# Hierarchy / defensive
# ---------------------------------------------------------------------------


def test_broken_parent_and_cycle_produce_diagnostics() -> None:
    from law_proposition_extractor_domain import StructuralHeading
    from law_proposition_extractor_pipeline.source_fragmentation import content_hash
    from law_proposition_extractor_domain import SourceFragment

    a = SourceFragment(
        id="f-a",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:49a",
        fragment_text="body a",
        fragment_hash=content_hash("body a"),
        parent_fragment_id="f-b",
        structural_heading=StructuralHeading(kind="article", text="Heading A"),
    )
    b = SourceFragment(
        id="f-b",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:49a:paragraph:1",
        fragment_text="body b",
        fragment_hash=content_hash("body b"),
        parent_fragment_id="f-a",
    )
    audit = audit_structural_fragments([a, b])
    assert audit.cycle_issues
    with pytest.raises(AssertionError, match="cyclic"):
        assert_hierarchy_sound(audit)

    foreign = SourceFragment(
        id="f-foreign",
        source_record_id="src-other",
        source_snapshot_id="snap-1",
        locator="title:iv",
        fragment_text="x",
        fragment_hash=content_hash("x"),
    )
    child = SourceFragment(
        id="f-child",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:1",
        fragment_text="y",
        fragment_hash=content_hash("y"),
        parent_fragment_id="f-foreign",
    )
    audit2 = audit_structural_fragments([foreign, child])
    assert audit2.cross_source_parent_issues


def test_heading_leak_helper_and_audit_field() -> None:
    assert heading_leaks_into_operative_text(
        fragment_text="Separate stowage of catches below the minimum conservation reference sizes applies",
        heading_text="Separate stowage of catches below the minimum conservation reference sizes",
    )
    assert not heading_leaks_into_operative_text(
        fragment_text="TITLE IV",
        heading_text="CONTROL OF FISHERIES",
        number_label="TITLE IV",
    )


# ---------------------------------------------------------------------------
# Article 49a invariants via structural contract (no Proposition Matcher changes)
# ---------------------------------------------------------------------------


def test_article_49a_tree_shape_for_contract() -> None:
    result = inspect_structural_fixture(fixture_by_id("article_49a_eur_2009_1224"))
    tree = result.tree_markdown
    assert "TITLE IV — CONTROL OF FISHERIES" in tree
    assert "Article 49a — Separate stowage" in tree
    # Paragraph children present under the article.
    assert "paragraph:1" in " ".join(r.locator for r in result.audit.fragment_rows)
    assert "paragraph:2" in " ".join(r.locator for r in result.audit.fragment_rows)
    assert "paragraph:3" in " ".join(r.locator for r in result.audit.fragment_rows)


def test_article_49a_acceptance_still_six_propositions() -> None:
    props_path = (
        judit_root()
        / "tests/fixtures/article_49a_legal_structure/serialized/propositions.json"
    )
    props = json.loads(props_path.read_text(encoding="utf-8"))
    assert isinstance(props, list)
    assert len(props) == 6


# ---------------------------------------------------------------------------
# Documentation / report
# ---------------------------------------------------------------------------


def test_structural_fixture_report_current_and_safe() -> None:
    report_path = judit_root() / REPORT_RELATIVE
    # Generate if missing so first run in a clean tree can still assert shape;
    # CI/check uses check_fixture_suite_report for staleness.
    if not report_path.is_file():
        from law_proposition_extractor_pipeline.source_structure_inspector import write_fixture_suite_report

        write_fixture_suite_report()
    check_fixture_suite_report()
    text = report_path.read_text(encoding="utf-8")
    assert_no_path_leaks(text, label="report")
    assert "Known structural patterns not yet represented offline" in text
    assert "article_49a_eur_2009_1224" in text
    for item in known_unrepresented_patterns():
        assert item in text
    assert not re.search(r"file://", text)


def test_report_render_deterministic() -> None:
    assert render_fixture_suite_report() == render_fixture_suite_report()
