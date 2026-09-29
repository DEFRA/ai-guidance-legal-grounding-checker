"""Compare two static export directories for regressions and drift."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import RunComparisonChangeGroup, RunComparisonSummary

from .linting import lint_bundle, load_exported_bundle
from .run_quality import build_run_quality_summary


def _utc_now_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def _empty_group() -> RunComparisonChangeGroup:
    return RunComparisonChangeGroup()


def _instrument_id(record: dict[str, Any]) -> str:
    meta = record.get("metadata")
    if not isinstance(meta, dict):
        return ""
    for key in ("instrument_id", "instrumentId"):
        v = meta.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _pair_records_by_id_or_instrument(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
) -> tuple[
    list[tuple[dict[str, Any], dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Pair rows with matching id; then pair unmatched rows by instrument_id when present."""
    b_by_id = {str(r.get("id", "")): r for r in baseline if r.get("id")}
    c_by_id = {str(r.get("id", "")): r for r in candidate if r.get("id")}
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    used_b: set[str] = set()
    used_c: set[str] = set()
    for sid, br in b_by_id.items():
        if sid in c_by_id:
            pairs.append((br, c_by_id[sid]))
            used_b.add(sid)
            used_c.add(sid)
    b_unmatched = [r for sid, r in b_by_id.items() if sid not in used_b]
    c_unmatched = [r for sid, r in c_by_id.items() if sid not in used_c]
    b_by_inst: dict[str, dict[str, Any]] = {}
    for r in b_unmatched:
        inst = _instrument_id(r)
        if inst and inst not in b_by_inst:
            b_by_inst[inst] = r
    c_by_inst: dict[str, dict[str, Any]] = {}
    for r in c_unmatched:
        inst = _instrument_id(r)
        if inst and inst not in c_by_inst:
            c_by_inst[inst] = r
    used_inst_b: set[str] = set()
    used_inst_c: set[str] = set()
    for inst, br in b_by_inst.items():
        if inst in c_by_inst:
            pairs.append((br, c_by_inst[inst]))
            used_inst_b.add(inst)
            used_inst_c.add(inst)
    rem_b = [r for r in b_unmatched if _instrument_id(r) not in used_inst_b]
    rem_c = [r for r in c_unmatched if _instrument_id(r) not in used_inst_c]
    return pairs, rem_b, rem_c


def _change_group_from_pairing(
    *,
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    removed: list[dict[str, Any]],
    added: list[dict[str, Any]],
    id_fn: Any,
    compare_fn: Any,
) -> RunComparisonChangeGroup:
    added_ids = sorted({id_fn(r) for r in added})
    removed_ids = sorted({id_fn(r) for r in removed})
    changed_ids: list[str] = []
    notes: list[str] = []
    for left, right in pairs:
        lid = id_fn(left)
        if compare_fn(left, right):
            changed_ids.append(lid)
            notes.append(f"{lid}: content differs")
    changed_ids = sorted(set(changed_ids))
    return RunComparisonChangeGroup(
        added_count=len(added_ids),
        removed_count=len(removed_ids),
        changed_count=len(changed_ids),
        added_ids=added_ids,
        removed_ids=removed_ids,
        changed_ids=changed_ids,
        notes=sorted(set(notes))[:200],
    )


def _proposition_match_key(p: dict[str, Any]) -> str:
    key = p.get("proposition_key")
    if key is not None and str(key).strip():
        return str(key).strip()
    return f"__id__:{p.get('id', '')}"


# Opaque / display fields: matching is by proposition_key; these may drift without a semantic change.
_PROPOSITION_COSMETIC_KEYS = frozenset(
    {
        "id",
        "label",
        "slug",
        "short_name",
        "notes",
        "observed_in_run_id",
        "proposition_version_id",
        "review_status",
    }
)


def _proposition_semantic_dict(p: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in p.items() if k not in _PROPOSITION_COSMETIC_KEYS}


def _compare_divergence_records(
    baseline: dict[str, list[dict[str, Any]]],
    candidate: dict[str, list[dict[str, Any]]],
    prefix: str,
) -> RunComparisonChangeGroup:
    added_ids: list[str] = []
    removed_ids: list[str] = []
    changed_ids: list[str] = []
    notes: list[str] = []
    for kind, rows_b in baseline.items():
        rows_c = candidate.get(kind, [])
        bmap = {str(r.get("id", "")): r for r in rows_b if r.get("id")}
        cmap = {str(r.get("id", "")): r for r in rows_c if r.get("id")}
        all_ids = set(bmap) | set(cmap)
        for rid in sorted(all_ids):
            comp_id = f"{prefix}{kind}:{rid}"
            if rid in bmap and rid not in cmap:
                removed_ids.append(comp_id)
            elif rid in cmap and rid not in bmap:
                added_ids.append(comp_id)
            elif rid in bmap and rid in cmap:
                if _stable_json(bmap[rid]) != _stable_json(cmap[rid]):
                    changed_ids.append(comp_id)
                    notes.append(f"{comp_id}: payload differs")
    return RunComparisonChangeGroup(
        added_count=len(added_ids),
        removed_count=len(removed_ids),
        changed_count=len(changed_ids),
        added_ids=sorted(added_ids),
        removed_ids=sorted(removed_ids),
        changed_ids=sorted(changed_ids),
        notes=sorted(set(notes))[:200],
    )


def _quality_rank(status: str) -> int:
    if status == "pass":
        return 0
    if status == "pass_with_warnings":
        return 1
    if status == "fail":
        return 2
    return 1


def _ensure_quality(bundle: dict[str, Any]) -> dict[str, Any]:
    existing = bundle.get("run_quality_summary")
    if isinstance(existing, dict) and existing.get("run_id"):
        return existing
    lint = lint_bundle(bundle)
    return build_run_quality_summary(bundle, lint_report=lint)


def _unexplained_proposition_removals(
    baseline_props: list[dict[str, Any]],
    candidate_props: list[dict[str, Any]],
    candidate_source_ids: set[str],
    candidate_fragment_ids: set[str],
) -> list[str]:
    b_keys = {_proposition_match_key(p): p for p in baseline_props if isinstance(p, dict)}
    c_keys = {_proposition_match_key(p) for p in candidate_props if isinstance(p, dict)}
    removed = set(b_keys) - c_keys
    unexplained: list[str] = []
    for k in sorted(removed):
        p = b_keys[k]
        src = str(p.get("source_record_id", "") or "")
        frag = str(p.get("source_fragment_id", "") or "")
        src_gone = bool(src) and src not in candidate_source_ids
        frag_gone = bool(frag) and frag not in candidate_fragment_ids
        if src_gone or frag_gone:
            continue
        unexplained.append(k)
    return unexplained


def compare_export_dirs(
    baseline_export_dir: str | Path,
    candidate_export_dir: str | Path,
    *,
    comparison_id: str | None = None,
) -> dict[str, Any]:
    """Load two exports, diff sources/snapshots/fragments/propositions/divergence/quality/artifacts."""
    root_b = Path(baseline_export_dir)
    root_c = Path(candidate_export_dir)
    if not root_b.is_dir() or not root_c.is_dir():
        summary = RunComparisonSummary(
            id=comparison_id or f"cmp-inconclusive-{uuid.uuid4().hex[:12]}",
            baseline_run_id="",
            candidate_run_id="",
            generated_at=_utc_now_iso_z(),
            status="inconclusive",
            source_changes=_empty_group(),
            snapshot_changes=_empty_group(),
            fragment_changes=_empty_group(),
            proposition_changes=_empty_group(),
            divergence_changes=_empty_group(),
            quality_changes=_empty_group(),
            artifact_hash_changes=_empty_group(),
            warnings=["baseline or candidate export path is not a directory"],
            recommendations=["Verify --baseline-export-dir and --candidate-export-dir."],
        )
        return summary.model_dump(mode="json")

    try:
        bundle_b = load_exported_bundle(root_b)
        bundle_c = load_exported_bundle(root_c)
    except (OSError, ValueError) as exc:
        summary = RunComparisonSummary(
            id=comparison_id or f"cmp-inconclusive-{uuid.uuid4().hex[:12]}",
            baseline_run_id="",
            candidate_run_id="",
            generated_at=_utc_now_iso_z(),
            status="inconclusive",
            source_changes=_empty_group(),
            snapshot_changes=_empty_group(),
            fragment_changes=_empty_group(),
            proposition_changes=_empty_group(),
            divergence_changes=_empty_group(),
            quality_changes=_empty_group(),
            artifact_hash_changes=_empty_group(),
            warnings=[f"failed to load export: {exc}"],
            recommendations=[],
        )
        return summary.model_dump(mode="json")

    run_b = bundle_b.get("run") if isinstance(bundle_b.get("run"), dict) else {}
    run_c = bundle_c.get("run") if isinstance(bundle_c.get("run"), dict) else {}
    baseline_run_id = str(run_b.get("id", ""))
    candidate_run_id = str(run_c.get("id", ""))
    if not baseline_run_id or not candidate_run_id:
        summary = RunComparisonSummary(
            id=comparison_id or f"cmp-inconclusive-{uuid.uuid4().hex[:12]}",
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            generated_at=_utc_now_iso_z(),
            status="inconclusive",
            source_changes=_empty_group(),
            snapshot_changes=_empty_group(),
            fragment_changes=_empty_group(),
            proposition_changes=_empty_group(),
            divergence_changes=_empty_group(),
            quality_changes=_empty_group(),
            artifact_hash_changes=_empty_group(),
            warnings=["missing run.id in baseline or candidate bundle"],
            recommendations=[],
        )
        return summary.model_dump(mode="json")

    src_b = bundle_b.get("source_records")
    src_c = bundle_c.get("source_records")
    if not isinstance(src_b, list):
        src_b = []
    if not isinstance(src_c, list):
        src_c = []
    sb = [r for r in src_b if isinstance(r, dict)]
    sc = [r for r in src_c if isinstance(r, dict)]
    spairs, srem_b, sadd_c = _pair_records_by_id_or_instrument(sb, sc)
    source_changes = _change_group_from_pairing(
        pairs=spairs,
        removed=srem_b,
        added=sadd_c,
        id_fn=lambda r: str(r.get("id", "")),
        compare_fn=lambda a, b: _stable_json(a) != _stable_json(b),
    )

    snap_b = bundle_b.get("source_snapshots")
    snap_c = bundle_c.get("source_snapshots")
    if not isinstance(snap_b, list):
        snap_b = []
    if not isinstance(snap_c, list):
        snap_c = []
    nb = [r for r in snap_b if isinstance(r, dict)]
    nc = [r for r in snap_c if isinstance(r, dict)]
    npairs, nrem_b, nadd_c = _pair_records_by_id_or_instrument(nb, nc)
    snapshot_changes = _change_group_from_pairing(
        pairs=npairs,
        removed=nrem_b,
        added=nadd_c,
        id_fn=lambda r: str(r.get("id", "")),
        compare_fn=lambda a, b: _stable_json(a) != _stable_json(b),
    )

    frag_b = bundle_b.get("source_fragments")
    frag_c = bundle_c.get("source_fragments")
    if not isinstance(frag_b, list):
        frag_b = []
    if not isinstance(frag_c, list):
        frag_c = []
    fb = [r for r in frag_b if isinstance(r, dict)]
    fc = [r for r in frag_c if isinstance(r, dict)]
    fpairs, frem_b, fadd_c = _pair_records_by_id_or_instrument(fb, fc)
    fragment_changes = _change_group_from_pairing(
        pairs=fpairs,
        removed=frem_b,
        added=fadd_c,
        id_fn=lambda r: str(r.get("id", "")),
        compare_fn=lambda a, b: _stable_json(a) != _stable_json(b),
    )

    prop_b = bundle_b.get("propositions")
    prop_c = bundle_c.get("propositions")
    if not isinstance(prop_b, list):
        prop_b = []
    if not isinstance(prop_c, list):
        prop_c = []
    pb = [r for r in prop_b if isinstance(r, dict)]
    pc = [r for r in prop_c if isinstance(r, dict)]
    b_by_key = {_proposition_match_key(p): p for p in pb}
    c_by_key = {_proposition_match_key(p): p for p in pc}
    all_keys = set(b_by_key) | set(c_by_key)
    prop_added = sorted(k for k in all_keys if k in c_by_key and k not in b_by_key)
    prop_removed = sorted(k for k in all_keys if k in b_by_key and k not in c_by_key)
    prop_changed: list[str] = []
    prop_notes: list[str] = []
    for k in sorted(set(b_by_key) & set(c_by_key)):
        if str(b_by_key[k].get("proposition_text", "")) != str(
            c_by_key[k].get("proposition_text", "")
        ):
            prop_changed.append(k)
            prop_notes.append(f"{k}: proposition_text differs")
        elif _stable_json(_proposition_semantic_dict(b_by_key[k])) != _stable_json(
            _proposition_semantic_dict(c_by_key[k])
        ):
            prop_changed.append(k)
            prop_notes.append(f"{k}: semantic fields differ (excluding label/slug/id)")
    proposition_changes = RunComparisonChangeGroup(
        added_count=len(prop_added),
        removed_count=len(prop_removed),
        changed_count=len(prop_changed),
        added_ids=prop_added,
        removed_ids=prop_removed,
        changed_ids=sorted(prop_changed),
        notes=sorted(set(prop_notes))[:200],
    )

    div_baseline = {
        "observation": [
            r for r in bundle_b.get("divergence_observations", []) if isinstance(r, dict)
        ],
        "assessment": [
            r for r in bundle_b.get("divergence_assessments", []) if isinstance(r, dict)
        ],
        "finding": [r for r in bundle_b.get("divergence_findings", []) if isinstance(r, dict)],
    }
    div_candidate = {
        "observation": [
            r for r in bundle_c.get("divergence_observations", []) if isinstance(r, dict)
        ],
        "assessment": [
            r for r in bundle_c.get("divergence_assessments", []) if isinstance(r, dict)
        ],
        "finding": [r for r in bundle_c.get("divergence_findings", []) if isinstance(r, dict)],
    }
    divergence_changes = _compare_divergence_records(div_baseline, div_candidate, "")

    q_b = _ensure_quality(bundle_b)
    q_c = _ensure_quality(bundle_c)
    qlint_b = lint_bundle(bundle_b)
    qlint_c = lint_bundle(bundle_c)
    quality_changed = (
        str(q_b.get("status", "")) != str(q_c.get("status", ""))
        or int(q_b.get("error_count", 0)) != int(q_c.get("error_count", 0))
        or int(q_b.get("warning_count", 0)) != int(q_c.get("warning_count", 0))
    )
    q_notes: list[str] = []
    if quality_changed:
        q_notes.append(
            f"status {q_b.get('status')} -> {q_c.get('status')}; "
            f"errors {q_b.get('error_count')} -> {q_c.get('error_count')}; "
            f"warnings {q_b.get('warning_count')} -> {q_c.get('warning_count')}"
        )
    quality_changes = RunComparisonChangeGroup(
        added_count=0,
        removed_count=0,
        changed_count=1 if quality_changed else 0,
        added_ids=[],
        removed_ids=[],
        changed_ids=["run_quality_summary"] if quality_changed else [],
        notes=q_notes,
    )

    art_b = bundle_b.get("run_artifacts")
    art_c = bundle_c.get("run_artifacts")
    if not isinstance(art_b, list):
        art_b = []
    if not isinstance(art_c, list):
        art_c = []
    ab = {str(a.get("id")): a for a in art_b if isinstance(a, dict) and a.get("id")}
    ac = {str(a.get("id")): a for a in art_c if isinstance(a, dict) and a.get("id")}
    all_aid = set(ab) | set(ac)
    ah_added = sorted(i for i in all_aid if i in ac and i not in ab)
    ah_removed = sorted(i for i in all_aid if i in ab and i not in ac)
    ah_changed: list[str] = []
    ah_notes: list[str] = []
    for i in sorted(set(ab) & set(ac)):
        hb = str(ab[i].get("content_hash", "") or "")
        hc = str(ac[i].get("content_hash", "") or "")
        if hb and hc and hb != hc:
            ah_changed.append(i)
            ah_notes.append(f"{i}: content_hash differs")
        elif _stable_json(ab[i]) != _stable_json(ac[i]):
            ah_changed.append(i)
            ah_notes.append(f"{i}: artifact metadata differs")
    artifact_hash_changes = RunComparisonChangeGroup(
        added_count=len(ah_added),
        removed_count=len(ah_removed),
        changed_count=len(ah_changed),
        added_ids=ah_added,
        removed_ids=ah_removed,
        changed_ids=sorted(ah_changed),
        notes=sorted(set(ah_notes))[:200],
    )

    groups = [
        source_changes,
        snapshot_changes,
        fragment_changes,
        proposition_changes,
        divergence_changes,
        quality_changes,
        artifact_hash_changes,
    ]
    any_change = any(
        g.added_count or g.removed_count or g.changed_count for g in groups
    )

    cand_src_ids = {str(r.get("id", "")) for r in sc if r.get("id")}
    cand_frag_ids = {str(r.get("id", "")) for r in fc if r.get("id")}
    unexplained = _unexplained_proposition_removals(pb, pc, cand_src_ids, cand_frag_ids)

    worse_quality = _quality_rank(str(q_c.get("status", ""))) > _quality_rank(
        str(q_b.get("status", ""))
    )
    more_lint_errors = int(qlint_c.get("error_count", 0)) > int(qlint_b.get("error_count", 0))
    mystery_prop_drop = bool(unexplained)

    is_regression = worse_quality or more_lint_errors or mystery_prop_drop

    warnings: list[str] = []
    if mystery_prop_drop:
        warnings.append(
            "Proposition(s) removed without matching source/fragment removal: "
            + ", ".join(unexplained[:20])
        )
    if worse_quality:
        warnings.append(
            f"Candidate run quality status regressed: {q_b.get('status')} -> {q_c.get('status')}"
        )
    if more_lint_errors:
        warnings.append(
            f"Candidate has more lint errors: {qlint_b.get('error_count')} -> {qlint_c.get('error_count')}"
        )

    recommendations: list[str] = []
    if is_regression:
        recommendations.append("Review warnings and fix quality or data lineage before shipping.")
    elif any_change:
        recommendations.append("Review change groups; confirm intentional drift.")

    if is_regression:
        status: Any = "regression"
    elif not any_change:
        status = "unchanged"
    else:
        status = "changed"

    cid = comparison_id or f"cmp-{baseline_run_id}-{candidate_run_id}-{uuid.uuid4().hex[:10]}"

    summary = RunComparisonSummary(
        id=cid,
        baseline_run_id=baseline_run_id,
        candidate_run_id=candidate_run_id,
        generated_at=_utc_now_iso_z(),
        status=status,
        source_changes=source_changes,
        snapshot_changes=snapshot_changes,
        fragment_changes=fragment_changes,
        proposition_changes=proposition_changes,
        divergence_changes=divergence_changes,
        quality_changes=quality_changes,
        artifact_hash_changes=artifact_hash_changes,
        warnings=warnings,
        recommendations=recommendations,
        metrics={
            "baseline_lint_error_count": qlint_b.get("error_count"),
            "candidate_lint_error_count": qlint_c.get("error_count"),
            "unexplained_proposition_removals": unexplained,
        },
    )
    return summary.model_dump(mode="json")


def write_comparison_summary(path: str | Path, summary: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
