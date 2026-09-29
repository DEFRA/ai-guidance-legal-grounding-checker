"""High-quality extraction mode behaviours (frontier alias, fallback policies, trace meta)."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from law_proposition_extractor_domain import Cluster, ReviewStatus, SourceRecord, Topic
from law_proposition_extractor_pipeline.extract import (
    EXTRACTION_SCHEMA_VERSION_V2,
    evidence_locates_verbatim_after_normalisation,
    extract_propositions_from_source,
    parse_extraction_meta,
    resolve_extraction_meta_for_proposition,
)


def _topic() -> Topic:
    return Topic(id="topic-em", name="EM", description="", subject_tags=[])


def _cluster() -> Cluster:
    return Cluster(id="cluster-em", topic_id="topic-em", name="EM cluster", description="")


def _source(*, text: str = "Operators must maintain records.") -> SourceRecord:
    return SourceRecord(
        id="src-em-1",
        title="Instrument",
        jurisdiction="UK",
        citation="C-EM",
        kind="regulation",
        authoritative_text=text,
        authoritative_locator="article:2",
        current_snapshot_id="snap-em-1",
        metadata={},
    )


def _mock_llm_client() -> MagicMock:
    client = MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000
    return client


def _v2_ok_payload(source_sentence: str) -> str:
    row = {
        "proposition_text": source_sentence,
        "display_label": "Label",
        "subject": "operators",
        "rule": "must maintain records",
        "object": "",
        "conditions": [],
        "exceptions": [],
        "temporal_condition": "",
        "provision_type": "core",
        "source_locator": "article:2",
        "evidence_text": source_sentence,
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "unit test",
    }
    return json.dumps({"propositions": [row]})


def test_frontier_mode_calls_frontier_extract_alias() -> None:
    models_seen: list[str] = []

    def capture_complete_text(*args: object, **kwargs: object) -> str:
        model = kwargs.get("model")
        if model is None and len(args) >= 2:
            model = args[1]
        models_seen.append(str(model))
        return _v2_ok_payload("Operators must maintain records.")

    client = _mock_llm_client()
    client.complete_text.side_effect = capture_complete_text

    out = extract_propositions_from_source(
        _source(),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="fallback",
        prompt_version="v2",
    )
    assert models_seen == ["frontier_extract"]
    assert len(out.propositions) == 1
    assert out.model_alias == "frontier_extract"


def test_on_before_llm_call_runs_immediately_before_model() -> None:
    order: list[str] = []
    client = _mock_llm_client()

    def complete_text(*_a: object, **_k: object) -> str:
        order.append("llm")
        return _v2_ok_payload("Operators must maintain records.")

    client.complete_text.side_effect = complete_text

    def hook(_trace: dict[str, Any]) -> None:
        order.append("before_llm")

    extract_propositions_from_source(
        _source(),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="fallback",
        prompt_version="v2",
        on_before_llm_call=hook,
    )
    assert order == ["before_llm", "llm"]


def test_fail_closed_no_heuristic_rows_and_failure_reason() -> None:
    client = _mock_llm_client()
    client.complete_text.side_effect = ValueError("invalid json from model")

    out = extract_propositions_from_source(
        _source(),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        prompt_version="v2",
    )
    assert out.propositions == []
    assert out.failed_closed is True
    assert out.failure_reason
    assert out.validation_errors


def test_mark_needs_review_keeps_heuristic_and_sets_review_status() -> None:
    client = _mock_llm_client()
    client.complete_text.return_value = '{"propositions":[]}'
    out = extract_propositions_from_source(
        _source(
            text=(
                "Section 2. Operators must maintain movement records before dispatch.\n"
                "Section 3. The competent authority may inspect records."
            )
        ),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="mark_needs_review",
        prompt_version="v2",
    )
    assert out.propositions
    assert all(p.review_status == ReviewStatus.NEEDS_REVIEW for p in out.propositions)
    assert out.fallback_used is True


def test_extraction_meta_records_mode_fallback_and_validation() -> None:
    client = _mock_llm_client()
    client.complete_text.return_value = '{"propositions":[]}'
    out = extract_propositions_from_source(
        _source(
            text=(
                "Art 1. Intro.\n"
                "Art 2. Operators shall maintain registers.\n"
            ),
        ),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fallback",
        prompt_version="v2",
    )
    prop = out.propositions[0]
    meta = resolve_extraction_meta_for_proposition(
        notes=prop.notes,
        extraction_debug_meta=prop.extraction_debug_meta,
    )
    assert meta is not None
    assert meta.get("extraction_mode") == "local"
    assert meta.get("fallback_policy") == "fallback"
    assert meta.get("fallback_used") is True
    assert meta.get("prompt_version") == "v2"
    assert meta.get("validation_errors")


def test_invalid_model_payload_handled_as_failure_under_fail_closed() -> None:
    client = _mock_llm_client()
    client.complete_text.return_value = "not-json"

    out = extract_propositions_from_source(
        _source(),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        prompt_version="v2",
    )
    assert out.propositions == []
    assert out.failed_closed


@pytest.mark.parametrize(
    ("mode", "expected_alias"),
    [
        ("local", "local_extract"),
        ("frontier", "frontier_extract"),
    ],
)
def test_model_alias_on_success_matches_mode(mode: str, expected_alias: str) -> None:
    client = _mock_llm_client()
    client.complete_text.return_value = _v2_ok_payload("Operators must maintain records.")

    out = extract_propositions_from_source(
        _source(),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode=mode,
        extraction_fallback="fallback",
        prompt_version="v2",
    )
    assert out.model_alias == expected_alias
    assert out.schema_version == EXTRACTION_SCHEMA_VERSION_V2


def test_definition_article_frontier_parse_failure_uses_definition_fallback() -> None:
    client = _mock_llm_client()
    client.complete_text.return_value = "{not-valid-json"
    article_2 = (
        "Article 2\n"
        "For the purposes of this Regulation, the following definitions shall apply:\n"
        "(a) 'equidae' or 'equine animals' means animals of domestic or wild species of the family Equidae;\n"
        "(b) 'holding' means an establishment where equidae are kept;\n"
        "(c) 'keeper' means a natural or legal person having permanent or temporary responsibility for equidae;\n"
        "(d) 'owner' means the natural or legal person with a property right over an equine animal;\n"
        "(e) 'transponder' means a read-only passive radio-frequency identification device."
    )
    out = extract_propositions_from_source(
        _source(text=article_2),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=8,
        extraction_mode="frontier",
        extraction_fallback="fallback",
        prompt_version="v2",
    )
    assert out.fallback_used is True
    assert out.fallback_strategy == "definition_extractor"
    assert len(out.propositions) > 1
    assert len({p.id for p in out.propositions}) == len(out.propositions)
    assert len({str(p.proposition_key) for p in out.propositions}) == len(out.propositions)
    assert not any(
        p.proposition_text.lower().startswith("article 2for the purposes") for p in out.propositions
    ), "fallback must not emit one full-article blob proposition"
    for p in out.propositions:
        assert p.label.startswith("Definition — ")
        assert p.article_reference == "Article 2"
        assert p.fragment_locator == "article:2"
        meta = resolve_extraction_meta_for_proposition(
            notes=p.notes,
            extraction_debug_meta=p.extraction_debug_meta,
        )
        assert meta is not None
        assert meta.get("provision_type") == "definition"
        eq = str(meta.get("evidence_quote") or "")
        assert eq
        ok, _strategy, _diag = evidence_locates_verbatim_after_normalisation(eq, article_2)
        assert ok
        assert str(meta.get("fallback_strategy") or "") == "definition_extractor"


def test_definition_fallback_mark_needs_review_keeps_high_confidence_rows_proposed() -> None:
    client = _mock_llm_client()
    client.complete_text.return_value = "{not-valid-json"
    article_2 = (
        "Article 2\n"
        "The following definitions shall apply:\n"
        "'keeper' means a natural or legal person having responsibility for equidae;\n"
        "'transponder' means a radio-frequency identification device."
    )
    out = extract_propositions_from_source(
        _source(text=article_2),
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        prompt_version="v2",
    )
    assert out.fallback_used is True
    assert out.fallback_strategy == "definition_extractor"
    assert len(out.propositions) == 2
    assert all(p.review_status == ReviewStatus.PROPOSED for p in out.propositions)
    for p in out.propositions:
        meta = resolve_extraction_meta_for_proposition(
            notes=p.notes,
            extraction_debug_meta=p.extraction_debug_meta,
        )
        assert meta is not None
        assert meta.get("model_confidence") == "high"
