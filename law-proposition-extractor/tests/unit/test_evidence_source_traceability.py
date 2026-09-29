"""Source-backed evidence constraints for frontier / v2 model extraction."""

import json
from unittest.mock import MagicMock

from law_proposition_extractor_domain import Cluster, ReviewStatus, SourceRecord, Topic
from law_proposition_extractor_pipeline.extract import (
    EXTRACTION_SCHEMA_VERSION_V2,
    _v2_model_prompt,
    evidence_locates_verbatim_after_normalisation,
    extract_propositions_from_source,
    resolve_extraction_meta_for_proposition,
)


def _topic() -> Topic:
    return Topic(id="topic-ev-t", name="T", description="", subject_tags=[])


def _cluster() -> Cluster:
    return Cluster(id="cluster-ev-t", topic_id="topic-ev-t", name="C", description="")


def _source(text: str) -> SourceRecord:
    return SourceRecord(
        id="src-evidence-t",
        title="Instrument",
        jurisdiction="UK",
        citation="C-EV",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator="article:2",
        current_snapshot_id="snap-evidence-t",
        metadata={},
    )


def _mock_llm() -> MagicMock:
    client = MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000
    return client


def _v2_row(
    *,
    proposition_text: str = "Operators shall maintain registers.",
    evidence_text: str = "Operators shall maintain registers.",
    reason: str = "aligned with source wording",
) -> dict[str, object]:
    return {
        "proposition_text": proposition_text,
        "display_label": "Lbl",
        "subject": "operators",
        "rule": "maintain registers",
        "object": "",
        "conditions": [],
        "exceptions": [],
        "temporal_condition": "",
        "provision_type": "core",
        "source_locator": "article:2",
        "evidence_text": evidence_text,
        "completeness_status": "complete",
        "confidence": "high",
        "reason": reason,
    }


def test_evidence_exact_substring_matches() -> None:
    src = "Section 9.\n Operators must maintain records.\n Further text follows."
    assert evidence_locates_verbatim_after_normalisation("Operators must maintain records.", src)[0]


def test_evidence_whitespace_and_newline_tolerance() -> None:
    src = "The operator MUST   maintain\nmovement   records\tbefore dispatch."
    ok, strat, _ = evidence_locates_verbatim_after_normalisation(
        "The operator must maintain movement records before dispatch.", src
    )
    assert ok
    assert "substring" in strat


def test_paraphrase_does_not_match() -> None:
    src = "The competent authority may inspect records relating to equine movements."
    assert not evidence_locates_verbatim_after_normalisation(
        "The regulator can review horse transport paperwork.", src
    )[0]


def test_table_numeric_token_match_on_flattened_schedule_row() -> None:
    src = (
        "After first calf and—annual milk yield more than 9000 litres64315142"
        "annual milk yield between 6000 and 9000 litres53276121"
    )
    ok, strat, diag = evidence_locates_verbatim_after_normalisation(
        "After first calf and—annual milk yield more than 9000 litres 64 315 142",
        src,
    )
    assert ok is True
    assert strat == "table_numeric_token_match"
    assert diag.get("table_match", {}).get("column_tokens") == ["64", "315", "142"]


def test_table_numeric_token_match_weighing_row() -> None:
    src = "females for breeding—weighing more than 500kg4522786Bulls"
    ok, strat, _ = evidence_locates_verbatim_after_normalisation(
        "weighing more than 500kg 45 227 86", src
    )
    assert ok is True
    assert strat == "table_numeric_token_match"


def test_table_numeric_token_match_decimal_poultry_row() -> None:
    src = "from 17 weeks (caged)0.121.131.0from 17 weeks (not caged)"
    ok, strat, _ = evidence_locates_verbatim_after_normalisation(
        "from 17 weeks (caged) 0.12 1.13 1.0", src
    )
    assert ok is True
    assert strat == "table_numeric_token_match"


def test_empty_evidence_without_reason_records_validation_issues() -> None:
    payload = json.dumps({"propositions": [_v2_row(evidence_text="", reason="")]})
    client = _mock_llm()
    client.complete_text.return_value = payload
    out = extract_propositions_from_source(
        _source(text="Standalone normative sentence in source."),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        prompt_version="v2",
    )
    assert out.fallback_used is True
    assert all(p.review_status == ReviewStatus.NEEDS_REVIEW for p in out.propositions)
    assert any("evidence_text empty but reason" in e for e in out.validation_errors)
    assert len(out.validation_issue_records) >= 1
    first = next(x for x in out.validation_issue_records if x.get("reason_code") == "empty_evidence_no_reason")
    assert first["candidate_evidence_text"] == ""
    assert first["failure_reason"]


def test_frontier_prompt_includes_verbatim_instruction() -> None:
    src = _source(text="Dummy instrument text.")
    text = _v2_model_prompt(
        src, _topic(), _cluster(), extraction_mode="frontier", max_propositions=4
    ).lower()
    assert "verbatim" in text
    assert "copied verbatim" in text.replace("\n", " ")


def test_success_stamps_evidence_quote_meta() -> None:
    instrument = (
        "Preamble wording.\n"
        "(a) Operators shall maintain registers;\n"
        "(b) the authority may inspect them."
    )
    row = _v2_row(
        evidence_text="Operators shall maintain registers;",
        proposition_text="Operators must retain registers.",
    )
    payload = json.dumps({"propositions": [row]})
    client = _mock_llm()
    client.complete_text.return_value = payload
    instrument = (
        "Preamble wording.\n"
        "(a) Operators shall maintain registers;\n"
        "(b) the authority may inspect them."
    )
    out = extract_propositions_from_source(
        _source(text=instrument),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="fallback",
        prompt_version="v2",
    )
    assert len(out.propositions) == 1
    p0 = out.propositions[0]
    meta = resolve_extraction_meta_for_proposition(
        notes=p0.notes,
        extraction_debug_meta=p0.extraction_debug_meta,
    )
    assert meta is not None
    assert meta.get("evidence_quote") == row["evidence_text"]


def test_frontier_prompt_includes_focus_scope_instructions() -> None:
    src = _source(text="Dummy.")
    text = _v2_model_prompt(
        src,
        _topic(),
        _cluster(),
        extraction_mode="frontier",
        max_propositions=8,
        focus_scopes=("alpha", "beta"),
    ).lower()
    assert "alpha" in text
    assert "beta" in text
    assert "focus scopes" in text


def test_frontier_prompt_without_focus_scopes_emphasises_cap_and_salience() -> None:
    src = _source(text="Dummy.")
    text = _v2_model_prompt(
        src,
        _topic(),
        _cluster(),
        extraction_mode="frontier",
        max_propositions=5,
        focus_scopes=None,
    ).lower()
    assert "at most 5" in text
    assert "no focus scopes" in text


def test_art109_equine_list_item_accepted_with_focus_scope_config() -> None:
    """Regression: long structured lists must not drop later priority-scope rows (mocked model path)."""
    snippet = (
        "(d)\n"
        "the following information related to kept animals of the equine species:\n"
        "(i)\n"
        "their unique code as provided for in Article 114;\n"
    )
    row = _v2_row(
        proposition_text="Equine database entries must record the unique code provided for in Article 114.",
        evidence_text="their unique code as provided for in Article 114;",
    )
    row["source_locator"] = "article:109(d)(i)"
    payload = json.dumps({"propositions": [row]})
    client = _mock_llm()
    client.complete_text.return_value = payload
    out = extract_propositions_from_source(
        _source(text=snippet),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=8,
        extraction_mode="frontier",
        extraction_fallback="fallback",
        prompt_version="v2",
        focus_scopes=("equine",),
    )
    assert len(out.propositions) == 1
    p0 = out.propositions[0]
    meta = resolve_extraction_meta_for_proposition(
        notes=p0.notes,
        extraction_debug_meta=p0.extraction_debug_meta,
    )
    assert meta is not None
    assert meta.get("focus_scopes") == ["equine"]
    q = meta.get("evidence_quote")
    assert q == row["evidence_text"]
    ok, _, _ = evidence_locates_verbatim_after_normalisation(str(q), snippet)
    assert ok
