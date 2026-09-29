"""Local/frontier LLM extraction metrics, traces, and fail_closed enforcement."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from law_proposition_extractor_domain import Cluster, SourceRecord, Topic
from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.extract import extract_propositions_from_source
from law_proposition_extractor_pipeline.extraction_llm_metrics import (
    ExtractionPlanFailure,
    compute_extraction_llm_trace_summary_metrics,
    merge_extraction_observability_metrics,
    validate_llm_extraction_job_plan,
)
from law_proposition_extractor_pipeline.linting import load_exported_bundle
from law_proposition_extractor_pipeline.runner import build_bundle_from_case
from law_proposition_extractor_pipeline.derived_cache import DerivedArtifactCache


@pytest.fixture(autouse=True)
def _noop_llm_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "law_proposition_extractor_pipeline.runner.preflight_llm_extraction",
        lambda _client, _mode: None,
    )


def _topic() -> Topic:
    return Topic(id="topic-slurry", name="slurry", description="", subject_tags=[])


def _cluster() -> Cluster:
    return Cluster(id="cluster-slurry", topic_id="topic-slurry", name="c", description="")


def _v2_payload(sentence: str) -> str:
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
                    "source_locator": "section:2",
                    "evidence_text": sentence,
                    "completeness_status": "complete",
                    "confidence": "high",
                    "reason": "test",
                }
            ]
        }
    )


class _FakeLocalLlmClient:
    def __init__(self) -> None:
        class _Settings:
            frontier_extract_model = "frontier_extract"
            local_extract_model = "local_extract"
            max_extract_input_tokens = 150_000
            extract_model_context_limit = 200_000
            skip_llm_preflight = True

        self.settings = _Settings()
        self.calls = 0

    def complete_text(self, *_args: object, **_kwargs: object) -> str:
        return self.complete_text_result(*_args, **_kwargs).content

    def complete_text_result(self, *_args: object, **_kwargs: object) -> TextCompletionResult:
        self.calls += 1
        sentence = "Operators must store slurry in covered stores."
        return TextCompletionResult(content=_v2_payload(sentence), finish_reason="stop")


def _inline_case(*, text: str) -> dict:
    return {
        "topic": {"name": "slurry", "description": "", "subject_tags": []},
        "cluster": {"name": "slurry", "description": ""},
        "sources": [
            {
                "id": "src-slurry-1",
                "title": "Slurry instrument",
                "jurisdiction": "UK",
                "citation": "TEST 1",
                "kind": "regulation",
                "text": text,
                "fragment_locator": "section:2",
            }
        ],
        "comparison": {"jurisdiction_a": "UK", "jurisdiction_b": "UK"},
    }


def test_local_extract_smoke_metrics_traces_and_propositions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeLocalLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)

    bundle = build_bundle_from_case(
        case_data=_inline_case(text="Section 2. Operators must store slurry in covered stores."),
        use_llm=True,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        divergence_reasoning="none",
        derived_cache_dir=str(tmp_path / "derived"),
    )

    traces = bundle["stage_traces"]
    pex_stage = next(t for t in traces if t.get("stage_name") == "proposition extraction")
    llm_traces = pex_stage["inputs"]["extraction_llm_call_traces"]
    metrics = compute_extraction_llm_trace_summary_metrics(llm_traces)

    assert fake.calls == 1
    assert metrics["attempted_llm_calls"] == 1
    assert metrics["successful_llm_calls"] == 1
    assert metrics["failed_llm_calls"] == 0
    assert len(bundle["propositions"]) > 0
    assert len(bundle["proposition_extraction_traces"]) > 0
    assert any(t.get("extraction_method") == "llm" for t in bundle["proposition_extraction_traces"])


def test_extract_propositions_attempted_before_invoke() -> None:
    order: list[str] = []
    client = _FakeLocalLlmClient()

    def complete_text_result(*_a: object, **_k: object) -> TextCompletionResult:
        order.append("llm")
        return TextCompletionResult(
            content=_v2_payload("Operators must store slurry in covered stores."),
            finish_reason="stop",
        )

    client.complete_text_result = complete_text_result  # type: ignore[method-assign]

    def hook(trace: dict) -> None:
        assert trace.get("llm_call_attempted") is True
        assert trace.get("llm_invoked") is not True
        order.append("before")

    source = SourceRecord(
        id="src-1",
        title="T",
        jurisdiction="UK",
        citation="C",
        kind="regulation",
        authoritative_text="Operators must store slurry in covered stores.",
        authoritative_locator="section:2",
        current_snapshot_id="snap-1",
        metadata={},
    )
    out = extract_propositions_from_source(
        source,
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        on_before_llm_call=hook,
    )
    assert order == ["before", "llm"]
    row = out.extraction_llm_call_traces[0]
    assert row.get("llm_call_attempted") is True
    assert row.get("llm_invoked") is True
    assert row.get("llm_call_succeeded") is True


def test_fail_closed_raises_when_selected_but_empty_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeLocalLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)

    with pytest.raises(RuntimeError, match="fail_closed local extraction produced 0 propositions"):
        build_bundle_from_case(
            case_data=_inline_case(text=""),
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            divergence_reasoning="none",
            derived_cache_dir=str(tmp_path / "derived-empty"),
        )
    assert fake.calls == 0


def test_all_fragments_skipped_fail_closed_with_skip_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Local mode selected but every fragment fails focus selection — clear failure + skip traces."""
    fake = _FakeLocalLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)

    case = _inline_case(
        text="Article 10. Movement logs and administrative formatting without matching focus terms."
    )
    case["extraction"] = {
        "focus_terms": ["slurry", "manure lagoon"],
        "fragment_selection_mode": "all_matching",
    }

    with pytest.raises(ExtractionPlanFailure, match="no_selected_fragments"):
        build_bundle_from_case(
            case_data=case,
            use_llm=True,
            extraction_mode="local",
            extraction_fallback="fail_closed",
            divergence_reasoning="none",
            derived_cache_dir=str(tmp_path / "derived-skip"),
        )

    assert fake.calls == 0


def test_load_exported_bundle_rejects_case_json_file(tmp_path: Path) -> None:
    case_path = tmp_path / "case.json"
    case_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not a valid --export-dir"):
        load_exported_bundle(case_path)


def test_no_focus_terms_local_runs_llm_over_authoritative_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Slurry-shaped case: authoritative text, no focus_terms — must not silently skip LLM."""
    fake = _FakeLocalLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)

    case = _inline_case(text="Section 2. Operators must store slurry in covered stores.")
    case["extraction"] = {"focus_terms": [], "fragment_selection_mode": "all_matching"}

    bundle = build_bundle_from_case(
        case_data=case,
        use_llm=True,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        divergence_reasoning="none",
        derived_cache_dir=str(tmp_path / "derived-no-focus"),
    )

    jobs = bundle.get("proposition_extraction_jobs") or []
    assert jobs
    assert any(row.get("selected_for_extraction") for row in jobs)
    metrics = merge_extraction_observability_metrics(
        jobs=jobs,
        llm_traces=bundle.get("extraction_llm_call_traces") or [],
    )
    assert fake.calls >= 1
    assert metrics["attempted_llm_calls"] >= 1
    assert len(bundle["propositions"]) > 0


def test_empty_aggregate_cache_is_ignored_and_llm_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeLocalLlmClient()
    monkeypatch.setattr("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: fake)
    case = _inline_case(text="Section 2. Operators must store slurry in covered stores.")

    class _CachedEmpty:
        payload = {"propositions": [], "proposition_extraction_failures": []}
        storage_uri = "mem://empty"
        cached_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

    def _get_empty(self: DerivedArtifactCache, *, stage_name: str, cache_key: str) -> object | None:
        if stage_name == "proposition_extraction":
            return _CachedEmpty()
        return None

    monkeypatch.setattr(DerivedArtifactCache, "get", _get_empty)

    bundle = build_bundle_from_case(
        case_data=case,
        use_llm=True,
        extraction_mode="local",
        extraction_fallback="fail_closed",
        divergence_reasoning="none",
        derived_cache_dir=str(tmp_path / "derived-empty-cache"),
    )
    assert fake.calls >= 1
    assert len(bundle["propositions"]) > 0
    pex = [t for t in bundle["stage_traces"] if t["stage_name"] == "proposition extraction"][0]
    assert pex["inputs"]["derived_artifact_cache"]["cache_status"] == "cache_miss_persisted"


def test_required_plus_focus_without_terms_raises_plan_failure() -> None:
    with pytest.raises(ExtractionPlanFailure, match="no_focus_terms"):
        validate_llm_extraction_job_plan(
            extraction_mode="local",
            extraction_fallback="fail_closed",
            extraction_jobs_created=10,
            extraction_jobs_selected=0,
            source_fragments_total=10,
            sources_count=1,
            focus_terms=[],
            required_locators=set(),
            fragment_selection_mode="required_plus_focus",
            has_authoritative_text=True,
        )


def test_empty_text_fail_closed_emits_skip_trace() -> None:
    client = _FakeLocalLlmClient()
    source = SourceRecord(
        id="src-empty",
        title="T",
        jurisdiction="UK",
        citation="C",
        kind="regulation",
        authoritative_text="   ",
        authoritative_locator="section:1",
        current_snapshot_id="snap-1",
        metadata={},
    )
    out = extract_propositions_from_source(
        source,
        _topic(),
        _cluster(),
        llm_client=client,
        limit=4,
        extraction_mode="local",
        extraction_fallback="fail_closed",
    )
    assert out.failed_closed
    assert len(out.extraction_llm_call_traces) == 1
    assert out.extraction_llm_call_traces[0]["skip_reason"] == "empty_source_text"
    metrics = compute_extraction_llm_trace_summary_metrics(out.extraction_llm_call_traces)
    assert metrics["attempted_llm_calls"] == 0
    assert metrics["llm_extraction_skipped_count"] == 1
