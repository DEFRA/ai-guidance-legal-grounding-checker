"""Aggregate source-reported legal effects into an export artifact."""

from __future__ import annotations

from typing import Any

from law_proposition_extractor_domain import OutstandingEffectsStatus

from law_proposition_extractor_pipeline.affecting_instrument_consumption import (
    collect_source_register_entries_from_bundle,
    reconcile_source_legal_effects_artifact,
)


def build_source_legal_effects_artifact(
    *,
    run_id: str,
    source_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build ``source_legal_effects.json`` from per-snapshot inventories.

    Empty inventories are valid. Older runs without snapshot metadata yield an
    empty artifact with ``outstanding_effects_status=source_status_unknown``.
    """
    effects: list[dict[str, Any]] = []
    effect_links: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    statuses: list[OutstandingEffectsStatus] = []
    meta_parts: list[dict[str, Any]] = []

    for snap in source_snapshots or []:
        if not isinstance(snap, dict):
            continue
        snap_meta = snap.get("metadata")
        if not isinstance(snap_meta, dict):
            continue
        inventory = snap_meta.get("source_legal_effects")
        if not isinstance(inventory, dict):
            continue
        for row in inventory.get("effects") or []:
            if isinstance(row, dict):
                effects.append(row)
        for row in inventory.get("effect_links") or []:
            if isinstance(row, dict):
                effect_links.append(row)
        for row in inventory.get("diagnostics") or []:
            if isinstance(row, dict):
                diagnostics.append(row)
        status_raw = inventory.get("outstanding_effects_status")
        try:
            statuses.append(OutstandingEffectsStatus(str(status_raw)))
        except ValueError:
            statuses.append(OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN)
        inv_meta = inventory.get("metadata")
        if isinstance(inv_meta, dict):
            meta_parts.append(inv_meta)

    if OutstandingEffectsStatus.SOURCE_REPORTS_PRESENT in statuses:
        outstanding = OutstandingEffectsStatus.SOURCE_REPORTS_PRESENT
    elif statuses and all(s == OutstandingEffectsStatus.SOURCE_REPORTS_NONE for s in statuses):
        outstanding = OutstandingEffectsStatus.SOURCE_REPORTS_NONE
    else:
        outstanding = OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN

    effects.sort(
        key=lambda row: (
            str(row.get("source_snapshot_id") or ""),
            str(row.get("annotation_label") or ""),
            str(row.get("annotation_id") or ""),
            str(row.get("id") or ""),
        )
    )
    effect_links.sort(
        key=lambda row: (
            str(row.get("effect_id") or ""),
            str(row.get("affected_locator") or ""),
            str(row.get("id") or ""),
        )
    )

    return {
        "schema_version": "1",
        "run_id": run_id,
        "effects": effects,
        "effect_links": effect_links,
        "outstanding_effects_status": outstanding.value,
        "diagnostics": diagnostics,
        "metadata": {
            "snapshot_inventory_count": len(meta_parts),
            "effect_count": len(effects),
            "effect_link_count": len(effect_links),
            "notes": (
                "Records amendment/effect annotations reported in the consumed source. "
                "Does not prove Law Proposition Extractor applied amendments or independently consumed "
                "affecting instruments. Revised manifestation status is separate. "
                "independent_consumption_status is reconciled against this run's "
                "source records/snapshots (and register entries when available)."
            ),
        },
    }


def attach_source_legal_effects(bundle: dict[str, Any]) -> None:
    """Derive ``source_legal_effects`` onto an export bundle.

    After aggregating per-snapshot inventories, reconciles affecting-instrument
    independent consumption against the run's source records/snapshots.
    """
    run = bundle.get("run")
    run_id = ""
    if isinstance(run, dict):
        run_id = str(run.get("id") or "")
    snapshots = bundle.get("source_snapshots")
    artifact = build_source_legal_effects_artifact(
        run_id=run_id,
        source_snapshots=snapshots if isinstance(snapshots, list) else [],
    )

    source_records = bundle.get("source_records")
    if not isinstance(source_records, list):
        sources = bundle.get("sources")
        source_records = sources if isinstance(sources, list) else []

    artifact = reconcile_source_legal_effects_artifact(
        artifact,
        source_records=source_records if isinstance(source_records, list) else [],
        source_snapshots=snapshots if isinstance(snapshots, list) else [],
        source_register_entries=collect_source_register_entries_from_bundle(bundle),
    )
    # Keep metadata effect_count in sync after reconciliation.
    meta = artifact.get("metadata")
    if isinstance(meta, dict):
        meta["effect_count"] = len(artifact.get("effects") or [])
    bundle["source_legal_effects"] = artifact
