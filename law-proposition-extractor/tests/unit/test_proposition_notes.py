from law_proposition_extractor_domain import Proposition, attach_extraction_meta, split_proposition_notes
from law_proposition_extractor_domain.proposition_notes import assign_proposition_extraction_debug, slim_proposition_extraction_meta


def test_split_meta_only_notes_has_no_human_review() -> None:
    meta = {"extraction_mode": "frontier", "evidence_quote": "verbatim span"}
    notes = attach_extraction_meta("", meta)
    parsed = split_proposition_notes(notes)
    assert parsed.extraction_meta == meta
    assert parsed.review_notes is None
    assert parsed.human_notes == ""


def test_split_mixed_notes_preserves_human_tail() -> None:
    meta = {"extraction_mode": "heuristic"}
    notes = attach_extraction_meta("Reviewer: check NVZ boundary.", meta)
    parsed = split_proposition_notes(notes)
    assert parsed.review_notes == "Reviewer: check NVZ boundary."
    assert parsed.extraction_meta == meta


def test_invalid_meta_json_preserves_original_notes() -> None:
    notes = "judit_extraction_meta:{not-json}\nReviewer note"
    parsed = split_proposition_notes(notes)
    assert parsed.meta_parse_failed is True
    assert parsed.human_notes == notes
    assert parsed.extraction_meta is None


def test_proposition_model_separates_legacy_notes_on_load() -> None:
    meta = {
        "extraction_mode": "frontier",
        "evidence_quote": "Operators must keep records.",
        "extraction_llm_call_traces": [{"llm_invoked": True, "raw_model_output_excerpt": "huge"}],
    }
    notes = attach_extraction_meta("Human reviewer comment.", meta)
    prop = Proposition.model_validate(
        {
            "id": "prop-001",
            "topic_id": "topic-001",
            "source_record_id": "src-001",
            "jurisdiction": "UK",
            "proposition_text": "Operators must keep records.",
            "legal_subject": "operator",
            "action": "keep records",
            "notes": notes,
        }
    )
    assert prop.review_notes == "Human reviewer comment."
    assert not str(prop.notes).startswith("judit_extraction_meta:")
    assert prop.extraction_debug_meta is not None
    assert "extraction_llm_call_traces" not in (prop.extraction_debug_meta or {})
    assert prop.extraction_debug_meta.get("evidence_quote") == "Operators must keep records."


def test_assign_extraction_debug_does_not_write_meta_to_notes() -> None:
    prop = Proposition(
        id="prop-002",
        topic_id="topic-001",
        source_record_id="src-001",
        jurisdiction="UK",
        proposition_text="Text.",
        legal_subject="x",
        action="y",
        review_notes="Keep this.",
    )
    assign_proposition_extraction_debug(
        prop,
        {"extraction_mode": "local", "evidence_quote": "Text."},
    )
    assert prop.extraction_debug_meta is not None
    assert prop.review_notes == "Keep this."
    assert "judit_extraction_meta" not in (prop.notes or "")


def test_slim_meta_strips_trace_only_keys() -> None:
    raw = {
        "extraction_mode": "frontier",
        "raw_model_output_excerpt": "blob",
        "extraction_llm_call_traces": [{"x": 1}],
    }
    slim = slim_proposition_extraction_meta(raw)
    assert slim.get("extraction_mode") == "frontier"
    assert "raw_model_output_excerpt" not in slim
    assert "extraction_llm_call_traces" not in slim


def test_meta_only_notes_yield_null_review_notes_on_model() -> None:
    prop = Proposition.model_validate(
        {
            "id": "prop-003",
            "topic_id": "t",
            "source_record_id": "s",
            "jurisdiction": "UK",
            "proposition_text": "P",
            "legal_subject": "a",
            "action": "b",
            "notes": attach_extraction_meta("", {"extraction_mode": "heuristic"}),
        }
    )
    assert prop.review_notes is None
    assert prop.extraction_debug_meta is not None
