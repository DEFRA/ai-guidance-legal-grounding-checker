"""Proposition Matcher proposition export view: inclusion rules and regression fixture."""

from __future__ import annotations

from law_proposition_extractor_domain import LegalEffectType, Proposition, PropositionTier
from law_proposition_extractor_pipeline.proposition_matcher_export_view import (
    beatrice_checkable_rows,
    beatrice_contextual_scope_rows,
    build_beatrice_proposition_view,
)

from tests.fixtures.regression.loader import normalize_proposition_from_fixture


def _obligation_prop() -> Proposition:
    return Proposition(
        id="prop-duty-001",
        topic_id="topic-001",
        source_record_id="src-a",
        jurisdiction="UK",
        fragment_locator="regulation 10",
        proposition_text="The occupier must keep records for five years.",
        legal_subject="occupier",
        action="keep records for five years",
        label="Record retention for five years",
        conditions=["exception: does not apply in a greenhouse"],
        proposition_tier=PropositionTier.SUBSTANTIVE_RULE,
        legal_effect_type=LegalEffectType.OBLIGATION,
        is_compliance_relevant=True,
        is_comparison_anchor=True,
        extraction_trace_id="trace-duty-001",
        extraction_debug_meta={"evidence_quote": "must keep records for five years"},
    )


def test_territorial_fixture_excluded_from_checkable_in_contextual_scope() -> None:
    scope_prop = normalize_proposition_from_fixture()
    duty = _obligation_prop()
    sources = {
        "lex-regression-slurry-2010": {"id": "lex-regression-slurry-2010", "title": "Slurry 2010"},
        "src-a": {"id": "src-a", "title": "Example SI"},
    }
    view = build_beatrice_proposition_view(
        [scope_prop, duty],
        sources_by_id=sources,
    )
    checkable = beatrice_checkable_rows(view)
    contextual = beatrice_contextual_scope_rows(view)

    checkable_ids = {row["proposition_id"] for row in checkable}
    contextual_ids = {row["proposition_id"] for row in contextual}

    assert scope_prop.id not in checkable_ids
    assert scope_prop.id in contextual_ids
    assert duty.id in checkable_ids

    scope_row = next(r for r in contextual if r["proposition_id"] == scope_prop.id)
    assert scope_row["legal_effect_type"] == "application_scope"
    assert scope_row["is_checkable_for_guidance"] is False
    assert scope_row["territorial_application"] == ["England"]
    assert scope_row["source_title"] == "Slurry 2010"
    assert "categories" not in scope_row


def test_checkable_row_shape_and_exceptions_split() -> None:
    duty = _obligation_prop()
    view = build_beatrice_proposition_view([duty])
    assert len(view) == 1
    row = view[0]
    assert row["beatrice_role"] == "checkable"
    assert row["exceptions"] == ["does not apply in a greenhouse"]
    assert row["conditions"] == []
    assert row["evidence_quote"] == "must keep records for five years"
    assert row["extraction_trace_id"] == "trace-duty-001"
    assert row["is_checkable_for_guidance"] is True


def test_boilerplate_excluded_from_view() -> None:
    citation = Proposition(
        id="prop-cite",
        topic_id="t",
        source_record_id="src",
        jurisdiction="UK",
        proposition_text="These Regulations may be cited as the Example Regulations 2026.",
        legal_subject="These Regulations",
        action="may be cited as",
        label="Citation",
        categories=["obligation"],
        proposition_tier=PropositionTier.INSTRUMENT_METADATA,
        legal_effect_type=LegalEffectType.CITATION,
        is_compliance_relevant=False,
    )
    view = build_beatrice_proposition_view([citation, _obligation_prop()])
    assert {r["proposition_id"] for r in view} == {"prop-duty-001"}


def test_definition_only_when_referenced_or_flag() -> None:
    duty = _obligation_prop()
    definition = Proposition(
        id="prop-def",
        topic_id="t",
        source_record_id="src",
        jurisdiction="UK",
        fragment_locator="regulation 2",
        proposition_text='"holding" means land used for agriculture.',
        legal_subject="holding",
        action="means",
        label="Definition of holding",
        proposition_tier=PropositionTier.DEFINITIONAL_RULE,
        legal_effect_type=LegalEffectType.DEFINITION,
        is_compliance_relevant=False,
    )
    duty_with_link = duty.model_copy(
        update={"cross_reference_targets": ["prop-def"]},
    )

    without_flag = build_beatrice_proposition_view([duty, definition])
    assert beatrice_checkable_rows(without_flag)
    assert not any(r["proposition_id"] == "prop-def" for r in without_flag)

    with_flag = build_beatrice_proposition_view([duty, definition], include_definitions=True)
    assert any(r["proposition_id"] == "prop-def" for r in with_flag)

    with_link = build_beatrice_proposition_view([duty_with_link, definition])
    roles = {r["proposition_id"]: r["beatrice_role"] for r in with_link}
    assert roles["prop-def"] == "definition"
    assert roles[duty.id] == "checkable"


def test_non_compliance_permission_excluded_even_if_effect_allowed() -> None:
    permission = Proposition(
        id="prop-perm",
        topic_id="t",
        source_record_id="src",
        jurisdiction="UK",
        proposition_text="The Agency may grant a derogation.",
        legal_subject="Agency",
        action="may grant",
        label="Agency may grant derogation",
        proposition_tier=PropositionTier.SUBSTANTIVE_RULE,
        legal_effect_type=LegalEffectType.PERMISSION,
        is_compliance_relevant=False,
    )
    view = build_beatrice_proposition_view([permission])
    assert view == []
