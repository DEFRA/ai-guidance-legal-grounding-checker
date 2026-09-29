"""Unit tests for export proposition hygiene (evidence backfill + re-classification)."""

from __future__ import annotations

from law_proposition_extractor_domain import LegalEffectType, Proposition, PropositionTier, SourceFragment, SourceRecord
from law_proposition_extractor_domain.proposition_notes import resolve_extraction_meta_for_proposition

from law_proposition_extractor_pipeline.export_proposition_hygiene import (
    apply_export_proposition_hygiene,
    backfill_evidence_quote_if_missing,
)


def _frag() -> SourceFragment:
    return SourceFragment(
        id="frag-reg2",
        source_record_id="lex-npp",
        source_snapshot_id="snap-1",
        locator="regulation:2",
        fragment_text=(
            'In these Regulations—“slurry” means excreta produced by livestock (other than poultry);'
            '"organic manure" means a nitrogen fertiliser derived from animal sources;'
            '"agricultural" has the meaning given by section 109(3) of the Agriculture Act 1947.'
        ),
        fragment_hash="abc",
    )


def test_backfill_evidence_for_repair_row_without_quote() -> None:
    prop = Proposition(
        id="prop-test",
        topic_id="topic-1",
        source_record_id="lex-npp",
        source_fragment_id="frag-reg2",
        fragment_locator="regulation:2",
        jurisdiction="UK",
        proposition_text="Slurry means excreta produced by livestock (other than poultry).",
        label="Definition: slurry",
        legal_subject="slurry",
        action="means",
        extraction_debug_meta={
            "repair_command": "repair-fragment",
            "extraction_mode": "fragment_repair",
        },
    )
    frag = _frag()
    assert backfill_evidence_quote_if_missing(
        prop,
        fragment_by_id={"frag-reg2": frag},
        source_by_id={},
    )
    meta = resolve_extraction_meta_for_proposition(extraction_debug_meta=prop.extraction_debug_meta)
    assert meta is not None
    assert "slurry" in str(meta.get("evidence_quote") or "").lower()


def test_hygiene_classifies_definition_label_rows() -> None:
    prop = Proposition(
        id="prop-test-2",
        topic_id="topic-1",
        source_record_id="lex-npp",
        source_fragment_id="frag-reg2",
        fragment_locator="regulation:2",
        jurisdiction="UK",
        proposition_text="Slurry means excreta produced by livestock.",
        label="Definition: slurry",
        legal_subject="slurry",
        action="means",
        proposition_tier=PropositionTier.UNKNOWN,
        legal_effect_type=LegalEffectType.UNKNOWN,
    )
    frag = _frag()
    apply_export_proposition_hygiene(
        [prop],
        source_by_id={
            "lex-npp": SourceRecord(
                id="lex-npp",
                title="NPP 2015",
                jurisdiction="UK",
                citation="SI 2015/668",
                kind="regulation",
            )
        },
        fragment_by_id={"frag-reg2": frag},
    )
    assert prop.proposition_tier == PropositionTier.DEFINITIONAL_RULE
    assert prop.legal_effect_type == LegalEffectType.DEFINITION
