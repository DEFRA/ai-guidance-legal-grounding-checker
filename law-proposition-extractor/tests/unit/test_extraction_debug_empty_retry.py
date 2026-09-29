"""debug-extract-fragment uses production empty-extraction retry semantics."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.extraction_debug import debug_extract_fragment
from law_proposition_extractor_pipeline.extraction_empty_failure import (
    EXTRACTION_SCHEMA_VIOLATION,
    TRANSPORT_EMPTY_RESPONSE,
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

    def complete_text(self, *, prompt: str, **_kwargs: object) -> str:
        return self.complete_text_result(prompt=prompt, **_kwargs).content

    def complete_text_result(self, *, prompt: str, **_kwargs: object) -> TextCompletionResult:
        content = self._responses.pop(0) if self._responses else "{}"
        return TextCompletionResult(content=content, finish_reason="stop")


def _mock_llm_client(seq: _SequentialLlm) -> MagicMock:
    client = MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000
    client.complete_text.side_effect = seq.complete_text
    client.complete_text_result.side_effect = seq.complete_text_result
    return client


def _write_case(tmp_path: Path, *, sentence: str) -> Path:
    case_path = tmp_path / "case.json"
    case_path.write_text(
        json.dumps(
            {
                "topic": {"name": "slurry", "description": "", "subject_tags": []},
                "cluster": {"name": "slurry", "description": ""},
                "sources": [
                    {
                        "id": "src-debug-1",
                        "title": "Instrument",
                        "jurisdiction": "UK",
                        "citation": "DBG",
                        "kind": "regulation",
                        "text": sentence,
                        "fragment_locator": "regulation:1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return case_path


def test_debug_extract_fragment_retries_empty_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sentence = "Operators must store slurry safely."
    seq = _SequentialLlm(["{}", _valid_proposition_payload(sentence)])
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.extraction_debug.JuditLLMClient",
        lambda: _mock_llm_client(seq),
    )

    payload = debug_extract_fragment(
        _write_case(tmp_path, sentence=sentence),
        source_id="src-debug-1",
        locator="regulation:1",
        extraction_mode="local",
        retry_empty_extraction=True,
    )

    assert payload["retry_empty_extraction"] is True
    assert payload["local_few_shot_prompt_mode"] is True
    assert payload["proposition_count"] > 0
    assert len(payload["attempts"]) == 2
    assert payload["attempts"][0]["attempt_index"] == 1
    assert payload["attempts"][0]["raw_model_response"] == "{}"
    assert payload["attempts"][0]["failure_type"] == EXTRACTION_SCHEMA_VIOLATION
    assert "proposition_count" not in payload["attempts"][0]
    assert payload["attempts"][1]["attempt_index"] == 2
    assert payload["attempts"][1]["failure_type"] is None
    assert payload["attempts"][1]["previous_failure_type"] == EXTRACTION_SCHEMA_VIOLATION
    assert payload["attempts"][1]["proposition_count"] == payload["proposition_count"]


def test_debug_extract_fragment_reports_retry_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seq = _SequentialLlm(["{}"])
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.extraction_debug.JuditLLMClient",
        lambda: _mock_llm_client(seq),
    )

    payload = debug_extract_fragment(
        _write_case(tmp_path, sentence="Operators must store slurry safely."),
        source_id="src-debug-1",
        locator="regulation:1",
        extraction_mode="local",
        retry_empty_extraction=False,
    )

    assert payload["retry_empty_extraction"] is False
    assert len(payload["attempts"]) == 1
    assert payload["proposition_count"] == 0


def test_debug_extract_fragment_reports_retry_not_eligible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seq = _SequentialLlm([""])
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.extraction_debug.JuditLLMClient",
        lambda: _mock_llm_client(seq),
    )

    payload = debug_extract_fragment(
        _write_case(tmp_path, sentence="Operators must store slurry safely."),
        source_id="src-debug-1",
        locator="regulation:1",
        extraction_mode="local",
        retry_empty_extraction=True,
    )

    assert payload["retry_empty_extraction"] is True
    assert payload["retry_eligible"] is False
    assert "transport_empty_response" in payload["retry_not_eligible_reason"]
    assert len(payload["attempts"]) == 1
    assert payload["attempts"][0]["failure_type"] == TRANSPORT_EMPTY_RESPONSE
