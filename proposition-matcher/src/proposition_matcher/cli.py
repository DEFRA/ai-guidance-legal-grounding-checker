"""Proposition Matcher CLI — the Guidance Proposition Extractor -> Proposition Matcher matching stage.

Subcommands:
  proposition-matcher run                         group-rerank batch match
  proposition-matcher backfill-match-processing   historic match_processing reconstruction

Each subcommand has its own ``--help``.
"""

from __future__ import annotations

import sys

_USAGE = (
    "usage: proposition-matcher <command> ...\n"
    "commands:\n"
    "  run                          group-rerank Guidance Proposition Extractor guidance "
    "against Law Proposition Extractor law (batch)\n"
    "  backfill-match-processing    reconstruct match_processing on historic Matcher runs "
    "(fail-closed; see --help)\n"
    "  validate-run                 validate native match_processing on a Matcher run\n"
    "  reconcile-rerun              three-way reconciliation report for a Matcher rerun\n"
)


def main() -> None:
    if len(sys.argv) < 2:
        sys.stderr.write(_USAGE)
        raise SystemExit(2)

    cmd = sys.argv.pop(1)  # drop the subcommand so the target argparse sees the rest
    if cmd in ("-h", "--help"):
        sys.stdout.write(_USAGE)
        raise SystemExit(0)
    if cmd == "run":
        from proposition_matcher.pipeline.batch_match import main as run

        run()
        return
    if cmd == "backfill-match-processing":
        from proposition_matcher.pipeline.backfill_match_processing import main as backfill

        backfill()
        return
    if cmd == "validate-run":
        from proposition_matcher.pipeline.validate_native_run import main as validate_run

        validate_run()
        return
    if cmd == "reconcile-rerun":
        from proposition_matcher.pipeline.reconcile_matcher_rerun import main as reconcile

        reconcile()
        return
    sys.stderr.write(f"proposition-matcher: unknown command {cmd!r}\n{_USAGE}")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
