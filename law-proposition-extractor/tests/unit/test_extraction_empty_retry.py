"""Targeted retry when local/frontier extraction returns empty JSON."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from law_proposition_extractor_domain import Cluster, SourceRecord, Topic
from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.extraction_empty_failure import (
    EXTRACTION_SCHEMA_VIOLATION,
    SCHEMA_VALID_BUT_EMPTY,
    TRANSPORT_EMPTY_RESPONSE,
)
from law_proposition_extractor_pipeline.extraction_llm_metrics import compute_extraction_llm_trace_summary_metrics
from law_proposition_extractor_pipeline.extract import extract_propositions_from_source


def _topic() -> Topic:
    return Topic(id="topic-er", name="slurry", description="", subject_tags=[])


def _cluster() -> Cluster:
    return Cluster(id="cluster-er", topic_id="topic-er", name="c", description="")


def _source(*, text: str = "Operators must store slurry safely.") -> SourceRecord:
    return SourceRecord(
        id="src-er-1",
        title="Instrument",
        jurisdiction="UK",
        citation="C-ER",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator="regulation:1",
        current_snapshot_id="snap-er-1",
        metadata={},
    )


def _mock_llm_client() -> MagicMock:
    client = MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000
    return client


def _valid_proposition_payload(sentence: str) -> str:
    return json.dumps(
        {
            "propositions": [
                {
                    "proposition_text": sentence,
                    "display_label": "L",
                    "subject": "operators",
                    "rule": "must store slurry safely",
                    "object": "",
                    "conditions": [],
                    "exceptions": [],
                    "temporal_condition": "",
                    "provision_type": "core",
                    "source_locator": "regulation:1",
                    "evidence_text": sentence,
                    "completeness_status": "complete",
                    "confidence": "high",
                    "reason": "test",
                }
            ]
        }
    )


class _SequentialLlm:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete_text(self, *, prompt: str, **_kwargs: object) -> str:
        return self.complete_text_result(prompt=prompt, **_kwargs).content

    def complete_text_result(self, *, prompt: str, **_kwargs: object) -> TextCompletionResult:
        self.prompts.append(prompt)
        content = self._responses.pop(0) if self._responses else "{}"
        return TextCompletionResult(content=content, finish_reason="stop")


def test_empty_json_retry_returns_propositions() -> None:
    sentence = "Operators must store slurry safely."
    seq = _SequentialLlm(["{}", _valid_proposition_payload(sentence)])
    client = _mock_llm_client()
    client.complete_text.side_effect = seq.complete_text
    client.complete_text_result.side_effect = seq.complete_text_result

    out = extract_propositions_from_source(
        _source(text=sentence),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
    )

    assert len(out.propositions) == 1
    assert len(seq.prompts) == 2
    assert "Your previous response was `{}`" in seq.prompts[1]
    assert "propositions" in seq.prompts[1]

    traces = out.extraction_llm_call_traces
    assert len(traces) == 2
    assert traces[0]["attempt_index"] == 0
    assert traces[0]["failure_type"] == EXTRACTION_SCHEMA_VIOLATION
    assert traces[0]["raw_model_output_excerpt"] == "{}"
    assert traces[0]["llm_call_succeeded"] is False
    assert traces[1]["attempt_index"] == 1
    assert traces[1]["previous_failure_type"] == EXTRACTION_SCHEMA_VIOLATION
    assert traces[1]["llm_call_succeeded"] is True

    metrics = compute_extraction_llm_trace_summary_metrics(traces)
    assert metrics["first_attempt_failed"] == 1
    assert metrics["retry_attempted"] == 1
    assert metrics["retry_successful"] == 1
    assert metrics["retry_failed"] == 0
    assert metrics["live_llm_calls_attempted"] == 2


def test_empty_json_retry_still_empty_fails_schema_valid_but_empty() -> None:
    seq = _SequentialLlm(["{}", "{}"])
    client = _mock_llm_client()
    client.complete_text.side_effect = seq.complete_text
    client.complete_text_result.side_effect = seq.complete_text_result

    out = extract_propositions_from_source(
        _source(),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
    )

    assert out.failed_closed
    assert not out.propositions
    assert len(seq.prompts) == 2

    traces = out.extraction_llm_call_traces
    assert len(traces) == 2
    assert traces[1]["failure_type"] == EXTRACTION_SCHEMA_VIOLATION
    assert traces[1]["llm_call_succeeded"] is False

    metrics = compute_extraction_llm_trace_summary_metrics(traces)
    assert metrics["first_attempt_failed"] == 1
    assert metrics["retry_attempted"] == 1
    assert metrics["retry_successful"] == 0
    assert metrics["retry_failed"] == 1


def test_transport_empty_does_not_retry_by_default() -> None:
    seq = _SequentialLlm(["", _valid_proposition_payload("Operators must store slurry safely.")])
    client = _mock_llm_client()
    client.complete_text.side_effect = seq.complete_text
    client.complete_text_result.side_effect = seq.complete_text_result

    out = extract_propositions_from_source(
        _source(),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        retry_empty_extraction_transport=False,
    )

    assert out.failed_closed
    assert len(seq.prompts) == 1
    traces = out.extraction_llm_call_traces
    assert len(traces) == 1
    assert traces[0]["failure_type"] == TRANSPORT_EMPTY_RESPONSE

    metrics = compute_extraction_llm_trace_summary_metrics(traces)
    assert metrics["retry_attempted"] == 0


def test_transport_empty_retries_when_explicitly_configured() -> None:
    sentence = "Operators must store slurry safely."
    seq = _SequentialLlm(["", _valid_proposition_payload(sentence)])
    client = _mock_llm_client()
    client.complete_text.side_effect = seq.complete_text
    client.complete_text_result.side_effect = seq.complete_text_result

    out = extract_propositions_from_source(
        _source(text=sentence),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        retry_empty_extraction_transport=True,
    )

    assert len(out.propositions) == 1
    assert len(seq.prompts) == 2
    metrics = compute_extraction_llm_trace_summary_metrics(out.extraction_llm_call_traces)
    assert metrics["retry_attempted"] == 1
    assert metrics["retry_successful"] == 1
