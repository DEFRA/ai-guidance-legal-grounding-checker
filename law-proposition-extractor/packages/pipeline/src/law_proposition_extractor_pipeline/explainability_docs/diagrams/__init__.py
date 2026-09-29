"""Generate and check Law Proposition Extractor explainability diagram suite (D2 → SVG)."""

from __future__ import annotations

import argparse
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from law_proposition_extractor_pipeline.heuristics import REGISTRY_VERSION

from ..fixture_bundle import fixture_content_hash
from ..markers import MarkerError
from ..paths import repo_root
from .article_49a import (
    assert_article_49a_d2_contract,
    render_article_49a_walkthrough_d2,
)
from .d2_markers import assert_d2_markers_balanced
from .divergence import (
    apply_divergence_generated_section,
    assert_divergence_d2_truthfulness,
)
from .paths import (
    DIAGRAM_IDS,
    GENERATED_D2_IDS,
    MIXED_D2_IDS,
    d2_path,
    diagram_output_dir,
    diagram_source_dir,
    diagrams_index_path,
    svg_path,
)
from .render import D2RenderError, assert_svg_safe, find_d2_binary, render_d2_to_svg


@dataclass(frozen=True)
class DiagramGenerateResult:
    written_d2: tuple[Path, ...]
    written_svg: tuple[Path, ...]
    unchanged_d2: tuple[Path, ...]
    unchanged_svg: tuple[Path, ...]
    generate_seconds: float
    render_seconds: float


@dataclass(frozen=True)
class DiagramCheckResult:
    ok: bool
    stale: tuple[str, ...]
    message: str
    check_seconds: float
    generate_seconds: float
    render_seconds: float


_MANAGED_META_PREFIXES = (
    "# explainability-diagram:",
    "# compatible-registry-version:",
    "# compatible-fixture-hash:",
    "# authorship:",
)


def _upsert_managed_metadata(document: str, diagram_id: str, *, authorship: str) -> str:
    """Refresh only managed metadata keys; preserve title/audience/purpose comments."""
    short_hash = fixture_content_hash()[:12]
    managed = {
        "# explainability-diagram:": f"# explainability-diagram: {diagram_id}",
        "# compatible-registry-version:": (
            f"# compatible-registry-version: {REGISTRY_VERSION}"
        ),
        "# compatible-fixture-hash:": f"# compatible-fixture-hash: {short_hash}",
        "# authorship:": f"# authorship: {authorship}",
    }
    lines = document.splitlines()
    # Drop existing managed keys anywhere in the leading comment block.
    kept: list[str] = []
    in_leading_comments = True
    for line in lines:
        if in_leading_comments and line.startswith("#"):
            if any(line.startswith(prefix) for prefix in _MANAGED_META_PREFIXES):
                continue
            kept.append(line)
            continue
        if in_leading_comments and line.strip() == "":
            kept.append(line)
            continue
        in_leading_comments = False
        kept.append(line)

    # Insert managed block at the very top (stable order).
    header = [managed[key] for key in _MANAGED_META_PREFIXES]
    # Avoid duplicating a blank line if kept already starts with one.
    body = "\n".join(kept).lstrip("\n")
    return "\n".join(header) + ("\n" + body if body else "\n")


def build_d2_text(diagram_id: str, *, root: Path | None = None) -> str:
    """Build the final D2 source text for ``diagram_id`` (offline, no LLM)."""
    base = root or repo_root()
    if diagram_id in GENERATED_D2_IDS:
        text = render_article_49a_walkthrough_d2()
        assert_article_49a_d2_contract(text)
        return text if text.endswith("\n") else text + "\n"

    path = d2_path(diagram_id, base)
    if not path.is_file():
        raise FileNotFoundError(f"Missing diagram source: {path}")
    body = path.read_text(encoding="utf-8")

    if diagram_id in MIXED_D2_IDS:
        assert_d2_markers_balanced(body)
        body = apply_divergence_generated_section(body, root=base)
        assert_divergence_d2_truthfulness(body, root=base)
        authorship = "mixed"
    else:
        authorship = "hand-authored"

    text = _upsert_managed_metadata(body, diagram_id, authorship=authorship)
    return text if text.endswith("\n") else text + "\n"


def render_diagram_svgs(
    d2_dir: Path,
    svg_dir: Path,
    *,
    d2_binary: str | None = None,
) -> float:
    """Render all catalogue diagrams; return render wall time in seconds."""
    binary = d2_binary or find_d2_binary()
    svg_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    for diagram_id in DIAGRAM_IDS:
        source = d2_dir / f"{diagram_id}.d2"
        output = svg_dir / f"{diagram_id}.svg"
        render_d2_to_svg(source, output, d2_binary=binary)
        assert_svg_safe(output.read_text(encoding="utf-8"), label=output.name)
    return time.perf_counter() - started


def generate(*, root: Path | None = None, dry_run: bool = False) -> DiagramGenerateResult:
    """Update committed D2 sources and SVG outputs."""
    base = root or repo_root()
    diagram_source_dir(base).mkdir(parents=True, exist_ok=True)
    diagram_output_dir(base).mkdir(parents=True, exist_ok=True)

    prior_d2 = {
        diagram_id: (
            d2_path(diagram_id, base).read_text(encoding="utf-8")
            if d2_path(diagram_id, base).is_file()
            else ""
        )
        for diagram_id in DIAGRAM_IDS
    }
    prior_svg = {
        diagram_id: (
            svg_path(diagram_id, base).read_bytes()
            if svg_path(diagram_id, base).is_file()
            else b""
        )
        for diagram_id in DIAGRAM_IDS
    }

    gen_started = time.perf_counter()
    built: dict[str, str] = {}
    for diagram_id in DIAGRAM_IDS:
        built[diagram_id] = build_d2_text(diagram_id, root=base)
    generate_seconds = time.perf_counter() - gen_started

    written_d2: list[Path] = []
    unchanged_d2: list[Path] = []
    for diagram_id, text in built.items():
        path = d2_path(diagram_id, base)
        if prior_d2[diagram_id] == text:
            unchanged_d2.append(path)
        else:
            if not dry_run:
                path.write_text(text, encoding="utf-8")
            written_d2.append(path)

    with tempfile.TemporaryDirectory(prefix="lpe-explainability-svg-") as tmp:
        tmp_path = Path(tmp)
        tmp_d2 = tmp_path / "d2"
        tmp_svg = tmp_path / "svg"
        tmp_d2.mkdir()
        for diagram_id, text in built.items():
            (tmp_d2 / f"{diagram_id}.d2").write_text(text, encoding="utf-8")
        render_seconds = render_diagram_svgs(tmp_d2, tmp_svg)

        written_svg: list[Path] = []
        unchanged_svg: list[Path] = []
        for diagram_id in DIAGRAM_IDS:
            out = svg_path(diagram_id, base)
            new_bytes = (tmp_svg / f"{diagram_id}.svg").read_bytes()
            if prior_svg[diagram_id] == new_bytes:
                unchanged_svg.append(out)
            else:
                if not dry_run:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(new_bytes)
                written_svg.append(out)

    return DiagramGenerateResult(
        written_d2=tuple(written_d2),
        written_svg=tuple(written_svg),
        unchanged_d2=tuple(unchanged_d2),
        unchanged_svg=tuple(unchanged_svg),
        generate_seconds=generate_seconds,
        render_seconds=render_seconds,
    )


def check(*, root: Path | None = None) -> DiagramCheckResult:
    """Fail if committed D2/SVG are stale. Does not modify the working tree."""
    base = root or repo_root()
    started = time.perf_counter()
    stale: list[str] = []
    generate_seconds = 0.0
    render_seconds = 0.0

    try:
        find_d2_binary()
    except D2RenderError as exc:
        return DiagramCheckResult(
            ok=False,
            stale=(),
            message=str(exc),
            check_seconds=time.perf_counter() - started,
            generate_seconds=0.0,
            render_seconds=0.0,
        )

    with tempfile.TemporaryDirectory(prefix="lpe-explainability-diagrams-") as tmp:
        tmp_path = Path(tmp)
        tmp_d2 = tmp_path / "d2"
        tmp_svg = tmp_path / "svg"
        try:
            gen_started = time.perf_counter()
            built: dict[str, str] = {}
            tmp_d2.mkdir()
            for diagram_id in DIAGRAM_IDS:
                text = build_d2_text(diagram_id, root=base)
                built[diagram_id] = text
                (tmp_d2 / f"{diagram_id}.d2").write_text(text, encoding="utf-8")
            generate_seconds = time.perf_counter() - gen_started
            render_seconds = render_diagram_svgs(tmp_d2, tmp_svg)
        except (MarkerError, D2RenderError, FileNotFoundError, RuntimeError, AssertionError) as exc:
            return DiagramCheckResult(
                ok=False,
                stale=(),
                message=f"Explainability diagrams check failed: {exc}",
                check_seconds=time.perf_counter() - started,
                generate_seconds=generate_seconds,
                render_seconds=render_seconds,
            )

        for diagram_id in DIAGRAM_IDS:
            committed_d2 = d2_path(diagram_id, base)
            committed_svg = svg_path(diagram_id, base)
            if not committed_d2.is_file():
                stale.append(f"{diagram_id}.d2 (missing)")
                continue
            if not committed_svg.is_file():
                stale.append(f"{diagram_id}.svg (missing)")
                continue
            if committed_d2.read_text(encoding="utf-8") != built[diagram_id]:
                stale.append(f"{diagram_id}.d2")
            if committed_svg.read_bytes() != (tmp_svg / f"{diagram_id}.svg").read_bytes():
                stale.append(f"{diagram_id}.svg")

        try:
            assert_article_49a_d2_contract(built["article-49a-walkthrough"])
            assert_divergence_d2_truthfulness(built["divergence-workflow"], root=base)
            _assert_pipeline_contract(built["source-to-statement-pipeline"])
            _assert_provenance_contract(built["source-version-and-effects"])
        except AssertionError as exc:
            return DiagramCheckResult(
                ok=False,
                stale=tuple(stale),
                message=f"Explainability diagrams contract failed: {exc}",
                check_seconds=time.perf_counter() - started,
                generate_seconds=generate_seconds,
                render_seconds=render_seconds,
            )

    if not diagrams_index_path(base).is_file():
        stale.append("diagrams.md (missing)")

    check_seconds = time.perf_counter() - started
    if stale:
        joined = ", ".join(stale)
        return DiagramCheckResult(
            ok=False,
            stale=tuple(stale),
            message=(
                "Explainability diagrams are stale for: "
                f"{joined}. Run `just generate-explainability-diagrams` "
                "or `just generate-explainability-docs`."
            ),
            check_seconds=check_seconds,
            generate_seconds=generate_seconds,
            render_seconds=render_seconds,
        )
    return DiagramCheckResult(
        ok=True,
        stale=(),
        message=(
            "Explainability diagrams are up to date "
            f"(generate={generate_seconds:.2f}s render={render_seconds:.2f}s "
            f"total={check_seconds:.2f}s)."
        ),
        check_seconds=check_seconds,
        generate_seconds=generate_seconds,
        render_seconds=render_seconds,
    )


_PIPELINE_ORDER = (
    "SourceRecord",
    "SourceSnapshot",
    "SourceFragment",
    "Extraction selection",
    "Structural extraction frontier",
    "Model extraction proposal",
    "Deterministic validation",
    "Proposition",
    "Legal-effect classification",
    "LegalRuleGroup",
    "typed legal relationship",
    "EffectiveLawStatement",
    "required context",
    "Proposition Matcher candidate",
    "Workbench review",
)


def _assert_pipeline_contract(d2_text: str) -> None:
    positions = []
    for label in _PIPELINE_ORDER:
        idx = d2_text.find(label)
        if idx < 0:
            raise AssertionError(f"Pipeline diagram missing stage label {label!r}")
        positions.append(idx)
    if positions != sorted(positions):
        raise AssertionError("Pipeline diagram stage labels are out of order")
    for token in ("[CFG]", "[DET]", "[LLM]", "[HUM]"):
        if token not in d2_text:
            raise AssertionError(f"Pipeline diagram missing method marker {token}")
    if "CRITICAL BOUNDARY" not in d2_text:
        raise AssertionError("Pipeline diagram must highlight the model/deterministic boundary")


def _assert_provenance_contract(d2_text: str) -> None:
    required = (
        "retrieval timestamp ≠ legal as-of date",
        "revised manifestation ≠ Law Proposition Extractor independently applied every amendment",
        "source-effect annotation ≠ independently consumed affecting instrument",
        "consumed affecting instrument ≠ verified amendment application",
    )
    for phrase in required:
        if phrase not in d2_text:
            raise AssertionError(f"Provenance diagram missing boundary: {phrase}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m law_proposition_extractor_pipeline.explainability_docs.diagrams",
        description="Generate or check Law Proposition Extractor explainability D2/SVG diagrams (offline).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="Update D2 sources and SVG outputs in place.")
    sub.add_parser("check", help="Fail if committed diagrams are stale (no writes).")
    args = parser.parse_args(argv)

    if args.command == "generate":
        result = generate()
        root = repo_root()
        for path in (*result.written_d2, *result.written_svg):
            print(f"updated {path.relative_to(root)}")
        for path in (*result.unchanged_d2, *result.unchanged_svg):
            print(f"unchanged {path.relative_to(root)}")
        print(
            f"runtime generate={result.generate_seconds:.2f}s "
            f"render={result.render_seconds:.2f}s"
        )
        return 0

    if args.command == "check":
        result = check()
        print(result.message)
        return 0 if result.ok else 1

    parser.error(f"Unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
