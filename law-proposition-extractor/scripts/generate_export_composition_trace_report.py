#!/usr/bin/env python3
"""Regenerate effective-law export with composition traces and write analysis report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

JUDIT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = JUDIT_ROOT / "runs/slurry-gb-principal-5-current-export"
REPORT_PATH = JUDIT_ROOT / "docs/export-composition-trace-report.md"


def derive_and_write_effective_law(export_dir: Path) -> None:
    from law_proposition_extractor_pipeline.export_context_closure_verification import derive_effective_law_for_export
    from law_proposition_extractor_pipeline.composition_trace import enrich_effective_law_statements

    payload = derive_effective_law_for_export(export_dir)
    propositions = json.loads((export_dir / "propositions.json").read_text(encoding="utf-8"))
    source_fragments = json.loads((export_dir / "source_fragments.json").read_text(encoding="utf-8"))
    sources_path = export_dir / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else []
    completeness_path = export_dir / "proposition_completeness_assessments.json"
    completeness = (
        json.loads(completeness_path.read_text(encoding="utf-8"))
        if completeness_path.exists()
        else []
    )
    enriched = enrich_effective_law_statements(
        statements_payload=payload,
        propositions=propositions,
        source_fragments=source_fragments,
        sources=sources,
        proposition_completeness_assessments=completeness,
    )
    (export_dir / "effective_law_statements.json").write_text(
        json.dumps(enriched, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    if not EXPORT_DIR.is_dir():
        raise FileNotFoundError(f"Export directory not found: {EXPORT_DIR}")

    derive_and_write_effective_law(EXPORT_DIR)

    env = {
        **dict(**__import__("os").environ),
        "EXPORT_COMPOSITION_TRACE_EXPORT_DIR": str(EXPORT_DIR),
        "EXPORT_COMPOSITION_TRACE_REPORT_PATH": str(REPORT_PATH),
    }
    subprocess.run(
        ["npm", "test", "--", "lib/export-composition-trace.test.ts"],
        cwd=JUDIT_ROOT / "apps/web",
        env=env,
        check=True,
    )
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
