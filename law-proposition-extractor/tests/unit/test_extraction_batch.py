import json
from dataclasses import replace
from unittest.mock import MagicMock

from law_proposition_extractor_domain import Cluster, ReviewStatus, SourceRecord, Topic
from law_proposition_extractor_pipeline.derived_cache import (
    DerivedArtifactCache,
    build_proposition_extraction_chunk_cache_key,
)
from law_proposition_extractor_pipeline.extract import plan_frontier_extraction_requests
from law_proposition_extractor_pipeline.extraction_batch import (
    FrontierBatchWorkItem,
    import_frontier_batch_results,
    import_frontier_batch_results_by_job,
)


def _topic() -> Topic:
    return Topic(id="topic-b", name="Batch", description="", subject_tags=[])


def _cluster() -> Cluster:
    return Cluster(id="cluster-b", topic_id="topic-b", name="Batch cluster", description="")


def _source() -> SourceRecord:
    return SourceRecord(
        id="src-b-1",
        title="Batch Source",
        jurisdiction="UK",
        citation="B-1",
        kind="regulation",
        authoritative_text="Article 1 Operators must keep movement records.",
        authoritative_locator="article:1",
        current_snapshot_id="snap-b-1",
        metadata={"extraction_fragment_id": "frag-b-1"},
    )


def test_planning_frontier_requests_produces_prompt_without_llm_calls() -> None:
    from law_proposition_extractor_pipeline.extract import MAX_ANTHROPIC_BATCH_CUSTOM_ID_LENGTH

    llm_client = MagicMock()
    reqs = plan_frontier_extraction_requests(
        source=_source(),
        topic=_topic(),
        cluster=_cluster(),
        model_alias="frontier_extract",
        max_propositions=4,
        max_input_tokens=150_000,
    )
    assert reqs
    assert all(req.prompt_text for req in reqs)
    assert all(req.request_id for req in reqs)
    assert all(len(req.request_id) <= MAX_ANTHROPIC_BATCH_CUSTOM_ID_LENGTH for req in reqs)
    llm_client.complete_text.assert_not_called()


def test_cached_successful_chunks_not_submitted_again(tmp_path) -> None:
    cache = DerivedArtifactCache(cache_dir=tmp_path / "derived")
    source = _source()
    reqs = plan_frontier_extraction_requests(
        source=source,
        topic=_topic(),
        cluster=_cluster(),
        model_alias="frontier_extract",
        max_propositions=4,
        derived_chunk_cache=cache,
        include_cached_successes=True,
    )
    assert reqs
    first = reqs[0]
    assert first.cache_key
    cache.put(
        stage_name="proposition_extraction_chunk",
        cache_key=str(first.cache_key),
        payload={
            "chunk_status": "llm_success",
            "validated_rows": [{"proposition_text": "x", "source_locator": "article:1"}],
        },
    )
    reqs_after = plan_frontier_extraction_requests(
        source=source,
        topic=_topic(),
        cluster=_cluster(),
        model_alias="frontier_extract",
        max_propositions=4,
        derived_chunk_cache=cache,
        include_cached_successes=False,
    )
    assert all(r.request_id != first.request_id for r in reqs_after)


def test_import_batch_result_validates_evidence_and_marks_failures_repairable() -> None:
    source = _source()
    reqs = plan_frontier_extraction_requests(
        source=source,
        topic=_topic(),
        cluster=_cluster(),
        model_alias="frontier_extract",
        max_propositions=4,
    )
    req = reqs[0]
    paraphrased_payload = json.dumps(
        {
            "propositions": [
                {
                    "proposition_text": "Operators must keep movement records",
                    "display_label": "Records",
                    "subject": "operators",
                    "rule": "must keep movement records",
                    "object": "",
                    "conditions": [],
                    "exceptions": [],
                    "temporal_condition": "",
                    "provision_type": "core",
                    "source_locator": "article:1",
                    "evidence_text": "Operators should keep records",  # paraphrase, not verbatim
                    "completeness_status": "complete",
                    "confidence": "high",
                    "reason": "test",
                }
            ]
        }
    )
    out = import_frontier_batch_results(
        requests=[req],
        provider_results={req.request_id: paraphrased_payload},
        source_by_request_id={req.request_id: source},
        topic=_topic(),
        cluster=_cluster(),
        extraction_fallback="mark_needs_review",
    )
    assert out.propositions == []
    assert out.failed_result_count == 1
    assert any("evidence_text not traceable" in err for err in out.validation_errors)


def test_import_batch_result_success_creates_propositions_and_traces() -> None:
    source = _source()
    req = plan_frontier_extraction_requests(
        source=source,
        topic=_topic(),
        cluster=_cluster(),
        model_alias="frontier_extract",
        max_propositions=4,
    )[0]
    payload = json.dumps(
        {
            "propositions": [
                {
                    "proposition_text": "Operators must keep movement records.",
                    "display_label": "Records",
                    "subject": "operators",
                    "rule": "must keep movement records",
                    "object": "",
                    "conditions": [],
                    "exceptions": [],
                    "temporal_condition": "",
                    "provision_type": "core",
                    "source_locator": "article:1",
                    "evidence_text": "Operators must keep movement records.",
                    "completeness_status": "complete",
                    "confidence": "high",
                    "reason": "test",
                }
            ]
        }
    )
    out = import_frontier_batch_results(
        requests=[req],
        provider_results={req.request_id: payload},
        source_by_request_id={req.request_id: source},
        topic=_topic(),
        cluster=_cluster(),
        extraction_fallback="mark_needs_review",
    )
    assert len(out.propositions) == 1
    assert out.failed_result_count == 0
    assert out.extraction_llm_call_traces[0]["batch_request_id"] == req.request_id
    # Propositions must carry the source fragment linkage (extraction_fragment_id), not None.
    assert out.propositions[0].source_fragment_id == "frag-b-1"


def _tagged_job_requests(source: SourceRecord, job_key: str) -> list:
    reqs = plan_frontier_extraction_requests(
        source=source,
        topic=_topic(),
        cluster=_cluster(),
        model_alias="frontier_extract",
        max_propositions=4,
    )
    return [replace(r, metadata={**r.metadata, "job_key": job_key}) for r in reqs]


def test_batch_empty_success_emits_no_propositions_without_fallback() -> None:
    """A valid model response with zero items (repealed/omitted fragment) yields no props."""
    source = _source()
    job_key = "job-empty"
    tagged = _tagged_job_requests(source, job_key)
    out = import_frontier_batch_results_by_job(
        requests=tagged,
        provider_results={r.request_id: json.dumps({"propositions": []}) for r in tagged},
        source_by_request_id={r.request_id: source for r in tagged},
        work_items_by_key={job_key: FrontierBatchWorkItem(job_key=job_key, work_source=source)},
        topic=_topic(),
        cluster=_cluster(),
        extraction_fallback="mark_needs_review",
    )
    res = out[job_key]
    assert res.propositions == []
    assert res.fallback_used is False


def test_batch_hard_failure_falls_back_to_heuristic() -> None:
    """A missing provider result is a genuine failure and still triggers heuristic fallback."""
    source = _source()
    job_key = "job-failed"
    tagged = _tagged_job_requests(source, job_key)
    out = import_frontier_batch_results_by_job(
        requests=tagged,
        provider_results={},  # no results -> hard failure
        source_by_request_id={r.request_id: source for r in tagged},
        work_items_by_key={job_key: FrontierBatchWorkItem(job_key=job_key, work_source=source)},
        topic=_topic(),
        cluster=_cluster(),
        extraction_fallback="mark_needs_review",
    )
    res = out[job_key]
    assert res.fallback_used is True
    assert res.fallback_strategy == "heuristic_fallback"
    assert res.propositions
    assert all(p.review_status == ReviewStatus.NEEDS_REVIEW for p in res.propositions)


def test_parse_batch_results_jsonl_multiline() -> None:
    from law_proposition_extractor_pipeline.extraction_batch import parse_batch_results_jsonl

    raw = (
        '{"custom_id":"pex-abc","result":{"type":"succeeded","message":{"content":[{"type":"text","text":"{}"}]}}}\n'
        '{"custom_id":"pex-def","result":{"type":"errored","error":{"type":"invalid_request_error"}}}\n'
    )
    rows = parse_batch_results_jsonl(raw)
    assert len(rows) == 2
    assert rows[0]["custom_id"] == "pex-abc"
    assert rows[1]["custom_id"] == "pex-def"


def test_resolve_anthropic_batch_model_id() -> None:
    from law_proposition_extractor_pipeline.extraction_batch import resolve_anthropic_batch_model_id

    assert resolve_anthropic_batch_model_id("frontier_extract") == "claude-sonnet-4-5-20250929"
    assert resolve_anthropic_batch_model_id("claude-sonnet-4-test") == "claude-sonnet-4-test"
    assert resolve_anthropic_batch_model_id("anthropic/claude-3-5-sonnet") == "claude-3-5-sonnet"


def test_fragment_cache_key_includes_fragment_identity() -> None:
    k_article_1 = build_proposition_extraction_chunk_cache_key(
        authority="legislation_gov_uk",
        authority_source_id="uksi/2015/668",
        source_fragment_locator="article:1",
        chunk_index=1,
        chunk_body_fingerprint="body-a",
        model_alias="frontier_extract",
        extraction_mode="frontier",
        prompt_version="v2",
        focus_scopes=(),
        max_propositions=4,
        pipeline_version="0.1.0",
        strategy_version="v1",
    )
    k_article_2 = build_proposition_extraction_chunk_cache_key(
        authority="legislation_gov_uk",
        authority_source_id="uksi/2015/668",
        source_fragment_locator="article:2",
        chunk_index=1,
        chunk_body_fingerprint="body-b",
        model_alias="frontier_extract",
        extraction_mode="frontier",
        prompt_version="v2",
        focus_scopes=(),
        max_propositions=4,
        pipeline_version="0.1.0",
        strategy_version="v1",
    )
    k_annex = build_proposition_extraction_chunk_cache_key(
        authority="legislation_gov_uk",
        authority_source_id="uksi/2015/668",
        source_fragment_locator="annex:i",
        chunk_index=1,
        chunk_body_fingerprint="body-c",
        model_alias="frontier_extract",
        extraction_mode="frontier",
        prompt_version="v2",
        focus_scopes=(),
        max_propositions=4,
        pipeline_version="0.1.0",
        strategy_version="v1",
    )
    assert k_article_1 != k_article_2
    assert k_article_1 != k_annex
    assert k_article_2 != k_annex


def test_chunk_cache_key_stable_across_snapshot_identity_remints() -> None:
    """Law Discovery lex-* / snapshot remints must not change chunk keys when ASID + body match."""
    common = dict(
        authority="legislation_gov_uk",
        authority_source_id="uksi/2015/668",
        source_fragment_locator="article:1",
        chunk_index=1,
        chunk_body_fingerprint="body-fp-shared",
        model_alias="frontier_extract",
        extraction_mode="frontier",
        prompt_version="v2",
        focus_scopes=(),
        max_propositions=4,
        pipeline_version="0.1.0",
        strategy_version="v1",
    )
    assert build_proposition_extraction_chunk_cache_key(**common) == (
        build_proposition_extraction_chunk_cache_key(**common)
    )
    other_asid = build_proposition_extraction_chunk_cache_key(
        **{**common, "authority_source_id": "uksi/2009/1741"}
    )
    assert other_asid != build_proposition_extraction_chunk_cache_key(**common)
