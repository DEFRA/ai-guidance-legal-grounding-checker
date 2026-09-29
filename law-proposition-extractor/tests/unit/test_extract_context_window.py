"""Context-window budgeting, chunking, and frontier_extract safety."""

import json
from typing import Any
from unittest.mock import MagicMock

from law_proposition_extractor_domain import Cluster, ReviewStatus, SourceRecord, Topic
from law_proposition_extractor_domain.proposition_notes import resolve_extraction_meta_for_proposition
from law_proposition_extractor_pipeline.extract import extract_propositions_from_source
from law_proposition_extractor_pipeline.runner import _build_proposition_extraction_traces


def _topic() -> Topic:
    return Topic(id="topic-cw", name="CW", description="", subject_tags=[])


def _cluster() -> Cluster:
    return Cluster(id="cluster-cw", topic_id="topic-cw", name="CW", description="")


def _client(*, max_in: int = 150_000, ctx: int = 200_000) -> MagicMock:
    c = MagicMock()
    c.settings.frontier_extract_model = "frontier_extract"
    c.settings.local_extract_model = "local_extract"
    c.settings.max_extract_input_tokens = max_in
    c.settings.extract_model_context_limit = ctx
    return c


def _row(proposition: str, evidence: str, locator: str = "article:1") -> dict[str, Any]:
    return {
        "proposition_text": proposition,
        "display_label": "L",
        "subject": "s",
        "rule": "r",
        "object": "",
        "conditions": [],
        "exceptions": [],
        "temporal_condition": "",
        "provision_type": "core",
        "source_locator": locator,
        "evidence_text": evidence,
        "completeness_status": "complete",
        "confidence": "high",
        "reason": "test",
    }


def _payload(row: dict[str, Any]) -> str:
    return json.dumps({"propositions": [row]})


def _long_preamble_two_articles(
    *, art1_body: str = "Operators must keep registers.", art2_body: str = "The authority may inspect premises."
) -> str:
    preamble = "\n".join([f"Preamble line {i}." for i in range(400)])
    return f"{preamble}\n\nArticle 1\n{art1_body}\n\nArticle 2\n{art2_body}\n"


def test_extreme_token_limit_skips_llm_fail_closed() -> None:
    client = _client(max_in=1)
    src = SourceRecord(
        id="src-cw-1",
        title="Big",
        jurisdiction="EU",
        citation="X",
        kind="regulation",
        authoritative_text="Some normative text that must not reach the model.\n" * 50,
        authoritative_locator="document:full",
        current_snapshot_id="snap-1",
        metadata={},
    )
    out = extract_propositions_from_source(
        src,
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="fail_closed",
    )
    client.complete_text.assert_not_called()
    assert out.failed_closed
    assert out.propositions == []
    assert out.extraction_llm_call_traces
    assert any("context_window_risk" in str(x) for x in out.validation_errors)
    assert any(
        t.get("skip_reason") == "context_window_risk" for t in out.extraction_llm_call_traces
    )


def test_extreme_token_limit_mark_needs_review_heuristic() -> None:
    client = _client(max_in=1)
    src = SourceRecord(
        id="src-cw-2",
        title="Big",
        jurisdiction="EU",
        citation="X",
        kind="regulation",
        authoritative_text="Section 2. Operators shall maintain movement registers.\n",
        authoritative_locator="section:2",
        current_snapshot_id="snap-1",
        metadata={},
    )
    out = extract_propositions_from_source(
        src,
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
    )
    client.complete_text.assert_not_called()
    assert out.fallback_used
    assert out.propositions
    assert all(p.review_status == ReviewStatus.NEEDS_REVIEW for p in out.propositions)
    meta = resolve_extraction_meta_for_proposition(
        notes=out.propositions[0].notes,
        extraction_debug_meta=out.propositions[0].extraction_debug_meta,
    )
    assert meta is not None
    assert meta.get("context_window_risk") is True
    pex = _build_proposition_extraction_traces(
        propositions=out.propositions,
        use_llm=True,
        extraction_prompt={"name": "extract.propositions.default", "version": "v2"},
        extraction_strategy_version="v1",
        extraction_hook={"cache_status": "none"},
        pipeline_version="test",
    )
    assert pex and pex[0].signals.get("context_window_risk") is True


def test_article_chunks_invoke_llm_once_per_article() -> None:
    client = _client(max_in=1500)
    n = 0

    def complete_text(*_a: object, **_kwargs: object) -> str:
        nonlocal n
        n += 1
        if n == 1:
            return _payload(
                _row(
                    "Operators must keep registers.",
                    "Operators must keep registers.",
                    "article:1|Article_1",
                )
            )
        return _payload(
            _row(
                "The authority may inspect premises.",
                "The authority may inspect premises.",
                "article:2|Article_2",
            )
        )

    client.complete_text.side_effect = complete_text
    src = SourceRecord(
        id="src-cw-art",
        title="Reg",
        jurisdiction="EU",
        citation="R",
        kind="regulation",
        authoritative_text=_long_preamble_two_articles(),
        authoritative_locator="reg:1",
        current_snapshot_id="snap-a",
        metadata={},
    )
    out = extract_propositions_from_source(
        src,
        _topic(),
        _cluster(),
        llm_client=client,
        limit=8,
        extraction_mode="frontier",
        extraction_fallback="fallback",
    )
    assert client.complete_text.call_count == 2
    assert len(out.propositions) == 2
    locs = {p.fragment_locator or "" for p in out.propositions}
    assert any("Article_1" in x for x in locs)
    assert any("Article_2" in x for x in locs)
    meta = resolve_extraction_meta_for_proposition(
        notes=out.propositions[0].notes,
        extraction_debug_meta=out.propositions[0].extraction_debug_meta,
    )
    assert meta is not None
    assert meta.get("estimated_input_tokens_max", 0) > 0


def test_merged_propositions_trace_tokens_and_signals() -> None:
    client = _client(max_in=1500)
    n = 0

    def complete_text(*_a: object, **_kwargs: object) -> str:
        nonlocal n
        n += 1
        if n == 1:
            return _payload(_row("Duty A.", "Duty A.", "article:1|Article_1"))
        return _payload(_row("Duty B.", "Duty B.", "article:2|Article_2"))

    client.complete_text.side_effect = complete_text
    src = SourceRecord(
        id="src-cw-tr",
        title="Reg",
        jurisdiction="EU",
        citation="R",
        kind="regulation",
        authoritative_text=_long_preamble_two_articles(art1_body="Duty A.", art2_body="Duty B."),
        authoritative_locator="reg:9",
        current_snapshot_id="snap-b",
        metadata={},
    )
    out = extract_propositions_from_source(
        src,
        _topic(),
        _cluster(),
        llm_client=client,
        limit=8,
        extraction_mode="frontier",
        extraction_fallback="fallback",
    )
    traces = _build_proposition_extraction_traces(
        propositions=out.propositions,
        use_llm=True,
        extraction_prompt={"name": "extract.propositions.default", "version": "v2"},
        extraction_strategy_version="v1",
        extraction_hook={"cache_status": "cache_miss_persisted"},
        pipeline_version="test",
    )
    assert len(traces) == 2
    for t in traces:
        assert t.signals.get("estimated_input_tokens_max", 0) > 0


def test_duplicate_cross_chunk_deduped() -> None:
    client = _client(max_in=1500)

    def complete_text(*_a: object, **_kwargs: object) -> str:
        row = _row("Same duty.", "Same duty.", "article:shared")
        return _payload(row)

    client.complete_text.side_effect = complete_text
    src = SourceRecord(
        id="src-dedupe",
        title="Reg",
        jurisdiction="EU",
        citation="R",
        kind="regulation",
        authoritative_text=_long_preamble_two_articles(art1_body="Same duty.", art2_body="Same duty."),
        authoritative_locator="reg:1",
        current_snapshot_id="snap-d",
        metadata={},
    )
    out = extract_propositions_from_source(
        src,
        _topic(),
        _cluster(),
        llm_client=client,
        limit=8,
        extraction_mode="frontier",
        extraction_fallback="fallback",
    )
    assert client.complete_text.call_count == 2
    assert len(out.propositions) == 1
