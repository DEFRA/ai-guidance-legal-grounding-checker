"""CLI: reconstruct ``match_processing`` on historic Matcher runs (fail-closed).

```bash
uv run proposition-matcher backfill-match-processing --run <historic> --check
uv run proposition-matcher backfill-match-processing --run <historic> --dest <derived>
```
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from proposition_matcher.matching.historic_match_processing import (
    POLICY_VERSION,
    analyse_run,
    format_analysis_text,
    report_to_dict,
    write_backfill,
)


def _tool_version() -> str:
    try:
        return version("proposition-matcher")
    except PackageNotFoundError:
        return "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="proposition-matcher backfill-match-processing",
        description=(
            f"Analyse or write a derived Matcher run with reconstructed "
            f"match_processing under {POLICY_VERSION}. Fail-closed: refuses "
            f"production write when any proposition is ambiguous."
        ),
    )
    p.add_argument(
        "--run",
        type=Path,
        required=True,
        help="Historic Matcher run directory (results.json or output.json)",
    )
    p.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Destination directory for the derived run (required unless --check)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Analysis only — print eligibility report, write nothing",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing destination directory",
    )
    p.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Optional path to write the machine-readable analysis report",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    run_dir = args.run.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"run directory not found: {run_dir}")

    tool_version = _tool_version()

    if args.check or args.dest is None:
        if not args.check and args.dest is None:
            raise SystemExit("provide --dest for write mode, or pass --check for analysis only")
        report, _, _ = analyse_run(run_dir, tool_version=tool_version)
        sys.stdout.write(format_analysis_text(report))
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps(report_to_dict(report), indent=2) + "\n")
        raise SystemExit(0 if report.production_backfill_eligible else 2)

    try:
        report = write_backfill(
            run_dir,
            args.dest.resolve(),
            overwrite=args.overwrite,
            tool_version=tool_version,
        )
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from exc
    except RuntimeError as exc:
        # Still emit analysis for operators.
        report, _, _ = analyse_run(
            run_dir, tool_version=tool_version, destination_run=args.dest.resolve()
        )
        sys.stderr.write(format_analysis_text(report))
        raise SystemExit(f"error: {exc}") from exc

    sys.stdout.write(format_analysis_text(report))
    sys.stdout.write(f"wrote derived run → {args.dest.resolve()}\n")
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report_to_dict(report), indent=2) + "\n")


if __name__ == "__main__":
    main()
