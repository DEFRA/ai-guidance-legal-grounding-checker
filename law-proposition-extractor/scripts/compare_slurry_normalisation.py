#!/usr/bin/env python3
"""Before/after comparison: slurry frontier export vs post-extraction normalisation v1."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import Proposition
from law_proposition_extractor_domain.enums import LegalEffectType, PropositionTier
from law_proposition_extractor_pipeline.proposition_quality_gates import (
    run_proposition_quality_gates,
    write_normalisation_quality_artifacts,
)
from law_proposition_extractor_pipeline.runner import _build_proposition_inventory
from law_proposition_extractor_pipeline.slurry_normalisation_acceptance import (
    AGRICULTURAL_LAND_ENGLAND_TEXT,
    DIFFUSE_SOURCE_2018,
    _REG1_LOCATOR,
    cross_instrument_cross_reference_targets,
    default_slurry_export_path,
    compliance_relevant_only_visible,
    explorer_visible_default,
    is_generic_these_regulations_key,
    load_slurry_export_propositions,
    normalise_slurry_propositions,
)

REPO = Path(__file__).resolve().parents[1]
EXPORT = default_slurry_export_path(REPO)
DIFFUSE_SOURCE = DIFFUSE_SOURCE_2018
EXAMPLE_TEXT = AGRICULTURAL_LAND_ENGLAND_TEXT

DEFAULT_FILTERS = {
    "filter_proposition_tier": "",
    "filter_legal_effect_type": "",
    "filter_territorial_application": "",
    "filter_extent": "",
    "show_instrument_metadata": False,
    "compliance_relevant_only": False,
    "comparison_anchors_only": False,
    "collapse_scope_rules": True,
}


def _load_before() -> list[dict[str, Any]]:
    return load_slurry_export_propositions(EXPORT)


def _normalise_after(before: list[dict[str, Any]]) -> list[Proposition]:
    return normalise_slurry_propositions(before)


def _tier(p: dict[str, Any] | Proposition) -> str:
    if isinstance(p, Proposition):
        return p.proposition_tier.value
    return str(p.get("proposition_tier") or "(none)")


def _effect(p: dict[str, Any] | Proposition) -> str:
    if isinstance(p, Proposition):
        return p.legal_effect_type.value
    return str(p.get("legal_effect_type") or "(none)")


def _compliance(p: dict[str, Any] | Proposition) -> bool | None:
    if isinstance(p, Proposition):
        return p.is_compliance_relevant
    v = p.get("is_compliance_relevant")
    return v if v is True or v is False else None


def _anchor(p: dict[str, Any] | Proposition) -> bool | None:
    if isinstance(p, Proposition):
        return p.is_comparison_anchor
    v = p.get("is_comparison_anchor")
    return v if v is True or v is False else None


def _categories(p: dict[str, Any]) -> list[str]:
    c = p.get("categories") or []
    return [str(x) for x in c] if isinstance(c, list) else []


def _cross_targets(p: dict[str, Any] | Proposition) -> list[str]:
    if isinstance(p, Proposition):
        return list(p.cross_reference_targets or [])
    t = p.get("cross_reference_targets") or []
    return [str(x) for x in t] if isinstance(t, list) else []


def _xref_key(p: dict[str, Any] | Proposition) -> str:
    if isinstance(p, Proposition):
        return str(p.cross_reference_key or "")
    return str(p.get("cross_reference_key") or "")


def _is_generic_key(key: str) -> bool:
    return is_generic_these_regulations_key(key)


def _instrument_metadata_hidden(p: Proposition) -> bool:
    if p.proposition_tier == PropositionTier.INSTRUMENT_METADATA:
        return True
    return p.legal_effect_type in {LegalEffectType.CITATION, LegalEffectType.COMMENCEMENT}


def _explorer_visible(p: Proposition) -> bool:
    return explorer_visible_default(p)


def _compliance_explorer_visible(p: Proposition) -> bool:
    return compliance_relevant_only_visible(p)


def _count_by(items: list[str]) -> dict[str, int]:
    return dict(Counter(items))


def _diff_counters(before: dict[str, int], after: dict[str, int]) -> list[tuple[str, int, int, int]]:
    keys = sorted(set(before) | set(after))
    rows: list[tuple[str, int, int, int]] = []
    for k in keys:
        b = before.get(k, 0)
        a = after.get(k, 0)
        rows.append((k, b, a, a - b))
    return rows


def _cross_instrument_links(props: list[dict[str, Any]] | list[Proposition]) -> list[dict[str, Any]]:
    if props and isinstance(props[0], Proposition):
        return cross_instrument_cross_reference_targets(props)  # type: ignore[arg-type]
    by_id: dict[str, Any] = {}
    for p in props:
        pid = str(p.get("id", ""))
        by_id[pid] = p
    bad: list[dict[str, Any]] = []
    for p in props:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", ""))
        sid = str(p.get("source_record_id") or "")
        for tid in _cross_targets(p):
            target = by_id.get(tid)
            if not isinstance(target, dict):
                continue
            tsid = str(target.get("source_record_id") or "")
            if tsid and sid and tsid != sid:
                bad.append(
                    {
                        "from_id": pid,
                        "to_id": tid,
                        "from_source": sid,
                        "to_source": tsid,
                        "xref_key": _xref_key(p),
                    }
                )
    return bad


def _reg1_rows(props: list[dict[str, Any]] | list[Proposition], source_id: str) -> list[Any]:
    out = []
    for p in props:
        sid = (
            p.source_record_id
            if isinstance(p, Proposition)
            else str(p.get("source_record_id") or "")
        )
        if sid != source_id:
            continue
        loc = (
            p.fragment_locator
            if isinstance(p, Proposition)
            else str(p.get("fragment_locator") or "")
        )
        if not _REG1_LOCATOR.match(str(loc).strip()):
            continue
        out.append(p)
    return sorted(
        out,
        key=lambda p: (
            p.fragment_locator if isinstance(p, Proposition) else str(p.get("fragment_locator"))
        ),
    )


def main() -> None:
    before = _load_before()
    after = _normalise_after(before)
    after_dicts = [p.model_dump() for p in after]

    inv_before = json.loads((EXPORT / "proposition_inventory.json").read_text(encoding="utf-8"))
    inv_after = _build_proposition_inventory(after)

    # Metrics
    tier_b = _count_by([_tier(p) for p in before])
    tier_a = _count_by([_tier(p) for p in after])
    effect_b = _count_by([_effect(p) for p in before])
    effect_a = _count_by([_effect(p) for p in after])

    comp_b = Counter()
    comp_a = Counter()
    for p in before:
        v = _compliance(p)
        comp_b[v if v is not None else "null"] += 1
    for p in after:
        v = p.is_compliance_relevant
        comp_a[v if v is not None else "null"] += 1

    anchor_b = Counter()
    anchor_a = Counter()
    for p in before:
        v = _anchor(p)
        anchor_b[v if v is not None else "null"] += 1
    for p in after:
        v = p.is_comparison_anchor
        anchor_a[v if v is not None else "null"] += 1

    hidden_a = sum(1 for p in after if _instrument_metadata_hidden(p))
    visible_b = len(before)  # no filter in old export
    visible_a = sum(1 for p in after if _explorer_visible(p))
    compliance_only_a = sum(1 for p in after if _compliance_explorer_visible(p))

    obligation_reclassified: list[dict[str, str]] = []
    for b, a in zip(before, after, strict=True):
        if "obligation" not in _categories(b):
            continue
        tier = a.proposition_tier.value
        effect = a.legal_effect_type.value
        if tier in {
            PropositionTier.SCOPE_RULE.value,
            PropositionTier.INSTRUMENT_METADATA.value,
            PropositionTier.DEFINITIONAL_RULE.value,
        } or effect in {
            LegalEffectType.APPLICATION_SCOPE.value,
            LegalEffectType.CITATION.value,
            LegalEffectType.COMMENCEMENT.value,
            LegalEffectType.EXTENT.value,
            LegalEffectType.DEFINITION.value,
        }:
            obligation_reclassified.append(
                {
                    "id": a.id,
                    "text": a.proposition_text[:80],
                    "tier": tier,
                    "effect": effect,
                    "label": a.label,
                }
            )

    generic_keys_b = sum(1 for p in before if _is_generic_key(_xref_key(p)))
    generic_keys_a = sum(1 for p in after if _is_generic_key(_xref_key(p)))

    cross_bad_b = _cross_instrument_links(before)
    cross_bad_a = _cross_instrument_links(after)

    # Links removed: before had target, after empty or only same-source
    links_removed: list[dict[str, str]] = []
    links_changed: list[dict[str, str]] = []
    for b, a in zip(before, after, strict=True):
        bt, at = set(_cross_targets(b)), set(_cross_targets(a))
        if bt and not at:
            links_removed.append(
                {
                    "id": a.id,
                    "old_key": _xref_key(b),
                    "old_targets": ", ".join(sorted(bt)),
                }
            )
        elif bt != at:
            links_changed.append(
                {
                    "id": a.id,
                    "old_targets": ", ".join(sorted(bt)),
                    "new_targets": ", ".join(sorted(at)),
                }
            )

    sem_idx_b = inv_before.get("semantic_comparison_index") or {}
    sem_idx_a = inv_after.get("semantic_comparison_index") or {}
    scoped_idx_a = inv_after.get("source_scoped_index") or {}

    # Label improvements: generic territorial/citation labels -> specific
    label_improvements: list[dict[str, str]] = []
    generic_labels = {
        "Territorial application",
        "Territorial extent",
        "Citation",
        "Commencement date",
    }
    for b, a in zip(before, after, strict=True):
        old_l = str(b.get("label") or "").strip()
        new_l = a.label.strip()
        if old_l in generic_labels and new_l and new_l != old_l:
            label_improvements.append(
                {
                    "id": a.id,
                    "old": old_l,
                    "new": new_l,
                    "locator": str(a.fragment_locator or ""),
                }
            )

    example_before = next(p for p in before if p.get("proposition_text") == EXAMPLE_TEXT)
    example_after = next(p for p in after if p.proposition_text == EXAMPLE_TEXT)

    reg1_before = _reg1_rows(before, DIFFUSE_SOURCE)
    reg1_after = _reg1_rows(after, DIFFUSE_SOURCE)

    report_lines = [
        "# Slurry frontier export: normalisation before/after",
        "",
        "**Baseline:** `runs/slurry-gb-principal-5-frontier-export` (frontier extraction, 5 principal sources, 678 propositions).",
        "",
        "**After:** same proposition texts and source selection; **post-extraction normalisation v1** "
        "(classification → jurisdiction → labelling → relationship keys) re-applied in-process. "
        "No re-run of frontier LLM extraction (47m / cost unchanged; comparison isolates normalisation).",
        "",
        "## Count summary",
        "",
        f"| Metric | Before | After | Δ |",
        f"| --- | ---: | ---: | ---: |",
        f"| Total propositions | {len(before)} | {len(after)} | 0 |",
        f"| Explorer visible (default filters) | {visible_b} | {visible_a} | {visible_a - visible_b} |",
        f"| Compliance-relevant only (after filter) | n/a | {compliance_only_a} | — |",
        f"| Hidden instrument metadata / citation / commencement | n/a | {hidden_a} | — |",
        f"| `is_compliance_relevant=true` | {comp_b.get(True, 0)} | {comp_a.get(True, 0)} | {comp_a.get(True, 0) - comp_b.get(True, 0)} |",
        f"| `is_compliance_relevant=false` | {comp_b.get(False, 0)} | {comp_a.get(False, 0)} | {comp_a.get(False, 0) - comp_b.get(False, 0)} |",
        f"| `is_comparison_anchor=true` | {anchor_b.get(True, 0)} | {anchor_a.get(True, 0)} | {anchor_a.get(True, 0) - anchor_b.get(True, 0)} |",
        f"| Generic `uk:these-regulations:*` keys | {generic_keys_b} | {generic_keys_a} | {generic_keys_a - generic_keys_b} |",
        f"| Cross-instrument `cross_reference_targets` | {len(cross_bad_b)} | {len(cross_bad_a)} | {len(cross_bad_a) - len(cross_bad_b)} |",
        f"| `semantic_comparison_index` buckets | {len(sem_idx_b)} | {len(sem_idx_a)} | {len(sem_idx_a) - len(sem_idx_b)} |",
        f"| `source_scoped_index` buckets | — | {len(scoped_idx_a)} | — |",
        "",
        "## By proposition_tier",
        "",
        "| Tier | Before | After | Δ |",
        "| --- | ---: | ---: | ---: |",
    ]
    for k, b, a, d in _diff_counters(tier_b, tier_a):
        report_lines.append(f"| {k} | {b} | {a} | {d} |")

    report_lines.extend(
        [
            "",
            "## By legal_effect_type",
            "",
            "| Effect | Before | After | Δ |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for k, b, a, d in _diff_counters(effect_b, effect_a):
        report_lines.append(f"| {k} | {b} | {a} | {d} |")

    report_lines.extend(
        [
            "",
            "## What improved",
            "",
            "- **Scope/application** rows (e.g. reg 1(d)) are no longer labelled as generic obligations; they get `scope_rule` / `application_scope`, specific labels, and `is_compliance_relevant=false`.",
            "- **Instrument boilerplate** (citation, commencement, extent) is classified as `instrument_metadata` and hidden from default explorer view.",
            "- **Generic cross-reference keys** (`uk:these-regulations:apply-to`) are replaced with source-scoped keys; **cross-instrument false links via `cross_reference_targets` are removed**.",
            f"- **`semantic_comparison_index`** populated ({len(sem_idx_a)} buckets) for cross-instrument *comparison hints* without auto-merging inventory.",
            "- **Human notes** separated from `judit_extraction_meta` blobs (`review_notes` null when only machine meta).",
            "",
            "## Obligation category → scope / metadata / definition",
            "",
            f"**{len(obligation_reclassified)}** propositions had LLM `categories: [\"obligation\"]` but normalised to scope, instrument metadata, or definition.",
            "",
        ]
    )
    for row in obligation_reclassified[:15]:
        report_lines.append(
            f"- `{row['id']}` **{row['effect']}** / {row['tier']}: {row['label'][:70]}…"
            if len(row["label"]) > 70
            else f"- `{row['id']}` **{row['effect']}** / {row['tier']}: {row['label']}"
        )
    if len(obligation_reclassified) > 15:
        report_lines.append(f"- … and {len(obligation_reclassified) - 15} more")

    report_lines.extend(
        [
            "",
            "## Relationship links",
            "",
            f"- **Removed** (had targets, now empty): {len(links_removed)}",
            f"- **Changed** (targets differ): {len(links_changed)}",
            "",
        ]
    )
    for row in links_removed[:8]:
        report_lines.append(f"  - `{row['id']}` key `{row['old_key']}` → dropped targets [{row['old_targets']}]")
    for row in cross_bad_b[:5]:
        report_lines.append(
            f"  - **Before false link:** `{row['from_id']}` ({row['from_source']}) → `{row['to_id']}` ({row['to_source']}) via `{row['xref_key']}`"
        )

    report_lines.extend(
        [
            "",
            "## Label examples (generic → specific)",
            "",
        ]
    )
    for row in label_improvements[:12]:
        report_lines.append(f"- `{row['locator']}`: **{row['old']}** → **{row['new']}**")

    report_lines.extend(
        [
            "",
            f"## 2018 Diffuse Pollution — regulation 1 (`{DIFFUSE_SOURCE}`)",
            "",
            "| Locator | Before label | After label | After tier | After effect | Compliance | Anchor |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for b, a in zip(reg1_before, reg1_after, strict=True):
        loc = a.fragment_locator
        report_lines.append(
            f"| {loc} | {b.get('label')} | {a.label} | {a.proposition_tier.value} | "
            f"{a.legal_effect_type.value} | {a.is_compliance_relevant} | {a.is_comparison_anchor} |"
        )

    report_lines.extend(
        [
            "",
            "## Example: agricultural land in England",
            "",
            "| Field | Before | After |",
            "| --- | --- | --- |",
            f"| label | {example_before.get('label')} | {example_after.label} |",
            f"| categories | {example_before.get('categories')} | (unchanged) |",
            f"| proposition_tier | — | {example_after.proposition_tier.value} |",
            f"| legal_effect_type | — | {example_after.legal_effect_type.value} |",
            f"| territorial_application | — | {example_after.territorial_application} |",
            f"| is_compliance_relevant | — | {example_after.is_compliance_relevant} |",
            f"| is_comparison_anchor | — | {example_after.is_comparison_anchor} |",
            f"| cross_reference_key | {example_before.get('cross_reference_key')} | {example_after.cross_reference_key} |",
            f"| cross_reference_targets | {example_before.get('cross_reference_targets')} | {example_after.cross_reference_targets} |",
            f"| semantic_comparison_key | — | {example_after.semantic_comparison_key or '—'} |",
            "",
            "## Suspicious regressions / caveats",
            "",
            "- **Proposition count unchanged** (678): normalisation only enriches fields; no rows added/removed.",
            "- **LLM `categories` array is not rewritten** — still shows `obligation` on some scope rows; UI/filters should use `legal_effect_type` / `proposition_tier`, not raw categories.",
            "- **Extent row on 2018 reg 1(c)** extends to England and Wales while (d) applies to agricultural land in England — territorially correct but analysts should read both extent and application_scope.",
            "- **Boilerplate vs LLM `provision_type`:** text patterns (`may be cited as`, `come into force`, `apply to`) override noisy extraction meta (e.g. reg 1(a) cited as `definition` in frontier output).",
            "- Re-running full frontier extraction could change proposition texts/counts; this report isolates normalisation only.",
            "",
            "## Explorer noise",
            "",
            f"- Default explorer list shrinks from **{visible_b}** to **{visible_a}** (−{visible_b - visible_a} hidden metadata/citation/commencement rows).",
            f"- **Compliance-only** filter retains **{compliance_only_a}** propositions (vs {comp_a.get(True, 0)} flagged compliance-relevant).",
            "- Example application-scope row is **visible** in default browse but **excluded** from compliance-only — substantive duties easier to scan.",
            "",
        ]
    )

    out_path = EXPORT / "NORMALISATION_COMPARISON.md"
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote {out_path}")

    quality_report = run_proposition_quality_gates(after, newly_normalised=True)
    md_q, json_q = write_normalisation_quality_artifacts(EXPORT, quality_report)
    print(f"Wrote {md_q} ({quality_report.error_count} errors, {quality_report.warning_count} warnings)")
    print(f"Wrote {json_q}")


if __name__ == "__main__":
    main()
