"""Rich-based pipeline progress for CLI commands."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator, Literal

from rich.console import Console, RenderableType
from rich.status import Status
from rich.table import Table

from .extraction_progress import (
    ExtractionJobProgressSnapshot,
    ExtractionProgressTracker,
    ExtractionRunPlan,
    format_checkpoint_line,
    format_dry_run_estimate,
    format_extraction_timing_summary,
    format_progress_compact,
    format_progress_single_line,
    load_extraction_timing_profile,
)

# ---- Controller protocol (duck-typed; avoid importing Protocol for older runners) ----


class NullPipelineProgress:
    __slots__ = ("_extraction",)

    def __init__(self) -> None:
        self._extraction: ExtractionProgressTracker | None = None

    def stage(self, title: str, *, detail: str | None = None) -> None:
        return

    def begin_extraction_run(
        self,
        plan: ExtractionRunPlan,
        *,
        derived_cache_dir: str | None = None,
        print_estimate: bool = True,
    ) -> None:
        return

    def extraction_source(self, index: int, total: int, mode: str, source_label: str) -> None:
        return

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

    def fallback_notice(
        self,
        source_label: str,
        reason: str | None,
        *,
        extraction_mode: str | None = None,
        fallback_policy: str | None = None,
    ) -> None:
        return

    def verbose(self, message: str) -> None:
        return

    def extraction_source_complete(self, outcome: Any) -> None:
        return


_NULL = NullPipelineProgress()


def null_pipeline_progress() -> NullPipelineProgress:
    return _NULL


class RichPipelineProgress:
    __slots__ = (
        "_console",
        "_status",
        "_verbose",
        "_very_verbose",
        "_extraction",
        "_last_snapshot",
    )

    def __init__(
        self,
        console: Console,
        status: Status,
        *,
        verbose: bool = False,
        very_verbose: bool = False,
    ) -> None:
        self._console = console
        self._status = status
        self._verbose = verbose
        self._very_verbose = very_verbose
        self._extraction: ExtractionProgressTracker | None = None
        self._last_snapshot: ExtractionJobProgressSnapshot | None = None

    @staticmethod
    def _short(label: str, max_len: int = 72) -> str:
        s = label.strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 1] + "…"

    def _update_extraction_status(self, snapshot: ExtractionJobProgressSnapshot) -> None:
        self._last_snapshot = snapshot
        self._status.update(format_progress_single_line(snapshot))

    def stage(self, title: str, *, detail: str | None = None) -> None:
        if detail:
            renderable: RenderableType = f"[bold]{title}[/bold] — [dim]{detail}[/dim]"
        else:
            renderable = f"[bold]{title}[/bold]"
        self._status.update(renderable)

    def begin_extraction_run(
        self,
        plan: ExtractionRunPlan,
        *,
        derived_cache_dir: str | None = None,
        print_estimate: bool = True,
    ) -> None:
        self._extraction = ExtractionProgressTracker(
            plan=plan,
            progress_every=plan.progress_every,
        )
        if print_estimate and plan.extraction_mode in {"local", "frontier"}:
            profile = load_extraction_timing_profile(derived_cache_dir)
            estimate = format_dry_run_estimate(
                selected_jobs=plan.selected_jobs,
                estimated_input_tokens=plan.estimated_input_tokens,
                extraction_mode=plan.extraction_mode,
                timing_profile=profile,
            )
            self._console.print(f"[dim]{estimate}[/dim]")

    def extraction_source(self, index: int, total: int, mode: str, source_label: str) -> None:
        if self._extraction is not None:
            return
        lab = self._short(source_label)
        self._status.update(
            f"[bold]Proposition extraction[/bold] — [cyan]{mode}[/cyan] "
            f"source [white]{index}/{total}[/white] ({lab})"
        )

    def extraction_job_started(
        self,
        *,
        overall_index: int,
        source_id: str,
        source_title: str,
        fragment_locator: str,
    ) -> None:
        if self._extraction is None:
            return
        self._extraction.begin_job(source_id)

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
        t = trace or {}
        sid = (source_record_id or str(t.get("source_record_id") or "")).strip()
        title = str(t.get("source_title") or "").strip()
        if not title and " · " in source_label:
            title = source_label.split(" · ", 1)[0].strip()
        elif not title:
            title = source_label
        locator = str(t.get("fragment_locator") or "").strip()
        if not locator and " · " in source_label:
            locator = source_label.split(" · ", 1)[-1].strip()

        if self._extraction is not None and sid:
            snapshot = self._extraction.snapshot(
                overall_job_index=index,
                source_id=sid,
                source_title=title,
                fragment_locator=locator,
                model_call=call,
                estimated_input_tokens=estimated_input_tokens,
                chunk_index=extraction_llm_chunk_index,
                chunk_total=extraction_llm_chunk_total,
            )
            self._update_extraction_status(snapshot)
            if self._very_verbose:
                self._console.print(f"[dim]{format_progress_compact(snapshot)}[/dim]")
            return

        lab = self._short(source_label)
        tid = sid
        tok = (
            f", estimated tokens: {estimated_input_tokens}"
            if isinstance(estimated_input_tokens, int) and estimated_input_tokens > 0
            else ""
        )
        chunk_hint = ""
        if isinstance(extraction_llm_chunk_index, int) and isinstance(extraction_llm_chunk_total, int):
            chunk_hint = f" — chunk {extraction_llm_chunk_index}/{extraction_llm_chunk_total}"
        sid_frag = f"{tid}{tok}" if tid else ""
        id_frag = f": {sid_frag}" if sid_frag else ""
        self._status.update(
            f"[bold]Proposition extraction[/bold] — Calling [magenta]{call}[/magenta] "
            f"for source [white]{index}/{total}[/white]{id_frag}{chunk_hint} ({lab})…"
        )

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
        if self._extraction is None:
            return
        checkpoint = self._extraction.finish_job(
            source_id=source_id,
            source_title=source_title,
            fragment_locator=fragment_locator,
            traces=traces,
            propositions_added=propositions_added,
            duration_seconds=duration_seconds,
        )
        snapshot = self._extraction.snapshot(
            overall_job_index=overall_index,
            source_id=source_id,
            source_title=source_title,
            fragment_locator=fragment_locator,
            model_call=(
                "frontier_extract"
                if self._extraction.plan.extraction_mode == "frontier"
                else "local_extract"
            ),
        )
        self._last_snapshot = snapshot
        if checkpoint:
            self._console.print(f"[green]{format_checkpoint_line(snapshot)}[/green]")

    def finish_extraction_run(self) -> dict[str, Any]:
        if self._extraction is None:
            return {}
        metrics = self._extraction.timing_metrics()
        metrics["extraction_mode"] = self._extraction.plan.extraction_mode
        self._console.print(format_extraction_timing_summary(metrics))
        return metrics

    def fallback_notice(
        self,
        source_label: str,
        reason: str | None,
        *,
        extraction_mode: str | None = None,
        fallback_policy: str | None = None,
    ) -> None:
        r = (reason or "").strip()
        if len(r) > 160:
            r = r[:159] + "…"
        lab = self._short(source_label, 48)
        mode = str(extraction_mode or "").strip().lower()
        if mode in {"local", "frontier"}:
            pol = str(fallback_policy or "fallback").strip()
            self._console.print(
                f"[bold red]⚠ LLM extraction fallback[/bold red] "
                f"[dim](mode={mode}, policy={pol})[/dim] [dim]{lab}[/dim]: {r}"
            )
            if pol == "fallback":
                self._console.print(
                    "[bold yellow]Heuristic rows were used instead of model extraction. "
                    "Use --extraction-fallback fail_closed with --use-llm to avoid silent degradation.[/bold yellow]"
                )
        else:
            self._console.print(f"[yellow]↪ Fallback[/yellow] [dim]{lab}[/dim][dim]:[/dim] {r}")

    def verbose(self, message: str) -> None:
        if not self._verbose and not self._very_verbose:
            return
        prefix = ""
        if self._last_snapshot is not None:
            s = self._last_snapshot
            prefix = (
                f"[{s.overall_job_index}/{s.overall_jobs_total} {s.percent_complete}%] "
            )
        self._console.print(f"[dim]{prefix}{message}[/dim]")

    def extraction_source_complete(self, outcome: Any) -> None:
        if self._extraction is not None:
            return
        traces = getattr(outcome, "extraction_llm_call_traces", None) or []
        rows = [t for t in traces if isinstance(t, dict)]
        propositions = getattr(outcome, "propositions", None) or []
        prop_count = len(propositions) if isinstance(propositions, list) else 0
        fallback_used = bool(getattr(outcome, "fallback_used", False))
        failed_closed = bool(getattr(outcome, "failed_closed", False))
        ctx_risk = any(str(t.get("skip_reason") or "") == "context_window_risk" for t in rows)
        src_id = ""
        if rows:
            src_id = str(rows[0].get("source_record_id") or "").strip()
        if not src_id:
            src_id = str(getattr(outcome, "source_record_id", "") or "").strip()
        source_hint = f" {src_id}" if src_id else ""
        status_bits = [f"propositions: {prop_count}"]
        if fallback_used:
            status_bits.append("fallback_used: true")
        if ctx_risk:
            status_bits.append("context_window_risk: true")
        if failed_closed:
            status_bits.append("failed_closed: true")
        self._status.update(
            "[bold]Proposition extraction[/bold] — "
            f"completed source{source_hint} ({', '.join(status_bits)})"
        )


@contextmanager
def pipeline_progress(
    console: Console,
    *,
    quiet: bool,
    verbose: bool,
    very_verbose: bool = False,
    progress_every: int = 10,
) -> Generator[object, None, None]:
    _ = progress_every
    if quiet:
        yield _NULL
        return
    with console.status("[dim]Starting…[/dim]", spinner="dots") as status:
        yield RichPipelineProgress(
            console,
            status,
            verbose=verbose,
            very_verbose=very_verbose,
        )


def print_completion_summary_table(
    console: Console,
    summary: dict[str, Any],
    *,
    verbose: bool = False,
) -> None:
    table = Table(title="Run summary", show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    od = str(summary.get("output_directory") or "").strip()
    table.add_row("Sources", str(summary.get("sources", "")))
    table.add_row("Propositions", str(summary.get("propositions", "")))
    table.add_row("Extraction mode (effective)", str(summary.get("extraction_mode_effective", summary.get("extraction_mode", ""))))
    table.add_row("Extraction mode (requested)", str(summary.get("extraction_mode_requested", "")))
    table.add_row("Fallback count", str(summary.get("fallback_count", "")))
    table.add_row("Low-confidence (extraction traces)", str(summary.get("low_confidence_count", "")))
    table.add_row("Non-blocking lint warnings", str(summary.get("validation_warning_count", "")))
    table.add_row("Output directory", od or "—")
    if verbose:
        dcd = str(summary.get("derived_cache_dir") or "").strip()
        table.add_row("Derived cache directory", dcd or "—")
    table.add_row("Run quality", str(summary.get("run_quality_status", "")))
    mode = str(summary.get("extraction_mode") or "")
    if mode in {"local", "frontier"}:
        dash = "—"

        def _cell(v: object) -> str:
            if v is None:
                return dash
            s = str(v).strip()
            return s if s else dash

        table.add_row("Source fragments", _cell(summary.get("source_fragments_total")))
        table.add_row("Extraction jobs created", _cell(summary.get("extraction_jobs_created")))
        table.add_row("Extraction jobs selected", _cell(summary.get("extraction_jobs_selected")))
        table.add_row("Extraction jobs executed", _cell(summary.get("extraction_jobs_executed")))
        table.add_row("Extraction jobs skipped", _cell(summary.get("extraction_jobs_skipped")))
        table.add_row("Live LLM calls attempted", _cell(summary.get("live_llm_calls_attempted", summary.get("attempted_llm_calls"))))
        table.add_row("Live LLM calls successful", _cell(summary.get("live_llm_calls_successful", summary.get("successful_llm_calls"))))
        table.add_row("Live LLM calls failed", _cell(summary.get("live_llm_calls_failed", summary.get("failed_llm_calls"))))
        table.add_row("Cached LLM results (ok)", _cell(summary.get("cached_llm_results_successful")))
        table.add_row("Cached LLM results (failed)", _cell(summary.get("cached_llm_results_failed")))
        table.add_row("LLM results reused from cache", _cell(summary.get("llm_results_reused_from_cache")))
        table.add_row("LLM extraction skipped", _cell(summary.get("llm_extraction_skipped_count")))
        skip_hist = summary.get("skip_reasons_by_type")
        if isinstance(skip_hist, dict) and skip_hist:
            table.add_row(
                "Skip reasons (top)",
                ", ".join(f"{k}={v}" for k, v in list(skip_hist.items())[:6]),
            )
        table.add_row("Max estimated input tokens", _cell(summary.get("max_estimated_input_tokens")))
        table.add_row("Context-window risk traces", _cell(summary.get("context_window_risk_count")))
        table.add_row("Largest extraction fragment locator", _cell(summary.get("largest_extraction_fragment_locator")))
        table.add_row("Largest extraction source id", _cell(summary.get("largest_extraction_source_record_id")))
        elapsed = summary.get("extraction_elapsed_seconds")
        if elapsed is not None:
            from .extraction_progress import format_duration

            table.add_row("Extraction elapsed", format_duration(float(elapsed)))
        avg = summary.get("average_seconds_per_job")
        if avg is not None:
            table.add_row("Average seconds/job", f"{float(avg):.1f}s")
    fail_msg = str(summary.get("llm_extraction_failure_message") or "").strip()
    if fail_msg:
        table.add_row("LLM extraction", f"[bold red]{fail_msg}[/bold red]")
    console.print(table)
