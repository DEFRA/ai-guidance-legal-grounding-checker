"""Fill generated mechanism/status blocks in divergence-workflow.d2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from law_proposition_extractor_pipeline.heuristics import REGISTRY_VERSION

from ..fixture_bundle import fixture_content_hash
from .d2_markers import replace_d2_generated_section
from .paths import divergence_status_manifest_path

_SECTION = "divergence-status-data"
_STATUS_MARKER = {
    "implemented": "[IMPL]",
    "partially_implemented": "[PARTIAL]",
    "planned": "[PLANNED]",
}


def load_divergence_status_manifest(root: Path | None = None) -> dict[str, Any]:
    path = divergence_status_manifest_path(root)
    return json.loads(path.read_text(encoding="utf-8"))


def render_divergence_status_d2_block(root: Path | None = None) -> str:
    """Render the GENERATED D2 fragment listing mechanisms with status tags."""
    manifest = load_divergence_status_manifest(root)
    fixture_hash = fixture_content_hash()[:12]
    lines: list[str] = [
        f"# compatible-registry-version: {REGISTRY_VERSION}",
        f"# compatible-fixture-hash: {fixture_hash}",
        "# status tags: [IMPL]=implemented [PARTIAL]=partially implemented [PLANNED]=planned",
        "",
        "mechanisms: {",
        '  label: "Divergence mechanisms (status from committed manifest)"',
        "  class: section",
        "",
    ]
    for row in manifest["mechanisms"]:
        status = str(row["status"])
        marker = _STATUS_MARKER[status]
        node_id = str(row["id"])
        label = str(row["label"])
        lines.append(f'  {node_id}: "{marker} {label}"')
        lines.append(f"  {node_id}.class: status_{status}")
        lines.append("")
    lines.append("}")
    lines.append("")
    lines.append("workflow_status: {")
    lines.append('  label: "Workflow stage status"')
    lines.append("  class: section")
    lines.append("")
    for row in manifest["workflow_stages"]:
        status = str(row["status"])
        marker = _STATUS_MARKER[status]
        node_id = f"wf_{row['id']}"
        label = str(row["label"])
        lines.append(f'  {node_id}: "{marker} {label}"')
        lines.append(f"  {node_id}.class: status_{status}")
        lines.append("")
    lines.append("}")
    lines.append("")
    lines.append("mechanisms -> workflow_status: \"same status legend\"")
    return "\n".join(lines).rstrip() + "\n"


def apply_divergence_generated_section(document: str, root: Path | None = None) -> str:
    return replace_d2_generated_section(
        document, _SECTION, render_divergence_status_d2_block(root=root)
    )


def assert_divergence_d2_truthfulness(d2_text: str, root: Path | None = None) -> None:
    """Ensure planned/unimplemented mechanisms are labelled, not implied complete."""
    manifest = load_divergence_status_manifest(root)
    for row in manifest["mechanisms"]:
        label = str(row["label"])
        status = str(row["status"])
        marker = _STATUS_MARKER[status]
        if f"{marker} {label}" not in d2_text:
            raise AssertionError(
                f"Divergence diagram missing truthful label for {label!r} ({status})."
            )
    for planned in (
        "dynamic-reference",
        "territorial",
        "revocation/replacement",
    ):
        if f"[PLANNED] {planned}" not in d2_text:
            raise AssertionError(f"Expected planned mechanism label for {planned!r}")
    if "[IMPL]" not in d2_text or "[PLANNED]" not in d2_text:
        raise AssertionError("Divergence diagram must show both implemented and planned states")
