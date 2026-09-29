"""Local-mode few-shot extraction prompt and empty-JSON regression."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from law_proposition_extractor_domain import Cluster, SourceRecord, Topic
from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.extract import (
    LOCAL_FEWSHOT_PROMPT_MARKER,
    _v2_model_prompt,
    extract_propositions_from_source,
    local_few_shot_prompt_used,
)
from law_proposition_extractor_pipeline.extraction_debug import debug_extract_fragment


def _topic() -> Topic:
    return Topic(id="topic-fs", name="T", description="", subject_tags=[])


def _cluster() -> Cluster:
    return Cluster(id="cluster-fs", topic_id="topic-fs", name="C", description="")


def _source(text: str) -> SourceRecord:
    return SourceRecord(
        id="src-fs",
        title="Instrument",
        jurisdiction="UK",
        citation="C-FS",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator="regulation:1",
        current_snapshot_id="snap-fs",
        metadata={},
    )


def _valid_reg1_payload(*, sentence: str) -> str:
    return json.dumps(
        {
            "propositions": [
                {
                    "proposition_text": sentence,
                    "display_label": "Citation",
                    "subject": "These Regulations",
                    "rule": "may be cited as",
                    "object": "the Nitrate Pollution Prevention Regulations 2015",
                    "conditions": [],
                    "exceptions": [],
                    "temporal_condition": "",
                    "provision_type": "core",
                    "source_locator": "regulation:1",
                    "evidence_text": sentence,
                    "completeness_status": "complete",
                    "confidence": "high",
                    "reason": "citation",
                }
            ]
        }
    )


class _MarkerGatedLlm:
    """Returns {} unless the prompt includes the local few-shot marker."""

    def __init__(self, *, sentence: str) -> None:
        self._sentence = sentence

    def complete_text(self, *, prompt: str, **_kwargs: object) -> str:
        return self.complete_text_result(prompt=prompt, **_kwargs).content

    def complete_text_result(self, *, prompt: str, **_kwargs: object) -> TextCompletionResult:
        if LOCAL_FEWSHOT_PROMPT_MARKER in prompt:
            return TextCompletionResult(
                content=_valid_reg1_payload(sentence=self._sentence),
                finish_reason="stop",
            )
        return TextCompletionResult(content="{}", finish_reason="stop")


def _mock_llm_client(seq: _MarkerGatedLlm) -> MagicMock:
    client = MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000
    client.complete_text.side_effect = seq.complete_text
    client.complete_text_result.side_effect = seq.complete_text_result
    return client


def test_local_few_shot_prompt_used_only_for_local_mode() -> None:
    assert local_few_shot_prompt_used("local") is True
    assert local_few_shot_prompt_used("frontier") is False


def test_local_prompt_includes_few_shot_marker_and_invalid_guidance() -> None:
    text = _v2_model_prompt(
        _source("Real fragment text."),
        _topic(),
        _cluster(),
        extraction_mode="local",
        max_propositions=4,
    )
    assert LOCAL_FEWSHOT_PROMPT_MARKER in text
    assert "INVALID outputs" in text
    assert "{}" in text
    assert '"propositions":null' in text
    assert "VALID JSON:" in text
    assert "Example Regulations 2026" in text
    assert "Now extract from the following real fragment." in text
    assert text.index("Now extract from the following real fragment.") < text.index(
        "Operative source text:"
    )


def test_frontier_prompt_excludes_local_few_shot_marker() -> None:
    text = _v2_model_prompt(
        _source("Real fragment text."),
        _topic(),
        _cluster(),
        extraction_mode="frontier",
        max_propositions=4,
    )
    assert LOCAL_FEWSHOT_PROMPT_MARKER not in text
    assert "Example Regulations 2026" not in text


def test_local_extraction_succeeds_when_prompt_has_few_shot_marker() -> None:
    sentence = (
        "1 These Regulations may be cited as the Nitrate Pollution Prevention Regulations 2015."
    )
    reg1 = f"{sentence}\n2 These Regulations come into force on 1st May 2015."
    client = _mock_llm_client(_MarkerGatedLlm(sentence=sentence))
    out = extract_propositions_from_source(
        _source(reg1),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        retry_empty_extraction=False,
    )
    assert len(out.propositions) == 1
    # v2 extraction uses the richer complete_text_result API (finish_reason aware).
    assert client.complete_text_result.call_count == 1
    first_prompt = client.complete_text_result.call_args.kwargs["prompt"]
    assert LOCAL_FEWSHOT_PROMPT_MARKER in first_prompt


def test_debug_extract_fragment_reports_local_few_shot_prompt_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    case_path = tmp_path / "case.json"
    case_path.write_text(
        json.dumps(
            {
                "topic": {"name": "nitrate", "description": "", "subject_tags": []},
                "cluster": {"name": "nitrate", "description": ""},
                "sources": [
                    {
                        "id": "src-nitrate",
                        "title": "Nitrate Regulations",
                        "jurisdiction": "UK",
                        "citation": "SI 2015",
                        "kind": "regulation",
                        "text": "1 These Regulations may be cited as the Nitrate Regulations 2015.",
                        "fragment_locator": "regulation:1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    sentence = "1 These Regulations may be cited as the Nitrate Regulations 2015."
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.extraction_debug.JuditLLMClient",
        lambda: _mock_llm_client(_MarkerGatedLlm(sentence=sentence)),
    )

    payload = debug_extract_fragment(
        case_path,
        source_id="src-nitrate",
        locator="regulation:1",
        extraction_mode="local",
        retry_empty_extraction=False,
    )

    assert payload["local_few_shot_prompt_mode"] is True
    assert payload["proposition_count"] == 1
