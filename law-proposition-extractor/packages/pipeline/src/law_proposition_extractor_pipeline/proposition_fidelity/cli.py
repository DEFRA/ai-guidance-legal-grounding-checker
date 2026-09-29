"""CLI for the offline proposition-fidelity benchmark."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .fixtures import REPORT_RELATIVE
from .report import (
    check_against_baseline,
    check_benchmark_report,
    write_baseline,
    write_benchmark_report,
)
from .runner import run_proposition_fidelity_benchmark


def _print_summary(result) -> None:
    t = result.totals
    print(
        f"proposition-fidelity: cases={t['cases']} "
        f"expected={t['expected_propositions']} produced={t['produced_propositions']} "
        f"pass_roles={t['fully_passing_roles']} warn_roles={t['warning_roles']} "
        f"fail_roles={t['failed_roles']} unexpected={t['unexpected_propositions']} "
        f"runtime_s={result.runtime_seconds}"
    )
    for case in result.cases:
        print(
            f"  - {case.case_id}: {case.case_status} "
            f"(expected={len(case.expected_roles)} produced={case.produced_count} "
            f"missing={len(case.missing_roles)} unexpected={len(case.unexpected_propositions)})"
        )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Law Proposition Extractor offline proposition-fidelity benchmark (no network/LLM)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Execute benchmark, write JSON + Markdown report.")
    run_p.add_argument(
        "--output",
        help="Optional JSON output path (default: temp file).",
    )
    run_p.add_argument(
        "--write-baseline",
        action="store_true",
        help="Also write tests/fixtures/proposition_fidelity/baseline.json.",
    )
    run_p.add_argument(
        "--no-report",
        action="store_true",
        help="Skip writing the Markdown report.",
    )

    sub.add_parser(
        "check",
        help="Run offline; compare committed report; fail on regression; no writes.",
    )
    sub.add_parser("generate-report", help="Write proposition-fidelity-benchmark.md.")
    sub.add_parser("check-report", help="Check committed report is current.")

    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_proposition_fidelity_benchmark()
        out = Path(args.output) if args.output else Path(
            tempfile.mkstemp(prefix="pf-bench-", suffix=".json")[1]
        )
        out.write_text(
            json.dumps(result.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if not args.no_report:
            write_benchmark_report(result)
            print(str(REPORT_RELATIVE))
        if args.write_baseline:
            path = write_baseline(result)
            # relative only
            print("tests/fixtures/proposition_fidelity/baseline.json")
            _ = path
        print(f"json={out.name}")
        _print_summary(result)
        regressions = check_against_baseline(result)
        if regressions:
            print("baseline regressions:", file=sys.stderr)
            for row in regressions:
                print(f"  - {row}", file=sys.stderr)
            return 1
        # Article 49a hard requirement
        a49 = next((c for c in result.cases if c.case_id == "article_49a"), None)
        if a49 is None or a49.case_status == "fail":
            # allow warning; hard fail only if article_49a truly failed without baseline blessing
            hard = [
                f
                for f in result.failures
                if f.startswith("article_49a/")
                and any(
                    x in f
                    for x in (
                        "coverage",
                        "evidence_fidelity",
                        "structural_context_boundary",
                        "actor_fidelity",
                        "legal_effect_fidelity",
                    )
                )
            ]
            if hard:
                return 1
        return 0

    if args.command == "check":
        # Must not modify the working tree.
        result = run_proposition_fidelity_benchmark()
        check_benchmark_report()
        regressions = check_against_baseline(result)
        _print_summary(result)
        if regressions:
            print("baseline regressions:", file=sys.stderr)
            for row in regressions:
                print(f"  - {row}", file=sys.stderr)
            return 1
        a49 = next((c for c in result.cases if c.case_id == "article_49a"), None)
        if a49 is None:
            print("article_49a case missing", file=sys.stderr)
            return 1
        if a49.missing_roles or a49.unexpected_propositions:
            print(
                f"article_49a not green: missing={a49.missing_roles} "
                f"unexpected={len(a49.unexpected_propositions)}",
                file=sys.stderr,
            )
            return 1
        print("proposition-fidelity benchmark check passed")
        return 0

    if args.command == "generate-report":
        path = write_benchmark_report()
        print(str(REPORT_RELATIVE))
        return 0 if path.is_file() else 1

    if args.command == "check-report":
        check_benchmark_report()
        print("proposition-fidelity report is current")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
