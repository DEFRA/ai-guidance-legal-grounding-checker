#!/usr/bin/env python3
"""Re-apply opaque proposition ids on an export bundle without LLM re-extraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.proposition_export_uniqueness import find_duplicate_proposition_ids
from law_proposition_extractor_pipeline.proposition_identity_reexport import reidentity_export_bundle
from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import slurry_export_available


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reidentity proposition ids in a static export (no LLM).",
    )
    parser.add_argument(
        "export_dir",
        type=Path,
        help="Source export directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output export directory (default: <export_dir>-fixed)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    export_dir = args.export_dir.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else export_dir.parent / f"{export_dir.name}-fixed"
    )

    if not slurry_export_available(export_dir):
        print(f"error: {export_dir / 'propositions.json'} not found", file=sys.stderr)
        return 1

    before = find_duplicate_proposition_ids(
        json.loads((export_dir / "propositions.json").read_text(encoding="utf-8"))
    )
    bundle = reidentity_export_bundle(export_dir, output_dir)
    meta = bundle.get("proposition_identity_reexport") or {}
    after = meta.get("duplicate_ids_after") or []

    print(f"Wrote {output_dir}")
    print(f"duplicate_id_groups before: {len(before)}")
    print(f"duplicate_id_groups after: {len(after)}")
    if before:
        for dup in before:
            print(f"  before: {dup['id']} x{dup['count']}")
    if after:
        for dup in after:
            print(f"  after: {dup['id']} x{dup['count']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
