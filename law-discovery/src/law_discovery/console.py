from __future__ import annotations

from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import NoReturn

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from law_discovery.models import CandidateSource, CategoryBrief, DiscoveryRun, RelatedSourceExpansionRun
from law_discovery.progress import CliProgressTracker, DiscoveryProgressEvent
from law_discovery.triage_helpers import (
    count_ai_adjusted_confidence,
    count_by_recommended_action,
    count_by_review_priority,
    discovery_run_has_ai_triage,
    format_top_candidate_line,
    select_top_candidates,
)


class OutputMode(StrEnum):
    RICH = "rich"
    PLAIN = "plain"
    QUIET = "quiet"


def _query_strings(extra: dict[str, object]) -> list[str]:
    queries = extra.get("queries")
    if not isinstance(queries, list):
        return []
    return [str(query) for query in queries if str(query)]


class DiscoveryConsole:
    """Rich/plain/quiet presentation for the discover command."""

    def __init__(self, mode: OutputMode = OutputMode.RICH) -> None:
        self.mode = mode
        self._lex_tracker: CliProgressTracker | None = None
        self._ai_tracker: CliProgressTracker | None = None
        self._ai_triage_tracker: CliProgressTracker | None = None
        self._progress_line_width = 0

        if mode == OutputMode.QUIET:
            self.console = Console(quiet=True, stderr=True)
        elif mode == OutputMode.PLAIN:
            self.console = Console(
                stderr=True,
                no_color=True,
                highlight=False,
                width=200,
                soft_wrap=False,
            )
        else:
            self.console = Console(stderr=True)

    def emit(self, stage: str, message: str, **kwargs: object) -> None:
        current = kwargs.get("current")
        total = kwargs.get("total")
        extra = kwargs.get("extra")
        event = DiscoveryProgressEvent(
            stage=stage,
            message=message,
            current=current if isinstance(current, int) else None,
            total=total if isinstance(total, int) else None,
            extra=extra if isinstance(extra, dict) else {},
        )
        self.handle_progress(event)

    def handle_progress(self, event: DiscoveryProgressEvent) -> None:
        if self.mode == OutputMode.QUIET:
            return
        if self.mode == OutputMode.PLAIN:
            self._handle_plain(event)
            return
        self._handle_rich(event)

    def show_startup_panel(
        self,
        *,
        category: CategoryBrief,
        output: Path,
        use_network: bool,
        lex_base_url: str | None,
        use_ai_assessment: bool,
        use_ai_triage: bool = False,
        ai_triage_batch_size: int = 15,
        ai_model: str | None = None,
        ai_base_url: str | None = None,
        expansion_path: Path | None = None,
    ) -> None:
        if self.mode == OutputMode.QUIET:
            return

        if self.mode == OutputMode.PLAIN:
            self.console.print("[law-discovery] Law Discovery Source Discovery", markup=False)
            self.console.print(
                f"[law-discovery] category: {category.label} ({category.category_id})",
                markup=False,
            )
            if use_network:
                self.console.print(
                    f"[law-discovery] network: enabled ({lex_base_url or 'not configured'})",
                    markup=False,
                )
            else:
                self.console.print(
                    "[law-discovery] network: disabled (no Lex calls will be made)",
                    markup=False,
                )
            if use_ai_assessment:
                model_text = ai_model or "not configured"
                base_text = ai_base_url or "not configured"
                self.console.print(
                    f"[law-discovery] AI assessment: enabled ({model_text} @ {base_text})",
                    markup=False,
                )
            else:
                self.console.print("[law-discovery] AI assessment: disabled", markup=False)
            if use_ai_triage:
                model_text = ai_model or "not configured"
                base_text = ai_base_url or "not configured"
                self.console.print(
                    f"[law-discovery] AI triage: enabled ({model_text} @ {base_text}, "
                    f"batch_size={ai_triage_batch_size})",
                    markup=False,
                )
            else:
                self.console.print("[law-discovery] AI triage: disabled", markup=False)
            if expansion_path is not None:
                self.console.print(f"[law-discovery] expansion: {expansion_path}", markup=False)
            self.console.print(f"[law-discovery] output: {output}", markup=False)
            return

        lines: list[str] = [
            f"[bold]Category[/]: {category.label}",
            f"[bold]Category ID[/]: {category.category_id}",
        ]
        if use_network:
            lines.append("[bold]Network[/]: [green]enabled[/]")
            if lex_base_url:
                lines.append(f"[bold]Lex base URL[/]: {lex_base_url}")
        else:
            lines.append("[bold]Network[/]: [yellow]disabled[/] — no Lex calls will be made")

        if use_ai_assessment:
            lines.append("[bold]AI assessment[/]: [green]enabled[/]")
        else:
            lines.append("[bold]AI assessment[/]: disabled")

        if use_ai_triage:
            lines.append("[bold]AI triage[/]: [green]enabled[/]")
            lines.append(f"[bold]AI triage batch size[/]: {ai_triage_batch_size}")
        else:
            lines.append("[bold]AI triage[/]: disabled")

        if ai_model and (use_ai_assessment or use_ai_triage):
            lines.append(f"[bold]AI model[/]: {ai_model}")
        if ai_base_url and (use_ai_assessment or use_ai_triage):
            lines.append(f"[bold]LiteLLM base URL[/]: {ai_base_url}")

        if expansion_path is not None:
            lines.append(f"[bold]Expansion[/]: {expansion_path}")

        lines.append(f"[bold]Output[/]: {output}")

        self.console.print(
            Panel(
                "\n".join(lines),
                title="Law Discovery Source Discovery",
                border_style="blue",
            )
        )

    def show_summary(self, run: DiscoveryRun, output: Path) -> None:
        if self.mode == OutputMode.QUIET:
            return

        candidates = run.candidate_sources
        has_ai_triage = discovery_run_has_ai_triage(candidates)
        top_lines = [
            format_top_candidate_line(candidate)
            for candidate in select_top_candidates(candidates)
            if candidate.title
        ]

        register_flag = (
            "--accept-ai-likely-accept" if has_ai_triage else "--accept-high-confidence"
        )
        next_command = (
            "uv run law-discovery make-register "
            f"{output} "
            f"--output runs/{run.category.category_id}/source-register.json "
            f"{register_flag}"
        )

        if self.mode == OutputMode.PLAIN:
            self.console.print(f"[law-discovery] wrote {output}", markup=False)
            self.console.print(f"[law-discovery] category_id: {run.category.category_id}", markup=False)
            self.console.print(f"[law-discovery] queries: {len(run.query_plan)}", markup=False)
            self.console.print(
                f"[law-discovery] candidate sources: {len(candidates)}",
                markup=False,
            )
            self.console.print(f"[law-discovery] warnings: {len(run.warnings)}", markup=False)
            self._print_plain_triage_or_confidence_summary(candidates, has_ai_triage)
            self._print_plain_ai_triage_summary(run.metadata)
            for index, line in enumerate(top_lines, start=1):
                self.console.print(f"[law-discovery] top candidate {index}: {line}", markup=False)
            self.console.print(f"[law-discovery] next: {next_command}", markup=False)
            return

        table = Table(title="Discovery summary", show_header=True, header_style="bold")
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        table.add_row("Output file", str(output))
        table.add_row("Category ID", run.category.category_id)
        table.add_row("Total queries", str(len(run.query_plan)))
        table.add_row("Candidate sources", str(len(candidates)))
        partial_results = run.metadata.get("partial_results")
        if partial_results is True:
            failed_queries = run.metadata.get("failed_query_count", 0)
            successful_queries = run.metadata.get("successful_query_count", 0)
            table.add_row(
                "Lex queries",
                f"{successful_queries} succeeded, {failed_queries} failed (partial results)",
            )
        self._add_rich_ai_triage_summary_rows(table, run.metadata)
        table.add_row("Warnings", str(len(run.warnings)))
        self._add_rich_triage_or_confidence_rows(table, candidates, has_ai_triage)

        self.console.print(table)
        self._print_rich_ai_triage_warning_panel(run.metadata)

        if top_lines:
            title_lines = "\n".join(
                f"  {index}. {line}" for index, line in enumerate(top_lines, 1)
            )
            self.console.print(
                Panel(
                    title_lines,
                    title="Top candidates",
                    border_style="green",
                )
            )

        self.console.print(
            Panel(
                next_command,
                title="Suggested next command",
                border_style="cyan",
            )
        )

    def _print_plain_triage_or_confidence_summary(
        self,
        candidates: list[CandidateSource],
        has_ai_triage: bool,
    ) -> None:
        if has_ai_triage:
            priority_counts = count_by_review_priority(candidates)
            action_counts = count_by_recommended_action(candidates)
            ai_confidence = count_ai_adjusted_confidence(candidates)
            self.console.print(
                "[law-discovery] AI review priority: "
                f"likely_accept={priority_counts['likely_accept']} "
                f"needs_human_review={priority_counts['needs_human_review']} "
                f"park_contextual={priority_counts['park_contextual']} "
                f"likely_reject={priority_counts['likely_reject']}",
                markup=False,
            )
            self.console.print(
                "[law-discovery] AI recommended action: "
                f"accept_candidate={action_counts['accept_candidate']} "
                f"needs_more_research={action_counts['needs_more_research']} "
                f"park={action_counts['park']} "
                f"reject_candidate={action_counts['reject_candidate']}",
                markup=False,
            )
            self.console.print(
                "[law-discovery] AI-adjusted confidence: "
                f"high={ai_confidence['high']} "
                f"medium={ai_confidence['medium']} "
                f"low={ai_confidence['low']} "
                f"unknown={ai_confidence['unknown']}",
                markup=False,
            )
            return

        confidence_counts = Counter(candidate.confidence for candidate in candidates)
        self.console.print(
            "[law-discovery] confidence: "
            f"high={confidence_counts.get('high', 0)} "
            f"medium={confidence_counts.get('medium', 0)} "
            f"low={confidence_counts.get('low', 0)} "
            f"unknown={confidence_counts.get('unknown', 0)}",
            markup=False,
        )

    @staticmethod
    def _add_rich_triage_or_confidence_rows(
        table: Table,
        candidates: list[CandidateSource],
        has_ai_triage: bool,
    ) -> None:
        if has_ai_triage:
            priority_counts = count_by_review_priority(candidates)
            action_counts = count_by_recommended_action(candidates)
            ai_confidence = count_ai_adjusted_confidence(candidates)
            table.add_row(
                "AI review priority (likely accept)",
                str(priority_counts["likely_accept"]),
            )
            table.add_row(
                "AI review priority (needs human review)",
                str(priority_counts["needs_human_review"]),
            )
            table.add_row(
                "AI review priority (park contextual)",
                str(priority_counts["park_contextual"]),
            )
            table.add_row(
                "AI review priority (likely reject)",
                str(priority_counts["likely_reject"]),
            )
            table.add_row(
                "AI action (accept candidate)",
                str(action_counts["accept_candidate"]),
            )
            table.add_row(
                "AI action (needs more research)",
                str(action_counts["needs_more_research"]),
            )
            table.add_row("AI action (park)", str(action_counts["park"]))
            table.add_row(
                "AI action (reject candidate)",
                str(action_counts["reject_candidate"]),
            )
            table.add_row("AI-adjusted high confidence", str(ai_confidence["high"]))
            table.add_row("AI-adjusted medium confidence", str(ai_confidence["medium"]))
            table.add_row("AI-adjusted low confidence", str(ai_confidence["low"]))
            table.add_row("AI-adjusted unknown confidence", str(ai_confidence["unknown"]))
            return

        confidence_counts = Counter(candidate.confidence for candidate in candidates)
        table.add_row("High confidence", str(confidence_counts.get("high", 0)))
        table.add_row("Medium confidence", str(confidence_counts.get("medium", 0)))
        table.add_row("Low confidence", str(confidence_counts.get("low", 0)))
        table.add_row("Unknown confidence", str(confidence_counts.get("unknown", 0)))

    def show_warnings(self, run: DiscoveryRun) -> None:
        if self.mode == OutputMode.QUIET or not run.warnings:
            return

        preview = run.warnings[:5]
        partial_results = run.metadata.get("partial_results")
        if self.mode == OutputMode.PLAIN:
            if partial_results is True:
                failed_queries = run.metadata.get("failed_query_count", 0)
                successful_queries = run.metadata.get("successful_query_count", 0)
                self.console.print(
                    "[law-discovery] partial results: "
                    f"{failed_queries} Lex query(s) failed, "
                    f"{successful_queries} succeeded",
                    markup=False,
                )
            self.console.print(f"[law-discovery] warnings ({len(run.warnings)}):", markup=False)
            for warning in preview:
                self.console.print(f"[law-discovery] warning: {warning}", markup=False)
            if len(run.warnings) > 5:
                self.console.print(
                    "[law-discovery] full warnings are preserved in the JSON output",
                    markup=False,
                )
            return

        partial_results = run.metadata.get("partial_results")
        header = ""
        if partial_results is True:
            failed_queries = run.metadata.get("failed_query_count", 0)
            successful_queries = run.metadata.get("successful_query_count", 0)
            header = (
                f"[yellow]Partial results:[/] {failed_queries} Lex "
                f"{'query' if failed_queries == 1 else 'queries'} failed; "
                f"{successful_queries} succeeded. "
                "Discovery output includes results from successful queries only.\n\n"
            )

        warning_text = "\n".join(f"• {warning}" for warning in preview)
        footer = (
            f"\n\n[dim]Showing first {len(preview)} of {len(run.warnings)} warnings. "
            "Full warnings are preserved in the JSON output.[/dim]"
        )
        self.console.print(
            Panel(
                header + warning_text + footer,
                title="Warnings",
                border_style="yellow",
            )
        )

    def show_warnings_from_list(self, warnings: list[str]) -> None:
        if self.mode == OutputMode.QUIET or not warnings:
            return
        preview = warnings[:5]
        if self.mode == OutputMode.PLAIN:
            self.console.print(f"[law-discovery] warnings ({len(warnings)}):", markup=False)
            for warning in preview:
                self.console.print(f"[law-discovery] warning: {warning}", markup=False)
            return
        warning_text = "\n".join(f"• {warning}" for warning in preview)
        self.console.print(
            Panel(warning_text, title=f"Warnings ({len(warnings)})", border_style="yellow")
        )

    def fail(self, message: str, *, code: int = 1) -> NoReturn:
        if self.mode == OutputMode.PLAIN:
            self.console.print(f"[law-discovery] error: {message}", markup=False)
        else:
            self.console.print(f"[bold red]Error:[/] {message}")
        raise SystemExit(code)

    def _plain_line(self, message: str) -> None:
        self.console.print(f"[law-discovery] {message}", markup=False)

    @staticmethod
    def _ai_triage_failure_reason(metadata: dict[str, object]) -> str:
        reasons = metadata.get("ai_triage_failure_reasons")
        if isinstance(reasons, list) and reasons:
            return str(reasons[0])
        return "unknown error"

    def _print_plain_ai_triage_summary(self, metadata: dict[str, object]) -> None:
        if not metadata.get("ai_triage_requested"):
            return

        self.console.print("[law-discovery] AI triage requested: yes", markup=False)
        self.console.print(
            "[law-discovery] AI triage successful batches: "
            f"{metadata.get('ai_triage_successful_batch_count', 0)}",
            markup=False,
        )
        self.console.print(
            "[law-discovery] AI triage failed batches: "
            f"{metadata.get('ai_triage_failed_batch_count', 0)}",
            markup=False,
        )
        self.console.print(
            "[law-discovery] AI triage fallback candidates: "
            f"{metadata.get('ai_triage_fallback_candidate_count', 0)}",
            markup=False,
        )
        if metadata.get("ai_triage_failed") is True:
            reason = self._ai_triage_failure_reason(metadata)
            self.console.print(
                f"[law-discovery] AI triage failed for all batches: {reason}",
                markup=False,
            )
        elif metadata.get("ai_triage_partial") is True:
            self.console.print(
                "[law-discovery] AI triage partially failed. Some candidates require manual review.",
                markup=False,
            )

    @staticmethod
    def _add_rich_ai_triage_summary_rows(
        table: Table,
        metadata: dict[str, object],
    ) -> None:
        if not metadata.get("ai_triage_requested"):
            return

        table.add_row("AI triage requested", "yes")
        table.add_row(
            "AI triage successful batches",
            str(metadata.get("ai_triage_successful_batch_count", 0)),
        )
        table.add_row(
            "AI triage failed batches",
            str(metadata.get("ai_triage_failed_batch_count", 0)),
        )
        table.add_row(
            "AI triage fallback candidates",
            str(metadata.get("ai_triage_fallback_candidate_count", 0)),
        )

    def _print_rich_ai_triage_warning_panel(self, metadata: dict[str, object]) -> None:
        if metadata.get("ai_triage_failed") is True:
            self.console.print(
                Panel(
                    "AI triage failed for all batches. "
                    "Results are untriaged fallback assessments.",
                    title="AI triage failed",
                    border_style="red",
                )
            )
        elif metadata.get("ai_triage_partial") is True:
            self.console.print(
                Panel(
                    "AI triage partially failed. Some candidates require manual review.",
                    title="AI triage partially failed",
                    border_style="yellow",
                )
            )

    def _print_built_queries(self, event: DiscoveryProgressEvent) -> None:
        if self.mode == OutputMode.PLAIN:
            self._plain_line(event.message)
            for query in _query_strings(event.extra):
                self._plain_line(f"  {query}")
            return

        self.console.print(Text(event.message, style="cyan"))
        for query in _query_strings(event.extra):
            self.console.print(f"  [dim]{query}[/dim]")

    def _handle_plain(self, event: DiscoveryProgressEvent) -> None:
        if event.stage == "build_query_plan" and _query_strings(event.extra):
            self._finish_active_progress_line()
            self._print_built_queries(event)
            return
        if event.stage == "lex_search_query":
            return
        if event.stage == "lex_search_start":
            secondary_label = event.extra.get("secondary_label")
            self._start_lex_tracker(
                event.total or 0,
                secondary_label=str(secondary_label) if secondary_label else None,
            )
            return
        if event.stage == "lex_search_result" and event.current is not None:
            raw_count = event.extra.get("raw_count")
            deduplicated = event.extra.get("deduplicated_count")
            secondary = raw_count if raw_count is not None else deduplicated
            self._update_lex_tracker(
                event.current,
                secondary_count=int(secondary) if secondary is not None else None,
            )
            return
        if event.stage == "lex_search_complete":
            self._finish_lex_tracker()
            return
        if event.stage == "ai_assess_start":
            self._start_ai_tracker(event.total or 0)
            return
        if event.stage == "ai_assess_candidate" and event.current is not None:
            self._update_ai_tracker(event.current)
            return
        if event.stage == "ai_assess_complete":
            self._finish_ai_tracker()
            return
        if event.stage == "ai_triage_start":
            total = event.total or int(event.extra.get("candidate_count", 0))
            unit = str(event.extra.get("unit", "candidates"))
            self._start_ai_triage_tracker(total, unit=unit)
            return
        if event.stage == "ai_triage_batch" and event.current is not None:
            self._update_ai_triage_tracker(event.current)
            return
        if event.stage == "ai_triage_complete":
            self._finish_ai_triage_tracker()
            return
        if event.stage == "warning":
            self._finish_active_progress_line()
            self._plain_line(f"warning: {event.message}")
            self._refresh_active_tracker_line()
            return
        self._finish_active_progress_line()
        self._plain_line(event.message)

    def _handle_rich(self, event: DiscoveryProgressEvent) -> None:
        if event.stage == "build_query_plan" and _query_strings(event.extra):
            self._finish_active_progress_line()
            self._print_built_queries(event)
            return
        if event.stage == "lex_search_query":
            return
        if event.stage == "lex_search_start":
            secondary_label = event.extra.get("secondary_label")
            self._start_lex_tracker(
                event.total or 0,
                secondary_label=str(secondary_label) if secondary_label else None,
            )
            return
        if event.stage == "lex_search_result" and event.current is not None:
            raw_count = event.extra.get("raw_count")
            deduplicated = event.extra.get("deduplicated_count")
            secondary = raw_count if raw_count is not None else deduplicated
            self._update_lex_tracker(
                event.current,
                secondary_count=int(secondary) if secondary is not None else None,
            )
            return
        if event.stage == "lex_search_complete":
            self._finish_lex_tracker()
            return
        if event.stage == "ai_assess_start":
            self._start_ai_tracker(event.total or 0)
            return
        if event.stage == "ai_assess_candidate" and event.current is not None:
            self._update_ai_tracker(event.current)
            return
        if event.stage == "ai_assess_complete":
            self._finish_ai_tracker()
            return
        if event.stage == "ai_triage_start":
            total = event.total or int(event.extra.get("candidate_count", 0))
            unit = str(event.extra.get("unit", "candidates"))
            self._start_ai_triage_tracker(total, unit=unit)
            return
        if event.stage == "ai_triage_batch" and event.current is not None:
            self._update_ai_triage_tracker(event.current)
            return
        if event.stage == "ai_triage_complete":
            self._finish_ai_triage_tracker()
            return
        if event.stage == "warning":
            self._finish_active_progress_line()
            self.console.print(f"[yellow]Warning:[/] {event.message}")
            self._refresh_active_tracker_line()
            return

        self._finish_active_progress_line()
        style = "green" if event.stage in {"complete", "write_output"} else "cyan"
        self.console.print(Text(event.message, style=style))

    def _write_progress_line(self, line: str, *, final: bool = False) -> None:
        display = f"[law-discovery] {line}" if self.mode == OutputMode.PLAIN else line
        if not final and self._progress_line_width > len(display):
            display = display.ljust(self._progress_line_width)
        self._progress_line_width = max(self._progress_line_width, len(display))
        end = "\n" if final else "\r"
        self.console.print(
            display,
            markup=self.mode != OutputMode.PLAIN,
            end=end,
            highlight=False,
            soft_wrap=False,
        )

    def _finish_active_progress_line(self) -> None:
        if self._progress_line_width == 0:
            return
        self._progress_line_width = 0

    def _refresh_active_tracker_line(self) -> None:
        tracker = self._lex_tracker or self._ai_tracker or self._ai_triage_tracker
        if tracker is not None:
            self._write_progress_line(tracker.format_line())

    def _start_lex_tracker(
        self,
        total: int,
        *,
        secondary_label: str | None = None,
    ) -> None:
        self._finish_lex_tracker()
        self._lex_tracker = CliProgressTracker(
            label="Searching",
            unit="queries",
            total=total,
            secondary_label=secondary_label,
        )
        self._write_progress_line(self._lex_tracker.format_line())

    def _update_lex_tracker(
        self,
        completed: int,
        *,
        secondary_count: int | None = None,
    ) -> None:
        if self._lex_tracker is None:
            return
        self._lex_tracker.set_completed(completed)
        if secondary_count is not None:
            self._lex_tracker.set_secondary_count(secondary_count)
        self._write_progress_line(self._lex_tracker.format_line())

    def _finish_lex_tracker(self) -> None:
        if self._lex_tracker is None:
            return
        self._lex_tracker.set_completed(self._lex_tracker.total)
        self._write_progress_line(self._lex_tracker.format_line(), final=True)
        self._lex_tracker = None
        self._finish_active_progress_line()

    def _start_ai_tracker(self, total: int) -> None:
        self._finish_ai_tracker()
        self._ai_tracker = CliProgressTracker(label="Assessing", unit="candidates", total=total)
        self._write_progress_line(self._ai_tracker.format_line())

    def _update_ai_tracker(self, completed: int) -> None:
        if self._ai_tracker is None:
            return
        self._ai_tracker.set_completed(completed)
        self._write_progress_line(self._ai_tracker.format_line())

    def _finish_ai_tracker(self) -> None:
        if self._ai_tracker is None:
            return
        self._ai_tracker.set_completed(self._ai_tracker.total)
        self._write_progress_line(self._ai_tracker.format_line(), final=True)
        self._ai_tracker = None
        self._finish_active_progress_line()

    def _start_ai_triage_tracker(self, total: int, *, unit: str = "candidates") -> None:
        self._finish_ai_triage_tracker()
        self._ai_triage_tracker = CliProgressTracker(label="Triaging", unit=unit, total=total)
        self._write_progress_line(self._ai_triage_tracker.format_line())

    def _update_ai_triage_tracker(self, completed: int) -> None:
        if self._ai_triage_tracker is None:
            return
        self._ai_triage_tracker.set_completed(completed)
        self._write_progress_line(self._ai_triage_tracker.format_line())

    def _finish_ai_triage_tracker(self) -> None:
        if self._ai_triage_tracker is None:
            return
        self._ai_triage_tracker.set_completed(self._ai_triage_tracker.total)
        self._write_progress_line(self._ai_triage_tracker.format_line(), final=True)
        self._ai_triage_tracker = None
        self._finish_active_progress_line()

    def show_related_expansion_summary(
        self,
        run: RelatedSourceExpansionRun,
        output: Path,
        *,
        use_ai_triage: bool,
    ) -> None:
        if self.mode == OutputMode.QUIET:
            return

        metadata = run.metadata
        query_count = metadata.get("query_count", 0)
        raw_candidate_count = metadata.get("raw_candidate_count")
        relationship_type_counts = metadata.get("relationship_type_counts", {})
        confidence_counts = metadata.get("confidence_counts", {})
        related_source_review_counts = metadata.get("related_source_review_counts", {})
        relationship_review_counts = metadata.get("relationship_review_counts", {})
        orphan_related_source_count = metadata.get("orphan_related_source_count")
        ai_success = metadata.get("ai_triage_success_count")
        ai_failure = metadata.get("ai_triage_failure_count")

        if self.mode == OutputMode.PLAIN:
            self.console.print(f"[law-discovery] wrote {output}", markup=False)
            self.console.print(f"[law-discovery] category_id: {run.category_id}", markup=False)
            self.console.print(f"[law-discovery] seed sources: {len(run.seed_sources)}", markup=False)
            self.console.print(f"[law-discovery] queries: {query_count}", markup=False)
            if raw_candidate_count is not None:
                self.console.print(
                    f"[law-discovery] raw candidates: {raw_candidate_count}",
                    markup=False,
                )
            self.console.print(
                f"[law-discovery] related sources: {len(run.related_sources)}",
                markup=False,
            )
            self.console.print(
                f"[law-discovery] relationships: {len(run.relationships)}",
                markup=False,
            )
            if orphan_related_source_count is not None:
                self.console.print(
                    f"[law-discovery] orphan related sources: {orphan_related_source_count}",
                    markup=False,
                )
            if isinstance(related_source_review_counts, dict) and related_source_review_counts:
                self.console.print("[law-discovery] related source review:", markup=False)
                for status, count in related_source_review_counts.items():
                    if count:
                        self.console.print(f"[law-discovery]   {status}: {count}", markup=False)
            if isinstance(relationship_review_counts, dict) and relationship_review_counts:
                self.console.print("[law-discovery] relationship review:", markup=False)
                for status, count in relationship_review_counts.items():
                    if count:
                        self.console.print(f"[law-discovery]   {status}: {count}", markup=False)
            if isinstance(relationship_type_counts, dict) and relationship_type_counts:
                self.console.print("[law-discovery] relationship types:", markup=False)
                for rel_type, count in sorted(relationship_type_counts.items()):
                    self.console.print(f"[law-discovery]   {rel_type}: {count}", markup=False)
            if isinstance(confidence_counts, dict) and confidence_counts:
                self.console.print("[law-discovery] confidence:", markup=False)
                for level, count in confidence_counts.items():
                    if count:
                        self.console.print(f"[law-discovery]   {level}: {count}", markup=False)
            if use_ai_triage:
                self.console.print(
                    f"[law-discovery] AI relationship triage success/failure: "
                    f"{ai_success}/{ai_failure}",
                    markup=False,
                )
            self.console.print(f"[law-discovery] warnings: {len(run.warnings)}", markup=False)
            return

        table = Table(title="Related source expansion summary", show_header=True)
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        table.add_row("Output", str(output))
        table.add_row("category_id", run.category_id)
        table.add_row("Seed sources", str(len(run.seed_sources)))
        table.add_row("Queries", str(query_count))
        if raw_candidate_count is not None:
            table.add_row("Raw candidates", str(raw_candidate_count))
        table.add_row("Related sources", str(len(run.related_sources)))
        table.add_row("Relationships", str(len(run.relationships)))
        if orphan_related_source_count is not None:
            table.add_row("Orphan related sources", str(orphan_related_source_count))
        if isinstance(related_source_review_counts, dict):
            for status, count in related_source_review_counts.items():
                if count:
                    table.add_row(f"Related source review ({status})", str(count))
        if isinstance(relationship_review_counts, dict):
            for status, count in relationship_review_counts.items():
                if count:
                    table.add_row(f"Relationship review ({status})", str(count))
        if isinstance(relationship_type_counts, dict):
            for rel_type, count in sorted(relationship_type_counts.items()):
                table.add_row(f"Relationship type ({rel_type})", str(count))
        if isinstance(confidence_counts, dict):
            for level, count in confidence_counts.items():
                if count:
                    table.add_row(f"Confidence ({level})", str(count))
        if use_ai_triage:
            table.add_row("AI triage success batches", str(ai_success))
            table.add_row("AI triage failure batches", str(ai_failure))
        table.add_row("Warnings", str(len(run.warnings)))
        self.console.print(table)
