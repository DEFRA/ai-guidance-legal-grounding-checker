"""Extraction structured output mode (json_schema vs json_object)."""

from __future__ import annotations

import json
import pytest

from law_proposition_extractor_pipeline.extraction_empty_failure import EXTRACTION_SCHEMA_VIOLATION
from law_proposition_extractor_pipeline.extraction_output_mode import (
    ExtractionOutputModeUnsupportedError,
    ensure_output_mode_supported,
    resolve_extraction_output_mode,
    validate_parsed_extraction_schema,
)
from law_proposition_extractor_pipeline.extract import _try_extract_model_v2_json
from law_proposition_extractor_domain import Cluster, SourceRecord, Topic


def _valid_payload(sentence: str) -> dict:
    return {
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


def test_schema_mode_rejects_empty_object() -> None:
    ok, err = validate_parsed_extraction_schema({}, extraction_output_mode="json_schema")
    assert not ok
    assert err is not None
    assert "propositions" in err


def test_schema_mode_parses_valid_propositions() -> None:
    sentence = "Operators must store slurry safely."
    parsed = _valid_payload(sentence)
    ok, err = validate_parsed_extraction_schema(parsed, extraction_output_mode="json_schema")
    assert ok
    assert err is None


def test_provider_unsupported_raises_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.extraction_output_mode.provider_supports_json_schema",
        lambda **_kwargs: False,
    )
    with pytest.raises(ExtractionOutputModeUnsupportedError) as exc_info:
        ensure_output_mode_supported(
            extraction_output_mode="json_schema",
            extraction_mode="local",
            model_alias="legacy_no_schema",
            allow_fallback=False,
        )
    msg = str(exc_info.value)
    assert "json_schema" in msg
    assert "allow-output-mode-fallback" in msg.lower() or "--allow-output-mode-fallback" in msg


def test_local_default_prefers_json_schema() -> None:
    assert (
        resolve_extraction_output_mode(
            extraction_mode="local",
            model_alias="local_extract",
            requested=None,
        )
        == "json_schema"
    )


def test_frontier_default_json_object_when_not_schema_alias() -> None:
    assert (
        resolve_extraction_output_mode(
            extraction_mode="frontier",
            model_alias="frontier_extract",
            requested=None,
        )
        == "json_object"
    )


class _StubLlm:
    def __init__(self, content: str) -> None:
        self._content = content
        self.last_json_schema: object = None
        self.settings = None

    def complete_text(self, **_kwargs: object) -> str:
        return self.complete_text_result(**_kwargs).content

    def complete_text_result(self, **_kwargs: object):
        from law_proposition_extractor_llm.client import TextCompletionResult

        self.last_json_schema = _kwargs.get("json_schema")
        rf = {"type": "json_schema", "json_schema": _kwargs["json_schema"]} if _kwargs.get(
            "json_schema"
        ) else {"type": "json_object"}
        return TextCompletionResult(
            content=self._content,
            finish_reason="stop",
            response_format=rf,
        )


def _topic_cluster() -> tuple[Topic, Cluster]:
    topic = Topic(id="t1", name="t", description="", subject_tags=[])
    cluster = Cluster(id="c1", topic_id="t1", name="c", description="")
    return topic, cluster


def _source() -> SourceRecord:
    return SourceRecord(
        id="src-1",
        title="Instrument",
        jurisdiction="UK",
        citation="TEST",
        kind="regulation",
        authoritative_text="Operators must store slurry safely.",
        authoritative_locator="regulation:1",
        current_snapshot_id="snap-1",
        metadata={},
    )


def test_try_extract_json_schema_rejects_bare_object() -> None:
    client = _StubLlm("{}")
    topic, cluster = _topic_cluster()
    rows, err, diag = _try_extract_model_v2_json(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=client,  # type: ignore[arg-type]
        model_alias="local_extract",
        extraction_mode="local",
        max_propositions=4,
        extraction_output_mode="json_schema",
    )
    assert rows is None
    assert err is not None
    assert diag is not None
    assert diag["failure_type"] == EXTRACTION_SCHEMA_VIOLATION
    assert client.last_json_schema is not None


def test_try_extract_json_schema_accepts_valid_propositions() -> None:
    sentence = "Operators must store slurry safely."
    client = _StubLlm(json.dumps(_valid_payload(sentence)))
    topic, cluster = _topic_cluster()
    rows, err, diag = _try_extract_model_v2_json(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=client,  # type: ignore[arg-type]
        model_alias="local_extract",
        extraction_mode="local",
        max_propositions=4,
        extraction_output_mode="json_schema",
    )
    assert err is None
    assert rows is not None
    assert len(rows) >= 1
    assert diag is not None
    assert diag.get("extraction_output_mode") == "json_schema"
    assert diag.get("schema_hash")
