"""Tests for dual Law Proposition Extractor law-source loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proposition_matcher.pipeline.law_loading import (
    detect_law_source,
    law_display_text,
    load_law_units,
)


def _minimal_prop(**overrides) -> dict:
    base = {
        "id": "prop:abc",
        "topic_id": "topic-1",
        "source_record_id": "src-1",
        "jurisdiction": "GB",
        "proposition_text": "An occupier must not cause pollution.",
        "legal_subject": "occupier",
        "action": "must not cause pollution",
        "fragment_locator": "regulation 2(1)",
    }
    base.update(overrides)
    return base


def _minimal_candidate(**overrides) -> dict:
    base = {
        "id": "bcand:deadbeef",
        "statement_text": "An occupier must not cause pollution.",
        "matching_text": (
            "Title: Pollution duty\n"
            "Law: An occupier must not cause pollution.\n"
            "Source: SI 2015/1234, regulation 2(1)"
        ),
        "presentation": {"locator_label": "regulation 2(1)"},
        "evidence": {"fragment_locators": ["regulation 2(1)"]},
        "source_proposition_ids": ["prop:abc"],
    }
    base.update(overrides)
    return base


def test_detect_propositions_list():
    assert detect_law_source([_minimal_prop()]) == "propositions"


def test_detect_propositions_wrapped():
    assert detect_law_source({"propositions": [_minimal_prop()]}) == "propositions"


def test_detect_candidates():
    assert detect_law_source({"candidates": [_minimal_candidate()], "schema_version": "1"}) == "candidates"


def test_detect_ambiguous_both_keys():
    with pytest.raises(ValueError, match="both"):
        detect_law_source({"propositions": [], "candidates": []})


def test_detect_unknown_shape():
    with pytest.raises(ValueError, match="unrecognised"):
        detect_law_source({"statements": []})


def test_load_propositions_list(tmp_path: Path):
    path = tmp_path / "propositions.json"
    path.write_text(json.dumps([_minimal_prop()]))
    units, source = load_law_units(path, source="auto")
    assert source == "propositions"
    assert len(units) == 1
    u = units[0]
    assert u.id == "prop:abc"
    assert u.embed_text == u.display_text == "An occupier must not cause pollution."
    assert u.citation == "regulation 2(1)"
    assert u.proposition_text == u.display_text
    assert u.payload["proposition_text"] == u.display_text


def test_load_propositions_wrapped(tmp_path: Path):
    path = tmp_path / "propositions.json"
    path.write_text(json.dumps({"propositions": [_minimal_prop(id="prop:x")]}))
    units, source = load_law_units(path, source="propositions")
    assert source == "propositions"
    assert units[0].id == "prop:x"


def test_load_candidates(tmp_path: Path):
    path = tmp_path / "proposition_matcher_law_candidates.json"
    path.write_text(json.dumps({"candidates": [_minimal_candidate()], "candidate_count": 1}))
    units, source = load_law_units(path, source="auto")
    assert source == "candidates"
    assert len(units) == 1
    u = units[0]
    assert u.id == "bcand:deadbeef"
    assert u.embed_text.startswith("Title: Pollution duty")
    assert u.display_text == "An occupier must not cause pollution."
    assert u.citation == "regulation 2(1)"
    assert u.payload["statement_text"] == u.display_text


def test_load_candidates_empty_matching_text_falls_back(tmp_path: Path):
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps({
        "candidates": [_minimal_candidate(matching_text="", statement_text="Fallback statement.")],
    }))
    units, _ = load_law_units(path, source="candidates")
    assert units[0].embed_text == "Fallback statement."
    assert units[0].display_text == "Fallback statement."


def test_explicit_source_mismatch(tmp_path: Path):
    path = tmp_path / "propositions.json"
    path.write_text(json.dumps({"propositions": [_minimal_prop()]}))
    with pytest.raises(SystemExit, match="looks like propositions"):
        load_law_units(path, source="candidates")


def test_law_display_text_prefers_proposition_then_statement():
    assert law_display_text({"proposition_text": "P", "statement_text": "S"}) == "P"
    assert law_display_text({"statement_text": "S"}) == "S"
    assert law_display_text({}) == ""
