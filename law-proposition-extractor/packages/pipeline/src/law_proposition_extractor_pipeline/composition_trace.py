"""Attach export-level composition traces via the shared TypeScript enrichment."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_JUDIT_ROOT = Path(__file__).resolve().parents[4]
_WEB_ROOT = _JUDIT_ROOT / "apps" / "web"


def _enrich_via_node(payload: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "input.json"
        output_path = Path(tmp) / "output.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        env = {
            **os.environ,
            "ENRICH_INPUT_PATH": str(input_path),
            "ENRICH_OUTPUT_PATH": str(output_path),
        }
        proc = subprocess.run(
            ["npm", "test", "--", "lib/export-composition-trace-enrich.test.ts"],
            cwd=_WEB_ROOT,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "composition trace enrichment failed:\n"
                f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
            )
        if not output_path.exists():
            raise RuntimeError("composition trace enrichment did not write output file")
        result: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
        return result


def enrich_effective_law_statements(
    *,
    statements_payload: dict[str, Any],
    propositions: list[dict[str, Any]],
    source_fragments: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    proposition_completeness_assessments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return effective-law payload with composition_trace on each statement."""
    payload = {
        "propositions": propositions,
        "source_fragments": source_fragments or [],
        "source_records": sources or [],
        "effective_law_statements": statements_payload,
        "proposition_completeness_assessments": proposition_completeness_assessments or [],
    }
    return _enrich_via_node(payload)


def attach_composition_traces(bundle: dict[str, Any]) -> None:
    """Mutate bundle effective_law_statements with composition_trace fields."""
    statements_payload = bundle.get("effective_law_statements")
    propositions = bundle.get("propositions")
    if not isinstance(statements_payload, dict) or not isinstance(propositions, list):
        return
    source_fragments = bundle.get("source_fragments")
    sources = bundle.get("sources") or bundle.get("source_records")
    completeness = bundle.get("proposition_completeness_assessments")
    bundle["effective_law_statements"] = enrich_effective_law_statements(
        statements_payload=statements_payload,
        propositions=propositions,
        source_fragments=source_fragments if isinstance(source_fragments, list) else None,
        sources=sources if isinstance(sources, list) else None,
        proposition_completeness_assessments=(
            completeness if isinstance(completeness, list) else None
        ),
    )
