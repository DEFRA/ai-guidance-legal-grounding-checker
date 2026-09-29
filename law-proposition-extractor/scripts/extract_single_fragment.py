#!/usr/bin/env python3
"""Run single-fragment extraction for prompt refinement (writes prompt-lab artifacts)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.extraction_prompt_eval import evaluate_and_write_prompt_lab_run
from law_proposition_extractor_pipeline.extraction_workbench import (
    load_prompt_lab_fixture,
    run_extract_fragment_workbench,
    write_extract_fragment_workbench_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract propositions from one legal fragment and write prompt-lab outputs.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        help="Fixture JSON with topic/cluster/source (and optional dry.raw_model_output).",
    )
    parser.add_argument(
        "--case-or-run-dir",
        type=Path,
        help="case.json, run directory, or exported bundle.",
    )
    parser.add_argument("--source-id", help="Source record id (with --case-or-run-dir).")
    parser.add_argument(
        "--locator",
        help="Fragment locator, e.g. regulation:1 (with --case-or-run-dir).",
    )
    parser.add_argument(
        "--mode",
        choices=("local", "frontier", "dry"),
        default="local",
        help="Extraction mode (dry = parse fixture model output, no LLM).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory (fragment.txt, prompt.txt, review.md, …).",
    )
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
        default=False,
        help="After extraction, write prompt_eval.json and PROMPT_EVAL.md (requires --fixture).",
    )
    parser.add_argument(
        "--fail-on-eval",
        action="store_true",
        help="With --eval, exit 1 when evaluation does not pass.",
    )
    args = parser.parse_args(argv)

    if args.fixture is None and args.case_or_run_dir is None:
        parser.error("Provide --fixture or --case-or-run-dir")
    if args.fixture is not None and args.case_or_run_dir is not None:
        parser.error("Use either --fixture or --case-or-run-dir, not both")
    if args.case_or_run_dir is not None and (not args.source_id or not args.locator):
        parser.error("--source-id and --locator are required with --case-or-run-dir")

    result = run_extract_fragment_workbench(
        fixture_path=args.fixture,
        case_or_run_dir=args.case_or_run_dir,
        source_id=args.source_id,
        locator=args.locator,
        extraction_mode=args.mode,
        max_propositions=args.max_propositions,
        retry_empty_extraction=not args.no_retry_empty_extraction,
        extraction_output_mode=args.extraction_output_mode,
        allow_output_mode_fallback=args.allow_output_mode_fallback,
    )
    out = write_extract_fragment_workbench_outputs(result, args.output_dir)
    print(f"Wrote prompt-lab artifacts to {out.resolve()}")

    if args.eval:
        if args.fixture is None:
            parser.error("--eval requires --fixture (prompt-lab schema)")
        load_prompt_lab_fixture(args.fixture)
        eval_result, json_path, md_path = evaluate_and_write_prompt_lab_run(
            fixture=args.fixture,
            run_dir=out,
        )
        status = "PASS" if eval_result.passed else "FAIL"
        print(
            f"Eval {status}: {eval_result.matched_expected_count}/"
            f"{eval_result.expected_count} expected matched"
        )
        print(f"Wrote {json_path.resolve()} and {md_path.resolve()}")
        if args.fail_on_eval and not eval_result.passed:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
