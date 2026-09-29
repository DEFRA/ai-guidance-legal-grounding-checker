"""Paths for live proposition calibration artifacts (evaluation-only)."""

from __future__ import annotations

from pathlib import Path

from law_proposition_extractor_pipeline.source_structure_fixtures import judit_root

CALIBRATION_ROOT_RELATIVE = Path("calibration/proposition_fidelity")
CALIBRATION_CASES: tuple[str, ...] = (
    "article_49a",
    "uk_regulation_12_spread",
    "wsi_regulation_36_4",
)
REPETITIONS: tuple[int, ...] = (1, 2, 3)
SAMPLE_FIXTURE_RELATIVE = Path("tests/fixtures/live_proposition_calibration/sample_run")
DOCS_RELATIVE = Path("docs/explainability/live-proposition-calibration.md")


def calibration_root(*, root: Path | None = None) -> Path:
    return (root or judit_root()) / CALIBRATION_ROOT_RELATIVE


def run_dir(calibration_run_id: str, *, root: Path | None = None) -> Path:
    return calibration_root(root=root) / calibration_run_id


def calls_dir(calibration_run_id: str, *, root: Path | None = None) -> Path:
    return run_dir(calibration_run_id, root=root) / "calls"


def call_artifact_name(case_id: str, repetition: int) -> str:
    return f"{case_id}-{repetition}.json"


def sample_fixture_dir(*, root: Path | None = None) -> Path:
    return (root or judit_root()) / SAMPLE_FIXTURE_RELATIVE
