"""Generate and check Law Proposition Extractor explainability handbook documents."""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import diagrams as explainability_diagrams
from .article_49a_walkthrough import render_article_49a_walkthrough_body
from .heuristics_catalogue import render_heuristic_catalogue
from .markers import MarkerError, assert_markers_balanced, replace_generated_section
from .paths import (
    ALL_HANDBOOK_FILES,
    GENERATED_FILES,
    handbook_dir,
    repo_root,
)

_HEURISTICS_SECTION = "heuristic-catalogue"
_WALKTHROUGH_SECTION = "article-49a-walkthrough"


@dataclass(frozen=True)
class GenerateResult:
    written: tuple[Path, ...]
    unchanged: tuple[Path, ...]


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    stale: tuple[str, ...]
    message: str


def _apply_heuristics(document: str) -> str:
    assert_markers_balanced(document)
    return replace_generated_section(document, _HEURISTICS_SECTION, render_heuristic_catalogue())


def _apply_walkthrough(document: str) -> str:
    assert_markers_balanced(document)
    return replace_generated_section(
        document, _WALKTHROUGH_SECTION, render_article_49a_walkthrough_body()
    )


def _assert_no_local_path_leaks(text: str, *, label: str) -> None:
    if "file://" in text:
        raise RuntimeError(f"{label} contains a file:// link.")
    for token in ("/Users/", "/home/", "/private/var/", "C:\\"):
        if token in text:
            raise RuntimeError(f"{label} contains an absolute filesystem path ({token}).")


def _render_document(name: str, source_text: str) -> str:
    if name == "heuristics.md":
        rendered = _apply_heuristics(source_text)
    elif name == "article-49a-walkthrough.md":
        rendered = _apply_walkthrough(source_text)
    else:
        rendered = source_text
    if name in GENERATED_FILES:
        _assert_no_local_path_leaks(rendered, label=name)
    return rendered


def generate(*, root: Path | None = None, dry_run: bool = False) -> GenerateResult:
    """Update generated sections in the handbook directory and diagram suite."""
    base = handbook_dir(root or repo_root())
    written: list[Path] = []
    unchanged: list[Path] = []
    for name in GENERATED_FILES:
        path = base / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing handbook file: {path}")
        original = path.read_text(encoding="utf-8")
        updated = _render_document(name, original)
        if updated == original:
            unchanged.append(path)
            continue
        if not dry_run:
            path.write_text(updated, encoding="utf-8")
        written.append(path)
    diagram_result = explainability_diagrams.generate(root=root or repo_root(), dry_run=dry_run)
    written.extend(diagram_result.written_d2)
    written.extend(diagram_result.written_svg)
    unchanged.extend(diagram_result.unchanged_d2)
    unchanged.extend(diagram_result.unchanged_svg)
    return GenerateResult(written=tuple(written), unchanged=tuple(unchanged))


def render_all_to_directory(output_dir: Path, *, root: Path | None = None) -> None:
    """Render handbook files into ``output_dir`` (for check mode)."""
    base = handbook_dir(root or repo_root())
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ALL_HANDBOOK_FILES:
        src = base / name
        if not src.is_file():
            raise FileNotFoundError(f"Missing handbook file: {src}")
        text = src.read_text(encoding="utf-8")
        rendered = _render_document(name, text) if name in GENERATED_FILES else text
        (output_dir / name).write_text(rendered, encoding="utf-8")


def check(*, root: Path | None = None) -> CheckResult:
    """Compare committed generated sections to a fresh in-memory/temp render.

    Does not modify the working tree. Also checks explainability diagrams.
    """
    base = handbook_dir(root or repo_root())
    stale: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lpe-explainability-docs-") as tmp:
        tmp_path = Path(tmp)
        try:
            render_all_to_directory(tmp_path, root=root or repo_root())
        except MarkerError as exc:
            return CheckResult(
                ok=False,
                stale=(),
                message=f"Explainability docs check failed: {exc}",
            )
        for name in GENERATED_FILES:
            committed = (base / name).read_text(encoding="utf-8")
            expected = (tmp_path / name).read_text(encoding="utf-8")
            if committed != expected:
                stale.append(name)
    diagram_check = explainability_diagrams.check(root=root or repo_root())
    if not diagram_check.ok:
        stale.extend(diagram_check.stale)
        if stale:
            joined = ", ".join(stale)
            return CheckResult(
                ok=False,
                stale=tuple(stale),
                message=(
                    "Explainability docs/diagrams are stale for: "
                    f"{joined}. {diagram_check.message}"
                ),
            )
        return CheckResult(
            ok=False,
            stale=(),
            message=diagram_check.message,
        )
    if stale:
        joined = ", ".join(stale)
        return CheckResult(
            ok=False,
            stale=tuple(stale),
            message=(
                "Explainability docs are stale for: "
                f"{joined}. Run "
                "`uv run --package law_proposition_extractor_pipeline python -m "
                "law_proposition_extractor_pipeline.explainability_docs generate` "
                "or `just generate-explainability-docs`."
            ),
        )
    return CheckResult(
        ok=True,
        stale=(),
        message=(
            "Explainability docs are up to date. " + diagram_check.message
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m law_proposition_extractor_pipeline.explainability_docs",
        description=(
            "Generate or check Law Proposition Extractor explainability handbook sections from "
            "the heuristic registry and Article 49a acceptance fixture."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="Update generated Markdown sections in place.")
    sub.add_parser(
        "check",
        help="Fail if committed generated sections are stale (no writes).",
    )
    args = parser.parse_args(argv)

    if args.command == "generate":
        result = generate()
        for path in result.written:
            print(f"updated {path.relative_to(repo_root())}")
        for path in result.unchanged:
            print(f"unchanged {path.relative_to(repo_root())}")
        return 0

    if args.command == "check":
        result = check()
        print(result.message)
        return 0 if result.ok else 1

    parser.error(f"Unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
