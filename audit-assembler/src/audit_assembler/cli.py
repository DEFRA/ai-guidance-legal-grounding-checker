"""Audit Assembler CLI — shape the upstream pipeline outputs into the content-audit
frontend's data files.

    audit-assembler build \
        --proposition-matcher-run   <proposition-matcher/runs/NAME> \
        --input-pair     <proposition-matcher/inputs/PAIR> \
        --relevance-filter-run      <guidance-relevance-filter/runs/NAME/output.json> \
        --seeds          <dir with the category + legislation seed files> \
        --dest           <ai-sdlc-content-audit/.../audit/data/data>

Reads Proposition Matcher's matched output (results.json, which carries the native guidance
ids), the input pair's ``law.json`` (Law Proposition Extractor law propositions), and Guidance Relevance Filter's run —
which supplies both the audited pages (content_id + page metadata + analytics)
and per-page relevance scores + corpus size. Reading age is recomputed per page
via the gov.uk content API (cached on disk). Writes the frontend data files in
pipeline-native shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from . import build as build_mod
from . import reading_age as ra
from .export_csv import (
    MissingSummariesError,
    default_pairs_csv_path,
    export_csv,
    try_write_pairs_csv,
)
from .law_candidates import load_candidates, merge_law_candidate_locators
from .validate_guidance_comparison import validate_assembled_dir

app = typer.Typer(add_completion=False, help=__doc__)


@app.callback()
def _main() -> None:
    """Audit Assembler — shape the audit for the content-audit frontend."""


def _load(path: Path):
    with path.open() as f:
        return json.load(f)


def _load_law_propositions(data) -> list[dict]:
    """Accept either a bare list or Law Proposition Extractor's ``{run_id, propositions:[…]}`` wrap."""
    if isinstance(data, dict) and "propositions" in data:
        return data["propositions"]
    return data


def _write(path: Path, data) -> None:
    with path.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _resolve_category(seeds_dir: Path, slug: str) -> dict:
    cats = _load(seeds_dir / "categories.json")
    seed = next((c for c in cats if c.get("id") == slug or c.get("name") == slug), None)
    if seed is None and len(cats) == 1:
        seed = cats[0]
    if seed is None:
        raise typer.BadParameter(
            f"no category matching {slug!r} in {seeds_dir / 'categories.json'}"
        )
    return {
        "id": slug,
        "title": seed.get("title") or seed.get("name"),
        "description": seed["description"],
    }


@app.command()
def build(
    proposition_matcher_run: Annotated[Path, typer.Option(help="Proposition Matcher run dir (results.json)")],
    input_pair: Annotated[Path, typer.Option(help="Proposition Matcher input pair dir (law.json)")],
    relevance_filter_run: Annotated[Path, typer.Option(help="Guidance Relevance Filter output.json (pages, relevance, corpus)")],
    seeds: Annotated[
        Path,
        typer.Option(help="Dir with categories/legislation/legislation-propositions seeds"),
    ],
    dest: Annotated[Path, typer.Option(help="Frontend data dir to write into")],
    category_slug: Annotated[str, typer.Option(help="Category slug (native id)")] = "slurry",
    reading_age_cache: Annotated[
        Path | None, typer.Option(help="Reading-age content-API cache dir (reused across runs)")
    ] = None,
    law_candidates: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Optional Law Proposition Extractor candidates export "
                "(beatrice_law_candidates.json / proposition_matcher_law_candidates.json) "
                "to join fragment_locator onto stripped Matcher law.json rows by id"
            )
        ),
    ] = None,
    dry_run: Annotated[bool, typer.Option(help="Compute and report, but write nothing")] = False,
) -> None:
    output_path = proposition_matcher_run / "results.json"
    for p in (output_path, input_pair / "law.json", relevance_filter_run):
        if not p.exists():
            raise typer.BadParameter(f"missing input: {p}")
    if law_candidates is not None and not law_candidates.exists():
        raise typer.BadParameter(f"missing input: {law_candidates}")
    if not dry_run and not dest.exists():
        raise typer.BadParameter(f"destination data dir not found: {dest}")

    cache_dir = reading_age_cache or (proposition_matcher_run.parent.parent.parent / "audit-assembler" / "cache")

    matcher_output = _load(output_path)
    law_input = _load_law_propositions(_load(input_pair / "law.json"))
    if not isinstance(law_input, list):
        raise typer.BadParameter(
            f"law.json must be a list or {{propositions: [...]}}; got {type(law_input).__name__}"
        )
    candidate_warnings: list[str] = []
    if law_candidates is not None:
        try:
            candidates = load_candidates(_load(law_candidates))
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        law_input = merge_law_candidate_locators(
            law_input, candidates, candidate_warnings
        )
    relevance_filter_output = _load(relevance_filter_run)
    legislation_seed = _load(seeds / "legislation.json")
    legacy_law_props = _load(seeds / "legislation-propositions.json")
    category = _resolve_category(seeds, category_slug)

    # Reading age is recomputed per audited page (cached on disk -> cheap re-runs).
    # Only the audited pages — those Proposition Matcher produced guidance for — are scored;
    # build() consumes reading age for exactly that set, so scoring the whole
    # Guidance Relevance Filter corpus would fetch thousands of pages whose scores are never read.
    audited_urls = {e["url"] for e in matcher_output if e.get("url")}
    page_urls = sorted(
        {p["url"] for p in relevance_filter_output if p.get("url") and p["url"] in audited_urls}
    )
    print(f"Scoring reading age for {len(page_urls)} pages (cache: {cache_dir})", file=sys.stderr)
    reading_age_by_url = ra.score_urls(page_urls, cache_dir, log=sys.stderr)

    files, warnings = build_mod.build(
        matcher_output=matcher_output,
        law_input=law_input,
        relevance_filter_output=relevance_filter_output,
        legislation_seed=legislation_seed,
        legacy_law_props=legacy_law_props,
        category=category,
        reading_age_by_url=reading_age_by_url,
    )
    warnings = candidate_warnings + warnings

    print("\nCounts:", file=sys.stderr)
    for name, data in files.items():
        n = len(data) if isinstance(data, list) else 1
        print(f"  {name:<32} {n}", file=sys.stderr)
    summary = files["subject-summary.json"][0]  # type: ignore[index]
    print(f"  status counts: {summary['proposition_status_counts']}", file=sys.stderr)

    if warnings:
        print(f"\n{len(warnings)} warning(s):", file=sys.stderr)
        for w in warnings:
            print(f"  WARN: {w}", file=sys.stderr)

    if dry_run:
        print("\nDry run — no files written.", file=sys.stderr)
        return

    for name, data in files.items():
        _write(dest / name, data)
    print(f"\nWrote {len(files)} files to {dest}", file=sys.stderr)

    csv_warnings: list[str] = []
    csv_rows = try_write_pairs_csv(dest, warnings=csv_warnings)
    if csv_rows is not None:
        print(f"Wrote {len(csv_rows)} rows to {dest / 'pairs.csv'}", file=sys.stderr)
    for warning in csv_warnings:
        print(f"  WARN: {warning}", file=sys.stderr)


@app.command("export-csv")
def export_csv_command(
    input_path: Annotated[
        Path,
        typer.Option(
            "--input",
            help="Envelope output.json or flat assembled presentation directory",
        ),
    ],
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="Destination CSV path (default: pairs.csv next to --input)",
        ),
    ] = None,
) -> None:
    """Export a denormalized guidance↔law pairs CSV from assembled presentation data.

    One row per reportable pair in guidance-proposition-law-comparisons.json,
    plus one stub row (law columns empty) per guidance proposition with zero
    reportable pairs. Requires non-empty match summaries.
    """
    if not input_path.exists():
        raise typer.BadParameter(f"input not found: {input_path}")

    if out is None:
        out = default_pairs_csv_path(input_path)

    warnings: list[str] = []
    try:
        rows = export_csv(input_path, out, warnings=warnings)
    except MissingSummariesError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if warnings:
        print(f"{len(warnings)} warning(s):", file=sys.stderr)
        for w in warnings:
            print(f"  WARN: {w}", file=sys.stderr)

    print(f"Wrote {len(rows)} rows to {out}", file=sys.stderr)


@app.command("validate-guidance-comparison-contract")
def validate_guidance_comparison_contract(
    dest: Annotated[
        Path,
        typer.Argument(help="Assembled Audit Assembler output directory"),
    ],
) -> None:
    """Validate guidance–law comparison invariants on assembled output.

    Checks summary completeness, reportable-pair counts, no-pair fallbacks,
    pair uniqueness, relationship filtering, entity joins, and legacy
    law-side GUIDANCE_MISSING separation.
    """
    if not dest.is_dir():
        raise typer.BadParameter(f"assembled dir not found: {dest}")

    errors = validate_assembled_dir(dest)
    if not errors:
        summaries = _load(dest / "guidance-proposition-match-summaries.json")
        comparisons = _load(dest / "guidance-proposition-law-comparisons.json")
        print(
            f"OK — {len(summaries)} summaries, {len(comparisons)} reportable pairs",
            file=sys.stderr,
        )
        return

    print(f"{len(errors)} guidance-comparison contract violation(s):", file=sys.stderr)
    for err in errors:
        print(f"  FAIL: {err}", file=sys.stderr)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
