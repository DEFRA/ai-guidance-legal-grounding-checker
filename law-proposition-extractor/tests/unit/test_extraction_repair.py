"""Repairable extraction detection, derived chunk cache semantics, and repair workflow."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from law_proposition_extractor_domain import Topic
from law_proposition_extractor_domain.models import Cluster, Proposition, ReviewStatus, SourceRecord
from law_proposition_extractor_pipeline.cli_run_summary import count_extraction_fallback_traces
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.derived_cache import DerivedArtifactCache
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.extract import (
    EXTRACTION_SCHEMA_VERSION_V2,
    ExtractSourceResult,
    attach_extraction_meta,
    extract_propositions_from_source,
    parse_extraction_meta,
    resolve_extraction_meta_for_proposition,
)
from law_proposition_extractor_pipeline.extraction_repair import (
    classify_repairable_failure_type,
    list_repairable_extraction_chunks,
    repairable_extraction_metrics_from_bundle,
    summarize_extraction_inspection,
)
from law_proposition_extractor_pipeline.runner import repair_extraction_from_export_dir


def _topic_cluster() -> tuple[Topic, Cluster]:
    return (
        Topic(id="topic-er", name="ER", description="", subject_tags=[]),
        Cluster(id="cluster-er", topic_id="topic-er", name="ER", description=""),
    )


def test_classify_quota_and_credit_messages() -> None:
    assert classify_repairable_failure_type("Insufficient credits remaining") == "insufficient_credits"
    assert classify_repairable_failure_type("You exceeded monthly quota") == "quota"


def test_repairable_metrics_null_token_estimate_when_repair_lacks_chunk_inputs() -> None:
    """Many repair targets have no stored input-token estimate — must serialize as null, not zero."""
    bundle = build_demo_bundle(use_llm=False)
    for tr in bundle["proposition_extraction_traces"]:
        if not isinstance(tr, dict) or str(tr.get("source_record_id")) != "src-uk-001":
            continue
        tr["extraction_mode"] = "frontier"
        tr["extraction_method"] = "fallback"
        tr["fallback_used"] = True
        tr["validation_errors"] = ["insufficient credits for model call"]
        tr["confidence"] = "medium"
        tr["signals"] = {**(tr.get("signals") or {}), "fallback_used": True}
    metrics = repairable_extraction_metrics_from_bundle(bundle)
    assert metrics["has_repairable_failures"] is True
    assert int(metrics["repairable_chunk_count"] or 0) >= 1
    assert metrics.get("estimated_retry_tokens") is None
    assert metrics.get("estimated_retry_token_count") is None


def test_repairable_metrics_positive_token_estimate_when_trace_signals_carry_max_tokens() -> None:
    bundle = build_demo_bundle(use_llm=False)
    for tr in bundle["proposition_extraction_traces"]:
        if not isinstance(tr, dict) or str(tr.get("source_record_id")) != "src-uk-001":
            continue
        tr["extraction_mode"] = "frontier"
        tr["extraction_method"] = "fallback"
        tr["fallback_used"] = True
        tr["validation_errors"] = ["insufficient credits for model call"]
        tr["confidence"] = "medium"
        tr["signals"] = {
            **(tr.get("signals") or {}),
            "fallback_used": True,
            "estimated_input_tokens_max": 12_500,
        }
    metrics = repairable_extraction_metrics_from_bundle(bundle)
    assert metrics.get("estimated_retry_tokens") == 12_500
    assert metrics.get("estimated_retry_token_count") == 12_500


def test_list_repairable_from_frontier_fallback_trace() -> None:
    bundle = build_demo_bundle(use_llm=False)
    for tr in bundle["proposition_extraction_traces"]:
        if not isinstance(tr, dict) or str(tr.get("source_record_id")) != "src-uk-001":
            continue
        tr["extraction_mode"] = "frontier"
        tr["extraction_method"] = "fallback"
        tr["fallback_used"] = True
        tr["validation_errors"] = ["insufficient credits for model call"]
        tr["confidence"] = "medium"
        tr["signals"] = {**(tr.get("signals") or {}), "fallback_used": True}
    chunks = list_repairable_extraction_chunks(bundle)
    assert chunks
    assert any(c.source_record_id == "src-uk-001" for c in chunks)
    summary = summarize_extraction_inspection(bundle)
    assert summary["has_repairable_extraction_failures"] is True
    assert summary["repairable_chunks"] >= 1


def test_list_repairable_merges_proposition_notes_meta_into_trace_errors() -> None:
    bundle = build_demo_bundle(use_llm=False)
    for row in bundle["propositions"]:
        if not isinstance(row, dict) or str(row.get("source_record_id")) != "src-uk-001":
            continue
        meta_notes = attach_extraction_meta(
            str(row.get("notes") or ""),
            {
                "extraction_mode": "frontier",
                "fallback_used": True,
                "validation_errors": ["Anthropic quota exceeded"],
            },
        )
        row["notes"] = meta_notes

    for tr in bundle["proposition_extraction_traces"]:
        if not isinstance(tr, dict) or str(tr.get("source_record_id")) != "src-uk-001":
            continue
        tr["extraction_mode"] = "frontier"
        tr["extraction_method"] = "fallback"
        tr["fallback_used"] = True
        tr["validation_errors"] = ["model call failed"]
        tr["confidence"] = "medium"
        tr["signals"] = {**(tr.get("signals") or {}), "fallback_used": True}

    chunks = list_repairable_extraction_chunks(bundle)
    assert chunks
    assert any((c.failure_type or "") == "quota" for c in chunks), (
        "notes-side judit_extraction_meta validation_errors must contribute to classify()"
    )


def test_list_repairable_detects_proposition_notes_meta_without_trace_fallback() -> None:
    """Notes may record frontier+fallback+errors while the trace row stays LLM (mixed exports)."""
    bundle = build_demo_bundle(use_llm=False)
    for row in bundle["propositions"]:
        if not isinstance(row, dict) or str(row.get("source_record_id")) != "src-uk-001":
            continue
        row["notes"] = attach_extraction_meta(
            str(row.get("notes") or ""),
            {
                "extraction_mode": "frontier",
                "fallback_used": True,
                "validation_errors": ["rate limit exceeded (429)"],
            },
        )
    for tr in bundle["proposition_extraction_traces"]:
        if not isinstance(tr, dict) or str(tr.get("source_record_id")) != "src-uk-001":
            continue
        tr["extraction_mode"] = "frontier"
        tr["extraction_method"] = "llm"
        tr["fallback_used"] = False
        tr["validation_errors"] = []
        tr["signals"] = {**(tr.get("signals") or {}), "fallback_used": False}

    chunks = list_repairable_extraction_chunks(bundle)
    assert chunks
    summary = summarize_extraction_inspection(bundle)
    assert summary["has_repairable_extraction_failures"] is True


def test_proposition_notes_meta_fallback_flag_parsed() -> None:
    bundle = build_demo_bundle(use_llm=False)
    row = next(
        x
        for x in bundle["propositions"]
        if isinstance(x, dict) and str(x.get("source_record_id")) == "src-uk-001"
    )
    row["notes"] = attach_extraction_meta(
        str(row.get("notes") or ""),
        {
            "extraction_mode": "frontier",
            "fallback_used": True,
            "validation_errors": ["insufficient credits"],
        },
    )
    # Structured extraction_debug_meta takes precedence; this test covers the legacy notes path,
    # so resolve without a structured override.
    meta = resolve_extraction_meta_for_proposition(
        notes=str(row.get("notes") or ""),
        extraction_debug_meta=None,
    )
    assert meta is not None
    assert meta.get("fallback_used") is True


def test_derived_chunk_failure_cache_skips_llm_without_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[int] = []

    def fake_try(
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        calls.append(1)
        return None, "insufficient credits for model call"

    monkeypatch.setattr("law_proposition_extractor_pipeline.extract._try_extract_model_v2_json", fake_try)
    topic, cluster = _topic_cluster()
    src = SourceRecord(
        id="src-chunk-cache",
        title="T",
        jurisdiction="UK",
        citation="C",
        kind="regulation",
        authoritative_text="Operators must keep records of animal movements.",
        authoritative_locator="article:1",
        current_snapshot_id="snap-cc",
        metadata={},
    )
    client = __import__("unittest.mock").mock.MagicMock()
    client.settings.frontier_extract_model = "frontier_extract"
    client.settings.local_extract_model = "local_extract"
    client.settings.max_extract_input_tokens = 150_000
    client.settings.extract_model_context_limit = 200_000

    cache = DerivedArtifactCache(cache_dir=tmp_path / "derived-chunk")
    extract_propositions_from_source(
        src,
        topic,
        cluster,
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        derived_chunk_cache=cache,
        retry_failed_llm=False,
    )
    assert len(calls) == 1
    extract_propositions_from_source(
        src,
        topic,
        cluster,
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        derived_chunk_cache=cache,
        retry_failed_llm=False,
    )
    assert len(calls) == 1

    def fake_try_ok(
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
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
    out = extract_propositions_from_source(
        src,
        topic,
        cluster,
        llm_client=client,
        limit=4,
        extraction_mode="frontier",
        extraction_fallback="mark_needs_review",
        derived_chunk_cache=cache,
        retry_failed_llm=True,
    )
    assert len(calls) == 2
    assert out.fallback_used is False
    assert not any(
        t.get("llm_cache_hit") == "failed_chunk_cached" for t in out.extraction_llm_call_traces
    )


def _patch_uk_traces_as_repairable(bundle: dict[str, Any]) -> None:
    for tr in bundle["proposition_extraction_traces"]:
        if not isinstance(tr, dict) or str(tr.get("source_record_id")) != "src-uk-001":
            continue
        tr["extraction_mode"] = "frontier"
        tr["extraction_method"] = "fallback"
        tr["fallback_used"] = True
        tr["validation_errors"] = ["insufficient credits for model call"]
        tr["confidence"] = "medium"
        tr["signals"] = {**(tr.get("signals") or {}), "fallback_used": True}
    for row in bundle["propositions"]:
        if not isinstance(row, dict) or str(row.get("source_record_id")) != "src-uk-001":
            continue
        row["notes"] = attach_extraction_meta(
            str(row.get("notes") or ""),
            {
                "extraction_mode": "frontier",
                "fallback_used": True,
                "validation_errors": ["insufficient credits for model call"],
            },
        )


def test_repair_only_calls_extract_for_repairable_source(
    tmp_path: Path,
) -> None:
    bundle = build_demo_bundle(use_llm=False)
    _patch_uk_traces_as_repairable(bundle)
    assert count_extraction_fallback_traces(bundle) >= 1

    uk_templates = [
        Proposition.model_validate(p)
        for p in bundle["propositions"]
        if isinstance(p, dict) and str(p.get("source_record_id")) == "src-uk-001"
    ]
    assert len(uk_templates) >= 1

    extract_calls: list[str] = []

    def fake_extract(*, source: SourceRecord, topic: Topic, cluster: Cluster, **kwargs: Any) -> Any:
        extract_calls.append(str(source.id))
        props: list[Proposition] = []
        for i, t in enumerate(uk_templates):
            props.append(
                t.model_copy(
                    update={
                        "id": f"prelim-uk-{i}",
                        "review_status": ReviewStatus.PROPOSED,
                        "notes": "",
                    }
                )
            )
        return ExtractSourceResult(
            propositions=props,
            extraction_mode=str(kwargs.get("extraction_mode") or "frontier"),
            model_alias="frontier_extract",
            fallback_policy=str(kwargs.get("extraction_fallback") or "mark_needs_review"),
            fallback_used=False,
            validation_errors=[],
            prompt_version=str(kwargs.get("prompt_version") or "v2"),
            schema_version=EXTRACTION_SCHEMA_VERSION_V2,
        )

    out_dir = tmp_path / "repaired"
    base_run_id = str(bundle["run"]["id"])
    with patch("law_proposition_extractor_pipeline.runner.extract_propositions_from_source", side_effect=fake_extract):
        repaired = repair_extraction_from_export_dir(
            base_bundle=bundle,
            export_dir_abs=str(tmp_path / "unused"),
            output_export_dir=out_dir,
            new_run_id=f"{base_run_id}-repaired",
            extraction_mode="frontier",
            extraction_fallback="mark_needs_review",
            only="repairable",
            in_place=False,
            retry_failed_extraction_cache=None,
            ignore_failed_extraction_cache=False,
            retry_failed_llm=True,
            source_cache_dir=str(tmp_path / "src-cache"),
            derived_cache_dir=str(tmp_path / "derived-cache"),
            use_llm=True,
            progress=None,
        )

    assert extract_calls == ["src-uk-001"]
    meta = repaired.get("extraction_repair_metadata") or {}
    assert meta.get("repaired_from_run_id") == base_run_id
    assert int(meta.get("repaired_chunk_count") or 0) >= 1
    assert count_extraction_fallback_traces(repaired) == 0


def test_repair_in_place_leaves_original_export_intact(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    _patch_uk_traces_as_repairable(bundle)
    orig = tmp_path / "orig"
    work = tmp_path / "work"
    export_bundle(bundle=bundle, output_dir=str(orig))
    shutil.copytree(orig, work)
    run_json_bytes = (orig / "run.json").read_bytes()

    uk_templates = [
        Proposition.model_validate(p)
        for p in bundle["propositions"]
        if isinstance(p, dict) and str(p.get("source_record_id")) == "src-uk-001"
    ]

    def fake_extract(*, source: SourceRecord, topic: Topic, cluster: Cluster, **kwargs: Any) -> Any:
        props = [
            t.model_copy(update={"id": f"prelim-uk-{i}", "notes": ""})
            for i, t in enumerate(uk_templates)
        ]
        return ExtractSourceResult(
            propositions=props,
            extraction_mode="frontier",
            model_alias="frontier_extract",
            fallback_policy="mark_needs_review",
            fallback_used=False,
            validation_errors=[],
            prompt_version="v2",
            schema_version=EXTRACTION_SCHEMA_VERSION_V2,
        )

    base_run_id = str(bundle["run"]["id"])
    with patch("law_proposition_extractor_pipeline.runner.extract_propositions_from_source", side_effect=fake_extract):
        repair_extraction_from_export_dir(
            base_bundle=bundle,
            export_dir_abs=str(work),
            output_export_dir=work,
            new_run_id=base_run_id,
            extraction_mode="frontier",
            extraction_fallback="mark_needs_review",
            only="repairable",
            in_place=True,
            retry_failed_extraction_cache=None,
            ignore_failed_extraction_cache=False,
            retry_failed_llm=True,
            source_cache_dir=str(tmp_path / "s2"),
            derived_cache_dir=str(tmp_path / "d2"),
            use_llm=True,
            progress=None,
        )

    assert (orig / "run.json").read_bytes() == run_json_bytes


def test_api_repair_extraction_endpoint_dispatches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from law_proposition_extractor_api.main import app
    from law_proposition_extractor_api.settings import settings

    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    run_id = str(bundle["run"]["id"])
    captured: dict[str, Any] = {}

    def fake_repair(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"run": {"id": "repaired-run"}, "extraction_repair_metadata": {"repaired_chunk_count": 1}}

    monkeypatch.setattr("law_proposition_extractor_api.main.repair_extraction_from_export_dir", fake_repair)
    previous_export_dir = settings.operations_export_dir
    settings.operations_export_dir = str(tmp_path)
    try:
        client = TestClient(app)
        resp = client.post(
            "/ops/run-jobs/repair-extraction",
            json={"run_id": run_id, "retry_failed_llm": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("run_id") == "repaired-run"
        assert captured.get("retry_failed_llm") is True
        assert captured.get("in_place") is False
    finally:
        settings.operations_export_dir = previous_export_dir
