"""Offline inspector for Article 49a reference / trigger presentation contract.

No network, LLM, or secrets. Summarises provenance, propositions, inline
relative resolution, groups, typed relationships, and expanded trigger cards.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    assert_article_49a_legal_structure,
    fixture_dir,
    run_article_49a_acceptance_pipeline,
)
from law_proposition_extractor_pipeline.context_locator_resolution import (
    LocatorStructuralContext,
    parse_locator_structural_context,
    resolve_context_locator,
)

HISTORICAL_7_PROP_EXPORT = Path(
    "runs/fish/article-49a-acceptance-2026-07-14-export"
)
CURRENT_COMPARISON_EXPORT = Path(
    "runs/fish/article-49a-current-code-comparison-export"
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "tests" / "fixtures").is_dir():
            return candidate
    return here.parents[4]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _props_from_export(export_dir: Path) -> list[dict[str, Any]]:
    payload = _load_json(export_dir / "propositions.json")
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        rows = payload.get("propositions") or []
        return [p for p in rows if isinstance(p, dict)]
    return []


def _statements_from_export(export_dir: Path) -> list[dict[str, Any]]:
    payload = _load_json(export_dir / "effective_law_statements.json")
    if isinstance(payload, dict):
        return [s for s in (payload.get("statements") or []) if isinstance(s, dict)]
    if isinstance(payload, list):
        return [s for s in payload if isinstance(s, dict)]
    return []


def _groups_from_export(export_dir: Path) -> list[dict[str, Any]]:
    path = export_dir / "legal_rule_groups.json"
    if not path.is_file():
        return []
    payload = _load_json(path)
    if isinstance(payload, dict):
        return [g for g in (payload.get("groups") or []) if isinstance(g, dict)]
    return []


def _rels_from_export(export_dir: Path) -> list[dict[str, Any]]:
    path = export_dir / "legal_rule_relationships.json"
    if not path.is_file():
        return []
    payload = _load_json(path)
    if isinstance(payload, dict):
        return [r for r in (payload.get("relationships") or []) if isinstance(r, dict)]
    return []


def _provenance(export_dir: Path) -> dict[str, Any]:
    for name in ("ARTIFACT_PROVENANCE.json", "artifact_provenance.json"):
        path = export_dir / name
        if path.is_file():
            payload = _load_json(path)
            if isinstance(payload, dict):
                return payload
    run_path = export_dir / "run.json"
    created = None
    if run_path.is_file():
        run = _load_json(run_path)
        if isinstance(run, dict):
            created = run.get("created_at")
    return {
        "freshness_class": "unknown",
        "generated_at": created,
        "proposition_count": None,
    }


def _structured_path(prop: dict[str, Any]) -> str | None:
    meta = prop.get("extraction_debug_meta")
    if isinstance(meta, dict) and meta.get("structured_list_path"):
        return str(meta["structured_list_path"])
    return None


def _duplicate_semantic_identities(props: list[dict[str, Any]]) -> list[str]:
    by_path: dict[str, list[str]] = {}
    for prop in props:
        path = _structured_path(prop)
        if not path:
            continue
        by_path.setdefault(path, []).append(str(prop.get("id")))
    return [f"{path}:{ids}" for path, ids in by_path.items() if len(ids) > 1]


def _legacy_locator_aliases(props: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for prop in props:
        loc = str(prop.get("fragment_locator") or "")
        if ":list:2-a-i" in loc or "subparagraph:a:item:i" in loc:
            out.append(f"canonical_terminal:{loc}")
        if loc.endswith(":(a)(i)") or loc.endswith(":a(i)"):
            out.append(f"legacy_alias:{loc}")
    return out


def inspect_export(export_dir: Path, *, label: str) -> dict[str, Any]:
    props = _props_from_export(export_dir)
    statements = _statements_from_export(export_dir)
    groups = _groups_from_export(export_dir)
    rels = _rels_from_export(export_dir)
    provenance = _provenance(export_dir)
    article_props = [
        p for p in props if str(p.get("fragment_locator") or "").startswith("article:49a")
    ]
    p3 = next(
        (
            p
            for p in article_props
            if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:3")
        ),
        None,
    )
    p3_stmt = None
    if p3 is not None:
        p3_stmt = next(
            (
                s
                for s in statements
                if str(p3["id"]) in (s.get("source_proposition_ids") or [])
            ),
            None,
        )
    triggers = [
        c
        for c in ((p3_stmt or {}).get("required_context") or [])
        if isinstance(c, dict) and c.get("kind") == "trigger_condition"
    ]
    resolved_inline: dict[str, Any] | None = None
    if p3 is not None:
        fragments = _load_json(export_dir / "source_fragments.json")
        if isinstance(fragments, dict):
            fragments = fragments.get("source_fragments") or fragments.get("fragments") or []
        structural = parse_locator_structural_context("article:49a:paragraph:3")
        if structural is not None:
            resolution = resolve_context_locator(
                "paragraph 2",
                source_record_id=str(p3.get("source_record_id") or ""),
                source_fragments=[f for f in fragments if isinstance(f, dict)],
                structural_context=LocatorStructuralContext(
                    source_record_id=str(p3.get("source_record_id") or ""),
                    segments=structural.segments,
                ),
                propositions=props,
            )
            matched = [
                str(f.get("locator"))
                for f in fragments
                if isinstance(f, dict)
                and str(f.get("id") or "") in set(resolution.matched_fragment_ids or [])
            ]
            canonical = (
                "article:49a:paragraph:2"
                if "article:49a:paragraph:2" in matched
                else resolution.resolved_locator
            )
            resolved_inline = {
                "raw_locator": "paragraph 2",
                "resolved": resolution.resolved,
                "resolution_basis": resolution.resolution_basis,
                "resolution_status": resolution.resolution_status,
                "resolved_locator": canonical,
                "resolver_surface_locator": resolution.resolved_locator,
                "matched_fragment_locators": matched,
            }

    return {
        "label": label,
        "export_dir": str(export_dir),
        "artifact_provenance": provenance,
        "propositions": len(article_props),
        "proposition_locators": [
            {
                "id": p.get("id"),
                "locator": p.get("fragment_locator"),
                "structured_list_path": _structured_path(p),
            }
            for p in article_props
        ],
        "effective_law_statements": len(statements),
        "resolved_inline_references": resolved_inline,
        "groups": [
            {
                "canonical_locator": g.get("canonical_locator"),
                "member_count": len(g.get("member_proposition_ids") or []),
                "members": g.get("member_proposition_ids"),
            }
            for g in groups
        ],
        "typed_relationships": [
            {
                "type": r.get("relationship_type"),
                "source": r.get("source_id"),
                "target": r.get("target_id"),
            }
            for r in rels
        ],
        "expanded_trigger_cards": len(triggers),
        "trigger_locators": [t.get("locator") for t in triggers],
        "duplicate_semantic_identities": _duplicate_semantic_identities(article_props),
        "legacy_locator_aliases": _legacy_locator_aliases(article_props),
    }


def inspect_fresh_current_code(work_dir: Path | None = None) -> dict[str, Any]:
    work = work_dir or Path(tempfile.mkdtemp(prefix="article-49a-inspect-"))
    result = run_article_49a_acceptance_pipeline(work_dir=work)
    roles = result.proposition_ids
    assert_article_49a_legal_structure(result.bundle)
    summary = inspect_export(result.export_dir, label="fresh_current_code")
    summary["roles"] = roles
    summary["acceptance"] = "pass"
    return summary


def render_summary(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# Article 49a reference contract inspection", ""]
    for row in rows:
        lines.append(f"## {row['label']}")
        lines.append(f"- export: `{row.get('export_dir')}`")
        prov = row.get("artifact_provenance") or {}
        lines.append(
            "- artifact provenance: "
            f"freshness={prov.get('freshness_class')!r} "
            f"generated_at={prov.get('generated_at')!r} "
            f"schema={prov.get('artifact_schema_version')!r} "
            f"contract={prov.get('semantic_contract_version')!r} "
            f"pipeline_build={prov.get('pipeline_build')!r}"
        )
        lines.append(f"- propositions: {row.get('propositions')}")
        lines.append(f"- effective-law statements: {row.get('effective_law_statements')}")
        inline = row.get("resolved_inline_references")
        if inline:
            lines.append(
                "- resolved inline references: "
                f"{inline.get('raw_locator')!r} → {inline.get('resolved_locator')!r} "
                f"basis={inline.get('resolution_basis')!r} "
                f"status={inline.get('resolution_status')!r} "
                f"matched={inline.get('matched_fragment_locators')}"
            )
        else:
            lines.append("- resolved inline references: (unavailable)")
        lines.append(f"- groups: {row.get('groups')}")
        lines.append(f"- typed relationships: {row.get('typed_relationships')}")
        lines.append(
            f"- expanded trigger cards: {row.get('expanded_trigger_cards')} "
            f"{row.get('trigger_locators')}"
        )
        lines.append(
            f"- duplicate semantic identities: {row.get('duplicate_semantic_identities')}"
        )
        lines.append(f"- legacy locator aliases: {row.get('legacy_locator_aliases')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def regenerate_current_code_comparison(root: Path | None = None) -> Path:
    """Regenerate comparison export without touching the historical 7-prop artifact."""
    base = root or _repo_root()
    out = base / CURRENT_COMPARISON_EXPORT
    work = base / "runs/fish/.article-49a-current-code-work"
    shutil.rmtree(work, ignore_errors=True)
    result = run_article_49a_acceptance_pipeline(work_dir=work)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(result.export_dir, out)
    snapshots = result.bundle.get("source_snapshots") or []
    snapshot_id = snapshots[0].get("id") if snapshots and isinstance(snapshots[0], dict) else None
    meta = {
        "artifact_schema_version": "1",
        "semantic_contract_version": "article_49a_legal_structure_v1",
        "pipeline_build": "current-code-offline-acceptance",
        "prompt_version": "fixture-curated",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "proposition_count": len(result.proposition_ids),
        "source_snapshot_id": snapshot_id,
        "freshness_class": "current_code",
        "predates_duplicate_terminal_suppression": False,
        "predates_prompt_v3": False,
        "predates_trigger_cue_v2": False,
        "matches_six_proposition_acceptance": len(result.proposition_ids) == 6,
        "notes": [
            "Offline regeneration via run_article_49a_acceptance_pipeline under current code.",
            "Historical seven-proposition export left immutable at "
            "article-49a-acceptance-2026-07-14-export.",
        ],
    }
    (out / "ARTIFACT_PROVENANCE.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="inspect",
        choices=("inspect", "regenerate"),
        help="inspect (default) or regenerate the current-code comparison export",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the text summary.",
    )
    parser.add_argument(
        "--skip-fresh",
        action="store_true",
        help="Skip regenerating a fresh current-code bundle (compare committed exports only).",
    )
    args = parser.parse_args(argv)
    root = _repo_root()

    if args.command == "regenerate":
        out = regenerate_current_code_comparison(root)
        print(out)
        return 0

    rows: list[dict[str, Any]] = []

    historical = root / HISTORICAL_7_PROP_EXPORT
    if historical.is_dir():
        rows.append(inspect_export(historical, label="displayed_historical_run_001"))

    current = root / CURRENT_COMPARISON_EXPORT
    if current.is_dir():
        rows.append(inspect_export(current, label="committed_current_code_comparison"))

    frontend_bundle = (
        root
        / "apps"
        / "web"
        / "lib"
        / "fixtures"
        / "article-49a-acceptance"
        / "serialized-bundle.json"
    )
    if frontend_bundle.is_file():
        # Present as a synthetic export-shaped summary from the frontend fixture.
        payload = _load_json(frontend_bundle)
        tmp = Path(tempfile.mkdtemp(prefix="article-49a-frontend-bundle-"))
        for name, key in (
            ("propositions.json", "propositions"),
            ("effective_law_statements.json", "effective_law_statements"),
            ("legal_rule_groups.json", "legal_rule_groups"),
            ("legal_rule_relationships.json", "legal_rule_relationships"),
            ("source_fragments.json", "source_fragments"),
        ):
            value = payload.get(key)
            if value is not None:
                (tmp / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        (tmp / "ARTIFACT_PROVENANCE.json").write_text(
            json.dumps(
                {
                    "freshness_class": "current_code",
                    "matches_six_proposition_acceptance": True,
                    "semantic_contract_version": "article_49a_legal_structure_v1",
                    "pipeline_build": "frontend-acceptance-serialized-bundle",
                    "proposition_count": len(payload.get("propositions") or []),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        rows.append(inspect_export(tmp, label="committed_frontend_acceptance_bundle"))

    if not args.skip_fresh:
        rows.append(inspect_fresh_current_code())

    # Fixture path presence check (offline contract source).
    fix = fixture_dir(root)
    if not fix.is_dir():
        raise SystemExit(f"Missing fixture dir: {fix}")

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(render_summary(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
