#!/usr/bin/env python3
"""Generate post context-closure impact report (Prompt 87-BR1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.export_context_closure_verification import derive_effective_law_for_export

JUDIT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = JUDIT_ROOT / "runs/slurry-gb-principal-5-current-export"
BEFORE_SNAPSHOT = EXPORT_DIR / ".derived-effective_law_statements.before-context-closure.json"
AFTER_EFFECTIVE = EXPORT_DIR / "effective_law_statements.json"
REPORT_PATH = JUDIT_ROOT / "docs/post-context-closure-impact-report.md"


def _ensure_before_snapshot() -> None:
    if BEFORE_SNAPSHOT.exists():
        return
    if not AFTER_EFFECTIVE.exists():
        raise FileNotFoundError(
            f"No before snapshot at {BEFORE_SNAPSHOT} and no {AFTER_EFFECTIVE}"
        )
    BEFORE_SNAPSHOT.write_text(AFTER_EFFECTIVE.read_text(encoding="utf-8"), encoding="utf-8")


def _refresh_after_effective_law() -> None:
    payload = derive_effective_law_for_export(EXPORT_DIR)
    AFTER_EFFECTIVE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    if not EXPORT_DIR.is_dir():
        raise FileNotFoundError(f"Export directory not found: {EXPORT_DIR}")

    _ensure_before_snapshot()
    _refresh_after_effective_law()

    env = {
        **dict(**__import__("os").environ),
        "CONTEXT_CLOSURE_IMPACT_EXPORT_DIR": str(EXPORT_DIR),
        "CONTEXT_CLOSURE_IMPACT_BEFORE_EFFECTIVE": str(BEFORE_SNAPSHOT),
        "CONTEXT_CLOSURE_IMPACT_AFTER_EFFECTIVE": str(AFTER_EFFECTIVE),
        "CONTEXT_CLOSURE_IMPACT_REPORT_PATH": str(REPORT_PATH),
    }
    subprocess.run(
        ["npm", "test", "--", "lib/compare-context-closure-impact.test.ts"],
        cwd=JUDIT_ROOT / "apps/web",
        env=env,
        check=True,
    )

    subsidiary = [
        "generate_export_context_closure_report.py",
        "generate_composition_trace_report.py",
        "generate_context_dependent_construction_report.py",
        "generate_reviewability_blockers_report.py",
    ]
    for script in subsidiary:
        subprocess.run(
            [sys.executable, str(JUDIT_ROOT / "scripts" / script)],
            cwd=JUDIT_ROOT,
            check=True,
        )

    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
