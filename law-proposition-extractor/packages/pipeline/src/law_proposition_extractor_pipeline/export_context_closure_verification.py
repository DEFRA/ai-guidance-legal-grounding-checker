"""Verify export context closure improvements against a run export bundle."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from law_proposition_extractor_pipeline.context_locator_resolution import (
    parse_container_locator_targets,
    resolve_context_locator,
    structural_context_for_proposition,
)
from law_proposition_extractor_pipeline.effective_law import build_effective_law_statements


@dataclass
class ExportContextClosureMetrics:
    export_dir: str
    unresolved_required_context_entries: int = 0
    empty_proposition_ids_entries: int = 0
    workbench_resolvable_export_empty: int = 0
    container_resolutions: int = 0
    ambiguous_entries: int = 0
    external_entries: int = 0
    resolved_with_proposition_ids: int = 0
    top_unresolved_locators: list[tuple[str, int]] = field(default_factory=list)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_unresolved_entry(entry: dict[str, Any]) -> bool:
    status = str(entry.get("resolution_status") or "").strip()
    prop_ids = [str(x).strip() for x in (entry.get("proposition_ids") or []) if str(x).strip()]
    if prop_ids:
        return False
    return status in {"", "unresolved", "ambiguous", "missing"}


def _primary_source_record_id(statement: dict[str, Any], proposition_by_id: dict[str, dict]) -> str | None:
    for prop_id in statement.get("source_proposition_ids") or []:
        source_id = str(proposition_by_id.get(str(prop_id), {}).get("source_record_id") or "").strip()
        if source_id:
            return source_id
    return None


def _workbench_resolvable(
    entry: dict[str, Any],
    *,
    statement: dict[str, Any],
    proposition_by_id: dict[str, dict],
    source_fragments: list[dict[str, Any]],
) -> bool:
    source_record_id = _primary_source_record_id(statement, proposition_by_id)
    if not source_record_id:
        return False
    host_prop_id = str((statement.get("source_proposition_ids") or [""])[0])
    host_prop = proposition_by_id.get(host_prop_id, {})
    structural_context = structural_context_for_proposition(
        host_prop,
        source_fragments=source_fragments,
    )
    resolution = resolve_context_locator(
        str(entry.get("locator") or ""),
        source_record_id=source_record_id,
        source_fragments=source_fragments,
        structural_context=structural_context,
        propositions=list(proposition_by_id.values()),
    )
    return resolution.resolved and bool(resolution.matched_fragment_ids)


def analyze_export_context_closure(
    export_dir: str | Path,
    *,
    effective_law_path: str | Path | None = None,
) -> ExportContextClosureMetrics:
    root = Path(export_dir)
    propositions = _load_json(root / "propositions.json")
    source_fragments = _load_json(root / "source_fragments.json")
    law_path = Path(effective_law_path) if effective_law_path else root / "effective_law_statements.json"
    statements_payload = _load_json(law_path)
    statements = statements_payload.get("statements") or []

    proposition_by_id = {str(p["id"]): p for p in propositions if p.get("id")}

    metrics = ExportContextClosureMetrics(export_dir=str(root))
    unresolved_locators: Counter[str] = Counter()

    for statement in statements:
        standalone = str(statement.get("standalone_status") or "")
        in_focus = standalone in {
            "context_dependent",
            "partially_resolved",
            "unresolved_reference",
        }
        source_record_id = _primary_source_record_id(statement, proposition_by_id)
        host_prop_id = str((statement.get("source_proposition_ids") or [""])[0])
        host_prop = proposition_by_id.get(host_prop_id, {})

        for entry in statement.get("required_context") or []:
            locator = str(entry.get("locator") or "")
            prop_ids = [str(x).strip() for x in (entry.get("proposition_ids") or []) if str(x).strip()]
            status = str(entry.get("resolution_status") or "")

            if (
                parse_container_locator_targets(locator)
                and status == "resolved"
                and prop_ids
            ):
                metrics.container_resolutions += 1

            if not in_focus:
                continue

            if not _is_unresolved_entry(entry):
                if prop_ids:
                    metrics.resolved_with_proposition_ids += 1
                continue

            metrics.unresolved_required_context_entries += 1
            unresolved_locators[locator] += 1

            if not prop_ids:
                metrics.empty_proposition_ids_entries += 1

            if status == "ambiguous":
                metrics.ambiguous_entries += 1
            if status == "external_reference":
                metrics.external_entries += 1

            if not prop_ids and _workbench_resolvable(
                entry,
                statement=statement,
                proposition_by_id=proposition_by_id,
                source_fragments=source_fragments,
            ):
                metrics.workbench_resolvable_export_empty += 1

    metrics.top_unresolved_locators = unresolved_locators.most_common(30)
    return metrics


def derive_effective_law_for_export(export_dir: str | Path) -> dict[str, Any]:
    """Re-derive effective law statements from existing propositions (no LLM)."""
    root = Path(export_dir)
    propositions = _load_json(root / "propositions.json")
    source_fragments = _load_json(root / "source_fragments.json")
    run_payload = _load_json(root / "run.json") if (root / "run.json").exists() else {}
    run_id = str(run_payload.get("id") or "run-unknown")
    groups_path = root / "legal_rule_groups.json"
    rels_path = root / "legal_rule_relationships.json"
    legal_rule_groups = _load_json(groups_path) if groups_path.exists() else None
    legal_rule_relationships = _load_json(rels_path) if rels_path.exists() else None
    return build_effective_law_statements(
        propositions,
        run_id=run_id,
        source_fragments=source_fragments,
        legal_rule_groups=legal_rule_groups if isinstance(legal_rule_groups, dict) else None,
        legal_rule_relationships=(
            legal_rule_relationships if isinstance(legal_rule_relationships, dict) else None
        ),
    )


def build_export_context_closure_report(
    before: ExportContextClosureMetrics,
    after: ExportContextClosureMetrics,
) -> str:
    lines: list[str] = []
    lines.append("# Export context closure report")
    lines.append("")
    lines.append(f"**Before export:** `{before.export_dir}`")
    lines.append(f"**After export:** `{after.export_dir}`")
    lines.append("")
    lines.append("Deterministic before/after comparison of required-context locator closure in effective-law export.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Before | After | Delta |")
    lines.append("| --- | ---: | ---: | ---: |")

    def row(label: str, b: int, a: int) -> None:
        lines.append(f"| {label} | {b} | {a} | {a - b:+d} |")

    row("Unresolved required_context entries", before.unresolved_required_context_entries, after.unresolved_required_context_entries)
    row("Entries with empty proposition_ids", before.empty_proposition_ids_entries, after.empty_proposition_ids_entries)
    row("Workbench-resolvable but export-empty divergence", before.workbench_resolvable_export_empty, after.workbench_resolvable_export_empty)
    row("Container locator resolutions (all statements)", before.container_resolutions, after.container_resolutions)
    row("Ambiguous entries (unresolved population)", before.ambiguous_entries, after.ambiguous_entries)
    row("Resolved entries with proposition_ids", before.resolved_with_proposition_ids, after.resolved_with_proposition_ids)
    lines.append("")
    lines.append("## Top unresolved locators (after)")
    lines.append("")
    lines.append("| Locator | Count |")
    lines.append("| --- | ---: |")
    for locator, count in after.top_unresolved_locators[:30]:
        lines.append(f"| `{locator}` | {count} |")
    lines.append("")
    lines.append("## Reproduction")
    lines.append("")
    lines.append("Re-derive effective law (no LLM):")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run --package law-proposition-extractor-pipeline python -c \"")
    lines.append("from pathlib import Path")
    lines.append("import json")
    lines.append("from law_proposition_extractor_pipeline.export_context_closure_verification import derive_effective_law_for_export")
    lines.append("root = Path('law-proposition-extractor/runs/slurry-gb-principal-5-current-export')")
    lines.append("payload = derive_effective_law_for_export(root)")
    lines.append("(root / 'effective_law_statements.json').write_text(json.dumps(payload, indent=2))")
    lines.append("\"")
    lines.append("```")
    lines.append("")
    lines.append("Generate this report:")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run --package law-proposition-extractor-pipeline python scripts/generate_export_context_closure_report.py")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)
