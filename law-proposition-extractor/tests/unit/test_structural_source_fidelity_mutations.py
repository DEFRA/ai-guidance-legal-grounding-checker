"""Mutation tests for structural-source fidelity (source-boundary oriented)."""

from __future__ import annotations

import copy
import json

import pytest

from law_proposition_extractor_domain import Cluster, SourceFragment, SourceRecord, StructuralHeading, Topic
from law_proposition_extractor_pipeline.extract import _v2_model_prompt, _validate_v2_items
from law_proposition_extractor_pipeline.source_fragmentation import content_hash
from law_proposition_extractor_pipeline.source_structure_audit import (
    assert_hierarchy_sound,
    assert_no_heading_leak,
    audit_structural_fragments,
    structural_rows_to_fragments,
)
from law_proposition_extractor_pipeline.source_structure_fixtures import fixture_by_id
from law_proposition_extractor_pipeline.source_structure_inspector import (
    check_structural_fixture,
    inspect_structural_fixture,
    render_inspect_markdown,
)
from law_proposition_extractor_pipeline.sources.adapters import _build_legislation_structural_fragments
from law_proposition_extractor_pipeline.structural_headings import resolve_structural_heading_contexts
from xml.etree import ElementTree


def _article_49a_rows() -> list[dict]:
    path = fixture_by_id("article_49a_eur_2009_1224").path
    root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
    rows, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
    )
    return rows


def _assert_no_forbidden_heading(contexts, *, needle: str, message: str) -> None:
    if any(needle in (c.heading_text or "") for c in contexts):
        raise AssertionError(message)


def test_mutation_heading_inserted_into_operative_fragment_text() -> None:
    rows = copy.deepcopy(_article_49a_rows())
    for row in rows:
        if row["locator"] == "article:49a":
            heading = row["structural_heading"]["text"]
            row["text"] = f"{heading} {row['text']}"
    audit = audit_structural_fragments(structural_rows_to_fragments(rows))
    with pytest.raises(AssertionError, match="leaked into operative"):
        assert_no_heading_leak(audit)


def test_mutation_article_heading_assigned_to_sibling_leaks_via_parent() -> None:
    fragments = structural_rows_to_fragments(_article_49a_rows())
    by_id = {f.id: f for f in fragments}
    art1 = next(f for f in fragments if f.locator == "article:1")
    para3 = next(f for f in fragments if f.locator == "article:49a:paragraph:3")
    leaked = para3.model_copy(update={"parent_fragment_id": art1.id})
    contexts = resolve_structural_heading_contexts(leaked, {**by_id, leaked.id: leaked})
    with pytest.raises(AssertionError, match="sibling article"):
        _assert_no_forbidden_heading(
            contexts,
            needle="Subject matter",
            message=(
                "Source-fidelity failure: article heading assigned to a sibling article "
                "path (Article 1 heading visible on Article 49a paragraph)"
            ),
        )


def test_mutation_article_1_parented_above_49a() -> None:
    fragments = structural_rows_to_fragments(_article_49a_rows())
    art1 = next(f for f in fragments if f.locator == "article:1")
    art49a = next(f for f in fragments if f.locator == "article:49a")
    broken = [
        art49a.model_copy(update={"parent_fragment_id": art1.id})
        if f.id == art49a.id
        else f
        for f in fragments
    ]
    audit = audit_structural_fragments(broken)
    with pytest.raises(AssertionError, match="sibling_provision_parented|parentage"):
        assert_hierarchy_sound(audit)


def test_mutation_article_14_heading_inherited_by_paragraph_3() -> None:
    fragments = structural_rows_to_fragments(_article_49a_rows())
    by_id = {f.id: f for f in fragments}
    art14 = next(f for f in fragments if f.locator == "article:14")
    para3 = next(f for f in fragments if f.locator == "article:49a:paragraph:3")
    leaked = para3.model_copy(update={"parent_fragment_id": art14.id})
    contexts = resolve_structural_heading_contexts(leaked, {**by_id, leaked.id: leaked})
    with pytest.raises(AssertionError, match="Article 14 heading inherited"):
        _assert_no_forbidden_heading(
            contexts,
            needle="fishing logbook",
            message=(
                "Source-fidelity failure: Article 14 heading inherited by "
                "article:49a:paragraph:3"
            ),
        )


def test_mutation_multi_provision_heading_assigned_arbitrarily() -> None:
    result = inspect_structural_fixture(fixture_by_id("multi_provision_cross_heading"))
    assert all(r.direct_heading_text is None for r in result.audit.fragment_rows)

    def _assert_unassigned(rows) -> None:
        for row in rows:
            if row.direct_heading_text:
                raise AssertionError(
                    "Source-fidelity failure: multi-provision cross-heading was "
                    f"assigned to {row.locator}"
                )

    mutated = copy.deepcopy(result.audit.fragment_rows)
    for row in mutated:
        if row.locator == "article:10":
            row.direct_heading_text = "Shared cross-heading for sibling articles"
    with pytest.raises(AssertionError, match="multi-provision cross-heading was assigned"):
        _assert_unassigned(mutated)


def test_mutation_commentary_not_captured_as_heading() -> None:
    result = inspect_structural_fixture(fixture_by_id("article_49a_eur_2009_1224"))
    by_loc = {r.locator: r for r in result.audit.fragment_rows}
    text = by_loc["article:1"].direct_heading_text or ""
    assert text == "Subject matter"
    assert "Footnote" not in text
    assert "commentary" not in text.lower()


def test_mutation_instrument_title_as_provision_heading() -> None:
    result = inspect_structural_fixture(fixture_by_id("uk_regulation_headed"))
    instrument = result.audit.instrument_title or ""
    assert instrument
    for row in result.audit.fragment_rows:
        assert row.direct_heading_text != instrument


def test_mutation_container_number_replacing_descriptive_heading() -> None:
    result = inspect_structural_fixture(fixture_by_id("article_49a_eur_2009_1224"))
    title = next(r for r in result.audit.fragment_rows if r.locator == "title:iv")
    assert title.number_label == "TITLE IV"
    assert title.direct_heading_text == "CONTROL OF FISHERIES"
    # Mutate number/heading swap and ensure a checker would catch it.
    title.number_label = "CONTROL OF FISHERIES"
    title.direct_heading_text = "TITLE IV"

    def _assert_title_iv_split(number_label: str | None, heading: str | None) -> None:
        if number_label != "TITLE IV" or heading != "CONTROL OF FISHERIES":
            raise AssertionError(
                "Source-fidelity failure: container number replaced descriptive heading"
            )

    with pytest.raises(AssertionError, match="container number replaced"):
        _assert_title_iv_split(title.number_label, title.direct_heading_text)


def test_mutation_heading_omitted_from_prompt_structural_context() -> None:
    fragments = structural_rows_to_fragments(_article_49a_rows())
    by_id = {f.id: f for f in fragments}
    para = next(f for f in fragments if f.locator == "article:49a:paragraph:1")
    contexts = resolve_structural_heading_contexts(para, by_id)
    assert contexts
    source = SourceRecord(
        id="src",
        title="t",
        jurisdiction="UK",
        citation="c",
        kind="regulation",
        authoritative_text=para.fragment_text,
        metadata={"structural_heading_contexts": []},
    )
    prompt = _v2_model_prompt(
        source,
        Topic(id="t", name="Topic"),
        Cluster(id="c", topic_id="t", name="Cluster"),
        extraction_mode="frontier",
    )

    def _assert_prompt_keeps_heading_block(text: str) -> None:
        if "Structural legislative context" not in text:
            raise AssertionError(
                "Source-fidelity failure: heading omitted from prompt structural context"
            )

    with pytest.raises(AssertionError, match="heading omitted from prompt"):
        _assert_prompt_keeps_heading_block(prompt)


def test_mutation_heading_must_not_appear_in_operative_prompt_section() -> None:
    heading = (
        "Separate stowage of catches below the minimum conservation reference sizes"
    )
    source = SourceRecord(
        id="src",
        title="t",
        jurisdiction="UK",
        citation="c",
        kind="regulation",
        authoritative_text="Operative body only about sampling.",
        metadata={
            "structural_heading_contexts": [
                {
                    "kind": "article",
                    "number_label": "Article 49a",
                    "heading_text": heading,
                    "owner_locator": "article:49a",
                }
            ]
        },
    )
    prompt = _v2_model_prompt(
        source,
        Topic(id="t", name="Topic"),
        Cluster(id="c", topic_id="t", name="Cluster"),
        extraction_mode="frontier",
    )
    operative_idx = prompt.index("Operative source text:")
    assert heading in prompt[:operative_idx]
    assert heading not in prompt[operative_idx:]


def test_mutation_heading_accepted_as_proposition_evidence() -> None:
    heading = (
        "Separate stowage of catches below the minimum conservation reference sizes"
    )
    operative = "All catches shall be placed in boxes."
    accepted, _, _ = _validate_v2_items(
        [{"proposition_text": "Separate stowage rule", "evidence_text": heading}],
        operative,
        limit=4,
    )

    def _assert_heading_evidence_rejected(rows: list) -> None:
        if rows:
            raise AssertionError(
                "Source-fidelity failure: heading accepted as proposition evidence"
            )

    _assert_heading_evidence_rejected(accepted)


def test_mutation_heading_emitted_as_seventh_proposition() -> None:
    props_path = (
        fixture_by_id("article_49a_eur_2009_1224").path.parent
        / "serialized"
        / "propositions.json"
    )
    props = json.loads(props_path.read_text(encoding="utf-8"))
    assert len(props) == 6
    mutated = list(props) + [
        {
            "id": "prop-heading-only",
            "proposition_text": (
                "Separate stowage of catches below the minimum conservation "
                "reference sizes"
            ),
        }
    ]

    def _assert_six(rows: list) -> None:
        if len(rows) != 6:
            raise AssertionError(
                "Source-fidelity / proposition-boundary failure: heading emitted as "
                "a seventh Article 49a proposition"
            )

    with pytest.raises(AssertionError, match="seventh Article 49a proposition"):
        _assert_six(mutated)


def test_mutation_cross_source_parent_accepted() -> None:
    foreign = SourceFragment(
        id="f-foreign",
        source_record_id="src-other",
        source_snapshot_id="snap-1",
        locator="title:iv",
        fragment_text="x",
        fragment_hash=content_hash("x"),
        structural_heading=StructuralHeading(kind="title", text="FOREIGN"),
    )
    child = SourceFragment(
        id="f-child",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:49a",
        fragment_text="y",
        fragment_hash=content_hash("y"),
        parent_fragment_id="f-foreign",
    )
    audit = audit_structural_fragments([foreign, child])
    with pytest.raises(AssertionError, match="cross-source"):
        assert_hierarchy_sound(audit)


def test_mutation_cyclic_hierarchy_accepted() -> None:
    a = SourceFragment(
        id="f-a",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:49a",
        fragment_text="a",
        fragment_hash=content_hash("a"),
        parent_fragment_id="f-b",
    )
    b = SourceFragment(
        id="f-b",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:49a:paragraph:1",
        fragment_text="b",
        fragment_hash=content_hash("b"),
        parent_fragment_id="f-a",
    )
    audit = audit_structural_fragments([a, b])
    with pytest.raises(AssertionError, match="cyclic"):
        assert_hierarchy_sound(audit)


def test_mutation_inspector_hiding_unassigned_heading_diagnostic() -> None:
    result = inspect_structural_fixture(fixture_by_id("multi_provision_cross_heading"))
    md = render_inspect_markdown(result)
    assert result.audit.unassigned_headings
    assert "multi_provision_group_title_unassigned" in md

    def _assert_unassigned_visible(unassigned, markdown: str) -> None:
        if not unassigned or "multi_provision_group_title_unassigned" not in markdown:
            raise AssertionError(
                "Source-fidelity failure: inspector hiding an unassigned heading diagnostic"
            )

    # Healthy path passes.
    _assert_unassigned_visible(result.audit.unassigned_headings, md)
    # Hidden diagnostics fail the checker.
    with pytest.raises(AssertionError, match="hiding an unassigned heading"):
        _assert_unassigned_visible([], md.replace("multi_provision_group_title_unassigned", ""))


def test_healthy_fixtures_still_pass_check() -> None:
    check_structural_fixture(fixture_by_id("article_49a_eur_2009_1224"))
    check_structural_fixture(fixture_by_id("multi_provision_cross_heading"))
    check_structural_fixture(fixture_by_id("uk_regulation_headed"))
