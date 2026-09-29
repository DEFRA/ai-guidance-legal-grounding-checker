"""Paths and catalogue for Law Proposition Extractor explainability diagrams."""

from __future__ import annotations

from pathlib import Path

from ..paths import repo_root

DIAGRAM_SOURCE_RELATIVE = Path("docs/assets/diagrams/explainability")
DIAGRAM_OUTPUT_RELATIVE = Path("docs/assets/generated/diagrams/explainability")
DIAGRAMS_INDEX_RELATIVE = Path("docs/explainability/diagrams.md")
DIVERGENCE_STATUS_MANIFEST = "divergence-implementation-status.json"

# Stable catalogue — every entry must have a committed .d2 and .svg.
DIAGRAM_IDS: tuple[str, ...] = (
    "law-proposition-extractor-system-map",
    "source-to-statement-pipeline",
    "legal-structure-data-model",
    "source-version-and-effects",
    "article-49a-walkthrough",
    "divergence-workflow",
)

# Fully generated from fixture/acceptance helpers (anti-drift).
GENERATED_D2_IDS: frozenset[str] = frozenset({"article-49a-walkthrough"})

# Hand-authored D2 with a generated data section filled at generate time.
MIXED_D2_IDS: frozenset[str] = frozenset({"divergence-workflow"})

# Pure hand-authored layout (metadata comments only may be refreshed).
HAND_AUTHORED_D2_IDS: frozenset[str] = frozenset(DIAGRAM_IDS) - GENERATED_D2_IDS - MIXED_D2_IDS

D2_RENDER_ARGS: tuple[str, ...] = (
    "--layout=dagre",
    "--theme=0",
    "--pad=48",
    "--scale=1",
)


def diagram_source_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / DIAGRAM_SOURCE_RELATIVE


def diagram_output_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / DIAGRAM_OUTPUT_RELATIVE


def diagrams_index_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / DIAGRAMS_INDEX_RELATIVE


def d2_path(diagram_id: str, root: Path | None = None) -> Path:
    return diagram_source_dir(root) / f"{diagram_id}.d2"


def svg_path(diagram_id: str, root: Path | None = None) -> Path:
    return diagram_output_dir(root) / f"{diagram_id}.svg"


def divergence_status_manifest_path(root: Path | None = None) -> Path:
    return diagram_source_dir(root) / DIVERGENCE_STATUS_MANIFEST
