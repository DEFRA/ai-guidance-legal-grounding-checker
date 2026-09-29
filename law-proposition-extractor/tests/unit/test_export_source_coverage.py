"""Source coverage guard for export acceptance and fresh verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from law_proposition_extractor_pipeline.export_acceptance import (
    compute_acceptance_status,
    detect_repairable_issues,
    run_export_acceptance_workflow,
)
from law_proposition_extractor_pipeline.extraction_provider_failure import (
    BENCHMARK_VERDICT_INCOMPLETE,
    attach_extraction_abort_to_bundle,
)
from law_proposition_extractor_pipeline.export_source_coverage import assess_export_source_coverage
from law_proposition_extractor_pipeline.proposition_quality_gates import PropositionQualityReport

ANTHROPIC_CREDIT_MSG = (
    "model call or JSON parse failed: Error code: 400 - "
    "'litellm.BadRequestError: AnthropicException - "
    '{"message":"Your credit balance is too low to access the Anthropic API."}'
)

_PROP_DEFAULTS = {
    "topic_id": "topic-test",
    "cluster_id": "cluster-test",
    "legal_subject": "subject",
    "action": "means",
    "jurisdiction": "UK",
    "source_jurisdiction": "UK",
    "is_compliance_relevant": True,
    "is_comparison_anchor": False,
    "review_notes": "",
    "extraction_debug_meta": {
        "evidence_quote": "Evidence text.",
        "model_confidence": "high",
        "validation_errors": [],
        "trace_warnings": [],
    },
}


def _prop(source_id: str, prop_id: str, *, compliance: bool = True, **extra: object) -> dict[str, Any]:
    row = {
        **_PROP_DEFAULTS,
        "id": prop_id,
        "source_record_id": source_id,
        "fragment_locator": "regulation 1",
        "proposition_text": "Test proposition text.",
        "label": f"Label {prop_id}",
        "proposition_tier": "substantive_rule",
        "legal_effect_type": "obligation",
        "is_compliance_relevant": compliance,
        **extra,
    }
    return row


def _source(source_id: str, title: str) -> dict[str, Any]:
    return {"id": source_id, "title": title, "jurisdiction": "UK", "citation": title, "kind": "regulation"}


def _write_two_source_export(export_dir: Path, *, props: list[dict[str, Any]]) -> None:
    export_dir.mkdir(parents=True, exist_ok=True)
    sources = [_source("src-a", "Source A"), _source("src-b", "Source B")]
    (export_dir / "sources.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    (export_dir / "propositions.json").write_text(json.dumps(props, indent=2) + "\n", encoding="utf-8")
    (export_dir / "MODEL.md").write_text("# test export\n", encoding="utf-8")
    (export_dir / "manifest.json").write_text(
        json.dumps({"proposition_count": len(props), "has_proposition_extraction_traces": False}) + "\n",
        encoding="utf-8",
    )


def test_clean_two_source_export_accepted(tmp_path: Path) -> None:
    export = tmp_path / "clean-two-source"
    _write_two_source_export(
        export,
        props=[
            _prop("src-a", "p-a1"),
            _prop("src-a", "p-a2"),
            _prop("src-b", "p-b1"),
        ],
    )
    report = run_export_acceptance_workflow(
        export_dir=export,
        auto_repair=False,
        acceptance_report=True,
        repair_mode="deterministic",
        use_llm_coverage=False,
    )
    assert report.acceptance_status in {"accepted", "accepted_with_warnings"}
    assert report.source_coverage["expected_source_count"] == 2
    assert report.source_coverage["sources_with_propositions"] == 2
    assert report.source_coverage["sources_with_zero_propositions"] == []


def test_missing_source_propositions_failed_incomplete_extraction(tmp_path: Path) -> None:
    from law_proposition_extractor_pipeline.fresh_extraction_verification import build_fresh_extraction_verification

    export = tmp_path / "missing-source"
    _write_two_source_export(
        export,
        props=[_prop("src-a", "p-a1"), _prop("src-a", "p-a2")],
    )
    verification = build_fresh_extraction_verification(export)
    assert verification.hard_failure is True
    assert any(f.check_id == "source_zero_propositions" for f in verification.findings)
    assert verification.source_coverage is not None
    assert verification.source_coverage.sources_with_zero_propositions == ["src-b"]

    quality = PropositionQualityReport(
        proposition_count=2,
        error_count=0,
        warning_count=0,
        newly_normalised=False,
    )
    status, hard, _human, _warnings = compute_acceptance_status(
        proposition_count=2,
        verification=verification,
        quality=quality,
        issues_after=[],
        anchor_summary={"all_dense_anchors_covered": True},
    )
    assert status == "failed"
    assert BENCHMARK_VERDICT_INCOMPLETE in hard


def test_zero_compliance_relevant_source_warns(tmp_path: Path) -> None:
    from law_proposition_extractor_pipeline.fresh_extraction_verification import build_fresh_extraction_verification

    export = tmp_path / "zero-compliance"
    _write_two_source_export(
        export,
        props=[
            _prop("src-a", "p-a1"),
            _prop("src-b", "p-b1", compliance=False, legal_effect_type="definition", proposition_tier="definitional_rule"),
        ],
    )
    verification = build_fresh_extraction_verification(export)
    assert verification.hard_failure is False
    assert any(f.check_id == "source_zero_compliance_relevant" for f in verification.findings)

    report = run_export_acceptance_workflow(
        export_dir=export,
        auto_repair=False,
        acceptance_report=True,
        repair_mode="deterministic",
        use_llm_coverage=False,
    )
    assert report.acceptance_status == "accepted_with_warnings"


def test_low_proposition_count_needs_review(tmp_path: Path) -> None:
    from law_proposition_extractor_pipeline.fresh_extraction_verification import build_fresh_extraction_verification

    export = tmp_path / "low-count"
    _write_two_source_export(
        export,
        props=[_prop("src-a", "p-a1") for _ in range(10)] + [_prop("src-b", "p-b1")],
    )
    (export / "source_proposition_baseline.json").write_text(
        json.dumps({"src-a": 100, "src-b": 100}) + "\n",
        encoding="utf-8",
    )
    verification = build_fresh_extraction_verification(export)
    assert any(f.check_id == "source_low_proposition_count" for f in verification.findings)

    quality = PropositionQualityReport(
        proposition_count=11,
        error_count=0,
        warning_count=0,
        newly_normalised=False,
    )
    status, _hard, human, _warnings = compute_acceptance_status(
        proposition_count=11,
        verification=verification,
        quality=quality,
        issues_after=[],
        anchor_summary={"all_dense_anchors_covered": True},
    )
    assert status == "needs_review"
    assert any("source_low_proposition_count:src-a" in item for item in human)


def test_provider_abort_metadata_still_fails_as_before() -> None:
    bundle: dict[str, Any] = {
        "run": {"id": "run-001"},
        "source_records": [{"id": "src-a"}, {"id": "src-b"}],
        "propositions": [{"id": "p1", "source_record_id": "src-a"}],
        "extraction_abort_metadata": {
            "aborted": True,
            "benchmark_verdict": BENCHMARK_VERDICT_INCOMPLETE,
            "failure_reason": "provider_billing_or_quota",
            "failed_extraction_jobs": 10,
            "attempted_extraction_jobs": 10,
        },
    }
    attach_extraction_abort_to_bundle(
        bundle,
        bundle["extraction_abort_metadata"],
    )
    issues = detect_repairable_issues(bundle=bundle)
    incomplete = [i for i in issues if i.check_id == "incomplete_extraction"]
    assert incomplete

    from law_proposition_extractor_pipeline.fresh_extraction_verification import FreshExtractionVerificationReport

    verification = FreshExtractionVerificationReport(
        export_dir=".",
        generated_at="2026-01-01T00:00:00Z",
        proposition_count=1,
        error_count=0,
        warning_count=0,
        hard_failure=False,
        export_presence={},
        counts={},
        prompt_lab_anchors=[],
    )
    quality = PropositionQualityReport(
        proposition_count=1,
        error_count=0,
        warning_count=0,
        newly_normalised=False,
    )
    status, hard, _human, _warnings = compute_acceptance_status(
        proposition_count=1,
        verification=verification,
        quality=quality,
        issues_after=issues,
        anchor_summary={"all_dense_anchors_covered": True},
    )
    assert status == "failed"
    assert BENCHMARK_VERDICT_INCOMPLETE in hard


def test_assess_export_source_coverage_counts() -> None:
    sources = {"src-a": _source("src-a", "A"), "src-b": _source("src-b", "B")}
    props = [_prop("src-a", "p1"), _prop("src-a", "p2", compliance=False)]
    summary = assess_export_source_coverage(".", props, sources_by_id=sources)
    assert summary.expected_source_count == 2
    assert summary.propositions_by_source["A"] == 2
    assert summary.compliance_relevant_by_source["A"] == 1
    assert summary.sources_with_zero_propositions == ["src-b"]
