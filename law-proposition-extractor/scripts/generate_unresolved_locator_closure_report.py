#!/usr/bin/env python3
"""Generate the unresolved locator closure report for the regenerated slurry export."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

JUDIT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = JUDIT_ROOT / "runs/slurry-gb-principal-5-current-export"
REPORT_PATH = JUDIT_ROOT / "docs/unresolved-locator-closure-report.md"


def main() -> int:
    if not EXPORT_DIR.is_dir():
        raise FileNotFoundError(f"Export directory not found: {EXPORT_DIR}")

    env = {
        **dict(**__import__("os").environ),
        "UNRESOLVED_LOCATOR_EXPORT_DIR": str(EXPORT_DIR),
        "UNRESOLVED_LOCATOR_REPORT_PATH": str(REPORT_PATH),
    }
    subprocess.run(
        ["npm", "test", "--", "lib/analyze-unresolved-locator-closure.test.ts"],
        cwd=JUDIT_ROOT / "apps/web",
        env=env,
        check=True,
    )
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
