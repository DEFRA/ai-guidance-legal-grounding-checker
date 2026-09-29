"""Regression: top-level articles must not parent to sibling articles (Article 49a BR1)."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

from law_proposition_extractor_domain import ReviewStatus, SourceFragment
from law_proposition_extractor_pipeline.fragment_types import fragment_type_from_locator
from law_proposition_extractor_pipeline.linting import lint_bundle
from law_proposition_extractor_pipeline.source_fragment_hierarchy import (
    is_valid_structural_parent,
    validate_source_fragment_hierarchy,
)
from law_proposition_extractor_pipeline.source_fragmentation import content_hash, expand_monolithic_source_fragment
from law_proposition_extractor_pipeline.sources.adapters import (
    LegislationGovUkAuthorityAdapter,
    _build_legislation_structural_fragments,
)
from law_proposition_extractor_pipeline.sources.service import SourceIngestionService, slugify
from law_proposition_extractor_pipeline.structural_child_extraction_preference import (
    FragmentSelectionDecision,
    apply_structural_child_extraction_preference,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "legislation_structure"
    / "sibling_articles_parts.xml"
)

ARTICLE_49A_SHAPED_XML = """
<Legislation DocumentURI="http://www.legislation.gov.uk/eur/2009/1224">
  <Title>Council Regulation (EC) No 1224/2009</Title>
  <EUBody>
    <P1 id="article-1"><Pnumber>Article 1</Pnumber>
      <Text>This Regulation establishes a control system.</Text>
    </P1>
    <P1 id="article-2"><Pnumber>Article 2</Pnumber>
      <Text>Article 2 defines terms.</Text>
    </P1>
    <P1 id="article-49a"><Pnumber>Article 49a</Pnumber>
      <Text>Separate stowage of catches.</Text>
      <P2 id="article-49a-1"><Pnumber>1</Pnumber>
        <Text>All catches below the applicable minimum conservation reference size shall be placed in boxes.</Text>
      </P2>
      <P2 id="article-49a-2"><Pnumber>2</Pnumber>
        <Text>Paragraph 1 shall not apply where catches contain more than 80% of listed species.</Text>
      </P2>
      <P2 id="article-49a-3"><Pnumber>3</Pnumber>
        <Text>In the cases referred to in paragraph 2, a fisheries administration must monitor catch composition.</Text>
      </P2>
    </P1>
    <P1 id="article-50"><Pnumber>Article 50</Pnumber>
      <Text>Article 50 concerns transport of fishery products.</Text>
    </P1>
  </EUBody>
</Legislation>
"""


def _ingest_xml(xml_payload: str, *, source_id: str, tmp_path: Path) -> list[SourceFragment]:
    def fake_fetch(source_url: str) -> tuple[str, dict[str, object]]:
        return xml_payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml_payload.encode("utf-8")),
            "fetched_url": source_url,
        }

    adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
    service = SourceIngestionService(
        cache_dir=tmp_path / "source-cache",
        adapters={"legislation_gov_uk": adapter},
    )
    result = service.ingest_sources(
        [
            {
                "authority": "legislation_gov_uk",
                "authority_source_id": "eur/2009/1224",
                "version_id": "2026-07-14",
                "id": source_id,
            }
        ]
    )
    return result.fragments


def _by_locator(fragments: list[SourceFragment]) -> dict[str, SourceFragment]:
    return {frag.locator: frag for frag in fragments}


def test_build_rows_use_traversal_ancestry_not_last_article() -> None:
    root = ElementTree.fromstring(ARTICLE_49A_SHAPED_XML)
    rows, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
    )
    by_loc = {row["locator"]: row for row in rows}
    assert by_loc["article:1"]["parent_locator"] is None
    assert by_loc["article:2"]["parent_locator"] is None
    assert by_loc["article:49a"]["parent_locator"] is None
    assert by_loc["article:50"]["parent_locator"] is None
    assert by_loc["article:49a:paragraph:1"]["parent_locator"] == "article:49a"
    assert by_loc["article:49a:paragraph:2"]["parent_locator"] == "article:49a"
    assert by_loc["article:49a:paragraph:3"]["parent_locator"] == "article:49a"


def test_part_chapter_containers_parent_articles() -> None:
    root = ElementTree.fromstring(FIXTURE.read_text(encoding="utf-8"))
    rows, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
    )
    by_loc = {row["locator"]: row for row in rows}
    assert by_loc["part:1"]["parent_locator"] is None
    assert by_loc["article:1"]["parent_locator"] == "part:1"
    assert by_loc["article:2"]["parent_locator"] == "part:1"
    assert by_loc["part:4"]["parent_locator"] is None
    assert by_loc["chapter:2"]["parent_locator"] == "part:4"
    assert by_loc["article:49a"]["parent_locator"] == "chapter:2"
    assert by_loc["article:50"]["parent_locator"] == "chapter:2"
    assert by_loc["article:49a:paragraph:1"]["parent_locator"] == "article:49a"
    assert (
        by_loc["article:49a:paragraph:2:subparagraph:a"]["parent_locator"]
        == "article:49a:paragraph:2"
    )


def test_article_49a_shaped_ingestion_rejects_article_1_parent(tmp_path: Path) -> None:
    fragments = _ingest_xml(ARTICLE_49A_SHAPED_XML, source_id="src-eur-49a-shape", tmp_path=tmp_path)
    by_loc = _by_locator(fragments)
    assert by_loc["article:1"].parent_fragment_id is None
    assert by_loc["article:2"].parent_fragment_id is None
    assert by_loc["article:49a"].parent_fragment_id is None
    assert by_loc["article:50"].parent_fragment_id is None
    assert by_loc["article:49a"].parent_fragment_id != by_loc["article:1"].id
    assert by_loc["article:49a:paragraph:1"].parent_fragment_id == by_loc["article:49a"].id
    assert by_loc["article:49a:paragraph:2"].parent_fragment_id == by_loc["article:49a"].id
    assert by_loc["article:49a:paragraph:3"].parent_fragment_id == by_loc["article:49a"].id
    assert by_loc["article:1"].id != by_loc["article:49a"].id
    # No self-parent / cycles on top-level articles.
    for loc in ("article:1", "article:2", "article:49a", "article:50"):
        assert by_loc[loc].parent_fragment_id != by_loc[loc].id


def test_part_fixture_ingestion_parents_to_containers(tmp_path: Path) -> None:
    fragments = _ingest_xml(
        FIXTURE.read_text(encoding="utf-8"),
        source_id="src-eur-parts",
        tmp_path=tmp_path,
    )
    by_loc = _by_locator(fragments)
    assert by_loc["article:1"].parent_fragment_id == by_loc["part:1"].id
    assert by_loc["article:2"].parent_fragment_id == by_loc["part:1"].id
    assert by_loc["article:49a"].parent_fragment_id == by_loc["chapter:2"].id
    assert by_loc["article:50"].parent_fragment_id == by_loc["chapter:2"].id
    assert by_loc["chapter:2"].parent_fragment_id == by_loc["part:4"].id
    assert fragment_type_from_locator("part:1") == "part"
    assert fragment_type_from_locator("chapter:2") == "chapter"


def test_parent_assignment_deterministic_under_reordered_siblings() -> None:
    root = ElementTree.fromstring(ARTICLE_49A_SHAPED_XML)
    rows_a, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
    )
    rows_b, _ = _build_legislation_structural_fragments(
        root=root,
        source_url="https://www.legislation.gov.uk/eur/2009/1224/data.xml",
    )
    assert [(r["locator"], r["parent_locator"], r["order_index"]) for r in rows_a] == [
        (r["locator"], r["parent_locator"], r["order_index"]) for r in rows_b
    ]


def test_expand_structural_null_parent_when_no_container() -> None:
    body = "Article 1\nOne.\n\nArticle 2\nTwo.\n"
    frag = SourceFragment(
        id="frag-src-eur-null-parent-001",
        source_record_id="src-eur-null-parent",
        source_snapshot_id="snap-eur-null-parent",
        fragment_type="instrument",
        locator="document:full",
        fragment_text=body,
        fragment_hash=content_hash(body),
        text_hash=content_hash(body),
        review_status=ReviewStatus.PROPOSED,
        metadata={
            "structural_fragments": [
                {"locator": "article:1", "text": "Article 1\nOne.", "order_index": 0},
                {"locator": "article:2", "text": "Article 2\nTwo.", "order_index": 1},
                {
                    "locator": "article:49a",
                    "text": "Article 49a body.",
                    "order_index": 2,
                },
                {
                    "locator": "article:49a:paragraph:1",
                    "parent_locator": "article:49a",
                    "text": "(1) Paragraph one.",
                    "order_index": 3,
                },
            ]
        },
    )
    out = expand_monolithic_source_fragment(
        frag,
        max_body_chars=10_000,
        overlap_chars=0,
        slugify=slugify,
    )
    by_loc = {f.locator: f for f in out}
    assert by_loc["article:1"].parent_fragment_id is None
    assert by_loc["article:2"].parent_fragment_id is None
    assert by_loc["article:49a"].parent_fragment_id is None
    assert by_loc["article:49a"].id != by_loc["article:1"].id
    assert by_loc["article:49a:paragraph:1"].parent_fragment_id == by_loc["article:49a"].id


def test_hierarchy_validation_detects_sibling_article_parent() -> None:
    diags = validate_source_fragment_hierarchy(
        [
            {
                "id": "frag-a1",
                "locator": "article:1",
                "parent_fragment_id": None,
                "source_record_id": "src-a",
                "source_snapshot_id": "snap-a",
            },
            {
                "id": "frag-a49a",
                "locator": "article:49a",
                "parent_fragment_id": "frag-a1",
                "source_record_id": "src-a",
                "source_snapshot_id": "snap-a",
            },
        ]
    )
    codes = {d["code"] for d in diags}
    assert "source_fragment_parent_not_structural_ancestor" in codes


def test_hierarchy_validation_detects_cycle_without_hanging() -> None:
    diags = validate_source_fragment_hierarchy(
        [
            {
                "id": "frag-a",
                "locator": "article:1",
                "parent_fragment_id": "frag-b",
                "source_record_id": "src-a",
                "source_snapshot_id": "snap-a",
            },
            {
                "id": "frag-b",
                "locator": "article:2",
                "parent_fragment_id": "frag-a",
                "source_record_id": "src-a",
                "source_snapshot_id": "snap-a",
            },
        ]
    )
    assert any(d["code"] == "source_fragment_parent_cycle" for d in diags)


def test_hierarchy_validation_missing_and_scope() -> None:
    diags = validate_source_fragment_hierarchy(
        [
            {
                "id": "frag-child",
                "locator": "article:49a:paragraph:1",
                "parent_fragment_id": "frag-missing",
                "source_record_id": "src-a",
                "source_snapshot_id": "snap-a",
            },
            {
                "id": "frag-cross",
                "locator": "article:49a:paragraph:2",
                "parent_fragment_id": "frag-other",
                "source_record_id": "src-a",
                "source_snapshot_id": "snap-a",
            },
            {
                "id": "frag-other",
                "locator": "article:49a",
                "parent_fragment_id": None,
                "source_record_id": "src-b",
                "source_snapshot_id": "snap-b",
            },
        ]
    )
    codes = {d["code"] for d in diags}
    assert "source_fragment_parent_missing" in codes
    assert "source_fragment_parent_scope_mismatch" in codes


def test_valid_fixture_emits_no_hierarchy_diagnostics(tmp_path: Path) -> None:
    fragments = _ingest_xml(
        FIXTURE.read_text(encoding="utf-8"),
        source_id="src-eur-valid",
        tmp_path=tmp_path,
    )
    diags = validate_source_fragment_hierarchy(
        [
            {
                "id": f.id,
                "locator": f.locator,
                "parent_fragment_id": f.parent_fragment_id,
                "source_record_id": f.source_record_id,
                "source_snapshot_id": f.source_snapshot_id,
            }
            for f in fragments
        ]
    )
    assert diags == []


def test_old_malformed_bundle_remains_loadable_with_warning() -> None:
    fragments = [
        {
            "id": "frag-a1",
            "source_record_id": "src-a",
            "source_snapshot_id": "snap-a",
            "locator": "article:1",
            "fragment_type": "article",
            "text_hash": "h1",
            "parent_fragment_id": None,
        },
        {
            "id": "frag-a49a",
            "source_record_id": "src-a",
            "source_snapshot_id": "snap-a",
            "locator": "article:49a",
            "fragment_type": "article",
            "text_hash": "h2",
            "parent_fragment_id": "frag-a1",
        },
    ]
    diags = validate_source_fragment_hierarchy(fragments)
    assert any(d["code"] == "source_fragment_parent_not_structural_ancestor" for d in diags)
    # Hierarchy problems are warnings in lint, never hard errors that block load.
    report = lint_bundle(
        {
            "source_records": [],
            "source_snapshots": [],
            "source_fragments": fragments,
            "propositions": [],
            "source_inventory": {"rows": []},
            "source_fetch_metadata": [],
            "source_fetch_attempts": [],
            "source_parse_traces": [],
            "proposition_extraction_traces": [],
            "source_target_links": [],
            "source_categorisation_rationales": [],
        }
    )
    assert not any(
        "source_fragment_parent_" in error for error in report["errors"]
    )
    assert any(
        "source_fragment_parent_not_structural_ancestor" in warning
        for warning in report["warnings"]
    )


def test_container_parent_is_valid_without_locator_prefix() -> None:
    assert is_valid_structural_parent(
        parent_locator="chapter:2",
        child_locator="article:49a",
    )
    assert not is_valid_structural_parent(
        parent_locator="article:1",
        child_locator="article:49a",
    )


def _selection_decision(fragment: SourceFragment, *, selected: bool) -> FragmentSelectionDecision:
    return FragmentSelectionDecision(
        source_record_id=fragment.source_record_id,
        fragment=fragment,
        selected=selected,
        selection_reason="focus_term_match" if selected else "skipped_no_focus_match",
        skip_reason=None if selected else "no_focus_match",
        fragment_locator=fragment.locator,
        fragment_type=fragment.fragment_type,
        fragment_text_length=len(fragment.fragment_text or ""),
    )


def test_structural_child_preference_still_suppresses_article_49a_parent() -> None:
    """Coverage-shaped 49a fixture still prefers paragraphs after parentage fix."""
    payload = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "structural_child_extraction"
            / "article_49a_shaped_fragments.json"
        ).read_text(encoding="utf-8")
    )
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
    by_loc = _by_locator(fragments)
    # Corrected parentage shape used by the fixture (doc container, not article:1).
    assert by_loc["article:49a"].parent_fragment_id == by_loc["document:full"].id
    assert by_loc["article:49a"].parent_fragment_id != "frag-demo-article-1-p1"
    article = by_loc["article:49a"]
    paragraphs = [
        by_loc["article:49a:paragraph:1"],
        by_loc["article:49a:paragraph:2"],
        by_loc["article:49a:paragraph:3"],
    ]
    out = apply_structural_child_extraction_preference(
        [
            _selection_decision(article, selected=True),
            *[_selection_decision(para, selected=True) for para in paragraphs],
        ],
        is_non_operative_fragment=lambda _ftype: False,
    )
    by_id = {d.fragment.id: d for d in out if d.fragment is not None}
    assert by_id[article.id].selected is False
    assert all(by_id[para.id].selected for para in paragraphs)


def test_source_effect_relevance_excludes_article_1_effects(tmp_path: Path) -> None:
    """Effects linked to article:1 must not be relevant to article:49a descendants."""
    xml = FIXTURE.read_text(encoding="utf-8")
    fragments = _ingest_xml(xml, source_id="src-eur-effects", tmp_path=tmp_path)
    by_loc = _by_locator(fragments)
    # Simulate effect links after ingestion finalization.
    effect_links = [
        ("effect-a", by_loc["article:1"].id, "article:1"),
        ("effect-b", by_loc["article:49a"].id, "article:49a"),
        ("effect-c", by_loc["article:49a:paragraph:1"].id, "article:49a:paragraph:1"),
        ("effect-d", by_loc["article:49a:paragraph:2"].id, "article:49a:paragraph:2"),
        ("effect-e", by_loc["article:49a:paragraph:3"].id, "article:49a:paragraph:3"),
    ]

    def ancestor_ids(fragment_id: str) -> set[str]:
        by_id = {f.id: f for f in fragments}
        out: set[str] = set()
        seen: set[str] = set()
        current = fragment_id
        while current and current not in seen:
            seen.add(current)
            parent = by_id[current].parent_fragment_id
            if not parent:
                break
            out.add(parent)
            current = parent
        return out

    p1_ancestors = ancestor_ids(by_loc["article:49a:paragraph:1"].id)
    assert by_loc["article:1"].id not in p1_ancestors
    assert by_loc["article:49a"].id in p1_ancestors

    relevant_to_p1 = {
        effect_id
        for effect_id, frag_id, _loc in effect_links
        if frag_id == by_loc["article:49a:paragraph:1"].id or frag_id in p1_ancestors
    }
    assert relevant_to_p1 == {"effect-b", "effect-c"}
    assert "effect-a" not in relevant_to_p1

    p2_ancestors = ancestor_ids(by_loc["article:49a:paragraph:2"].id)
    relevant_to_p2 = {
        effect_id
        for effect_id, frag_id, _loc in effect_links
        if frag_id == by_loc["article:49a:paragraph:2"].id or frag_id in p2_ancestors
    }
    assert relevant_to_p2 == {"effect-b", "effect-d"}
    assert "effect-c" not in relevant_to_p2

    p3_ancestors = ancestor_ids(by_loc["article:49a:paragraph:3"].id)
    relevant_to_p3 = {
        effect_id
        for effect_id, frag_id, _loc in effect_links
        if frag_id == by_loc["article:49a:paragraph:3"].id or frag_id in p3_ancestors
    }
    assert relevant_to_p3 == {"effect-b", "effect-e"}


def test_cross_source_identical_locators_do_not_collide_in_parent_map(tmp_path: Path) -> None:
    a = _ingest_xml(ARTICLE_49A_SHAPED_XML, source_id="src-a", tmp_path=tmp_path / "a")
    b = _ingest_xml(ARTICLE_49A_SHAPED_XML, source_id="src-b", tmp_path=tmp_path / "b")
    a49 = next(f for f in a if f.locator == "article:49a")
    b49 = next(f for f in b if f.locator == "article:49a")
    assert a49.source_record_id != b49.source_record_id
    assert a49.id != b49.id
    assert a49.parent_fragment_id is None
    assert b49.parent_fragment_id is None
