#!/usr/bin/env python3
"""Write SUSPICIOUS_PROPOSITION_REVIEW.md for a proposition export (deterministic)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import slurry_export_available
from law_proposition_extractor_pipeline.suspicious_proposition_review import (
    REVIEW_JSON_FILENAME,
    REVIEW_MD_FILENAME,
    build_review_from_export_dir,
    write_suspicious_proposition_review,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic suspicious proposition review for an export.",
    )
    parser.add_argument(
        "export_dir",
        nargs="?",
        type=Path,
        default=None,
        help="Export directory (default: runs/slurry-gb-principal-5-current-export)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline export for delta (default: slurry-gb-principal-5-frontier-export if present)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    export_dir = args.export_dir if args.export_dir is not None else (
        repo / "runs" / "slurry-gb-principal-5-current-export"
    )
    export_dir = export_dir.resolve()

    if not slurry_export_available(export_dir):
        print(f"error: {export_dir / 'propositions.json'} not found", file=sys.stderr)
        return 1

    review = build_review_from_export_dir(
        export_dir,
        baseline_export_dir=args.baseline,
    )
    md_path, json_path = write_suspicious_proposition_review(export_dir, review)
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    s = review.summary
    print(
        f"Summary: dup_id_groups={s.get('duplicate_proposition_id_groups')} "
        f"exact_text_groups={s.get('exact_text_duplicate_groups')} "
        f"unknown={s.get('unknown_classifications')} "
        f"val_warn={s.get('validation_warning_propositions')} "
        f"blocker={s.get('duplicates_are_blocker')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
