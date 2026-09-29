#!/usr/bin/env python3
"""Write NORMALISED_PROPOSITION_REVIEW.md for human inspection of normalised exports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.normalised_proposition_review import (
    build_review_from_export_dir,
    default_review_export_path,
    write_normalised_proposition_review,
)
from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import slurry_export_available


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic review report for normalised proposition exports.",
    )
    parser.add_argument(
        "export_dir",
        nargs="?",
        type=Path,
        default=None,
        help="Export directory containing propositions.json (default: slurry frontier export)",
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="Skip writing normalised_proposition_review.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    export_dir = args.export_dir if args.export_dir is not None else default_review_export_path(repo)
    export_dir = export_dir.resolve()

    if not slurry_export_available(export_dir):
        print(
            f"error: {export_dir / 'propositions.json'} not found",
            file=sys.stderr,
        )
        return 1

    review = build_review_from_export_dir(export_dir)
    md_path, json_path = write_normalised_proposition_review(
        export_dir,
        review,
        write_json=not args.no_json,
    )
    print(f"Wrote {md_path}")
    if json_path is not None:
        print(f"Wrote {json_path}")
    counts = review.to_dict()["counts"]
    print(
        "Sections: "
        + ", ".join(f"{key}={counts[key]}" for key in sorted(counts)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
