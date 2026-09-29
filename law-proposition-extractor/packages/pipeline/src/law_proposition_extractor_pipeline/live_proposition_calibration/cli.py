"""CLI for live proposition calibration (evaluation-only)."""

from __future__ import annotations

import sys

from .paths import CALIBRATION_CASES, REPETITIONS, calibration_root
from .runner import check_calibration_run, inspect_calibration_run, run_live_proposition_calibration


def _print_summary(result) -> None:
    t = result.totals
    print(
        f"live-proposition-calibration: run={result.calibration_run_id} "
        f"cases={t.get('cases')} reps={t.get('case_repetitions')} "
        f"provider_calls={result.provider_call_count} retries={result.provider_retry_count} "
        f"critical_failures={t.get('critical_gate_failures')} "
        f"runtime_s={result.runtime_seconds}"
    )
    for case in result.cases:
        print(
            f"  - {case.case_id}: stability={case.stability} "
            f"fidelity={case.case_fidelity_gate} repeatability={case.repeatability_gate} "
            f"success={case.successful_repetitions}/3"
        )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Law Proposition Extractor live proposition calibration (frontier model + prompt v3). "
            "Requires network/credentials for `run`."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Execute live calibration (9 case-repetitions).")
    run_p.add_argument("--run-id", help="Optional calibration_run_id (default: timestamp).")
    run_p.add_argument(
        "--no-docs",
        action="store_true",
        help="Do not write docs/explainability/live-proposition-calibration.md.",
    )

    inspect_p = sub.add_parser(
        "inspect", help="Offline: print report for an existing calibration run."
    )
    inspect_p.add_argument("run_id")

    check_p = sub.add_parser(
        "check", help="Offline: validate saved calibration artifacts."
    )
    check_p.add_argument("run_id")
    check_p.add_argument(
        "--require-green",
        action="store_true",
        help="Also fail if critical_failures is non-empty.",
    )

    replay_p = sub.add_parser(
        "replay-article-49a",
        help=(
            "Offline: replay saved Article 49a live responses through the "
            "corrected deterministic pipeline (no model calls)."
        ),
    )
    replay_p.add_argument("run_id")
    replay_p.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write post_fix_replay.json (still prints summary).",
    )

    replay_uk_p = sub.add_parser(
        "replay-uk-regulation-12",
        help=(
            "Offline: replay saved UK regulation 12 live responses through "
            "dependent-qualification suppression (no model calls)."
        ),
    )
    replay_uk_p.add_argument("run_id")
    replay_uk_p.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write uk_regulation_12_post_fix_replay.json.",
    )

    recheck_p = sub.add_parser(
        "recheck",
        help=(
            "Offline: complete current-code recheck of all saved live-calibration "
            "responses (no model/network calls). Writes current_code_recheck.*."
        ),
    )
    recheck_p.add_argument("run_id")
    recheck_p.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write current_code_recheck.json / .md.",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        print(
            "Starting live calibration: "
            f"cases={list(CALIBRATION_CASES)} repetitions={list(REPETITIONS)}",
            flush=True,
        )
        result = run_live_proposition_calibration(
            calibration_run_id=args.run_id,
            write_docs=not args.no_docs,
        )
        out = calibration_root() / result.calibration_run_id
        print(f"artifacts={out.as_posix()}")
        _print_summary(result)
        if result.critical_failures:
            print("critical failures:", file=sys.stderr)
            for row in result.critical_failures:
                print(f"  - {row}", file=sys.stderr)
            return 1
        return 0

    if args.command == "inspect":
        text = inspect_calibration_run(args.run_id)
        print(text)
        return 0

    if args.command == "check":
        errors = check_calibration_run(args.run_id)
        if errors:
            print("calibration artifact check failed:", file=sys.stderr)
            for row in errors:
                print(f"  - {row}", file=sys.stderr)
            return 1
        if args.require_green:
            from .artifacts import load_calibration_result

            result = load_calibration_result(args.run_id)
            fails = result.get("critical_failures") or []
            if fails:
                print("calibration not green:", file=sys.stderr)
                for row in fails:
                    print(f"  - {row}", file=sys.stderr)
                return 1
        print(f"live proposition calibration check passed: {args.run_id}")
        return 0

    if args.command == "replay-article-49a":
        from .replay_article_49a import (
            assert_article_49a_post_fix_replay,
            replay_article_49a_calibration_run,
        )

        payload = replay_article_49a_calibration_run(
            args.run_id,
            write_result=not args.no_write,
        )
        print(
            f"post-fix Article 49a replay: run={args.run_id} "
            f"model_calls={payload.get('model_calls_made')} "
            f"historical_modified={payload.get('historical_artifacts_modified')}"
        )
        for row in payload.get("repetitions") or []:
            orig = row.get("original_live_calibration") or {}
            replay = row.get("post_fix_replay") or {}
            print(
                f"  rep {row.get('repetition')}: "
                f"original triggered_by={orig.get('triggered_by_count')} → "
                f"replay triggered_by={replay.get('triggered_by_count')} "
                f"triggers={len(replay.get('p3_trigger_condition_proposition_ids') or [])}"
            )
        try:
            assert_article_49a_post_fix_replay(payload)
        except AssertionError as exc:
            print(f"replay assertion failed: {exc}", file=sys.stderr)
            return 1
        if payload.get("written_to"):
            print(f"wrote={payload['written_to']}")
        return 0

    if args.command == "replay-uk-regulation-12":
        from .replay_uk_regulation_12 import (
            assert_uk_regulation_12_post_fix_replay,
            replay_uk_regulation_12_calibration_run,
        )

        payload = replay_uk_regulation_12_calibration_run(
            args.run_id,
            write_result=not args.no_write,
        )
        print(
            f"post-fix UK regulation 12 replay: run={args.run_id} "
            f"model_calls={payload.get('model_calls_made')} "
            f"historical_modified={payload.get('historical_artifacts_modified')}"
        )
        for row in payload.get("repetitions") or []:
            orig = row.get("original_live_calibration") or {}
            replay = row.get("post_fix_replay") or {}
            print(
                f"  rep {row.get('repetition')}: "
                f"original props={orig.get('proposition_count')} → "
                f"replay props={replay.get('proposition_count')} "
                f"measurement_preserved={replay.get('measurement_basis_preserved')}"
            )
        try:
            assert_uk_regulation_12_post_fix_replay(payload)
        except AssertionError as exc:
            print(f"replay assertion failed: {exc}", file=sys.stderr)
            return 1
        if payload.get("written_to"):
            print(f"wrote={payload['written_to']}")
        return 0

    if args.command == "recheck":
        from .current_code_recheck import (
            assert_current_code_recheck,
            recheck_live_proposition_calibration,
        )

        payload = recheck_live_proposition_calibration(
            args.run_id,
            write_result=not args.no_write,
        )
        totals = payload.get("totals") or {}
        print(
            f"current-code recheck: run={args.run_id} "
            f"cases={totals.get('cases')} reps={totals.get('case_repetitions')} "
            f"model_calls={payload.get('model_calls_made')} "
            f"historical_modified={payload.get('historical_artifacts_modified')} "
            f"remaining_warn={totals.get('remaining_warnings')} "
            f"remaining_fail={totals.get('remaining_failures')}"
        )
        for case in payload.get("cases") or []:
            for row in case.get("repetitions") or []:
                ev = row.get("evaluation") or {}
                print(
                    f"  {case.get('case_id')} rep {row.get('repetition')}: "
                    f"status={ev.get('case_status')} "
                    f"props={ev.get('produced_count')} "
                    f"matched={ev.get('matched_role_count')} "
                    f"unexpected={ev.get('unexpected_count')}"
                )
        try:
            assert_current_code_recheck(payload)
        except AssertionError as exc:
            print(f"recheck assertion failed: {exc}", file=sys.stderr)
            return 1
        written = payload.get("written_to") or {}
        if written:
            print(f"wrote_json={written.get('json')}")
            print(f"wrote_md={written.get('markdown')}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
