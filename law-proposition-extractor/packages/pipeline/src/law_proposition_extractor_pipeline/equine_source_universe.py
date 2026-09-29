"""Staged equine source universe: manifest, profiles, readiness snapshot."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

_UI_CLUSTER_LABELS: dict[str, str] = {
    "equine_identification_passport": "Equine identification / passport",
    "eu_exit_amendments": "EU Exit amendments",
    "movement_import_trade": "Movement / import / trade",
    "official_controls": "Official controls",
    "context_guidance_candidates": "Context / guidance / candidates",
}

AnalysisScope = Literal["selected_sources", "candidate_universe"]


def load_equine_source_universe(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Source universe must be a JSON object.")
    inst = raw.get("instruments")
    if not isinstance(inst, list) or len(inst) < 1:
        raise ValueError("instruments must be a non-empty list.")
    profs = raw.get("profiles")
    if not isinstance(profs, dict) or not profs:
        raise ValueError("profiles must be a non-empty object.")
    return raw


def universe_instrument_count(universe: dict[str, Any]) -> int:
    inst = universe.get("instruments")
    return len(inst) if isinstance(inst, list) else 0


def cluster_counts_by_ui_cluster(universe: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in universe.get("instruments") or []:
        if not isinstance(row, dict):
            continue
        k = str(row.get("ui_cluster") or "unknown").strip() or "unknown"
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items()))


def build_universe_readiness_snapshot(
    *,
    universe_path: str | Path,
    profile_id: str,
    analysed_legislation_source_count: int,
    universe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    u = universe if universe is not None else load_equine_source_universe(universe_path)
    prof = u.get("profiles") or {}
    prof_obj = prof.get(profile_id) if isinstance(prof, dict) else None
    clusters = cluster_counts_by_ui_cluster(u)
    labelled = {k: {"count": v, "label": _UI_CLUSTER_LABELS.get(k, k)} for k, v in clusters.items()}
    return {
        "universe_id": str(u.get("universe_id") or ""),
        "universe_version": str(u.get("version") or ""),
        "universe_path": str(Path(universe_path).resolve()) if universe_path else "",
        "profile_id": profile_id,
        "profile_label": str((prof_obj or {}).get("label") or profile_id)
        if isinstance(prof_obj, dict)
        else profile_id,
        "universe_instrument_count": universe_instrument_count(u),
        "analysed_legislation_source_count": analysed_legislation_source_count,
        "cluster_counts": labelled,
        "disclaimer": str(u.get("disclaimer") or ""),
        "analysis_scope": str((prof_obj or {}).get("analysis_scope") or "")
        if isinstance(prof_obj, dict)
        else "",
    }


def profile_member_ids(universe: dict[str, Any], profile_id: str) -> list[str]:
    prof = universe.get("profiles") or {}
    if not isinstance(prof, dict):
        return []
    p = prof.get(profile_id)
    if not isinstance(p, dict):
        raise KeyError(f"Unknown corpus profile {profile_id!r}")
    mids = p.get("member_instrument_ids")
    if not isinstance(mids, list):
        raise ValueError(f"Profile {profile_id} missing member_instrument_ids list")
    return [str(x) for x in mids]


_ASID_RE = re.compile(r"^[a-z]+/\d{4}/\d+$")


def assert_known_authority_id(asid: str) -> None:
    if not _ASID_RE.match(asid.strip().lower()):
        raise ValueError(f"Invalid instrument id shape: {asid!r}")


def estimate_summary_from_universe_offline(
    universe: dict[str, Any],
    profile_id: str,
    *,
    avg_chars_per_instrument: int = 120_000,
    avg_fragments_per_instrument: int = 3,
) -> dict[str, Any]:
    """Heuristic cost class when XML is not fetched (no network)."""
    ids = profile_member_ids(universe, profile_id)
    prof = (universe.get("profiles") or {}).get(profile_id)
    if not isinstance(prof, dict):
        raise KeyError(f"Unknown corpus profile {profile_id!r}")
    scope = prof.get("analysis_scope")
    if scope == "candidate_universe":
        n = 0
        frag_mult = 0
    else:
        n = len(ids)
        frag_mult = avg_fragments_per_instrument
    approx_frags = max(0, n * frag_mult)
    approx_calls = approx_frags  # lower bound; chunking can raise
    approx_tokens = approx_calls * 40_000  # rough mid estimate
    tier = "small"
    if n >= 18 or approx_calls >= 40:
        tier = "very_large"
    elif n >= 12 or approx_calls >= 24:
        tier = "large"
    elif n >= 6 or approx_calls >= 12:
        tier = "medium"
    return {
        "mode": "offline_heuristic",
        "profile_id": profile_id,
        "analysed_source_count": n,
        "estimated_fragment_count": approx_frags,
        "estimated_llm_invocations_lower_bound": approx_calls,
        "estimated_input_tokens_approx": approx_tokens,
        "cost_class": tier,
        "avg_chars_per_instrument_assumption": avg_chars_per_instrument,
    }


def _discovery_family_from_ui_cluster(ui: str) -> str:
    m = {
        "equine_identification_passport": "equine_passport_identification",
        "eu_exit_amendments": "eu_exit_amendments",
        "movement_import_trade": "movement_entry_certification",
        "official_controls": "official_controls",
        "context_guidance_candidates": "uk_context",
    }
    return m.get(ui, "uk_context")


def _legislation_source(inst: dict[str, Any]) -> dict[str, Any]:
    i = inst
    return {
        "id": i["source_id"],
        "authority": "legislation_gov_uk",
        "authority_source_id": i["id"],
        "title": i["title"],
        "version_id": i["date"],
        "as_of_date": i["date"],
        "metadata": {
            "cluster": "animal_identification_traceability",
            "equine_source_universe": {
                "instrument_id": i["id"],
                "ui_cluster": i["ui_cluster"],
                "source_family": i["source_family"],
                "analysis_role": i["analysis_role"],
                "extraction_default": i["extraction_default"],
            },
        },
    }


def _family_candidate(inst: dict[str, Any], profile_id: str) -> dict[str, Any]:
    parts = str(inst["id"]).split("/")
    cid = f"uni-{parts[0]}-{parts[1]}-{parts[2]}"
    series, year, num = parts
    citation = f"{series.upper()} {year}/{num}"
    return {
        "id": cid,
        "title": inst["title"],
        "citation": citation,
        "url": inst["url"],
        "source_role": "unknown",
        "relationship_to_target": "contextual",
        "inclusion_status": "candidate_needs_review",
        "reason": str(inst.get("notes") or "Source universe row — register and ingest to analyse as a legal source."),
        "metadata": {
            "equine_law_discovery": {
                "family": _discovery_family_from_ui_cluster(str(inst.get("ui_cluster") or "")),
                "lineage": "source_universe",
            },
            "equine_source_universe": {
                "instrument_id": inst["id"],
                "ui_cluster": inst["ui_cluster"],
                "extraction_default": "candidate_only",
                "analysis_role": inst["analysis_role"],
                "corpus_profile_id": profile_id,
            },
        },
    }


def _base_case_stub(universe: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_versions": {"proposition_extraction": "v2-structured-list-round-robin"},
        "topic": {
            "name": "Equine staged corpus",
            "description": str(universe.get("disclaimer") or ""),
            "subject_tags": ["equine", "staged-corpus"],
        },
        "cluster": {
            "name": "animal_identification_traceability",
            "description": "Identification, import, trade, and control-related duties.",
        },
        "extraction": {},
        "sources": [],
        "narrative": {"title": "Staged equine corpus", "summary": "Profile-selected instruments."},
        "run_notes": "",
    }


def materialize_case_for_profile(universe: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """Build case_data dict for ``profile_id`` (same shape as committed example JSON files)."""
    profs = universe.get("profiles")
    if not isinstance(profs, dict):
        raise ValueError("universe missing profiles")
    prof = profs.get(profile_id)
    if not isinstance(prof, dict):
        raise KeyError(f"Unknown corpus profile {profile_id!r}")
    inst_by_id = {str(i["id"]): i for i in universe.get("instruments") or [] if isinstance(i, dict)}

    case = _base_case_stub(universe)
    case["extraction"] = deepcopy(prof.get("extraction") or {})
    case["corpus_profile_id"] = profile_id
    case["equine_source_universe_ref"] = {
        "path": "examples/equine_source_universe.json",
        "universe_id": str(universe.get("universe_id") or ""),
    }

    mids = prof.get("member_instrument_ids")
    if not isinstance(mids, list):
        raise ValueError(f"Profile {profile_id} missing member_instrument_ids")

    if prof.get("analysis_scope") == "candidate_universe":
        case["case_analysis_mode"] = "candidate_universe"
        case["sources"] = []
        case["source_family_candidates"] = [_family_candidate(inst_by_id[iid], profile_id) for iid in mids]
        case["topic"]["name"] = "Equine source universe — discovery candidates (full 21)"
        case["topic"]["description"] = str(universe.get("disclaimer") or "")
        case["narrative"]["title"] = "Full equine source universe (candidates)"
        case["narrative"]["summary"] = (
            "All staged instruments appear as discovery candidates only; no statutory fetch for this profile."
        )
        case["run_notes"] = (
            "candidate_universe mode: sources[] empty; candidates list the staged universe. "
            "Not auto-analysed — use passport/movement profiles for extraction."
        )
    else:
        members = [inst_by_id[i] for i in mids]
        case["sources"] = [_legislation_source(i) for i in members]
        lbl = str(prof.get("label") or profile_id)
        case["topic"]["name"] = lbl
        case["topic"]["description"] = f'{universe.get("disclaimer") or ""} Active profile: {profile_id}.'
        case["topic"]["subject_tags"] = ["equine", "staged-corpus", profile_id]
        case["narrative"]["title"] = lbl
        case["narrative"]["summary"] = f"Profile {profile_id}: {len(members)} legislation.gov.uk instruments."
        case["run_notes"] = (
            f"Profile {profile_id} — {len(members)} instruments. "
            "Wider universe: examples/equine_source_universe.json."
        )
    return case


def materialize_case_from_universe_path(path: str | Path, profile_id: str) -> dict[str, Any]:
    u = load_equine_source_universe(path)
    return materialize_case_for_profile(u, profile_id)
