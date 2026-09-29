#!/usr/bin/env python3
"""Generate before/after export context closure report for the slurry export."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from law_proposition_extractor_pipeline.export_context_closure_verification import (
    analyze_export_context_closure,
    build_export_context_closure_report,
    derive_effective_law_for_export,
)

JUDIT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = JUDIT_ROOT / "runs/slurry-gb-principal-5-current-export"
BEFORE_SNAPSHOT = EXPORT_DIR / ".derived-effective_law_statements.before-context-closure.json"
REPORT_PATH = JUDIT_ROOT / "docs/export-context-closure-report.md"


def main() -> int:
    if not EXPORT_DIR.is_dir():
        raise FileNotFoundError(f"Export directory not found: {EXPORT_DIR}")

    if not BEFORE_SNAPSHOT.exists():
        existing = EXPORT_DIR / "effective_law_statements.json"
        if existing.exists():
            BEFORE_SNAPSHOT.write_text(existing.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            raise FileNotFoundError(
                f"No before snapshot at {BEFORE_SNAPSHOT} and no effective_law_statements.json"
            )

    before_metrics = analyze_export_context_closure(
        EXPORT_DIR,
        effective_law_path=BEFORE_SNAPSHOT,
    )

    payload = derive_effective_law_for_export(EXPORT_DIR)
    effective_path = EXPORT_DIR / "effective_law_statements.json"
    effective_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    after_metrics = analyze_export_context_closure(EXPORT_DIR)
    report = build_export_context_closure_report(before_metrics, after_metrics)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(
        f"Unresolved entries: {before_metrics.unresolved_required_context_entries} -> "
        f"{after_metrics.unresolved_required_context_entries}"
    )
    print(
        f"Workbench/export divergence: {before_metrics.workbench_resolvable_export_empty} -> "
        f"{after_metrics.workbench_resolvable_export_empty}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
