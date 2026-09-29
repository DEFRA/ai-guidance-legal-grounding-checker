"""Split human review notes from pipeline extraction/debug metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

EXTRACTION_META_PREFIX = "judit_extraction_meta:"
EXTRACTION_REUSE_PREFIX = "judit_extraction_reuse:"

# Keys kept on the proposition for classification/evidence UI; heavy debug lives on traces.
_PROPOSITION_EXTRACTION_META_KEYS = frozenset(
    {
        "extraction_mode",
        "model_alias",
        "fallback_policy",
        "fallback_used",
        "validation_errors",
        "prompt_version",
        "schema_version",
        "provision_type",
        "completeness_status",
        "model_confidence",
        "evidence_quote",
        "evidence_match_strategy",
        "trace_warnings",
        "estimated_input_tokens_max",
        "context_window_risk",
        "extraction_chunk_count",
        "focus_scopes",
        "fallback_strategy",
    }
)

# Never embed on propositions — preserved on PropositionExtractionTrace.signals / bundle traces.
_TRACE_ONLY_EXTRACTION_META_KEYS = frozenset(
    {
        "extraction_llm_call_traces",
        "raw_model_output_excerpt",
        "raw_model_output_truncated",
        "pipeline_evidence_issue_records",
    }
)


@dataclass(frozen=True)
class ParsedPropositionNotes:
    """Result of parsing a legacy or mixed ``notes`` field."""

    review_notes: str | None
    human_notes: str
    extraction_meta: dict[str, Any] | None
    extraction_reuse: dict[str, Any] | None
    meta_parse_failed: bool
  # When True, ``human_notes`` retains the original blob for lossless reload.


def slim_proposition_extraction_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Drop trace-oriented keys from metadata stored on the proposition artifact."""
    if not meta:
        return {}
    return {k: v for k, v in meta.items() if k not in _TRACE_ONLY_EXTRACTION_META_KEYS}


def full_trace_extraction_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Full extraction metadata blob for trace ``signals`` (no data loss)."""
    return dict(meta) if meta else {}


def parse_extraction_meta(notes: str | None) -> dict[str, Any] | None:
    if not notes:
        return None
    first = notes.split("\n", 1)[0].strip()
    if not first.startswith(EXTRACTION_META_PREFIX):
        return None
    raw = first[len(EXTRACTION_META_PREFIX) :].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data:
        return None
    return data


def parse_extraction_reuse(
    notes: str | None = None,
    *,
    extraction_debug_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if isinstance(extraction_debug_meta, dict):
        reuse = extraction_debug_meta.get("extraction_reuse")
        if isinstance(reuse, dict) and reuse:
            return reuse
    if not notes:
        return None
    for raw_ln in notes.split("\n"):
        ln = raw_ln.strip()
        if not ln.startswith(EXTRACTION_REUSE_PREFIX):
            continue
        raw_json = ln[len(EXTRACTION_REUSE_PREFIX) :].strip()
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict) and data:
            return data
    return None


def notes_begin_with_extraction_meta(notes: str | None) -> bool:
    if not notes or not str(notes).strip():
        return False
    return str(notes).split("\n", 1)[0].strip().startswith(EXTRACTION_META_PREFIX)


def split_proposition_notes(notes: str | None) -> ParsedPropositionNotes:
    """
    Parse ``notes`` into human text vs extraction metadata.

    Invalid metadata JSON preserves the original string in ``human_notes``.
    """
    raw = str(notes or "")
    if not raw.strip():
        return ParsedPropositionNotes(
            review_notes=None,
            human_notes="",
            extraction_meta=None,
            extraction_reuse=None,
            meta_parse_failed=False,
        )

    lines = raw.split("\n")
    first = lines[0].strip() if lines else ""
    reuse = parse_extraction_reuse(raw)

  # Strip reuse lines from human tail when splitting.
    human_lines: list[str] = []
    for ln in lines[1:]:
        stripped = ln.strip()
        if stripped.startswith(EXTRACTION_REUSE_PREFIX):
            continue
        human_lines.append(ln)
    human_tail = "\n".join(human_lines).strip()

    if not first.startswith(EXTRACTION_META_PREFIX):
        return ParsedPropositionNotes(
            review_notes=human_tail or raw.strip() or None,
            human_notes=raw.strip(),
            extraction_meta=None,
            extraction_reuse=reuse,
            meta_parse_failed=False,
        )

    meta_raw = first[len(EXTRACTION_META_PREFIX) :].strip()
    try:
        data = json.loads(meta_raw)
    except json.JSONDecodeError:
        return ParsedPropositionNotes(
            review_notes=None,
            human_notes=raw,
            extraction_meta=None,
            extraction_reuse=reuse,
            meta_parse_failed=True,
        )

    if not isinstance(data, dict):
        return ParsedPropositionNotes(
            review_notes=None,
            human_notes=raw,
            extraction_meta=None,
            extraction_reuse=reuse,
            meta_parse_failed=True,
        )

    review = human_tail or None
    return ParsedPropositionNotes(
        review_notes=review,
        human_notes=review or "",
        extraction_meta=data,
        extraction_reuse=reuse,
        meta_parse_failed=False,
    )


def resolve_extraction_meta_for_proposition(
    *,
    notes: str | None = None,
    extraction_debug_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Prefer structured ``extraction_debug_meta``; fall back to legacy ``notes`` line."""
    if isinstance(extraction_debug_meta, dict) and extraction_debug_meta:
        return dict(extraction_debug_meta)
    return parse_extraction_meta(notes)


def assign_proposition_extraction_reuse(proposition: Any, reuse: dict[str, Any]) -> None:
    """Record cross-source extraction reuse audit on the proposition (not human notes)."""
    dbg = dict(getattr(proposition, "extraction_debug_meta", None) or {})
    dbg["extraction_reuse"] = dict(reuse)
    proposition.extraction_debug_meta = dbg


def assign_proposition_extraction_debug(
    proposition: Any,
    meta: dict[str, Any],
    *,
    preserve_human_notes: bool = True,
) -> None:
    """Store debug metadata on the proposition and keep human text out of ``notes``."""
    full_meta = dict(meta)
    slim = slim_proposition_extraction_meta(full_meta)
    proposition.extraction_debug_meta = slim if slim else None

    existing_review = getattr(proposition, "review_notes", None)
    existing_notes = str(getattr(proposition, "notes", "") or "")

    human = ""
    if preserve_human_notes:
        if isinstance(existing_review, str) and existing_review.strip():
            human = existing_review.strip()
        elif existing_notes.strip() and not notes_begin_with_extraction_meta(existing_notes):
            human = existing_notes.strip()
        else:
            parsed = split_proposition_notes(existing_notes)
            if parsed.review_notes and not parsed.meta_parse_failed:
                human = parsed.review_notes.strip()

    proposition.review_notes = human or None
    proposition.notes = human


def attach_extraction_meta(base_notes: str, meta: dict[str, Any]) -> str:
    """
    Legacy: embed metadata in ``notes`` first line.

    Prefer ``assign_proposition_extraction_debug`` on :class:`Proposition` for new code.
    """
    line = f"{EXTRACTION_META_PREFIX}{json.dumps(meta, sort_keys=True)}"
    rest = (base_notes or "").strip()
    if rest:
        return f"{line}\n{rest}"
    return line


def attach_extraction_reuse(base_notes: str, reuse: dict[str, Any]) -> str:
    line = f"{EXTRACTION_REUSE_PREFIX}{json.dumps(reuse, sort_keys=True)}"
    rest = (base_notes or "").strip()
    if rest:
        return f"{rest}\n{line}"
    return line


def apply_notes_separation(model: Any) -> Any:
    """
    Migrate legacy ``notes`` embedding into ``review_notes`` + ``extraction_debug_meta``.

    Idempotent when fields are already separated.
    """
    notes = str(getattr(model, "notes", "") or "")
    existing_debug = getattr(model, "extraction_debug_meta", None)
    existing_review = getattr(model, "review_notes", None)

    if isinstance(existing_debug, dict) and existing_debug and not notes_begin_with_extraction_meta(notes):
        if existing_review is not None or not notes.strip():
            model.notes = str(existing_review or "").strip()
            return model

    parsed = split_proposition_notes(notes)

    if parsed.meta_parse_failed:
        model.review_notes = None
        model.notes = notes
        return model

    if isinstance(existing_debug, dict) and existing_debug:
        merged_meta = {**parsed.extraction_meta, **existing_debug} if parsed.extraction_meta else existing_debug
    else:
        merged_meta = parsed.extraction_meta

    if merged_meta:
        slimmed = slim_proposition_extraction_meta(merged_meta)
        model.extraction_debug_meta = slimmed if slimmed else None
    elif not getattr(model, "extraction_debug_meta", None):
        model.extraction_debug_meta = None

    if parsed.review_notes and str(parsed.review_notes).strip():
        model.review_notes = str(parsed.review_notes).strip()
    elif isinstance(existing_review, str) and existing_review.strip():
        model.review_notes = existing_review.strip()
    elif notes_begin_with_extraction_meta(notes) and not parsed.review_notes:
        model.review_notes = None
    else:
        model.review_notes = None

    human = model.review_notes if model.review_notes else ""
    model.notes = human if human else ""

    return model
