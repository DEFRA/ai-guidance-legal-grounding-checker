from __future__ import annotations

from law_discovery.progress import (
    ETA_UNKNOWN,
    CliProgressTracker,
    format_duration,
)


def test_format_duration_minutes_and_seconds() -> None:
    assert format_duration(0) == "00:00"
    assert format_duration(68) == "01:08"
    assert format_duration(134) == "02:14"


def test_format_duration_hours() -> None:
    assert format_duration(3661) == "01:01:01"
    assert format_duration(7200) == "02:00:00"


def test_format_duration_rounds_to_nearest_second() -> None:
    assert format_duration(68.4) == "01:08"
    assert format_duration(68.6) == "01:09"


def test_percentage_and_eta_when_nothing_completed() -> None:
    tracker = CliProgressTracker(label="Searching", unit="queries", total=66)
    assert tracker.percentage == 0
    assert tracker.format_eta() == ETA_UNKNOWN
    assert "ETA calculating" in tracker.format_line()


def test_eta_from_observed_throughput() -> None:
    start = 1000.0
    tracker = CliProgressTracker(
        label="Searching",
        unit="queries",
        total=66,
        completed=18,
        _start_time=start,
        _now=lambda: start + 68,
    )
    assert tracker.percentage == 27
    assert tracker.elapsed_seconds == 68
    assert tracker.eta_seconds == 68 / 18 * (66 - 18)
    assert tracker.format_eta() == "03:01"
    assert tracker.format_line() == (
        "Searching 18/66 queries · 27% · elapsed 01:08 · ETA 03:01"
    )


def test_triage_line_format() -> None:
    start = 2000.0
    tracker = CliProgressTracker(
        label="Triaging",
        unit="candidates",
        total=276,
        completed=37,
        _start_time=start,
        _now=lambda: start + 134,
    )
    assert tracker.format_line() == (
        "Triaging 37/276 candidates · 13% · elapsed 02:14 · ETA 14:26"
    )


def test_eta_none_when_complete() -> None:
    tracker = CliProgressTracker(
        label="Validating",
        unit="sources",
        total=51,
        completed=51,
        _start_time=0.0,
        _now=lambda: 42.0,
    )
    assert tracker.format_eta() == ETA_UNKNOWN
    assert tracker.percentage == 100


def test_set_completed_clamps_to_total() -> None:
    tracker = CliProgressTracker(label="Searching", unit="queries", total=10)
    tracker.set_completed(15)
    assert tracker.completed == 10
    tracker.set_completed(-3)
    assert tracker.completed == 0
