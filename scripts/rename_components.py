#!/usr/bin/env python3
"""Mechanical directory/package rename helper for the descriptive-name migration.

Safe to re-run only on a tree that still uses legacy top-level dirs.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DIR_MOVES = [
    ("mary", "guidance-discovery"),
    ("radia", "guidance-relevance-filter"),
    ("susan", "guidance-proposition-extractor"),
    ("ada", "law-discovery"),
    ("beatrice", "proposition-matcher"),
    ("anna", "match-adjudicator"),
    ("esther", "audit-assembler"),
    ("judit", "law-proposition-extractor"),
]

PKG_MOVES = [
    ("guidance-relevance-filter/src/radia", "guidance-relevance-filter/src/guidance_relevance_filter"),
    ("guidance-proposition-extractor/src/susan", "guidance-proposition-extractor/src/guidance_proposition_extractor"),
    ("law-discovery/src/ada", "law-discovery/src/law_discovery"),
    ("proposition-matcher/src/beatrice", "proposition-matcher/src/proposition_matcher"),
    ("match-adjudicator/src/anna", "match-adjudicator/src/match_adjudicator"),
    ("audit-assembler/src/esther", "audit-assembler/src/audit_assembler"),
    (
        "law-proposition-extractor/packages/domain/src/judit_domain",
        "law-proposition-extractor/packages/domain/src/law_proposition_extractor_domain",
    ),
    (
        "law-proposition-extractor/packages/pipeline/src/judit_pipeline",
        "law-proposition-extractor/packages/pipeline/src/law_proposition_extractor_pipeline",
    ),
    (
        "law-proposition-extractor/packages/llm/src/judit_llm",
        "law-proposition-extractor/packages/llm/src/law_proposition_extractor_llm",
    ),
    (
        "law-proposition-extractor/packages/storage/src/judit_storage",
        "law-proposition-extractor/packages/storage/src/law_proposition_extractor_storage",
    ),
    (
        "law-proposition-extractor/packages/exporters/src/judit_exporters",
        "law-proposition-extractor/packages/exporters/src/law_proposition_extractor_exporters",
    ),
    (
        "law-proposition-extractor/apps/api/src/judit_api",
        "law-proposition-extractor/apps/api/src/law_proposition_extractor_api",
    ),
]


def _git_mv(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        print(f"skip missing {src}")
        return
    if dest.exists():
        print(f"skip exists {dest}")
        return
    try:
        subprocess.run(["git", "mv", str(src), str(dest)], check=True, cwd=ROOT)
    except subprocess.CalledProcessError:
        shutil.move(str(src), str(dest))
        print(f"filesystem move {src} -> {dest}")


def main() -> int:
    for src, dest in DIR_MOVES:
        _git_mv(ROOT / src, ROOT / dest)
    for src, dest in PKG_MOVES:
        _git_mv(ROOT / src, ROOT / dest)
    print("directory/package moves done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
