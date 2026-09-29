"""Local extraction benchmark command and success criteria."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from law_proposition_extractor_llm import JuditLLMClient
from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.extraction_benchmark import (
    benchmark_local_extraction,
    format_benchmark_summary_table,
    is_benchmark_extraction_success,
    parse_locators,
    parse_model_aliases,
    resolve_model_output_mode,
    run_single_benchmark_extraction,
)
from law_proposition_extractor_pipeline.extraction_empty_failure import (
    EXTRACTION_SCHEMA_VIOLATION,
    NON_JSON_RESPONSE,
    SCHEMA_VALID_BUT_EMPTY,
)


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
        self.json_schema_calls = 0
        self.json_object_calls = 0

    def complete_text(self, *, prompt: str, **_kwargs: object) -> str:
        return self.complete_text_result(prompt=prompt, **_kwargs).content

    def complete_text_result(self, *, prompt: str, **_kwargs: object) -> TextCompletionResult:
        if _kwargs.get("json_schema") is not None:
            self.json_schema_calls += 1
        elif _kwargs.get("enforce_json_object"):
            self.json_object_calls += 1
        content = self._responses.pop(0) if self._responses else "{}"
        return TextCompletionResult(content=content, finish_reason="stop")


def _mock_llm_client(seq: _SequentialLlm, *, model_alias: str = "local_extract") -> JuditLLMClient:
    client = JuditLLMClient.__new__(JuditLLMClient)
    client.settings = MagicMock()
    client.settings.local_extract_model = model_alias
    client.settings.frontier_extract_model = model_alias
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000
    client.complete_text = seq.complete_text
    client.complete_text_result = seq.complete_text_result
    return client


def _write_case(tmp_path: Path, *, sentence: str, locator: str = "regulation:1") -> Path:
    case_path = tmp_path / "case.json"
    case_path.write_text(
        json.dumps(
            {
                "topic": {"name": "slurry", "description": "", "subject_tags": []},
                "cluster": {"name": "slurry", "description": ""},
                "sources": [
                    {
                        "id": "lex-120b4f9c395b3f94",
                        "title": "Instrument",
                        "jurisdiction": "UK",
                        "citation": "DBG",
                        "kind": "regulation",
                        "text": sentence,
                        "fragment_locator": locator,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return case_path


def test_resolve_model_output_mode() -> None:
    assert resolve_model_output_mode("local_extract", extraction_mode="local") == "json_schema"
    assert resolve_model_output_mode("qwen3_14b_schema") == "json_schema"
    assert resolve_model_output_mode("frontier_extract", extraction_mode="frontier") == "json_object"


def test_parse_locators_and_models() -> None:
    assert parse_locators(locator="regulation:1", locators=None) == ["regulation:1"]
    assert parse_locators(
        locator=None, locators="regulation:1, regulation:2"
    ) == ["regulation:1", "regulation:2"]
    assert parse_model_aliases("local_extract,qwen3_14b_schema") == [
        "local_extract",
        "qwen3_14b_schema",
    ]


def test_is_benchmark_extraction_success_validated_row() -> None:
    assert is_benchmark_extraction_success(
        outcome_proposition_count=1,
        parse_result={"validated_row_count": 1, "failure_type": None},
        last_trace={"failure_type": None},
    )


def test_is_benchmark_extraction_success_empty_rationale() -> None:
    raw = json.dumps({"propositions": [], "empty_rationale": "non-substantive heading"})
    assert is_benchmark_extraction_success(
        outcome_proposition_count=0,
        parse_result={"validated_row_count": 0, "failure_type": SCHEMA_VALID_BUT_EMPTY},
        last_trace={"failure_type": SCHEMA_VALID_BUT_EMPTY, "raw_model_output_excerpt": raw},
    )


def test_is_benchmark_extraction_success_rejects_non_json() -> None:
    assert not is_benchmark_extraction_success(
        outcome_proposition_count=0,
        parse_result={"validated_row_count": 0, "failure_type": NON_JSON_RESPONSE},
        last_trace={"failure_type": NON_JSON_RESPONSE, "raw_model_output_excerpt": "not json"},
    )


def test_run_single_benchmark_extraction_records_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sentence = "Operators must store slurry safely."
    seq = _SequentialLlm([_valid_proposition_payload(sentence)])
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.extraction_benchmark.JuditLLMClient",
        lambda *_args, **_kwargs: _mock_llm_client(seq),
    )

    run = run_single_benchmark_extraction(
        _write_case(tmp_path, sentence=sentence),
        source_id="lex-120b4f9c395b3f94",
        locator="regulation:1",
        model_alias="local_extract",
    )

    assert run["success"] is True
    assert run["output_mode"] == "json_schema"
    assert run["few_shot_marker_present"] is True
    assert run["proposition_count"] == 1
    assert run["validated_row_count"] == 1
    assert run["estimated_input_tokens"] > 0
    assert run["latency_ms"] >= 0
    assert seq.json_schema_calls == 1
    assert seq.json_object_calls == 0


def test_run_single_benchmark_extraction_uses_json_schema_for_schema_alias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sentence = "Operators must store slurry safely."
    seq = _SequentialLlm([_valid_proposition_payload(sentence)])
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.extraction_benchmark.JuditLLMClient",
        lambda *_args, **_kwargs: _mock_llm_client(seq, model_alias="qwen3_14b_schema"),
    )

    run = run_single_benchmark_extraction(
        _write_case(tmp_path, sentence=sentence),
        source_id="lex-120b4f9c395b3f94",
        locator="regulation:1",
        model_alias="qwen3_14b_schema",
    )

    assert run["output_mode"] == "json_schema"
    assert seq.json_schema_calls == 1
    assert seq.json_object_calls == 0


def test_benchmark_local_extraction_aggregates_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sentence = "Operators must store slurry safely."
    seq = _SequentialLlm([_valid_proposition_payload(sentence), "{}"])
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.extraction_benchmark.JuditLLMClient",
        lambda *_args, **_kwargs: _mock_llm_client(seq),
    )

    payload = benchmark_local_extraction(
        _write_case(tmp_path, sentence=sentence),
        source_id="lex-120b4f9c395b3f94",
        locators="regulation:1",
        models="local_extract",
        attempts=2,
        retry_empty_extraction=False,
    )

    summary = payload["summary_by_model"][0]
    assert summary["model_alias"] == "local_extract"
    assert summary["attempts"] == 2
    assert summary["success_rate"] == 0.5
    assert summary["avg_props"] == 0.5
    assert summary["dominant_failure"] == EXTRACTION_SCHEMA_VIOLATION


def test_format_benchmark_summary_table() -> None:
    table = format_benchmark_summary_table(
        [
            {
                "model_alias": "local_extract",
                "output_mode": "json_object",
                "attempts": 3,
                "success_rate": 0.67,
                "avg_props": 1.0,
                "dominant_failure": None,
                "avg_latency_ms": 1200.0,
            }
        ]
    )
    assert "model_alias" in table
    assert "local_extract" in table
    assert "0.67" in table
