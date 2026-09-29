"""Structural legislative heading capture, inheritance, and prompt context."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import pytest
from pydantic import ValidationError

from law_proposition_extractor_domain import (
    Cluster,
    SourceFragment,
    SourceRecord,
    StructuralHeading,
    StructuralHeadingKind,
    Topic,
)
from law_proposition_extractor_pipeline.extract import EXTRACTION_PROMPT_VERSION, _v2_model_prompt
from law_proposition_extractor_pipeline.source_fragmentation import content_hash, expand_monolithic_source_fragment
from law_proposition_extractor_pipeline.sources.adapters import _build_legislation_structural_fragments
from law_proposition_extractor_pipeline.sources.clml_heading import serialize_clml_heading_text
from law_proposition_extractor_pipeline.structural_headings import (
    nearest_provision_heading,
    parse_structural_heading_contexts,
    resolve_structural_heading_contexts,
)

ARTICLE_49A_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "article_49a_legal_structure"
    / "source.xml"
)

MULTI_PROVISION_GROUP_XML = """
<Legislation DocumentURI="http://www.legislation.gov.uk/eur/2009/1224">
  <EUBody>
    <P1group>
      <Title>Shared cross-heading</Title>
      <P1 id="article-10"><Pnumber>Article 10</Pnumber><Text>First provision body.</Text></P1>
      <P1 id="article-11"><Pnumber>Article 11</Pnumber><Text>Second provision body.</Text></P1>
    </P1group>
  </EUBody>
</Legislation>
"""

HEADING_NEGATIVE_XML = """
<Legislation DocumentURI="http://www.legislation.gov.uk/eur/2009/1224">
  <Title>Instrument Title Must Not Become Fragment Heading</Title>
  <EUBody>
    <P1group>
      <Title>Subject matter</Title>
      <P1 id="article-1">
        <Pnumber>Article 1</Pnumber>
        <Text>Operative body with
          <CommentaryRef Ref="c999"/>
          commentary marker.
        </Text>
      </P1>
    </P1group>
    <Commentaries>
      <Commentary id="c999"><Para><Text>Footnote commentary body must not be a heading.</Text></Para></Commentary>
    </Commentaries>
  </EUBody>
</Legislation>
"""


def _rows_from_xml(xml: str) -> list[dict]:
    root = ElementTree.fromstring(xml)
    rows, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
    )
    return rows


def test_structural_heading_requires_normalized_non_empty_text() -> None:
    heading = StructuralHeading(
        kind=StructuralHeadingKind.ARTICLE,
        text="  Separate   stowage  ",
        number_label="Article 49a",
    )
    assert heading.text == "Separate stowage"
    with pytest.raises(ValidationError):
        StructuralHeading(kind="article", text="   ")


def test_unknown_heading_kind_coerces() -> None:
    heading = StructuralHeading.model_validate(
        {"kind": "future_kind_xyz", "text": "Something"}
    )
    assert heading.kind == StructuralHeadingKind.UNKNOWN


def test_source_fragment_round_trip_heading_fields() -> None:
    frag = SourceFragment(
        id="frag-1",
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator="article:49a",
        fragment_text="Operative body.",
        fragment_hash=content_hash("Operative body."),
        number_label="Article 49a",
        structural_heading=StructuralHeading(
            kind="article",
            text="Separate stowage of catches",
            number_label="Article 49a",
            owner_locator="article:49a",
            change_ids=("O003001M119",),
            commentary_refs=("c000004",),
        ),
    )
    dumped = frag.model_dump(mode="json")
    restored = SourceFragment.model_validate(dumped)
    assert restored.number_label == "Article 49a"
    assert restored.structural_heading is not None
    assert restored.structural_heading.change_ids == ("O003001M119",)


def test_old_source_fragment_json_without_heading_loads() -> None:
    frag = SourceFragment.model_validate(
        {
            "id": "frag-legacy",
            "source_record_id": "src-1",
            "source_snapshot_id": "snap-1",
            "locator": "article:1",
            "fragment_text": "Old body",
            "fragment_hash": content_hash("Old body"),
        }
    )
    assert frag.structural_heading is None
    assert frag.number_label is None


def test_extraction_job_heading_contexts_round_trip() -> None:
    raw = [
        {
            "kind": "title",
            "number_label": "TITLE IV",
            "heading_text": "CONTROL OF FISHERIES",
            "owner_locator": "title:iv",
        },
        {
            "kind": "article",
            "number_label": "Article 49a",
            "heading_text": "Separate stowage",
            "owner_locator": "article:49a",
        },
    ]
    contexts = parse_structural_heading_contexts(raw)
    assert len(contexts) == 2
    assert contexts[0].heading_text == "CONTROL OF FISHERIES"
    assert parse_structural_heading_contexts(None) == []
    assert parse_structural_heading_contexts({}) == []


def test_article_49a_fixture_captures_heading_and_provenance() -> None:
    rows = _rows_from_xml(ARTICLE_49A_FIXTURE.read_text(encoding="utf-8"))
    by_loc = {r["locator"]: r for r in rows}
    art = by_loc["article:49a"]
    heading = art["structural_heading"]
    assert art["number_label"] == "Article 49a"
    assert heading["text"] == (
        "Separate stowage of catches below the minimum conservation "
        "reference sizes"
    )
    assert heading["kind"] == "article"
    assert "O003001M119" in heading["change_ids"]
    assert "c000004" in heading["commentary_refs"]
    assert "Separate stowage" not in art["text"]


def test_article_1_and_14_headings_captured() -> None:
    rows = _rows_from_xml(ARTICLE_49A_FIXTURE.read_text(encoding="utf-8"))
    by_loc = {r["locator"]: r for r in rows}
    assert by_loc["article:1"]["structural_heading"]["text"] == "Subject matter"
    assert by_loc["article:14"]["structural_heading"]["text"] == (
        "Completion and submission of the fishing logbook"
    )


def test_title_iv_number_and_descriptive_title_separate() -> None:
    rows = _rows_from_xml(ARTICLE_49A_FIXTURE.read_text(encoding="utf-8"))
    title = next(r for r in rows if r["locator"] == "title:iv")
    assert title["number_label"] == "TITLE IV"
    assert title["text"] == "TITLE IV"
    assert title["structural_heading"]["text"] == "CONTROL OF FISHERIES"


def test_multi_provision_group_title_not_misassigned() -> None:
    rows = _rows_from_xml(MULTI_PROVISION_GROUP_XML)
    by_loc = {r["locator"]: r for r in rows}
    assert by_loc["article:10"].get("structural_heading") is None
    assert by_loc["article:11"].get("structural_heading") is None
    diag = (by_loc["article:10"].get("metadata") or {}).get(
        "structural_heading_diagnostic"
    ) or (by_loc["article:11"].get("metadata") or {}).get(
        "structural_heading_diagnostic"
    )
    assert diag and "multi_provision_group_title_unassigned" in str(diag)


def test_commentary_and_instrument_title_not_captured_as_heading() -> None:
    rows = _rows_from_xml(HEADING_NEGATIVE_XML)
    by_loc = {r["locator"]: r for r in rows}
    assert by_loc["article:1"]["structural_heading"]["text"] == "Subject matter"
    assert "Footnote commentary" not in by_loc["article:1"]["structural_heading"]["text"]
    assert "Instrument Title" not in by_loc["article:1"]["structural_heading"]["text"]


def test_addition_wrapped_heading_serialization() -> None:
    root = ElementTree.fromstring(
        """
        <Title>
          <Addition ChangeId="O003001M119" CommentaryRef="c000004">
            Separate stowage of catches
          </Addition>
        </Title>
        """
    )
    assert serialize_clml_heading_text(root) == "Separate stowage of catches"


def _frag(
    *,
    fid: str,
    locator: str,
    parent: str | None = None,
    heading: dict | None = None,
    number_label: str | None = None,
) -> SourceFragment:
    return SourceFragment(
        id=fid,
        source_record_id="src-1",
        source_snapshot_id="snap-1",
        locator=locator,
        fragment_text=f"body for {locator}",
        fragment_hash=content_hash(f"body for {locator}"),
        parent_fragment_id=parent,
        number_label=number_label,
        structural_heading=(
            StructuralHeading.model_validate(heading) if heading else None
        ),
    )


def test_inheritance_outermost_to_nearest_and_no_leak() -> None:
    title = _frag(
        fid="f-title",
        locator="title:iv",
        number_label="TITLE IV",
        heading={
            "kind": "title",
            "text": "CONTROL OF FISHERIES",
            "number_label": "TITLE IV",
            "owner_locator": "title:iv",
        },
    )
    art = _frag(
        fid="f-art",
        locator="article:49a",
        parent="f-title",
        number_label="Article 49a",
        heading={
            "kind": "article",
            "text": "Separate stowage of catches below the minimum conservation reference sizes",
            "number_label": "Article 49a",
            "owner_locator": "article:49a",
        },
    )
    art1 = _frag(
        fid="f-art1",
        locator="article:1",
        parent="f-title",
        heading={"kind": "article", "text": "Subject matter", "owner_locator": "article:1"},
    )
    para = _frag(fid="f-p3", locator="article:49a:paragraph:3", parent="f-art")
    sub = _frag(
        fid="f-p2a",
        locator="article:49a:paragraph:2:subparagraph:a",
        parent="f-art",
    )
    by_id = {f.id: f for f in (title, art, art1, para, sub)}

    contexts = resolve_structural_heading_contexts(para, by_id)
    assert [c.heading_text for c in contexts] == [
        "CONTROL OF FISHERIES",
        "Separate stowage of catches below the minimum conservation reference sizes",
    ]
    assert "Subject matter" not in [c.heading_text for c in contexts]
    nearest = nearest_provision_heading(sub, by_id)
    assert nearest is not None
    assert nearest.owner_locator == "article:49a"


def test_inheritance_handles_cycles_and_cross_source() -> None:
    a = _frag(
        fid="f-a",
        locator="article:49a",
        parent="f-b",
        heading={"kind": "article", "text": "Heading A", "owner_locator": "article:49a"},
    )
    b = _frag(fid="f-b", locator="article:49a:paragraph:1", parent="f-a")
    # Cross-source parent must not be followed.
    foreign = SourceFragment(
        id="f-foreign",
        source_record_id="src-other",
        source_snapshot_id="snap-1",
        locator="title:iv",
        fragment_text="x",
        fragment_hash=content_hash("x"),
        structural_heading=StructuralHeading(kind="title", text="FOREIGN"),
    )
    a2 = a.model_copy(update={"parent_fragment_id": "f-foreign"})
    by_id = {"f-a": a, "f-b": b, "f-foreign": foreign}
    contexts = resolve_structural_heading_contexts(b, by_id)
    assert any(c.heading_text == "Heading A" for c in contexts)
    contexts2 = resolve_structural_heading_contexts(a2, {"f-a": a2, "f-foreign": foreign})
    assert all(c.heading_text != "FOREIGN" for c in contexts2)


def test_prompt_includes_labelled_structural_context_block() -> None:
    source = SourceRecord(
        id="src-1",
        title="Reg",
        jurisdiction="UK",
        citation="EUR 2009/1224",
        kind="regulation",
        authoritative_text="Operative paragraph body about stowage.",
        metadata={
            "structural_heading_contexts": [
                {
                    "kind": "title",
                    "number_label": "TITLE IV",
                    "heading_text": "CONTROL OF FISHERIES",
                    "owner_locator": "title:iv",
                },
                {
                    "kind": "article",
                    "number_label": "Article 49a",
                    "heading_text": (
                        "Separate stowage of catches below the minimum "
                        "conservation reference sizes"
                    ),
                    "owner_locator": "article:49a",
                },
            ]
        },
    )
    prompt = _v2_model_prompt(
        source,
        Topic(id="t", name="Topic"),
        Cluster(id="c", topic_id="t", name="Cluster"),
        extraction_mode="frontier",
    )
    assert "Structural legislative context" in prompt
    assert "non-operative headings" in prompt
    assert "not by itself an operative legal proposition" in prompt
    assert "TITLE IV — CONTROL OF FISHERIES" in prompt
    assert "Article 49a — Separate stowage" in prompt
    assert "Operative source text:" in prompt
    operative_idx = prompt.index("Operative source text:")
    heading_idx = prompt.index("Structural legislative context")
    assert heading_idx < operative_idx
    assert "Separate stowage" not in prompt[operative_idx:]
    assert EXTRACTION_PROMPT_VERSION == "v3"


def test_heading_not_eligible_as_evidence_against_operative_text() -> None:
    from law_proposition_extractor_pipeline.extract import evidence_locates_verbatim_after_normalisation

    heading = (
        "Separate stowage of catches below the minimum conservation reference sizes"
    )
    operative = "A fisheries administration must monitor the catch composition by way of sampling."
    ok, _, _ = evidence_locates_verbatim_after_normalisation(heading, operative)
    assert ok is False


def test_expand_preserves_heading_without_changing_fragment_ids() -> None:
    rows = _rows_from_xml(ARTICLE_49A_FIXTURE.read_text(encoding="utf-8"))
    mono = SourceFragment(
        id="frag-src-eur-2009-1224-001",
        source_record_id="src-eur-2009-1224",
        source_snapshot_id="snap-1",
        locator="document:full",
        fragment_text="placeholder large enough " * 400,
        fragment_hash=content_hash("placeholder"),
        metadata={"structural_fragments": rows},
    )
    from law_proposition_extractor_pipeline.sources.service import slugify

    expanded = expand_monolithic_source_fragment(
        mono, max_body_chars=50_000, slugify=slugify
    )
    by_loc = {f.locator: f for f in expanded}
    art = by_loc["article:49a"]
    assert art.structural_heading is not None
    assert art.id.startswith("frag-src-eur-2009-1224-")
    assert "Separate stowage" not in art.fragment_text
