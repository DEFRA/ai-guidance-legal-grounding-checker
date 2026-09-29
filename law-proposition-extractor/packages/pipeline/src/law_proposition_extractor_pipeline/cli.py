import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import typer
from law_proposition_extractor_domain import ReviewStatus
from law_proposition_extractor_llm.settings import LLMSettings
from rich.console import Console
from rich.panel import Panel

from .cli_progress import pipeline_progress, print_completion_summary_table
from .cli_run_summary import build_cli_completion_summary
from .llm_extraction_config import (
    describe_llm_extraction_endpoint,
    format_llm_extraction_endpoint_line,
    resolve_extraction_fallback_for_run,
    resolve_extraction_mode_requested,
)


def _extraction_cache_retry_kwargs(
    *,
    retry_failed_extraction_cache: bool | None,
    ignore_failed_extraction_cache: bool,
    retry_failed_llm: bool | None,
) -> dict[str, bool | None]:
    if ignore_failed_extraction_cache and retry_failed_extraction_cache is True:
        raise typer.BadParameter(
            "Use either --ignore-failed-extraction-cache or --retry-failed-extraction-cache, not both."
        )
    return {
        "retry_failed_extraction_cache": retry_failed_extraction_cache,
        "ignore_failed_extraction_cache": ignore_failed_extraction_cache,
        "retry_failed_llm": retry_failed_llm,
    }


def _provider_failure_abort_kwargs(
    *,
    abort_on_provider_failure: bool | None,
    provider_failure_threshold: int | None,
    max_failed_extraction_jobs: int | None,
) -> dict[str, bool | int | None]:
    return {
        "abort_on_provider_failure": abort_on_provider_failure,
        "provider_failure_threshold": provider_failure_threshold,
        "max_failed_extraction_jobs": max_failed_extraction_jobs,
    }


def _extraction_output_mode_kwargs(
    *,
    extraction_output_mode: str | None,
    allow_output_mode_fallback: bool,
) -> dict[str, str | bool | None]:
    if extraction_output_mode is not None:
        mode = str(extraction_output_mode).strip()
        if mode not in {"json_object", "json_schema", "text_then_parse"}:
            raise typer.BadParameter(
                "--extraction-output-mode must be json_object, json_schema, or text_then_parse"
            )
    return {
        "extraction_output_mode": extraction_output_mode,
        "allow_output_mode_fallback": allow_output_mode_fallback,
    }


from .corpus_run_estimate import estimate_corpus_run_from_case
from .demo import build_demo_bundle
from .equine_corpus_workflow import prepare_case_data_for_equine_corpus, run_equine_corpus_export
from .equine_source_universe import (
    estimate_summary_from_universe_offline,
    load_equine_source_universe,
    materialize_case_from_universe_path,
)
from .extraction_batch import (
    AnthropicBatchLLMClient,
    BatchJobStore,
    PlannedExtractionRequest,
    import_frontier_batch_results,
    plan_frontier_batch_for_case,
)
from .file_input import load_case_file
from .linting import lint_export_dir
from .operations import OperationalStore
from .operations_clear import (
    ClearOperationsConfirmationError,
    UnsafeExportDirError,
    execute_clear_operations_all,
    execute_clear_operations_runs_only,
    format_clear_report,
)
from .pipeline_reviews import append_pipeline_review_decision
from .reviews import parse_edited_fields_payload
from .run_comparison import compare_export_dirs, write_comparison_summary
from .run_quality import build_run_quality_summary
from .runner import (
    apply_assessment_review_decision,
    export_case_file,
    export_run_file,
    run_case_file,
    run_registry_sources,
)
from .source_bundle_intake import (
    FullLawDiscoveryBundleRejectedError,
    IntakeBundlePlan,
    IntakeBundleSelection,
    SourceBundleIntakeError,
    format_intake_summary_lines,
    list_selected_source_titles,
    load_source_bundle,
    materialize_case_from_intake_bundle,
    plan_intake_bundle_dry_run,
    write_materialized_case,
)
from .run_persistence import (
    build_persisted_run_config,
    export_mismatch_messages,
    expects_persisted_run_layout,
    has_persisted_run_bundle,
    load_persisted_run_bundle,
    load_persisted_run_config,
    persist_run_outputs,
    planned_extraction_mode,
    rerun_extraction_warning,
    resolve_run_directory,
    run_bundle_path,
    validate_rerun_extraction_allowed,
)
from .run_status import build_run_status_report, format_path_mtime_iso, format_run_status_lines

app = typer.Typer(help="Run file-backed Law Proposition Extractor pipeline cases.")
console = Console()


def _persist_cli_run(
    *,
    output: str | Path,
    case_data: dict[str, Any],
    bundle: dict[str, Any],
    use_llm: bool,
    extraction_mode: str | None,
    extraction_fallback: str | None,
    extraction_execution_mode: str | None = None,
    divergence_reasoning: str | None = None,
    principal_only: bool | None = None,
    include_amendments: bool | None = None,
    include_revocations: bool | None = None,
    max_sources: int | None = None,
    source_sections: dict[str, Any] | None = None,
) -> Path:
    run_config = build_persisted_run_config(
        bundle=bundle,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        extraction_fallback=extraction_fallback,
        extraction_execution_mode=extraction_execution_mode,
        divergence_reasoning=divergence_reasoning,
        case_data=case_data,
        principal_only=principal_only,
        include_amendments=include_amendments,
        include_revocations=include_revocations,
        max_sources=max_sources,
        source_sections=source_sections,
    )
    return persist_run_outputs(
        output=output,
        case_data=case_data,
        bundle=bundle,
        run_config=run_config,
    )


def _print_export_completion(
    *,
    bundle: dict[str, Any],
    output_dir: str,
    source_path: str,
    title: str,
    source_bundle: dict[str, Any] | None = None,
    verbose: bool = False,
) -> None:
    rq = bundle.get("run_quality_summary")
    if not isinstance(rq, dict):
        rq = build_run_quality_summary(bundle)
    if source_bundle is not None:
        messages = export_mismatch_messages(source_bundle=source_bundle, exported_bundle=bundle)
        if messages:
            console.print(
                f"[bold red]Refusing to export:[/bold red] export would change {' and '.join(messages)}."
            )
            raise typer.Exit(code=1)
    summary = build_cli_completion_summary(
        bundle, quality_summary=rq, output_dir=output_dir
    )
    print_completion_summary_table(console, summary, verbose=verbose)
    console.print(Panel.fit(title, style="green"))
    console.print(f"Output directory: [bold]{output_dir}[/bold]")
    console.print(f"Source: [bold]{source_path}[/bold]")
    console.print(
        f"Assessments exported: [bold]{len(bundle.get('divergence_assessments') or [])}[/bold]"
    )


def _effective_extraction_mode(case_data: dict, cli_mode: str | None) -> str:
    if cli_mode:
        return str(cli_mode).strip()
    cx = case_data.get("extraction") if isinstance(case_data.get("extraction"), dict) else {}
    return str(cx.get("mode") or "heuristic").strip()


def _large_legislation_universe_case(case_data: dict) -> bool:
    g = case_data.get("corpus_run_guard")
    if isinstance(g, dict) and str(g.get("tier") or "") == "full_universe":
        return True
    srcs = case_data.get("sources") or []
    if len(srcs) < 18:
        return False
    return all(
        isinstance(s, dict) and str(s.get("authority") or "") == "legislation_gov_uk" for s in srcs
    )


def _maybe_confirm_large_corpus_run(
    *,
    case_data: dict,
    use_llm: bool,
    extraction_mode: str | None,
    accept_large: bool,
    offline_chars_per_instrument: int = 95_000,
) -> None:
    if not use_llm or accept_large:
        return
    if _effective_extraction_mode(case_data, extraction_mode) != "frontier":
        return
    if not _large_legislation_universe_case(case_data):
        return
    est = estimate_corpus_run_from_case(
        case_data,
        extraction_mode="frontier",
        offline_chars_per_instrument=offline_chars_per_instrument,
    )
    console.print(
        Panel.fit(
            "[bold yellow]Large corpus run[/bold yellow]\n"
            "This case queues many full statutory bodies for frontier extraction — expect high cost "
            "and noise. Prefer staged profiles under examples/equine_*_case.json.\n\n"
            f"Offline sizing heuristic: ~{est['estimated_llm_invocations']} LLM calls (lower bound), "
            f"cost class: {est['cost_class']}, legislation sources: {est['source_count']}.",
            style="yellow",
        )
    )
    if not typer.confirm("Proceed with frontier extraction on this corpus?", default=False):
        raise typer.Abort()


@app.command("demo")
def demo(
    use_llm: bool = typer.Option(False, help="Route extraction/reasoning via LiteLLM."),
) -> None:
    bundle = build_demo_bundle(use_llm=use_llm)
    console.print(Panel.fit("Law Proposition Extractor demo bundle", style="green"))
    console.print_json(json.dumps(bundle))


@app.command("run-case")
def run_case(
    case_path: str = typer.Argument(
        ...,
        help="Path to a Law Proposition Extractor case JSON file (topic/cluster/sources). Not an Law Discovery source bundle — use run-bundle for intake JSON.",
    ),
    use_llm: bool = typer.Option(False, help="Route extraction/reasoning via LiteLLM."),
    extraction_mode: str | None = typer.Option(
        None,
        "--extraction-mode",
        help="Proposition extraction: heuristic | local | frontier (default: heuristic, or local with --use-llm).",
    ),
    extraction_execution_mode: str | None = typer.Option(
        None,
        "--extraction-execution-mode",
        help="interactive | batch (batch valid with extraction_mode=frontier).",
    ),
    extraction_fallback: str = typer.Option(
        "fallback",
        "--extraction-fallback",
        help="fallback | fail_closed | mark_needs_review",
    ),
    divergence_reasoning: str | None = typer.Option(
        None,
        "--divergence-reasoning",
        help="Divergence rationale: none | frontier (default: frontier with --use-llm).",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
    derived_cache_dir: str | None = typer.Option(
        None,
        "--derived-cache-dir",
        help="Explicit derived artifact cache directory.",
    ),
    retry_failed_extraction_cache: bool | None = typer.Option(
        None,
        "--retry-failed-extraction-cache/--no-retry-failed-extraction-cache",
        help="Re-call the model for chunks cached as failed (default: on for fail_closed local/frontier).",
    ),
    ignore_failed_extraction_cache: bool = typer.Option(
        False,
        "--ignore-failed-extraction-cache",
        help="Reuse cached failed chunk entries without LLM calls (zero-attempt runs).",
    ),
    retry_failed_llm: bool | None = typer.Option(
        None,
        "--retry-failed-llm/--no-retry-failed-llm",
        help="Alias for --retry-failed-extraction-cache.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress, summary table, and banner."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Per-job extraction locator lines with progress prefix.",
    ),
    very_verbose: bool = typer.Option(
        False,
        "--very-verbose",
        help="Full multi-line progress snapshot on each LLM call (very noisy).",
    ),
    progress_every: int = typer.Option(
        10,
        "--progress-every",
        min=1,
        help="Print a checkpoint line every N completed extraction jobs (local/frontier).",
    ),
    accept_large_corpus_run: bool = typer.Option(
        False,
        "--i-accept-large-corpus-run",
        help="Acknowledge frontier extraction over a very large legislation universe (skips confirmation).",
    ),
    extraction_output_mode: str | None = typer.Option(
        None,
        "--extraction-output-mode",
        help="LLM structured output: json_object | json_schema | text_then_parse (default: local→json_schema when supported).",
    ),
    allow_output_mode_fallback: bool = typer.Option(
        False,
        "--allow-output-mode-fallback/--no-allow-output-mode-fallback",
        help="Fall back to json_object when json_schema is unsupported or rejected by the provider.",
    ),
    abort_on_provider_failure: bool = typer.Option(
        True,
        "--abort-on-provider-failure/--no-abort-on-provider-failure",
        help="Fail fast when billing/auth or repeated transient provider errors occur during extraction.",
    ),
    provider_failure_threshold: int = typer.Option(
        5,
        "--provider-failure-threshold",
        min=1,
        help="Consecutive transient provider failures (rate limit/transport) before aborting extraction.",
    ),
    max_failed_extraction_jobs: int | None = typer.Option(
        None,
        "--max-failed-extraction-jobs",
        min=1,
        help="Optional hard cap on failed extraction jobs before abort (in addition to rate/consecutive rules).",
    ),
) -> None:
    case_payload = load_case_file(case_path)
    _maybe_confirm_large_corpus_run(
        case_data=case_payload,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        accept_large=accept_large_corpus_run,
    )
    cache_retry = _extraction_cache_retry_kwargs(
        retry_failed_extraction_cache=retry_failed_extraction_cache,
        ignore_failed_extraction_cache=ignore_failed_extraction_cache,
        retry_failed_llm=retry_failed_llm,
    )
    output_mode_kwargs = _extraction_output_mode_kwargs(
        extraction_output_mode=extraction_output_mode,
        allow_output_mode_fallback=allow_output_mode_fallback,
    )
    provider_abort_kwargs = _provider_failure_abort_kwargs(
        abort_on_provider_failure=abort_on_provider_failure,
        provider_failure_threshold=provider_failure_threshold,
        max_failed_extraction_jobs=max_failed_extraction_jobs,
    )
    with pipeline_progress(
        console,
        quiet=quiet,
        verbose=verbose,
        very_verbose=very_verbose,
        progress_every=progress_every,
    ) as progress:
        bundle = run_case_file(
            case_path=case_path,
            use_llm=use_llm,
            extraction_mode=extraction_mode,
            extraction_execution_mode=extraction_execution_mode,
            extraction_fallback=extraction_fallback,
            divergence_reasoning=divergence_reasoning,
            source_cache_dir=source_cache_dir,
            derived_cache_dir=derived_cache_dir,
            progress=progress,
            progress_every=progress_every,
            **cache_retry,
            **output_mode_kwargs,
            **provider_abort_kwargs,
        )
    _persist_cli_run(
        output=resolve_run_directory(case_path),
        case_data=case_payload,
        bundle=bundle,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        extraction_fallback=extraction_fallback,
        extraction_execution_mode=extraction_execution_mode,
        divergence_reasoning=divergence_reasoning,
    )
    if not quiet:
        quality = build_run_quality_summary(bundle)
        summary = build_cli_completion_summary(
            bundle, quality_summary=quality, output_dir=None
        )
        print_completion_summary_table(
            console, summary, verbose=verbose or very_verbose
        )
        console.print(Panel.fit(f"Ran case: {case_path}", style="green"))
    console.print_json(json.dumps(bundle))


@app.command("export-case")
def export_case(
    case_path: str = typer.Argument(
        ...,
        help="Run directory or case.json from a prior run-bundle/run-case.",
    ),
    output_dir: str = typer.Option(
        "dist/static-report",
        "--output-dir",
        "--output",
        help="Directory for static bundle output (--output aliases run-bundle flag name).",
    ),
    rerun: bool = typer.Option(
        False,
        "--rerun",
        help="Re-run extraction before export. Requires explicit --extraction-mode when a prior run exists.",
    ),
    use_llm: bool = typer.Option(False, help="Route extraction/reasoning via LiteLLM (only with --rerun)."),
    extraction_mode: str | None = typer.Option(
        None,
        "--extraction-mode",
        help="Proposition extraction: heuristic | local | frontier (required with --rerun when a prior run exists).",
    ),
    extraction_execution_mode: str | None = typer.Option(
        None,
        "--extraction-execution-mode",
        help="interactive | batch (batch valid with extraction_mode=frontier).",
    ),
    extraction_fallback: str = typer.Option(
        "fallback",
        "--extraction-fallback",
        help="fallback | fail_closed | mark_needs_review",
    ),
    divergence_reasoning: str | None = typer.Option(
        None,
        "--divergence-reasoning",
        help="none | frontier",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
    derived_cache_dir: str | None = typer.Option(
        None,
        "--derived-cache-dir",
        help="Explicit derived artifact cache directory.",
    ),
    retry_failed_extraction_cache: bool | None = typer.Option(
        None,
        "--retry-failed-extraction-cache/--no-retry-failed-extraction-cache",
        help="Re-call the model for chunks cached as failed (default: on for fail_closed local/frontier).",
    ),
    ignore_failed_extraction_cache: bool = typer.Option(
        False,
        "--ignore-failed-extraction-cache",
        help="Reuse cached failed chunk entries without LLM calls (zero-attempt runs).",
    ),
    retry_failed_llm: bool | None = typer.Option(
        None,
        "--retry-failed-llm/--no-retry-failed-llm",
        help="Alias for --retry-failed-extraction-cache.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress, summary table, and banner."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Per-job extraction locator lines with progress prefix.",
    ),
    very_verbose: bool = typer.Option(
        False,
        "--very-verbose",
        help="Full multi-line progress snapshot on each LLM call (very noisy).",
    ),
    progress_every: int = typer.Option(
        10,
        "--progress-every",
        min=1,
        help="Print a checkpoint line every N completed extraction jobs (local/frontier).",
    ),
    accept_large_corpus_run: bool = typer.Option(
        False,
        "--i-accept-large-corpus-run",
        help="Acknowledge frontier extraction over a very large legislation universe (skips confirmation).",
    ),
) -> None:
    """Export a persisted run without re-running extraction.

    When ``run_bundle.json`` exists, writes the static bundle from that run.
    Use ``run-and-export-case`` or ``export-case --rerun`` to regenerate extraction outputs.
    """
    case_payload = load_case_file(case_path)
    persisted = load_persisted_run_config(case_payload)
    has_persisted = has_persisted_run_bundle(case_path)

    if (
        expects_persisted_run_layout(case_path)
        and not has_persisted
        and not rerun
    ):
        console.print(
            "[bold red]No run_bundle.json found in this run directory.[/bold red] "
            "Re-run with `run-case`/`run-bundle` (now persists run outputs), "
            "or use `run-and-export-case` with explicit `--extraction-mode`."
        )
        raise typer.Exit(code=1)

    if has_persisted and not rerun:
        source_bundle = load_persisted_run_bundle(case_path)
        with pipeline_progress(
            console,
            quiet=quiet,
            verbose=verbose,
            very_verbose=very_verbose,
            progress_every=progress_every,
        ) as progress:
            bundle = export_run_file(
                run_path=case_path,
                output_dir=output_dir,
                progress=progress,
            )
        if not quiet:
            _print_export_completion(
                bundle=bundle,
                output_dir=output_dir,
                source_path=case_path,
                title=f"Exported persisted run: {case_path}",
                source_bundle=source_bundle,
                verbose=verbose or very_verbose,
            )
        return

    if persisted is not None and not rerun and not has_persisted:
        console.print(
            "[bold red]Case metadata records a prior run but run_bundle.json is missing.[/bold red] "
            "Re-run with `run-case`/`run-bundle`, or pass `--rerun` with explicit `--extraction-mode`."
        )
        raise typer.Exit(code=1)

    if rerun and persisted is not None:
        try:
            validate_rerun_extraction_allowed(
                persisted=persisted,
                rerun=True,
                use_llm=use_llm,
                extraction_mode=extraction_mode,
                case_data=case_payload,
            )
        except ValueError as exc:
            console.print(f"[bold red]{exc}[/bold red]")
            raise typer.Exit(code=1) from exc

    planned_mode = planned_extraction_mode(
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        case_data=case_payload,
    )
    if not quiet:
        console.print(f"[yellow]{rerun_extraction_warning(planned_mode)}[/yellow]")

    _maybe_confirm_large_corpus_run(
        case_data=case_payload,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        accept_large=accept_large_corpus_run,
    )
    cache_retry = _extraction_cache_retry_kwargs(
        retry_failed_extraction_cache=retry_failed_extraction_cache,
        ignore_failed_extraction_cache=ignore_failed_extraction_cache,
        retry_failed_llm=retry_failed_llm,
    )
    try:
        with pipeline_progress(
            console,
            quiet=quiet,
            verbose=verbose,
            very_verbose=very_verbose,
            progress_every=progress_every,
        ) as progress:
            bundle = export_case_file(
                case_path=case_path,
                output_dir=output_dir,
                use_llm=use_llm,
                extraction_mode=extraction_mode,
                extraction_execution_mode=extraction_execution_mode,
                extraction_fallback=extraction_fallback,
                divergence_reasoning=divergence_reasoning,
                source_cache_dir=source_cache_dir,
                derived_cache_dir=derived_cache_dir,
                progress=progress,
                progress_every=progress_every,
                rerun=rerun or not has_persisted,
                **cache_retry,
            )
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(code=1) from exc
    if not quiet:
        _print_export_completion(
            bundle=bundle,
            output_dir=output_dir,
            source_path=case_path,
            title=f"Exported case: {case_path}",
            verbose=verbose or very_verbose,
        )


@app.command("run-status")
def run_status_cmd(
    run_path: str = typer.Argument(
        ...,
        help="Run directory or case.json from run-case/run-bundle.",
    ),
) -> None:
    """Summarise a persisted run directory and suggest the next operator command."""
    report = build_run_status_report(run_path)
    for line in format_run_status_lines(report):
        console.print(line)


@app.command("export-run")
def export_run_cmd(
    run_path: str = typer.Argument(
        ...,
        help="Run directory or case.json containing run_bundle.json from run-case/run-bundle.",
    ),
    output_dir: str = typer.Option(
        "dist/static-report",
        "--output-dir",
        "--output",
        help="Directory for static bundle output.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress, summary table, and banner."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Per-job extraction locator lines with progress prefix.",
    ),
    very_verbose: bool = typer.Option(
        False,
        "--very-verbose",
        help="Full multi-line progress snapshot on each LLM call (very noisy).",
    ),
    progress_every: int = typer.Option(
        10,
        "--progress-every",
        min=1,
        help="Print a checkpoint line every N completed extraction jobs (local/frontier).",
    ),
    auto_repair: bool = typer.Option(
        False,
        "--auto-repair",
        help="After export, run deterministic repair passes and acceptance checks on the output.",
    ),
    acceptance_report: bool = typer.Option(
        False,
        "--acceptance-report",
        help="Write EXPORT_ACCEPTANCE.md and export_acceptance.json (implies repair when combined with --auto-repair).",
    ),
    repair_mode: str = typer.Option(
        "deterministic",
        "--repair-mode",
        help="deterministic | llm | both — coverage fragment repair requires llm or both.",
    ),
    max_repair_attempts: int = typer.Option(
        2,
        "--max-repair-attempts",
        min=1,
        help="Maximum rounds of deterministic repair passes.",
    ),
    strict_acceptance: bool = typer.Option(
        False,
        "--strict-acceptance",
        help="Exit non-zero unless acceptance status is accepted (not accepted_with_warnings).",
    ),
    allow_incomplete_export: bool = typer.Option(
        False,
        "--allow-incomplete-export",
        help="Export even when extraction aborted or is inferred incomplete (not benchmarkable).",
    ),
) -> None:
    """Export an existing persisted run without re-running extraction."""
    if repair_mode not in {"deterministic", "llm", "both"}:
        raise typer.BadParameter("--repair-mode must be deterministic, llm, or both")
    if not has_persisted_run_bundle(run_path):
        console.print(
            "[bold red]No run_bundle.json found.[/bold red] "
            "Run `run-case` or `run-bundle` first, then export with `export-run`."
        )
        raise typer.Exit(code=1)
    bundle_file = run_bundle_path(resolve_run_directory(run_path))
    if not quiet:
        console.print(
            f"Exporting persisted run_bundle.json last modified at "
            f"{format_path_mtime_iso(bundle_file)}"
        )
    source_bundle = load_persisted_run_bundle(run_path)
    with pipeline_progress(
        console,
        quiet=quiet,
        verbose=verbose,
        very_verbose=very_verbose,
        progress_every=progress_every,
    ) as progress:
        try:
            bundle = export_run_file(
                run_path=run_path,
                output_dir=output_dir,
                progress=progress,
                allow_incomplete_export=allow_incomplete_export,
            )
        except ValueError as exc:
            console.print(f"[bold red]{exc}[/bold red]")
            raise typer.Exit(code=1) from exc
    if auto_repair or acceptance_report:
        from .export_acceptance import (
            acceptance_exit_code,
            print_acceptance_console_summary,
            run_export_acceptance_workflow,
        )

        report = run_export_acceptance_workflow(
            export_dir=output_dir,
            bundle=bundle,
            auto_repair=auto_repair or acceptance_report,
            acceptance_report=acceptance_report,
            repair_mode=repair_mode,  # type: ignore[arg-type]
            max_repair_attempts=max_repair_attempts,
            strict_acceptance=strict_acceptance,
            use_llm_coverage=repair_mode in {"llm", "both"},
        )
        if not quiet:
            print_acceptance_console_summary(report)
        code = acceptance_exit_code(report, strict=strict_acceptance)
        if code != 0:
            raise typer.Exit(code=code)
    if not quiet:
        _print_export_completion(
            bundle=bundle,
            output_dir=output_dir,
            source_path=run_path,
            title=f"Exported persisted run: {run_path}",
            source_bundle=source_bundle,
            verbose=verbose or very_verbose,
        )


@app.command("accept-export")
def accept_export_cmd(
    export_dir: str = typer.Option(
        ...,
        "--export-dir",
        help="Existing export bundle to normalise, repair, and accept.",
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        help="Write accepted export here (default: repair in place on --export-dir).",
    ),
    repair_mode: str = typer.Option(
        "both",
        "--repair-mode",
        help="deterministic | llm | both",
    ),
    max_repair_attempts: int = typer.Option(
        2,
        "--max-repair-attempts",
        min=1,
    ),
    strict_acceptance: bool = typer.Option(
        False,
        "--strict-acceptance",
    ),
    no_repair: bool = typer.Option(
        False,
        "--no-repair",
        help="Run verification and acceptance only (no repair passes).",
    ),
) -> None:
    """Run post-export repair-and-acceptance on an existing static bundle."""
    if repair_mode not in {"deterministic", "llm", "both"}:
        raise typer.BadParameter("--repair-mode must be deterministic, llm, or both")
    from .export_acceptance import (
        acceptance_exit_code,
        print_acceptance_console_summary,
        run_export_acceptance_workflow,
    )

    report = run_export_acceptance_workflow(
        export_dir=export_dir,
        output_dir=output_dir or export_dir,
        auto_repair=not no_repair,
        acceptance_report=True,
        repair_mode=repair_mode,  # type: ignore[arg-type]
        max_repair_attempts=max_repair_attempts,
        strict_acceptance=strict_acceptance,
        use_llm_coverage=repair_mode in {"llm", "both"},
    )
    print_acceptance_console_summary(report)
    raise typer.Exit(code=acceptance_exit_code(report, strict=strict_acceptance))


@app.command("run-and-export-case")
def run_and_export_case(
    case_path: str = typer.Argument(..., help="Path to the input case JSON file or run directory."),
    output_dir: str = typer.Option(
        "dist/static-report",
        "--output-dir",
        "--output",
        help="Directory for static bundle output.",
    ),
    use_llm: bool = typer.Option(False, help="Route extraction/reasoning via LiteLLM."),
    extraction_mode: str | None = typer.Option(
        None,
        "--extraction-mode",
        help="Proposition extraction: heuristic | local | frontier (required when re-exporting a prior LLM run).",
    ),
    extraction_execution_mode: str | None = typer.Option(
        None,
        "--extraction-execution-mode",
        help="interactive | batch (batch valid with extraction_mode=frontier).",
    ),
    extraction_fallback: str = typer.Option(
        "fallback",
        "--extraction-fallback",
        help="fallback | fail_closed | mark_needs_review",
    ),
    divergence_reasoning: str | None = typer.Option(
        None,
        "--divergence-reasoning",
        help="none | frontier",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
    derived_cache_dir: str | None = typer.Option(
        None,
        "--derived-cache-dir",
        help="Explicit derived artifact cache directory.",
    ),
    retry_failed_extraction_cache: bool | None = typer.Option(
        None,
        "--retry-failed-extraction-cache/--no-retry-failed-extraction-cache",
        help="Re-call the model for chunks cached as failed (default: on for fail_closed local/frontier).",
    ),
    ignore_failed_extraction_cache: bool = typer.Option(
        False,
        "--ignore-failed-extraction-cache",
        help="Reuse cached failed chunk entries without LLM calls (zero-attempt runs).",
    ),
    retry_failed_llm: bool | None = typer.Option(
        None,
        "--retry-failed-llm/--no-retry-failed-llm",
        help="Alias for --retry-failed-extraction-cache.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress, summary table, and banner."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Per-job extraction locator lines with progress prefix.",
    ),
    very_verbose: bool = typer.Option(
        False,
        "--very-verbose",
        help="Full multi-line progress snapshot on each LLM call (very noisy).",
    ),
    progress_every: int = typer.Option(
        10,
        "--progress-every",
        min=1,
        help="Print a checkpoint line every N completed extraction jobs (local/frontier).",
    ),
    accept_large_corpus_run: bool = typer.Option(
        False,
        "--i-accept-large-corpus-run",
        help="Acknowledge frontier extraction over a very large legislation universe (skips confirmation).",
    ),
    abort_on_provider_failure: bool = typer.Option(
        True,
        "--abort-on-provider-failure/--no-abort-on-provider-failure",
        help="Fail fast when billing/auth or repeated transient provider errors occur during extraction.",
    ),
    provider_failure_threshold: int = typer.Option(
        5,
        "--provider-failure-threshold",
        min=1,
        help="Consecutive transient provider failures before aborting extraction.",
    ),
    max_failed_extraction_jobs: int | None = typer.Option(
        None,
        "--max-failed-extraction-jobs",
        min=1,
        help="Optional hard cap on failed extraction jobs before abort.",
    ),
    allow_incomplete_export: bool = typer.Option(
        False,
        "--allow-incomplete-export",
        help="Export even when extraction is incomplete (not benchmarkable).",
    ),
) -> None:
    """Run extraction from a case file and export the static bundle (always re-runs the pipeline)."""
    case_payload = load_case_file(case_path)
    persisted = load_persisted_run_config(case_payload)
    if persisted is not None:
        try:
            validate_rerun_extraction_allowed(
                persisted=persisted,
                rerun=True,
                use_llm=use_llm,
                extraction_mode=extraction_mode,
                case_data=case_payload,
            )
        except ValueError as exc:
            console.print(f"[bold red]{exc}[/bold red]")
            raise typer.Exit(code=1) from exc

    planned_mode = planned_extraction_mode(
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        case_data=case_payload,
    )
    if not quiet:
        console.print(f"[yellow]{rerun_extraction_warning(planned_mode)}[/yellow]")

    _maybe_confirm_large_corpus_run(
        case_data=case_payload,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        accept_large=accept_large_corpus_run,
    )
    cache_retry = _extraction_cache_retry_kwargs(
        retry_failed_extraction_cache=retry_failed_extraction_cache,
        ignore_failed_extraction_cache=ignore_failed_extraction_cache,
        retry_failed_llm=retry_failed_llm,
    )
    provider_abort_kwargs = _provider_failure_abort_kwargs(
        abort_on_provider_failure=abort_on_provider_failure,
        provider_failure_threshold=provider_failure_threshold,
        max_failed_extraction_jobs=max_failed_extraction_jobs,
    )
    try:
        with pipeline_progress(
            console,
            quiet=quiet,
            verbose=verbose,
            very_verbose=very_verbose,
            progress_every=progress_every,
        ) as progress:
            bundle = export_case_file(
                case_path=case_path,
                output_dir=output_dir,
                use_llm=use_llm,
                extraction_mode=extraction_mode,
                extraction_execution_mode=extraction_execution_mode,
                extraction_fallback=extraction_fallback,
                divergence_reasoning=divergence_reasoning,
                source_cache_dir=source_cache_dir,
                derived_cache_dir=derived_cache_dir,
                progress=progress,
                progress_every=progress_every,
                rerun=True,
                allow_incomplete_export=allow_incomplete_export,
                **cache_retry,
                **provider_abort_kwargs,
            )
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(code=1) from exc
    if not quiet:
        _print_export_completion(
            bundle=bundle,
            output_dir=output_dir,
            source_path=case_path,
            title=f"Ran and exported case: {case_path}",
            verbose=verbose or very_verbose,
        )


def _intake_bundle_selection(
    *,
    principal_only: bool,
    include_amendments: bool,
    include_revocations: bool,
    max_sources: int | None,
    allow_full_law_discovery_bundle: bool,
) -> IntakeBundleSelection:
    return IntakeBundleSelection(
        principal_only=principal_only,
        include_amendments=include_amendments,
        include_revocations=include_revocations,
        max_sources=max_sources,
        allow_full_law_discovery_bundle=allow_full_law_discovery_bundle,
    )


def _print_intake_bundle_summary(
    bundle_payload: dict[str, Any],
    plan: IntakeBundlePlan,
    *,
    selection: IntakeBundleSelection,
    output: str | None = None,
    dry_run: bool = False,
) -> None:
    console.print(Panel.fit("[bold]Law Discovery Law Proposition Extractor intake bundle[/bold]", style="cyan"))
    for line in format_intake_summary_lines(bundle_payload, plan, selection=selection):
        console.print(line)
    titles = list_selected_source_titles(bundle_payload, selection)
    if titles:
        console.print("[bold]Sources to process:[/bold]")
        for idx, title in enumerate(titles, start=1):
            console.print(f"  {idx}. {title}")
    if output is not None:
        label = "Intended case output" if dry_run else "Case output"
        console.print(f"{label}: [bold]{output}[/bold]")
    if dry_run:
        console.print("[dim]Dry run — no pipeline execution or LLM calls.[/dim]")


@app.command("run-bundle")
def run_bundle(
    source_bundle_json: str = typer.Argument(
        ...,
        help="Path to Law Discovery Law Proposition Extractor intake source bundle JSON (metadata.intake.kind=judit_intake).",
    ),
    output: str = typer.Option(
        ...,
        "--output",
        help="Law Proposition Extractor case directory (writes case.json) or path ending in .json.",
    ),
    use_llm: bool = typer.Option(False, help="Route extraction/reasoning via LiteLLM."),
    extraction_mode: str | None = typer.Option(
        None,
        "--extraction-mode",
        help="Proposition extraction: heuristic | local | frontier.",
    ),
    extraction_execution_mode: str | None = typer.Option(
        None,
        "--extraction-execution-mode",
        help="interactive | batch (batch valid with extraction_mode=frontier).",
    ),
    extraction_fallback: str | None = typer.Option(
        None,
        "--extraction-fallback",
        help="fallback | fail_closed | mark_needs_review (default: fail_closed with --use-llm, else fallback).",
    ),
    divergence_reasoning: str | None = typer.Option(
        None,
        "--divergence-reasoning",
        help="none | frontier",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
    derived_cache_dir: str | None = typer.Option(
        None,
        "--derived-cache-dir",
        help="Explicit derived artifact cache directory.",
    ),
    retry_failed_extraction_cache: bool | None = typer.Option(
        None,
        "--retry-failed-extraction-cache/--no-retry-failed-extraction-cache",
        help="Re-call the model for chunks cached as failed (default: on for fail_closed local/frontier).",
    ),
    ignore_failed_extraction_cache: bool = typer.Option(
        False,
        "--ignore-failed-extraction-cache",
        help="Reuse cached failed chunk entries without LLM calls (zero-attempt runs).",
    ),
    retry_failed_llm: bool | None = typer.Option(
        None,
        "--retry-failed-llm/--no-retry-failed-llm",
        help="Alias for --retry-failed-extraction-cache.",
    ),
    abort_on_provider_failure: bool = typer.Option(
        True,
        "--abort-on-provider-failure/--no-abort-on-provider-failure",
        help="Fail fast when billing/auth or repeated transient provider errors occur during extraction.",
    ),
    provider_failure_threshold: int = typer.Option(
        5,
        "--provider-failure-threshold",
        min=1,
        help="Consecutive transient provider failures before aborting extraction.",
    ),
    max_failed_extraction_jobs: int | None = typer.Option(
        None,
        "--max-failed-extraction-jobs",
        min=1,
        help="Optional hard cap on failed extraction jobs before abort.",
    ),
    principal_only: bool = typer.Option(
        True,
        "--principal-only/--no-principal-only",
        help="Process principal_sources only (default for first extraction run).",
    ),
    include_amendments: bool = typer.Option(
        False,
        "--include-amendments",
        help="Also process amending_sources from the intake bundle.",
    ),
    include_revocations: bool = typer.Option(
        False,
        "--include-revocations",
        help="Also process revocation_sources from the intake bundle.",
    ),
    max_sources: int | None = typer.Option(
        None,
        "--max-sources",
        min=1,
        help="Cap total selected sources after role filtering.",
    ),
    allow_full_law_discovery_bundle: bool = typer.Option(
        False,
        "--allow-full-law-discovery-bundle", "--allow-full-ada-bundle",  # COMPAT_LEGACY_NAME
        help="Allow a full reviewed Law Discovery bundle (contextual/rejected populations present).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print source counts and estimated extraction batches without running the pipeline.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress, summary table, and banner."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Print extra per-source diagnostic lines during extraction."
    ),
    very_verbose: bool = typer.Option(
        False,
        "--very-verbose",
        help="Full multi-line progress snapshot on each LLM call (very noisy).",
    ),
    progress_every: int = typer.Option(
        10,
        "--progress-every",
        min=1,
        help="Print a checkpoint line every N completed extraction jobs (local/frontier).",
    ),
    accept_large_corpus_run: bool = typer.Option(
        False,
        "--i-accept-large-corpus-run",
        help="Acknowledge frontier extraction over a very large legislation universe (skips confirmation).",
    ),
) -> None:
    """Materialise a Law Proposition Extractor case from an Law Discovery intake bundle, then run the pipeline."""
    selection = _intake_bundle_selection(
        principal_only=principal_only,
        include_amendments=include_amendments,
        include_revocations=include_revocations,
        max_sources=max_sources,
        allow_full_law_discovery_bundle=allow_full_law_discovery_bundle,
    )
    try:
        bundle_payload = load_source_bundle(source_bundle_json)
    except (FullLawDiscoveryBundleRejectedError, SourceBundleIntakeError) as exc:
        console.print(f"[bold red]Refused:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    try:
        plan = plan_intake_bundle_dry_run(bundle_payload, selection)
    except FullLawDiscoveryBundleRejectedError as exc:
        console.print(f"[bold red]Refused:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_intake_bundle_summary(
        bundle_payload,
        plan,
        selection=selection,
        output=output,
        dry_run=dry_run,
    )
    if dry_run:
        return

    try:
        case_payload = materialize_case_from_intake_bundle(bundle_payload, selection)
    except FullLawDiscoveryBundleRejectedError as exc:
        console.print(f"[bold red]Refused:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    case_json_path = write_materialized_case(case_payload, output)
    console.print(f"Wrote case file: [bold]{case_json_path}[/bold]")

    _maybe_confirm_large_corpus_run(
        case_data=case_payload,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        accept_large=accept_large_corpus_run,
    )

    resolved_fallback = resolve_extraction_fallback_for_run(
        use_llm=use_llm, extraction_fallback=extraction_fallback
    )
    ext_mode_planned = resolve_extraction_mode_requested(
        use_llm=use_llm, extraction_mode=extraction_mode, case_data=case_payload
    )
    if ext_mode_planned in {"local", "frontier"}:
        llm_settings = LLMSettings()
        endpoint = describe_llm_extraction_endpoint(ext_mode_planned, llm_settings)  # type: ignore[arg-type]
        console.print(
            f"[bold]LLM extraction endpoint:[/bold] {format_llm_extraction_endpoint_line(endpoint)}"
        )
        if use_llm and extraction_fallback is None:
            console.print(
                "[dim]--extraction-fallback not set; using fail_closed (no heuristic fallback on model failure).[/dim]"
            )

    cache_retry = _extraction_cache_retry_kwargs(
        retry_failed_extraction_cache=retry_failed_extraction_cache,
        ignore_failed_extraction_cache=ignore_failed_extraction_cache,
        retry_failed_llm=retry_failed_llm,
    )
    provider_abort_kwargs = _provider_failure_abort_kwargs(
        abort_on_provider_failure=abort_on_provider_failure,
        provider_failure_threshold=provider_failure_threshold,
        max_failed_extraction_jobs=max_failed_extraction_jobs,
    )
    try:
        with pipeline_progress(
            console,
            quiet=quiet,
            verbose=verbose,
            very_verbose=very_verbose,
            progress_every=progress_every,
        ) as progress:
            bundle = run_case_file(
                case_path=str(case_json_path),
                use_llm=use_llm,
                extraction_mode=extraction_mode,
                extraction_execution_mode=extraction_execution_mode,
                extraction_fallback=resolved_fallback,
                divergence_reasoning=divergence_reasoning,
                source_cache_dir=source_cache_dir,
                derived_cache_dir=derived_cache_dir,
                progress=progress,
                progress_every=progress_every,
                **cache_retry,
                **provider_abort_kwargs,
            )
    except RuntimeError as exc:
        msg = str(exc)
        lower = msg.lower()
        if "preflight failed" in lower:
            console.print(f"[bold red]LLM preflight failed:[/bold red] {exc}")
            raise typer.Exit(code=1) from exc
        if "extraction_plan_failed:" in lower:
            console.print(f"[bold red]Extraction plan failed:[/bold red] {exc}")
            raise typer.Exit(code=1) from exc
        if "fail_closed" in lower and "extraction produced 0 propositions" in lower:
            console.print(f"[bold red]LLM extraction failed (fail_closed):[/bold red] {exc}")
            raise typer.Exit(code=1) from exc
        raise
    _persist_cli_run(
        output=output,
        case_data=case_payload,
        bundle=bundle,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        extraction_fallback=resolved_fallback,
        extraction_execution_mode=extraction_execution_mode,
        divergence_reasoning=divergence_reasoning,
        principal_only=principal_only,
        include_amendments=include_amendments,
        include_revocations=include_revocations,
        max_sources=max_sources,
        source_sections={
            "principal_only": principal_only,
            "include_amendments": include_amendments,
            "include_revocations": include_revocations,
            "max_sources": max_sources,
        },
    )
    if not quiet:
        quality = build_run_quality_summary(bundle)
        summary = build_cli_completion_summary(
            bundle, quality_summary=quality, output_dir=None
        )
        print_completion_summary_table(
            console, summary, verbose=verbose or very_verbose
        )
        fail_msg = str(summary.get("llm_extraction_failure_message") or "").strip()
        if fail_msg:
            console.print(f"[bold red]{fail_msg}[/bold red]")
        console.print(
            Panel.fit(
                f"Ran intake bundle: {source_bundle_json}\nCase: {case_json_path}",
                style="green",
            )
        )
    console.print_json(json.dumps(bundle))


@app.command("estimate-corpus-run")
def estimate_corpus_run_cmd(
    universe_path: str = typer.Argument(..., help="Path to examples/equine_source_universe.json (or compatible)."),
    profile: str = typer.Option(
        ...,
        "--profile",
        help="Corpus profile id (e.g. equine_passport_identification_v0_1).",
    ),
    extraction_mode: str = typer.Option(
        "frontier",
        "--extraction-mode",
        help="frontier | local (for chunk / token planning).",
    ),
    offline_only: bool = typer.Option(
        False,
        "--offline-only",
        help="Universe member-count heuristic only (no ingest, no network).",
    ),
    fetch: bool = typer.Option(
        False,
        "--fetch",
        help="Fetch legislation.gov.uk XML for sizing (still no LLM). Default uses synthetic body sizing.",
    ),
    offline_chars: int = typer.Option(
        120_000,
        "--offline-chars-per-instrument",
        help="When not using --fetch: synthetic body characters per legislation source for ingest planning.",
    ),
) -> None:
    """Estimate fragments and LLM invocations — does not call model providers."""
    if offline_only:
        uni = load_equine_source_universe(universe_path)
        console.print_json(json.dumps(estimate_summary_from_universe_offline(uni, profile)))
        return
    case_data = materialize_case_from_universe_path(universe_path, profile)
    em = extraction_mode if extraction_mode in ("frontier", "local") else "frontier"
    est = estimate_corpus_run_from_case(
        case_data,
        extraction_mode=em,
        offline_chars_per_instrument=None if fetch else offline_chars,
    )
    console.print_json(json.dumps(est))


@app.command("plan-extraction-batch")
def plan_extraction_batch(
    case_path: str = typer.Argument(..., help="Path to case JSON."),
    export_dir: str = typer.Option("dist/static-report", "--export-dir"),
) -> None:
    case_data = load_case_file(case_path)
    settings = LLMSettings()
    extraction_cfg = case_data.get("extraction") if isinstance(case_data.get("extraction"), dict) else {}
    mode = str(extraction_cfg.get("mode") or "frontier")
    if mode != "frontier":
        raise typer.BadParameter("batch planning requires extraction.mode=frontier")
    planned = plan_frontier_batch_for_case(
        case_data=case_data,
        model_alias=settings.frontier_extract_model,
        source_cache_dir=None,
        derived_cache_dir=None,
        max_input_tokens=settings.max_extract_input_tokens,
        extract_model_context_limit=settings.extract_model_context_limit,
    )
    plan_id = f"plan-{Path(case_path).stem}"
    store = BatchJobStore(export_dir=export_dir)
    store.write_job(
        batch_job_id=plan_id,
        metadata={
            "batch_job_id": plan_id,
            "status": "planned",
            "submitted_at": None,
            "completed_at": None,
            "provider": "anthropic",
            "model_alias": settings.frontier_extract_model,
            "request_count": len(planned.requests),
            "estimated_input_tokens_total": sum(r.estimated_input_tokens for r in planned.requests),
            "source_count": planned.source_count,
            "fragment_count": planned.fragment_count,
        },
        requests=planned.requests,
    )
    console.print_json(
        json.dumps(
            {
                "batch_job_id": plan_id,
                "status": "planned",
                "request_count": len(planned.requests),
                "estimated_input_tokens_total": sum(r.estimated_input_tokens for r in planned.requests),
                "storage_dir": str(store.job_dir(plan_id)),
            }
        )
    )


@app.command("submit-extraction-batch")
def submit_extraction_batch(
    batch_job_id: str = typer.Argument(..., help="Batch job id from plan-extraction-batch."),
    export_dir: str = typer.Option("dist/static-report", "--export-dir"),
) -> None:
    store = BatchJobStore(export_dir=export_dir)
    job_dir = store.job_dir(batch_job_id)
    req_path = job_dir / "requests.json"
    if not req_path.is_file():
        raise typer.BadParameter(f"requests.json not found for {batch_job_id}")
    requests_raw = json.loads(req_path.read_text(encoding="utf-8"))
    requests = [PlannedExtractionRequest(**item) for item in requests_raw if isinstance(item, dict)]
    client = AnthropicBatchLLMClient()
    provider_batch_id = client.submit_batch(requests)
    meta = {
        "batch_job_id": batch_job_id,
        "provider_batch_job_id": provider_batch_id,
        "status": "submitted",
        "provider": "anthropic",
        "model_alias": requests[0].model_alias if requests else "",
        "request_count": len(requests),
        "estimated_input_tokens_total": sum(r.estimated_input_tokens for r in requests),
        "submitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    (job_dir / "batch_job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    console.print_json(json.dumps(meta))


@app.command("poll-extraction-batch")
def poll_extraction_batch(
    batch_job_id: str = typer.Argument(..., help="Batch job id."),
    export_dir: str = typer.Option("dist/static-report", "--export-dir"),
    fetch_results: bool = typer.Option(True, "--fetch-results/--no-fetch-results"),
) -> None:
    store = BatchJobStore(export_dir=export_dir)
    job_dir = store.job_dir(batch_job_id)
    meta_path = job_dir / "batch_job.json"
    if not meta_path.is_file():
        raise typer.BadParameter(f"batch_job.json not found for {batch_job_id}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    provider_batch_id = str(meta.get("provider_batch_job_id") or "").strip()
    if not provider_batch_id:
        raise typer.BadParameter("provider_batch_job_id missing, submit first")
    client = AnthropicBatchLLMClient()
    status = client.get_batch_status(provider_batch_id)
    result_payload: dict[str, Any] = {"status": status}
    meta["provider_status"] = status.get("processing_status")
    if fetch_results and str(status.get("processing_status") or "").lower() == "ended":
        rows = client.fetch_batch_results(provider_batch_id)
        store.write_results(batch_job_id=batch_job_id, results=rows)
        meta["status"] = "results_available"
        meta["result_count"] = len(rows)
        meta["completed_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        result_payload["result_count"] = len(rows)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    console.print_json(json.dumps(result_payload))


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


@app.command("import-extraction-batch")
def import_extraction_batch(
    batch_job_id: str = typer.Argument(..., help="Batch job id with results.jsonl"),
    case_path: str = typer.Argument(..., help="Case JSON used for planning."),
    export_dir: str = typer.Option("dist/static-report", "--export-dir"),
    extraction_fallback: str = typer.Option("mark_needs_review", "--extraction-fallback"),
) -> None:
    store = BatchJobStore(export_dir=export_dir)
    job_dir = store.job_dir(batch_job_id)
    req_path = job_dir / "requests.json"
    results_path = job_dir / "results.jsonl"
    if not req_path.is_file() or not results_path.is_file():
        raise typer.BadParameter("requests.json and results.jsonl are required")
    req_rows = json.loads(req_path.read_text(encoding="utf-8"))
    requests = [PlannedExtractionRequest(**row) for row in req_rows if isinstance(row, dict)]
    results_raw = [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    provider_results = _anthropic_result_text_by_request([r for r in results_raw if isinstance(r, dict)])
    planned_case = plan_frontier_batch_for_case(
        case_data=load_case_file(case_path),
        model_alias=LLMSettings().frontier_extract_model,
    )
    usable_requests = [r for r in requests if r.request_id in planned_case.source_by_request_id]
    imported = import_frontier_batch_results(
        requests=usable_requests,
        provider_results=provider_results,
        source_by_request_id=planned_case.source_by_request_id,
        topic=planned_case.topic,
        cluster=planned_case.cluster,
        extraction_fallback=extraction_fallback,
    )
    console.print_json(
        json.dumps(
            {
                "batch_job_id": batch_job_id,
                "imported_proposition_count": len(imported.propositions),
                "failed_result_count": imported.failed_result_count,
                "validation_error_count": len(imported.validation_errors),
            }
        )
    )


@app.command("build-equine-corpus")
def build_equine_corpus(
    corpus_config: str = typer.Option(
        "examples/corpus_equine_law.json",
        "--corpus-config",
        help="Path to equine corpus configuration JSON.",
    ),
    output_dir: str = typer.Option(
        "dist/static-report",
        "--output-dir",
        help="Directory for static bundle and coverage artifacts.",
    ),
    use_llm: bool = typer.Option(
        False,
        help="Route extraction via LiteLLM (frontier mode requires a client; offline CI uses heuristic).",
    ),
    extraction_mode: str | None = typer.Option(
        None,
        "--extraction-mode",
        help="heuristic | local | frontier (default: corpus/case extraction.mode).",
    ),
    extraction_execution_mode: str | None = typer.Option(
        None,
        "--extraction-execution-mode",
        help="interactive | batch (batch valid with extraction_mode=frontier).",
    ),
    extraction_fallback: str | None = typer.Option(
        None,
        "--extraction-fallback",
        help="fallback | fail_closed | mark_needs_review (default: corpus/case fallback_policy).",
    ),
    divergence_reasoning: str | None = typer.Option(
        None,
        "--divergence-reasoning",
        help="none | frontier (default: frontier when use_llm).",
    ),
    source_cache_dir: str | None = typer.Option(None, "--source-cache-dir"),
    derived_cache_dir: str | None = typer.Option(None, "--derived-cache-dir"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    accept_large_corpus_run: bool = typer.Option(
        False,
        "--i-accept-large-corpus-run",
        help="Acknowledge frontier extraction over a very large legislation universe (skips confirmation).",
    ),
) -> None:
    """Build equine law corpus export: discovery merge, extraction, bundle, coverage matrices."""
    case_data_preview, _cc, _cp = prepare_case_data_for_equine_corpus(corpus_config)
    _maybe_confirm_large_corpus_run(
        case_data=case_data_preview,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        accept_large=accept_large_corpus_run,
    )
    with pipeline_progress(console, quiet=quiet, verbose=verbose) as progress:
        bundle, cov_summary = run_equine_corpus_export(
            corpus_config_path=corpus_config,
            output_dir=output_dir,
            use_llm=use_llm,
            extraction_mode=extraction_mode,
            extraction_execution_mode=extraction_execution_mode,
            extraction_fallback=extraction_fallback,
            divergence_reasoning=divergence_reasoning,
            source_cache_dir=source_cache_dir,
            derived_cache_dir=derived_cache_dir,
            progress=progress,
        )
    if not quiet:
        console.print(
            Panel.fit(
                "[bold]Equine corpus — coverage status (pending review)[/bold]\n"
                "This workflow does not claim complete equine law. See artifact disclaimers.",
                style="cyan",
            )
        )
        console.print(
            f"Sources discovered (family candidates): [bold]{cov_summary['sources_discovered_candidates']}[/bold]"
        )
        console.print(
            f"Sources included (ingested): [bold]{cov_summary['sources_included_rows']}[/bold]"
        )
        console.print(
            f"Propositions — direct equine scope links: [bold]{cov_summary['propositions_direct_equine_scope']}[/bold]"
        )
        console.print(
            f"Propositions — indirect: [bold]{cov_summary['propositions_indirect_equine_scope']}[/bold] | "
            f"contextual: [bold]{cov_summary['propositions_contextual_equine_scope']}[/bold]"
        )
        console.print(
            f"Propositions — unreviewed (proposed): [bold]{cov_summary['propositions_unreviewed']}[/bold]"
        )
        console.print(
            f"Propositions — total: [bold]{cov_summary['propositions_total']}[/bold] | "
            f"guidance-ready: [bold]{cov_summary['guidance_ready_propositions']}[/bold]"
        )
        console.print(
            f"Pending legal candidates (discovery rows): [bold]{cov_summary['pending_legal_candidates']}[/bold]"
        )
        console.print(
            f"Lint warnings (total): [bold]{cov_summary.get('lint_warning_total', 0)}[/bold] "
            f"| by quality gate: [bold]{cov_summary.get('lint_warnings_by_quality_gate', {})}[/bold]"
        )
        console.print(
            f"Extraction traces — fallback method: [bold]{cov_summary.get('extraction_trace_fallback_method_count', 0)}[/bold] "
            f"| low confidence: [bold]{cov_summary.get('extraction_trace_low_confidence_count', 0)}[/bold]"
        )
        gaps = cov_summary.get("gaps_needing_manual_review") or []
        if gaps:
            console.print(
                f"Gaps / manual review hints ([bold]{len(gaps)}[/bold] shown, max 50):"
            )
            for line in gaps[:20]:
                console.print(f"  - {line}")
        console.print(
            f"Wrote [bold]equine_source_coverage.json[/bold], [bold]equine_proposition_coverage.json[/bold], "
            f"[bold]equine_corpus_readiness.json[/bold], CSV under [bold]{output_dir}[/bold]"
        )
        rq = bundle.get("run_quality_summary")
        if not isinstance(rq, dict):
            rq = build_run_quality_summary(bundle)
        summary = build_cli_completion_summary(
            bundle, quality_summary=rq, output_dir=output_dir
        )
        print_completion_summary_table(console, summary, verbose=verbose)
        console.print(Panel.fit("build-equine-corpus completed", style="green"))


@app.command("apply-assessment-review")
def apply_assessment_review(
    case_path: str = typer.Argument(..., help="Path to the input case JSON file."),
    assessment_id: str = typer.Argument(..., help="Assessment ID to review."),
    new_status: ReviewStatus = typer.Argument(..., help="New review status."),
    reviewer: str = typer.Option(..., "--reviewer", help="Reviewer identifier."),
    note: str = typer.Option("", "--note", help="Review note."),
    edited_fields_json: str | None = typer.Option(
        None,
        "--edited-fields-json",
        help="Optional JSON object of edited fields.",
    ),
    use_llm: bool = typer.Option(False, help="Route extraction/reasoning via LiteLLM."),
    extraction_mode: str | None = typer.Option(None, "--extraction-mode"),
    extraction_fallback: str = typer.Option("fallback", "--extraction-fallback"),
    divergence_reasoning: str | None = typer.Option(None, "--divergence-reasoning"),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
    derived_cache_dir: str | None = typer.Option(
        None,
        "--derived-cache-dir",
        help="Explicit derived artifact cache directory.",
    ),
) -> None:
    bundle = run_case_file(
        case_path=case_path,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        extraction_fallback=extraction_fallback,
        divergence_reasoning=divergence_reasoning,
        source_cache_dir=source_cache_dir,
        derived_cache_dir=derived_cache_dir,
    )
    updated_bundle = apply_assessment_review_decision(
        bundle=bundle,
        assessment_id=assessment_id,
        new_status=new_status.value,
        reviewer=reviewer,
        note=note,
        edited_fields=parse_edited_fields_payload(edited_fields_json),
    )
    updated_assessment = next(
        item for item in updated_bundle["divergence_assessments"] if item["id"] == assessment_id
    )
    decision = updated_bundle["review_decisions"][-1]
    console.print(Panel.fit(f"Applied review to: {assessment_id}", style="green"))
    console.print_json(json.dumps({"assessment": updated_assessment, "review_decision": decision}))


def _load_json_payload(reference_json: str | None, reference_file: str | None) -> dict[str, object]:
    if reference_json and reference_file:
        raise ValueError("Provide either --reference-json or --reference-file, not both.")
    if not reference_json and not reference_file:
        raise ValueError("Provide --reference-json or --reference-file.")
    if reference_json:
        payload = json.loads(reference_json)
    else:
        assert reference_file is not None
        payload = json.loads(Path(reference_file).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Reference payload must be a JSON object.")
    return payload


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@app.command("source-registry-list")
def source_registry_list(
    source_registry_path: str | None = typer.Option(
        None,
        "--source-registry-path",
        help="Path to local source registry JSON file.",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
) -> None:
    registry = SourceRegistryService(
        registry_path=source_registry_path,
        source_cache_dir=source_cache_dir,
    )
    console.print_json(json.dumps({"sources": registry.list_entries()}))


@app.command("source-registry-inspect")
def source_registry_inspect(
    registry_id: str = typer.Argument(..., help="Registry source ID."),
    source_registry_path: str | None = typer.Option(
        None,
        "--source-registry-path",
        help="Path to local source registry JSON file.",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
) -> None:
    registry = SourceRegistryService(
        registry_path=source_registry_path,
        source_cache_dir=source_cache_dir,
    )
    console.print_json(json.dumps(registry.inspect_entry(registry_id=registry_id)))


@app.command("source-registry-register")
def source_registry_register(
    reference_json: str | None = typer.Option(
        None,
        "--reference-json",
        help="JSON object with source reference fields.",
    ),
    reference_file: str | None = typer.Option(
        None,
        "--reference-file",
        help="Path to JSON file containing source reference fields.",
    ),
    refresh: bool = typer.Option(
        True,
        "--refresh/--no-refresh",
        help="Fetch/normalize immediately after registration.",
    ),
    source_registry_path: str | None = typer.Option(
        None,
        "--source-registry-path",
        help="Path to local source registry JSON file.",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
) -> None:
    payload = _load_json_payload(reference_json, reference_file)
    registry = SourceRegistryService(
        registry_path=source_registry_path,
        source_cache_dir=source_cache_dir,
    )
    entry = registry.register_reference(reference=payload, refresh=refresh)
    console.print_json(json.dumps(entry))


@app.command("source-registry-refresh")
def source_registry_refresh(
    registry_id: str = typer.Argument(..., help="Registry source ID."),
    source_registry_path: str | None = typer.Option(
        None,
        "--source-registry-path",
        help="Path to local source registry JSON file.",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
) -> None:
    registry = SourceRegistryService(
        registry_path=source_registry_path,
        source_cache_dir=source_cache_dir,
    )
    entry = registry.refresh_reference(registry_id=registry_id)
    console.print_json(json.dumps(entry))


@app.command("run-registry-sources")
def run_registry_sources_command(
    registry_ids: list[str] = typer.Option(
        ...,
        "--registry-id",
        help="Registry source ID. Repeat for multiple sources.",
    ),
    topic_name: str = typer.Option(..., "--topic-name", help="Run topic name."),
    cluster_name: str | None = typer.Option(
        None,
        "--cluster-name",
        help="Optional run cluster name.",
    ),
    analysis_mode: str = typer.Option(
        "auto",
        "--analysis-mode",
        help="auto, divergence, or single_jurisdiction.",
    ),
    analysis_scope: str = typer.Option(
        "selected_sources",
        "--analysis-scope",
        help="eu, uk, eu_uk, or selected_sources (registry tick list).",
    ),
    refresh_sources: bool = typer.Option(
        False,
        "--refresh-sources",
        help="Refresh registry sources before running analysis.",
    ),
    run_id: str | None = typer.Option(None, "--run-id", help="Explicit run ID."),
    run_notes: str = typer.Option("", "--run-notes", help="Optional run notes."),
    subject_tags_csv: str = typer.Option(
        "",
        "--subject-tags",
        help="Comma-separated topic subject tags.",
    ),
    comparison_jurisdiction_a: str | None = typer.Option(
        None,
        "--comparison-jurisdiction-a",
        help="Explicit jurisdiction_a override.",
    ),
    comparison_jurisdiction_b: str | None = typer.Option(
        None,
        "--comparison-jurisdiction-b",
        help="Explicit jurisdiction_b override.",
    ),
    proposition_index: int = typer.Option(
        0,
        "--proposition-index",
        help="Default proposition index for comparison pairing.",
    ),
    use_llm: bool = typer.Option(False, help="Route extraction/reasoning via LiteLLM."),
    extraction_mode: str | None = typer.Option(None, "--extraction-mode"),
    extraction_execution_mode: str | None = typer.Option(
        None,
        "--extraction-execution-mode",
        help="interactive | batch (batch valid with extraction_mode=frontier).",
    ),
    extraction_fallback: str = typer.Option("fallback", "--extraction-fallback"),
    divergence_reasoning: str | None = typer.Option(None, "--divergence-reasoning"),
    source_registry_path: str | None = typer.Option(
        None,
        "--source-registry-path",
        help="Path to local source registry JSON file.",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Explicit source snapshot cache directory.",
    ),
    derived_cache_dir: str | None = typer.Option(
        None,
        "--derived-cache-dir",
        help="Explicit derived artifact cache directory.",
    ),
    focus_scopes_csv: str = typer.Option(
        "",
        "--focus-scopes",
        help="Comma-separated extraction focus scopes (optional).",
    ),
    max_propositions_per_source: int | None = typer.Option(
        None,
        "--max-propositions-per-source",
        help="Max propositions extracted per source (optional).",
    ),
) -> None:
    scopes = _split_csv(focus_scopes_csv)
    bundle = run_registry_sources(
        registry_ids=registry_ids,
        topic_name=topic_name,
        cluster_name=cluster_name,
        analysis_mode=analysis_mode,
        analysis_scope=analysis_scope,
        refresh_sources=refresh_sources,
        run_id=run_id,
        run_notes=run_notes,
        subject_tags=_split_csv(subject_tags_csv),
        comparison_jurisdiction_a=comparison_jurisdiction_a,
        comparison_jurisdiction_b=comparison_jurisdiction_b,
        proposition_index=proposition_index,
        use_llm=use_llm,
        extraction_mode=extraction_mode,
        extraction_execution_mode=extraction_execution_mode,
        extraction_fallback=extraction_fallback,
        divergence_reasoning=divergence_reasoning,
        source_registry_path=source_registry_path,
        source_cache_dir=source_cache_dir,
        derived_cache_dir=derived_cache_dir,
        focus_scopes=scopes if scopes else None,
        max_propositions_per_source=max_propositions_per_source,
    )
    console.print_json(json.dumps(bundle))


@app.command("list-runs")
def list_runs(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps({"runs": store.list_runs()}))


@app.command("inspect-run")
def inspect_run(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps(store.inspect_run(run_id=run_id)))


@app.command("inspect-stage-traces")
def inspect_stage_traces(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts (or run-bundle output dir with case.json).",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Include full stage trace payloads (default is compact summary).",
    ),
) -> None:
    export_path = Path(export_dir)
    if export_path.is_dir() and (export_path / "case.json").is_file():
        jobs_path = export_path / "proposition_extraction_jobs.json"
        if jobs_path.is_file():
            from law_proposition_extractor_pipeline.linting import load_exported_bundle

            from law_proposition_extractor_pipeline.extraction_llm_metrics import build_extraction_job_inspection

            bundle = load_exported_bundle(export_path)
            console.print_json(
                json.dumps(
                    {
                        "export_dir": str(export_path),
                        "extraction_job_inspection": build_extraction_job_inspection(bundle),
                    }
                )
            )
            return
        console.print(
            "[yellow]Directory has case.json but no exported bundle artifacts. "
            "Run export-run after run-bundle, or pass a full static export directory.[/yellow]"
        )
    store = OperationalStore(export_dir=export_dir)
    payload = store.list_stage_traces(run_id=run_id, compact=not full)
    console.print_json(json.dumps(payload))


@app.command("inspect-extraction-jobs")
def inspect_extraction_jobs(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing an exported static bundle.",
    ),
    show_raw_failure_examples: int = typer.Option(
        0,
        "--show-raw-failure-examples",
        min=0,
        help="Include up to N failed live LLM traces with raw model output excerpts.",
    ),
) -> None:
    from .extraction_inspection import summarize_extraction_jobs
    from .linting import load_exported_bundle

    try:
        bundle = load_exported_bundle(export_dir)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print_json(
        json.dumps(
            summarize_extraction_jobs(
                bundle, raw_failure_example_limit=show_raw_failure_examples
            ),
            indent=2,
        )
    )


@app.command("debug-extract-fragment")
def debug_extract_fragment_cmd(
    case_or_run_dir: str = typer.Argument(
        ...,
        help="case.json, run directory with run_bundle.json, or exported static bundle.",
    ),
    source_id: str = typer.Option(..., "--source-id", help="Source record id."),
    locator: str = typer.Option(
        ...,
        "--locator",
        help="Fragment locator (e.g. regulation:1).",
    ),
    extraction_mode: str = typer.Option(
        "local",
        "--extraction-mode",
        help="local | frontier",
    ),
    retry_empty_extraction: bool = typer.Option(
        True,
        "--retry-empty-extraction/--no-retry-empty-extraction",
        help="Retry once when extraction returns empty JSON (default: on).",
    ),
    extraction_output_mode: str | None = typer.Option(
        None,
        "--extraction-output-mode",
        help="LLM structured output: json_object | json_schema | text_then_parse.",
    ),
    allow_output_mode_fallback: bool = typer.Option(
        False,
        "--allow-output-mode-fallback/--no-allow-output-mode-fallback",
        help="Fall back to json_object when json_schema is unsupported or rejected.",
    ),
) -> None:
    from .extraction_debug import debug_extract_fragment

    if extraction_mode not in {"local", "frontier"}:
        raise typer.BadParameter("--extraction-mode must be local or frontier")
    output_mode_kwargs = _extraction_output_mode_kwargs(
        extraction_output_mode=extraction_output_mode,
        allow_output_mode_fallback=allow_output_mode_fallback,
    )
    try:
        payload = debug_extract_fragment(
            case_or_run_dir,
            source_id=source_id,
            locator=locator,
            extraction_mode=extraction_mode,  # type: ignore[arg-type]
            retry_empty_extraction=retry_empty_extraction,
            **output_mode_kwargs,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print_json(json.dumps(payload, indent=2))


@app.command("extract-fragment")
def extract_fragment_cmd(
    fixture: str | None = typer.Option(
        None,
        "--fixture",
        help="Prompt-lab fixture JSON, or legacy topic/cluster/source plus optional dry block.",
    ),
    case_or_run_dir: str | None = typer.Option(
        None,
        "--case-or-run-dir",
        help="case.json, run directory, or exported bundle (with --source-id and --locator).",
    ),
    source_id: str | None = typer.Option(None, "--source-id", help="Source record id."),
    locator: str | None = typer.Option(
        None,
        "--locator",
        help="Fragment locator (e.g. regulation:1).",
    ),
    mode: str = typer.Option(
        "local",
        "--mode",
        help="local | frontier | dry (dry uses fixture raw model output, no LLM).",
    ),
    output_dir: str = typer.Option(
        ...,
        "--output-dir",
        help="Directory for fragment.txt, prompt.txt, propositions, review.md, MODEL.md, …",
    ),
    max_propositions: int = typer.Option(
        8,
        "--max-propositions",
        min=1,
        help="Maximum propositions to extract from the fragment.",
    ),
    retry_empty_extraction: bool = typer.Option(
        True,
        "--retry-empty-extraction/--no-retry-empty-extraction",
        help="Retry once when extraction returns empty JSON (default: on).",
    ),
    extraction_output_mode: str | None = typer.Option(
        None,
        "--extraction-output-mode",
        help="LLM structured output: json_object | json_schema | text_then_parse.",
    ),
    allow_output_mode_fallback: bool = typer.Option(
        False,
        "--allow-output-mode-fallback/--no-allow-output-mode-fallback",
        help="Fall back to json_object when json_schema is unsupported or rejected.",
    ),
    run_eval: bool = typer.Option(
        False,
        "--eval/--no-eval",
        help="After extraction, score output against fixture expected propositions.",
    ),
) -> None:
    from .extraction_workbench import run_extract_fragment_workbench, write_extract_fragment_workbench_outputs

    if mode not in {"local", "frontier", "dry"}:
        raise typer.BadParameter("--mode must be local, frontier, or dry")
    if fixture is None and case_or_run_dir is None:
        raise typer.BadParameter("Provide --fixture or --case-or-run-dir")
    if fixture is not None and case_or_run_dir is not None:
        raise typer.BadParameter("Use either --fixture or --case-or-run-dir, not both")
    if case_or_run_dir is not None and (not source_id or not locator):
        raise typer.BadParameter("--source-id and --locator are required with --case-or-run-dir")
    if run_eval and fixture is None:
        raise typer.BadParameter(
            "--eval requires --fixture with expected_propositions (prompt-lab schema)"
        )

    output_mode_kwargs = _extraction_output_mode_kwargs(
        extraction_output_mode=extraction_output_mode,
        allow_output_mode_fallback=allow_output_mode_fallback,
    )
    try:
        result = run_extract_fragment_workbench(
            fixture_path=fixture,
            case_or_run_dir=case_or_run_dir,
            source_id=source_id,
            locator=locator,
            extraction_mode=mode,  # type: ignore[arg-type]
            max_propositions=max_propositions,
            retry_empty_extraction=retry_empty_extraction,
            **output_mode_kwargs,
        )
        written = write_extract_fragment_workbench_outputs(result, output_dir)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(f"Wrote prompt-lab artifacts to {written.resolve()}")

    if run_eval:
        from .extraction_prompt_eval import evaluate_and_write_prompt_lab_run

        assert fixture is not None
        try:
            eval_result, json_path, md_path = evaluate_and_write_prompt_lab_run(
                fixture=fixture,
                run_dir=written,
            )
        except (ValueError, FileNotFoundError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        status = "PASS" if eval_result.passed else "FAIL"
        console.print(
            f"Eval {status}: {eval_result.matched_expected_count}/"
            f"{eval_result.expected_count} expected matched"
        )
        console.print(f"Wrote {json_path.resolve()} and {md_path.resolve()}")


@app.command("extract-fragment-batch")
def extract_fragment_batch_cmd(
    fixture_dir: str | None = typer.Option(
        None,
        "--fixture-dir",
        help="Directory containing prompt-lab fixture JSON files.",
    ),
    fixture: list[str] = typer.Option(
        [],
        "--fixture",
        help="Repeatable path to a fixture JSON (skips directory discovery for that file).",
    ),
    mode: str = typer.Option(
        "local",
        "--mode",
        help="local | frontier | dry (dry uses fixture dry.raw_model_output, no LLM).",
    ),
    output_root: str = typer.Option(
        ...,
        "--output-root",
        help="Root directory for per-fixture run dirs and batch summary artifacts.",
    ),
    fixture_glob: str | None = typer.Option(
        None,
        "--fixture-glob",
        help="Glob pattern for fixture filenames (e.g. slurry-good-*.json).",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        min=1,
        help="Run at most N fixtures after discovery.",
    ),
    max_propositions: int = typer.Option(
        8,
        "--max-propositions",
        min=1,
        help="Maximum propositions to extract per fragment.",
    ),
    retry_empty_extraction: bool = typer.Option(
        True,
        "--retry-empty-extraction/--no-retry-empty-extraction",
        help="Retry once when extraction returns empty JSON (default: on).",
    ),
    extraction_output_mode: str | None = typer.Option(
        None,
        "--extraction-output-mode",
        help="LLM structured output: json_object | json_schema | text_then_parse.",
    ),
    allow_output_mode_fallback: bool = typer.Option(
        False,
        "--allow-output-mode-fallback/--no-allow-output-mode-fallback",
        help="Fall back to json_object when json_schema is unsupported or rejected.",
    ),
    run_eval: bool = typer.Option(
        True,
        "--eval/--no-eval",
        help="Score each run against fixture expected propositions (default: on).",
    ),
    eval_only: bool = typer.Option(
        False,
        "--eval-only",
        help="Re-score existing per-fixture run dirs under --output-root (no extraction).",
    ),
    reapply_normalisation: bool = typer.Option(
        False,
        "--reapply-normalisation",
        help="Re-run classification normalisation from propositions.raw.json before eval.",
    ),
    overwrite: bool = typer.Option(
        True,
        "--overwrite/--no-overwrite",
        help="Overwrite existing per-fixture run directories (default: on).",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop batch on first fixture failure.",
    ),
) -> None:
    from .extraction_prompt_lab_batch import run_prompt_lab_batch

    if mode not in {"local", "frontier", "dry"}:
        raise typer.BadParameter("--mode must be local, frontier, or dry")
    if not fixture_dir and not fixture:
        raise typer.BadParameter("Provide --fixture-dir and/or one or more --fixture paths")

    output_mode_kwargs = _extraction_output_mode_kwargs(
        extraction_output_mode=extraction_output_mode,
        allow_output_mode_fallback=allow_output_mode_fallback,
    )
    fixture_paths = [Path(p) for p in fixture] if fixture else None
    try:
        result = run_prompt_lab_batch(
            output_root=output_root,
            extraction_mode=mode,  # type: ignore[arg-type]
            fixture_dir=Path(fixture_dir) if fixture_dir else None,
            fixture_paths=fixture_paths,
            fixture_glob=fixture_glob,
            limit=limit,
            run_eval=run_eval,
            eval_only=eval_only,
            reapply_normalisation=reapply_normalisation,
            overwrite=overwrite,
            fail_fast=fail_fast,
            max_propositions=max_propositions,
            retry_empty_extraction=retry_empty_extraction,
            **output_mode_kwargs,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    passed = sum(1 for row in result.rows if row.status == "pass")
    warned = sum(1 for row in result.rows if row.status == "warn")
    failed = sum(1 for row in result.rows if row.status == "fail")
    errored = sum(1 for row in result.rows if row.status == "error")
    skipped = sum(1 for row in result.rows if row.status == "skipped")
    console.print(
        f"Batch complete: {passed} pass, {warned} warn, {failed} fail, "
        f"{errored} error, {skipped} skipped"
    )
    console.print(f"Verdict: {result.verdict} — {result.verdict_detail}")
    console.print(f"Wrote {Path(output_root).resolve() / 'prompt_lab_summary.json'}")


@app.command("eval-extract-fragment")
def eval_extract_fragment_cmd(
    fixture: str = typer.Option(
        ...,
        "--fixture",
        help="Prompt-lab fixture JSON with expected propositions.",
    ),
    run_dir: str = typer.Option(
        ...,
        "--run-dir",
        help="Workbench output directory to evaluate.",
    ),
    use_raw: bool = typer.Option(
        False,
        "--use-raw",
        help="Evaluate propositions.raw.json instead of normalised output.",
    ),
    reapply_normalisation: bool = typer.Option(
        False,
        "--reapply-normalisation",
        help="Re-run classification normalisation from propositions.raw.json before eval.",
    ),
) -> None:
    from .extraction_prompt_eval import evaluate_and_write_prompt_lab_run

    try:
        result, json_path, md_path = evaluate_and_write_prompt_lab_run(
            fixture=fixture,
            run_dir=run_dir,
            prefer_normalised=not use_raw,
            reapply_normalisation=reapply_normalisation,
        )
    except OSError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if result.eval_status == "error":
        status = "ERROR"
    elif result.passed:
        status = "PASS"
    else:
        status = "FAIL"
    console.print(
        f"{status}: {result.matched_expected_count}/{result.expected_count} expected matched"
    )
    console.print(f"Wrote {json_path.resolve()} and {md_path.resolve()}")
    if result.eval_status == "error":
        raise typer.Exit(code=2)
    if not result.passed:
        raise typer.Exit(code=1)


@app.command("benchmark-local-extraction")
def benchmark_local_extraction_cmd(
    case_or_run_dir: str = typer.Argument(
        ...,
        help="case.json, run directory with run_bundle.json, or exported static bundle.",
    ),
    source_id: str = typer.Option(..., "--source-id", help="Source record id."),
    locator: str | None = typer.Option(
        None,
        "--locator",
        help="Single fragment locator (e.g. regulation:1). Use --locators for multiple.",
    ),
    locators: str | None = typer.Option(
        None,
        "--locators",
        help="Comma-separated fragment locators (e.g. regulation:1,regulation:2).",
    ),
    models: str = typer.Option(
        "local_extract",
        "--models",
        help="Comma-separated LiteLLM model aliases to benchmark.",
    ),
    attempts: int = typer.Option(
        3,
        "--attempts",
        min=1,
        help="Independent extraction attempts per model and locator.",
    ),
    extraction_mode: str = typer.Option(
        "local",
        "--extraction-mode",
        help="local | frontier",
    ),
    retry_empty_extraction: bool = typer.Option(
        True,
        "--retry-empty-extraction/--no-retry-empty-extraction",
        help="Retry once when extraction returns empty JSON (default: on).",
    ),
    output: str = typer.Option(
        "runs/local-extraction-benchmark.json",
        "--output",
        help="Path to write benchmark JSON results.",
    ),
) -> None:
    from .extraction_benchmark import benchmark_local_extraction, format_benchmark_summary_table

    if extraction_mode not in {"local", "frontier"}:
        raise typer.BadParameter("--extraction-mode must be local or frontier")
    try:
        payload = benchmark_local_extraction(
            case_or_run_dir,
            source_id=source_id,
            locator=locator,
            locators=locators,
            models=models,
            attempts=attempts,
            extraction_mode=extraction_mode,  # type: ignore[arg-type]
            retry_empty_extraction=retry_empty_extraction,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    output_path = Path(output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    console.print(format_benchmark_summary_table(payload.get("summary_by_model") or []))
    console.print(f"\nWrote benchmark results to {output_path.resolve()}")


@app.command("list-run-review-decisions")
def list_run_review_decisions(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps(store.list_review_decisions(run_id=run_id)))


@app.command("list-sources")
def list_sources(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps(store.list_source_records(run_id=run_id)))


@app.command("list-source-target-links")
def list_source_target_links(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps(store.list_source_target_links(run_id=run_id)))


@app.command("list-effective-source-target-links")
def list_effective_source_target_links_cmd(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    source_record_id: str | None = typer.Option(
        None,
        "--source-record-id",
        help="Optional filter by source_record_id.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(
        json.dumps(
            store.list_effective_source_target_links(
                run_id=run_id,
                source_record_id=source_record_id,
            )
        )
    )


@app.command("list-effective-source-categorisation-rationales")
def list_effective_source_categorisation_rationales_cmd(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    source_record_id: str | None = typer.Option(
        None,
        "--source-record-id",
        help="Optional filter by source_record_id.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(
        json.dumps(
            store.list_effective_source_categorisation_rationales(
                run_id=run_id,
                source_record_id=source_record_id,
            )
        )
    )


@app.command("list-effective-proposition-extraction-traces")
def list_effective_proposition_extraction_traces_cmd(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    proposition_id: str | None = typer.Option(
        None,
        "--proposition-id",
        help="Optional filter by proposition_id.",
    ),
    source_record_id: str | None = typer.Option(
        None,
        "--source-record-id",
        help="Optional filter by source_record_id.",
    ),
    source_fragment_id: str | None = typer.Option(
        None,
        "--source-fragment-id",
        help="Optional filter by source_fragment_id.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(
        json.dumps(
            store.list_effective_proposition_extraction_traces(
                run_id=run_id,
                proposition_id=proposition_id,
                source_record_id=source_record_id,
                source_fragment_id=source_fragment_id,
            )
        )
    )


@app.command("list-source-fetch-attempts")
def list_source_fetch_attempts(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    source_record_id: str | None = typer.Option(
        None,
        "--source-record-id",
        help="Optional source record filter.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(
        json.dumps(
            store.list_source_fetch_attempts(
                run_id=run_id,
                source_record_id=source_record_id,
            )
        )
    )


@app.command("inspect-source")
def inspect_source(
    source_id: str = typer.Argument(..., help="Source record ID."),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps(store.inspect_source_record(source_id=source_id, run_id=run_id)))


@app.command("inspect-source-snapshots")
def inspect_source_snapshots(
    source_id: str = typer.Argument(..., help="Source record ID."),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps(store.list_source_snapshots(source_id=source_id, run_id=run_id)))


@app.command("inspect-source-fragments")
def inspect_source_fragments(
    source_id: str = typer.Argument(..., help="Source record ID."),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps(store.list_source_fragments(source_id=source_id, run_id=run_id)))


@app.command("list-propositions")
def list_propositions(
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID to inspect. Defaults to latest exported run.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(json.dumps(store.list_propositions(run_id=run_id)))


@app.command("add-review-decision")
def add_review_decision(
    artifact_type: str = typer.Option(..., "--artifact-type", help="Pipeline artifact_type key."),
    artifact_id: str = typer.Option(..., "--artifact-id", help="Stable id of the artifact."),
    decision: str = typer.Option(
        ...,
        "--decision",
        help="approved | rejected | needs_review | overridden | deferred",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
    run_id: str | None = typer.Option(None, "--run-id", help="Defaults to run.json id."),
    reviewer: str | None = typer.Option(None, "--reviewer"),
    reason: str = typer.Option("", "--reason"),
    applies_to_field: str | None = typer.Option(None, "--applies-to-field"),
    supersedes_decision_id: str | None = typer.Option(
        None,
        "--supersedes-decision-id",
        help="Optional id of a prior decision this row supersedes.",
    ),
    decision_id: str | None = typer.Option(
        None,
        "--decision-id",
        help="Optional explicit id (must be unique).",
    ),
) -> None:
    row = append_pipeline_review_decision(
        export_dir,
        run_id=run_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        decision=decision,
        reviewer=reviewer,
        reason=reason,
        applies_to_field=applies_to_field,
        supersedes_decision_id=supersedes_decision_id,
        decision_id=decision_id,
    )
    console.print_json(json.dumps(row))


@app.command("list-review-decisions")
def list_review_decisions_cmd(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
    run_id: str | None = typer.Option(None, "--run-id"),
    artifact_type: str | None = typer.Option(None, "--artifact-type"),
    artifact_id: str | None = typer.Option(None, "--artifact-id"),
    decision: str | None = typer.Option(None, "--decision"),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    payload = store.list_pipeline_review_decisions(
        run_id=run_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        decision=decision,
    )
    console.print_json(json.dumps(payload))


@app.command("compare-runs")
def compare_runs(
    baseline_export_dir: str = typer.Option(
        ...,
        "--baseline-export-dir",
        help="Directory containing baseline static export (flat bundle).",
    ),
    candidate_export_dir: str = typer.Option(
        ...,
        "--candidate-export-dir",
        help="Directory containing candidate static export.",
    ),
    write_summary: str | None = typer.Option(
        None,
        "--write-summary",
        help="Optional path to write run_comparison_summary.json.",
    ),
) -> None:
    summary = compare_export_dirs(
        baseline_export_dir=baseline_export_dir,
        candidate_export_dir=candidate_export_dir,
    )
    console.print_json(json.dumps(summary))
    if write_summary:
        write_comparison_summary(write_summary, summary)
    status = summary.get("status")
    if status == "regression":
        raise typer.Exit(code=1)
    if status == "inconclusive":
        raise typer.Exit(code=2)


@app.command("lint-export")
def lint_export(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
    no_quality_summary: bool = typer.Option(
        False,
        "--no-quality-summary",
        help="Omit run_quality_summary from CLI output (lint only).",
    ),
) -> None:
    report = lint_export_dir(
        export_dir=export_dir,
        include_run_quality_summary=not no_quality_summary,
    )
    console.print_json(json.dumps(report))
    if not report.get("ok", False):
        raise typer.Exit(code=1)


@app.command("clear-operations-runs")
def clear_operations_runs(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Operations export bundle directory.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be deleted only."),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Required for destructive delete (unless --dry-run).",
    ),
    source_registry_path: str | None = typer.Option(
        None,
        "--source-registry-path",
        help="Registry JSON path used with the API/pipeline (default: temp dir law-proposition-extractor/registry).",
    ),
) -> None:
    """Remove exported analysis bundles; keep registered sources in the registry file."""
    try:
        outcome = execute_clear_operations_runs_only(
            export_dir=export_dir,
            source_registry_path=source_registry_path,
            dry_run=dry_run,
            confirm=confirm,
        )
    except (ClearOperationsConfirmationError, UnsafeExportDirError) as exc:
        console.print(Panel.fit(str(exc), style="yellow"))
        raise typer.Exit(code=1) from exc

    console.print(format_clear_report(outcome))


@app.command("clear-operations-all")
def clear_operations_all(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Operations export bundle directory.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be deleted only."),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Required for destructive delete (unless --dry-run).",
    ),
    source_registry_path: str | None = typer.Option(
        None,
        "--source-registry-path",
        help="Registry JSON path to reset.",
    ),
    source_cache_dir: str | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Source snapshot cache directory to clear.",
    ),
    derived_cache_dir: str | None = typer.Option(
        None,
        "--derived-cache-dir",
        help="Derived artifact cache directory to clear.",
    ),
) -> None:
    """Wipe export bundles, registry, source snapshots cache, and derived cache (development reset)."""
    try:
        outcome = execute_clear_operations_all(
            export_dir=export_dir,
            source_registry_path=source_registry_path,
            source_cache_dir=source_cache_dir,
            derived_cache_dir=derived_cache_dir,
            dry_run=dry_run,
            confirm=confirm,
        )
    except (ClearOperationsConfirmationError, UnsafeExportDirError) as exc:
        console.print(Panel.fit(str(exc), style="yellow"))
        raise typer.Exit(code=1) from exc

    console.print(format_clear_report(outcome))


@app.command("inspect-proposition-history")
def inspect_proposition_history(
    proposition_key: str = typer.Argument(..., help="Proposition lineage key."),
    include_runs: bool = typer.Option(
        True,
        "--include-runs/--no-include-runs",
        help="Aggregate observations across exported runs.",
    ),
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Directory containing exported run artifacts.",
    ),
) -> None:
    store = OperationalStore(export_dir=export_dir)
    console.print_json(
        json.dumps(
            store.proposition_history(
                proposition_key=proposition_key,
                include_runs=include_runs,
            )
        )
    )


@app.command("inspect-extraction-failures")
def inspect_extraction_failures(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help=(
            "Directory containing an exported static bundle (run.json, propositions.json, …). "
            "Not a Law Proposition Extractor case.json file — export the run first."
        ),
    ),
) -> None:
    from .extraction_repair import summarize_extraction_inspection
    from .linting import load_exported_bundle

    try:
        bundle = load_exported_bundle(export_dir)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print_json(json.dumps(summarize_extraction_inspection(bundle), indent=2))


@app.command("inspect-structural-source")
def inspect_structural_source_cmd(
    source: str = typer.Argument(
        ...,
        help="Structural fixture id (from the offline matrix) or path to offline CLML XML.",
    ),
    fmt: str = typer.Option(
        "json",
        "--format",
        help="Output format: json | markdown | tree.",
    ),
) -> None:
    """Inspect Law Proposition Extractor structural hierarchy/headings from offline XML (no network)."""
    from .source_structure_inspector import main as structural_main

    code = structural_main(["inspect", source, "--format", fmt])
    if code != 0:
        raise typer.Exit(code)


@app.command("check-structural-fixtures")
def check_structural_fixtures_cmd() -> None:
    """Run the offline multi-instrument structural-source fidelity contract."""
    from .source_structure_inspector import main as structural_main

    code = structural_main(["check"])
    if code != 0:
        raise typer.Exit(code)


@app.command("run-proposition-fidelity-benchmark")
def run_proposition_fidelity_benchmark_cmd(
    output: str | None = typer.Option(
        None,
        "--output",
        help="Optional JSON output path (default: temp file).",
    ),
    write_baseline: bool = typer.Option(
        False,
        "--write-baseline",
        help="Also write tests/fixtures/proposition_fidelity/baseline.json.",
    ),
) -> None:
    """Run the offline multi-instrument proposition-fidelity benchmark (no LLM)."""
    from .proposition_fidelity.cli import main as pf_main

    argv = ["run"]
    if output:
        argv.extend(["--output", output])
    if write_baseline:
        argv.append("--write-baseline")
    code = pf_main(argv)
    if code != 0:
        raise typer.Exit(code)


@app.command("check-proposition-fidelity-benchmark")
def check_proposition_fidelity_benchmark_cmd() -> None:
    """Check proposition-fidelity report/baseline offline without modifying the tree."""
    from .proposition_fidelity.cli import main as pf_main

    code = pf_main(["check"])
    if code != 0:
        raise typer.Exit(code)


@app.command("repair-extraction")
def repair_extraction(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Source export bundle to repair.",
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        help="Write repaired bundle here (required unless --in-place).",
    ),
    in_place: bool = typer.Option(
        False,
        "--in-place",
        help="Overwrite the export-dir bundle in place (destructive).",
    ),
    only: str = typer.Option(
        "repairable",
        "--only",
        help="repairable | all (re-run every extraction job)",
    ),
    extraction_mode: str = typer.Option("frontier", "--extraction-mode"),
    extraction_fallback: str = typer.Option(
        "mark_needs_review",
        "--extraction-fallback",
        help="fallback | fail_closed | mark_needs_review",
    ),
    use_llm: bool = typer.Option(True, "--use-llm/--no-use-llm"),
    retry_failed_extraction_cache: bool | None = typer.Option(
        None,
        "--retry-failed-extraction-cache/--no-retry-failed-extraction-cache",
        help="Bypass derived-cache entries for failed chunks and re-call the model.",
    ),
    ignore_failed_extraction_cache: bool = typer.Option(
        False,
        "--ignore-failed-extraction-cache",
        help="Reuse cached failed chunks without re-calling the model.",
    ),
    retry_failed_llm: bool | None = typer.Option(
        True,
        "--retry-failed-llm/--no-retry-failed-llm",
        help="Alias for --retry-failed-extraction-cache (default: retry).",
    ),
    source_cache_dir: str | None = typer.Option(None, "--source-cache-dir"),
    derived_cache_dir: str | None = typer.Option(None, "--derived-cache-dir"),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    from .extraction_repair import run_cli_repair_pipeline

    if only not in {"repairable", "all"}:
        raise typer.BadParameter("only must be repairable or all")

    lit_only: Literal["repairable", "all"] = (
        "repairable" if only == "repairable" else "all"
    )
    cache_retry = _extraction_cache_retry_kwargs(
        retry_failed_extraction_cache=retry_failed_extraction_cache,
        ignore_failed_extraction_cache=ignore_failed_extraction_cache,
        retry_failed_llm=retry_failed_llm,
    )

    with pipeline_progress(console, quiet=quiet, verbose=verbose) as progress:
        bundle = run_cli_repair_pipeline(
            export_dir=Path(export_dir),
            output_dir=Path(output_dir) if output_dir else None,
            extraction_mode=extraction_mode,
            extraction_fallback=extraction_fallback,
            only=lit_only,
            in_place=in_place,
            source_cache_dir=source_cache_dir,
            derived_cache_dir=derived_cache_dir,
            use_llm=use_llm,
            progress=progress,
            **cache_retry,
        )
    meta = bundle.get("extraction_repair_metadata") or {}
    console.print(Panel.fit("Repair complete", style="green"))
    console.print(json.dumps(meta, indent=2))
    rq = bundle.get("run_quality_summary")
    if isinstance(rq, dict):
        console.print(json.dumps({"run_quality_summary": rq}, indent=2))


@app.command("repair-extraction-json")
def repair_extraction_json(
    export_dir: str = typer.Option(
        "dist/static-report",
        "--export-dir",
        help="Source export bundle with failed extraction JSON excerpts.",
    ),
    output_dir: str = typer.Option(
        ...,
        "--output-dir",
        help="Write JSON-repaired bundle here.",
    ),
    use_llm_repair: bool = typer.Option(
        False,
        "--use-llm-repair",
        help="Reserved for a future model-backed repair pass (default: deterministic only).",
    ),
) -> None:
    from .extraction_json_repair import run_cli_json_repair_pipeline

    try:
        bundle = run_cli_json_repair_pipeline(
            export_dir=Path(export_dir),
            output_dir=Path(output_dir),
            use_llm_repair=use_llm_repair,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except NotImplementedError as exc:
        raise typer.BadParameter(str(exc)) from exc

    meta = bundle.get("extraction_json_repair_metadata") or {}
    console.print(Panel.fit("JSON extraction repair complete", style="green"))
    console.print(
        json.dumps(
            {
                "failed_chunks_considered": meta.get("failed_chunks_considered", 0),
                "repaired_chunks": meta.get("repaired_chunks", 0),
                "recovered_propositions": meta.get("recovered_propositions", 0),
                "still_failed_chunks": meta.get("still_failed_chunks", 0),
            },
            indent=2,
        )
    )
    console.print(json.dumps(meta, indent=2))


@app.command("repair-fragment")
def repair_fragment_cmd(
    export_dir: str = typer.Option(
        ...,
        "--export-dir",
        help="Source export bundle to patch.",
    ),
    output_dir: str = typer.Option(
        ...,
        "--output-dir",
        help="Write fragment-repaired export here.",
    ),
    source_id: str = typer.Option(..., "--source-id", help="Source record id."),
    locator: str = typer.Option(..., "--locator", help="Fragment locator (e.g. regulation:2)."),
    extraction_mode: str = typer.Option("frontier", "--extraction-mode", help="local | frontier"),
    max_propositions: int = typer.Option(
        12,
        "--max-propositions",
        min=1,
        help="Maximum propositions to extract from the fragment.",
    ),
    retry_empty_extraction: bool = typer.Option(
        True,
        "--retry-empty-extraction/--no-retry-empty-extraction",
        help="Retry once when extraction returns empty JSON (default: on).",
    ),
    extraction_output_mode: str | None = typer.Option(
        None,
        "--extraction-output-mode",
        help="LLM structured output: json_object | json_schema | text_then_parse.",
    ),
    allow_output_mode_fallback: bool = typer.Option(
        False,
        "--allow-output-mode-fallback/--no-allow-output-mode-fallback",
        help="Fall back to json_object when json_schema is unsupported or rejected.",
    ),
    use_llm: bool = typer.Option(True, "--use-llm/--no-use-llm"),
) -> None:
    from .extraction_fragment_repair import run_fragment_repair_pipeline

    if extraction_mode not in {"local", "frontier"}:
        raise typer.BadParameter("--extraction-mode must be local or frontier")
    output_mode_kwargs = _extraction_output_mode_kwargs(
        extraction_output_mode=extraction_output_mode,
        allow_output_mode_fallback=allow_output_mode_fallback,
    )
    try:
        bundle = run_fragment_repair_pipeline(
            export_dir=Path(export_dir),
            output_dir=Path(output_dir),
            source_id=source_id,
            locator=locator,
            extraction_mode=extraction_mode,  # type: ignore[arg-type]
            max_propositions=max_propositions,
            retry_empty_extraction=retry_empty_extraction,
            use_llm=use_llm,
            **output_mode_kwargs,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    meta = bundle.get("fragment_repair_summary") or {}
    console.print(Panel.fit("Fragment repair complete", style="green"))
    console.print(
        json.dumps(
            {
                "source_record_id": meta.get("source_record_id"),
                "fragment_locator": meta.get("fragment_locator"),
                "removed_proposition_count": meta.get("removed_proposition_count"),
                "added_proposition_count": meta.get("added_proposition_count"),
                "proposition_count_before": meta.get("proposition_count_before"),
                "proposition_count_after": meta.get("proposition_count_after"),
                "npp_reg2_definition_anchors": meta.get("npp_reg2_definition_anchors"),
            },
            indent=2,
        )
    )


@app.command("verify-regulation-paragraph-fragments")
def verify_regulation_paragraph_fragments_cmd(
    fixture: Path | None = typer.Option(
        None,
        "--fixture",
        help="Offline CLML XML fixture. Omit the value to use the bundled WSI 2021/77 regulation 36 fixture.",
    ),
    case_path: Path | None = typer.Option(
        None,
        "--case",
        help="Case JSON — ingest WSI 2021/77 via legislation.gov.uk (network, no LLM).",
    ),
    export_dir: Path | None = typer.Option(
        None,
        "--export-dir",
        help="Verify an existing export's source_fragments.json (no fetch).",
    ),
    authority_source_id: str = typer.Option(
        "wsi/2021/77",
        "--authority-source-id",
        help="Legislation.gov.uk authority source id.",
    ),
    source_record_id: str = typer.Option(
        "lex-805b03f284dcf364",
        "--source-record-id",
        help="Source record id filter for export verification.",
    ),
    locator_prefix: str = typer.Option(
        "regulation:36",
        "--locator-prefix",
        help="Locator prefix to list and verify.",
    ),
    source_cache_dir: Path | None = typer.Option(
        None,
        "--source-cache-dir",
        help="Optional source snapshot cache directory for --case mode.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Write REGULATION_PARAGRAPH_FRAGMENTATION_VERIFICATION.md/json here.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print verification JSON to stdout.",
    ),
) -> None:
    """Verify regulation paragraph structural fragments without LLM extraction."""
    from .regulation_paragraph_fragmentation_verification import (
        EXPECTED_REGULATION_36_LOCATORS,
        build_report_from_case,
        build_report_from_export,
        build_report_from_fixture_xml,
        print_verification_console_summary,
        verification_exit_code,
        write_verification_outputs,
    )

    default_fixture = (
        Path(__file__).resolve().parents[4]
        / "tests"
        / "fixtures"
        / "regulation_paragraph_fragmentation"
        / "wsi_2021_77_regulation_36.xml"
    )
    common = {
        "authority_source_id": authority_source_id,
        "source_record_id": source_record_id,
        "locator_prefix": locator_prefix,
        "expected_locators": EXPECTED_REGULATION_36_LOCATORS,
    }

    if export_dir is not None:
        report = build_report_from_export(export_dir.resolve(), **common)
    elif case_path is not None:
        report = build_report_from_case(
            case_path.resolve(),
            cache_dir=source_cache_dir.resolve() if source_cache_dir else None,
            **common,
        )
    elif fixture is not None:
        report = build_report_from_fixture_xml(fixture.resolve(), **common)
    else:
        report = build_report_from_fixture_xml(default_fixture.resolve(), **common)

    print_verification_console_summary(report)
    if json_output:
        console.print_json(json.dumps(report.to_dict()))
    if output_dir is not None:
        md_path, json_path = write_verification_outputs(output_dir.resolve(), report)
        console.print(f"Wrote {md_path}")
        console.print(f"Wrote {json_path}")
    if verification_exit_code(report) != 0:
        raise typer.Exit(code=1)


def demo_command() -> None:
    demo(use_llm=False)


def main() -> None:
    app(prog_name="law-proposition-extractor-run-case")


def run_case_command() -> None:
    main()


def export_case_command() -> None:
    app(prog_name="law-proposition-extractor-export-case")
