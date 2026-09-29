#!/usr/bin/env python3
"""Batch-run extraction prompt-lab fixtures and write aggregate summary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.extraction_prompt_lab_batch import run_prompt_lab_batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run extract-fragment across prompt-lab fixtures with aggregate summary.",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        help="Directory containing prompt-lab fixture JSON files.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        action="append",
        default=[],
        help="Repeatable fixture JSON path.",
    )
    parser.add_argument(
        "--mode",
        choices=("local", "frontier", "dry"),
        default="local",
        help="Extraction mode (dry = parse fixture model output, no LLM).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Root directory for per-fixture runs and batch summary.",
    )
    parser.add_argument("--fixture-glob", default=None, help="Glob for fixture filenames.")
    parser.add_argument("--limit", type=int, default=None, metavar="N")
    parser.add_argument("--max-propositions", type=int, default=8, metavar="N")
    parser.add_argument(
        "--no-retry-empty-extraction",
        action="store_true",
        help="Disable one-shot retry on empty JSON extraction.",
    )
    parser.add_argument(
        "--extraction-output-mode",
        choices=("json_object", "json_schema", "text_then_parse"),
        default=None,
    )
    parser.add_argument(
        "--allow-output-mode-fallback",
        action="store_true",
        help="Fall back to json_object when json_schema is rejected.",
    )
    parser.add_argument(
        "--eval",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Score each run against fixture expected propositions (default: on).",
    )
    parser.add_argument(
        "--overwrite",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Overwrite existing per-fixture run directories (default: on).",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop batch on first fixture failure.",
    )
    args = parser.parse_args(argv)

    if args.fixture_dir is None and not args.fixture:
        parser.error("Provide --fixture-dir and/or one or more --fixture paths")

    try:
        result = run_prompt_lab_batch(
            output_root=args.output_root,
            extraction_mode=args.mode,
            fixture_dir=args.fixture_dir,
            fixture_paths=args.fixture or None,
            fixture_glob=args.fixture_glob,
            limit=args.limit,
            run_eval=args.eval,
            overwrite=args.overwrite,
            fail_fast=args.fail_fast,
            max_propositions=args.max_propositions,
            retry_empty_extraction=not args.no_retry_empty_extraction,
            extraction_output_mode=args.extraction_output_mode,
            allow_output_mode_fallback=args.allow_output_mode_fallback,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    passed = sum(1 for row in result.rows if row.status == "pass")
    warned = sum(1 for row in result.rows if row.status == "warn")
    failed = sum(1 for row in result.rows if row.status == "fail")
    errored = sum(1 for row in result.rows if row.status == "error")
    skipped = sum(1 for row in result.rows if row.status == "skipped")
    print(
        f"Batch complete: {passed} pass, {warned} warn, {failed} fail, "
        f"{errored} error, {skipped} skipped"
    )
    print(f"Verdict: {result.verdict} — {result.verdict_detail}")
    print(f"Wrote {args.output_root.resolve() / 'prompt_lab_summary.json'}")
    return 1 if failed or errored else 0


if __name__ == "__main__":
    sys.exit(main())
