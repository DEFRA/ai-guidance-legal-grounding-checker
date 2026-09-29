from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from rich.console import Console

from law_discovery.console import DiscoveryConsole, OutputMode
from law_discovery.models import CandidateSource, CandidateTriageMetadata, CategoryBrief, DiscoveryRun
from law_discovery.progress import DiscoveryProgressEvent


def test_handle_progress_plain_shows_eta_line() -> None:
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.PLAIN)
    console.console = Console(file=stderr, no_color=True, highlight=False, width=200)

    console.handle_progress(
        DiscoveryProgressEvent(stage="lex_search_start", message="Searching Lex", total=3)
    )
    console.handle_progress(
        DiscoveryProgressEvent(
            stage="lex_search_result",
            message="Collected 0 raw candidates",
            current=1,
            total=3,
        )
    )
    console.handle_progress(
        DiscoveryProgressEvent(stage="lex_search_complete", message="Lex search complete")
    )

    output = stderr.getvalue()
    assert "Searching 1/3 queries" in output
    assert "ETA calculating" in output or "ETA " in output
    assert "Searching 3/3 queries · 100%" in output


def test_built_queries_each_shown_once_rich() -> None:
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.RICH)
    console.console = Console(file=stderr, width=120)

    queries = ["first query", "second query"]
    console.handle_progress(
        DiscoveryProgressEvent(stage="build_query_plan", message="Building query plan...")
    )
    console.handle_progress(
        DiscoveryProgressEvent(
            stage="build_query_plan",
            message="Built 2 queries",
            extra={"query_count": 2, "queries": queries},
        )
    )
    console.handle_progress(
        DiscoveryProgressEvent(stage="lex_search_start", message="Searching Lex", total=2)
    )
    for index, query in enumerate(queries, start=1):
        console.handle_progress(
            DiscoveryProgressEvent(
                stage="lex_search_query",
                message=query,
                current=index,
                total=2,
                extra={"query": query},
            )
        )
        console.handle_progress(
            DiscoveryProgressEvent(
                stage="lex_search_result",
                message="Collected 0 raw candidates",
                current=index,
                total=2,
                extra={"raw_count": 0, "query": query},
            )
        )

    output = stderr.getvalue()
    assert "Built 2 queries" in output
    for query in queries:
        assert output.count(query) == 1, f"{query!r} appeared {output.count(query)} times"


def test_built_queries_each_shown_once_plain() -> None:
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.PLAIN)
    console.console = Console(file=stderr, no_color=True, highlight=False, width=200)

    queries = ["first query", "second query"]
    console.handle_progress(
        DiscoveryProgressEvent(
            stage="build_query_plan",
            message="Built 2 queries",
            extra={"query_count": 2, "queries": queries},
        )
    )
    for index, query in enumerate(queries, start=1):
        console.handle_progress(
            DiscoveryProgressEvent(
                stage="lex_search_query",
                message=query,
                current=index,
                total=2,
                extra={"query": query},
            )
        )

    output = stderr.getvalue()
    for query in queries:
        assert output.count(query) == 1, f"{query!r} appeared {output.count(query)} times"


def _run_with_ai_triage_metadata(**metadata: object) -> DiscoveryRun:
    return DiscoveryRun(
        run_id="law-discovery-run-test",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        category=CategoryBrief(
            category_id="slurry",
            label="Slurry and manure",
            description="Test",
        ),
        query_plan=[],
        candidate_sources=[],
        metadata={
            "ai_triage_requested": True,
            "ai_triage_batch_count": 2,
            "ai_triage_successful_batch_count": 0,
            "ai_triage_failed_batch_count": 2,
            "ai_triage_successful_candidate_count": 0,
            "ai_triage_fallback_candidate_count": 4,
            "ai_triage_failed": True,
            "ai_triage_partial": False,
            "ai_triage_failure_reasons": ["AI triage batch failed: Connection error"],
            **metadata,
        },
    )


def test_show_summary_plain_reports_ai_triage_failure() -> None:
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.PLAIN)
    console.console = Console(file=stderr, no_color=True, highlight=False, width=200)

    console.show_summary(_run_with_ai_triage_metadata(), Path("runs/slurry/discovery-run.json"))

    output = stderr.getvalue()
    assert "AI triage requested: yes" in output
    assert "AI triage failed for all batches:" in output
    assert "Connection error" in output.replace("\n", " ")


def test_show_summary_rich_reports_ai_triage_failure_panel() -> None:
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.RICH)
    console.console = Console(file=stderr, width=120)

    console.show_summary(_run_with_ai_triage_metadata(), Path("runs/slurry/discovery-run.json"))

    output = stderr.getvalue()
    normalized = " ".join(output.replace("│", " ").split())
    assert "AI triage failed for all batches" in normalized
    assert "untriaged fallback assessments" in normalized


def test_show_summary_plain_prefers_ai_triage_counts() -> None:
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.PLAIN)
    console.console = Console(file=stderr, no_color=True, highlight=False, width=200)

    run = DiscoveryRun(
        run_id="law-discovery-run-triage-summary",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        category=CategoryBrief(category_id="slurry", label="Slurry", description="Test"),
        query_plan=[],
        candidate_sources=[
            CandidateSource(
                source_id="a",
                title="NVZ Regulations",
                confidence="high",
                ai_triage=CandidateTriageMetadata(
                    relevance="high",
                    review_priority="likely_accept",
                    relationship_to_category="directly_regulates",
                    confidence_after_ai="high",
                    recommended_action="accept_candidate",
                    rationale="Core.",
                ),
            ),
            CandidateSource(
                source_id="b",
                title="Local Act",
                confidence="high",
                ai_triage=CandidateTriageMetadata(
                    relevance="not_relevant",
                    review_priority="likely_reject",
                    relationship_to_category="unknown",
                    confidence_after_ai="low",
                    recommended_action="reject_candidate",
                    rationale="Noise.",
                ),
            ),
        ],
        metadata={"ai_triage_requested": True},
    )
    console.show_summary(run, Path("runs/slurry/discovery-run.json"))

    output = stderr.getvalue()
    assert "AI review priority:" in output
    assert "likely_accept=1" in output
    assert "likely_reject=1" in output
    assert "AI-adjusted confidence:" in output
    assert "[law-discovery] confidence:" not in output
    assert "[likely_accept]" in output
    assert "--accept-ai-likely-accept" in output


def test_show_summary_rich_reports_ai_triage_partial_panel() -> None:
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.RICH)
    console.console = Console(file=stderr, width=120)

    run = _run_with_ai_triage_metadata(
        ai_triage_successful_batch_count=1,
        ai_triage_failed_batch_count=1,
        ai_triage_failed=False,
        ai_triage_partial=True,
    )
    console.show_summary(run, Path("runs/slurry/discovery-run.json"))

    output = stderr.getvalue()
    normalized = " ".join(output.replace("│", " ").split())
    assert "AI triage partially failed." in normalized
    assert "Some candidates require manual review." in normalized
