from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ProgressCallback = Callable[["DiscoveryProgressEvent"], None]

ETA_UNKNOWN = "calculating"


@dataclass(frozen=True)
class DiscoveryProgressEvent:
    stage: str
    message: str
    current: int | None = None
    total: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def emit_progress(
    callback: ProgressCallback | None,
    event: DiscoveryProgressEvent,
) -> None:
    if callback is not None:
        callback(event)


def format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS for terminal display."""
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


@dataclass
class CliProgressTracker:
    """Track throughput-based progress and ETA for long-running CLI work."""

    label: str
    unit: str
    total: int
    completed: int = 0
    secondary_label: str | None = None
    secondary_count: int = 0
    _start_time: float = field(default_factory=time.monotonic)
    _now: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self._now() - self._start_time)

    @property
    def percentage(self) -> int:
        if self.total <= 0:
            return 100 if self.completed > 0 else 0
        return min(100, int(self.completed * 100 / self.total))

    @property
    def eta_seconds(self) -> float | None:
        if self.completed <= 0 or self.total <= self.completed:
            return None
        average_seconds = self.elapsed_seconds / self.completed
        remaining = self.total - self.completed
        return average_seconds * remaining

    def set_completed(self, completed: int) -> None:
        self.completed = max(0, min(completed, self.total))

    def format_eta(self) -> str:
        eta = self.eta_seconds
        if eta is None:
            return ETA_UNKNOWN
        return format_duration(eta)

    def set_secondary_count(self, count: int) -> None:
        self.secondary_count = max(0, count)

    def format_line(self) -> str:
        line = (
            f"{self.label} {self.completed}/{self.total} {self.unit} · "
            f"{self.percentage}% · "
            f"elapsed {format_duration(self.elapsed_seconds)} · "
            f"ETA {self.format_eta()}"
        )
        if self.secondary_label is not None:
            line = f"{line} · {self.secondary_count} {self.secondary_label}"
        return line
