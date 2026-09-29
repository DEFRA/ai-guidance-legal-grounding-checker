"""Failed/successful proposition extraction chunk derived-cache behaviour."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from law_proposition_extractor_domain import Cluster, SourceRecord, Topic

from law_proposition_extractor_pipeline.derived_cache import DerivedArtifactCache, clear_proposition_extraction_derived_cache
from law_proposition_extractor_pipeline.extract import extract_propositions_from_source
from law_proposition_extractor_pipeline.runner import _enforce_fail_closed_llm_extraction


def _topic_cluster() -> tuple[Topic, Cluster]:
    topic = Topic(id="t1", name="T", description="", subject_tags=[])
    cluster = Cluster(id="c1", topic_id="t1", name="C", description="")
    return topic, cluster


def _source() -> SourceRecord:
    return SourceRecord(
        id="src-cache-policy",
        title="T",
        jurisdiction="UK",
        citation="C",
        kind="regulation",
        authoritative_text="Operators must keep records of animal movements.",
        authoritative_locator="article:1",
        current_snapshot_id="snap-cc",
        metadata={},
    )


def _mock_client() -> Any:
    client = __import__("unittest.mock").mock.MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000
    return client


def test_cached_successful_extraction_reused_without_second_llm_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int] = []

    def fake_try_ok(**kwargs: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
        calls.append(1)
        sent = str(kwargs.get("prompt_source_text") or "")
        row = {
            "proposition_text": sent[:80],
            "display_label": "L",
            "subject": "s",
            "rule": "r",
            "object": "",
            "conditions": [],
            "exceptions": [],
            "temporal_condition": "",
            "provision_type": "core",
            "source_locator": "article:1",
            "evidence_text": sent[:80],
            "completeness_status": "complete",
            "confidence": "high",
            "reason": "test",
        }
        return [row], None

    monkeypatch.setattr("law_proposition_extractor_pipeline.extract._try_extract_model_v2_json", fake_try_ok)
    topic, cluster = _topic_cluster()
    cache = DerivedArtifactCache(cache_dir=tmp_path / "derived-chunk")
    kwargs = dict(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=_mock_client(),
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="fail_closed",
        derived_chunk_cache=cache,
        retry_failed_llm=False,
    )
    extract_propositions_from_source(**kwargs)
    assert len(calls) == 1
    extract_propositions_from_source(**kwargs)
    assert len(calls) == 1


def test_cached_failed_extraction_retried_by_default_for_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int] = []

    def fake_fail(**kwargs: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
        calls.append(1)
        return None, "model error"

    monkeypatch.setattr("law_proposition_extractor_pipeline.extract._try_extract_model_v2_json", fake_fail)
    topic, cluster = _topic_cluster()
    cache = DerivedArtifactCache(cache_dir=tmp_path / "derived-fail")
    base = dict(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=_mock_client(),
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        derived_chunk_cache=cache,
    )
    extract_propositions_from_source(**base, retry_failed_llm=False)
    assert len(calls) == 1
    out = extract_propositions_from_source(**base, retry_failed_llm=True)
    assert len(calls) == 2
    assert not any(
        t.get("llm_cache_hit") == "failed_chunk_cached" for t in out.extraction_llm_call_traces
    )


def test_ignore_failed_cache_skips_llm_on_second_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int] = []

    def fake_fail(**kwargs: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
        calls.append(1)
        return None, "model error"

    monkeypatch.setattr("law_proposition_extractor_pipeline.extract._try_extract_model_v2_json", fake_fail)
    topic, cluster = _topic_cluster()
    cache = DerivedArtifactCache(cache_dir=tmp_path / "derived-ignore")
    base = dict(
        source=_source(),
        topic=topic,
        cluster=cluster,
        llm_client=_mock_client(),
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        derived_chunk_cache=cache,
        retry_failed_llm=False,
    )
    extract_propositions_from_source(**base)
    out = extract_propositions_from_source(**base)
    assert len(calls) == 1
    assert any(
        t.get("skip_reason") == "failed_chunk_cached" for t in out.extraction_llm_call_traces
    )


def test_enforce_fail_closed_zero_attempts_hints_ignore_and_cache_clear() -> None:
    traces = [
        {
            "skipped_llm": True,
            "skip_reason": "failed_chunk_cached",
            "llm_call_attempted": False,
        }
    ]
    jobs = [{"selected_for_extraction": True}]
    with pytest.raises(RuntimeError) as exc:
        _enforce_fail_closed_llm_extraction(
            extraction_mode="local",
            extraction_fallback="fail_closed",
            proposition_extraction_jobs=jobs,
            accumulated_propositions=[],
            extraction_llm_diagnostic_traces=traces,
            derived_cache_dir="/var/law-proposition-extractor/derived",
            retry_failed_extraction_cache=False,
        )
    msg = str(exc.value)
    assert "failed_chunk_cached=1" in msg
    assert "--ignore-failed-extraction-cache" in msg
    assert "proposition_extraction_chunk" in msg


def test_clear_proposition_extraction_derived_cache_removes_stage_trees(tmp_path: Path) -> None:
    cache = DerivedArtifactCache(cache_dir=tmp_path / "derived")
    cache.put(
        stage_name="proposition_extraction_chunk",
        cache_key="abc",
        payload={"chunk_status": "failure"},
    )
    cache.put(
        stage_name="proposition_extraction",
        cache_key="def",
        payload={"propositions": []},
    )
    cache.put(
        stage_name="proposition_extraction_content_hash",
        cache_key="ch",
        payload={"propositions": [{"id": "p1"}]},
    )
    cache.put(stage_name="narrative", cache_key="ghi", payload={"text": "x"})
    removed = clear_proposition_extraction_derived_cache(cache.cache_dir)
    assert removed
    assert not (cache.cache_dir / "proposition_extraction_chunk").exists()
    assert not (cache.cache_dir / "proposition_extraction").exists()
    assert not (cache.cache_dir / "proposition_extraction_content_hash").exists()
    assert (cache.cache_dir / "narrative" / "ghi.json").exists()
