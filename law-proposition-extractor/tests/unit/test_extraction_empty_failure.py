"""Granular empty LLM extraction failure classification and inspection."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from law_proposition_extractor_domain import Cluster, SourceRecord, Topic
from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.extraction_empty_failure import (
    EXTRACTION_SCHEMA_VIOLATION,
    NON_JSON_RESPONSE,
    PARSED_EMPTY_PROPOSITION_LIST,
    POST_FILTER_REMOVED_ALL,
    SCHEMA_VALID_BUT_EMPTY,
    TRANSPORT_EMPTY_RESPONSE,
    classify_empty_extraction_outcome,
    classify_extraction_failure_type,
)
from law_proposition_extractor_pipeline.extraction_inspection import (
    collect_raw_failure_examples,
    summarize_extraction_jobs,
)
from law_proposition_extractor_pipeline.extract import _try_extract_model_v2_json, _validate_v2_items


def _source() -> SourceRecord:
    return SourceRecord(
        id="src-1",
        title="Test instrument",
        jurisdiction="UK",
        citation="TEST",
        kind="regulation",
        authoritative_text="1 Operators must store slurry safely.",
        authoritative_locator="regulation:1",
        current_snapshot_id="snap-1",
        metadata={},
    )


def _topic_cluster() -> tuple[Topic, Cluster]:
    topic = Topic(id="t1", name="slurry", description="", subject_tags=[])
    cluster = Cluster(id="c1", topic_id="t1", name="c", description="")
    return topic, cluster


class _StubLlm:
    def __init__(self, content: str) -> None:
        self._content = content

    def complete_text(self, **_kwargs: object) -> str:
        return self.complete_text_result(**_kwargs).content

    def complete_text_result(self, **_kwargs: object) -> TextCompletionResult:
        return TextCompletionResult(content=self._content, finish_reason="stop")


def test_transport_empty_response() -> None:
    client = _StubLlm("")
    topic, cluster = _topic_cluster()
    rows, err, diag = _try_extract_model_v2_json(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=client,  # type: ignore[arg-type]
        model_alias="local_extract",
        extraction_mode="local",
        max_propositions=4,
    )
    assert rows is None
    assert err == "provider returned no content"
    assert diag is not None
    assert diag["failure_type"] == TRANSPORT_EMPTY_RESPONSE


def test_parsed_empty_proposition_list() -> None:
    client = _StubLlm(json.dumps({"propositions": []}))
    topic, cluster = _topic_cluster()
    rows, err, diag = _try_extract_model_v2_json(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=client,  # type: ignore[arg-type]
        model_alias="local_extract",
        extraction_mode="local",
        max_propositions=4,
        extraction_output_mode="json_object",
    )
    assert rows is None
    assert diag is not None
    assert diag["failure_type"] == PARSED_EMPTY_PROPOSITION_LIST
    assert "propositions=[]" in (err or "")


def test_non_json_response() -> None:
    client = _StubLlm("Here are the obligations: operators must comply.")
    topic, cluster = _topic_cluster()
    rows, err, diag = _try_extract_model_v2_json(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=client,  # type: ignore[arg-type]
        model_alias="local_extract",
        extraction_mode="local",
        max_propositions=4,
    )
    assert rows is None
    assert diag is not None
    assert diag["failure_type"] == NON_JSON_RESPONSE
    assert "JSON parse" in (err or "")


def test_post_filter_removed_all_via_validation() -> None:
    raw_rows = [
        {
            "proposition_text": "Operators must store slurry.",
            "subject": "operators",
            "rule": "must store",
            "object": "",
            "conditions": [],
            "exceptions": [],
            "temporal_condition": "",
            "provision_type": "core",
            "source_locator": "regulation:1",
            "evidence_text": "this text is not in the source chunk at all",
            "completeness_status": "complete",
            "confidence": "high",
            "reason": "test",
        }
    ]
    accepted, errors, _issues = _validate_v2_items(raw_rows, _source().authoritative_text, limit=4)
    assert not accepted
    assert errors
    ftype, freason = classify_empty_extraction_outcome(
        raw=json.dumps({"propositions": raw_rows}),
        parsed={"propositions": raw_rows},
        raw_rows=raw_rows,
    )
    assert ftype == POST_FILTER_REMOVED_ALL
    assert "validation removed all" in freason


def test_empty_json_object_without_propositions_field() -> None:
    client = _StubLlm("{}")
    topic, cluster = _topic_cluster()
    _rows, _err, diag = _try_extract_model_v2_json(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=client,  # type: ignore[arg-type]
        model_alias="local_extract",
        extraction_mode="local",
        max_propositions=4,
        extraction_output_mode="json_schema",
    )
    assert diag is not None
    assert diag["failure_type"] == EXTRACTION_SCHEMA_VIOLATION


def test_schema_valid_but_empty_atoms() -> None:
    ftype, _ = classify_empty_extraction_outcome(
        raw='{"propositions":[{"display_label":"x"}]}',
        parsed={"propositions": [{"display_label": "x"}]},
        raw_rows=[{"display_label": "x"}],
    )
    assert ftype == SCHEMA_VALID_BUT_EMPTY


def test_classify_extraction_failure_type_prefers_explicit() -> None:
    assert (
        classify_extraction_failure_type(
            "model returned no propositions",
            explicit_failure_type=PARSED_EMPTY_PROPOSITION_LIST,
        )
        == PARSED_EMPTY_PROPOSITION_LIST
    )


def test_collect_raw_failure_examples_from_traces() -> None:
    bundle = {
        "proposition_extraction_jobs": [],
        "extraction_llm_call_traces": [
            {
                "source_record_id": "src-a",
                "fragment_locator": "reg:1",
                "llm_call_attempted": True,
                "llm_invoked": True,
                "llm_call_succeeded": False,
                "failure_type": PARSED_EMPTY_PROPOSITION_LIST,
                "failure_reason": "model returned valid JSON with propositions=[]",
                "raw_model_output_excerpt": '{"propositions":[]}',
                "model_alias": "local_extract",
                "finish_reason": "stop",
                "prompt_hash": "abc123",
                "estimated_input_tokens": 42,
            }
        ],
    }
    examples = collect_raw_failure_examples(bundle, limit=5)
    assert len(examples) == 1
    assert examples[0]["failure_type"] == PARSED_EMPTY_PROPOSITION_LIST
    summary = summarize_extraction_jobs(bundle, raw_failure_example_limit=3)
    assert len(summary["raw_failure_examples"]) == 1
