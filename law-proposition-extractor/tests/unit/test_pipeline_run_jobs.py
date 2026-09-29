from types import SimpleNamespace
from pathlib import Path

from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.pipeline_run_jobs import (
    PersistingPipelineProgress,
    RunJobStore,
    job_metrics_from_bundle,
    new_job_id,
    terminal_job_status_from_run_quality,
)


def test_run_job_events_ordered_by_sequence(tmp_path: Path) -> None:
    store = RunJobStore(tmp_path)
    jid = new_job_id()
    store.create_job(job_id=jid, request_summary={"topic_name": "t"})
    pr = PersistingPipelineProgress(store, jid)
    pr.mark_running()
    pr.stage("Source intake", detail="1 raw")
    pr.stage("Source parsing", detail="0 traces")
    pr.stage("Source fragmentation", detail="0 frags")
    events = store.read_events(jid)
    seqs = [int(e["sequence_number"]) for e in events]
    assert seqs == sorted(seqs)
    assert len(events) >= 2


def test_extraction_failure_emits_error_event(tmp_path: Path) -> None:
    store = RunJobStore(tmp_path)
    jid = new_job_id()
    store.create_job(job_id=jid, request_summary={})
    pr = PersistingPipelineProgress(store, jid)
    outcome = SimpleNamespace(
        propositions=[],
        extraction_llm_call_traces=[
            {
                "source_record_id": "s1",
                "source_title": "T",
                "llm_invoked": False,
                "skip_reason": "context_window_risk",
            }
        ],
        extraction_mode="frontier",
        model_alias="m1",
        fallback_used=False,
        failed_closed=True,
        failure_reason="litellm.RateLimitError: quota",
        validation_errors=[],
    )
    pr.extraction_source_complete(outcome)
    events = store.read_events(jid)
    assert any(
        any("quota" in str(x) for x in (e.get("errors") or []))
        for e in events
        if e.get("status") == "fail"
    )


def test_job_metrics_include_extraction_llm_summary(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle, output_dir=str(tmp_path))
    m = job_metrics_from_bundle(bundle)
    assert "llm_extraction_call_count" in m
    assert "max_estimated_input_tokens" in m
    assert terminal_job_status_from_run_quality(bundle) in {"pass", "warning", "fail"}
