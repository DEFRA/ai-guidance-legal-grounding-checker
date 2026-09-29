"""Offline multi-instrument proposition-fidelity benchmark (Law Proposition Extractor-only).

Test/audit infrastructure. Not part of ordinary production export bundles.
"""

from __future__ import annotations

from .results import (
    DimensionStatus,
    PropositionFidelityBenchmarkResult,
    PropositionFidelityCaseResult,
    PropositionFidelityRoleResult,
)
from .runner import run_proposition_fidelity_benchmark

__all__ = [
    "DimensionStatus",
    "PropositionFidelityBenchmarkResult",
    "PropositionFidelityCaseResult",
    "PropositionFidelityRoleResult",
    "run_proposition_fidelity_benchmark",
]
