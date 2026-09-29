#!/usr/bin/env python3
"""Verify regulation paragraph structural fragmentation without LLM extraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.regulation_paragraph_fragmentation_verification import (
    DEFAULT_REGULATION_LOCATOR_PREFIX,
    EXPECTED_REGULATION_36_LOCATORS,
    WSI_2021_77_AUTHORITY_SOURCE_ID,
    WSI_2021_77_SOURCE_RECORD_ID,
    build_report_from_case,
    build_report_from_export,
    build_report_from_fixture_xml,
    print_verification_console_summary,
    verification_exit_code,
    write_verification_outputs,
)

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "regulation_paragraph_fragmentation"
    / "wsi_2021_77_regulation_36.xml"
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify regulation paragraph structural fragments (no LLM, no proposition extraction). "
            "Default mode uses the offline WSI 2021/77 regulation 36 fixture."
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--fixture",
        type=Path,
        nargs="?",
        const=DEFAULT_FIXTURE,
        help=f"Offline CLML XML fixture (default: {DEFAULT_FIXTURE.name}).",
    )
    source.add_argument(
        "--case",
        type=Path,
        help="Case JSON path — ingest the WSI 2021/77 source via legislation.gov.uk (network).",
    )
    source.add_argument(
        "--export-dir",
        type=Path,
        help="Existing export directory — read source_fragments.json only.",
    )
    parser.add_argument(
        "--authority-source-id",
        default=WSI_2021_77_AUTHORITY_SOURCE_ID,
        help="Legislation.gov.uk authority source id (default: wsi/2021/77).",
    )
    parser.add_argument(
        "--source-record-id",
        default=WSI_2021_77_SOURCE_RECORD_ID,
        help="Source record id filter (default: lex-805b03f284dcf364).",
    )
    parser.add_argument(
        "--locator-prefix",
        default=DEFAULT_REGULATION_LOCATOR_PREFIX,
        help="Locator prefix to list and verify (default: regulation:36).",
    )
    parser.add_argument(
        "--source-cache-dir",
        type=Path,
        help="Optional source snapshot cache directory for --case mode.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write REGULATION_PARAGRAPH_FRAGMENTATION_VERIFICATION.md/json here.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the verification JSON report to stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    common = {
        "authority_source_id": args.authority_source_id,
        "source_record_id": args.source_record_id,
        "locator_prefix": args.locator_prefix,
        "expected_locators": EXPECTED_REGULATION_36_LOCATORS,
    }

    if args.export_dir is not None:
        report = build_report_from_export(args.export_dir.resolve(), **common)
    elif args.case is not None:
        report = build_report_from_case(
            args.case.resolve(),
            cache_dir=args.source_cache_dir.resolve() if args.source_cache_dir else None,
            **common,
        )
    else:
        fixture_path = (args.fixture if args.fixture is not None else DEFAULT_FIXTURE).resolve()
        report = build_report_from_fixture_xml(fixture_path, **common)

    print_verification_console_summary(report)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    if args.output_dir is not None:
        md_path, json_path = write_verification_outputs(args.output_dir.resolve(), report)
        print(f"Wrote {md_path}")
        print(f"Wrote {json_path}")
    return verification_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
