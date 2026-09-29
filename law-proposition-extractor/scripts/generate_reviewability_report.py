#!/usr/bin/env python3
"""Generate effective-law artefacts for the stale export and write the reviewability report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.effective_law import attach_effective_law_artifacts
from law_proposition_extractor_pipeline.linting import load_exported_bundle

JUDIT_ROOT = Path(__file__).resolve().parents[1]
BEFORE_DIR = JUDIT_ROOT / "runs/slurry-gb-principal-5-current-export-json-repaired"
AFTER_DIR = JUDIT_ROOT / "runs/slurry-gb-principal-5-current-export"
REPORT_PATH = JUDIT_ROOT / "docs/reviewability-improvement-report.md"
BEFORE_EFFECTIVE_PATH = BEFORE_DIR / ".derived-effective_law_statements.json"


def _ensure_before_effective_law() -> Path:
    if (BEFORE_DIR / "effective_law_statements.json").exists():
        return BEFORE_DIR / "effective_law_statements.json"

    bundle = load_exported_bundle(BEFORE_DIR)
    attach_effective_law_artifacts(bundle)
    payload = bundle.get("effective_law_statements")
    if not isinstance(payload, dict):
        raise RuntimeError("Failed to derive effective_law_statements for before export")
    BEFORE_EFFECTIVE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return BEFORE_EFFECTIVE_PATH


def main() -> int:
    before_effective = _ensure_before_effective_law()
    ts_runner = JUDIT_ROOT / "apps/web/lib/compare-reviewability-exports.test.ts"
    if not ts_runner.exists():
        raise FileNotFoundError(ts_runner)

    env = {
        **dict(**__import__("os").environ),
        "REVIEWABILITY_BEFORE_DIR": str(BEFORE_DIR),
        "REVIEWABILITY_AFTER_DIR": str(AFTER_DIR),
        "REVIEWABILITY_BEFORE_EFFECTIVE": str(before_effective),
        "REVIEWABILITY_REPORT_PATH": str(REPORT_PATH),
    }
    subprocess.run(
        ["npm", "test", "--", "lib/compare-reviewability-exports.test.ts"],
        cwd=JUDIT_ROOT / "apps/web",
        env=env,
        check=True,
    )
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
