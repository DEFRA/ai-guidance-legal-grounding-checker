from __future__ import annotations

import json
import math
import re
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from law_proposition_extractor_domain import Cluster, Proposition, ReviewStatus, SourceRecord, Topic
from law_proposition_extractor_llm import JuditLLMClient
from law_proposition_extractor_llm.client import TextCompletionResult

from .derived_cache import DerivedArtifactCache, build_proposition_extraction_chunk_cache_key


def _source_authority_cache_identity(source: SourceRecord) -> tuple[str, str]:
    """Resolve authority + ASID for chunk-cache keys (stable across Law Discovery lex-* remints)."""
    meta = source.metadata if isinstance(source.metadata, dict) else {}
    authority = str(meta.get("authority") or source.provenance or "unknown").strip() or "unknown"
    asid = str(meta.get("authority_source_id") or source.id).strip() or source.id
    return authority, asid
from .extraction_empty_failure import (
    EXTRACTION_SCHEMA_VIOLATION,
    POST_FILTER_REMOVED_ALL,
    build_empty_extraction_retry_prompt_suffix,
    build_llm_failure_trace_fields,
    classify_empty_extraction_outcome,
    is_empty_extraction_retry_eligible,
    parse_model_propositions_container,
)
from .extraction_output_mode import (
    ExtractionOutputMode,
    ExtractionOutputModeRejectedError,
    ExtractionOutputModeUnsupportedError,
    V2_EXTRACTION_JSON_SCHEMA,
    build_litellm_json_schema_wrapper,
    build_response_format_for_mode,
    ensure_output_mode_supported,
    fallback_output_mode,
    is_output_mode_rejection_error,
    output_mode_trace_fields,
    resolve_extraction_output_mode,
    validate_parsed_extraction_schema,
)
from .dependent_qualification import reconcile_dependent_qualification_rows
from .intake import content_hash, slugify
from .repealed_provisions import is_repealed_or_empty_fragment
from .structured_list_decomposition import (
    COMPOSITION_BASIS,
    draft_structured_list_leaves,
    fold_exceptions_for_row,
    StructuredListIdentityContext,
    merge_structured_leaf_rows,
    rows_include_standalone_derogation,
)


def _proposition_id_stem(source: SourceRecord) -> str:
    stem = slugify(source.id)
    if isinstance(source.metadata, dict):
        fid = source.metadata.get("extraction_fragment_id")
        if fid:
            stem = f"{stem}-{slugify(str(fid))}"
    return stem


_TRIGGER_WORDS = ("must", "shall", "may", "required", "prohibited", "must not", "shall not")

# Structured list rows prepend this header before JSON extraction metadata on ``notes``.
STRUCTURED_NOTE_PREFIX = "heuristic extraction:structured_list"

STRUCTURED_LIST_RULE_ID = "extract.heuristic.structured_list_items"

EXTRACTION_SCHEMA_VERSION_V2 = "v2"
EXTRACTION_PROMPT_VERSION_V2 = "v2"
# v3: adds labelled non-operative structural heading context (legislative headings).
EXTRACTION_PROMPT_VERSION_V3 = "v3"
EXTRACTION_PROMPT_VERSION = EXTRACTION_PROMPT_VERSION_V3
from law_proposition_extractor_domain.proposition_notes import (
    EXTRACTION_META_PREFIX,
    EXTRACTION_REUSE_PREFIX,
    assign_proposition_extraction_debug,
    assign_proposition_extraction_reuse,
    attach_extraction_meta,
    attach_extraction_reuse,
    parse_extraction_meta,
    parse_extraction_reuse,
    resolve_extraction_meta_for_proposition,
    slim_proposition_extraction_meta,
    split_proposition_notes,
)

_TRACE_ONLY_PIPELINE_META_KEYS = frozenset(
    {
        "extraction_llm_call_traces",
        "pipeline_evidence_issue_records",
    }
)

_PROVISION_TYPES_V2 = frozenset(
    {"core", "definition", "exception", "transitional", "cross_reference"}
)
_COMPLETENESS_V2 = frozenset({"complete", "context_dependent", "fragmentary"})

_V2_SYSTEM_PROMPT = "You extract legal propositions as strict JSON only."

# Unique marker embedded in local-mode prompts (tests assert presence).
LOCAL_FEWSHOT_PROMPT_MARKER = "[LOCAL_FEWSHOT_V1]"


def local_few_shot_prompt_used(extraction_mode: Literal["frontier", "local"] | str) -> bool:
    """True when v2 extraction prompts include the local few-shot worked example."""
    return extraction_mode == "local"


def _local_few_shot_block() -> str:
    """Compact worked example for local LLMs (citation / commencement / application)."""
    valid_json = (
        '{"propositions":[{"proposition_text":"These Regulations may be cited as the Example '
        'Regulations 2026.","display_label":"Citation","subject":"These Regulations","rule":"may be '
        'cited as","object":"the Example Regulations 2026","conditions":[],"exceptions":[],'
        '"temporal_condition":"","provision_type":"core","source_locator":"regulation:1",'
        '"evidence_text":"These Regulations may be cited as the Example Regulations 2026.",'
        '"completeness_status":"complete","confidence":"high","reason":"The fragment states the '
        'short title/citation of the instrument."},{"proposition_text":"These Regulations come '
        'into force on 1 May 2026.","display_label":"Commencement","subject":"These Regulations",'
        '"rule":"come into force on","object":"1 May 2026","conditions":[],"exceptions":[],'
        '"temporal_condition":"1 May 2026","provision_type":"transitional","source_locator":'
        '"regulation:1","evidence_text":"These Regulations come into force on 1 May 2026.",'
        '"completeness_status":"complete","confidence":"high","reason":"The fragment states the '
        'commencement date."},{"proposition_text":"These Regulations apply in relation to England '
        'only.","display_label":"Territorial application","subject":"These Regulations","rule":'
        '"apply in relation to","object":"England only","conditions":[],"exceptions":[],'
        '"temporal_condition":"","provision_type":"core","source_locator":"regulation:1",'
        '"evidence_text":"These Regulations apply in relation to England only.",'
        '"completeness_status":"complete","confidence":"high","reason":"The fragment states the '
        'territorial application of the instrument."}]}'
    )
    return f"""
{LOCAL_FEWSHOT_PROMPT_MARKER}
Worked example (local mode — match this JSON shape on the real fragment below):

INVALID outputs (never return these): {{}} | {{"propositions":null}} | prose outside JSON

Guidance:
- For ordinary statutory provisions, returning no propositions is unusual.
- If the text states citation, commencement, territorial extent, application, duty, prohibition, power, definition, exception, or cross-reference, extract at least one proposition.
- Only return "propositions":[] when the fragment is genuinely non-substantive; include top-level "empty_rationale".

SOURCE TEXT:
1 These Regulations may be cited as the Example Regulations 2026.
2 These Regulations come into force on 1 May 2026.
3 These Regulations apply in relation to England only.

VALID JSON:
{valid_json}

Now extract from the following real fragment.
""".strip()


def estimate_llm_input_tokens(*, prompt: str, system_prompt: str | None = None) -> int:
    """Conservative token estimate for context-window budgeting (over-estimates vs typical ~4 chars/token)."""
    joined = (prompt or "") + "\n" + (system_prompt or "")
    return max(1, math.ceil(len(joined) / 3.0))


_RE_ARTICLE_HEADING_LINE = re.compile(
    r"(?m)^(Article\s+\d+[a-z]?\b[^\n]*)$",
    re.IGNORECASE,
)
_RE_SECTION_HEADING_LINE = re.compile(
    r"(?m)^(Section\s+\d+[.:]?\s*[^\n]*)$",
    re.IGNORECASE,
)


@dataclass
class ExtractSourceResult:
    propositions: list[Proposition]
    extraction_mode: str
    model_alias: str | None
    fallback_policy: str
    fallback_used: bool
    validation_errors: list[str]
    prompt_version: str
    schema_version: str
    failed_closed: bool = False
    failure_reason: str | None = None
    validation_issue_records: list[dict[str, Any]] = field(default_factory=list)
    extraction_llm_call_traces: list[dict[str, Any]] = field(default_factory=list)
    repairable_extraction_halt: bool = False
    repairable_extraction_halt_reason: str | None = None
    fallback_strategy: str | None = None
    structured_list_decision_facts: list[dict[str, Any]] = field(default_factory=list)
    dependent_qualification_decision_facts: list[dict[str, Any]] = field(
        default_factory=list
    )


def _looks_like_infra_llm_failure(message: str) -> bool:
    """Heuristic infra/provider failures — used for ``stop_repairable`` extraction policy."""
    blob = message.lower()
    if not blob.strip():
        return False
    keys = (
        "credit",
        "quota",
        "429",
        "rate limit",
        "ratelimit",
        "context length",
        "context window",
        "token limit",
        "max_tokens",
        "too large",
        "model",
        "overloaded",
        "unavailable",
        "api_error",
        "api error",
    )
    return any(k in blob for k in keys)


def extract_propositions(
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    llm_client: JuditLLMClient | None = None,
    limit: int = 3,
) -> list[Proposition]:
    """Legacy helper for unit tests and demos.

    Production / CLI runs use :func:`extract_propositions_from_source` (v2 schema, frontier/local/heuristic).
    """
    if llm_client and source.authoritative_text.strip():
        llm_result = _legacy_try_llm_extraction_pre_v2(
            source=source,
            topic=topic,
            cluster=cluster,
            llm_client=llm_client,
        )
        if llm_result:
            return llm_result[:limit]

    return _heuristic_extraction(source=source, topic=topic, cluster=cluster, limit=limit)


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split()).strip()


_RE_DEFINITION_HEADER = re.compile(
    r"\b(?:for\s+the\s+purposes\s+of\s+this\s+(?:regulation|directive|decision|act)[^.:;\n]{0,200}\b)?"
    r"the\s+following\s+definitions\s+shall\s+apply\b",
    re.IGNORECASE,
)
_RE_QUOTED_TERM = re.compile(r"[\"'‘’“”]([^\"'‘’“”]{1,180})[\"'‘’“”]")
_RE_DEFINITION_ENTRY = re.compile(
    r"(?is)(?P<term>"
    r"(?:[\"'‘’“”][^\"'‘’“”]{1,180}[\"'‘’“”](?:\s+or\s+[\"'‘’“”][^\"'‘’“”]{1,180}[\"'‘’“”]){0,3})"
    r")\s+(?P<verb>means|shall\s+mean)\b"
)
_PRIORITY_DEFINITION_TERMS: tuple[str, ...] = (
    "equidae",
    "equine animal",
    "holding",
    "keeper",
    "owner",
    "registered equidae",
    "equidae for breeding and production",
    "equidae for slaughter",
    "competent authority",
    "transponder",
    "unique life number",
    "mark",
    "smart card",
    "veterinarian responsible",
    "official veterinarian",
    "appropriate authority",
)


def _normalize_definition_term_key(term: str) -> str:
    lowered = term.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _is_definition_provision(text: str) -> bool:
    body = text.strip()
    if not body:
        return False
    if _RE_DEFINITION_HEADER.search(body):
        return True
    if re.search(r"(?i)\bshall\s+mean\b", body):
        return True
    if re.search(r"(?i)\bmeans\b", body) and _RE_QUOTED_TERM.search(body):
        return True
    return False


def _definition_term_display(term_blob: str) -> str:
    terms = [m.group(1).strip() for m in _RE_QUOTED_TERM.finditer(term_blob) if m.group(1).strip()]
    if not terms:
        return _normalize_whitespace(term_blob.strip(" ,.;:"))
    uniq: list[str] = []
    seen: set[str] = set()
    for t in terms:
        key = _normalize_definition_term_key(t)
        if key and key not in seen:
            seen.add(key)
            uniq.append(t)
    if not uniq:
        return _normalize_whitespace(term_blob.strip(" ,.;:"))
    if len(uniq) == 1:
        return uniq[0]
    return " / ".join(uniq)


def _definition_priority_rank(term_display: str) -> int:
    key = _normalize_definition_term_key(term_display)
    if not key:
        return len(_PRIORITY_DEFINITION_TERMS) + 100
    for idx, target in enumerate(_PRIORITY_DEFINITION_TERMS):
        tkey = _normalize_definition_term_key(target)
        if not tkey:
            continue
        if tkey in key or key in tkey:
            return idx
    return len(_PRIORITY_DEFINITION_TERMS) + 50


def _definition_fallback_extraction(
    *,
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    limit: int,
) -> tuple[list[Proposition], list[dict[str, Any]], list[str]]:
    text = source.authoritative_text or ""
    if not _is_definition_provision(text):
        return [], [], []
    matches = list(_RE_DEFINITION_ENTRY.finditer(text))
    if not matches:
        return [], [], []

    article_reference = _extract_reference_from_locator(source.authoritative_locator) or _extract_article_reference(
        text
    )
    if not article_reference:
        article_reference = "Article 2"
    m_art = re.match(r"(?i)^article\s+(\d+[a-z]?)$", article_reference.strip())
    if m_art:
        article_reference = f"Article {m_art.group(1)}"

    candidates: list[tuple[int, int, Proposition, dict[str, Any], str]] = []
    for idx, match in enumerate(matches):
        start = match.start("term")
        end = matches[idx + 1].start("term") if idx + 1 < len(matches) else len(text)
        span_raw = text[start:end]
        span = span_raw.strip()
        if not span:
            continue

        term_display = _definition_term_display(match.group("term"))
        if not term_display:
            continue
        verb = _normalize_whitespace(match.group("verb").lower())
        local_verb_index = span.lower().find(verb)
        if local_verb_index == -1:
            continue
        definition_tail = span[local_verb_index + len(verb) :].strip(" \n\t:;.")
        if not definition_tail:
            continue

        evidence_text = span
        ok, strategy, _diag = evidence_locates_verbatim_after_normalisation(evidence_text, text)
        confidence: Literal["high", "medium", "low"]
        if ok:
            confidence = "high"
        else:
            confidence = "medium"
        review_status = ReviewStatus.PROPOSED if confidence == "high" else ReviewStatus.NEEDS_REVIEW
        label = f"Definition — “{term_display}”"
        proposition_text = f"{term_display} means {definition_tail}"
        priority = _definition_priority_rank(term_display)

        proposition = Proposition(
            id="",
            proposition_key="",
            topic_id=topic.id,
            cluster_id=cluster.id,
            source_record_id=source.id,
            source_fragment_id=None,
            fragment_locator=source.authoritative_locator,
            source_snapshot_id=source.current_snapshot_id,
            jurisdiction=source.jurisdiction,
            article_reference=article_reference,
            proposition_text=proposition_text,
            label=label,
            short_name=label[:200],
            legal_subject=term_display,
            action="means" if "mean" in verb else "defines",
            conditions=[],
            authority=_guess_authority(definition_tail),
            required_documents=_guess_required_documents(definition_tail),
            affected_subjects=[term_display],
            notes="deterministic definition fallback extraction",
            review_status=review_status,
        )
        extra_meta: dict[str, Any] = {
            "provision_type": "definition",
            "completeness_status": "complete",
            "model_confidence": confidence,
            "evidence_quote": evidence_text,
            "evidence_match_strategy": strategy,
            "trace_warnings": [] if confidence == "high" else ["definition_evidence_requires_review"],
        }
        candidates.append((priority, idx, proposition, extra_meta, confidence))

    candidates.sort(key=lambda item: (item[0], item[1]))
    picked = candidates[: max(1, limit)]
    out_props: list[Proposition] = []
    out_meta: list[dict[str, Any]] = []
    warnings: list[str] = []
    slug_base = slugify(source.id.strip())
    for seq, (_prio, _idx, prop, meta, confidence) in enumerate(picked, start=1):
        term_slug = slugify(prop.legal_subject) or f"definition-{seq:03d}"
        prop.id = f"prop-{_proposition_id_stem(source)}-{seq:03d}"
        prop.proposition_key = f"{slug_base}:{term_slug}:p{seq:03d}"
        out_props.append(prop)
        out_meta.append(meta)
        if confidence != "high":
            warnings.append(f"definition_fallback_medium_confidence:{prop.legal_subject}")
    return out_props, out_meta, warnings


def _is_placeholder_locator(locator: str | None) -> bool:
    if locator is None:
        return True
    return locator.strip().lower() in {"", "document:full", "full", "document"}


def _extract_source_fragments(source: SourceRecord) -> list[tuple[str, str]]:
    lines = [line.strip() for line in source.authoritative_text.splitlines() if line.strip()]
    if not lines and source.authoritative_text.strip():
        lines = [source.authoritative_text.strip()]
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    locators_raw = metadata.get("fragment_locators")
    locators = (
        [str(item) for item in locators_raw if str(item).strip()]
        if isinstance(locators_raw, list)
        else []
    )
    default_locator = source.authoritative_locator or "document:full"

    if not lines:
        return [(default_locator, "No source text provided.")]
    if len(locators) == len(lines):
        return list(zip(locators, lines, strict=False))
    if len(locators) == 1:
        # One locator for the whole instrument fragment (e.g. entire article) — keep full text together
        # so structured list / multi-sentence parsing sees list markers and continuations.
        merged = "\n".join(lines)
        return [(locators[0], merged)]
    if not locators:
        merged = "\n".join(lines)
        return [(default_locator, merged)]
    return [(default_locator, line) for line in lines]


def _split_by_article_or_section_headings(text: str, base_locator: str) -> list[tuple[str, str]] | None:
    """Split consolidated instruments on Article/Section headings when clearly delineated."""
    stripped = text.strip()
    if not stripped:
        return None
    matches = list(_RE_ARTICLE_HEADING_LINE.finditer(stripped))
    if len(matches) < 2:
        matches = list(_RE_SECTION_HEADING_LINE.finditer(stripped))
    if len(matches) < 2:
        return None
    parts: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(stripped)
        heading = m.group(1).strip()
        body = stripped[start:end].strip()
        if not body:
            continue
        slug = re.sub(r"\s+", "_", heading[:96])
        loc_base = base_locator if not _is_placeholder_locator(base_locator) else heading
        parts.append((f"{loc_base}|{slug}", body))
    return parts if len(parts) >= 2 else None


def _hard_split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    t = text.strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]
    out: list[str] = []
    ov = max(0, overlap_chars)
    step = max(256, max_chars - ov) if max_chars > ov else max_chars
    i = 0
    while i < len(t):
        out.append(t[i : i + max_chars])
        i += step
    return out


def _split_paragraph_overlap_chunks(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    if not paras:
        return [text.strip()] if text.strip() else []
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0
    ov = max(0, overlap_chars)

    def flush() -> None:
        nonlocal current_parts, current_len
        if not current_parts:
            return
        piece = "\n\n".join(current_parts)
        chunks.append(piece)
        current_parts = []
        current_len = 0
        if ov > 0 and len(piece) > ov:
            tail = piece[-ov:].strip()
            if tail:
                current_parts.append(tail)
                current_len = len(tail)

    for p in paras:
        if len(p) > max_chars:
            flush()
            chunks.extend(_hard_split_text(p, max_chars, ov))
            continue
        sep_len = 2 if current_parts else 0
        projected = current_len + sep_len + len(p)
        if current_parts and projected > max_chars:
            flush()
            sep_len = 2 if current_parts else 0
            projected = current_len + sep_len + len(p)
        current_parts.append(p)
        current_len = projected

    flush()
    return chunks


MAX_ANTHROPIC_BATCH_CUSTOM_ID_LENGTH = 64


def planned_extraction_request_id(
    *,
    source_id: str,
    frag_id: str | None,
    chunk_index: int,
    prompt_fingerprint: str,
) -> str:
    """Stable request id for batch custom_id (Anthropic max 64 chars)."""
    material = f"{source_id}|{frag_id or 'full'}|{chunk_index}|{prompt_fingerprint}"
    digest = content_hash(material)[:48]
    return f"pex-{digest}"


@dataclass(frozen=True)
class _PlannedExtractChunk:
    locator: str
    text: str
    split_strategy: str


@dataclass(frozen=True)
class PlannedExtractionRequest:
    request_id: str
    source_record_id: str
    source_snapshot_id: str | None
    source_fragment_id: str | None
    source_fragment_locator: str | None
    fragment_locator: str
    source_title: str
    model_alias: str
    prompt_version: str
    schema_version: str
    prompt_text: str
    system_text: str | None
    estimated_input_tokens: int
    cache_key: str | None
    focus_scopes: list[str]
    max_propositions_per_source: int
    metadata: dict[str, Any]


def _plan_llm_text_chunks(
    source: SourceRecord,
    *,
    max_body_chars: int,
    overlap_chars: int,
) -> list[_PlannedExtractChunk]:
    overlap_chars = max(0, overlap_chars)
    max_body_chars = max(512, max_body_chars)
    planned: list[_PlannedExtractChunk] = []
    for locator, fragment_text in _extract_source_fragments(source):
        ft = fragment_text.strip()
        if not ft:
            continue
        base_loc = locator if locator.strip() else (source.authoritative_locator or "document:full")
        if len(ft) <= max_body_chars:
            planned.append(_PlannedExtractChunk(locator=base_loc, text=ft, split_strategy="metadata_fragment"))
            continue
        headed = _split_by_article_or_section_headings(ft, base_loc)
        if headed:
            for loc_h, body_h in headed:
                if len(body_h) <= max_body_chars:
                    planned.append(_PlannedExtractChunk(locator=loc_h, text=body_h, split_strategy="article_heading"))
                else:
                    for piece in _split_paragraph_overlap_chunks(body_h, max_body_chars, overlap_chars):
                        planned.append(
                            _PlannedExtractChunk(locator=loc_h, text=piece, split_strategy="paragraph_overlap")
                        )
            continue
        for piece in _split_paragraph_overlap_chunks(ft, max_body_chars, overlap_chars):
            planned.append(_PlannedExtractChunk(locator=base_loc, text=piece, split_strategy="paragraph_overlap"))
    return planned


def plan_frontier_extraction_requests(
    *,
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    model_alias: str,
    max_propositions: int,
    focus_scopes: Sequence[str] | None = None,
    prompt_version: str = EXTRACTION_PROMPT_VERSION_V2,
    schema_version: str = EXTRACTION_SCHEMA_VERSION_V2,
    max_input_tokens: int = 150_000,
    extract_model_context_limit: int = 200_000,
    derived_chunk_cache: DerivedArtifactCache | None = None,
    chunk_cache_pipeline_version: str = "0.1.0",
    chunk_cache_strategy_version: str = "v1",
    include_cached_successes: bool = False,
) -> list[PlannedExtractionRequest]:
    """Plan frontier extraction prompts without invoking the LLM."""
    full_body = source.authoritative_text.strip()
    if not full_body:
        return []
    overlap_chars = min(8192, max(512, int(max_input_tokens) // 40))
    initial_est = _estimate_extract_prompt_tokens(
        source=source,
        topic=topic,
        cluster=cluster,
        extraction_mode="frontier",
        max_propositions=max_propositions,
        focus_scopes=focus_scopes,
        prompt_source_text=full_body,
        fragment_locator_hint=None,
    )
    if initial_est <= max_input_tokens:
        planned_chunks = [
            _PlannedExtractChunk(
                locator=source.authoritative_locator or "document:full",
                text=full_body,
                split_strategy="single",
            )
        ]
    else:
        max_body_chars = _max_body_chars_for_extract_budget(
            source=source,
            topic=topic,
            cluster=cluster,
            extraction_mode="frontier",
            max_propositions=max_propositions,
            focus_scopes=focus_scopes,
            token_budget=max_input_tokens,
        )
        planned_chunks = _plan_llm_text_chunks(
            source,
            max_body_chars=max_body_chars,
            overlap_chars=overlap_chars,
        )
    scopes_tuple = tuple(sorted(str(s).strip() for s in (focus_scopes or ()) if str(s).strip()))
    frag_id = None
    if isinstance(source.metadata, dict) and source.metadata.get("extraction_fragment_id") is not None:
        frag_id = str(source.metadata.get("extraction_fragment_id"))
    source_snapshot_id = str(source.current_snapshot_id).strip() if source.current_snapshot_id else None
    out: list[PlannedExtractionRequest] = []
    for ci, planned in enumerate(planned_chunks, start=1):
        fitted = _fit_body_text_to_extract_budget(
            body=planned.text,
            source=source,
            topic=topic,
            cluster=cluster,
            extraction_mode="frontier",
            max_propositions=max_propositions,
            focus_scopes=focus_scopes,
            fragment_locator_hint=planned.locator,
            max_input_tokens=max_input_tokens,
        )
        if fitted is None:
            continue
        chunk_text, chunk_est = fitted
        prompt = _v2_model_prompt(
            source,
            topic,
            cluster,
            extraction_mode="frontier",
            max_propositions=max_propositions,
            focus_scopes=focus_scopes,
            prompt_source_text=chunk_text,
            fragment_locator_hint=planned.locator,
        )
        chunk_fp = content_hash(chunk_text)[:48]
        cache_key: str | None = None
        if model_alias:
            authority, authority_source_id = _source_authority_cache_identity(source)
            cache_key = build_proposition_extraction_chunk_cache_key(
                authority=authority,
                authority_source_id=authority_source_id,
                source_fragment_locator=planned.locator,
                chunk_index=ci,
                chunk_body_fingerprint=chunk_fp,
                model_alias=str(model_alias),
                extraction_mode="frontier",
                prompt_version=prompt_version,
                focus_scopes=scopes_tuple,
                max_propositions=max_propositions,
                pipeline_version=chunk_cache_pipeline_version,
                strategy_version=chunk_cache_strategy_version,
            )
        if cache_key and derived_chunk_cache is not None and not include_cached_successes:
            cached_hit = derived_chunk_cache.get(
                stage_name="proposition_extraction_chunk", cache_key=cache_key
            )
            if cached_hit is not None and isinstance(cached_hit.payload, dict):
                if cached_hit.payload.get("chunk_status") == "llm_success":
                    vr = cached_hit.payload.get("validated_rows")
                    if isinstance(vr, list) and vr:
                        continue
        request_id = planned_extraction_request_id(
            source_id=source.id,
            frag_id=frag_id,
            chunk_index=ci,
            prompt_fingerprint=content_hash(prompt)[:16],
        )
        out.append(
            PlannedExtractionRequest(
                request_id=request_id,
                source_record_id=source.id,
                source_snapshot_id=source_snapshot_id,
                source_fragment_id=frag_id,
                source_fragment_locator=source.authoritative_locator,
                fragment_locator=planned.locator,
                source_title=source.title,
                model_alias=model_alias,
                prompt_version=prompt_version,
                schema_version=schema_version,
                prompt_text=prompt,
                system_text=_V2_SYSTEM_PROMPT,
                estimated_input_tokens=chunk_est,
                cache_key=cache_key,
                focus_scopes=list(scopes_tuple),
                max_propositions_per_source=max_propositions,
                metadata={
                    "extraction_mode": "frontier",
                    "configured_context_limit": int(extract_model_context_limit),
                    "max_extract_input_tokens": int(max_input_tokens),
                    "chunk_index": ci,
                    "chunk_total": len(planned_chunks),
                    "split_strategy": planned.split_strategy,
                    "chunk_body_fingerprint": chunk_fp,
                },
            )
        )
    return out


def _estimate_extract_prompt_tokens(
    *,
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    extraction_mode: Literal["frontier", "local"],
    max_propositions: int,
    focus_scopes: Sequence[str] | None,
    prompt_source_text: str,
    fragment_locator_hint: str | None,
) -> int:
    prompt = _v2_model_prompt(
        source,
        topic,
        cluster,
        extraction_mode=extraction_mode,
        max_propositions=max_propositions,
        focus_scopes=focus_scopes,
        prompt_source_text=prompt_source_text,
        fragment_locator_hint=fragment_locator_hint,
    )
    return estimate_llm_input_tokens(prompt=prompt, system_prompt=_V2_SYSTEM_PROMPT)


def _max_body_chars_for_extract_budget(
    *,
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    extraction_mode: Literal["frontier", "local"],
    max_propositions: int,
    focus_scopes: Sequence[str] | None,
    token_budget: int,
    safety_margin_tokens: int = 2048,
) -> int:
    """Derive max source-text characters per chunk from conservative token budget."""
    avail = max(256, token_budget - safety_margin_tokens)
    probe_body = "."
    overhead = _estimate_extract_prompt_tokens(
        source=source,
        topic=topic,
        cluster=cluster,
        extraction_mode=extraction_mode,
        max_propositions=max_propositions,
        focus_scopes=focus_scopes,
        prompt_source_text=probe_body,
        fragment_locator_hint=None,
    )
    body_token_budget = max(128, avail - overhead)
    # Prompt tokens scale ~len/3 for body; invert conservatively.
    return max(512, int(body_token_budget * 3))


def _merge_dedupe_validated_v2_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for item in rows:
        ptxt = str(item.get("proposition_text") or "").strip()
        loc_raw = str(item.get("source_locator") or "").strip()
        key = (_normalize_proposition_comparison(ptxt), loc_raw.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _fit_body_text_to_extract_budget(
    *,
    body: str,
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    extraction_mode: Literal["frontier", "local"],
    max_propositions: int,
    focus_scopes: Sequence[str] | None,
    fragment_locator_hint: str | None,
    max_input_tokens: int,
) -> tuple[str, int] | None:
    chunk_text = body.strip()
    if not chunk_text:
        return None
    while True:
        est = _estimate_extract_prompt_tokens(
            source=source,
            topic=topic,
            cluster=cluster,
            extraction_mode=extraction_mode,
            max_propositions=max_propositions,
            focus_scopes=focus_scopes,
            prompt_source_text=chunk_text,
            fragment_locator_hint=fragment_locator_hint,
        )
        if est <= max_input_tokens:
            return chunk_text, est
        if len(chunk_text) <= 400:
            return None
        chunk_text = chunk_text[: max(len(chunk_text) * 2 // 3, 400)]


def _split_fragment_sentences(fragment_text: str) -> list[str]:
    normalized = _normalize_whitespace(fragment_text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?;])\s+(?=(?:\(?[a-z0-9ivx]+\)|[A-Z]))", normalized)
    cleaned = [_normalize_whitespace(part.strip(" ;")) for part in parts if part.strip(" ;")]
    return cleaned or [normalized]


def _build_sentence_candidates(source: SourceRecord) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for locator, fragment_text in _extract_source_fragments(source):
        for sentence in _split_fragment_sentences(fragment_text):
            candidates.append((locator, sentence))
    return candidates


def _is_operative_locator(locator: str | None) -> bool:
    if not locator:
        return False
    lowered = locator.lower()
    if any(marker in lowered for marker in ("introduction", "preamble", "recital", "note")):
        return False
    return any(
        marker in lowered
        for marker in (
            "article",
            "section",
            "regulation",
            "paragraph",
            "schedule",
            "chapter",
            "part",
        )
    )


def _legacy_try_llm_extraction_pre_v2(
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    llm_client: JuditLLMClient,
) -> list[Proposition]:
    """DEPRECATED pre-v2 extraction prompt (ad-hoc JSON shape, ``local_extract_model`` only).

    Not used by ``extract_propositions_from_source`` / frontier or local quality extraction — those use
    :func:`_v2_model_prompt` and schema validation. Retained for :func:`extract_propositions` tests only.
    """
    prompt = f"""
Extract legal propositions from this source (at most a handful per call).

Return JSON only with this shape:
{{
  "propositions": [
    {{
      "article_reference": "optional string",
      "proposition_text": "string",
      "legal_subject": "string",
      "action": "string",
      "conditions": ["string"],
      "authority": "optional string",
      "required_documents": ["string"],
      "affected_subjects": ["string"],
      "notes": "optional string"
    }}
  ]
}}

Topic: {topic.name}
Cluster: {cluster.name}
Jurisdiction: {source.jurisdiction}
Citation: {source.citation}

Source text:
{source.authoritative_text}
""".strip()

    try:
        raw = llm_client.complete_text(
            prompt=prompt,
            model=llm_client.settings.local_extract_model,
            system_prompt="You extract legal propositions as strict JSON.",
            temperature=0.0,
        )
        parsed = _parse_json(raw)
    except Exception:
        return []

    propositions: list[Proposition] = []
    for index, item in enumerate(parsed.get("propositions", []), start=1):
        propositions.append(
            Proposition(
                id=f"prop-{_proposition_id_stem(source)}-{index:03d}",
                topic_id=topic.id,
                cluster_id=cluster.id,
                source_record_id=source.id,
                source_fragment_id=None,
                fragment_locator=source.authoritative_locator,
                source_snapshot_id=source.current_snapshot_id,
                jurisdiction=source.jurisdiction,
                article_reference=item.get("article_reference"),
                proposition_text=item["proposition_text"],
                legal_subject=item["legal_subject"],
                action=item["action"],
                conditions=item.get("conditions", []),
                authority=item.get("authority"),
                required_documents=item.get("required_documents", []),
                affected_subjects=item.get("affected_subjects", []),
                notes=item.get("notes", ""),
            )
        )
    return propositions


@dataclass(frozen=True)
class _StructuredDraft:
    marker_label: str
    path_key: str
    standalone_text: str
    parent_intro: str
    item_tail: str
    branch_context: str = ""
    is_derogation: bool = False
    conditions: tuple[str, ...] = ()
    cross_reference_targets: tuple[str, ...] = ()
    composition_meta: dict[str, Any] | None = None
    component_texts: tuple[str, ...] = ()


_STRUCTURED_NOTE_SIGNATURE_KEYS = (
    "structured_list_path",
    "list_marker",
    "parent_context",
    "composition_basis",
)


def parse_structured_extraction_notes(notes: str | None) -> dict[str, Any] | None:
    """Parse structured-list extraction metadata from ``notes``.

    Handles both the prefixed form (``STRUCTURED_NOTE_PREFIX`` + JSON) and the case where the
    Proposition notes-separation validator has stripped the prefix, leaving bare JSON that still
    carries the structured-list signature keys.
    """
    if not notes:
        return None
    has_prefix = STRUCTURED_NOTE_PREFIX in notes
    if has_prefix:
        idx = notes.find(STRUCTURED_NOTE_PREFIX)
        remainder = notes[idx + len(STRUCTURED_NOTE_PREFIX) :].lstrip("\n:")
        sep = remainder.find("{")
        if sep == -1:
            return None
        remainder = remainder[sep:]
    else:
        stripped = notes.strip()
        if not stripped.startswith("{"):
            return None
        remainder = stripped
    try:
        data = json.loads(remainder.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if has_prefix or any(key in data for key in _STRUCTURED_NOTE_SIGNATURE_KEYS):
        return data
    return None


def _normalize_proposition_comparison(text: str) -> str:
    return " ".join(text.lower().split())


def _draft_structured_subpropositions(fragment_text: str, base_locator: str) -> list[_StructuredDraft]:
    """Compose one draft per terminal structured-list alternative (stem+branch+leaf).

    Uses :func:`draft_structured_list_leaves` so both multiline and inline EU/UK list
    layouts are covered. Intermediate branches and governing stems are not emitted as
    standalone drafts.
    """
    leaves = draft_structured_list_leaves(fragment_text, base_locator)
    out: list[_StructuredDraft] = []
    for leaf in leaves:
        out.append(
            _StructuredDraft(
                marker_label=leaf.marker_label,
                path_key=leaf.path_key,
                standalone_text=leaf.standalone_text,
                parent_intro=leaf.parent_intro,
                item_tail=leaf.item_tail,
                branch_context=leaf.branch_context,
                is_derogation=leaf.is_derogation,
                conditions=leaf.conditions,
                cross_reference_targets=leaf.cross_reference_targets,
                composition_meta=leaf.composition_meta,
                component_texts=tuple(c.text for c in leaf.components if c.text.strip()),
            )
        )
    return out


def _structured_list_candidates_for_source(source: SourceRecord) -> list[tuple[str, _StructuredDraft]]:
    out: list[tuple[str, _StructuredDraft]] = []
    for locator, fragment in _extract_source_fragments(source):
        for draft in _draft_structured_subpropositions(fragment, locator):
            out.append((locator, draft))
    return out


def _structured_primary_bucket(marker_label: str) -> str:
    """Bucket for round-robin across list items: primary ``(a)`` / head before ``->``."""
    head = marker_label.split("->", 1)[0].strip()
    m_head = re.match(r"^\(([a-z])\)", head, re.IGNORECASE)
    return (m_head.group(1).lower() if m_head else head)[:16]


def _prioritize_structured_drafts(
    drafts: list[tuple[str, _StructuredDraft]],
    quota: int,
) -> list[tuple[str, _StructuredDraft]]:
    """
    When a list explodes into roman sub-items, taking ``drafts[:quota]`` only ever
    returns ``(a)``. Interleave primaries `(a)`, `(b)`, … so later letters (e.g. equine
    `(d)`) survive under small extraction limits.
    """
    if quota <= 0 or not drafts:
        return []
    if len(drafts) <= quota:
        return drafts
    letter_order: list[str] = []
    seen: set[str] = set()
    for _, draft in drafts:
        bkt = _structured_primary_bucket(draft.marker_label)
        if bkt not in seen:
            seen.add(bkt)
            letter_order.append(bkt)
    queues: dict[str, deque[tuple[str, _StructuredDraft]]] = {}
    for item in drafts:
        bkt = _structured_primary_bucket(item[1].marker_label)
        queues.setdefault(bkt, deque()).append(item)
    selected: list[tuple[str, _StructuredDraft]] = []
    while len(selected) < quota:
        progressed = False
        for bkt in letter_order:
            if len(selected) >= quota:
                break
            q = queues.get(bkt)
            if q:
                selected.append(q.popleft())
                progressed = True
        if not progressed:
            break
    return selected


def _structured_list_props(
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    *,
    quota: int,
) -> tuple[list[Proposition], list[str]]:
    if quota <= 0:
        return [], []
    drafts = _structured_list_candidates_for_source(source)
    picked = _prioritize_structured_drafts(drafts, quota)
    props: list[Proposition] = []
    norms: list[str] = []
    base_art = (
        source.authoritative_locator
        if not _is_placeholder_locator(source.authoritative_locator or "")
        else None
    ) or (_extract_article_reference(source.authoritative_text) or "article:unknown")

    for seq_num, (_, draft) in enumerate(picked, start=1):
        standalone = draft.standalone_text
        if not standalone.strip():
            continue
        if is_repealed_or_empty_fragment(standalone):
            continue

        evidence_loc_suffix = draft.path_key
        composite_loc = f"{base_art}:list:{evidence_loc_suffix}"
        fragment_locator = composite_loc[:512]
        article_reference = (
            _extract_article_reference(standalone)
            or _extract_reference_from_locator(fragment_locator)
            or draft.marker_label.strip("() ")
        )

        slug_base = slugify(source.id.strip())
        key_frag = slugify(evidence_loc_suffix.replace("__", "_"))
        proposition_key = f"{slug_base}:{key_frag}:p{seq_num:03d}"

        meta = {
            "parent_context": draft.parent_intro,
            "branch_context": draft.branch_context,
            "list_marker": draft.marker_label,
            "evidence_locator": fragment_locator,
            "structured_list_path": draft.path_key,
            "duplicate_suppression_hint": standalone[:160],
            "composition_basis": COMPOSITION_BASIS,
            "source_component_locators": (draft.composition_meta or {}).get(
                "source_component_locators", []
            ),
            "provision_type": "exception" if draft.is_derogation else "core",
        }
        sentence = standalone
        legal_subject = _guess_subject(sentence)
        notes = STRUCTURED_NOTE_PREFIX + "\n" + json.dumps(meta, sort_keys=True)
        conditions = list(draft.conditions) if draft.conditions else _guess_conditions(sentence)

        props.append(
            Proposition(
                id=f"prop-{_proposition_id_stem(source)}-{seq_num:03d}",
                proposition_key=proposition_key,
                topic_id=topic.id,
                cluster_id=cluster.id,
                source_record_id=source.id,
                source_fragment_id=None,
                fragment_locator=fragment_locator,
                source_snapshot_id=source.current_snapshot_id,
                jurisdiction=source.jurisdiction,
                article_reference=article_reference,
                proposition_text=sentence,
                legal_subject=legal_subject,
                action=_guess_action(sentence),
                conditions=conditions,
                authority=_guess_authority(sentence),
                required_documents=_guess_required_documents(sentence),
                affected_subjects=[legal_subject],
                notes=notes,
                explicit_cross_reference_targets=list(draft.cross_reference_targets),
                extraction_debug_meta={
                    "extraction_mode": "heuristic",
                    "provision_type": meta["provision_type"],
                    "composition_basis": COMPOSITION_BASIS,
                    "parent_context": draft.parent_intro,
                    "branch_context": draft.branch_context,
                    "list_marker": draft.marker_label,
                    "structured_list_path": draft.path_key,
                    "source_component_locators": meta["source_component_locators"],
                    "evidence_quote": draft.item_tail,
                    "evidence_locator": fragment_locator,
                    "duplicate_suppression_hint": standalone[:160],
                },
            )
        )
        norms.append(_normalize_proposition_comparison(sentence))

    intro_only = drafts[0][1].parent_intro.strip() if drafts else ""
    # Also suppress the raw fragment / authoritative text so sentence fallback does not
    # re-emit the whole list container alongside terminal leaves.
    full_text = (source.authoritative_text or "").strip()
    extra_exclusions = [intro_only, full_text]
    for _, draft in drafts:
        if draft.branch_context:
            extra_exclusions.append(draft.branch_context)
    return props, [*norms, *(_normalize_proposition_comparison(x) for x in extra_exclusions if x)]


def _heuristic_sentence_extraction_filtered(
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    *,
    limit: int,
    exclude_norm_texts: set[str],
    id_seq_start: int,
) -> list[Proposition]:
    excludes = {_normalize_proposition_comparison(x) for x in exclude_norm_texts if x.strip()}
    sentence_candidates = [
        (locator, sentence)
        for locator, sentence in _build_sentence_candidates(source)
        if not is_repealed_or_empty_fragment(sentence)
    ]
    normative_candidates = [
        (locator, sentence)
        for locator, sentence in sentence_candidates
        if _looks_normative(sentence) and _normalize_proposition_comparison(sentence) not in excludes
    ]
    preferred_normative_candidates = [
        (locator, sentence)
        for locator, sentence in normative_candidates
        if _is_operative_locator(locator)
    ]
    fallback_pool = [
        (locator, sentence)
        for locator, sentence in sentence_candidates
        if _normalize_proposition_comparison(sentence) not in excludes
    ]
    selected_candidates = (
        preferred_normative_candidates
        or normative_candidates
        or fallback_pool[:max(1, limit)]
        or [
            (
                source.authoritative_locator or "document:full",
                source.authoritative_text.strip() or "No source text provided.",
            )
        ]
    )

    propositions: list[Proposition] = []
    for offset, (locator, sentence) in enumerate(selected_candidates[:limit]):
        seq = id_seq_start + offset
        if _normalize_proposition_comparison(sentence) in excludes:
            continue
        legal_subject = _guess_subject(sentence)
        action = _guess_action(sentence)
        article_reference = _extract_article_reference(sentence) or _extract_reference_from_locator(
            locator
        )

        propositions.append(
            Proposition(
                id=f"prop-{_proposition_id_stem(source)}-{seq:03d}",
                proposition_key=None,
                topic_id=topic.id,
                cluster_id=cluster.id,
                source_record_id=source.id,
                source_fragment_id=None,
                fragment_locator=str(locator) if locator else None,
                source_snapshot_id=source.current_snapshot_id,
                jurisdiction=source.jurisdiction,
                article_reference=article_reference,
                proposition_text=sentence,
                legal_subject=legal_subject,
                action=action,
                conditions=_guess_conditions(sentence),
                authority=_guess_authority(sentence),
                required_documents=_guess_required_documents(sentence),
                affected_subjects=[legal_subject],
                notes="heuristic extraction",
            )
        )
    return propositions


def _heuristic_extraction(
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    limit: int,
) -> list[Proposition]:
    structured_candidates = _structured_list_candidates_for_source(source)
    structured_props: list[Proposition] = []
    exclusions: list[str] = []
    if structured_candidates:
        structured_props, exclusions = _structured_list_props(
            source,
            topic,
            cluster,
            quota=limit,
        )

    # When a fragment yields ≥2 structured terminal leaves, prefer those exclusively.
    # Sentence fallback otherwise re-emits partial list prose split on semicolons/periods.
    if len(structured_props) >= 2:
        return structured_props[:limit]

    exclude_norms = {_normalize_proposition_comparison(x) for x in exclusions if x}
    remainder = max(0, limit - len(structured_props))
    sentence_props: list[Proposition] = []
    if remainder > 0:
        sentence_props = _heuristic_sentence_extraction_filtered(
            source,
            topic,
            cluster,
            limit=remainder,
            exclude_norm_texts=exclude_norms,
            id_seq_start=len(structured_props) + 1,
        )

    merged = [*structured_props, *sentence_props]
    return merged[:limit]


_UNICODE_QUOTES: dict[int, str] = {
    0x201C: '"',
    0x201D: '"',
    0x2018: "'",
    0x2019: "'",
    0x00AB: '"',
    0x00BB: '"',
    0x2039: "'",
    0x203A: "'",
}


def _fold_unicode_quotes(s: str) -> str:
    return "".join(_UNICODE_QUOTES.get(ord(ch), ch) for ch in s)


def _strip_soft_hyphens(s: str) -> str:
    return s.replace("\u00AD", "").replace("\uFEFF", "")


_LINE_LIST_PREFIX_ITER = re.compile(
    r"^(?:"
    r"\(?:?\d+\)?[.)]\s+"
    r"|"
    r"\(\s*[a-z0-9ivxl]+\s*\)\s+"
    r"|"
    r"[\-\u2013\u2014•\*·]+\s+"
    r")",
    flags=re.IGNORECASE,
)


def _strip_first_list_like_prefix(fragment: str) -> str | None:
    stripped = fragment.lstrip()
    if not stripped:
        return None
    m = _LINE_LIST_PREFIX_ITER.match(stripped)
    if not m:
        return None
    tail = stripped[m.end() :].lstrip()
    if tail.startswith(";"):
        tail = tail[1:].lstrip()
    return tail


def _strip_list_like_line_prefixes(line: str) -> str:
    cur = line.strip()
    if not cur:
        return ""
    for _ in range(8):
        nxt = _strip_first_list_like_prefix(cur)
        if nxt is None:
            break
        cur = nxt.strip()
        if not cur:
            return ""
    return cur


def _normalize_evidence_for_match(s: str, *, strip_line_list_markers: bool) -> str:
    t = _strip_soft_hyphens(s)
    t = _fold_unicode_quotes(t)
    if strip_line_list_markers:
        chunks: list[str] = []
        for raw in t.replace("\r\n", "\n").split("\n"):
            norm_line = _strip_list_like_line_prefixes(raw)
            if norm_line.strip():
                chunks.append(norm_line.strip())
        t = " ".join(chunks)
    else:
        t = " ".join(t.split())
    return t.lower()


_TABLE_DASH_RE = re.compile(r"[\u2013\u2014—–\-]+")
_NUMERIC_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?$")
_NUMERIC_FINDALL_RE = re.compile(r"\d+(?:\.\d+)?")


def _insert_letter_digit_boundaries(s: str) -> str:
    out = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", s)
    return re.sub(r"(\d)([a-zA-Z])", r"\1 \2", out)


def _normalize_table_match_text(s: str) -> str:
    t = _strip_soft_hyphens(s)
    t = _fold_unicode_quotes(t)
    t = _TABLE_DASH_RE.sub(" ", t)
    t = t.replace("(", " ").replace(")", " ")
    t = re.sub(r"[^\w.\s]+", " ", t.lower())
    t = _insert_letter_digit_boundaries(t)
    return " ".join(t.split())


def _table_match_tokens(s: str) -> list[str]:
    return [tok for tok in _normalize_table_match_text(s).split() if tok]


def _is_numeric_table_token(token: str) -> bool:
    return bool(_NUMERIC_TOKEN_RE.match(token))


def _tokens_subsequence(needle: list[str], haystack: list[str]) -> bool:
    if not needle:
        return False
    hi = 0
    for tok in needle:
        while hi < len(haystack) and haystack[hi] != tok:
            hi += 1
        if hi >= len(haystack):
            return False
        hi += 1
    return True


def _split_table_row_evidence_tokens(tokens: list[str]) -> tuple[list[str], list[str]]:
    numeric_indices = [idx for idx, tok in enumerate(tokens) if _is_numeric_table_token(tok)]
    if len(numeric_indices) < 2:
        return tokens, []
    column_indices = numeric_indices[-3:] if len(numeric_indices) >= 3 else numeric_indices[-2:]
    split_at = column_indices[0]
    return tokens[:split_at], tokens[split_at:]


def _table_numeric_columns_match(column_tokens: list[str], source_text: str) -> bool:
    columns = [tok for tok in column_tokens if _is_numeric_table_token(tok)]
    if len(columns) < 2:
        return False
    src_tokens = _table_match_tokens(source_text)
    src_numeric = [tok for tok in src_tokens if _is_numeric_table_token(tok)]
    if _tokens_subsequence(columns, src_numeric):
        return True
    concat = "".join(re.sub(r"\.", "", tok) for tok in columns)
    digit_hay = re.sub(r"[^\d]", "", source_text)
    return bool(concat and concat in digit_hay)


def evidence_locates_table_numeric_token_match(
    evidence: str, source_text: str
) -> tuple[bool, str, dict[str, Any]]:
    """Match flattened schedule/table rows via label token subsequence plus numeric columns."""
    diagnostics: dict[str, Any] = {"attempted": ["table_numeric_token_match"]}
    cand_raw = evidence.strip()
    if not cand_raw:
        return False, "empty_candidate", diagnostics
    tokens = _table_match_tokens(cand_raw)
    label_tokens, column_tokens = _split_table_row_evidence_tokens(tokens)
    column_nums = [tok for tok in column_tokens if _is_numeric_table_token(tok)]
    if len(column_nums) < 2 or len(label_tokens) < 2:
        diagnostics["failure"] = "not_table_like_evidence"
        return False, "table_numeric_token_match", diagnostics
    src_tokens = _table_match_tokens(source_text)
    if not _tokens_subsequence(label_tokens, src_tokens):
        diagnostics["failure"] = "table_label_tokens_not_in_source"
        diagnostics["label_token_count"] = len(label_tokens)
        return False, "table_numeric_token_match", diagnostics
    if not _table_numeric_columns_match(column_tokens, source_text):
        diagnostics["failure"] = "table_numeric_columns_not_in_source"
        diagnostics["column_tokens"] = column_nums
        return False, "table_numeric_token_match", diagnostics
    diagnostics["success"] = "table_numeric_token_match"
    diagnostics["column_tokens"] = column_nums
    return True, "table_numeric_token_match", diagnostics


def evidence_locates_verbatim_after_normalisation(
    evidence: str, source_text: str
) -> tuple[bool, str, dict[str, Any]]:
    """Return True only if a normalisation of evidence appears verbatim in the same-normalised source (no fuzzy paraphrase)."""
    variants: tuple[tuple[bool, str], ...] = (
        (False, "whitespace_quote_fold_lc_substring_match"),
        (True, "whitespace_quote_fold_lc_list_marker_substring_match"),
    )
    diagnostics: dict[str, Any] = {"attempted": [], "haystack_lens": [], "needle_lens": []}
    cand_raw = evidence.strip()
    if not cand_raw:
        return False, "empty_candidate", diagnostics
    hay_raw = source_text
    for strip_markers, label in variants:
        ev_n = _normalize_evidence_for_match(cand_raw, strip_line_list_markers=strip_markers)
        src_n = _normalize_evidence_for_match(hay_raw, strip_line_list_markers=strip_markers)
        diagnostics["attempted"].append(label)
        diagnostics["needle_lens"].append(len(ev_n))
        diagnostics["haystack_lens"].append(len(src_n))
        if not ev_n:
            diagnostics["failure"] = "evidence_normalized_to_empty"
            return False, label, diagnostics
        if ev_n in src_n:
            diagnostics["success"] = label
            return True, label, diagnostics
        diagnostics.setdefault("needle_tail", ev_n[-36:])
    table_ok, table_strategy, table_diag = evidence_locates_table_numeric_token_match(
        cand_raw, hay_raw
    )
    diagnostics["attempted"].extend(table_diag.get("attempted") or [])
    if table_ok:
        diagnostics["success"] = table_strategy
        diagnostics["table_match"] = table_diag
        return True, table_strategy, diagnostics
    diagnostics["table_match"] = table_diag
    diagnostics["failure"] = "no_normalized_substring_match_paraphrase_or_unrecoverable_markup"
    return False, variants[-1][1], diagnostics


def _validate_v2_items(
    raw_items: list[dict[str, Any]],
    source_text: str,
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    issue_records: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for idx, item in enumerate(raw_items):
        if not isinstance(item, dict):
            msg = f"row {idx}: expected object"
            errors.append(msg)
            issue_records.append(
                {
                    "kind": "structure",
                    "row_index": idx,
                    "candidate_evidence_text": "",
                    "source_locator_hint": "",
                    "normalization_matching_strategy": "",
                    "reason_code": "invalid_row_type",
                    "failure_reason": msg,
                    "diagnostics": {},
                }
            )
            continue
        ptxt = str(item.get("proposition_text") or "").strip()
        if not ptxt:
            msg = f"row {idx}: proposition_text empty"
            errors.append(msg)
            issue_records.append(
                {
                    "kind": "proposition",
                    "row_index": idx,
                    "candidate_evidence_text": str(item.get("evidence_text") or ""),
                    "source_locator_hint": str(item.get("source_locator") or "").strip(),
                    "normalization_matching_strategy": "",
                    "reason_code": "empty_proposition",
                    "failure_reason": msg,
                    "diagnostics": {},
                }
            )
            continue
        ev = str(item.get("evidence_text") or "").strip()
        reason_raw = str(item.get("reason") or "").strip()
        loc_raw = str(item.get("source_locator") or "").strip()
        if not ev:
            if not reason_raw:
                msg = (
                    f"row {idx}: evidence_text empty but reason does not explain why "
                    "(copy verbatim or leave empty only with justification)"
                )
                errors.append(msg)
                issue_records.append(
                    {
                        "kind": "evidence_traceability",
                        "row_index": idx,
                        "candidate_evidence_text": "",
                        "source_locator_hint": loc_raw,
                        "normalization_matching_strategy": "none_empty_evidence",
                        "reason_code": "empty_evidence_no_reason",
                        "failure_reason": msg,
                        "diagnostics": {},
                    }
                )
                continue
        else:
            ok, strategy, diag = evidence_locates_verbatim_after_normalisation(ev, source_text)
            # Structured-list composition: composed text may span non-contiguous
            # stem/branch/leaf nodes; accept when each recorded component locates in source.
            if not ok:
                component_texts = item.get("_source_component_texts")
                if (
                    isinstance(component_texts, list)
                    and component_texts
                    and (
                        str(item.get("_composition_basis") or "") == COMPOSITION_BASIS
                        or isinstance(item.get("_structured_list_meta"), dict)
                    )
                ):
                    all_ok = True
                    comp_diags: list[dict[str, Any]] = []
                    for ct in component_texts:
                        if not isinstance(ct, str) or not ct.strip():
                            continue
                        cok, cstrat, _cdiag = evidence_locates_verbatim_after_normalisation(
                            ct, source_text
                        )
                        comp_diags.append({"text": ct[:120], "ok": cok, "strategy": cstrat})
                        if not cok:
                            all_ok = False
                    if all_ok:
                        ok = True
                        strategy = "structured_list_component_match"
                        diag = {
                            "components": comp_diags,
                            "composition_basis": COMPOSITION_BASIS,
                        }
            if not ok:
                msg = f"row {idx}: evidence_text not traceable to source"
                errors.append(msg)
                issue_records.append(
                    {
                        "kind": "evidence_traceability",
                        "row_index": idx,
                        "candidate_evidence_text": ev,
                        "source_locator_hint": loc_raw,
                        "normalization_matching_strategy": strategy,
                        "reason_code": "no_verbatim_normalized_span",
                        "failure_reason": msg,
                        "diagnostics": diag,
                    }
                )
                continue
            item["_validated_evidence_match_strategy"] = strategy
            if strategy == "table_numeric_token_match":
                item.setdefault("_trace_warnings", []).append(
                    "evidence_matched_via_table_numeric_token_strategy"
                )
                if str(item.get("completeness_status") or "").strip() == "complete":
                    item["completeness_status"] = "context_dependent"
            elif strategy == "structured_list_component_match":
                item.setdefault("_trace_warnings", []).append(
                    "evidence_matched_via_structured_list_components"
                )
        nk = (_normalize_proposition_comparison(ptxt), loc_raw.lower())
        if nk in seen_keys:
            msg = f"row {idx}: duplicate proposition_text for same locator"
            errors.append(msg)
            issue_records.append(
                {
                    "kind": "dedup",
                    "row_index": idx,
                    "candidate_evidence_text": ev,
                    "source_locator_hint": loc_raw,
                    "normalization_matching_strategy": str(
                        item.get("_validated_evidence_match_strategy") or ""
                    ),
                    "reason_code": "duplicate_proposition_same_locator",
                    "failure_reason": msg,
                    "diagnostics": {},
                }
            )
            continue
        seen_keys.add(nk)
        pt = item.get("provision_type")
        if pt is not None and str(pt) not in _PROVISION_TYPES_V2:
            msg = f"row {idx}: invalid provision_type"
            errors.append(msg)
            issue_records.append(
                {
                    "kind": "schema",
                    "row_index": idx,
                    "candidate_evidence_text": ev,
                    "source_locator_hint": loc_raw,
                    "normalization_matching_strategy": str(
                        item.get("_validated_evidence_match_strategy") or ""
                    ),
                    "reason_code": "invalid_provision_type",
                    "failure_reason": msg,
                    "diagnostics": {},
                }
            )
            continue
        cs = item.get("completeness_status")
        if cs is not None and str(cs) not in _COMPLETENESS_V2:
            msg = f"row {idx}: invalid completeness_status"
            errors.append(msg)
            issue_records.append(
                {
                    "kind": "schema",
                    "row_index": idx,
                    "candidate_evidence_text": ev,
                    "source_locator_hint": loc_raw,
                    "normalization_matching_strategy": str(
                        item.get("_validated_evidence_match_strategy") or ""
                    ),
                    "reason_code": "invalid_completeness",
                    "failure_reason": msg,
                    "diagnostics": {},
                }
            )
            continue
        accepted.append(item)
        if len(accepted) >= limit:
            break
    return accepted, errors, issue_records


def _v2_model_prompt(
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    *,
    extraction_mode: Literal["frontier", "local"],
    max_propositions: int = 4,
    focus_scopes: Sequence[str] | None = None,
    prompt_source_text: str | None = None,
    fragment_locator_hint: str | None = None,
    structural_heading_contexts: Sequence[Any] | None = None,
) -> str:
    schema = """
{
  "propositions": [
    {
      "proposition_text": "string",
      "display_label": "string",
      "subject": "string",
      "rule": "string",
      "object": "string",
      "conditions": ["string"],
      "exceptions": ["string"],
      "temporal_condition": "string or empty",
      "provision_type": "core | definition | exception | transitional | cross_reference",
      "source_locator": "string",
      "evidence_text": "string",
      "completeness_status": "complete | context_dependent | fragmentary",
      "confidence": "high | medium | low",
      "reason": "string"
    }
  ]
}
""".strip()
    scopes = tuple(str(s).strip() for s in (focus_scopes or ()) if str(s).strip())
    cap_line = (
        f"Extract at most {max_propositions} legally distinct propositions for this response "
        f"(hard cap — omit lower-salience rows if needed)."
    )
    list_rules = """
Structured lists:
- Where the Source uses numbered paragraphs, lettered subparagraphs ((a), (b), …), or roman sub-items ((i), (ii), …), treat each substantive obligation or exception alternative as its own proposition when it is legally distinct from neighbouring rows.
- Nested terminals such as (a)(i) and (a)(ii) are separate propositions; each must carry forward the governing stem (e.g. "Paragraph 1 shall not apply") and any intermediate branch condition.
- Do not merge unrelated list items; do not stop after an early subset when later items in the same list remain legally distinct and within the cap below.
- Do not emit a proposition solely for a governing stem or intermediate branch when terminal leaves complete that statement.
"""
    scoped_prior = ""
    if scopes:
        joined = "; ".join(scopes)
        scoped_prior = f"""
Focus scopes (case-config priority labels — interpret substantively, not keyword matching):
- The case prioritises material relating to: {joined}
- Within the cap below, include propositions whose substance connects to those scopes, including items that appear later in long lists, before dropping them in favour of unrelated earlier rows.
"""
    else:
        scoped_prior = """
No focus scopes:
- Within the cap below, prefer the most legally salient obligations for the Topic and Cluster; stay within the cap rather than enumerating every peripheral line.
- Returning propositions=[] is unusual for substantive regulatory text that was selected for extraction. Use propositions=[] only when the Source chunk contains no legally distinct obligation, definition, exception, or transitional rule you can support with schema fields — and set reason on any retained row explaining omissions.
"""

    frontier_rules = ""
    if extraction_mode == "frontier":
        frontier_rules = f"""
Frontier extraction rules (critical for audits):
- {cap_line}
{list_rules.strip()}
{scoped_prior.strip()}
- proposition_text MAY be rewritten as a concise, readable legal proposition (normalized wording OK).
- evidence_text MUST be copied verbatim from the Source text chunk — character-for-character as it appears there (subset / exact span selection). It must be the shortest contiguous span from the Source that suffices to justify the proposition. Do NOT paraphrase, summarise, or re-order words inside evidence_text.
- source_locator MUST preserve traceability to the obligation's position (e.g. article/paragraph identifiers, list marks such as '(d)(ii)' or '(b)') consistent with the Source layout.
- If no contiguous verbatim span can be selected (ambiguous layout, garbled OCR, contradictory instructions), set evidence_text to an empty string and use reason to explain briefly why verbatim evidence could not be provided.
"""

    local_rules = ""
    if extraction_mode == "local":
        local_rules = f"""
Local extraction rules:
- {cap_line}
{list_rules.strip()}
{scoped_prior.strip()}
- source_locator SHOULD identify where the obligation sits when identifiable from the Source.
- Returning propositions=[] is unusual for ordinary statutory provisions. If the text states citation, commencement, territorial extent, application, duty, prohibition, power, definition, exception, or cross-reference, extract at least one proposition.
- Only return an empty propositions array when the fragment is genuinely non-substantive; add top-level "empty_rationale" (string) explaining why.
- Invalid outputs: {{}}, {{"propositions":null}}, and any prose outside JSON. Valid output MUST have top-level "propositions" as an array.
"""

    rules_line = ""
    if frontier_rules.strip():
        rules_line = frontier_rules.strip() + "\n\n"
    elif local_rules.strip():
        rules_line = local_rules.strip() + "\n\n"

    schema_terms = ""
    if extraction_mode == "frontier":
        schema_terms = """
Semantics:
- proposition_text: normalised legal proposition (readable).
- evidence_text: exact quote from Source (verbatim span), or \"\" when impossible with rationale in reason.
"""

    body_text = source.authoritative_text if prompt_source_text is None else prompt_source_text
    locator_note = ""
    if fragment_locator_hint and str(fragment_locator_hint).strip():
        locator_note = f"\nFragment locator (traceability): {str(fragment_locator_hint).strip()}\n"

    few_shot_block = ""
    if extraction_mode == "local":
        few_shot_block = _local_few_shot_block() + "\n\n"

    heading_contexts = structural_heading_contexts
    if heading_contexts is None and isinstance(source.metadata, dict):
        heading_contexts = source.metadata.get("structural_heading_contexts")
    structural_block = ""
    if heading_contexts:
        from law_proposition_extractor_pipeline.structural_headings import format_heading_contexts_for_prompt

        heading_lines = format_heading_contexts_for_prompt(heading_contexts)
        if heading_lines.strip():
            structural_block = f"""
Structural legislative context
(non-operative headings; use only to understand subject and scope):

{heading_lines}

A heading is contextual source text, not by itself an operative legal proposition.
Do not extract a standalone proposition from a heading.
Do not add conditions, duties or exceptions found only in a heading unless the operative text supports them.
Do not use heading text as evidence_text; evidence_text must be a verbatim span from the operative source text below.
"""

    return f"""
Extract legal propositions from the source text. Return JSON only with this exact shape:
{schema}

{rules_line}{few_shot_block}{schema_terms}Topic: {topic.name}
Cluster: {cluster.name}
Jurisdiction: {source.jurisdiction}
Citation: {source.citation}
{locator_note}{structural_block}
Operative source text:
{body_text}
""".strip()


def _parse_model_propositions_container(parsed: Any) -> list[dict[str, Any]]:
    rows, _raw = parse_model_propositions_container(parsed)
    return rows


_SENSITIVE_OUTPUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"',;]+"),
    re.compile(r"(?i)(x-api-key\s*:\s*)[^\s\"',;]+"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s\"',;]+"),
    re.compile(r"(?i)(client[_-]?secret\s*[=:]\s*)[^\s\"',;]+"),
)


def _redact_sensitive_model_output(raw: str) -> str:
    text = raw
    for pattern in _SENSITIVE_OUTPUT_PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text


def _safe_model_output_excerpt(raw: str, *, cap: int = 4000) -> tuple[str, bool]:
    redacted = _redact_sensitive_model_output(raw)
    truncated = len(redacted) > cap
    return redacted[:cap], truncated


def _resolve_try_extract_output_mode(
    *,
    extraction_mode: Literal["frontier", "local"],
    model_alias: str,
    llm_client: JuditLLMClient,
    extraction_output_mode: ExtractionOutputMode | str | None,
    json_output_mode: Literal["json_object", "json_schema"] | None,
    allow_output_mode_fallback: bool,
) -> ExtractionOutputMode:
    if extraction_output_mode is not None:
        requested: ExtractionOutputMode | str | None = extraction_output_mode
    elif json_output_mode is not None:
        requested = json_output_mode
    else:
        requested = None
    resolved = resolve_extraction_output_mode(
        extraction_mode=extraction_mode,
        model_alias=model_alias,
        requested=requested,
        settings=getattr(llm_client, "settings", None),
    )
    return ensure_output_mode_supported(
        extraction_output_mode=resolved,
        extraction_mode=extraction_mode,
        model_alias=model_alias,
        settings=getattr(llm_client, "settings", None),
        allow_fallback=allow_output_mode_fallback,
    )


def _client_uses_complete_text_result(llm_client: object) -> bool:
    if isinstance(llm_client, JuditLLMClient):
        return True
    if type(llm_client).__name__ == "MagicMock":
        ctr = llm_client.complete_text_result
        return ctr.side_effect is not None or getattr(ctr, "_mock_wraps", None) is not None
    return callable(getattr(llm_client, "complete_text_result", None))


def _complete_extraction_llm(
    *,
    llm_client: JuditLLMClient,
    prompt: str,
    model_alias: str,
    output_mode: ExtractionOutputMode,
    allow_output_mode_fallback: bool,
) -> TextCompletionResult:
    """Call the LLM with the resolved extraction output mode; optionally fall back on rejection."""
    modes_to_try: list[ExtractionOutputMode] = [output_mode]
    fb = fallback_output_mode(output_mode)
    if allow_output_mode_fallback and fb is not None and fb not in modes_to_try:
        modes_to_try.append(fb)

    last_error: Exception | None = None
    for attempt_mode in modes_to_try:
        enforce_json = attempt_mode == "json_object"
        schema_wrapper = (
            build_litellm_json_schema_wrapper() if attempt_mode == "json_schema" else None
        )
        try:
            if _client_uses_complete_text_result(llm_client):
                return llm_client.complete_text_result(
                    prompt=prompt,
                    model=model_alias,
                    system_prompt=_V2_SYSTEM_PROMPT,
                    temperature=0.0,
                    enforce_json_object=enforce_json,
                    json_schema=schema_wrapper,
                )
            legacy_raw = llm_client.complete_text(
                prompt=prompt,
                model=model_alias,
                system_prompt=_V2_SYSTEM_PROMPT,
                temperature=0.0,
                enforce_json_object=enforce_json,
            )
            return TextCompletionResult(
                content=legacy_raw or "",
                finish_reason=None,
                response_format=build_response_format_for_mode(attempt_mode),
            )
        except Exception as exc:
            last_error = exc
            if (
                attempt_mode == "json_schema"
                and allow_output_mode_fallback
                and fb == "json_object"
                and is_output_mode_rejection_error(str(exc))
            ):
                continue
            if attempt_mode == "json_schema" and not allow_output_mode_fallback:
                if is_output_mode_rejection_error(str(exc)):
                    raise ExtractionOutputModeRejectedError(
                        f"provider rejected json_schema structured output for model {model_alias!r}: {exc}"
                    ) from exc
            raise
    assert last_error is not None
    raise last_error


def _try_extract_model_v2_json(
    *,
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    llm_client: JuditLLMClient,
    model_alias: str,
    extraction_mode: Literal["frontier", "local"],
    max_propositions: int,
    focus_scopes: Sequence[str] | None = None,
    prompt_source_text: str | None = None,
    fragment_locator_hint: str | None = None,
    prompt_version: str = EXTRACTION_PROMPT_VERSION,
    estimated_input_tokens: int | None = None,
    prompt_retry_suffix: str | None = None,
    extraction_output_mode: ExtractionOutputMode | str | None = None,
    json_output_mode: Literal["json_object", "json_schema"] | None = None,
    allow_output_mode_fallback: bool = False,
    workbench_raw_outputs: list[str] | None = None,
    structural_heading_contexts: Sequence[Any] | None = None,
) -> tuple[list[dict[str, Any]] | None, str | None, dict[str, Any] | None]:
    body = source.authoritative_text if prompt_source_text is None else prompt_source_text
    prompt = _v2_model_prompt(
        source,
        topic,
        cluster,
        extraction_mode=extraction_mode,
        max_propositions=max_propositions,
        focus_scopes=focus_scopes,
        prompt_source_text=body,
        fragment_locator_hint=fragment_locator_hint,
        structural_heading_contexts=structural_heading_contexts,
    )
    if prompt_retry_suffix:
        prompt = f"{prompt}\n\n{prompt_retry_suffix}"
    raw: str | None = None
    finish_reason: str | None = None
    effective_mode = _resolve_try_extract_output_mode(
        extraction_mode=extraction_mode,
        model_alias=model_alias,
        llm_client=llm_client,
        extraction_output_mode=extraction_output_mode,
        json_output_mode=json_output_mode,
        allow_output_mode_fallback=allow_output_mode_fallback,
    )
    mode_trace = output_mode_trace_fields(extraction_output_mode=effective_mode)
    try:
        completion = _complete_extraction_llm(
            llm_client=llm_client,
            prompt=prompt,
            model_alias=model_alias,
            output_mode=effective_mode,
            allow_output_mode_fallback=allow_output_mode_fallback,
        )
        if completion.response_format is not None:
            mode_trace["response_format"] = completion.response_format
            mode_trace["response_format_type"] = str(
                completion.response_format.get("type") or mode_trace["response_format_type"]
            )
        if allow_output_mode_fallback and effective_mode == "json_schema":
            sent_type = str((completion.response_format or {}).get("type") or "")
            if sent_type == "json_object":
                effective_mode = "json_object"
                mode_trace["extraction_output_mode"] = "json_object"
                mode_trace["response_format_type"] = "json_object"
                mode_trace.pop("schema_hash", None)
        raw = completion.content
        finish_reason = completion.finish_reason
        if workbench_raw_outputs is not None and isinstance(raw, str):
            workbench_raw_outputs.append(raw)
        if not (raw or "").strip():
            failure_type, failure_reason = classify_empty_extraction_outcome(raw=raw)
            diag = build_llm_failure_trace_fields(
                raw=raw,
                failure_type=failure_type,
                failure_reason=failure_reason,
                model_alias=model_alias,
                prompt_version=prompt_version,
                prompt_text=prompt,
                fragment_locator=fragment_locator_hint,
                estimated_input_tokens=estimated_input_tokens,
                finish_reason=finish_reason,
                candidate_row_count=0,
                accepted_row_count=0,
            )
            diag.update(mode_trace)
            return None, failure_reason, diag
        parse_result = _parse_json_result(raw)
        parsed = parse_result.parsed
        schema_ok, schema_err = validate_parsed_extraction_schema(
            parsed, extraction_output_mode=effective_mode
        )
        if not schema_ok:
            failure_reason = schema_err or "extraction response violates JSON schema"
            diag = build_llm_failure_trace_fields(
                raw=raw,
                failure_type=EXTRACTION_SCHEMA_VIOLATION,
                failure_reason=failure_reason,
                model_alias=model_alias,
                prompt_version=prompt_version,
                prompt_text=prompt,
                fragment_locator=fragment_locator_hint,
                estimated_input_tokens=estimated_input_tokens,
                finish_reason=finish_reason,
                candidate_row_count=0,
                accepted_row_count=0,
            )
            diag.update(mode_trace)
            return None, failure_reason, diag
    except (ExtractionOutputModeUnsupportedError, ExtractionOutputModeRejectedError) as exc:
        diag = build_llm_failure_trace_fields(
            raw=None,
            failure_type=EXTRACTION_SCHEMA_VIOLATION,
            failure_reason=str(exc),
            model_alias=model_alias,
            prompt_version=prompt_version,
            prompt_text=prompt,
            fragment_locator=fragment_locator_hint,
            estimated_input_tokens=estimated_input_tokens,
            finish_reason=None,
            candidate_row_count=0,
            accepted_row_count=0,
        )
        diag.update(mode_trace)
        return None, str(exc), diag
    except json.JSONDecodeError as exc:
        # parse_extraction_json raises JSONDecodeError both for genuinely unparseable text and for
        # valid JSON with the wrong shape (missing `propositions`, non-object root). The latter is a
        # schema violation, not a non-JSON response — classify it accordingly.
        schema_shaped = any(
            marker in str(exc)
            for marker in ("missing top-level propositions key", "parsed value is not a JSON object")
        )
        if schema_shaped:
            failure_type = EXTRACTION_SCHEMA_VIOLATION
            failure_reason = f"extraction response violates JSON schema: {exc}"
        else:
            failure_type, failure_reason = classify_empty_extraction_outcome(
                raw=raw, json_parse_failed=True
            )
        diag = build_llm_failure_trace_fields(
            raw=raw,
            failure_type=failure_type,
            failure_reason=failure_reason,
            model_alias=model_alias,
            prompt_version=prompt_version,
            prompt_text=prompt,
            fragment_locator=fragment_locator_hint,
            estimated_input_tokens=estimated_input_tokens,
            finish_reason=finish_reason,
            parse_error_message=str(exc),
            parse_error_line=int(exc.lineno) if isinstance(exc.lineno, int) else None,
            parse_error_column=int(exc.colno) if isinstance(exc.colno, int) else None,
        )
        diag.update(mode_trace)
        return None, failure_reason if schema_shaped else f"model call or JSON parse failed: {exc}", diag
    except Exception as exc:
        diag = build_llm_failure_trace_fields(
            raw=raw,
            failure_type=EXTRACTION_SCHEMA_VIOLATION,
            failure_reason=f"model call or JSON parse failed: {exc}",
            model_alias=model_alias,
            prompt_version=prompt_version,
            prompt_text=prompt,
            fragment_locator=fragment_locator_hint,
            estimated_input_tokens=estimated_input_tokens,
            finish_reason=finish_reason,
            candidate_row_count=0,
            accepted_row_count=0,
        )
        diag.update(mode_trace)
        return None, f"model call or JSON parse failed: {exc}", diag
    rows = _parse_model_propositions_container(parsed)
    if not rows:
        failure_type, failure_reason = classify_empty_extraction_outcome(
            raw=raw, parsed=parsed, raw_rows=rows
        )
        diag = build_llm_failure_trace_fields(
            raw=raw,
            failure_type=failure_type,
            failure_reason=failure_reason,
            model_alias=model_alias,
            prompt_version=prompt_version,
            prompt_text=prompt,
            fragment_locator=fragment_locator_hint,
            estimated_input_tokens=estimated_input_tokens,
            finish_reason=finish_reason,
            candidate_row_count=0,
            accepted_row_count=0,
        )
        diag.update(mode_trace)
        return None, failure_reason, diag
    success_diag: dict[str, Any] = {
        "finish_reason": finish_reason,
        **mode_trace,
    }
    if parse_result is not None and getattr(parse_result, "json_repair_applied", False):
        success_diag["json_repair_applied"] = True
        success_diag["json_repair_method"] = parse_result.json_repair_method
    if completion.model:
        success_diag["response_model"] = completion.model
    if isinstance(raw, str) and raw:
        excerpt, truncated = _safe_model_output_excerpt(raw, cap=2048)
        success_diag["raw_model_output_excerpt"] = excerpt
        success_diag["raw_model_output_truncated"] = truncated
    return rows, None, success_diag


@dataclass
class _ChunkLlmAttemptOutcome:
    validated_rows: list[dict[str, Any]]
    model_err: str | None
    failure_type: str | None
    raw_model_output: str | None
    repairable_halt: bool = False
    issue_records: list[dict[str, Any]] = field(default_factory=list)
    valerrs: list[str] = field(default_factory=list)


def _run_chunk_llm_extraction_attempt(
    *,
    trace: dict[str, Any],
    attempt_index: int,
    previous_failure_type: str | None,
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    llm_client: JuditLLMClient,
    model_alias: str,
    llm_prompt_mode: Literal["frontier", "local"],
    limit: int,
    focus_scopes: Sequence[str] | None,
    chunk_text: str,
    fragment_locator: str,
    prompt_version: str,
    chunk_est: int,
    chunk_label: str,
    prompt_retry_suffix: str | None = None,
    extraction_output_mode: ExtractionOutputMode | str | None = None,
    json_output_mode: Literal["json_object", "json_schema"] | None = None,
    allow_output_mode_fallback: bool = False,
    model_error_policy: Literal[
        "continue_with_fallback", "stop_repairable", "continue_repairable"
    ],
    on_before_llm_call: Callable[[dict[str, Any]], None] | None,
    workbench_raw_outputs: list[str] | None = None,
) -> _ChunkLlmAttemptOutcome:
    trace["attempt_index"] = attempt_index
    if previous_failure_type:
        trace["previous_failure_type"] = previous_failure_type
    trace["llm_call_attempted"] = True
    if on_before_llm_call is not None:
        on_before_llm_call(dict(trace))

    try_result = _try_extract_model_v2_json(
        source=source,
        topic=topic,
        cluster=cluster,
        llm_client=llm_client,
        model_alias=model_alias,
        extraction_mode=llm_prompt_mode,
        max_propositions=limit,
        focus_scopes=focus_scopes,
        prompt_source_text=chunk_text,
        fragment_locator_hint=fragment_locator,
        prompt_version=prompt_version,
        estimated_input_tokens=chunk_est,
        prompt_retry_suffix=prompt_retry_suffix,
        extraction_output_mode=extraction_output_mode,
        json_output_mode=json_output_mode,
        allow_output_mode_fallback=allow_output_mode_fallback,
        workbench_raw_outputs=workbench_raw_outputs,
    )
    parse_diag: dict[str, Any] | None = None
    if isinstance(try_result, tuple) and len(try_result) == 3:
        raw_rows, model_err, parse_diag = try_result
    else:
        raw_rows, model_err = try_result  # backward-compatible for monkeypatched tests

    if parse_diag:
        for key in (
            "extraction_output_mode",
            "response_format_type",
            "schema_hash",
            "response_format",
            "json_output_mode",
        ):
            if key in parse_diag:
                trace[key] = parse_diag[key]
    if "extraction_output_mode" not in trace:
        trace["extraction_output_mode"] = extraction_output_mode or json_output_mode or "json_object"
    trace["llm_invoked"] = True
    raw_model_output: str | None = None
    if workbench_raw_outputs:
        raw_model_output = workbench_raw_outputs[-1]
    elif isinstance(parse_diag, dict):
        excerpt = parse_diag.get("raw_model_output_excerpt")
        if isinstance(excerpt, str) and excerpt.strip():
            raw_model_output = excerpt

    if model_err:
        valerrs = [f"{chunk_label}: {model_err}"]
        trace["llm_call_succeeded"] = False
        failure_type: str | None = None
        if parse_diag:
            trace.update(parse_diag)
            failure_type = str(parse_diag.get("failure_type") or "") or None
        else:
            trace["model_error"] = model_err
        raw_model_output = str(trace.get("raw_model_output_excerpt") or "") or None
        repairable_halt = (
            model_error_policy == "stop_repairable" and _looks_like_infra_llm_failure(model_err)
        )
        return _ChunkLlmAttemptOutcome(
            validated_rows=[],
            model_err=model_err,
            failure_type=failure_type,
            raw_model_output=raw_model_output,
            repairable_halt=repairable_halt,
            valerrs=valerrs,
        )

    assert raw_rows is not None
    if parse_diag:
        trace.update(
            {k: v for k, v in parse_diag.items() if k not in trace or trace[k] is None}
        )
    v_rows, verrs, row_issues = _validate_v2_items(raw_rows, chunk_text, limit=limit)
    valerrs = [f"{chunk_label}: {x}" for x in verrs]
    if raw_rows and not v_rows:
        pf_type = POST_FILTER_REMOVED_ALL
        pf_reason = f"model produced {len(raw_rows)} candidate row(s) but validation removed all"
        valerrs.append(f"{chunk_label}: {pf_reason}")
        trace.update(
            build_llm_failure_trace_fields(
                raw=raw_model_output,
                failure_type=pf_type,
                failure_reason=pf_reason,
                model_alias=str(model_alias or ""),
                prompt_version=prompt_version,
                prompt_text=_v2_model_prompt(
                    source,
                    topic,
                    cluster,
                    extraction_mode=llm_prompt_mode,
                    max_propositions=limit,
                    focus_scopes=focus_scopes,
                    prompt_source_text=chunk_text,
                    fragment_locator_hint=fragment_locator,
                ),
                fragment_locator=fragment_locator,
                estimated_input_tokens=chunk_est,
                finish_reason=(
                    str(parse_diag.get("finish_reason"))
                    if isinstance(parse_diag, dict) and parse_diag.get("finish_reason")
                    else None
                ),
                candidate_row_count=len(raw_rows),
                accepted_row_count=0,
            )
        )
        trace["llm_call_succeeded"] = False
        return _ChunkLlmAttemptOutcome(
            validated_rows=[],
            model_err=pf_reason,
            failure_type=pf_type,
            raw_model_output=raw_model_output,
            issue_records=row_issues,
            valerrs=valerrs,
        )

    trace["llm_call_succeeded"] = bool(v_rows)
    return _ChunkLlmAttemptOutcome(
        validated_rows=v_rows,
        model_err=None,
        failure_type=None,
        raw_model_output=raw_model_output,
        issue_records=row_issues,
        valerrs=valerrs,
    )


def _stamp_props_meta(
    props: list[Proposition],
    *,
    extraction_mode: str,
    model_alias: str | None,
    fallback_policy: str,
    fallback_used: bool,
    validation_errors: list[str],
    prompt_version: str,
    schema_version: str,
    extra_per_prop: list[dict[str, Any]] | None = None,
    pipeline_signals: dict[str, Any] | None = None,
) -> None:
    pipe = dict(pipeline_signals or {})
    trace_only = {
        k: pipe.pop(k) for k in list(pipe.keys()) if k in _TRACE_ONLY_PIPELINE_META_KEYS
    }
    for i, p in enumerate(props):
        ex = dict(extra_per_prop[i]) if extra_per_prop and i < len(extra_per_prop) else {}
        meta = {
            "extraction_mode": extraction_mode,
            "model_alias": model_alias,
            "fallback_policy": fallback_policy,
            "fallback_used": fallback_used,
            "validation_errors": list(validation_errors),
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            **pipe,
            **ex,
        }
        assign_proposition_extraction_debug(p, meta)
    del trace_only  # chunk-level traces live on ExtractSourceResult.extraction_llm_call_traces


def _build_propositions_from_v2_rows(
    *,
    rows: list[dict[str, Any]],
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    limit: int,
    id_sequence_start: int = 1,
) -> list[Proposition]:
    out: list[Proposition] = []
    frag_id: str | None = None
    if isinstance(source.metadata, dict) and source.metadata.get("extraction_fragment_id") is not None:
        frag_id = str(source.metadata["extraction_fragment_id"])
    # When standalone derogation propositions exist for this fragment, do not also fold
    # exceptions[] into opaque ``exception: …`` conditions on sibling propositions.
    standalone_derogation = rows_include_standalone_derogation(rows)
    for offset, item in enumerate(rows[:limit]):
        index = id_sequence_start + offset
        ptxt = str(item.get("proposition_text") or "").strip()
        subject = str(item.get("subject") or "").strip() or _guess_subject(ptxt)
        rule = str(item.get("rule") or "").strip() or _guess_action(ptxt)
        obj = str(item.get("object") or "").strip()
        affected = [obj] if obj else [subject]
        conditions = [str(x) for x in item.get("conditions") or [] if str(x).strip()]
        conditions = fold_exceptions_for_row(
            row=item,
            conditions=conditions,
            fragment_has_standalone_derogation=standalone_derogation,
        )
        tc = item.get("temporal_condition")
        if isinstance(tc, str) and tc.strip():
            conditions.append(f"temporal: {tc.strip()}")
        locator = str(item.get("source_locator") or "").strip()
        frag_loc = locator if locator else (source.authoritative_locator or None)
        art = (
            _extract_reference_from_locator(frag_loc)
            if frag_loc and not _is_placeholder_locator(frag_loc)
            else _extract_article_reference(ptxt)
        )
        label = str(item.get("display_label") or "").strip()
        reason_tail = str(item.get("reason") or "").strip()
        extraction_dbg: dict[str, Any] = {}
        if label:
            extraction_dbg["display_label"] = label
        struct_meta = item.get("_structured_list_meta")
        if isinstance(struct_meta, dict):
            extraction_dbg.update(
                {
                    k: struct_meta[k]
                    for k in (
                        "composition_basis",
                        "parent_context",
                        "branch_context",
                        "list_marker",
                        "structured_list_path",
                        "source_component_locators",
                        "provision_type",
                        "structured_list_dedupe",
                    )
                    if k in struct_meta
                }
            )
        if item.get("_composition_basis"):
            extraction_dbg.setdefault("composition_basis", item.get("_composition_basis"))
        if isinstance(item.get("_structured_list_dedupe"), dict):
            extraction_dbg.setdefault(
                "structured_list_dedupe", item.get("_structured_list_dedupe")
            )
        cand_id = str(item.get("_extraction_candidate_id") or "").strip()
        if cand_id:
            extraction_dbg["extraction_candidate_id"] = cand_id
        origin = str(item.get("_structured_list_candidate_origin") or "").strip()
        if origin:
            extraction_dbg["structured_list_candidate_origin"] = origin
        xref_targets: list[str] = []
        prop = Proposition(
            id=f"prop-{_proposition_id_stem(source)}-{index:03d}",
            topic_id=topic.id,
            cluster_id=cluster.id,
            source_record_id=source.id,
            source_fragment_id=frag_id,
            fragment_locator=frag_loc if frag_loc else source.authoritative_locator,
            source_snapshot_id=source.current_snapshot_id,
            jurisdiction=source.jurisdiction,
            article_reference=art,
            proposition_text=ptxt,
            label=label,
            short_name="",
            legal_subject=subject,
            action=rule,
            conditions=conditions,
            authority=_guess_authority(ptxt),
            required_documents=_guess_required_documents(ptxt),
            affected_subjects=affected,
            notes="",
            review_notes=reason_tail or None,
            extraction_debug_meta=extraction_dbg or None,
            explicit_cross_reference_targets=xref_targets,
        )
        out.append(prop)
    return out


def extract_propositions_from_source(
    source: SourceRecord,
    topic: Topic,
    cluster: Cluster,
    *,
    llm_client: JuditLLMClient | None,
    limit: int,
    extraction_mode: Literal["heuristic", "local", "frontier"],
    extraction_fallback: Literal["fallback", "fail_closed", "mark_needs_review"],
    prompt_version: str = EXTRACTION_PROMPT_VERSION,
    on_before_llm_call: Callable[[dict[str, Any]], None] | None = None,
    focus_scopes: Sequence[str] | None = None,
    model_error_policy: Literal[
        "continue_with_fallback", "stop_repairable", "continue_repairable"
    ] = "continue_with_fallback",
    derived_chunk_cache: DerivedArtifactCache | None = None,
    retry_failed_llm: bool = False,
    retry_empty_extraction: bool = True,
    retry_empty_extraction_transport: bool = False,
    chunk_cache_pipeline_version: str = "0.1.0",
    chunk_cache_strategy_version: str = "v1",
    extraction_output_mode: ExtractionOutputMode | str | None = None,
    json_output_mode: Literal["json_object", "json_schema"] | None = None,
    allow_output_mode_fallback: bool = False,
    workbench_capture: dict[str, Any] | None = None,
) -> ExtractSourceResult:
    scope_signals: dict[str, Any] = {}
    workbench_raw_outputs: list[str] | None = None
    if workbench_capture is not None:
        workbench_raw_outputs = []
        workbench_capture["raw_model_outputs"] = workbench_raw_outputs
    if focus_scopes:
        cleaned_fs = [str(s).strip() for s in focus_scopes if str(s).strip()]
        if cleaned_fs:
            scope_signals["focus_scopes"] = cleaned_fs

    def _merge_signals(extra: dict[str, Any] | None) -> dict[str, Any] | None:
        if not scope_signals and not extra:
            return None
        merged = dict(scope_signals)
        if extra:
            merged.update(extra)
        return merged

    base_kwargs = dict(
        extraction_mode=extraction_mode,
        fallback_policy=extraction_fallback,
        prompt_version=prompt_version,
    )
    if extraction_mode == "heuristic":
        props = _heuristic_extraction(source=source, topic=topic, cluster=cluster, limit=limit)
        _stamp_props_meta(
            props,
            model_alias=None,
            fallback_used=False,
            validation_errors=[],
            schema_version="none",
            pipeline_signals=_merge_signals(None),
            **base_kwargs,
        )
        return ExtractSourceResult(
            propositions=props,
            model_alias=None,
            fallback_used=False,
            validation_errors=[],
            schema_version="none",
            validation_issue_records=[],
            extraction_llm_call_traces=[],
            **base_kwargs,
        )

    settings = llm_client.settings if llm_client is not None else None
    model_alias_early = (
        settings.frontier_extract_model
        if extraction_mode == "frontier" and settings is not None
        else (settings.local_extract_model if settings is not None else None)
    )
    configured_ctx_limit = (
        int(getattr(settings, "extract_model_context_limit", 200_000)) if settings is not None else None
    )

    def _early_skip_trace(skip_reason: str) -> dict[str, Any]:
        fid = None
        if isinstance(source.metadata, dict):
            raw_f = source.metadata.get("extraction_fragment_id")
            if raw_f is not None:
                fid = str(raw_f)
        return {
            "source_record_id": source.id,
            "source_title": source.title,
            "source_fragment_id": fid,
            "fragment_locator": source.authoritative_locator,
            "model_alias": model_alias_early,
            "configured_context_limit": configured_ctx_limit,
            "extraction_mode": extraction_mode,
            "skipped_llm": True,
            "skip_reason": skip_reason,
            "llm_call_attempted": False,
            "llm_invoked": False,
            "llm_call_succeeded": False,
            "extraction_llm_chunk_index": 0,
            "extraction_llm_chunk_total": 0,
            "extraction_chunk_split_strategy": "none",
        }

    preflight_err: str | None = None
    preflight_skip: str | None = None
    if llm_client is None:
        preflight_err = "LLM extraction requested but LiteLLM client is not configured"
        preflight_skip = "llm_client_missing"
    elif not source.authoritative_text.strip():
        preflight_err = "LLM extraction requested but source text is empty"
        preflight_skip = "empty_source_text"

    if preflight_err is not None and preflight_skip is not None:
        early_traces = [_early_skip_trace(preflight_skip)]
        if extraction_fallback == "fail_closed":
            return ExtractSourceResult(
                propositions=[],
                model_alias=model_alias_early,
                fallback_used=False,
                validation_errors=[preflight_err],
                schema_version=EXTRACTION_SCHEMA_VERSION_V2,
                failed_closed=True,
                failure_reason=preflight_err,
                validation_issue_records=[],
                extraction_llm_call_traces=early_traces,
                **base_kwargs,
            )
        if extraction_fallback == "mark_needs_review":
            props = _heuristic_extraction(source=source, topic=topic, cluster=cluster, limit=limit)
            for p in props:
                p.review_status = ReviewStatus.NEEDS_REVIEW
            val_err = [preflight_err]
            _stamp_props_meta(
                props,
                model_alias=None,
                fallback_used=True,
                validation_errors=val_err,
                schema_version="none",
                pipeline_signals=_merge_signals(None),
                **base_kwargs,
            )
            return ExtractSourceResult(
                propositions=props,
                model_alias=None,
                fallback_used=True,
                validation_errors=val_err,
                schema_version="none",
                validation_issue_records=[],
                extraction_llm_call_traces=early_traces,
                **base_kwargs,
            )
        props = _heuristic_extraction(source=source, topic=topic, cluster=cluster, limit=limit)
        _stamp_props_meta(
            props,
            model_alias=None,
            fallback_used=True,
            validation_errors=[preflight_err],
            schema_version="none",
            pipeline_signals=_merge_signals(None),
            **base_kwargs,
        )
        return ExtractSourceResult(
            propositions=props,
            model_alias=None,
            fallback_used=True,
            validation_errors=[preflight_err],
            schema_version="none",
            validation_issue_records=[],
            extraction_llm_call_traces=early_traces,
            **base_kwargs,
        )

    assert llm_client is not None
    settings = llm_client.settings
    max_input_tokens = int(getattr(settings, "max_extract_input_tokens", 150_000))
    configured_ctx_limit = int(getattr(settings, "extract_model_context_limit", 200_000))
    overlap_chars = min(8192, max(512, max_input_tokens // 40))

    model_alias = (
        settings.frontier_extract_model if extraction_mode == "frontier" else settings.local_extract_model
    )
    llm_prompt_mode: Literal["frontier", "local"] = (
        "frontier" if extraction_mode == "frontier" else "local"
    )

    extraction_llm_call_traces: list[dict[str, Any]] = []

    def _trace_row(**extra: Any) -> dict[str, Any]:
        fid = None
        if isinstance(source.metadata, dict):
            raw_f = source.metadata.get("extraction_fragment_id")
            if raw_f is not None:
                fid = str(raw_f)
        row: dict[str, Any] = {
            "source_record_id": source.id,
            "source_title": source.title,
            "source_fragment_id": fid,
            "fragment_locator": source.authoritative_locator,
            "model_alias": model_alias,
            "configured_context_limit": configured_ctx_limit,
            "extraction_mode": extraction_mode,
        }
        row.update(extra)
        return row

    full_body = source.authoritative_text.strip()
    initial_est = _estimate_extract_prompt_tokens(
        source=source,
        topic=topic,
        cluster=cluster,
        extraction_mode=llm_prompt_mode,
        max_propositions=limit,
        focus_scopes=focus_scopes,
        prompt_source_text=full_body,
        fragment_locator_hint=None,
    )

    planned_chunks: list[_PlannedExtractChunk]
    if initial_est <= max_input_tokens:
        planned_chunks = [
            _PlannedExtractChunk(
                locator=source.authoritative_locator or "document:full",
                text=full_body,
                split_strategy="single",
            )
        ]
    else:
        max_body_chars = _max_body_chars_for_extract_budget(
            source=source,
            topic=topic,
            cluster=cluster,
            extraction_mode=llm_prompt_mode,
            max_propositions=limit,
            focus_scopes=focus_scopes,
            token_budget=max_input_tokens,
        )
        planned_chunks = _plan_llm_text_chunks(
            source,
            max_body_chars=max_body_chars,
            overlap_chars=overlap_chars,
        )

    preflight_blocked: str | None = None
    if initial_est > max_input_tokens and not planned_chunks:
        preflight_blocked = (
            f"context_window_risk: prompt estimate {initial_est} exceeds "
            f"max_extract_input_tokens={max_input_tokens} and no chunks were planned"
        )
        extraction_llm_call_traces.append(
            _trace_row(
                estimated_input_tokens=initial_est,
                skipped_llm=True,
                skip_reason="context_window_risk",
                extraction_llm_chunk_index=0,
                extraction_llm_chunk_total=0,
                extraction_chunk_split_strategy="none",
                llm_invoked=False,
            )
        )

    aggregated_validated: list[dict[str, Any]] = []
    issue_records: list[dict[str, Any]] = []
    valerrs: list[str] = []
    repairable_halt = False
    repairable_halt_reason: str | None = None
    scopes_tuple = tuple(sorted(str(s).strip() for s in (focus_scopes or ()) if str(s).strip()))
    cache_authority, cache_authority_source_id = _source_authority_cache_identity(source)

    if preflight_blocked and model_error_policy == "stop_repairable":
        return ExtractSourceResult(
            propositions=[],
            model_alias=model_alias,
            fallback_used=False,
            validation_errors=[preflight_blocked],
            schema_version=EXTRACTION_SCHEMA_VERSION_V2,
            validation_issue_records=[],
            extraction_llm_call_traces=extraction_llm_call_traces,
            repairable_extraction_halt=True,
            repairable_extraction_halt_reason=preflight_blocked,
            **base_kwargs,
        )

    if preflight_blocked is None and planned_chunks:
        n_chunks = len(planned_chunks)
        for ci, planned in enumerate(planned_chunks, start=1):
            fitted = _fit_body_text_to_extract_budget(
                body=planned.text,
                source=source,
                topic=topic,
                cluster=cluster,
                extraction_mode=llm_prompt_mode,
                max_propositions=limit,
                focus_scopes=focus_scopes,
                fragment_locator_hint=planned.locator,
                max_input_tokens=max_input_tokens,
            )
            if fitted is None:
                valerrs.append(
                    f"context_window_risk: extraction chunk {ci}/{n_chunks} cannot be shaped to "
                    f"fit max_extract_input_tokens={max_input_tokens}"
                )
                extraction_llm_call_traces.append(
                    _trace_row(
                        estimated_input_tokens=-1,
                        skipped_llm=True,
                        skip_reason="context_window_risk",
                        extraction_llm_chunk_index=ci,
                        extraction_llm_chunk_total=n_chunks,
                        fragment_locator=planned.locator,
                        extraction_chunk_split_strategy=planned.split_strategy,
                        llm_invoked=False,
                    )
                )
                if model_error_policy == "stop_repairable":
                    repairable_halt = True
                    repairable_halt_reason = (
                        f"context_window_risk: extraction chunk {ci}/{n_chunks} cannot be shaped to "
                        f"fit max_extract_input_tokens={max_input_tokens}"
                    )
                    break
                continue

            chunk_text, chunk_est = fitted
            chunk_label = f"chunk {ci}/{n_chunks}"
            trace_base = dict(
                estimated_input_tokens=chunk_est,
                skipped_llm=False,
                extraction_llm_chunk_index=ci,
                extraction_llm_chunk_total=n_chunks,
                fragment_locator=planned.locator,
                extraction_chunk_split_strategy=planned.split_strategy,
                llm_invoked=False,
            )

            chunk_fp = content_hash(chunk_text)[:48]
            cache_key_str: str | None = None
            if derived_chunk_cache is not None and model_alias:
                cache_key_str = build_proposition_extraction_chunk_cache_key(
                    authority=cache_authority,
                    authority_source_id=cache_authority_source_id,
                    source_fragment_locator=planned.locator,
                    chunk_index=ci,
                    chunk_body_fingerprint=chunk_fp,
                    model_alias=str(model_alias),
                    extraction_mode=str(extraction_mode),
                    prompt_version=prompt_version,
                    focus_scopes=scopes_tuple,
                    max_propositions=limit,
                    pipeline_version=chunk_cache_pipeline_version,
                    strategy_version=chunk_cache_strategy_version,
                )
                cached_hit = derived_chunk_cache.get(
                    stage_name="proposition_extraction_chunk", cache_key=cache_key_str
                )
                if cached_hit is not None and isinstance(cached_hit.payload, dict):
                    cst = cached_hit.payload.get("chunk_status")
                    if cst == "llm_success":
                        vr = cached_hit.payload.get("validated_rows")
                        if isinstance(vr, list) and vr:
                            trace_pre = _trace_row(**trace_base, attempt_index=0)
                            trace_pre["llm_cache_hit"] = True
                            trace_pre["llm_invoked"] = False
                            trace_pre["llm_call_attempted"] = False
                            trace_pre["llm_call_succeeded"] = True
                            extraction_llm_call_traces.append(trace_pre)
                            aggregated_validated.extend(
                                [dict(r) for r in vr if isinstance(r, dict)]
                            )
                            continue
                    if cst == "failure" and not retry_failed_llm:
                        trace_pre = _trace_row(**trace_base, attempt_index=0)
                        trace_pre["llm_cache_hit"] = "failed_chunk_cached"
                        trace_pre["llm_invoked"] = False
                        trace_pre["llm_call_attempted"] = False
                        trace_pre["llm_call_succeeded"] = False
                        trace_pre["skipped_llm"] = True
                        trace_pre["skip_reason"] = "failed_chunk_cached"
                        extraction_llm_call_traces.append(trace_pre)
                        valerrs.append(f"{chunk_label}: skipped failed chunk cache entry")
                        continue

            trace_first = _trace_row(**trace_base)
            extraction_llm_call_traces.append(trace_first)
            first_outcome = _run_chunk_llm_extraction_attempt(
                trace=trace_first,
                attempt_index=0,
                previous_failure_type=None,
                source=source,
                topic=topic,
                cluster=cluster,
                llm_client=llm_client,
                model_alias=str(model_alias),
                llm_prompt_mode=llm_prompt_mode,
                limit=limit,
                focus_scopes=focus_scopes,
                chunk_text=chunk_text,
                fragment_locator=planned.locator,
                prompt_version=prompt_version,
                chunk_est=chunk_est,
                chunk_label=chunk_label,
                extraction_output_mode=extraction_output_mode,
                json_output_mode=json_output_mode,
                allow_output_mode_fallback=allow_output_mode_fallback,
                model_error_policy=model_error_policy,
                on_before_llm_call=on_before_llm_call,
                workbench_raw_outputs=workbench_raw_outputs,
            )
            valerrs.extend(first_outcome.valerrs)
            issue_records.extend(first_outcome.issue_records)

            final_outcome = first_outcome
            if (
                retry_empty_extraction
                and not first_outcome.validated_rows
                and is_empty_extraction_retry_eligible(
                    first_outcome.failure_type,
                    extraction_mode=extraction_mode,
                    retry_transport_empty=retry_empty_extraction_transport,
                )
            ):
                retry_suffix = build_empty_extraction_retry_prompt_suffix(
                    first_outcome.raw_model_output or trace_first.get("raw_model_output_excerpt")
                )
                trace_retry = _trace_row(**trace_base)
                extraction_llm_call_traces.append(trace_retry)
                retry_outcome = _run_chunk_llm_extraction_attempt(
                    trace=trace_retry,
                    attempt_index=1,
                    previous_failure_type=first_outcome.failure_type,
                    source=source,
                    topic=topic,
                    cluster=cluster,
                    llm_client=llm_client,
                    model_alias=str(model_alias),
                    llm_prompt_mode=llm_prompt_mode,
                    limit=limit,
                    focus_scopes=focus_scopes,
                    chunk_text=chunk_text,
                    fragment_locator=planned.locator,
                    prompt_version=prompt_version,
                    chunk_est=chunk_est,
                    chunk_label=chunk_label,
                    prompt_retry_suffix=retry_suffix,
                    extraction_output_mode=extraction_output_mode,
                    json_output_mode=json_output_mode,
                    allow_output_mode_fallback=allow_output_mode_fallback,
                    model_error_policy=model_error_policy,
                    on_before_llm_call=on_before_llm_call,
                    workbench_raw_outputs=workbench_raw_outputs,
                )
                valerrs.extend(retry_outcome.valerrs)
                issue_records.extend(retry_outcome.issue_records)
                final_outcome = retry_outcome

            if final_outcome.repairable_halt:
                repairable_halt = True
                repairable_halt_reason = final_outcome.model_err
                break

            if final_outcome.validated_rows:
                aggregated_validated.extend(final_outcome.validated_rows)
                if cache_key_str and derived_chunk_cache is not None and model_alias:
                    derived_chunk_cache.put(
                        stage_name="proposition_extraction_chunk",
                        cache_key=cache_key_str,
                        payload={
                            "chunk_status": "llm_success",
                            "validated_rows": final_outcome.validated_rows,
                        },
                    )
            elif cache_key_str and derived_chunk_cache is not None and model_alias:
                derived_chunk_cache.put(
                    stage_name="proposition_extraction_chunk",
                    cache_key=cache_key_str,
                    payload={
                        "chunk_status": "failure",
                        "error": final_outcome.model_err or "extraction failed",
                    },
                )
                if model_error_policy == "stop_repairable" and final_outcome.model_err:
                    if _looks_like_infra_llm_failure(final_outcome.model_err):
                        repairable_halt = True
                        repairable_halt_reason = final_outcome.model_err
                        break
                continue

    merged_validated = _merge_dedupe_validated_v2_rows(aggregated_validated, limit=limit)
    # Deterministic structured-list terminal guard: when the LLM already returned rows for a
    # structured fragment, fill any missing terminal leaves and drop stem/branch-only rows.
    # Do not invent rows here on total LLM failure — that would bypass definition/heuristic
    # fallback paths.
    source_text_for_structure = (
        source.authoritative_text if isinstance(source.authoritative_text, str) else ""
    )
    base_loc = str(source.authoritative_locator or "").strip()
    structure_drafts = draft_structured_list_leaves(source_text_for_structure, base_loc)
    structured_list_coverage_diags: list[dict[str, Any]] = []
    structured_list_decision_facts: list[dict[str, Any]] = []
    if structure_drafts and merged_validated:
        frag_id = ""
        if isinstance(source.metadata, dict) and source.metadata.get("extraction_fragment_id"):
            frag_id = str(source.metadata["extraction_fragment_id"])
        sl_identity = StructuredListIdentityContext(
            source_record_id=str(source.id or ""),
            source_snapshot_id=str(source.current_snapshot_id or ""),
            source_fragment_id=frag_id,
        )
        merged_validated, structured_list_coverage_diags, structured_list_decision_facts = (
            merge_structured_leaf_rows(
                existing_rows=merged_validated,
                drafts=structure_drafts,
                base_locator=base_loc,
                limit=limit,
                identity=sl_identity,
            )
        )
        # Attach grounded LLM call / prompt refs already available on this extract.
        llm_trace_id = ""
        for tr in extraction_llm_call_traces:
            if isinstance(tr, dict) and tr.get("llm_invoked"):
                llm_trace_id = str(tr.get("id") or tr.get("trace_id") or tr.get("cache_key") or "")
                if llm_trace_id:
                    break
        for fact in structured_list_decision_facts:
            if fact.get("candidate_origin") in {"llm", "reconciled_llm_and_draft"}:
                if llm_trace_id and not fact.get("llm_call_trace_id"):
                    fact["llm_call_trace_id"] = llm_trace_id
                if prompt_version and not fact.get("prompt_version"):
                    fact["prompt_version"] = prompt_version
                if model_alias and not fact.get("model_alias"):
                    fact["model_alias"] = model_alias
        needs_validation = [
            r for r in merged_validated if not r.get("_validated_evidence_match_strategy")
        ]
        if needs_validation:
            accepted_new, row_errs, row_issues = _validate_v2_items(
                needs_validation, source_text_for_structure, limit=limit
            )
            valerrs.extend(row_errs)
            issue_records.extend(row_issues)
            accepted_keys = {
                (
                    str(r.get("source_locator") or ""),
                    str(r.get("proposition_text") or ""),
                )
                for r in accepted_new
            }
            rebuilt: list[dict[str, Any]] = []
            for r in merged_validated:
                key = (
                    str(r.get("source_locator") or ""),
                    str(r.get("proposition_text") or ""),
                )
                if r.get("_validated_evidence_match_strategy"):
                    rebuilt.append(r)
                elif key in accepted_keys:
                    match = next(
                        (
                            a
                            for a in accepted_new
                            if (
                                str(a.get("source_locator") or ""),
                                str(a.get("proposition_text") or ""),
                            )
                            == key
                        ),
                        r,
                    )
                    # Preserve structured-list identity/meta across evidence revalidation.
                    preserved = dict(match)
                    for priv_key in (
                        "_structured_list_meta",
                        "_structured_list_dedupe",
                        "_composition_basis",
                        "_source_component_texts",
                        "_extraction_candidate_id",
                        "_structured_list_candidate_origin",
                        "_structured_list_compose_captured",
                        "_filled_from_structured_list_draft",
                    ):
                        if priv_key in r and priv_key not in preserved:
                            preserved[priv_key] = r[priv_key]
                        elif priv_key in r and not preserved.get(priv_key):
                            preserved[priv_key] = r[priv_key]
                    rebuilt.append(preserved)
            merged_validated = rebuilt[:limit]
    dependent_qualification_decision_facts: list[dict[str, Any]] = []
    dependent_qualification_diags: list[dict[str, Any]] = []
    if merged_validated:
        frag_id = ""
        if isinstance(source.metadata, dict) and source.metadata.get("extraction_fragment_id"):
            frag_id = str(source.metadata["extraction_fragment_id"])
        dq_identity = StructuredListIdentityContext(
            source_record_id=str(source.id or ""),
            source_snapshot_id=str(source.current_snapshot_id or ""),
            source_fragment_id=frag_id,
        )
        merged_validated, dependent_qualification_diags, dependent_qualification_decision_facts = (
            reconcile_dependent_qualification_rows(
                merged_validated,
                source_text=source_text_for_structure,
                identity=dq_identity,
            )
        )

    if workbench_capture is not None:
        workbench_capture["validated_rows"] = list(merged_validated)
        if structured_list_coverage_diags:
            workbench_capture["structured_list_coverage_diagnostics"] = (
                structured_list_coverage_diags
            )
        if dependent_qualification_diags:
            workbench_capture["dependent_qualification_diagnostics"] = (
                dependent_qualification_diags
            )

    blocked_reason = preflight_blocked
    if blocked_reason:
        valerrs.insert(0, blocked_reason)

    model_failed = bool(blocked_reason) or not merged_validated

    if (
        model_failed
        and repairable_halt
        and model_error_policy == "stop_repairable"
    ):
        merged_err = valerrs or [repairable_halt_reason or "model extraction halted early (repairable)"]
        return ExtractSourceResult(
            propositions=[],
            model_alias=model_alias,
            fallback_used=False,
            validation_errors=merged_err,
            schema_version=EXTRACTION_SCHEMA_VERSION_V2,
            validation_issue_records=issue_records,
            extraction_llm_call_traces=extraction_llm_call_traces,
            repairable_extraction_halt=True,
            repairable_extraction_halt_reason=repairable_halt_reason or merged_err[0],
            **base_kwargs,
        )

    if model_failed:
        definition_fb_props: list[Proposition] = []
        definition_fb_meta: list[dict[str, Any]] = []
        definition_fb_warnings: list[str] = []
        if _is_definition_provision(source.authoritative_text):
            definition_fb_props, definition_fb_meta, definition_fb_warnings = _definition_fallback_extraction(
                source=source,
                topic=topic,
                cluster=cluster,
                limit=limit,
            )
        use_definition_fallback = bool(definition_fb_props)

        if extraction_fallback == "fail_closed":
            merged_err = valerrs or ["model extraction produced no valid propositions"]
            return ExtractSourceResult(
                propositions=[],
                model_alias=model_alias,
                fallback_used=False,
                validation_errors=merged_err,
                schema_version=EXTRACTION_SCHEMA_VERSION_V2,
                failed_closed=True,
                failure_reason=merged_err[0],
                validation_issue_records=issue_records,
                extraction_llm_call_traces=extraction_llm_call_traces,
                fallback_strategy=None,
                **base_kwargs,
            )
        if extraction_fallback == "mark_needs_review":
            if use_definition_fallback:
                props = definition_fb_props
            else:
                props = _heuristic_extraction(source=source, topic=topic, cluster=cluster, limit=limit)
                for p in props:
                    p.review_status = ReviewStatus.NEEDS_REVIEW
            fb_errs = list(valerrs)
            fb_errs.extend(definition_fb_warnings)
            pipe_fb: dict[str, Any] = {}
            if issue_records:
                pipe_fb["pipeline_evidence_issue_records"] = issue_records
            if extraction_llm_call_traces:
                pipe_fb["extraction_llm_call_traces"] = extraction_llm_call_traces
            if blocked_reason and "context_window_risk" in blocked_reason:
                pipe_fb["context_window_risk"] = True
            elif valerrs and any("context_window_risk" in str(x) for x in valerrs):
                pipe_fb["context_window_risk"] = True
            if use_definition_fallback:
                pipe_fb["fallback_strategy"] = "definition_extractor"
            _stamp_props_meta(
                props,
                model_alias=model_alias,
                fallback_used=True,
                validation_errors=fb_errs,
                schema_version="none",
                extra_per_prop=definition_fb_meta if use_definition_fallback else None,
                pipeline_signals=_merge_signals(pipe_fb if pipe_fb else None),
                **base_kwargs,
            )
            return ExtractSourceResult(
                propositions=props,
                model_alias=model_alias,
                fallback_used=True,
                validation_errors=fb_errs,
                schema_version="none",
                validation_issue_records=issue_records,
                extraction_llm_call_traces=extraction_llm_call_traces,
                fallback_strategy="definition_extractor" if use_definition_fallback else "heuristic_fallback",
                **base_kwargs,
            )
        if use_definition_fallback:
            props = definition_fb_props
        else:
            props = _heuristic_extraction(source=source, topic=topic, cluster=cluster, limit=limit)
        fb_errs = list(valerrs)
        fb_errs.extend(definition_fb_warnings)
        pipe_fb2: dict[str, Any] = {}
        if issue_records:
            pipe_fb2["pipeline_evidence_issue_records"] = issue_records
        if extraction_llm_call_traces:
            pipe_fb2["extraction_llm_call_traces"] = extraction_llm_call_traces
        if blocked_reason and "context_window_risk" in blocked_reason:
            pipe_fb2["context_window_risk"] = True
        elif valerrs and any("context_window_risk" in str(x) for x in valerrs):
            pipe_fb2["context_window_risk"] = True
        if use_definition_fallback:
            pipe_fb2["fallback_strategy"] = "definition_extractor"
        _stamp_props_meta(
            props,
            model_alias=model_alias,
            fallback_used=True,
            validation_errors=fb_errs,
            schema_version="none",
            extra_per_prop=definition_fb_meta if use_definition_fallback else None,
            pipeline_signals=_merge_signals(pipe_fb2 if pipe_fb2 else None),
            **base_kwargs,
        )
        return ExtractSourceResult(
            propositions=props,
            model_alias=model_alias,
            fallback_used=True,
            validation_errors=fb_errs,
            schema_version="none",
            validation_issue_records=issue_records,
            extraction_llm_call_traces=extraction_llm_call_traces,
            fallback_strategy="definition_extractor" if use_definition_fallback else "heuristic_fallback",
            **base_kwargs,
        )

    props = _build_propositions_from_v2_rows(
        rows=merged_validated,
        source=source,
        topic=topic,
        cluster=cluster,
        limit=limit,
    )
    row_extras: list[dict[str, Any]] = []
    for r in merged_validated[: len(props)]:
        ev_raw = str(r.get("evidence_text") or "").strip()
        strat = str(r.get("_validated_evidence_match_strategy") or "")
        tw: list[str] = []
        if not ev_raw:
            tw.append("evidence_quote_empty_explained_in_reason")
        for w in r.get("_trace_warnings") or []:
            if isinstance(w, str) and w.strip():
                tw.append(w.strip())
        ex: dict[str, Any] = {
            "provision_type": r.get("provision_type"),
            "completeness_status": r.get("completeness_status"),
            "model_confidence": r.get("confidence"),
            "evidence_quote": ev_raw,
            "evidence_match_strategy": strat or (
                "empty_with_reason" if not ev_raw else "unknown"
            ),
            "trace_warnings": tw,
        }
        struct_meta = r.get("_structured_list_meta")
        if isinstance(struct_meta, dict):
            for key in (
                "composition_basis",
                "parent_context",
                "branch_context",
                "list_marker",
                "structured_list_path",
                "source_component_locators",
                "structured_list_dedupe",
            ):
                if key in struct_meta and struct_meta[key] not in (None, "", []):
                    ex[key] = struct_meta[key]
            if struct_meta.get("provision_type") and not ex.get("provision_type"):
                ex["provision_type"] = struct_meta["provision_type"]
        if r.get("_composition_basis"):
            ex.setdefault("composition_basis", r.get("_composition_basis"))
        if isinstance(r.get("_structured_list_dedupe"), dict):
            ex.setdefault("structured_list_dedupe", r.get("_structured_list_dedupe"))
        cand_id = str(r.get("_extraction_candidate_id") or "").strip()
        if cand_id:
            ex["extraction_candidate_id"] = cand_id
        origin = str(r.get("_structured_list_candidate_origin") or "").strip()
        if origin:
            ex["structured_list_candidate_origin"] = origin
        if structured_list_coverage_diags:
            ex.setdefault(
                "structured_list_coverage_diagnostics", structured_list_coverage_diags
            )
            suppression = [
                d
                for d in structured_list_coverage_diags
                if isinstance(d, dict)
                and str(d.get("code") or "")
                in {
                    "structured_list_terminal_duplicate_suppressed",
                    "structured_list_path_multiple_distinct_propositions",
                }
            ]
            if suppression:
                ex.setdefault("structured_list_dedupe_diagnostics", suppression)
        row_extras.append(ex)
    trace_errs = [e for e in valerrs if e]
    pipe_flags: dict[str, Any] = {}
    if issue_records:
        pipe_flags["pipeline_evidence_issue_records"] = issue_records
    if extraction_llm_call_traces:
        pipe_flags["extraction_llm_call_traces"] = extraction_llm_call_traces
        invoked = sum(1 for t in extraction_llm_call_traces if t.get("llm_invoked"))
        if invoked:
            pipe_flags["extraction_chunk_count"] = invoked
        ests = [
            int(t["estimated_input_tokens"])
            for t in extraction_llm_call_traces
            if isinstance(t.get("estimated_input_tokens"), int) and int(t["estimated_input_tokens"]) > 0
        ]
        if ests:
            pipe_flags["estimated_input_tokens_max"] = max(ests)
        if any(str(t.get("skip_reason") or "") == "context_window_risk" for t in extraction_llm_call_traces):
            pipe_flags["context_window_risk"] = True
    _stamp_props_meta(
        props,
        model_alias=model_alias,
        fallback_used=False,
        validation_errors=trace_errs,
        schema_version=EXTRACTION_SCHEMA_VERSION_V2,
        extra_per_prop=row_extras,
        pipeline_signals=_merge_signals(pipe_flags if pipe_flags else None),
        **base_kwargs,
    )
    return ExtractSourceResult(
        propositions=props,
        model_alias=model_alias,
        fallback_used=False,
        validation_errors=trace_errs,
        schema_version=EXTRACTION_SCHEMA_VERSION_V2,
        validation_issue_records=issue_records,
        extraction_llm_call_traces=extraction_llm_call_traces,
        repairable_extraction_halt=repairable_halt,
        repairable_extraction_halt_reason=repairable_halt_reason if repairable_halt else None,
        fallback_strategy=None,
        structured_list_decision_facts=list(structured_list_decision_facts),
        dependent_qualification_decision_facts=list(
            dependent_qualification_decision_facts
        ),
        **base_kwargs,
    )


def _split_sentences(text: str) -> list[str]:
    return _split_fragment_sentences(text)


def _looks_normative(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(word in lowered for word in _TRIGGER_WORDS)


def _guess_subject(sentence: str) -> str:
    lowered = sentence.lower()
    candidates = [
        "operator",
        "keeper",
        "authority",
        "competent authority",
        "importer",
        "exporter",
        "person",
        "member state",
        "appropriate authority",
    ]
    for candidate in candidates:
        if candidate in lowered:
            return candidate
    stripped = re.sub(
        r"^(article|section|regulation|paragraph|schedule)\s+\d+[a-z]?[.:]?\s*",
        "",
        sentence,
        flags=re.IGNORECASE,
    )
    words = stripped.split()
    return words[0].lower() if words else "actor"


def _guess_action(sentence: str) -> str:
    lowered = sentence.lower()
    patterns = [
        "must",
        "shall",
        "may",
        "must not",
        "shall not",
        "is required to",
        "are required to",
        "is prohibited from",
        "are prohibited from",
    ]
    for pattern in patterns:
        if pattern in lowered:
            after = lowered.split(pattern, 1)[1].strip(" .,:;")
            return _normalize_whitespace(after.split(".")[0])[:120]
    return _normalize_whitespace(sentence)[:120]


def _guess_conditions(sentence: str) -> list[str]:
    lowered = sentence.lower()
    markers = ["before ", "after ", "where ", "if ", "unless ", "when "]
    conditions: list[str] = []
    for marker in markers:
        if marker in lowered:
            conditions.append(marker.strip() + " " + lowered.split(marker, 1)[1].strip(" .,:;"))
    return conditions[:3]


def _guess_authority(sentence: str) -> str | None:
    lowered = sentence.lower()
    if "competent authority" in lowered:
        return "competent authority"
    if "appropriate authority" in lowered:
        return "appropriate authority"
    if "commission" in lowered:
        return "commission"
    return None


def _guess_required_documents(sentence: str) -> list[str]:
    lowered = sentence.lower()
    documents = []
    for term in ("certificate", "register", "record", "licence", "authorization", "authorisation"):
        if term in lowered:
            documents.append(term)
    return documents


def _extract_article_reference(sentence: str) -> str | None:
    match = re.search(
        r"\b((?:art(?:icle)?|section|regulation|paragraph|schedule)\.?\s*\d+[a-z]?)\b",
        sentence,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _extract_reference_from_locator(locator: str | None) -> str | None:
    if _is_placeholder_locator(locator):
        return None
    value = str(locator)
    match = re.search(
        r"(article|section|regulation|paragraph|schedule)[:/_-]?(\d+[a-z]?)",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


def _parse_json_result(raw: str):
    from .extraction_json_repair import parse_extraction_json

    return parse_extraction_json(raw)


def _parse_json(raw: str) -> dict[str, Any]:
    return _parse_json_result(raw).parsed
