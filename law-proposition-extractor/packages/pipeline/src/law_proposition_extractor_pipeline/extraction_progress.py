"""Progress, ETA, and timing metrics for long-running LLM proposition extraction."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from law_proposition_extractor_pipeline.extraction_llm_metrics import compute_extraction_llm_trace_summary_metrics

DEFAULT_LOCAL_SECONDS_PER_JOB_LOW = 20.0
DEFAULT_LOCAL_SECONDS_PER_JOB_HIGH = 45.0
DEFAULT_FRONTIER_SECONDS_PER_JOB_LOW = 8.0
DEFAULT_FRONTIER_SECONDS_PER_JOB_HIGH = 25.0
TIMING_PROFILE_FILENAME = "extraction_timing_profile.json"


def format_duration(seconds: float | None) -> str:
    """Human-readable duration; empty-safe."""
    if seconds is None or seconds < 0:
        return "0s"
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def format_eta_clock(now: datetime, remaining_seconds: float | None) -> str:
    if remaining_seconds is None or remaining_seconds <= 0:
        return "—"
    eta = now + timedelta(seconds=remaining_seconds)
    return eta.astimezone().strftime("%H:%M")


def compute_eta_seconds(
    *,
    completed_jobs: int,
    total_jobs: int,
    elapsed_seconds: float,
    job_durations: list[float],
) -> float | None:
    """Estimate remaining seconds from average completed job duration."""
    if total_jobs <= 0 or completed_jobs <= 0:
        return None
    if completed_jobs >= total_jobs:
        return 0.0
    if job_durations:
        avg = sum(job_durations) / len(job_durations)
    elif elapsed_seconds > 0:
        avg = elapsed_seconds / completed_jobs
    else:
        return None
    remaining_jobs = total_jobs - completed_jobs
    return max(0.0, avg * remaining_jobs)


def compute_percent_complete(completed_jobs: int, total_jobs: int) -> float:
    if total_jobs <= 0:
        return 0.0
    return round(100.0 * completed_jobs / total_jobs, 1)


@dataclass
class ExtractionSourcePlan:
    source_index: int
    source_id: str
    source_title: str
    jobs_in_source: int


@dataclass
class ExtractionRunPlan:
    total_jobs: int
    selected_jobs: int
    estimated_input_tokens: int
    extraction_mode: str
    sources: list[ExtractionSourcePlan]
    progress_every: int = 10


@dataclass
class ExtractionJobProgressSnapshot:
    overall_job_index: int
    overall_jobs_total: int
    source_index: int
    sources_total: int
    source_title: str
    source_job_index: int
    source_jobs_total: int
    fragment_locator: str
    model_call: str
    estimated_input_tokens: int | None
    chunk_index: int | None
    chunk_total: int | None
    completed_jobs: int
    percent_complete: float
    elapsed_seconds: float
    average_seconds_per_job: float | None
    remaining_seconds: float | None
    eta_clock: str
    successful_calls: int
    failed_calls: int
    skipped_calls: int
    propositions_so_far: int
    cached_successful_calls: int
    cached_failed_calls: int


@dataclass
class ExtractionProgressCounters:
    completed_jobs: int = 0
    propositions_so_far: int = 0
    job_durations: list[float] = field(default_factory=list)
    slowest_job_seconds: float = 0.0
    slowest_job_locator: str | None = None
    slowest_job_source_id: str | None = None
    slowest_job_source_title: str | None = None


class ExtractionProgressTracker:
    """Mutable extraction progress state (pure logic; no I/O except optional profile load)."""

    def __init__(
        self,
        *,
        plan: ExtractionRunPlan,
        progress_every: int = 10,
        started_at: datetime | None = None,
        started_perf: float | None = None,
    ) -> None:
        self.plan = plan
        self.progress_every = max(1, progress_every)
        self.started_at = started_at or datetime.now(UTC)
        self._started_perf = started_perf if started_perf is not None else perf_counter()
        self.counters = ExtractionProgressCounters()
        self._llm_traces: list[dict[str, Any]] = []
        self._source_by_id: dict[str, ExtractionSourcePlan] = {
            s.source_id: s for s in plan.sources
        }
        self._source_job_counts: dict[str, int] = {}
        self._current_job_start_perf: float | None = None

    def _llm_metrics(self) -> dict[str, Any]:
        return compute_extraction_llm_trace_summary_metrics(self._llm_traces)

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, perf_counter() - self._started_perf)

    def _average_seconds_per_job(self) -> float | None:
        durations = self.counters.job_durations
        if durations:
            return sum(durations) / len(durations)
        completed = self.counters.completed_jobs
        if completed > 0 and self.elapsed_seconds > 0:
            return self.elapsed_seconds / completed
        return None

    def _remaining_seconds(self) -> float | None:
        return compute_eta_seconds(
            completed_jobs=self.counters.completed_jobs,
            total_jobs=self.plan.total_jobs,
            elapsed_seconds=self.elapsed_seconds,
            job_durations=self.counters.job_durations,
        )

    def source_job_index(self, source_id: str) -> int:
        return self._source_job_counts.get(source_id, 0) + 1

    def begin_job(self, source_id: str) -> None:
        self._current_job_start_perf = perf_counter()
        self._source_job_counts[source_id] = self._source_job_counts.get(source_id, 0) + 1

    def finish_job(
        self,
        *,
        source_id: str,
        source_title: str,
        fragment_locator: str,
        traces: list[dict[str, Any]] | None = None,
        propositions_added: int = 0,
        duration_seconds: float | None = None,
    ) -> bool:
        """Record job completion. Returns True if a checkpoint line should be printed."""
        if duration_seconds is None and self._current_job_start_perf is not None:
            duration_seconds = max(0.0, perf_counter() - self._current_job_start_perf)
        self._current_job_start_perf = None
        if duration_seconds is not None:
            self.counters.job_durations.append(duration_seconds)
            if duration_seconds >= self.counters.slowest_job_seconds:
                self.counters.slowest_job_seconds = duration_seconds
                self.counters.slowest_job_locator = fragment_locator or None
                self.counters.slowest_job_source_id = source_id
                self.counters.slowest_job_source_title = source_title
        if traces:
            self._llm_traces.extend(row for row in traces if isinstance(row, dict))
        self.counters.propositions_so_far += max(0, propositions_added)
        self.counters.completed_jobs += 1
        every = self.progress_every
        return self.counters.completed_jobs > 0 and self.counters.completed_jobs % every == 0

    def snapshot(
        self,
        *,
        overall_job_index: int,
        source_id: str,
        source_title: str,
        fragment_locator: str,
        model_call: str,
        estimated_input_tokens: int | None = None,
        chunk_index: int | None = None,
        chunk_total: int | None = None,
    ) -> ExtractionJobProgressSnapshot:
        src_plan = self._source_by_id.get(source_id)
        source_index = src_plan.source_index if src_plan else 1
        source_jobs_total = src_plan.jobs_in_source if src_plan else self.plan.total_jobs
        avg = self._average_seconds_per_job()
        remaining = self._remaining_seconds()
        now = datetime.now(UTC)
        llm_metrics = self._llm_metrics()
        return ExtractionJobProgressSnapshot(
            overall_job_index=overall_job_index,
            overall_jobs_total=self.plan.total_jobs,
            source_index=source_index,
            sources_total=len(self.plan.sources) or 1,
            source_title=source_title,
            source_job_index=self.source_job_index(source_id),
            source_jobs_total=source_jobs_total,
            fragment_locator=fragment_locator,
            model_call=model_call,
            estimated_input_tokens=estimated_input_tokens,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
            completed_jobs=self.counters.completed_jobs,
            percent_complete=compute_percent_complete(
                self.counters.completed_jobs, self.plan.total_jobs
            ),
            elapsed_seconds=self.elapsed_seconds,
            average_seconds_per_job=avg,
            remaining_seconds=remaining,
            eta_clock=format_eta_clock(now, remaining),
            successful_calls=int(llm_metrics.get("live_llm_calls_successful") or 0),
            failed_calls=int(llm_metrics.get("live_llm_calls_failed") or 0),
            skipped_calls=int(llm_metrics.get("llm_extraction_skipped_count") or 0),
            cached_successful_calls=int(llm_metrics.get("cached_llm_results_successful") or 0),
            cached_failed_calls=int(llm_metrics.get("cached_llm_results_failed") or 0),
            propositions_so_far=self.counters.propositions_so_far,
        )

    def timing_metrics(self) -> dict[str, Any]:
        completed_at = datetime.now(UTC)
        durations = self.counters.job_durations
        avg = (sum(durations) / len(durations)) if durations else None
        median = statistics.median(durations) if len(durations) >= 1 else None
        elapsed = self.elapsed_seconds
        jobs_per_min = (
            (self.counters.completed_jobs / elapsed) * 60.0 if elapsed > 0 and self.counters.completed_jobs else None
        )
        metrics: dict[str, Any] = {
            "extraction_started_at": self.started_at.isoformat().replace("+00:00", "Z"),
            "extraction_completed_at": completed_at.isoformat().replace("+00:00", "Z"),
            "extraction_elapsed_seconds": round(elapsed, 3),
            "extraction_jobs_total": self.plan.total_jobs,
            "extraction_jobs_completed": self.counters.completed_jobs,
            "extraction_jobs_per_minute": round(jobs_per_min, 3) if jobs_per_min is not None else None,
            "average_seconds_per_job": round(avg, 3) if avg is not None else None,
            "median_seconds_per_job": round(float(median), 3) if median is not None else None,
            "slowest_job_seconds": round(self.counters.slowest_job_seconds, 3)
            if self.counters.slowest_job_seconds > 0
            else None,
            "slowest_job_locator": self.counters.slowest_job_locator,
            "slowest_job_source_id": self.counters.slowest_job_source_id,
            "slowest_job_source_title": self.counters.slowest_job_source_title,
            "propositions_extracted": self.counters.propositions_so_far,
        }
        metrics.update(self._llm_metrics())
        metrics["skipped_llm_calls"] = metrics.get("llm_extraction_skipped_count", 0)
        return metrics


def format_progress_compact(snapshot: ExtractionJobProgressSnapshot) -> str:
    pct = snapshot.percent_complete
    avg = (
        f"{snapshot.average_seconds_per_job:.1f}s"
        if snapshot.average_seconds_per_job is not None
        else "—"
    )
    remaining = (
        f"~{format_duration(snapshot.remaining_seconds)}"
        if snapshot.remaining_seconds is not None
        else "—"
    )
    chunk = ""
    if snapshot.chunk_index is not None and snapshot.chunk_total is not None:
        chunk = f" · chunk {snapshot.chunk_index}/{snapshot.chunk_total}"
    locator = snapshot.fragment_locator or "—"
    tok = (
        str(snapshot.estimated_input_tokens)
        if isinstance(snapshot.estimated_input_tokens, int) and snapshot.estimated_input_tokens > 0
        else "—"
    )
    lines = [
        f"Proposition extraction {snapshot.overall_job_index}/{snapshot.overall_jobs_total} ({pct}%)",
        f"Source {snapshot.source_index}/{snapshot.sources_total}: {snapshot.source_title} · "
        f"source job {snapshot.source_job_index}/{snapshot.source_jobs_total} · "
        f"overall job {snapshot.overall_job_index}/{snapshot.overall_jobs_total}",
        f"Current: {snapshot.source_title} · {locator}{chunk}",
        f"Model: {snapshot.model_call}",
        f"Estimated input tokens: {tok}",
        (
            f"Elapsed: {format_duration(snapshot.elapsed_seconds)} · avg/job: {avg} · "
            f"remaining: {remaining} · ETA: {snapshot.eta_clock}"
        ),
        (
            f"Calls: {snapshot.successful_calls} live ok / {snapshot.failed_calls} live failed / "
            f"{snapshot.cached_successful_calls} cached ok / {snapshot.cached_failed_calls} cached fail / "
            f"{snapshot.skipped_calls} skipped"
        ),
        f"Propositions so far: {snapshot.propositions_so_far}",
    ]
    return "\n".join(lines)


def format_progress_single_line(snapshot: ExtractionJobProgressSnapshot) -> str:
    pct = snapshot.percent_complete
    avg = (
        f"{snapshot.average_seconds_per_job:.1f}s/job"
        if snapshot.average_seconds_per_job is not None
        else "—"
    )
    remaining = (
        format_duration(snapshot.remaining_seconds)
        if snapshot.remaining_seconds is not None
        else "—"
    )
    loc = snapshot.fragment_locator or "—"
    return (
        f"Extract {snapshot.overall_job_index}/{snapshot.overall_jobs_total} ({pct}%) · "
        f"src {snapshot.source_index}/{snapshot.sources_total} · {loc} · "
        f"{format_duration(snapshot.elapsed_seconds)} · ETA {snapshot.eta_clock} · {avg} · "
        f"{snapshot.propositions_so_far} props"
    )


def format_checkpoint_line(snapshot: ExtractionJobProgressSnapshot) -> str:
    pct = snapshot.percent_complete
    return (
        f"✓ {snapshot.completed_jobs}/{snapshot.overall_jobs_total} jobs complete ({pct}%) · "
        f"{snapshot.successful_calls} live ok · {snapshot.failed_calls} live failed · "
        f"{snapshot.cached_successful_calls} cached ok · "
        f"{snapshot.skipped_calls} skipped · {snapshot.propositions_so_far} propositions · "
        f"elapsed {format_duration(snapshot.elapsed_seconds)} · ETA {snapshot.eta_clock}"
    )


def format_extraction_timing_summary(metrics: dict[str, Any]) -> str:
    slow_loc = metrics.get("slowest_job_locator") or "—"
    slow_title = metrics.get("slowest_job_source_title") or metrics.get("slowest_job_source_id") or ""
    slow_label = f"{slow_title} · {slow_loc}" if slow_title else str(slow_loc)
    slow_secs = metrics.get("slowest_job_seconds")
    slow_part = f"{slow_secs:.1f}s — {slow_label}" if isinstance(slow_secs, (int, float)) else "—"
    elapsed = metrics.get("extraction_elapsed_seconds")
    avg = metrics.get("average_seconds_per_job")
    lines = [
        "Extraction timing:",
        f"  Jobs: {metrics.get('extraction_jobs_total', '—')}",
        f"  Completed: {metrics.get('extraction_jobs_completed', '—')}",
        f"  Live calls: {metrics.get('live_llm_calls_successful', 0)} ok / "
        f"{metrics.get('live_llm_calls_failed', 0)} failed "
        f"({metrics.get('live_llm_calls_attempted', 0)} attempted)",
        f"  Cached reuse: {metrics.get('cached_llm_results_successful', 0)} ok / "
        f"{metrics.get('cached_llm_results_failed', 0)} failed",
        f"  Skipped: {metrics.get('skipped_llm_calls', 0)}",
        f"  Propositions: {metrics.get('propositions_extracted', 0)}",
        f"  Elapsed: {format_duration(float(elapsed) if isinstance(elapsed, (int, float)) else 0)}",
        f"  Average: {avg:.1f}s/job" if isinstance(avg, (int, float)) else "  Average: —",
        f"  Slowest: {slow_part}",
    ]
    return "\n".join(lines)


def load_extraction_timing_profile(derived_cache_dir: str | Path | None) -> dict[str, Any] | None:
    if not derived_cache_dir:
        return None
    path = Path(derived_cache_dir) / TIMING_PROFILE_FILENAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def persist_extraction_timing_profile(derived_cache_dir: str | Path, metrics: dict[str, Any]) -> None:
    path = Path(derived_cache_dir) / TIMING_PROFILE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: metrics.get(k) for k in (
        "extraction_elapsed_seconds",
        "extraction_jobs_total",
        "extraction_jobs_completed",
        "average_seconds_per_job",
        "median_seconds_per_job",
        "extraction_jobs_per_minute",
        "extraction_mode",
    ) if metrics.get(k) is not None}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_dry_run_estimate(
    *,
    selected_jobs: int,
    estimated_input_tokens: int,
    extraction_mode: str,
    timing_profile: dict[str, Any] | None = None,
) -> str:
    lines = [
        f"Selected extraction jobs: {selected_jobs}",
        f"Estimated input tokens: {estimated_input_tokens:,}",
    ]
    if timing_profile and isinstance(timing_profile.get("average_seconds_per_job"), (int, float)):
        avg = float(timing_profile["average_seconds_per_job"])
        total_secs = avg * selected_jobs
        lines.append(
            f"Previous run average: {avg:.1f}s/job "
            f"(from {timing_profile.get('extraction_jobs_completed', '?')} jobs)."
        )
        lines.append(f"Rough estimate: {format_duration(total_secs)}")
    else:
        lines.append("No previous timing profile found.")
        if extraction_mode == "frontier":
            lo, hi = DEFAULT_FRONTIER_SECONDS_PER_JOB_LOW, DEFAULT_FRONTIER_SECONDS_PER_JOB_HIGH
        else:
            lo, hi = DEFAULT_LOCAL_SECONDS_PER_JOB_LOW, DEFAULT_LOCAL_SECONDS_PER_JOB_HIGH
        lines.append(
            f"Rough {extraction_mode} estimate at {lo:.0f}–{hi:.0f}s/job: "
            f"{format_duration(lo * selected_jobs)}–{format_duration(hi * selected_jobs)}"
        )
    return "\n".join(lines)


def build_extraction_run_plan(
    extraction_jobs: list[tuple[Any, Any]],
    *,
    selected_jobs: int,
    estimated_input_tokens: int,
    extraction_mode: str,
    progress_every: int = 10,
) -> ExtractionRunPlan:
    source_order: list[str] = []
    source_titles: dict[str, str] = {}
    jobs_per_source: dict[str, int] = {}
    for source, _frag in extraction_jobs:
        sid = str(source.id)
        if sid not in source_order:
            source_order.append(sid)
            source_titles[sid] = str(source.title or sid)
        jobs_per_source[sid] = jobs_per_source.get(sid, 0) + 1
    sources = [
        ExtractionSourcePlan(
            source_index=idx,
            source_id=sid,
            source_title=source_titles[sid],
            jobs_in_source=jobs_per_source[sid],
        )
        for idx, sid in enumerate(source_order, start=1)
    ]
    return ExtractionRunPlan(
        total_jobs=len(extraction_jobs),
        selected_jobs=selected_jobs,
        estimated_input_tokens=estimated_input_tokens,
        extraction_mode=extraction_mode,
        sources=sources,
        progress_every=progress_every,
    )


def merge_timing_metrics_into_observability(
    observability: dict[str, Any],
    timing: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(observability)
    timing_keys = (
        "extraction_started_at",
        "extraction_completed_at",
        "extraction_elapsed_seconds",
        "extraction_jobs_total",
        "extraction_jobs_completed",
        "extraction_jobs_per_minute",
        "average_seconds_per_job",
        "median_seconds_per_job",
        "slowest_job_seconds",
        "slowest_job_locator",
        "slowest_job_source_id",
        "slowest_job_source_title",
        "propositions_extracted",
    )
    llm_metric_keys = (
        "live_llm_calls_attempted",
        "live_llm_calls_successful",
        "live_llm_calls_failed",
        "cached_llm_results_successful",
        "cached_llm_results_failed",
        "cached_successful_llm_results",
        "cached_failed_llm_results",
        "llm_results_reused_from_cache",
        "attempted_llm_calls",
        "successful_llm_calls",
        "failed_llm_calls",
        "llm_extraction_call_count",
        "llm_extraction_skipped_count",
        "skipped_llm_calls",
    )
    for key in timing_keys:
        if key in timing and timing[key] is not None:
            merged[key] = timing[key]
    for key in llm_metric_keys:
        if key in observability and observability[key] is not None:
            merged[key] = observability[key]
    return merged


def extraction_timing_metrics_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    for tr in bundle.get("stage_traces") or []:
        if not isinstance(tr, dict):
            continue
        if str(tr.get("stage_name") or "") != "proposition extraction":
            continue
        outputs = tr.get("outputs")
        if not isinstance(outputs, dict):
            return {}
        timing_keys = (
            "extraction_started_at",
            "extraction_completed_at",
            "extraction_elapsed_seconds",
            "extraction_jobs_total",
            "extraction_jobs_completed",
            "extraction_jobs_per_minute",
            "average_seconds_per_job",
            "median_seconds_per_job",
            "slowest_job_seconds",
            "slowest_job_locator",
            "slowest_job_source_id",
            "slowest_job_source_title",
            "propositions_extracted",
        )
        return {k: outputs[k] for k in timing_keys if k in outputs}
    return {}
