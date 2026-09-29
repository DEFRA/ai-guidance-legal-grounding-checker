#!/usr/bin/env python3
"""Verify a fresh one-source Law Proposition Extractor extraction export (deterministic, no LLM)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.fresh_extraction_verification import (
    build_fresh_extraction_verification,
    print_verification_console_summary,
    verification_exit_code,
    write_fresh_extraction_verification,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a fresh Law Proposition Extractor extraction export directory.",
    )
    parser.add_argument(
        "export_dir",
        type=Path,
        help="Export directory containing propositions.json",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures (exit 1)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    export_dir = args.export_dir.resolve()
    report = build_fresh_extraction_verification(export_dir)
    md_path, json_path = write_fresh_extraction_verification(export_dir, report)
    print_verification_console_summary(report)
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    return verification_exit_code(report, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
