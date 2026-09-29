from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from law_proposition_extractor_llm import JuditLLMClient
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.linting import load_exported_bundle
from law_proposition_extractor_pipeline.operations import OperationalStore, OperationsError
from law_proposition_extractor_pipeline.operations_clear import (
    ClearOperationsConfirmationError,
    ClearOperationsOutcome,
    UnsafeExportDirError,
    execute_clear_operations_all,
    execute_clear_operations_runs_only,
)
from law_proposition_extractor_pipeline.pipeline_run_jobs import (
    PersistingPipelineProgress,
    RunJobStore,
    new_job_id,
)
from law_proposition_extractor_pipeline.dataset_comparison_run import run_proposition_dataset_comparison
from law_proposition_extractor_pipeline.equine_corpus_workflow import run_equine_corpus_export
from law_proposition_extractor_pipeline.runner import repair_extraction_from_export_dir, run_registry_sources
from law_proposition_extractor_pipeline.sources import (
    SourceRegistryError,
    SourceRegistryService,
    SourceSearchError,
    SourceSearchService,
)
from law_proposition_extractor_pipeline.sources.family_candidate_registration import register_family_candidates
from law_proposition_extractor_pipeline.sources.source_family_discovery import discover_related_for_registry_entry
from pydantic import BaseModel, Field, model_validator

from .settings import settings

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/llm/status")
def llm_status() -> JSONResponse:
    try:
        client = JuditLLMClient()
        model_ids = client.list_models()
        return JSONResponse(
            {
                "status": "ok",
                "base_url": client.settings.base_url,
                "models": model_ids,
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": str(exc),
            },
        )


@app.get("/models")
def models() -> JSONResponse:
    return llm_status()


class DevClearRunsRequest(BaseModel):
    dry_run: bool = False
    confirmation_text: str | None = None


class DevClearAllRequest(BaseModel):
    dry_run: bool = False
    confirmation_text: str | None = None


def _clear_outcome_dict(*, outcome: ClearOperationsOutcome) -> dict[str, Any]:
    return {
        "mode": outcome.mode,
        "dry_run": outcome.dry_run,
        "export_dir": outcome.export_dir,
        "deleted_paths_export": list(outcome.deleted_paths_export),
        "preserved_registry_path": outcome.preserved_registry_path,
        "cleared_source_cache_paths": list(outcome.cleared_source_cache_paths),
        "cleared_derived_cache_paths": list(outcome.cleared_derived_cache_paths),
        "registry_reset_written": outcome.registry_reset_written,
        "messages": list(outcome.messages),
    }


def _with_clear_error_handling(handler) -> dict[str, Any]:
    try:
        return handler()
    except UnsafeExportDirError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ClearOperationsConfirmationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ops/dev/clear/runs")
def ops_dev_clear_runs(payload: DevClearRunsRequest) -> dict[str, Any]:
    def _handler() -> dict[str, Any]:
        if not payload.dry_run:
            if (payload.confirmation_text or "").strip() != "CLEAR RUNS":
                raise HTTPException(
                    status_code=400,
                    detail="Destructive clear requires confirmation_text exactly CLEAR RUNS, or set dry_run: true.",
                )
        outcome = execute_clear_operations_runs_only(
            export_dir=settings.operations_export_dir,
            source_registry_path=settings.source_registry_path,
            dry_run=payload.dry_run,
            confirm=not payload.dry_run,
        )
        response: dict[str, Any] = _clear_outcome_dict(outcome=outcome)
        response["kind"] = "clear_operations_runs"
        return response

    return _with_clear_error_handling(_handler)


@app.post("/ops/dev/clear/all")
def ops_dev_clear_all(payload: DevClearAllRequest) -> dict[str, Any]:
    def _handler() -> dict[str, Any]:
        if not payload.dry_run:
            if (payload.confirmation_text or "").strip() != "CLEAR ALL":
                raise HTTPException(
                    status_code=400,
                    detail="Destructive clear requires confirmation_text exactly CLEAR ALL, or set dry_run: true.",
                )
        outcome = execute_clear_operations_all(
            export_dir=settings.operations_export_dir,
            source_registry_path=settings.source_registry_path,
            source_cache_dir=settings.source_cache_dir,
            derived_cache_dir=settings.derived_cache_dir,
            dry_run=payload.dry_run,
            confirm=not payload.dry_run,
        )
        payload_out: dict[str, Any] = _clear_outcome_dict(outcome=outcome)
        payload_out["kind"] = "clear_operations_all"
        return payload_out

    return _with_clear_error_handling(_handler)


@app.get("/demo")
def demo(use_llm: bool = False, case_name: str | None = None) -> dict[str, Any]:
    return build_demo_bundle(use_llm=use_llm, case_name=case_name)


@app.post("/demo/export")
def demo_export(use_llm: bool = False, case_name: str | None = None) -> dict[str, Any]:
    bundle = build_demo_bundle(use_llm=use_llm, case_name=case_name)
    export_bundle(bundle, output_dir="dist/static-report")
    return {
        "status": "ok",
        "output_dir": "dist/static-report",
        "run_id": bundle.get("run", {}).get("id"),
        "workflow_mode": bundle.get("workflow_mode", bundle.get("run", {}).get("workflow_mode")),
        "has_divergence_outputs": bundle.get("has_divergence_outputs", False),
    }


def _operations_store() -> OperationalStore:
    return OperationalStore(
        export_dir=settings.operations_export_dir,
        source_registry_path=settings.source_registry_path,
    )


def _run_job_store() -> RunJobStore:
    return RunJobStore(Path(settings.operations_export_dir))


def _with_operations_error_handling(handler) -> Any:
    try:
        return handler()
    except OperationsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _source_registry() -> SourceRegistryService:
    return SourceRegistryService(
        registry_path=settings.source_registry_path,
        source_cache_dir=settings.source_cache_dir,
    )


def _source_search_service() -> SourceSearchService:
    return SourceSearchService()


def _with_registry_error_handling(handler) -> Any:
    try:
        return handler()
    except SourceRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _with_source_search_error_handling(handler) -> Any:
    try:
        return handler()
    except SourceSearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SourceRegistryReferenceRequest(BaseModel):
    reference: dict[str, Any]
    refresh: bool = True


class RegisterFamilyCandidatesRequest(BaseModel):
    target_registry_id: str = Field(min_length=1)
    candidate_ids: list[str] = Field(default_factory=list)


class RegistryRunRequest(BaseModel):
    registry_ids: list[str] = Field(min_length=1)
    topic_name: str
    cluster_name: str | None = None
    analysis_mode: str = "auto"
    analysis_scope: Literal["eu", "uk", "eu_uk", "selected_sources"] = "selected_sources"
    refresh_sources: bool = False
    run_id: str | None = None
    run_notes: str = ""
    subject_tags: list[str] = Field(default_factory=list)
    comparison_jurisdiction_a: str | None = None
    comparison_jurisdiction_b: str | None = None
    proposition_index: int = 0
    use_llm: bool = False
    quality_run: bool = False
    extraction_mode: Literal["heuristic", "local", "frontier"] | None = None
    extraction_execution_mode: Literal["interactive", "batch"] | None = None
    extraction_fallback: Literal["fallback", "mark_needs_review", "fail_closed"] | None = None
    divergence_reasoning: Literal["none", "frontier"] | None = None
    focus_scopes: list[str] | None = None
    max_propositions_per_source: int | None = Field(default=None, ge=1, le=256)
    source_family_selection: dict[str, Any] | None = None
    model_error_policy: Literal[
        "continue_with_fallback", "stop_repairable", "continue_repairable"
    ] | None = None


def _registry_run_equine_hint(topic_name: str, subject_tags: list[str]) -> bool:
    blob = f"{topic_name} {' '.join(subject_tags)}".lower()
    return any(k in blob for k in ("equine", "equidae", "equid", "horse"))


def _resolve_registry_run_extraction(
    payload: RegistryRunRequest,
) -> tuple[bool, str | None, str, str | None, list[str] | None, int | None, str | None]:
    use_llm = bool(payload.use_llm)
    mode = payload.extraction_mode
    fb = payload.extraction_fallback
    div = payload.divergence_reasoning
    focus = list(payload.focus_scopes) if payload.focus_scopes is not None else None
    max_p = payload.max_propositions_per_source
    model_error_policy = payload.model_error_policy

    if payload.quality_run:
        use_llm = True
        mode = mode or "frontier"
        fb = fb or "mark_needs_review"
        div = div or "frontier"
        if model_error_policy is None:
            model_error_policy = "stop_repairable"
        if max_p is None:
            max_p = 12
        if focus is None and _registry_run_equine_hint(payload.topic_name, payload.subject_tags):
            focus = ["equine", "equidae", "equid", "horse"]

    if fb is None:
        fb = "fallback"

    return use_llm, mode, fb, div, focus, max_p, model_error_policy


class EquineCorpusRunRequest(BaseModel):
    corpus_config_path: str | None = None
    corpus_id: str | None = None
    use_llm: bool = False
    extraction_mode: Literal["heuristic", "local", "frontier"] | None = None
    extraction_execution_mode: Literal["interactive", "batch"] | None = None
    extraction_fallback: Literal["fallback", "mark_needs_review", "fail_closed"] | None = None
    divergence_reasoning: Literal["none", "frontier"] | None = None
    focus_scopes: list[str] | None = None
    max_propositions_per_source: int | None = Field(default=None, ge=1, le=256)


def _resolve_equine_corpus_config_for_job(payload: EquineCorpusRunRequest) -> Path:
    raw_path = (payload.corpus_config_path or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate.resolve()
    cid = (payload.corpus_id or "equine_law").strip()
    if cid != "equine_law":
        raise ValueError(f"Unsupported corpus_id {cid!r} (supported: equine_law)")
    p = Path((settings.equine_corpus_config_path or "examples/corpus_equine_law.json").strip())
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def _equine_corpus_run_job_worker(job_id: str, payload_data: dict[str, Any]) -> None:
    payload = EquineCorpusRunRequest.model_validate(payload_data)
    store = _run_job_store()
    pr = PersistingPipelineProgress(store, job_id)
    pr.mark_running()
    try:
        cfg_path = _resolve_equine_corpus_config_for_job(payload)
        if not cfg_path.is_file():
            raise FileNotFoundError(f"Corpus config not found: {cfg_path}")
        ext_fb = payload.extraction_fallback or "fallback"
        bundle, _summary = run_equine_corpus_export(
            corpus_config_path=cfg_path,
            output_dir=settings.operations_export_dir,
            use_llm=payload.use_llm,
            extraction_mode=payload.extraction_mode,
            extraction_execution_mode=payload.extraction_execution_mode,
            extraction_fallback=ext_fb,
            divergence_reasoning=payload.divergence_reasoning,
            source_cache_dir=settings.source_cache_dir,
            derived_cache_dir=settings.derived_cache_dir,
            progress=pr,
            focus_scopes=payload.focus_scopes,
            max_propositions_per_source=payload.max_propositions_per_source,
        )
        pr.finalize_job_success(bundle)
    except Exception as exc:
        pr.finalize_job_failure(exc)


def _registry_run_job_worker(job_id: str, payload_data: dict[str, Any]) -> None:
    payload = RegistryRunRequest.model_validate(payload_data)
    use_llm, ext_mode, ext_fb, div_reason, focus_scopes, max_props, model_error_policy = (
        _resolve_registry_run_extraction(payload)
    )
    store = _run_job_store()
    pr = PersistingPipelineProgress(store, job_id)
    pr.mark_running()
    try:
        bundle = run_registry_sources(
            registry_ids=payload.registry_ids,
            topic_name=payload.topic_name,
            cluster_name=payload.cluster_name,
            analysis_mode=payload.analysis_mode,
            analysis_scope=payload.analysis_scope,
            refresh_sources=payload.refresh_sources,
            run_id=payload.run_id,
            run_notes=payload.run_notes,
            subject_tags=payload.subject_tags,
            comparison_jurisdiction_a=payload.comparison_jurisdiction_a,
            comparison_jurisdiction_b=payload.comparison_jurisdiction_b,
            proposition_index=payload.proposition_index,
            use_llm=use_llm,
            extraction_mode=ext_mode,
            extraction_execution_mode=payload.extraction_execution_mode,
            extraction_fallback=ext_fb,
            divergence_reasoning=div_reason,
            source_registry_path=settings.source_registry_path,
            source_cache_dir=settings.source_cache_dir,
            derived_cache_dir=settings.derived_cache_dir,
            source_family_selection=payload.source_family_selection,
            focus_scopes=focus_scopes,
            max_propositions_per_source=max_props,
            model_error_policy=model_error_policy,
            progress=pr,
        )
        pr.stage("Export bundle", detail=str(settings.operations_export_dir))
        export_bundle(bundle, output_dir=settings.operations_export_dir)
        rq = bundle.get("run_quality_summary")
        if isinstance(rq, dict):
            pr.stage(
                "Lint / quality summary",
                detail=f"status={rq.get('status')}, warnings={rq.get('warning_count', 0)}",
            )
        pr.finalize_job_success(bundle)
    except SourceRegistryError as exc:
        pr.finalize_job_failure(exc)
    except Exception as exc:
        pr.finalize_job_failure(exc)


class ComparePropositionDatasetsRequest(BaseModel):
    """Compare two exported proposition datasets (divergence only; no source extraction)."""

    left_run_id: str = Field(min_length=1)
    right_run_id: str = Field(min_length=1)
    comparison_run_id: str | None = None
    topic_name: str | None = None
    use_llm: bool = False
    divergence_reasoning: Literal["none", "frontier"] | None = None
    proposition_index: int = 0
    comparison_jurisdiction_a: str | None = None
    comparison_jurisdiction_b: str | None = None
    pairing_settings: dict[str, Any] | None = None


def _compare_proposition_datasets_job_worker(job_id: str, payload_data: dict[str, Any]) -> None:
    payload = ComparePropositionDatasetsRequest.model_validate(payload_data)
    store = _run_job_store()
    pr = PersistingPipelineProgress(store, job_id)
    pr.mark_running()
    try:
        ops = _operations_store()
        left_path = ops.resolve_run_export_dir(payload.left_run_id)
        right_path = ops.resolve_run_export_dir(payload.right_run_id)
        left_b = load_exported_bundle(left_path)
        right_b = load_exported_bundle(right_path)
        div = payload.divergence_reasoning or "none"
        use_llm = bool(payload.use_llm) or div == "frontier"
        bundle = run_proposition_dataset_comparison(
            left_bundle=left_b,
            right_bundle=right_b,
            comparison_run_id=payload.comparison_run_id,
            topic_name=payload.topic_name,
            use_llm=use_llm,
            divergence_reasoning=div,
            extraction_mode="heuristic",
            extraction_fallback="fallback",
            proposition_index=payload.proposition_index,
            source_cache_dir=settings.source_cache_dir,
            derived_cache_dir=settings.derived_cache_dir,
            pairing_settings=payload.pairing_settings,
            comparison_jurisdiction_a=payload.comparison_jurisdiction_a,
            comparison_jurisdiction_b=payload.comparison_jurisdiction_b,
        )
        pr.stage("Export bundle", detail=str(settings.operations_export_dir))
        export_bundle(bundle, output_dir=settings.operations_export_dir)
        rq = bundle.get("run_quality_summary")
        if isinstance(rq, dict):
            pr.stage(
                "Lint / quality summary",
                detail=f"status={rq.get('status')}, warnings={rq.get('warning_count', 0)}",
            )
        pr.finalize_job_success(bundle)
    except Exception as exc:
        pr.finalize_job_failure(exc)


class SourceRegistrySearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=240)
    provider: str = "legislation_gov_uk"
    limit: int = Field(default=10, ge=1, le=25)


class PipelineReviewDecisionAppendRequest(BaseModel):
    """Append-only pipeline review row (governance)."""

    artifact_type: str = "proposition"
    artifact_id: str = Field(min_length=1)
    decision: Literal["approved", "rejected", "needs_review", "overridden", "deferred"]
    reviewer: str | None = None
    reason: str = ""
    replacement_value: Any | None = None
    evidence: list[str] = Field(default_factory=list)
    applies_to_field: str | None = None
    supersedes_decision_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    decision_id: str | None = None


@app.get("/ops/runs")
def list_runs() -> dict[str, Any]:
    return _with_operations_error_handling(lambda: {"runs": _operations_store().list_runs()})


@app.get("/ops/runs/{run_id}")
def inspect_run(run_id: str) -> dict[str, Any]:
    return _with_operations_error_handling(lambda: _operations_store().inspect_run(run_id=run_id))


@app.get("/ops/corpus-coverage/equine")
def ops_equine_corpus_coverage() -> dict[str, Any]:
    return _with_operations_error_handling(lambda: _operations_store().equine_corpus_coverage())


@app.get("/ops/runs/{run_id}/traces")
def inspect_run_traces(run_id: str) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_stage_traces(run_id=run_id)
    )


@app.get("/ops/runs/{run_id}/review-decisions")
def list_run_review_decisions(run_id: str) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_review_decisions(run_id=run_id)
    )


@app.get("/ops/pipeline-review-decisions")
def list_pipeline_review_decisions(
    run_id: str | None = Query(default=None),
    artifact_type: str | None = Query(default=None),
    artifact_id: str | None = Query(default=None),
    decision: str | None = Query(default=None),
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_pipeline_review_decisions(
            run_id=run_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            decision=decision,
        )
    )


@app.post("/ops/runs/{run_id}/pipeline-review-decisions")
def append_run_pipeline_review_decision(
    run_id: str, payload: PipelineReviewDecisionAppendRequest
) -> dict[str, Any]:
    def _handler() -> dict[str, Any]:
        row = _operations_store().append_pipeline_review_decision(
            run_id=run_id,
            artifact_type=payload.artifact_type,
            artifact_id=payload.artifact_id,
            decision=payload.decision,
            reviewer=payload.reviewer,
            reason=payload.reason,
            replacement_value=payload.replacement_value,
            evidence=payload.evidence,
            applies_to_field=payload.applies_to_field,
            supersedes_decision_id=payload.supersedes_decision_id,
            metadata=payload.metadata,
            decision_id=payload.decision_id,
        )
        return {"pipeline_review_decision": row}

    try:
        return _handler()
    except OperationsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/ops/sources")
def list_sources(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_source_records(run_id=run_id)
    )


@app.get("/ops/source-snapshots")
def list_source_snapshots_for_run(
    run_id: str | None = None,
    include_authoritative_text: bool = False,
) -> dict[str, Any]:
    """List all source snapshots for a run (Workbench provenance; no N+1 per source)."""
    return _with_operations_error_handling(
        lambda: _operations_store().list_all_source_snapshots(
            run_id=run_id,
            include_authoritative_text=include_authoritative_text,
        )
    )


@app.get("/ops/source-snapshots/{snapshot_id}/content")
def get_source_snapshot_content(snapshot_id: str, run_id: str | None = None) -> dict[str, Any]:
    """Return persisted authoritative snapshot text for a registered snapshot id only."""
    return _with_operations_error_handling(
        lambda: _operations_store().get_source_snapshot_content(
            snapshot_id=snapshot_id,
            run_id=run_id,
        )
    )


@app.get("/ops/source-target-links")
def list_source_target_links(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_source_target_links(run_id=run_id)
    )


@app.get("/ops/source-fetch-attempts")
def list_source_fetch_attempts(
    run_id: str | None = None,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_source_fetch_attempts(
            run_id=run_id,
            source_record_id=source_record_id,
        )
    )


@app.get("/ops/source-fragments")
def list_source_fragments(
    run_id: str | None = None,
    source_record_id: str | None = None,
    source_snapshot_id: str | None = None,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_source_fragments_filtered(
            run_id=run_id,
            source_record_id=source_record_id,
            source_snapshot_id=source_snapshot_id,
        )
    )


@app.get("/ops/source-parse-traces")
def list_source_parse_traces(
    run_id: str | None = None,
    source_record_id: str | None = None,
    source_snapshot_id: str | None = None,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_source_parse_traces(
            run_id=run_id,
            source_record_id=source_record_id,
            source_snapshot_id=source_snapshot_id,
        )
    )


@app.get("/ops/propositions")
def list_propositions(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_propositions(run_id=run_id)
    )


@app.get("/ops/legal-scopes")
def list_legal_scopes(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_legal_scopes(run_id=run_id)
    )


@app.get("/ops/proposition-scope-links")
def list_proposition_scope_links(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_proposition_scope_links(run_id=run_id)
    )


@app.get("/ops/legal-scopes/{scope_id}/propositions")
def list_scope_propositions(
    scope_id: str,
    run_id: str | None = None,
    include_descendants: bool = True,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_propositions_for_scope(
            scope_id,
            run_id=run_id,
            include_descendants=include_descendants,
        )
    )


@app.get("/ops/proposition-extraction-traces")
def list_proposition_extraction_traces(
    run_id: str | None = None,
    proposition_id: str | None = None,
    source_record_id: str | None = None,
    source_fragment_id: str | None = None,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_proposition_extraction_traces(
            run_id=run_id,
            proposition_id=proposition_id,
            source_record_id=source_record_id,
            source_fragment_id=source_fragment_id,
        )
    )


@app.get("/ops/proposition-completeness-assessments")
def list_proposition_completeness_assessments(
    run_id: str | None = None,
    proposition_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_proposition_completeness_assessments(
            run_id=run_id,
            proposition_id=proposition_id,
            status=status,
        )
    )


@app.get("/ops/effective/source-categorisation-rationales")
def list_effective_source_categorisation_rationales(
    run_id: str | None = None,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_effective_source_categorisation_rationales(
            run_id=run_id,
            source_record_id=source_record_id,
        )
    )


@app.get("/ops/effective/source-target-links")
def list_effective_source_target_links(
    run_id: str | None = None,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_effective_source_target_links(
            run_id=run_id,
            source_record_id=source_record_id,
        )
    )


@app.get("/ops/effective/proposition-extraction-traces")
def list_effective_proposition_extraction_traces(
    run_id: str | None = None,
    proposition_id: str | None = None,
    source_record_id: str | None = None,
    source_fragment_id: str | None = None,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_effective_proposition_extraction_traces(
            run_id=run_id,
            proposition_id=proposition_id,
            source_record_id=source_record_id,
            source_fragment_id=source_fragment_id,
        )
    )


@app.get("/ops/effective/propositions")
def list_effective_propositions(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_effective_propositions(run_id=run_id)
    )


@app.get("/ops/source-legal-effects")
def get_source_legal_effects(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().read_source_legal_effects(run_id=run_id)
    )


@app.get("/ops/decision-explanations")
def get_decision_explanations(run_id: str | None = None) -> dict[str, Any]:
    """Return the active run's decision_explanations artifact (soft-missing OK)."""
    return _with_operations_error_handling(
        lambda: _operations_store().read_decision_explanations(run_id=run_id)
    )


@app.get("/ops/heuristics")
def list_heuristics(
    run_id: str | None = None,
    referenced_only: bool = False,
) -> dict[str, Any]:
    """Return code-declared heuristic registry definitions (no heuristic execution)."""
    return _with_operations_error_handling(
        lambda: _operations_store().list_heuristic_definitions(
            run_id=run_id,
            referenced_only=referenced_only,
        )
    )


@app.get("/ops/proposition-groups")
def list_proposition_groups(
    run_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    confidence: str | None = Query(default=None),
    article: str | None = Query(default=None),
    search: str | None = Query(default=None),
    instrument_family: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_debug: bool = Query(default=False),
    include_coarse_parent_rows: bool = Query(default=False),
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_proposition_groups(
            run_id=run_id,
            scope=scope,
            source_id=source_id,
            review_status=review_status,
            confidence=confidence,
            article=article,
            search=search,
            instrument_family=instrument_family,
            limit=limit,
            offset=offset,
            include_debug=include_debug,
            include_coarse_parent_rows=include_coarse_parent_rows,
        )
    )


@app.get("/ops/proposition-groups/{group_id:path}")
def inspect_proposition_group_detail(
    group_id: str,
    run_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    confidence: str | None = Query(default=None),
    article: str | None = Query(default=None),
    search: str | None = Query(default=None),
    instrument_family: str | None = Query(default=None),
    include_coarse_parent_rows: bool = Query(default=False),
) -> dict[str, Any]:
    def _handler() -> dict[str, Any]:
        return _operations_store().inspect_proposition_group_detail(
            group_id,
            run_id=run_id,
            scope=scope,
            source_id=source_id,
            review_status=review_status,
            confidence=confidence,
            article=article,
            search=search,
            instrument_family=instrument_family,
            include_coarse_parent_rows=include_coarse_parent_rows,
        )

    try:
        return _handler()
    except OperationsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/ops/divergence-assessments")
def list_divergence_assessments(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_divergence_assessments(run_id=run_id)
    )


@app.get("/ops/run-quality-summary")
def get_run_quality_summary(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().read_run_quality_summary(run_id=run_id)
    )


@app.get("/ops/effective-law-statements")
def get_effective_law_statements(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().read_effective_law_statements(run_id=run_id)
    )


@app.get("/ops/proposition-matcher-law-candidates")
def get_proposition_matcher_law_candidates(run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().read_proposition_matcher_law_candidates(run_id=run_id)
    )


@app.get("/ops/propositions/{proposition_key}/history")
def inspect_proposition_history(
    proposition_key: str,
    include_runs: bool = True,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().proposition_history(
            proposition_key=proposition_key,
            include_runs=include_runs,
        )
    )


@app.get("/ops/divergence-findings/{finding_id}/history")
def inspect_divergence_history(
    finding_id: str,
    include_runs: bool = True,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().divergence_history(
            finding_id=finding_id,
            include_runs=include_runs,
        )
    )


@app.get("/ops/sources/{source_id}")
def inspect_source(source_id: str, run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().inspect_source_record(source_id=source_id, run_id=run_id)
    )


@app.get("/ops/sources/{source_id}/snapshots")
def inspect_source_snapshots(source_id: str, run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_source_snapshots(source_id=source_id, run_id=run_id)
    )


@app.get("/ops/sources/{source_id}/timeline")
def inspect_source_snapshot_timeline(source_id: str, run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().source_snapshot_timeline(source_id=source_id, run_id=run_id)
    )


@app.get("/ops/sources/{source_id}/history")
def inspect_source_snapshot_history(
    source_id: str,
    include_runs: bool = True,
    include_registry: bool = True,
) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().source_snapshot_history(
            source_id=source_id,
            include_runs=include_runs,
            include_registry=include_registry,
        )
    )


@app.get("/ops/sources/{source_id}/fragments")
def inspect_source_fragments(source_id: str, run_id: str | None = None) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_source_fragments(source_id=source_id, run_id=run_id)
    )


@app.get("/ops/source-registry")
def source_registry_list() -> dict[str, Any]:
    return _with_registry_error_handling(lambda: {"sources": _source_registry().list_entries()})


@app.get("/ops/source-registry/{registry_id}")
def source_registry_inspect(registry_id: str) -> dict[str, Any]:
    return _with_registry_error_handling(
        lambda: _source_registry().inspect_entry(registry_id=registry_id)
    )


@app.post("/ops/source-registry/register")
def source_registry_register(payload: SourceRegistryReferenceRequest) -> dict[str, Any]:
    return _with_registry_error_handling(
        lambda: _source_registry().register_reference(
            reference=payload.reference,
            refresh=payload.refresh,
        )
    )


@app.post("/ops/source-registry/search")
def source_registry_search(payload: SourceRegistrySearchRequest) -> dict[str, Any]:
    def _handler() -> dict[str, Any]:
        store = _source_registry().list_entries()
        return _source_search_service().search(
            query=payload.query,
            provider=payload.provider,
            limit=payload.limit,
            registry_entries=store,
        )

    return _with_source_search_error_handling(_handler)


@app.post("/ops/source-registry/{registry_id}/discover-related")
def source_registry_discover_related(registry_id: str) -> dict[str, Any]:
    return _with_registry_error_handling(
        lambda: discover_related_for_registry_entry(
            _source_registry().inspect_entry(registry_id=registry_id)
        )
    )


@app.post("/ops/source-registry/register-family-candidates")
def source_registry_register_family_candidates(
    payload: RegisterFamilyCandidatesRequest,
) -> dict[str, Any]:
    return _with_registry_error_handling(
        lambda: register_family_candidates(
            _source_registry(),
            target_registry_id=payload.target_registry_id,
            candidate_ids=payload.candidate_ids,
        )
    )


@app.post("/ops/source-registry/{registry_id}/refresh")
def source_registry_refresh(registry_id: str) -> dict[str, Any]:
    return _with_registry_error_handling(
        lambda: _source_registry().refresh_reference(registry_id=registry_id)
    )


@app.post("/ops/runs/from-registry")
def run_from_registry(payload: RegistryRunRequest) -> dict[str, Any]:
    def _handler() -> dict[str, Any]:
        use_llm, ext_mode, ext_fb, div_reason, focus_scopes, max_props, model_error_policy = (
            _resolve_registry_run_extraction(payload)
        )
        bundle = run_registry_sources(
            registry_ids=payload.registry_ids,
            topic_name=payload.topic_name,
            cluster_name=payload.cluster_name,
            analysis_mode=payload.analysis_mode,
            analysis_scope=payload.analysis_scope,
            refresh_sources=payload.refresh_sources,
            run_id=payload.run_id,
            run_notes=payload.run_notes,
            subject_tags=payload.subject_tags,
            comparison_jurisdiction_a=payload.comparison_jurisdiction_a,
            comparison_jurisdiction_b=payload.comparison_jurisdiction_b,
            proposition_index=payload.proposition_index,
            use_llm=use_llm,
            extraction_mode=ext_mode,
            extraction_fallback=ext_fb,
            divergence_reasoning=div_reason,
            source_registry_path=settings.source_registry_path,
            source_cache_dir=settings.source_cache_dir,
            derived_cache_dir=settings.derived_cache_dir,
            source_family_selection=payload.source_family_selection,
            focus_scopes=focus_scopes,
            max_propositions_per_source=max_props,
            model_error_policy=model_error_policy,
        )
        export_bundle(bundle, output_dir=settings.operations_export_dir)
        return bundle

    return _with_registry_error_handling(_handler)


@app.post("/ops/run-jobs/from-registry")
def create_registry_run_job(
    payload: RegistryRunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    job_id = new_job_id()
    store = _run_job_store()
    store.create_job(
        job_id=job_id,
        request_summary={
            "topic_name": payload.topic_name,
            "registry_ids": list(payload.registry_ids),
            "analysis_mode": payload.analysis_mode,
            "analysis_scope": payload.analysis_scope,
            "quality_run": payload.quality_run,
            "extraction_mode": payload.extraction_mode,
            "use_llm": payload.use_llm,
        },
    )
    background_tasks.add_task(_registry_run_job_worker, job_id, payload.model_dump(mode="json"))
    return {"job_id": job_id, "status": "queued"}


@app.post("/ops/run-jobs/compare-proposition-datasets")
def create_compare_proposition_datasets_job(
    payload: ComparePropositionDatasetsRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    job_id = new_job_id()
    store = _run_job_store()
    store.create_job(
        job_id=job_id,
        request_summary={
            "job_kind": "compare_proposition_datasets",
            "left_run_id": payload.left_run_id,
            "right_run_id": payload.right_run_id,
            "use_llm": payload.use_llm,
            "divergence_reasoning": payload.divergence_reasoning,
        },
    )
    background_tasks.add_task(
        _compare_proposition_datasets_job_worker, job_id, payload.model_dump(mode="json")
    )
    return {"job_id": job_id, "status": "queued"}


@app.post("/ops/run-jobs/equine-corpus")
def create_equine_corpus_run_job(
    payload: EquineCorpusRunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    try:
        cfg_path = _resolve_equine_corpus_config_for_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = new_job_id()
    store = _run_job_store()
    store.create_job(
        job_id=job_id,
        request_summary={
            "job_kind": "equine_corpus",
            "corpus_config_path": str(cfg_path),
            "corpus_id": str(payload.corpus_id or "equine_law"),
            "analysis_mode": "equine_corpus",
            "extraction_mode": payload.extraction_mode,
            "extraction_fallback": payload.extraction_fallback,
            "use_llm": payload.use_llm,
            "focus_scopes": payload.focus_scopes,
            "max_propositions_per_source": payload.max_propositions_per_source,
        },
    )
    background_tasks.add_task(
        _equine_corpus_run_job_worker, job_id, payload.model_dump(mode="json")
    )
    return {"job_id": job_id, "status": "queued"}


class OpsRepairExtractionRequest(BaseModel):
    """Repair extraction for an exported run. Prefer ``run_id``; ``export_dir`` is for local dev override."""

    export_dir: str | None = Field(default=None, min_length=1)
    run_id: str | None = Field(default=None, min_length=1)
    job_id: str | None = Field(default=None, min_length=1)
    output_dir: str | None = None
    retry_failed_llm: bool = True
    extraction_mode: Literal["frontier", "local"] = "frontier"
    extraction_fallback: Literal["fallback", "mark_needs_review", "fail_closed"] = "mark_needs_review"

    @model_validator(mode="after")
    def _require_target(self) -> OpsRepairExtractionRequest:
        if not self.export_dir and not self.run_id and not self.job_id:
            raise ValueError("Provide run_id, job_id, or export_dir (dev override).")
        return self


def _resolve_ops_repair_export_root(payload: OpsRepairExtractionRequest) -> Path:
    if payload.export_dir:
        return Path(payload.export_dir).expanduser().resolve()
    store = _operations_store()
    run_id: str | None = payload.run_id
    if payload.job_id:
        job = RunJobStore(Path(settings.operations_export_dir)).read_job(payload.job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Run job not found: {payload.job_id}")
        rid = job.get("run_id")
        run_id = str(rid).strip() if rid else run_id
        if not run_id:
            raise HTTPException(
                status_code=400,
                detail="Job has no run_id yet; pass run_id explicitly or wait until the job completes.",
            )
    if run_id:
        try:
            return store.resolve_run_export_dir(run_id)
        except OperationsError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail="Could not resolve export directory for repair.")


@app.post("/ops/run-jobs/repair-extraction")
def ops_run_jobs_repair_extraction(payload: OpsRepairExtractionRequest) -> dict[str, Any]:
    def _handler() -> dict[str, Any]:
        from law_proposition_extractor_pipeline.linting import load_exported_bundle, merge_export_root_mirror_into_run_bundle

        export_root = _resolve_ops_repair_export_root(payload)
        base_bundle = load_exported_bundle(str(export_root))
        base_bundle = merge_export_root_mirror_into_run_bundle(
            base_bundle, operations_export_root=settings.operations_export_dir
        )
        run_blob = base_bundle.get("run")
        base_run_id = str(run_blob.get("id")) if isinstance(run_blob, dict) else "unknown-run"

        output_raw = payload.output_dir
        if output_raw:
            out_path = Path(output_raw).expanduser().resolve()
        else:
            out_path = (export_root.parent / f"{export_root.name}-repaired").resolve()

        repaired = repair_extraction_from_export_dir(
            base_bundle=base_bundle,
            export_dir_abs=str(export_root),
            output_export_dir=out_path,
            new_run_id=f"{base_run_id}-repaired",
            extraction_mode=payload.extraction_mode,
            extraction_fallback=payload.extraction_fallback,
            only="repairable",
            in_place=False,
            retry_failed_extraction_cache=None,
            ignore_failed_extraction_cache=False,
            retry_failed_llm=payload.retry_failed_llm,
            source_cache_dir=settings.source_cache_dir,
            derived_cache_dir=settings.derived_cache_dir,
            use_llm=True,
            progress=None,
        )
        repaired_run = repaired.get("run")
        rid = repaired_run.get("id") if isinstance(repaired_run, dict) else None
        return {
            "run_id": rid,
            "output_dir": str(out_path),
            "extraction_repair_metadata": repaired.get("extraction_repair_metadata"),
        }

    try:
        return _handler()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/ops/run-jobs")
def list_run_jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: {"jobs": _operations_store().list_run_jobs(limit=limit)}
    )


@app.get("/ops/run-jobs/{job_id}")
def get_run_job(job_id: str) -> dict[str, Any]:
    return _with_operations_error_handling(lambda: {"job": _operations_store().get_run_job(job_id=job_id)})


@app.get("/ops/run-jobs/{job_id}/events")
def get_run_job_events(job_id: str) -> dict[str, Any]:
    return _with_operations_error_handling(
        lambda: _operations_store().list_run_job_events(job_id=job_id)
    )
