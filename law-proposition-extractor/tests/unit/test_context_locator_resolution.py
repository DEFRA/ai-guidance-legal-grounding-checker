"""Unit tests for export context locator resolution (Review Workbench parity)."""

from __future__ import annotations

from law_proposition_extractor_pipeline.context_locator_resolution import (
    LocatorSegment,
    LocatorStructuralContext,
    ResolvedContextFragment,
    apply_structural_context_to_reference,
    build_canonical_locator,
    locator_matches_target,
    normalize_cross_reference_locator,
    parse_container_locator_targets,
    parse_locator_reference,
    parse_locator_structural_context,
    proposition_ids_for_fragments,
    resolve_context_locator,
    resolve_locator_targets,
)

SOURCE = "lex-test"


def _frag(
    *,
    frag_id: str,
    locator: str,
    source_record_id: str = SOURCE,
) -> dict:
    return {
        "id": frag_id,
        "source_record_id": source_record_id,
        "locator": locator,
        "fragment_text": f"Text for {locator}.",
    }


def _prop(
    *,
    prop_id: str,
    fragment_locator: str,
    source_fragment_id: str | None = None,
    source_record_id: str = SOURCE,
) -> dict:
    row: dict = {
        "id": prop_id,
        "source_record_id": source_record_id,
        "fragment_locator": fragment_locator,
        "proposition_text": "Example proposition.",
    }
    if source_fragment_id:
        row["source_fragment_id"] = source_fragment_id
    return row


SCHEDULE_ONE_FRAGMENTS = [
    _frag(frag_id="frag-schedule-1-p2", locator="schedule:1:paragraph:2"),
    _frag(frag_id="frag-schedule-1-p3", locator="schedule:1:paragraph:3"),
    _frag(frag_id="frag-schedule-1-p4", locator="schedule:1:paragraph:4"),
    _frag(frag_id="frag-schedule-1-p5", locator="schedule:1:paragraph:5"),
    _frag(frag_id="frag-schedule-1-p7a", locator="schedule:1:paragraph:7(a)"),
    _frag(frag_id="frag-schedule-1-p8", locator="schedule:1:paragraph:8"),
    _frag(frag_id="frag-schedule-1-p9", locator="schedule:1:paragraph:9"),
    _frag(frag_id="frag-schedule-2-p9", locator="schedule:2:paragraph:9"),
]

REGULATION_FRAGMENTS = [
    _frag(frag_id="frag-reg-36", locator="regulation:36"),
    _frag(frag_id="frag-reg-36-p1", locator="regulation:36:paragraph:1"),
]


def _schedule_one_context():
    return parse_locator_structural_context("schedule:1:paragraph:8")


def _regulation_context():
    return parse_locator_structural_context("regulation:36")


def test_normalize_colon_and_spaced_locators() -> None:
    assert normalize_cross_reference_locator("schedule:1") == "schedule 1"
    assert normalize_cross_reference_locator("regulation:19") == "regulation 19"
    assert normalize_cross_reference_locator("schedule:2:paragraph:1") == "schedule 2(1)"
    assert normalize_cross_reference_locator("schedule:1:paragraph:7") == "schedule 1(7)"
    assert normalize_cross_reference_locator("para 7(a)") == "paragraph 7(a)"


def test_schedule_1_resolves_as_container_with_propositions() -> None:
    fragments = [
        _frag(frag_id="frag-schedule-1", locator="schedule:1"),
        _frag(frag_id="frag-schedule-1-p1", locator="schedule:1:paragraph:1"),
    ]
    props = [
        _prop(prop_id="prop:s1", fragment_locator="schedule:1", source_fragment_id="frag-schedule-1"),
        _prop(prop_id="prop:s1-p1", fragment_locator="schedule:1:paragraph:1", source_fragment_id="frag-schedule-1-p1"),
    ]
    resolution = resolve_context_locator(
        "schedule 1",
        source_record_id=SOURCE,
        source_fragments=fragments,
        propositions=props,
    )
    assert resolution.resolved is True
    assert resolution.resolution_mode == "container"
    assert set(resolution.proposition_ids) == {"prop:s1", "prop:s1-p1"}


def test_schedule_3_resolves_as_container_not_ambiguous() -> None:
    fragments = [
        _frag(frag_id="frag-schedule-3-part-1", locator="schedule:3:part:1"),
        _frag(frag_id="frag-schedule-3-part-2", locator="schedule:3:part:2"),
    ]
    resolution = resolve_context_locator(
        "schedule 3",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=_schedule_one_context(),
    )
    assert resolution.resolved is True
    assert resolution.review_status == "accepted"
    assert resolution.resolution_mode == "container"
    assert len(resolution.matched_fragment_ids) == 2


def test_regulation_36_4_resolves_exact_paragraph() -> None:
    fragments = [
        *REGULATION_FRAGMENTS,
        _frag(frag_id="frag-reg-36-p4", locator="regulation:36:paragraph:4"),
    ]
    props = [
        _prop(
            prop_id="prop:reg36-p4",
            fragment_locator="regulation:36:paragraph:4",
            source_fragment_id="frag-reg-36-p4",
        ),
    ]
    resolution = resolve_context_locator(
        "regulation 36(4)",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=_regulation_context(),
        propositions=props,
    )
    assert resolution.resolved is True
    assert resolution.resolution_mode == "exact"
    assert resolution.matched_fragment_ids == ["frag-reg-36-p4"]
    assert resolution.proposition_ids == ["prop:reg36-p4"]
    assert locator_matches_target("regulation:36:paragraph:4", "regulation 36(4)")


def test_bare_paragraph_9_inherits_schedule_context() -> None:
    props = [
        _prop(
            prop_id="prop:p9",
            fragment_locator="schedule:1:paragraph:9",
            source_fragment_id="frag-schedule-1-p9",
        ),
    ]
    resolution = resolve_context_locator(
        "paragraph 9",
        source_record_id=SOURCE,
        source_fragments=SCHEDULE_ONE_FRAGMENTS,
        structural_context=_schedule_one_context(),
        propositions=props,
    )
    assert resolution.resolved is True
    assert resolution.matched_fragment_ids == ["frag-schedule-1-p9"]
    assert resolution.proposition_ids == ["prop:p9"]
    assert resolve_locator_targets("paragraph 9", _schedule_one_context()) == ["schedule 1(9)"]


def test_paragraphs_2_to_5_expands_and_links() -> None:
    props = [
        _prop(prop_id="prop:p2", fragment_locator="schedule:1:paragraph:2", source_fragment_id="frag-schedule-1-p2"),
        _prop(prop_id="prop:p3", fragment_locator="schedule:1:paragraph:3", source_fragment_id="frag-schedule-1-p3"),
        _prop(prop_id="prop:p4", fragment_locator="schedule:1:paragraph:4", source_fragment_id="frag-schedule-1-p4"),
        _prop(prop_id="prop:p5", fragment_locator="schedule:1:paragraph:5", source_fragment_id="frag-schedule-1-p5"),
    ]
    resolution = resolve_context_locator(
        "paragraphs 2 to 5",
        source_record_id=SOURCE,
        source_fragments=SCHEDULE_ONE_FRAGMENTS,
        structural_context=_schedule_one_context(),
        propositions=props,
    )
    assert resolution.resolved is True
    assert len(resolution.matched_fragment_ids) == 4
    assert set(resolution.proposition_ids) == {"prop:p2", "prop:p3", "prop:p4", "prop:p5"}


def test_external_instrument_reference_stays_unresolved() -> None:
    resolution = resolve_context_locator(
        "regulation 4 of the Environmental Permitting (England and Wales) Regulations 2010",
        source_record_id=SOURCE,
        source_fragments=REGULATION_FRAGMENTS,
        structural_context=_regulation_context(),
    )
    assert resolution.resolved is False
    assert resolution.proposition_ids == []


def test_bare_paragraph_9_ambiguous_without_context() -> None:
    resolution = resolve_context_locator(
        "paragraph 9",
        source_record_id=SOURCE,
        source_fragments=SCHEDULE_ONE_FRAGMENTS,
        structural_context=LocatorStructuralContext(segments=[]),
    )
    assert resolution.resolved is False
    assert resolution.review_status == "ambiguous"
    assert len(resolution.matched_fragment_ids) == 2


def test_parts_1_and_2_of_schedule_3() -> None:
    targets = parse_container_locator_targets("Parts 1 and 2 of Schedule 3")
    assert targets is not None
    assert [t.display for t in targets] == ["Schedule 3, Part 1", "Schedule 3, Part 2"]
    fragments = [
        _frag(frag_id="frag-schedule-3-part-1", locator="schedule:3:part:1"),
        _frag(frag_id="frag-schedule-3-part-2", locator="schedule:3:part:2"),
    ]
    resolution = resolve_context_locator(
        "Parts 1 and 2 of Schedule 3",
        source_record_id=SOURCE,
        source_fragments=fragments,
        structural_context=_schedule_one_context(),
    )
    assert resolution.resolved is True
    assert resolution.resolution_mode == "container"
    assert len(resolution.matched_fragment_ids) == 2


def test_proposition_ids_for_fragments_by_locator_match() -> None:
    fragments = [
        ResolvedContextFragment("frag-reg-36-p4", "regulation:36:paragraph:4"),
    ]
    props = [
        _prop(prop_id="prop:via-locator", fragment_locator="regulation:36:paragraph:4"),
    ]
    assert proposition_ids_for_fragments(fragments, props, source_record_id=SOURCE) == [
        "prop:via-locator"
    ]


def test_parse_locator_reference_range() -> None:
    assert parse_locator_reference("paragraphs 2 to 5") is not None
    parsed = parse_locator_reference("paragraphs 2 to 5")
    assert parsed is not None
    assert parsed.kind == "range"  # type: ignore[union-attr]


SCHEDULE_1A_PARAGRAPH_18_FRAGMENTS = [
    _frag(frag_id="frag-schedule-1a-p18", locator="schedule:1a:paragraph:18"),
]

SCHEDULE_1A_PARAGRAPH_18_PROPOSITIONS = [
    _prop(
        prop_id="prop:18-1a",
        fragment_locator="schedule:1a:paragraph:18(1)(a)",
    ),
    _prop(
        prop_id="prop:18-1b",
        fragment_locator="schedule:1a:paragraph:18(1)(b)",
    ),
    _prop(
        prop_id="prop:18-2",
        fragment_locator="schedule:1a:paragraph:18(2)",
    ),
]


def _schedule_1a_paragraph_18_1_b_context():
    return parse_locator_structural_context("schedule:1a:paragraph:18(1)(b)")


def test_nested_schedule_paragraph_colon_path_parses() -> None:
    context = _schedule_1a_paragraph_18_1_b_context()
    assert context is not None
    assert context.segments == [
        LocatorSegment(kind="schedule", num="1a"),
        LocatorSegment(kind="paragraph", num="18", sub="1)(b"),
    ]
    assert normalize_cross_reference_locator("schedule:1a:paragraph:18(1)(b)") == "schedule 1a(18(1)(b))"
    assert locator_matches_target("schedule:1a:paragraph:18(1)(a)", "schedule 1a(18(1))")


def test_schedule_1a_paragraph_18_1_resolves_as_container_from_nested_context() -> None:
    context = _schedule_1a_paragraph_18_1_b_context()
    resolution = resolve_context_locator(
        "paragraph 18(1)",
        source_record_id=SOURCE,
        source_fragments=SCHEDULE_1A_PARAGRAPH_18_FRAGMENTS,
        structural_context=context,
        propositions=SCHEDULE_1A_PARAGRAPH_18_PROPOSITIONS,
    )
    assert resolution.resolved is True
    assert resolution.review_status == "accepted"
    assert resolution.resolution_status == "resolved"
    assert resolution.resolution_mode == "container"
    assert set(resolution.proposition_ids) == {"prop:18-1a", "prop:18-1b"}


def test_schedule_1a_nested_paragraph_targets_from_context() -> None:
    context = _schedule_1a_paragraph_18_1_b_context()
    assert resolve_locator_targets("paragraph 18", context) == ["schedule 1a(18)"]
    assert resolve_locator_targets("paragraph 18(1)", context) == ["schedule 1a(18(1))"]
    assert resolve_locator_targets("paragraph 18(1)(a)", context) == ["schedule 1a(18(1)(a))"]

    parsed = parse_locator_reference("paragraph 18(1)")
    assert parsed is not None
    contextualised = apply_structural_context_to_reference(context, parsed)
    assert build_canonical_locator(list(contextualised.segments)) == "schedule 1a(18(1))"
