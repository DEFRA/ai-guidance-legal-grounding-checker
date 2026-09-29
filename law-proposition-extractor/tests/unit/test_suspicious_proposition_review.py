"""Unit tests for suspicious proposition review builder."""

from __future__ import annotations

from law_proposition_extractor_pipeline.suspicious_proposition_review import (
    REVIEW_JSON_FILENAME,
    REVIEW_MD_FILENAME,
    build_suspicious_proposition_review,
    write_suspicious_proposition_review,
)


def test_duplicate_id_detected(tmp_path) -> None:
    rows = [
        {
            "id": "prop:dup",
            "source_record_id": "lex-a",
            "fragment_locator": "regulation 1(1)",
            "proposition_text": "Alpha text.",
            "label": "A",
            "proposition_tier": "substantive_rule",
            "legal_effect_type": "obligation",
            "source_scoped_key": "lex-a:alpha",
        },
        {
            "id": "prop:dup",
            "source_record_id": "lex-a",
            "fragment_locator": "regulation 1(1)",
            "proposition_text": "Alpha text variant.",
            "label": "B",
            "proposition_tier": "substantive_rule",
            "legal_effect_type": "obligation",
            "source_scoped_key": "lex-a:alpha",
        },
    ]
    review = build_suspicious_proposition_review(rows, export_dir=tmp_path)
    assert review.summary["duplicate_proposition_id_groups"] == 1
    assert review.summary["duplicates_are_blocker"] is True

    md_path, json_path = write_suspicious_proposition_review(tmp_path, review)
    assert md_path.name == REVIEW_MD_FILENAME
    assert json_path.name == REVIEW_JSON_FILENAME
    assert md_path.is_file() and json_path.is_file()
