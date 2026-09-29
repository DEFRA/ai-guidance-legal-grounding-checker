"""Deterministic proposition completeness (standalone readability) heuristics."""

from __future__ import annotations

import re
from typing import Any, Sequence

from law_proposition_extractor_domain import (
    Proposition,
    PropositionCompletenessAssessment,
    PropositionExtractionTrace,
    SourceRecord,
)

_RE_OPERATIVE = re.compile(
    r"\b("
    r"shall|must|should|may|required to|prohibited|obliged|establish(?:es)?|maintaining|maintain|"
    r"ensure[sd]?|applies|apply|responsible|entitled|powers?|obligations?|requirements?"
    r")\b",
    re.I,
)

_RE_LIST_START = re.compile(
    r"^(\(?[a-z]\)|\(?[ivxlcdm]+\)|\d+[\).])\s+",
    re.I,
)

# Lowercase prefix → missing_context kinds (additive; keep narrow to reduce false positives).
_CONTEXT_PREFIX_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("this regulation", ("instrument_identity",)),
    ("this directive", ("instrument_identity",)),
    ("this decision", ("instrument_identity",)),
    ("this article", ("article_locator",)),
    ("this paragraph", ("article_locator",)),
    ("that database", ("object",)),
    ("those animals", ("object",)),
    ("these measures", ("object",)),
]


def _dump(p: Any) -> dict[str, Any]:
    if hasattr(p, "model_dump"):
        return p.model_dump(mode="json")
    return dict(p) if isinstance(p, dict) else {}


def _trace_by_proposition_id(
    traces: Sequence[PropositionExtractionTrace | dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in traces:
        d = _dump(raw)
        pid = str(d.get("proposition_id") or "").strip()
        if pid and pid not in out:
            out[pid] = d
    return out


def _sources_by_id(sources: Sequence[SourceRecord | dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in sources:
        d = _dump(raw)
        sid = str(d.get("id") or "").strip()
        if sid:
            out[sid] = d
    return out


def _instrument_label(source: dict[str, Any] | None) -> str | None:
    if not source:
        return None
    c = str(source.get("citation") or "").strip()
    if c:
        return c
    t = str(source.get("title") or "").strip()
    return t or None


def _replace_first_ci(text: str, needle: str, replacement: str) -> str:
    m = re.search(re.escape(needle), text, flags=re.IGNORECASE)
    if not m:
        return text
    return text[: m.start()] + replacement + text[m.end() :]


def _apply_instrument_phrases(text: str, label: str) -> str | None:
    t = text
    lower = t.lower()
    changed = False
    for phrase in ("This Regulation", "This Directive", "This Decision"):
        if phrase.lower() in lower:
            t = _replace_first_ci(t, phrase, label)
            lower = t.lower()
            changed = True
    return t if changed else None


def _apply_article_phrase(text: str, article_ref: str) -> str | None:
    if not text.lower().startswith("this article"):
        return None
    return _replace_first_ci(text, "This Article", article_ref.strip())


def _prefix_context(
    text: str,
) -> tuple[tuple[str, ...], str] | None:
    t = text.strip()
    if not t:
        return None
    lower = t.lower()
    for prefix, kinds in _CONTEXT_PREFIX_RULES:
        if lower.startswith(prefix):
            return kinds, prefix
    return None


def _fragmentary_crossref_dangling(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 120:
        return False
    if _RE_OPERATIVE.search(t):
        return False
    low = t.lower()
    if not any(k in low for k in ("article", "annex", "regulation", "directive", "§")):
        return False
    return True


def _fragmentary_list_bare(text: str, has_parent: bool) -> bool:
    if has_parent:
        return False
    t = text.strip()
    if len(t) >= 100:
        return False
    if not _RE_LIST_START.match(t):
        return False
    return not bool(_RE_OPERATIVE.search(t))


def _fragmentary_short_inert(text: str, has_parent: bool) -> bool:
    if has_parent:
        return False
    t = text.strip()
    if len(t) >= 80:
        return False
    return not bool(_RE_OPERATIVE.search(t))


def _confidence_for(
    status: str,
    *,
    suggested: str | None,
    operative: bool,
    text_len: int,
) -> str:
    if status == "fragmentary":
        return "low"
    if status == "context_dependent":
        return "medium" if suggested else "low"
    if operative and text_len > 40:
        return "high"
    return "medium"


def _assess_one(
    proposition: dict[str, Any],
    trace: dict[str, Any] | None,
    source: dict[str, Any] | None,
) -> PropositionCompletenessAssessment:
    pid = str(proposition.get("id") or "").strip()
    pkey = proposition.get("proposition_key")
    pkey_s = str(pkey).strip() if pkey not in (None, "") else None
    text = str(proposition.get("proposition_text") or "")
    stripped = text.strip()
    frag_loc = str(proposition.get("fragment_locator") or "")
    article_ref = str(proposition.get("article_reference") or "").strip()

    signals: dict[str, Any] = {"text_char_length": len(stripped)}
    trace_signals: dict[str, Any] = {}
    if trace and isinstance(trace.get("signals"), dict):
        trace_signals = dict(trace["signals"])

    parent_ctx_raw = trace_signals.get("parent_context")
    parent_ctx = str(parent_ctx_raw).strip() if parent_ctx_raw not in (None, "") else ""
    has_parent = bool(parent_ctx)
    list_marker = trace_signals.get("list_marker")
    composition_basis = str(trace_signals.get("composition_basis") or "").strip()
    structured_list = (
        bool(list_marker)
        or ":list:" in frag_loc.lower()
        or composition_basis == "structured_list_leaf"
    )
    if has_parent:
        signals["extraction.parent_context_present"] = True
    if structured_list:
        signals["extraction.structured_list"] = True

    evidence: list[str] = []
    missing: list[str] = []
    status: str = "complete"
    reason = "Readable as a standalone extracted proposition (no deictic opener; operative language present)."
    suggested: str | None = None
    injections: dict[str, Any] = {}
    operative = bool(_RE_OPERATIVE.search(stripped))

    if not stripped:
        status = "fragmentary"
        reason = "Empty proposition text."
        missing = ["object"]
        evidence.append("proposition.proposition_text empty")
        signals["rule"] = "empty_text"
    elif _fragmentary_crossref_dangling(stripped):
        status = "fragmentary"
        reason = "Text relies on a legal anchor cross-reference without standalone operative language."
        missing = ["cross_reference"]
        evidence.append("cross_reference_only_heuristic")
        signals["rule"] = "cross_reference_dangling"
    elif _fragmentary_list_bare(stripped, has_parent):
        status = "fragmentary"
        reason = "List-style fragment without operative language and no parent context in extraction trace."
        missing = ["object"]
        evidence.append("list_marker_without_operative")
        signals["rule"] = "list_marker_bare"
    elif _fragmentary_short_inert(stripped, has_parent):
        status = "fragmentary"
        reason = "Very short text with no operative language and no parent context in extraction trace."
        missing = ["actor", "object"]
        evidence.append("short_text_no_operative")
        signals["rule"] = "short_inert"
    else:
        prefix_hit = _prefix_context(stripped)
        if prefix_hit:
            kinds, prefix = prefix_hit
            status = "context_dependent"
            missing = list(dict.fromkeys((*missing, *kinds)))
            reason = f"Deictic source reference at start ({prefix!r}) — needs injected context for standalone reading."
            evidence.append(f"proposition_text.prefix:{prefix}")
            signals["rule"] = "deictic_prefix"
            label = _instrument_label(source)
            if "instrument_identity" in kinds and label:
                inst_suggested = _apply_instrument_phrases(stripped, label)
                if inst_suggested:
                    suggested = inst_suggested
                    injections["instrument_identity"] = label
                    evidence.append("suggested_display.instrument_replacement")
            if kinds == ("article_locator",) and article_ref:
                art_suggested = _apply_article_phrase(stripped, article_ref)
                if art_suggested:
                    suggested = art_suggested
                    injections["article_locator"] = article_ref
                    evidence.append("suggested_display.article_reference_replacement")
        elif has_parent and structured_list:
            status = "complete"
            reason = (
                "Structured list item with parent context captured in extraction trace — reads as a full operative clause."
            )
            evidence.append("extraction_trace.signals.parent_context")
            signals["rule"] = "structured_list_parent_ok"

    conf = _confidence_for(status, suggested=suggested, operative=operative, text_len=len(stripped))
    if has_parent and parent_ctx:
        injections.setdefault("parent_context_excerpt", parent_ctx[:500])

    return PropositionCompletenessAssessment(
        id=f"pca-{pid}" if pid else "pca-unknown",
        proposition_id=pid,
        proposition_key=pkey_s,
        status=status,  # type: ignore[arg-type]
        confidence=conf,  # type: ignore[arg-type]
        reason=reason,
        missing_context=missing,
        suggested_display_statement=suggested,
        context_injections=injections,
        evidence=evidence,
        method="deterministic",
        signals=signals,
    )


def build_proposition_completeness_assessments(
    *,
    propositions: Sequence[Proposition | dict[str, Any]],
    proposition_extraction_traces: Sequence[PropositionExtractionTrace | dict[str, Any]],
    source_records: Sequence[SourceRecord | dict[str, Any]],
) -> list[PropositionCompletenessAssessment]:
    traces_map = _trace_by_proposition_id(proposition_extraction_traces)
    src_map = _sources_by_id(source_records)
    out: list[PropositionCompletenessAssessment] = []
    for raw in propositions:
        p = _dump(raw)
        pid = str(p.get("id") or "").strip()
        sid = str(p.get("source_record_id") or "").strip()
        out.append(
            _assess_one(
                p,
                traces_map.get(pid),
                src_map.get(sid),
            )
        )
    return out
