#!/usr/bin/env python3
"""Evaluate a prompt-lab extraction run against fixture review targets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.extraction_prompt_eval import (
    evaluate_prompt_lab_extraction,
    write_prompt_eval_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score prompt-lab extraction output against expected propositions.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
        help="Prompt-lab fixture JSON (expected propositions and optional evaluation config).",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Workbench output directory (propositions.normalised.json, …).",
    )
    parser.add_argument(
        "--use-raw",
        action="store_true",
        help="Evaluate propositions.raw.json instead of normalised output.",
    )
    parser.add_argument(
        "--fail-on-fail",
        action="store_true",
        help="Exit with code 1 when evaluation does not pass.",
    )
    args = parser.parse_args(argv)

    result = evaluate_prompt_lab_extraction(
        fixture=args.fixture,
        run_dir=args.run_dir,
        prefer_normalised=not args.use_raw,
    )
    json_path, md_path = write_prompt_eval_outputs(result, args.run_dir)
    status = "PASS" if result.passed else "FAIL"
    print(f"{status}: {result.matched_expected_count}/{result.expected_count} expected matched")
    print(f"Wrote {json_path.resolve()} and {md_path.resolve()}")
    if args.fail_on_fail and not result.passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
