"""Paths and constants for the Law Proposition Extractor explainability handbook generator."""

from __future__ import annotations

from pathlib import Path

GENERATION_COMMAND = (
    "uv run --package law_proposition_extractor_pipeline python -m law_proposition_extractor_pipeline.explainability_docs generate"
)
CHECK_COMMAND = "uv run --package law_proposition_extractor_pipeline python -m law_proposition_extractor_pipeline.explainability_docs check"

HANDBOOK_RELATIVE = Path("docs/explainability")
FIXTURE_RELATIVE = Path("tests/fixtures/article_49a_legal_structure")

GENERATED_FILES = (
    "heuristics.md",
    "article-49a-walkthrough.md",
)

HANDWRITTEN_FILES = (
    "README.md",
    "concepts.md",
    "pipeline.md",
    "artifacts-and-lineage.md",
    "glossary.md",
    "diagrams.md",
)

ALL_HANDBOOK_FILES = HANDWRITTEN_FILES + GENERATED_FILES


def repo_root() -> Path:
    """Return the Law Proposition Extractor repository root (directory containing ``docs/``)."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "docs" / "explainability").is_dir() and (
            candidate / "packages" / "pipeline"
        ).is_dir():
            return candidate
        if (candidate / "law-proposition-extractor" / "docs" / "explainability").is_dir():
            return candidate / "law-proposition-extractor"
    raise RuntimeError("Could not locate Law Proposition Extractor repository root from explainability_docs package.")


def handbook_dir(root: Path | None = None) -> Path:
    base = root or repo_root()
    return base / HANDBOOK_RELATIVE


def fixture_dir(root: Path | None = None) -> Path:
    base = root or repo_root()
    return base / FIXTURE_RELATIVE
