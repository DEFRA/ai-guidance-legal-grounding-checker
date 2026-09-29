"""Post-export proposition hygiene: evidence backfill and re-classification (no LLM)."""

from __future__ import annotations

import copy
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import Proposition, SourceFragment, SourceRecord, assign_proposition_extraction_debug
from law_proposition_extractor_domain.proposition_notes import resolve_extraction_meta_for_proposition

from .export import export_bundle
from .extract import evidence_locates_verbatim_after_normalisation
from .extraction_json_repair import _enrich_bundle_from_export_files
from .linting import load_exported_bundle
from .proposition_normalisation import normalise_extracted_propositions

HYGIENE_COMMAND = "export-proposition-hygiene"


def _resolve_fragment_text(
    prop: Proposition,
    *,
    fragment_by_id: dict[str, SourceFragment],
    source_by_id: dict[str, SourceRecord],
) -> str:
    frag_id = str(prop.source_fragment_id or "").strip()
    if frag_id and frag_id in fragment_by_id:
        return str(fragment_by_id[frag_id].fragment_text or "")
    source = source_by_id.get(str(prop.source_record_id or ""))
    if source is not None:
        return str(source.authoritative_text or "")
    return ""


def _statutory_evidence_candidates(prop: Proposition) -> list[str]:
    subject = str(prop.legal_subject or "").strip()
    action = str(prop.action or "").strip().lower()
    label = str(prop.label or "").strip()
    candidates: list[str] = []
    if label.lower().startswith("definition:"):
        term = label.split(":", 1)[-1].strip()
        if term:
            subject = subject or term
    if not subject:
        return candidates
    for quote in ('"', "\u201c"):
        if action in {"means", "defines", ""}:
            candidates.append(f"{quote}{subject}{quote} means")
        if subject.lower().startswith("eutrophic"):
            candidates.append(f'{quote}eutrophic{quote}, in relation to water, means')
        if action in {"includes", "means", "defines", ""}:
            candidates.append(f"{quote}{subject}{quote}, in relation to")
        if "meaning" in action or action == "has the meaning given":
            candidates.append(f"{quote}{subject}{quote} has the meaning given")
        candidates.append(f"{quote}{subject}{quote}")
    candidates.append(subject)
    return candidates


def _expand_evidence_span(fragment_text: str, start: int, *, max_len: int = 160) -> str:
    end = min(len(fragment_text), start + max_len)
    span = fragment_text[start:end]
    for stop in ('";', ".", ";"):
        idx = span.find(stop)
        if idx > 24:
            span = span[: idx + (1 if stop != '";' else 0)]
            break
    return span.strip()


def derive_evidence_quote_from_fragment(prop: Proposition, fragment_text: str) -> str | None:
    """Find a verbatim evidence span in the source fragment for a proposition."""
    if not fragment_text.strip():
        return None
    meta = resolve_extraction_meta_for_proposition(
        notes=str(prop.notes or ""),
        extraction_debug_meta=prop.extraction_debug_meta,
    )
    existing = str((meta or {}).get("evidence_quote") or "").strip()
    if existing:
        ok, _, _ = evidence_locates_verbatim_after_normalisation(existing, fragment_text)
        if ok:
            return existing

    for needle in _statutory_evidence_candidates(prop):
        match = re.search(re.escape(needle), fragment_text, re.IGNORECASE)
        if not match:
            continue
        span = _expand_evidence_span(fragment_text, match.start())
        ok, _, _ = evidence_locates_verbatim_after_normalisation(span, fragment_text)
        if ok:
            return span

    ptxt = str(prop.proposition_text or "").strip()
    if len(ptxt) >= 24:
        words = ptxt.split()
        for size in (12, 10, 8, 6):
            if len(words) < size:
                continue
            chunk = " ".join(words[:size])
            ok, _, _ = evidence_locates_verbatim_after_normalisation(chunk, fragment_text)
            if ok:
                return chunk
    return None


def backfill_evidence_quote_if_missing(
    prop: Proposition,
    *,
    fragment_by_id: dict[str, SourceFragment],
    source_by_id: dict[str, SourceRecord],
) -> bool:
    meta = dict(prop.extraction_debug_meta or {})
    if str(meta.get("evidence_quote") or "").strip():
        return False
    fragment_text = _resolve_fragment_text(
        prop,
        fragment_by_id=fragment_by_id,
        source_by_id=source_by_id,
    )
    quote = derive_evidence_quote_from_fragment(prop, fragment_text)
    if not quote:
        return False
    meta["evidence_quote"] = quote
    meta.setdefault("evidence_match_strategy", "hygiene_backfill_from_fragment")
    if meta.get("repair_command") or meta.get("extraction_mode") == "fragment_repair":
        meta["evidence_backfill_reason"] = "fragment_repair_provenance_merge_recovery"
    assign_proposition_extraction_debug(prop, meta)
    return True


def apply_export_proposition_hygiene(
    propositions: list[Proposition],
    *,
    source_by_id: dict[str, SourceRecord],
    fragment_by_id: dict[str, SourceFragment],
) -> dict[str, int]:
    """Backfill missing evidence quotes and re-run deterministic classification passes."""
    stats = {"evidence_backfilled": 0}
    for prop in propositions:
        if backfill_evidence_quote_if_missing(
            prop,
            fragment_by_id=fragment_by_id,
            source_by_id=source_by_id,
        ):
            stats["evidence_backfilled"] += 1
    normalise_extracted_propositions(propositions, source_by_id=source_by_id)
    return stats


def run_export_hygiene_pipeline(
    *,
    export_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Load an export bundle, hygiene-normalise propositions, and re-export."""
    root = Path(export_dir).expanduser().resolve()
    out_dir = Path(output_dir).expanduser().resolve()
    bundle = _enrich_bundle_from_export_files(load_exported_bundle(root), root)
    sources = {
        str(row["id"]): SourceRecord.model_validate(row)
        for row in (bundle.get("source_records") or [])
        if isinstance(row, dict) and row.get("id")
    }
    fragments = {
        str(row["id"]): SourceFragment.model_validate(row)
        for row in (bundle.get("source_fragments") or [])
        if isinstance(row, dict) and row.get("id")
    }
    props = [Proposition.model_validate(row) for row in (bundle.get("propositions") or []) if isinstance(row, dict)]

    stats = apply_export_proposition_hygiene(
        props,
        source_by_id=sources,
        fragment_by_id=fragments,
    )
    run_existing = bundle.get("run") if isinstance(bundle.get("run"), dict) else {}

    updated = copy.deepcopy(bundle)
    updated["propositions"] = [p.model_dump(mode="json") for p in props]

    from .runner import _build_proposition_inventory

    updated["proposition_inventory"] = _build_proposition_inventory(props)

    hygiene_meta = {
        "hygiene_command": HYGIENE_COMMAND,
        "hygiene_source_export_dir": str(root),
        "hygiene_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "proposition_count": len(props),
        **stats,
    }
    existing = updated.get("export_hygiene_metadata")
    if isinstance(existing, list):
        updated["export_hygiene_metadata"] = [*existing, hygiene_meta]
    elif isinstance(existing, dict):
        updated["export_hygiene_metadata"] = [existing, hygiene_meta]
    else:
        updated["export_hygiene_metadata"] = [hygiene_meta]

    out_dir.mkdir(parents=True, exist_ok=True)
    export_bundle(updated, output_dir=str(out_dir.resolve()))
    updated["export_hygiene_summary"] = hygiene_meta
    return updated
