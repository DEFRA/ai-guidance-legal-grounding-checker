from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from law_proposition_extractor_domain import Cluster, Proposition, ReviewStatus, SourceRecord, Topic

from .derived_cache import DerivedArtifactCache
from .extract import (
    EXTRACTION_PROMPT_VERSION_V2,
    EXTRACTION_SCHEMA_VERSION_V2,
    ExtractSourceResult,
    _build_propositions_from_v2_rows,
    _heuristic_extraction,
    _merge_dedupe_validated_v2_rows,
    _parse_json,
    _parse_model_propositions_container,
    _stamp_props_meta,
    _validate_v2_items,
    extract_propositions_from_source,
    plan_frontier_extraction_requests,
    PlannedExtractionRequest,
)
from .intake import create_cluster, create_topic
from .source_fragmentation import expand_monolithic_source_fragment, max_fragment_body_chars_for_llm_budget
from .sources.service import SourceIngestionService


DEFAULT_ANTHROPIC_BATCH_MODEL = "claude-sonnet-4-5-20250929"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def resolve_anthropic_batch_model_id(model_alias: str) -> str:
    """Map a LiteLLM alias (e.g. frontier_extract) to an Anthropic Messages API model id."""
    override = os.getenv("JUDIT_ANTHROPIC_BATCH_MODEL", "").strip()
    if override:
        return override
    alias = str(model_alias or "").strip()
    if alias.startswith("claude-"):
        return alias
    if alias.startswith("anthropic/"):
        return alias.split("/", 1)[1]
    return DEFAULT_ANTHROPIC_BATCH_MODEL


@dataclass(frozen=True)
class FrontierBatchWorkItem:
    job_key: str
    work_source: SourceRecord


def _anthropic_result_text_by_request(rows: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        rid = str(row.get("custom_id") or "").strip()
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        message = result.get("message") if isinstance(result.get("message"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), list) else []
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and str(item.get("type") or "") == "text":
                text_parts.append(str(item.get("text") or ""))
        if rid and text_parts:
            out[rid] = "\n".join(text_parts).strip()
    return out


def _batch_status_detail(status: dict[str, Any]) -> str:
    counts = status.get("request_counts") if isinstance(status.get("request_counts"), dict) else {}
    processing = str(status.get("processing_status") or status.get("status") or "unknown")
    succeeded = counts.get("succeeded")
    errored = counts.get("errored")
    processing_n = counts.get("processing")
    total = status.get("request_count")
    parts = [f"status={processing}"]
    if total is not None:
        parts.append(f"total={total}")
    if succeeded is not None:
        parts.append(f"ok={succeeded}")
    if errored is not None:
        parts.append(f"err={errored}")
    if processing_n is not None:
        parts.append(f"in_flight={processing_n}")
    return ", ".join(parts)


def poll_anthropic_batch_until_ended(
    client: BatchLLMClient,
    batch_job_id: str,
    *,
    poll_interval_seconds: float = 30.0,
    on_status: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    while True:
        status = client.get_batch_status(batch_job_id)
        if on_status is not None:
            on_status(status)
        processing = str(status.get("processing_status") or "").lower()
        if processing in {"ended", "canceling", "canceled", "expired"}:
            return status
        time.sleep(max(1.0, poll_interval_seconds))


def parse_batch_results_jsonl(raw: str) -> list[dict[str, Any]]:
    """Parse Anthropic Message Batch results (.jsonl — one JSON object per line)."""
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Anthropic batch results JSONL parse failed at line {line_no}: {exc}"
            ) from exc
        if isinstance(item, dict):
            rows.append(item)
    return rows


def load_batch_results_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return parse_batch_results_jsonl(Path(path).read_text(encoding="utf-8"))


class BatchLLMClient(Protocol):
    def submit_batch(self, requests: list[PlannedExtractionRequest]) -> str: ...

    def get_batch_status(self, batch_job_id: str) -> dict[str, Any]: ...

    def fetch_batch_results(self, batch_job_id: str) -> list[dict[str, Any]]: ...


class AnthropicBatchLLMClient:
    """Small adapter around Anthropic Message Batches API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base_url: str = "https://api.anthropic.com/v1",
        anthropic_version: str = "2023-06-01",
    ) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.api_base_url = api_base_url.rstrip("/")
        self.anthropic_version = anthropic_version

    def _request_json(self, *, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = self._request_text(path=path, method=method, payload=payload)
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Anthropic response payload.")
        return data

    def _request_text(self, *, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> str:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic batch execution.")
        body = None
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
        }
        if payload is not None:
            headers["content-type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.api_base_url}{path}",
            method=method,
            headers=headers,
            data=body,
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic batch API error ({exc.code}): {err}") from exc

    def _request(self, *, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request_json(path=path, method=method, payload=payload)

    def submit_batch(self, requests: list[PlannedExtractionRequest]) -> str:
        entries: list[dict[str, Any]] = []
        for req in requests:
            provider_model = resolve_anthropic_batch_model_id(req.model_alias)
            entries.append(
                {
                    "custom_id": req.request_id,
                    "params": {
                        "model": provider_model,
                        "max_tokens": 4096,
                        "system": req.system_text or "",
                        "messages": [{"role": "user", "content": req.prompt_text}],
                        "temperature": 0.0,
                    },
                }
            )
        payload = self._request(path="/messages/batches", method="POST", payload={"requests": entries})
        batch_id = str(payload.get("id") or "").strip()
        if not batch_id:
            raise RuntimeError("Anthropic batch submission did not return id.")
        return batch_id

    def get_batch_status(self, batch_job_id: str) -> dict[str, Any]:
        return self._request(path=f"/messages/batches/{batch_job_id}")

    def fetch_batch_results(self, batch_job_id: str) -> list[dict[str, Any]]:
        raw = self._request_text(path=f"/messages/batches/{batch_job_id}/results")
        return parse_batch_results_jsonl(raw)


@dataclass
class BatchImportResult:
    propositions: list[Proposition]
    validation_errors: list[str]
    validation_issue_records: list[dict[str, Any]]
    extraction_llm_call_traces: list[dict[str, Any]]
    failed_result_count: int


@dataclass
class PlannedBatchCase:
    topic: Topic
    cluster: Cluster
    requests: list[PlannedExtractionRequest]
    source_by_request_id: dict[str, SourceRecord]
    source_count: int
    fragment_count: int


class BatchJobStore:
    def __init__(self, export_dir: str | Path) -> None:
        self.root = Path(export_dir) / "runs" / "_batch_jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, batch_job_id: str) -> Path:
        return self.root / str(batch_job_id)

    def write_job(
        self,
        *,
        batch_job_id: str,
        metadata: dict[str, Any],
        requests: list[PlannedExtractionRequest],
    ) -> None:
        jd = self.job_dir(batch_job_id)
        jd.mkdir(parents=True, exist_ok=True)
        (jd / "batch_job.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (jd / "requests.json").write_text(
            json.dumps([asdict(item) for item in requests], indent=2), encoding="utf-8"
        )

    def write_results(self, *, batch_job_id: str, results: list[dict[str, Any]]) -> None:
        jd = self.job_dir(batch_job_id)
        jd.mkdir(parents=True, exist_ok=True)
        (jd / "results.jsonl").write_text(
            "\n".join(json.dumps(item, sort_keys=True) for item in results),
            encoding="utf-8",
        )

    def write_results_raw(self, *, batch_job_id: str, raw_jsonl: str) -> Path:
        jd = self.job_dir(batch_job_id)
        jd.mkdir(parents=True, exist_ok=True)
        path = jd / "results.raw.jsonl"
        path.write_text(raw_jsonl, encoding="utf-8")
        return path

    def read_results_if_present(self, batch_job_id: str) -> list[dict[str, Any]] | None:
        jd = self.job_dir(batch_job_id)
        for name in ("results.jsonl", "results.raw.jsonl"):
            path = jd / name
            if path.is_file() and path.stat().st_size > 0:
                return load_batch_results_jsonl(path)
        return None

    def read_batch_metadata(self, batch_job_id: str) -> dict[str, Any] | None:
        path = self.job_dir(batch_job_id) / "batch_job.json"
        if not path.is_file():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None

    def write_errors(self, *, batch_job_id: str, errors: list[dict[str, Any]]) -> None:
        jd = self.job_dir(batch_job_id)
        jd.mkdir(parents=True, exist_ok=True)
        (jd / "errors.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")


def plan_frontier_batch_for_source(
    *,
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    model_alias: str,
    max_propositions: int,
    focus_scopes: list[str] | None,
    prompt_version: str,
    max_input_tokens: int,
    extract_model_context_limit: int,
    derived_chunk_cache: DerivedArtifactCache | None,
    chunk_cache_pipeline_version: str,
    chunk_cache_strategy_version: str,
) -> list[PlannedExtractionRequest]:
    return plan_frontier_extraction_requests(
        source=source,
        topic=topic,
        cluster=cluster,
        model_alias=model_alias,
        max_propositions=max_propositions,
        focus_scopes=focus_scopes,
        prompt_version=prompt_version,
        schema_version=EXTRACTION_SCHEMA_VERSION_V2,
        max_input_tokens=max_input_tokens,
        extract_model_context_limit=extract_model_context_limit,
        derived_chunk_cache=derived_chunk_cache,
        chunk_cache_pipeline_version=chunk_cache_pipeline_version,
        chunk_cache_strategy_version=chunk_cache_strategy_version,
        include_cached_successes=False,
    )


def plan_frontier_batch_for_case(
    *,
    case_data: dict[str, Any],
    model_alias: str,
    source_cache_dir: str | None = None,
    derived_cache_dir: str | None = None,
    max_input_tokens: int = 150_000,
    extract_model_context_limit: int = 200_000,
    prompt_version: str = "v2",
    chunk_cache_pipeline_version: str = "0.1.0",
    chunk_cache_strategy_version: str = "v1",
) -> PlannedBatchCase:
    topic_cfg = case_data["topic"]
    cluster_cfg = case_data["cluster"]
    topic = create_topic(
        name=topic_cfg["name"],
        description=topic_cfg.get("description", ""),
        subject_tags=topic_cfg.get("subject_tags", []),
    )
    cluster = create_cluster(
        topic=topic,
        name=cluster_cfg["name"],
        description=cluster_cfg.get("description", ""),
    )
    extraction_cfg = case_data.get("extraction") if isinstance(case_data.get("extraction"), dict) else {}
    scopes_raw = extraction_cfg.get("focus_scopes") if isinstance(extraction_cfg, dict) else None
    focus_scopes = [str(item).strip() for item in scopes_raw or [] if str(item).strip()]
    max_props = extraction_cfg.get("max_propositions_per_source") if isinstance(extraction_cfg, dict) else None
    max_propositions = int(max_props) if isinstance(max_props, int) and max_props > 0 else 4
    ingest = SourceIngestionService(cache_dir=Path(source_cache_dir) if source_cache_dir else None)
    intake = ingest.ingest_sources(case_data.get("sources") or [])
    max_body = max_fragment_body_chars_for_llm_budget(max_extract_input_tokens=max_input_tokens)
    overlap = min(8192, max(512, max_input_tokens // 40))
    derived_cache = (
        DerivedArtifactCache(cache_dir=Path(derived_cache_dir))
        if derived_cache_dir
        else None
    )
    requests: list[PlannedExtractionRequest] = []
    source_by_request_id: dict[str, SourceRecord] = {}
    expanded_count = 0
    by_record = {s.id: s for s in intake.sources}
    for frag in intake.fragments:
        expanded = expand_monolithic_source_fragment(
            frag,
            max_body_chars=max_body,
            overlap_chars=overlap,
        )
        for piece in expanded:
            expanded_count += 1
            src = by_record[piece.source_record_id]
            metadata = dict(src.metadata) if isinstance(src.metadata, dict) else {}
            metadata["extraction_fragment_id"] = piece.id
            work = src.model_copy(
                deep=True,
                update={
                    "authoritative_text": piece.fragment_text,
                    "authoritative_locator": piece.locator,
                    "metadata": metadata,
                },
            )
            planned = plan_frontier_batch_for_source(
                source=work,
                topic=topic,
                cluster=cluster,
                model_alias=model_alias,
                max_propositions=max_propositions,
                focus_scopes=focus_scopes or None,
                prompt_version=prompt_version,
                max_input_tokens=max_input_tokens,
                extract_model_context_limit=extract_model_context_limit,
                derived_chunk_cache=derived_cache,
                chunk_cache_pipeline_version=chunk_cache_pipeline_version,
                chunk_cache_strategy_version=chunk_cache_strategy_version,
            )
            requests.extend(planned)
            for req in planned:
                source_by_request_id[req.request_id] = work
    return PlannedBatchCase(
        topic=topic,
        cluster=cluster,
        requests=requests,
        source_by_request_id=source_by_request_id,
        source_count=len(intake.sources),
        fragment_count=expanded_count,
    )


def import_frontier_batch_results(
    *,
    requests: list[PlannedExtractionRequest],
    provider_results: dict[str, str],
    source_by_request_id: dict[str, SourceRecord],
    topic: Topic,
    cluster: Cluster,
    extraction_fallback: str,
    derived_chunk_cache: DerivedArtifactCache | None = None,
) -> BatchImportResult:
    all_props: list[Proposition] = []
    valerrs: list[str] = []
    issue_records: list[dict[str, Any]] = []
    llm_traces: list[dict[str, Any]] = []
    failed = 0
    for req in requests:
        source = source_by_request_id[req.request_id]
        raw_text = provider_results.get(req.request_id, "")
        trace: dict[str, Any] = {
            "source_record_id": req.source_record_id,
            "source_title": req.source_title,
            "source_fragment_id": req.source_fragment_id,
            "fragment_locator": req.fragment_locator,
            "model_alias": req.model_alias,
            "estimated_input_tokens": req.estimated_input_tokens,
            "llm_invoked": True,
            "batch_request_id": req.request_id,
            "provider_status": "ok" if raw_text else "missing_result",
        }
        llm_traces.append(trace)
        if not raw_text:
            failed += 1
            valerrs.append(f"batch request {req.request_id}: missing provider result")
            continue
        try:
            parsed = _parse_json(raw_text)
            rows = _parse_model_propositions_container(parsed)
        except Exception as exc:
            failed += 1
            valerrs.append(f"batch request {req.request_id}: invalid JSON payload ({exc})")
            continue
        v_rows, verrs, row_issues = _validate_v2_items(rows, source.authoritative_text, limit=req.max_propositions_per_source)
        if not v_rows:
            failed += 1
        valerrs.extend([f"batch request {req.request_id}: {x}" for x in verrs])
        issue_records.extend(row_issues)
        deduped = _merge_dedupe_validated_v2_rows(v_rows, limit=req.max_propositions_per_source)
        if req.cache_key and derived_chunk_cache is not None and deduped:
            derived_chunk_cache.put(
                stage_name="proposition_extraction_chunk",
                cache_key=req.cache_key,
                payload={"chunk_status": "llm_success", "validated_rows": deduped},
            )
        props = _build_propositions_from_v2_rows(
            rows=deduped,
            source=source,
            topic=topic,
            cluster=cluster,
            limit=req.max_propositions_per_source,
            id_sequence_start=1,
        )
        _stamp_props_meta(
            props,
            extraction_mode="frontier",
            model_alias=req.model_alias,
            fallback_policy=extraction_fallback,
            fallback_used=False,
            validation_errors=verrs,
            prompt_version=req.prompt_version,
            schema_version=req.schema_version,
            pipeline_signals={
                "focus_scopes": req.focus_scopes,
                "batch_request_id": req.request_id,
                "estimated_input_tokens": req.estimated_input_tokens,
                "extraction_llm_call_traces": [trace],
            },
        )
        all_props.extend(props)
    return BatchImportResult(
        propositions=all_props,
        validation_errors=valerrs,
        validation_issue_records=issue_records,
        extraction_llm_call_traces=llm_traces,
        failed_result_count=failed,
    )


def _process_batch_chunk(
    *,
    req: PlannedExtractionRequest,
    raw_text: str,
    source: SourceRecord,
    derived_chunk_cache: DerivedArtifactCache | None,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], dict[str, Any], str]:
    """Returns (deduped_rows, valerrs, issue_records, trace, status).

    status is one of: ``ok`` (usable rows), ``empty_success`` (valid model response with no
    items — e.g. a repealed/omitted fragment), or ``failed`` (missing result, invalid JSON, or
    items returned that all failed validation).
    """
    meta = req.metadata if isinstance(req.metadata, dict) else {}
    trace: dict[str, Any] = {
        "source_record_id": req.source_record_id,
        "source_title": req.source_title,
        "source_fragment_id": req.source_fragment_id,
        "fragment_locator": req.fragment_locator,
        "model_alias": req.model_alias,
        "estimated_input_tokens": req.estimated_input_tokens,
        "llm_invoked": True,
        "llm_call_attempted": True,
        "llm_call_succeeded": bool(raw_text),
        "batch_request_id": req.request_id,
        "extraction_execution_mode": "batch",
        "extraction_llm_chunk_index": meta.get("chunk_index"),
        "extraction_llm_chunk_total": meta.get("chunk_total"),
        "extraction_chunk_split_strategy": meta.get("split_strategy"),
        "provider_status": "ok" if raw_text else "missing_result",
    }
    if not raw_text:
        return [], [f"batch request {req.request_id}: missing provider result"], [], trace, "failed"
    try:
        parsed = _parse_json(raw_text)
        rows = _parse_model_propositions_container(parsed)
    except Exception as exc:
        return [], [f"batch request {req.request_id}: invalid JSON payload ({exc})"], [], trace, "failed"
    v_rows, verrs, row_issues = _validate_v2_items(
        rows, source.authoritative_text, limit=req.max_propositions_per_source
    )
    valerrs = [f"batch request {req.request_id}: {x}" for x in verrs]
    if not v_rows:
        # Valid response with no usable rows: empty-success when the model returned no items
        # (genuinely nothing to extract), failed when items were returned but all rejected.
        return [], valerrs, row_issues, trace, ("failed" if rows else "empty_success")
    deduped = _merge_dedupe_validated_v2_rows(v_rows, limit=req.max_propositions_per_source)
    if req.cache_key and derived_chunk_cache is not None and deduped:
        derived_chunk_cache.put(
            stage_name="proposition_extraction_chunk",
            cache_key=req.cache_key,
            payload={"chunk_status": "llm_success", "validated_rows": deduped},
        )
    return deduped, valerrs, row_issues, trace, "ok"


def import_frontier_batch_results_by_job(
    *,
    requests: list[PlannedExtractionRequest],
    provider_results: dict[str, str],
    source_by_request_id: dict[str, SourceRecord],
    work_items_by_key: dict[str, FrontierBatchWorkItem],
    topic: Topic,
    cluster: Cluster,
    extraction_fallback: str,
    derived_chunk_cache: DerivedArtifactCache | None = None,
    prompt_version: str = EXTRACTION_PROMPT_VERSION_V2,
) -> dict[str, ExtractSourceResult]:
    by_job: dict[str, list[PlannedExtractionRequest]] = defaultdict(list)
    for req in requests:
        meta = req.metadata if isinstance(req.metadata, dict) else {}
        job_key = str(meta.get("job_key") or "").strip()
        if job_key:
            by_job[job_key].append(req)

    outcomes: dict[str, ExtractSourceResult] = {}
    base_kwargs = dict(
        extraction_mode="frontier",
        fallback_policy=extraction_fallback,
        prompt_version=prompt_version,
        schema_version=EXTRACTION_SCHEMA_VERSION_V2,
    )

    for job_key, item in work_items_by_key.items():
        job_reqs = by_job.get(job_key, [])
        source = item.work_source
        model_alias = job_reqs[0].model_alias if job_reqs else None
        aggregated: list[dict[str, Any]] = []
        valerrs: list[str] = []
        issue_records: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []
        hard_failures = 0

        for req in sorted(job_reqs, key=lambda r: int((r.metadata or {}).get("chunk_index") or 0)):
            raw = provider_results.get(req.request_id, "")
            deduped, verrs, row_issues, trace, status = _process_batch_chunk(
                req=req,
                raw_text=raw,
                source=source_by_request_id.get(req.request_id, source),
                derived_chunk_cache=derived_chunk_cache,
            )
            traces.append(trace)
            valerrs.extend(verrs)
            issue_records.extend(row_issues)
            if status == "failed":
                hard_failures += 1
            aggregated.extend(deduped)

        merged = _merge_dedupe_validated_v2_rows(
            aggregated,
            limit=job_reqs[0].max_propositions_per_source if job_reqs else 4,
        )

        # Every chunk returned a valid (possibly empty) response with nothing extractable — a
        # legitimately empty fragment (e.g. repealed/omitted provision). Emit zero propositions
        # rather than falling back to heuristic noise.
        if not merged and hard_failures == 0:
            outcomes[job_key] = ExtractSourceResult(
                propositions=[],
                model_alias=model_alias,
                fallback_used=False,
                validation_errors=valerrs,
                validation_issue_records=issue_records,
                extraction_llm_call_traces=traces,
                **base_kwargs,
            )
            continue

        if not merged and hard_failures and extraction_fallback == "fail_closed":
            outcomes[job_key] = ExtractSourceResult(
                propositions=[],
                model_alias=model_alias,
                fallback_used=False,
                validation_errors=valerrs,
                failed_closed=True,
                failure_reason="batch extraction produced no valid rows",
                validation_issue_records=issue_records,
                extraction_llm_call_traces=traces,
                **base_kwargs,
            )
            continue

        if not merged and extraction_fallback == "mark_needs_review":
            props = _heuristic_extraction(
                source=source,
                topic=topic,
                cluster=cluster,
                limit=job_reqs[0].max_propositions_per_source if job_reqs else 4,
            )
            for prop in props:
                prop.review_status = ReviewStatus.NEEDS_REVIEW
            fallback_kwargs = {**base_kwargs, "schema_version": "none"}
            _stamp_props_meta(
                props,
                model_alias=model_alias,
                fallback_used=True,
                validation_errors=valerrs,
                pipeline_signals={"extraction_llm_call_traces": traces, "extraction_execution_mode": "batch"},
                **fallback_kwargs,
            )
            outcomes[job_key] = ExtractSourceResult(
                propositions=props,
                model_alias=model_alias,
                fallback_used=True,
                validation_errors=valerrs,
                validation_issue_records=issue_records,
                extraction_llm_call_traces=traces,
                fallback_strategy="heuristic_fallback",
                **fallback_kwargs,
            )
            continue

        if not merged:
            props = _heuristic_extraction(
                source=source,
                topic=topic,
                cluster=cluster,
                limit=job_reqs[0].max_propositions_per_source if job_reqs else 4,
            )
            fallback_kwargs = {**base_kwargs, "schema_version": "none"}
            _stamp_props_meta(
                props,
                model_alias=model_alias,
                fallback_used=True,
                validation_errors=valerrs,
                pipeline_signals={"extraction_llm_call_traces": traces, "extraction_execution_mode": "batch"},
                **fallback_kwargs,
            )
            outcomes[job_key] = ExtractSourceResult(
                propositions=props,
                model_alias=model_alias,
                fallback_used=True,
                validation_errors=valerrs,
                validation_issue_records=issue_records,
                extraction_llm_call_traces=traces,
                fallback_strategy="heuristic_fallback",
                **fallback_kwargs,
            )
            continue

        props = _build_propositions_from_v2_rows(
            rows=merged,
            source=source,
            topic=topic,
            cluster=cluster,
            limit=job_reqs[0].max_propositions_per_source if job_reqs else 4,
        )
        pipe_flags: dict[str, Any] = {"extraction_execution_mode": "batch"}
        if traces:
            pipe_flags["extraction_llm_call_traces"] = traces
            ests = [
                int(t["estimated_input_tokens"])
                for t in traces
                if isinstance(t.get("estimated_input_tokens"), int) and int(t["estimated_input_tokens"]) > 0
            ]
            if ests:
                pipe_flags["estimated_input_tokens_max"] = max(ests)
        _stamp_props_meta(
            props,
            model_alias=model_alias,
            fallback_used=False,
            validation_errors=[e for e in valerrs if e],
            pipeline_signals=pipe_flags,
            **base_kwargs,
        )
        outcomes[job_key] = ExtractSourceResult(
            propositions=props,
            model_alias=model_alias,
            fallback_used=False,
            validation_errors=[e for e in valerrs if e],
            validation_issue_records=issue_records,
            extraction_llm_call_traces=traces,
            **base_kwargs,
        )
    return outcomes


def run_frontier_extraction_batch(
    *,
    work_items: list[FrontierBatchWorkItem],
    topic: Topic,
    cluster: Cluster,
    model_alias: str,
    max_propositions: int,
    focus_scopes: list[str] | None,
    extraction_fallback: str,
    prompt_version: str,
    max_input_tokens: int,
    extract_model_context_limit: int,
    derived_chunk_cache: DerivedArtifactCache | None,
    chunk_cache_pipeline_version: str,
    chunk_cache_strategy_version: str,
    llm_client: Any | None = None,
    retry_failed_llm: bool = False,
    batch_client: BatchLLMClient | None = None,
    poll_interval_seconds: float = 30.0,
    on_batch_status: Callable[[dict[str, Any]], None] | None = None,
    store: BatchJobStore | None = None,
    store_batch_job_id: str | None = None,
) -> dict[str, ExtractSourceResult]:
    """Plan, submit, poll, and import frontier extraction via Anthropic Message Batches."""
    work_by_key = {item.job_key: item for item in work_items}
    all_requests: list[PlannedExtractionRequest] = []
    source_by_request_id: dict[str, SourceRecord] = {}
    cache_only_keys: list[str] = []

    for item in work_items:
        planned = plan_frontier_extraction_requests(
            source=item.work_source,
            topic=topic,
            cluster=cluster,
            model_alias=model_alias,
            max_propositions=max_propositions,
            focus_scopes=focus_scopes,
            prompt_version=prompt_version,
            schema_version=EXTRACTION_SCHEMA_VERSION_V2,
            max_input_tokens=max_input_tokens,
            extract_model_context_limit=extract_model_context_limit,
            derived_chunk_cache=derived_chunk_cache,
            chunk_cache_pipeline_version=chunk_cache_pipeline_version,
            chunk_cache_strategy_version=chunk_cache_strategy_version,
            include_cached_successes=False,
        )
        if not planned:
            cache_only_keys.append(item.job_key)
            continue
        for req in planned:
            tagged = replace(req, metadata={**req.metadata, "job_key": item.job_key})
            all_requests.append(tagged)
            source_by_request_id[tagged.request_id] = item.work_source

    outcomes: dict[str, ExtractSourceResult] = {}

    if cache_only_keys and llm_client is not None:
        for job_key in cache_only_keys:
            item = work_by_key[job_key]
            outcomes[job_key] = extract_propositions_from_source(
                source=item.work_source,
                topic=topic,
                cluster=cluster,
                llm_client=llm_client,
                limit=max_propositions,
                extraction_mode="frontier",
                extraction_fallback=extraction_fallback,  # type: ignore[arg-type]
                prompt_version=prompt_version,
                focus_scopes=focus_scopes,
                derived_chunk_cache=derived_chunk_cache,
                retry_failed_llm=retry_failed_llm,
                chunk_cache_pipeline_version=chunk_cache_pipeline_version,
                chunk_cache_strategy_version=chunk_cache_strategy_version,
            )

    if not all_requests:
        return outcomes

    client = batch_client or AnthropicBatchLLMClient()
    provider_batch_id: str | None = None
    rows: list[dict[str, Any]] | None = None

    if store is not None and store_batch_job_id:
        rows = store.read_results_if_present(store_batch_job_id)
        if rows:
            if on_batch_status is not None:
                on_batch_status(
                    {
                        "processing_status": "ended",
                        "resumed_from_cache": True,
                        "result_count": len(rows),
                    }
                )
        else:
            meta = store.read_batch_metadata(store_batch_job_id)
            if meta is not None:
                provider_batch_id = str(meta.get("provider_batch_job_id") or "").strip() or None

    if rows is None:
        if not provider_batch_id:
            provider_batch_id = client.submit_batch(all_requests)
            if store is not None and store_batch_job_id:
                store.write_job(
                    batch_job_id=store_batch_job_id,
                    metadata={
                        "batch_job_id": store_batch_job_id,
                        "provider_batch_job_id": provider_batch_id,
                        "status": "submitted",
                        "provider": "anthropic",
                        "model_alias": model_alias,
                        "provider_model_id": resolve_anthropic_batch_model_id(model_alias),
                        "request_count": len(all_requests),
                        "estimated_input_tokens_total": sum(
                            r.estimated_input_tokens for r in all_requests
                        ),
                        "submitted_at": _utc_now_iso(),
                    },
                    requests=all_requests,
                )
        elif store is not None and store_batch_job_id:
            # Resume path: reload planned requests if the store has them.
            req_path = store.job_dir(store_batch_job_id) / "requests.json"
            if req_path.is_file() and not all_requests:
                req_rows = json.loads(req_path.read_text(encoding="utf-8"))
                all_requests = [
                    PlannedExtractionRequest(**row) for row in req_rows if isinstance(row, dict)
                ]

        def _status_cb(status: dict[str, Any]) -> None:
            if on_batch_status is not None:
                on_batch_status(status)

        assert provider_batch_id is not None
        final_status = poll_anthropic_batch_until_ended(
            client,
            provider_batch_id,
            poll_interval_seconds=poll_interval_seconds,
            on_status=_status_cb,
        )
        raw_jsonl = client._request_text(path=f"/messages/batches/{provider_batch_id}/results")
        if store is not None and store_batch_job_id:
            store.write_results_raw(batch_job_id=store_batch_job_id, raw_jsonl=raw_jsonl)
        rows = parse_batch_results_jsonl(raw_jsonl)
        if store is not None and store_batch_job_id:
            store.write_results(batch_job_id=store_batch_job_id, results=rows)
            meta_path = store.job_dir(store_batch_job_id) / "batch_job.json"
            meta: dict[str, Any] = store.read_batch_metadata(store_batch_job_id) or {}
            meta.update(
                {
                    "status": "results_available",
                    "provider_status": final_status.get("processing_status"),
                    "result_count": len(rows),
                    "completed_at": _utc_now_iso(),
                }
            )
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    assert rows is not None
    if store is not None and store_batch_job_id and not (
        store.job_dir(store_batch_job_id) / "results.jsonl"
    ).is_file():
        store.write_results(batch_job_id=store_batch_job_id, results=rows)

    provider_results = _anthropic_result_text_by_request(rows)
    batch_outcomes = import_frontier_batch_results_by_job(
        requests=all_requests,
        provider_results=provider_results,
        source_by_request_id=source_by_request_id,
        work_items_by_key=work_by_key,
        topic=topic,
        cluster=cluster,
        extraction_fallback=extraction_fallback,
        derived_chunk_cache=derived_chunk_cache,
        prompt_version=prompt_version,
    )
    outcomes.update(batch_outcomes)
    return outcomes
