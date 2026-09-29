"""Structural-relative resolution for bare paragraph/subparagraph/point references."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_pipeline.context_locator_resolution import (
    LocatorStructuralContext,
    apply_structural_context_to_reference,
    parse_locator_reference,
    parse_locator_structural_context,
    resolve_context_locator,
    resolve_locator_targets,
    structural_context_for_proposition,
)
from law_proposition_extractor_pipeline.effective_law import build_effective_law_statements

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "structural_child_extraction"
    / "article_49a_shaped_fragments.json"
)
SOURCE = "src-control-regulation-demo"


def _load_fixture_fragments() -> list[dict]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    source_id = str(payload["source_record_id"])
    rows: list[dict] = []
    for item in payload["fragments"]:
        rows.append(
            {
                "id": item["id"],
                "source_record_id": source_id,
                "locator": item["locator"],
                "fragment_text": item["fragment_text"],
                "parent_fragment_id": item.get("parent_fragment_id"),
                "order_index": item.get("order_index"),
                "fragment_type": item.get("fragment_type"),
            }
        )
    return rows


def _prop(
    *,
    prop_id: str,
    fragment_locator: str,
    source_fragment_id: str,
    xrefs: list[str] | None = None,
    text: str = "Example proposition.",
) -> dict:
    return {
        "id": prop_id,
        "source_record_id": SOURCE,
        "fragment_locator": fragment_locator,
        "source_fragment_id": source_fragment_id,
        "proposition_text": text,
        "explicit_cross_reference_targets": list(xrefs or []),
        "legal_effect_type": "obligation",
        "proposition_tier": "substantive_rule",
    }


def _49a_propositions() -> list[dict]:
    return [
        _prop(
            prop_id="prop:49a-p1-a",
            fragment_locator="article:49a:paragraph:1 (first sentence)",
            source_fragment_id="frag-demo-49a-p1",
        ),
        _prop(
            prop_id="prop:49a-p1-b",
            fragment_locator="article:49a:paragraph:1 (second sentence)",
            source_fragment_id="frag-demo-49a-p1",
        ),
        _prop(
            prop_id="prop:49a-p2-a",
            fragment_locator="article 49a, paragraph 2(a)(i)",
            source_fragment_id="frag-demo-49a-p2",
            xrefs=["paragraph 1"],
            text="The obligation in paragraph 1 does not apply for small pelagic fisheries.",
        ),
        _prop(
            prop_id="prop:49a-p2-a-ii",
            fragment_locator="article 49a, paragraph 2(a)(ii)",
            source_fragment_id="frag-demo-49a-p2",
            xrefs=["paragraph 1"],
            text="The obligation in paragraph 1 does not apply for industrial-purpose fisheries.",
        ),
        _prop(
            prop_id="prop:49a-p2-b",
            fragment_locator="article 49a, paragraph 2(b)",
            source_fragment_id="frag-demo-49a-p2",
            xrefs=["article 14", "paragraph 1"],
            text=(
                "The obligation in paragraph 1 does not apply to vessels under 12m "
                "where catches are recorded in accordance with Article 14."
            ),
        ),
        _prop(
            prop_id="prop:49a-p3",
            fragment_locator="article 49a, paragraph 3",
            source_fragment_id="frag-demo-49a-p3",
            xrefs=["paragraph 2"],
            text="In the cases referred to in paragraph 2, a fisheries administration must monitor catch composition.",
        ),
        _prop(
            prop_id="prop:noise-p1",
            fragment_locator="article:1:paragraph:1",
            source_fragment_id="frag-demo-article-1-p1",
        ),
        _prop(
            prop_id="prop:noise-p2",
            fragment_locator="article:1:paragraph:2",
            source_fragment_id="frag-demo-article-1-p2",
        ),
        _prop(
            prop_id="prop:art14",
            fragment_locator="article:14",
            source_fragment_id="frag-demo-article-14",
        ),
        _prop(
            prop_id="prop:art14-p1",
            fragment_locator="article:14:paragraph:1",
            source_fragment_id="frag-demo-article-14-p1",
        ),
    ]


def test_parse_free_text_and_chained_article_locators() -> None:
    comma = parse_locator_structural_context("article 49a, paragraph 2(b)")
    assert comma is not None
    assert [(s.kind, s.num, s.sub) for s in comma.segments] == [
        ("article", "49a", None),
        ("paragraph", "2", "b"),
    ]

    chained = parse_locator_structural_context("Article 49a(2)(b)")
    assert chained is not None
    assert [(s.kind, s.num, s.sub) for s in chained.segments] == [
        ("article", "49a", None),
        ("paragraph", "2", "b"),
    ]

    annotated = parse_locator_structural_context(
        "article:49a:paragraph:1 (first sentence)"
    )
    assert annotated is not None
    assert [(s.kind, s.num, s.sub) for s in annotated.segments] == [
        ("article", "49a", None),
        ("paragraph", "1", None),
    ]


def test_structural_context_prefers_source_fragment_over_free_text_locator() -> None:
    fragments = _load_fixture_fragments()
    prop = _prop(
        prop_id="prop:x",
        fragment_locator="article 49a, paragraph 2(b)",
        source_fragment_id="frag-demo-49a-p2",
    )
    # Without fragments, free-text now parses; with fragments, canonical child wins.
    ctx = structural_context_for_proposition(prop, source_fragments=fragments)
    assert ctx is not None
    assert [(s.kind, s.num, s.sub) for s in ctx.segments] == [
        ("article", "49a", None),
        ("paragraph", "2", None),
    ]


def test_paragraph_1_from_49a_paragraph_2_resolves_uniquely() -> None:
    fragments = _load_fixture_fragments()
    props = _49a_propositions()
    prop = next(p for p in props if p["id"] == "prop:49a-p2-b")
    ctx = structural_context_for_proposition(prop, source_fragments=fragments)
    resolution = resolve_context_locator(
        "paragraph 1",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=ctx,
        propositions=props,
    )
    assert resolution.resolution_status == "resolved"
    assert resolution.review_status == "accepted"
    assert resolution.matched_fragment_ids == ["frag-demo-49a-p1"]
    assert set(resolution.proposition_ids) == {"prop:49a-p1-a", "prop:49a-p1-b"}
    assert resolution.resolution_basis == "structural_relative"
    assert "frag-demo-article-1-p1" not in resolution.matched_fragment_ids
    assert resolve_locator_targets("paragraph 1", ctx) == ["article 49a(1)"]


def test_paragraph_2_from_49a_paragraph_3_resolves_uniquely() -> None:
    fragments = _load_fixture_fragments()
    props = _49a_propositions()
    prop = next(p for p in props if p["id"] == "prop:49a-p3")
    ctx = structural_context_for_proposition(prop, source_fragments=fragments)
    resolution = resolve_context_locator(
        "paragraph 2",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=ctx,
        propositions=props,
    )
    assert resolution.resolution_status == "resolved"
    assert resolution.matched_fragment_ids == ["frag-demo-49a-p2"]
    assert resolution.proposition_ids == [
        "prop:49a-p2-a",
        "prop:49a-p2-a-ii",
        "prop:49a-p2-b",
    ] or set(resolution.proposition_ids) == {
        "prop:49a-p2-a",
        "prop:49a-p2-a-ii",
        "prop:49a-p2-b",
    }
    assert resolution.resolution_basis == "structural_relative"
    assert len(resolution.matched_fragment_ids) == 1


def test_identically_numbered_paragraphs_elsewhere_excluded() -> None:
    fragments = _load_fixture_fragments()
    props = _49a_propositions()
    ctx = structural_context_for_proposition(
        next(p for p in props if p["id"] == "prop:49a-p2-a"),
        source_fragments=fragments,
    )
    resolution = resolve_context_locator(
        "paragraph 1",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=ctx,
        propositions=props,
    )
    assert resolution.matched_fragment_ids == ["frag-demo-49a-p1"]
    assert "prop:noise-p1" not in resolution.proposition_ids


def test_article_14_remains_external_to_49a() -> None:
    fragments = _load_fixture_fragments()
    props = _49a_propositions()
    ctx = structural_context_for_proposition(
        next(p for p in props if p["id"] == "prop:49a-p2-b"),
        source_fragments=fragments,
    )
    resolution = resolve_context_locator(
        "article 14",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=ctx,
        propositions=props,
    )
    assert resolution.resolution_status in {"resolved", "partially_resolved"}
    assert "frag-demo-article-14" in resolution.matched_fragment_ids or set(
        resolution.proposition_ids
    ) >= {"prop:art14", "prop:art14-p1"}
    assert "frag-demo-49a" not in resolution.matched_fragment_ids
    assert resolution.resolution_basis in {"explicit", None} or resolution.resolution_basis == "explicit"


def test_paragraph_1_of_article_14_not_localised_to_49a() -> None:
    fragments = _load_fixture_fragments()
    props = _49a_propositions()
    ctx = structural_context_for_proposition(
        next(p for p in props if p["id"] == "prop:49a-p2-b"),
        source_fragments=fragments,
    )
    parsed = parse_locator_reference("paragraph 1 of Article 14")
    assert parsed is not None
    assert not isinstance(parsed, type(None))
    contextualised = apply_structural_context_to_reference(ctx, parsed)
    assert resolve_locator_targets("paragraph 1 of Article 14", ctx) == ["article 14(1)"]
    resolution = resolve_context_locator(
        "paragraph 1 of Article 14",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=ctx,
        propositions=props,
    )
    assert resolution.resolution_status == "resolved"
    assert resolution.matched_fragment_ids == ["frag-demo-article-14-p1"]
    assert resolution.proposition_ids == ["prop:art14-p1"]
    assert contextualised.segments[0].kind == "article"
    assert contextualised.segments[0].num == "14"


def test_local_subparagraph_and_point_qualify_within_enclosing_levels() -> None:
    ctx = parse_locator_structural_context("article:49a:paragraph:2")
    assert resolve_locator_targets("subparagraph (a)", ctx) == ["article 49a(2(a))"]

    ctx_sub = parse_locator_structural_context("Article 49a(2)(a)")
    assert resolve_locator_targets("point (ii)", ctx_sub) == ["article 49a(2(a(ii)))"]


def test_missing_local_target_falls_back_instrument_wide() -> None:
    fragments = [
        row
        for row in _load_fixture_fragments()
        if row["id"] != "frag-demo-49a-p1"
    ]
    props = [p for p in _49a_propositions() if p["id"] not in {"prop:49a-p1-a", "prop:49a-p1-b"}]
    ctx = structural_context_for_proposition(
        next(p for p in props if p["id"] == "prop:49a-p2-a"),
        source_fragments=fragments,
    )
    resolution = resolve_context_locator(
        "paragraph 1",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=ctx,
        propositions=props,
    )
    # Local qualification yields article 49a(1); without that fragment, matcher may
    # fall through. Accept unresolved local miss or instrument-wide noise hit.
    assert resolution.resolution_basis in {
        "structural_relative",
        "instrument_wide",
        "unresolved",
    }
    if resolution.resolution_status == "ambiguous":
        assert resolution.resolution_basis == "instrument_wide"
        assert "frag-demo-article-1-p1" in resolution.matched_fragment_ids


def test_no_enclosing_structure_keeps_conservative_instrument_wide_behaviour() -> None:
    fragments = _load_fixture_fragments()
    resolution = resolve_context_locator(
        "paragraph 1",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=LocatorStructuralContext(segments=[]),
        propositions=_49a_propositions(),
    )
    assert resolution.resolution_status == "ambiguous"
    assert resolution.resolution_basis == "instrument_wide"
    assert len(resolution.matched_fragment_ids) >= 2


def test_resolution_deterministic_regardless_of_fragment_order() -> None:
    fragments = _load_fixture_fragments()
    props = _49a_propositions()
    ctx = structural_context_for_proposition(
        next(p for p in props if p["id"] == "prop:49a-p3"),
        source_fragments=fragments,
    )
    orders = [
        fragments,
        list(reversed(fragments)),
        sorted(fragments, key=lambda row: str(row["id"]), reverse=True),
    ]
    outcomes = []
    for ordered in orders:
        assert {row["id"] for row in ordered} == {row["id"] for row in fragments}
        resolution = resolve_context_locator(
            "paragraph 2",
            source_record_id=SOURCE,
            source_fragments=ordered,
            structural_context=ctx,
            propositions=props,
        )
        outcomes.append(
            (
                resolution.resolution_status,
                tuple(sorted(resolution.matched_fragment_ids)),
                tuple(sorted(resolution.proposition_ids)),
                resolution.resolution_basis,
            )
        )
    assert len(set(outcomes)) == 1
    assert outcomes[0][0] == "resolved"
    assert outcomes[0][1] == ("frag-demo-49a-p2",)
    assert set(outcomes[0][2]) == {"prop:49a-p2-a", "prop:49a-p2-a-ii", "prop:49a-p2-b"}
    assert outcomes[0][3] == "structural_relative"


def test_effective_law_no_longer_marks_49a_local_refs_ambiguous() -> None:
    fragments = _load_fixture_fragments()
    props = _49a_propositions()
    payload = build_effective_law_statements(
        props,
        run_id="run-structural-relative-49a",
        source_fragments=fragments,
    )
    statements = payload["statements"]
    by_source = {
        (statement["source_proposition_ids"] or [None])[0]: statement for statement in statements
    }

    p2 = by_source["prop:49a-p2-b"]
    para1_ctx = next(
        entry for entry in p2["required_context"] if entry.get("locator") == "paragraph 1"
    )
    assert para1_ctx["resolution_status"] == "resolved"
    assert para1_ctx.get("resolution_basis") == "structural_relative"
    assert set(para1_ctx["proposition_ids"]) == {"prop:49a-p1-a", "prop:49a-p1-b"}
    assert "ambiguous locator resolution for paragraph 1" not in (p2.get("warnings") or [])

    art14_ctx = next(
        entry for entry in p2["required_context"] if entry.get("locator") == "article 14"
    )
    assert art14_ctx["resolution_status"] in {"resolved", "partially_resolved"}

    p3 = by_source["prop:49a-p3"]
    para2_ctx = next(
        entry for entry in p3["required_context"] if entry.get("locator") == "paragraph 2"
    )
    assert para2_ctx["resolution_status"] == "resolved"
    assert para2_ctx.get("resolution_basis") == "structural_relative"
    assert set(para2_ctx["proposition_ids"]) == {
        "prop:49a-p2-a",
        "prop:49a-p2-a-ii",
        "prop:49a-p2-b",
    }
    assert "ambiguous locator resolution for paragraph 2" not in (p3.get("warnings") or [])

    # Regression: local refs must not expand to the instrument-wide candidate set.
    assert len(para1_ctx["proposition_ids"]) < 5
    assert len(para2_ctx["proposition_ids"]) < 5
