"""Persistent pipeline run jobs + API-facing progress events (additive)."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from .cli_run_summary import (
    count_extraction_fallback_traces,
    count_low_confidence_extraction_traces,
)
from .extraction_llm_metrics import (
    compute_extraction_llm_trace_summary_metrics,
    extraction_llm_call_traces_from_bundle,
)

ProgressStage = Literal[
    "loading_case",
    "source_intake",
    "source_parsing",
    "source_fragmentation",
    "proposition_extraction",
    "proposition_inventory",
    "divergence_comparison",
    "scope_linking",
    "completeness_assessment",
    "export_bundle",
    "run_quality",
    "done",
]

JobStatus = Literal["queued", "running", "pass", "warning", "fail", "cancelled"]

EventStatus = Literal["pending", "running", "pass", "warning", "fail", "skipped"]


def _utc_now_iso_z() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _stage_from_title(title: str) -> ProgressStage | None:
    t = title.strip()
    mapping: list[tuple[str, ProgressStage]] = [
        ("Loading case", "loading_case"),
        ("Source intake", "source_intake"),
        ("Source parsing", "source_parsing"),
        ("Source fragmentation", "source_fragmentation"),
        ("Proposition extraction", "proposition_extraction"),
        ("Proposition inventory", "proposition_inventory"),
        ("Divergence comparison", "divergence_comparison"),
        ("Scope linking", "scope_linking"),
        ("Completeness assessment", "completeness_assessment"),
        ("Export bundle", "export_bundle"),
        ("Lint / quality summary", "run_quality"),
    ]
    for prefix, slug in mapping:
        if t == prefix or t.startswith(prefix):
            return slug
    return None


def _job_dir(export_dir: Path, job_id: str) -> Path:
    return export_dir / "runs" / "_jobs" / job_id


@dataclass
class RunJobStore:
    """Filesystem persistence under ``export_dir/runs/_jobs/{job_id}/``."""

    export_dir: Path
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _ensure_job_dir(self, job_id: str) -> Path:
        d = _job_dir(self.export_dir, job_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create_job(
        self,
        *,
        job_id: str,
        request_summary: dict[str, Any],
    ) -> dict[str, Any]:
        now = _utc_now_iso_z()
        job: dict[str, Any] = {
            "id": job_id,
            "requested_at": now,
            "started_at": None,
            "finished_at": None,
            "status": "queued",
            "run_id": None,
            "request_summary": request_summary,
            "current_stage": None,
            "progress_message": None,
            "event_count": 0,
            "metrics": {
                "source_count": 0,
                "fragment_count": 0,
                "proposition_count": 0,
                "llm_extraction_call_count": 0,
                "llm_extraction_skipped_count": 0,
                "max_estimated_input_tokens": None,
                "fallback_count": 0,
                "low_confidence_count": 0,
                "warning_count": 0,
                "error_count": 0,
                "context_window_risk_count": 0,
            },
        }
        with self._lock:
            self._ensure_job_dir(job_id)
            self._write_json_atomic(_job_dir(self.export_dir, job_id) / "job.json", job)
            self._write_json_atomic(_job_dir(self.export_dir, job_id) / "events.json", {"events": []})
        return job

    def read_job(self, job_id: str) -> dict[str, Any] | None:
        path = _job_dir(self.export_dir, job_id) / "job.json"
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def read_events(self, job_id: str) -> list[dict[str, Any]]:
        path = _job_dir(self.export_dir, job_id) / "events.json"
        if not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            ev = raw.get("events") if isinstance(raw, dict) else None
            if not isinstance(ev, list):
                return []
            return [e for e in ev if isinstance(e, dict)]
        except (json.JSONDecodeError, OSError):
            return []

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        root = self.export_dir / "runs" / "_jobs"
        if not root.is_dir():
            return []
        rows: list[tuple[str, dict[str, Any]]] = []
        for child in root.iterdir():
            if not child.is_dir():
                continue
            job = self.read_job(child.name)
            if job:
                rows.append((str(job.get("requested_at") or ""), job))
        rows.sort(key=lambda x: (x[0], x[1].get("id", "")), reverse=True)
        return [r[1] for r in rows[:limit]]

    def update_job(self, job_id: str, patch: dict[str, Any]) -> None:
        with self._lock:
            cur = self.read_job(job_id)
            if not cur:
                return
            cur.update(patch)
            self._write_json_atomic(_job_dir(self.export_dir, job_id) / "job.json", cur)

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            path = _job_dir(self.export_dir, job_id) / "events.json"
            if not path.parent.is_dir():
                path.parent.mkdir(parents=True, exist_ok=True)
            existing = self.read_events(job_id)
            existing.append(event)
            self._write_json_atomic(path, {"events": existing})
            jpath = _job_dir(self.export_dir, job_id) / "job.json"
            job = self.read_job(job_id)
            if job:
                job["event_count"] = len(existing)
                self._write_json_atomic(jpath, job)

    def merge_job(self, job_id: str, mutator: Any) -> None:
        with self._lock:
            job = self.read_job(job_id)
            if not job:
                return
            mutator(job)
            self._write_json_atomic(_job_dir(self.export_dir, job_id) / "job.json", job)

    @staticmethod
    def _write_json_atomic(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)


def new_job_id() -> str:
    return str(uuid.uuid4())


def new_event_id() -> str:
    return str(uuid.uuid4())


def job_metrics_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Populate job ``metrics`` from a completed export bundle."""
    rq = bundle.get("run_quality_summary") if isinstance(bundle.get("run_quality_summary"), dict) else {}
    metrics_rq = rq.get("metrics") if isinstance(rq.get("metrics"), dict) else {}
    traces = extraction_llm_call_traces_from_bundle(bundle)
    ext_summary = compute_extraction_llm_trace_summary_metrics(traces)
    low_conf = count_low_confidence_extraction_traces(bundle)
    src_n = len(bundle.get("source_records") or bundle.get("sources") or [])
    frag_n = len(bundle.get("source_fragments") or [])
    prop_n = len(bundle.get("propositions") or [])
    fb = count_extraction_fallback_traces(bundle)
    return {
        "source_count": int(rq.get("source_count") or src_n),
        "fragment_count": int(rq.get("fragment_count") or frag_n),
        "proposition_count": int(rq.get("proposition_count") or prop_n),
        "llm_extraction_call_count": int(
            metrics_rq.get("llm_extraction_call_count") or ext_summary.get("llm_extraction_call_count") or 0
        ),
        "llm_extraction_skipped_count": int(
            metrics_rq.get("llm_extraction_skipped_count")
            or ext_summary.get("llm_extraction_skipped_count")
            or 0
        ),
        "max_estimated_input_tokens": metrics_rq.get("max_estimated_input_tokens")
        if metrics_rq.get("max_estimated_input_tokens") is not None
        else ext_summary.get("max_estimated_input_tokens"),
        "fallback_count": fb,
        "low_confidence_count": low_conf,
        "warning_count": int(rq.get("warning_count") or 0),
        "error_count": int(rq.get("error_count") or 0),
        "context_window_risk_count": int(
            metrics_rq.get("context_window_risk_count")
            or ext_summary.get("context_window_risk_count")
            or 0
        ),
    }


def terminal_job_status_from_run_quality(bundle: dict[str, Any]) -> JobStatus:
    rq = bundle.get("run_quality_summary") if isinstance(bundle.get("run_quality_summary"), dict) else {}
    st = str(rq.get("status") or "").strip().lower()
    if st == "fail":
        return "fail"
    if st == "pass_with_warnings":
        return "warning"
    return "pass"


class PersistingPipelineProgress:
    """Writes `PipelineRunProgressEvent` rows + keeps `job.json` in sync."""

    __slots__ = (
        "_ctx_risk_hits",
        "_cumulative_traces",
        "_fallback_so_far",
        "_job_id",
        "_lock",
        "_pending_detail",
        "_pending_slug",
        "_pending_start_iso",
        "_pending_start_perf",
        "_seq",
        "_store",
    )

    def __init__(self, store: RunJobStore, job_id: str) -> None:
        self._store = store
        self._job_id = job_id
        self._seq = 0
        self._lock = threading.Lock()
        self._pending_slug: ProgressStage | None = None
        self._pending_start_perf: float | None = None
        self._pending_start_iso: str | None = None
        self._pending_detail: str | None = None
        self._cumulative_traces: list[dict[str, Any]] = []
        self._ctx_risk_hits = 0
        self._fallback_so_far = 0

    def mark_running(self) -> None:
        now = _utc_now_iso_z()
        self._store.update_job(
            self._job_id,
            {"status": "running", "started_at": now, "progress_message": "Running pipeline…"},
        )

    def _next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def _emit(
        self,
        *,
        stage: ProgressStage,
        status: EventStatus,
        message: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_ms: int | None = None,
        source_record_id: str | None = None,
        source_title: str | None = None,
        source_fragment_id: str | None = None,
        fragment_locator: str | None = None,
        model_alias: str | None = None,
        extraction_mode: str | None = None,
        estimated_input_tokens: int | None = None,
        configured_context_limit: int | None = None,
        llm_invoked: bool | None = None,
        fallback_used: bool | None = None,
        context_window_risk: bool | None = None,
        metrics: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        run_id: str | None = None,
    ) -> None:
        rid = self._store.read_job(self._job_id)
        seq = self._next_seq()
        ev: dict[str, Any] = {
            "id": new_event_id(),
            "run_job_id": self._job_id,
            "run_id": run_id or (str(rid.get("run_id")) if rid and rid.get("run_id") else None),
            "sequence_number": seq,
            "stage": stage,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "message": message,
            "source_record_id": source_record_id,
            "source_title": source_title,
            "source_fragment_id": source_fragment_id,
            "fragment_locator": fragment_locator,
            "model_alias": model_alias,
            "extraction_mode": extraction_mode,
            "estimated_input_tokens": estimated_input_tokens,
            "configured_context_limit": configured_context_limit,
            "llm_invoked": llm_invoked,
            "fallback_used": fallback_used,
            "context_window_risk": context_window_risk,
            "metrics": dict(metrics or {}),
            "warnings": list(warnings or []),
            "errors": list(errors or []),
        }
        self._store.append_event(self._job_id, ev)

    def _close_pending(
        self,
        *,
        status: EventStatus = "pass",
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        if self._pending_slug is None or self._pending_start_perf is None:
            return
        fin = perf_counter()
        dur_ms = int(max(0.0, (fin - self._pending_start_perf)) * 1000.0)
        iso_fin = _utc_now_iso_z()
        self._emit(
            stage=self._pending_slug,
            status=status,
            message=self._pending_detail,
            started_at=self._pending_start_iso,
            finished_at=iso_fin,
            duration_ms=dur_ms,
            warnings=list(warnings or []),
            errors=list(errors or []),
        )
        self._pending_slug = None
        self._pending_start_perf = None
        self._pending_start_iso = None
        self._pending_detail = None

    def _touch_job_stage(self, slug: ProgressStage | None, msg: str | None) -> None:
        self._store.merge_job(
            self._job_id,
            lambda j: j.update({"current_stage": slug, "progress_message": msg}),
        )

    def _refresh_job_metrics_partial(self) -> None:
        ext = compute_extraction_llm_trace_summary_metrics(self._cumulative_traces)

        def _upd(j: dict[str, Any]) -> None:
            m = j.get("metrics")
            if not isinstance(m, dict):
                m = {}
                j["metrics"] = m
            m["llm_extraction_call_count"] = int(ext.get("llm_extraction_call_count") or 0)
            m["llm_extraction_skipped_count"] = int(ext.get("llm_extraction_skipped_count") or 0)
            mtok = ext.get("max_estimated_input_tokens")
            m["max_estimated_input_tokens"] = mtok
            m["fallback_count"] = int(self._fallback_so_far)
            m["context_window_risk_count"] = int(self._ctx_risk_hits)

        self._store.merge_job(self._job_id, _upd)

    def stage(self, title: str, *, detail: str | None = None) -> None:
        slug = _stage_from_title(title)
        if slug:
            self._close_pending(status="pass")
            self._pending_slug = slug
            self._pending_start_perf = perf_counter()
            self._pending_start_iso = _utc_now_iso_z()
            self._pending_detail = detail
            msg = f"{title}" + (f" — {detail}" if detail else "")
            self._touch_job_stage(slug, msg)
        else:
            self._touch_job_stage(self._pending_slug, (title + (f" — {detail}" if detail else "")))

    def extraction_source(self, index: int, total: int, mode: str, source_label: str) -> None:
        msg = f"Proposition extraction — {mode} source {index}/{total} ({source_label})"
        self._touch_job_stage("proposition_extraction", msg)

    def begin_extraction_run(
        self,
        plan: Any,
        *,
        derived_cache_dir: str | None = None,
        print_estimate: bool = True,
    ) -> None:
        return

    def extraction_job_started(
        self,
        *,
        overall_index: int,
        source_id: str,
        source_title: str,
        fragment_locator: str,
    ) -> None:
        return

    def extraction_job_finished(
        self,
        *,
        overall_index: int,
        source_id: str,
        source_title: str,
        fragment_locator: str,
        traces: list[dict[str, Any]] | None = None,
        propositions_added: int = 0,
        duration_seconds: float | None = None,
    ) -> None:
        return

    def finish_extraction_run(self) -> dict[str, Any]:
        return {}

    def before_model_extract(
        self,
        kind: Literal["frontier", "local"],
        index: int,
        total: int,
        source_label: str,
        *,
        source_record_id: str | None = None,
        estimated_input_tokens: int | None = None,
        extraction_llm_chunk_index: int | None = None,
        extraction_llm_chunk_total: int | None = None,
        trace: dict[str, Any] | None = None,
    ) -> None:
        call = "frontier_extract" if kind == "frontier" else "local_extract"
        locator = ""
        if trace and trace.get("fragment_locator"):
            locator = str(trace.get("fragment_locator") or "").strip()
        elif ":" in source_label and " · " in source_label:
            locator = source_label.split(" · ", 1)[-1].strip()
        chunk = ""
        if isinstance(extraction_llm_chunk_index, int) and isinstance(extraction_llm_chunk_total, int):
            chunk = f" chunk {extraction_llm_chunk_index}/{extraction_llm_chunk_total}"
        msg = (
            f"Calling {call} for source {index}/{total}{chunk}"
            + (f", fragment {locator}" if locator else f" ({source_label})")
        )
        trace_tokens = estimated_input_tokens
        t = trace or {}
        sid = (source_record_id or "").strip() or (str(t.get("source_record_id") or "").strip() or None)
        sfrag = t.get("source_fragment_id")
        stitle = t.get("source_title")
        mall = t.get("model_alias")
        ctx_lim = t.get("configured_context_limit")
        self._emit(
            stage="proposition_extraction",
            status="running",
            message=msg,
            started_at=_utc_now_iso_z(),
            source_record_id=sid,
            source_title=str(stitle) if stitle else None,
            source_fragment_id=str(sfrag) if sfrag else None,
            fragment_locator=locator or None,
            estimated_input_tokens=trace_tokens if isinstance(trace_tokens, int) else None,
            configured_context_limit=int(ctx_lim) if isinstance(ctx_lim, int) else None,
            model_alias=str(mall) if mall else None,
            extraction_mode=str(t.get("extraction_mode")) if t.get("extraction_mode") else None,
            llm_invoked=False,
            context_window_risk=None,
            metrics={
                "extraction_llm_chunk_index": extraction_llm_chunk_index,
                "extraction_llm_chunk_total": extraction_llm_chunk_total,
            },
        )
        self._touch_job_stage("proposition_extraction", msg)

    def fallback_notice(self, source_label: str, reason: str | None) -> None:
        r = (reason or "").strip()
        if len(r) > 256:
            r = r[:255] + "…"
        self._emit(
            stage="proposition_extraction",
            status="warning",
            message=f"Fallback: {source_label}",
            started_at=_utc_now_iso_z(),
            warnings=[r] if r else [],
        )

    def verbose(self, message: str) -> None:
        return

    def extraction_source_complete(self, outcome: Any) -> None:
        traces = getattr(outcome, "extraction_llm_call_traces", None) or []
        rows = [t for t in traces if isinstance(t, dict)]
        self._cumulative_traces.extend(rows)
        for t in rows:
            if str(t.get("skip_reason") or "") == "context_window_risk":
                self._ctx_risk_hits += 1
        if bool(getattr(outcome, "fallback_used", False)):
            self._fallback_so_far += 1
        src_id = ""
        if rows:
            src_id = str(rows[0].get("source_record_id") or "")
        title = str(getattr(outcome, "source_title", "") or "")
        if not title and rows:
            title = str(rows[0].get("source_title") or "")
        frag_id = None
        loc = None
        if rows:
            frag_id = rows[0].get("source_fragment_id")
            loc = rows[0].get("fragment_locator")
        mode = str(getattr(outcome, "extraction_mode", "") or "")
        if not mode and rows:
            mode = str(rows[0].get("extraction_mode") or "")
        mall = getattr(outcome, "model_alias", None)
        if mall is None and rows:
            mall = rows[0].get("model_alias")
        llm_calls = sum(1 for t in rows if t.get("llm_invoked") is True)
        skipped = sum(1 for t in rows if t.get("skipped_llm") is True)
        ctx_any = any(str(t.get("skip_reason") or "") == "context_window_risk" for t in rows)
        failed = bool(getattr(outcome, "failed_closed", False))
        fb = bool(getattr(outcome, "fallback_used", False))
        st: EventStatus = "pass"
        errs: list[str] = []
        warns: list[str] = []
        if failed:
            st = "fail"
            fr = getattr(outcome, "failure_reason", None)
            if fr:
                errs.append(str(fr))
            verr = getattr(outcome, "validation_errors", None)
            if isinstance(verr, list) and verr:
                errs.extend(str(x) for x in verr[:5])
        elif fb:
            st = "warning"
        # Sub-step event only: whole-stage completion is emitted by _close_pending when leaving
        # this stage (message + duration_ms). Do not phrase this as full "proposition extraction complete".
        msg = (
            f"Finished extracting source {src_id}"
            + (f" · LLM calls {llm_calls}, skipped {skipped}" if rows else "")
        )
        configured_ctx = None
        for t in rows:
            c = t.get("configured_context_limit")
            if isinstance(c, int):
                configured_ctx = c
                break
        self._emit(
            stage="proposition_extraction",
            status=st,
            message=msg,
            started_at=_utc_now_iso_z(),
            source_record_id=src_id or None,
            source_title=title or None,
            source_fragment_id=str(frag_id) if frag_id else None,
            fragment_locator=str(loc) if loc else None,
            model_alias=str(mall) if mall else None,
            extraction_mode=mode or None,
            llm_invoked=bool(llm_calls),
            fallback_used=fb,
            context_window_risk=ctx_any,
            configured_context_limit=configured_ctx,
            metrics={"llm_calls_for_source": llm_calls, "skipped_llm_for_source": skipped},
            warnings=warns,
            errors=errs,
        )
        props = getattr(outcome, "propositions", None) or []

        def _upd(j: dict[str, Any]) -> None:
            m = j.get("metrics")
            if not isinstance(m, dict):
                m = {}
                j["metrics"] = m
            m["proposition_count"] = int(m.get("proposition_count") or 0) + len(props)

        self._store.merge_job(self._job_id, _upd)
        self._refresh_job_metrics_partial()

    def finalize_job_success(self, bundle: dict[str, Any]) -> None:
        self._close_pending(status="pass")
        run = bundle.get("run") if isinstance(bundle.get("run"), dict) else {}
        rid = str(run.get("id") or "")
        mj = job_metrics_from_bundle(bundle)
        jst = terminal_job_status_from_run_quality(bundle)

        def _upd(j: dict[str, Any]) -> None:
            j["status"] = jst
            j["finished_at"] = _utc_now_iso_z()
            j["run_id"] = rid or j.get("run_id")
            j["current_stage"] = "done"
            j["progress_message"] = "Finished"
            j["metrics"] = mj

        self._store.merge_job(self._job_id, _upd)
        fin = _utc_now_iso_z()
        rq = bundle.get("run_quality_summary") if isinstance(bundle.get("run_quality_summary"), dict) else {}
        self._emit(
            stage="done",
            status="pass" if jst == "pass" else ("warning" if jst == "warning" else "fail"),
            message="Run finished",
            started_at=fin,
            finished_at=fin,
            run_id=rid or None,
            metrics={
                "run_quality_status": rq.get("status"),
                "lint_warnings_sample": list((rq.get("gate_results") or [])[:0]),
            },
            warnings=list(rq.get("recommendations") or [])[:12]
            if isinstance(rq.get("recommendations"), list)
            else [],
        )

    def finalize_job_failure(self, exc: BaseException | str, *, partial_run_id: str | None = None) -> None:
        msg = str(exc) if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
        now = _utc_now_iso_z()
        self._close_pending(status="fail", errors=[msg])

        def _upd(j: dict[str, Any]) -> None:
            j["status"] = "fail"
            j["finished_at"] = now
            j["progress_message"] = msg
            j["current_stage"] = None
            if partial_run_id:
                j["run_id"] = partial_run_id

        self._store.merge_job(self._job_id, _upd)
        self._emit(
            stage="done",
            status="fail",
            message=msg,
            started_at=now,
            finished_at=now,
            errors=[msg],
            run_id=partial_run_id,
        )
