"""Provider/billing extraction failure classification and fail-fast abort policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from law_proposition_extractor_pipeline.export_acceptance import (
    compute_acceptance_status,
    detect_repairable_issues,
)
from law_proposition_extractor_pipeline.extraction_provider_failure import (
    BENCHMARK_VERDICT_INCOMPLETE,
    ProviderFailureAbortPolicy,
    ProviderFailureAbortTracker,
    assess_extraction_benchmark_completeness,
    classify_provider_extraction_failure,
    is_export_blocked_for_incomplete_extraction,
)
from law_proposition_extractor_pipeline.fresh_extraction_verification import FreshExtractionVerificationReport
from law_proposition_extractor_pipeline.proposition_quality_gates import PropositionQualityReport
from law_proposition_extractor_pipeline.runner import export_run_file

ANTHROPIC_CREDIT_MSG = (
    "model call or JSON parse failed: Error code: 400 - "
    "'litellm.BadRequestError: AnthropicException - "
    '{"message":"Your credit balance is too low to access the Anthropic API."}'
)


def test_anthropic_credit_error_classified_as_billing() -> None:
    assert (
        classify_provider_extraction_failure(ANTHROPIC_CREDIT_MSG)
        == "provider_billing_or_quota"
    )


def test_abort_after_first_billing_error() -> None:
    policy = ProviderFailureAbortPolicy(enabled=True, consecutive_transient_threshold=5)
    tracker = ProviderFailureAbortTracker(policy=policy)
    aborted = tracker.record_provider_failure(
        category="provider_billing_or_quota",
        message=ANTHROPIC_CREDIT_MSG,
        source_record_id="src-1",
        source_fragment_id="frag-1",
        extraction_job_id="job-1",
    )
    assert aborted is True
    assert tracker.abort_metadata is not None
    assert tracker.abort_metadata["failure_reason"] == "provider_billing_or_quota"
    assert tracker.abort_metadata["run_status"] == "failed"


def test_transient_failures_respect_consecutive_threshold() -> None:
    policy = ProviderFailureAbortPolicy(enabled=True, consecutive_transient_threshold=3)
    tracker = ProviderFailureAbortTracker(policy=policy)
    for i in range(2):
        assert not tracker.record_provider_failure(
            category="provider_rate_limit",
            message=f"rate limit {i}",
            source_record_id="src-1",
            source_fragment_id=None,
            extraction_job_id=f"job-{i}",
        )
    assert tracker.record_provider_failure(
        category="provider_rate_limit",
        message="rate limit 3",
        source_record_id="src-1",
        source_fragment_id=None,
        extraction_job_id="job-3",
    )
    assert tracker.abort_metadata is not None
    assert tracker.abort_metadata["abort_reason"] == "consecutive_transient_provider_failures"


def test_export_guard_refuses_incomplete_run(tmp_path: Path) -> None:
    bundle: dict[str, Any] = {
        "run": {"id": "run-001"},
        "source_records": [{"id": "src-a"}, {"id": "src-b"}],
        "propositions": [{"id": "p1", "source_record_id": "src-a"}],
        "proposition_extraction_jobs": [
            {
                "id": f"job-{i}",
                "selected_for_extraction": True,
                "llm_invoked": True,
                "proposition_count": 0,
                "errors": [ANTHROPIC_CREDIT_MSG],
                "started_at": "2026-01-01T00:00:00Z",
            }
            for i in range(25)
        ],
        "extraction_llm_call_traces": [
            {
                "llm_call_succeeded": False,
                "model_error": ANTHROPIC_CREDIT_MSG,
            }
            for _ in range(10)
        ],
    }
    run_dir = tmp_path / "run-incomplete"
    run_dir.mkdir()
    (run_dir / "run_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError, match="Refusing to export"):
        export_run_file(str(run_dir), str(tmp_path / "out"), allow_incomplete_export=False)

    blocked, _ = is_export_blocked_for_incomplete_extraction(bundle)
    assert blocked is True


def test_acceptance_flags_incomplete_extraction() -> None:
    bundle: dict[str, Any] = {
        "run": {"id": "run-001"},
        "source_records": [{"id": "src-a"}, {"id": "src-b"}],
        "propositions": [],
        "proposition_extraction_jobs": [
            {
                "id": f"job-{i}",
                "selected_for_extraction": True,
                "llm_invoked": True,
                "proposition_count": 0,
                "errors": [ANTHROPIC_CREDIT_MSG],
                "started_at": "2026-01-01T00:00:00Z",
            }
            for i in range(25)
        ],
        "extraction_llm_call_traces": [
            {"llm_call_succeeded": False, "model_error": ANTHROPIC_CREDIT_MSG} for _ in range(5)
        ],
    }
    issues = detect_repairable_issues(bundle=bundle)
    incomplete = [i for i in issues if i.check_id == "incomplete_extraction"]
    assert incomplete
    verification = FreshExtractionVerificationReport(
        export_dir=".",
        generated_at="2026-01-01T00:00:00Z",
        proposition_count=0,
        error_count=0,
        warning_count=0,
        hard_failure=False,
        export_presence={},
        counts={},
        prompt_lab_anchors=[],
    )
    quality = PropositionQualityReport(
        proposition_count=0,
        error_count=0,
        warning_count=0,
        newly_normalised=False,
    )
    status, hard, _human, _warnings = compute_acceptance_status(
        proposition_count=0,
        verification=verification,
        quality=quality,
        issues_after=issues,
        anchor_summary={"all_dense_anchors_covered": True},
    )
    assert status == "failed"
    assert BENCHMARK_VERDICT_INCOMPLETE in hard


def test_infer_old_partial_run_incomplete() -> None:
    """Simulate slurry-like partial run: many billing failures and empty sources."""
    sources = [{"id": f"src-{i}"} for i in range(5)]
    props = [{"id": f"p-{i}", "source_record_id": "src-0"} for i in range(3)]
    props += [{"id": f"p-{i}", "source_record_id": "src-1"} for i in range(3, 6)]
    jobs = []
    traces = []
    for i in range(100):
        jobs.append(
            {
                "id": f"job-{i:04d}",
                "selected_for_extraction": True,
                "llm_invoked": True,
                "proposition_count": 0 if i >= 20 else 1,
                "errors": [ANTHROPIC_CREDIT_MSG] if i >= 20 else [],
                "started_at": "2026-01-01T00:00:00Z",
            }
        )
        if i >= 20:
            traces.append({"llm_call_succeeded": False, "model_error": ANTHROPIC_CREDIT_MSG})
    bundle = {
        "source_records": sources,
        "propositions": props,
        "proposition_extraction_jobs": jobs,
        "extraction_llm_call_traces": traces,
    }
    assessment = assess_extraction_benchmark_completeness(bundle)
    blocked, _ = is_export_blocked_for_incomplete_extraction(bundle)
    assert assessment["incomplete"] is True
    assert assessment["inferred"] is True
    assert assessment["failure_reason"] == "provider_billing_or_quota"
    assert len(assessment["sources_with_zero_propositions"]) >= 3
    assert blocked is True
