"""Deterministic decomposition of structured exception/obligation lists into terminal leaves.

Governing stem + intermediate branch context + terminal leaf text are composed into one
standalone proposition per legally alternative terminal item. Prefer source structure
(line-oriented markers when present; otherwise conservative inline markers) over LLM
inference. Do not emit redundant stem-only or intermediate-branch-only propositions.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from law_proposition_extractor_pipeline.intake import slugify

# Primary letter markers (a)–(z), excluding lone (i) which is roman.
_RE_PRIMARY_LETTER = re.compile(r"\(([a-hj-z])\)", re.IGNORECASE)
# Roman list markers; tolerate CLML double-paren quirk ``(i))``.
_RE_ROMAN = re.compile(r"\(([ivxlcdm]+)\)\)?", re.IGNORECASE)
_RE_PARA_OPENER = re.compile(r"^\(?(\d+[a-z]?)\)?[.\)]?\s+", re.IGNORECASE)
_RE_PARA_FROM_LOCATOR = re.compile(r"paragraph:(\d+[a-z]?)", re.IGNORECASE)
_RE_SHALL_NOT_APPLY = re.compile(
    r"\b(?:shall|does|do)\s+not\s+apply\b",
    re.IGNORECASE,
)

_MIN_PRIMARY_SIBLINGS = 2
_ROMAN_ONLY = frozenset({"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"})

COMPOSITION_BASIS = "structured_list_leaf"
COVERAGE_DIAGNOSTIC = "structured_list_terminal_uncovered"
DUPLICATE_SUPPRESSED_DIAGNOSTIC = "structured_list_terminal_duplicate_suppressed"
MULTIPLE_DISTINCT_DIAGNOSTIC = "structured_list_path_multiple_distinct_propositions"

# Winner-selection factor names aligned with _candidate_quality_key (no numeric score).
_WINNER_FACTOR_NAMES = (
    "canonical_list_locator",
    "list_locator_form",
    "source_component_coverage",
    "leaf_in_evidence",
    "tighter_leaf_evidence",
    "stem_preserved_in_proposition",
    "branch_preserved_in_proposition",
    "cross_reference_preservation",
    "completeness_status",
    "provision_type_present",
    "fewer_unsupported_conditions",
    "draft_proximity",
    "deterministic_composition_reason",
    "stable_lexical_tie_break_locator",
    "stable_lexical_tie_break_text",
)


@dataclass(frozen=True)
class StructuredListIdentityContext:
    """Stable source identity for extraction-candidate digests."""

    source_record_id: str = ""
    source_snapshot_id: str = ""
    source_fragment_id: str = ""

# Stopwords excluded when comparing leaf/claim token overlap.
_CLAIM_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "or",
        "and",
        "to",
        "in",
        "for",
        "on",
        "with",
        "where",
        "when",
        "that",
        "this",
        "one",
        "more",
        "than",
        "shall",
        "not",
        "apply",
        "following",
        "species",
        "i.e",
        "ie",
        "paragraph",
    }
)


@dataclass(frozen=True)
class SourceComponent:
    role: str  # stem | branch | leaf
    text: str
    locator_suffix: str


@dataclass(frozen=True)
class StructuredListLeafDraft:
    """One terminal alternative composed from stem (+ optional branch) + leaf."""

    marker_label: str
    path_key: str
    standalone_text: str
    parent_intro: str
    branch_context: str
    item_tail: str
    components: tuple[SourceComponent, ...]
    is_derogation: bool
    conditions: tuple[str, ...]
    cross_reference_targets: tuple[str, ...]

    @property
    def composition_meta(self) -> dict[str, Any]:
        return {
            "composition_basis": COMPOSITION_BASIS,
            "parent_context": self.parent_intro,
            "branch_context": self.branch_context,
            "list_marker": self.marker_label,
            "structured_list_path": self.path_key,
            "source_component_locators": [
                {"role": c.role, "locator_suffix": c.locator_suffix, "text": c.text}
                for c in self.components
            ],
            "provision_type": "exception" if self.is_derogation else "core",
        }


def _normalize_ws(value: str) -> str:
    return " ".join(value.split()).strip()


def _paragraph_n_from_locator(base_locator: str) -> str | None:
    m = _RE_PARA_FROM_LOCATOR.search(base_locator or "")
    return m.group(1) if m else None


def _paragraph_n_from_text(text: str) -> str | None:
    m = _RE_PARA_OPENER.match(text.strip())
    return m.group(1) if m else None


def _is_roman_token(inner: str) -> bool:
    return inner.lower() in _ROMAN_ONLY


def _find_primary_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end_of_marker, letter) for primary letter markers in order."""
    out: list[tuple[int, int, str]] = []
    for m in _RE_PRIMARY_LETTER.finditer(text):
        letter = m.group(1).lower()
        if letter == "i":
            continue
        out.append((m.start(), m.end(), letter))
    return out


def _find_roman_spans(segment: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for m in _RE_ROMAN.finditer(segment):
        inner = m.group(1).lower()
        if not _is_roman_token(inner):
            continue
        out.append((m.start(), m.end(), inner))
    return out


def _strip_trailing_list_joiners(body: str) -> str:
    return body.strip().rstrip(";,").strip()


def _compose_effect(*, stem: str, branch: str, leaf: str) -> str:
    parts = [p for p in (stem.rstrip(":").strip(), branch.strip(), leaf.strip()) if p]
    return _normalize_ws(" ".join(parts))


def _extract_cross_refs(text: str) -> tuple[str, ...]:
    """Conservative explicit refs for typed-relationship builders."""
    refs: list[str] = []
    for m in re.finditer(
        r"\b(paragraph\s+\d+[a-z]?|article\s+\d+[a-z]?)\b",
        text,
        flags=re.IGNORECASE,
    ):
        tok = _normalize_ws(m.group(1)).lower()
        # Canonicalise casing for display-ish form used in fixtures.
        parts = tok.split()
        pretty = f"{parts[0]} {parts[1]}" if len(parts) == 2 else tok
        if pretty not in refs:
            refs.append(pretty)
    return tuple(refs)


def _stem_cross_refs_for_exception(stem: str, branch_and_leaf: str) -> tuple[str, ...]:
    """Associate exception cue with stem refs; keep other refs from the leaf/branch."""
    stem_refs = _extract_cross_refs(stem)
    other_refs = _extract_cross_refs(branch_and_leaf)
    ordered: list[str] = []
    for r in (*stem_refs, *other_refs):
        if r not in ordered:
            ordered.append(r)
    return tuple(ordered)


def draft_structured_list_leaves(
    fragment_text: str,
    base_locator: str = "",
) -> list[StructuredListLeafDraft]:
    """Compose one draft per terminal list alternative.

    Returns [] when structure is too uncertain (fewer than two primary siblings,
    malformed markers, or empty stem).
    """
    raw = fragment_text or ""
    if not raw.strip():
        return []

    # Prefer newline-oriented layout when primary markers sit at line starts;
    # otherwise parse inline markers in the collapsed text.
    lines = [_normalize_ws(ln) for ln in raw.splitlines() if ln.strip()]
    multiline_candidates = _draft_from_multiline(lines, base_locator)
    if multiline_candidates:
        return multiline_candidates

    collapsed = _normalize_ws(raw)
    return _draft_from_inline(collapsed, base_locator)


def _draft_from_multiline(
    lines: list[str],
    base_locator: str,
) -> list[StructuredListLeafDraft]:
    if len(lines) < 3:
        return []
    primary_ix: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = re.match(r"^\(([a-z])\)\s*(.*)$", ln, re.IGNORECASE)
        if not m:
            continue
        inner = m.group(1).lower()
        if inner == "i":
            continue
        primary_ix.append((i, inner))
    if len(primary_ix) < _MIN_PRIMARY_SIBLINGS:
        return []

    first_primary = primary_ix[0][0]
    para_n = (
        _paragraph_n_from_locator(base_locator)
        or _paragraph_n_from_text(" ".join(lines[: first_primary + 1]))
        or "1"
    )
    parent_intro = _normalize_ws(" ".join(lines[0:first_primary]))
    if not parent_intro:
        return []

    drafts: list[StructuredListLeafDraft] = []
    is_derogation = bool(_RE_SHALL_NOT_APPLY.search(parent_intro))

    for k, (start_i, letter) in enumerate(primary_ix):
        end_i = primary_ix[k + 1][0] if k + 1 < len(primary_ix) else len(lines)
        segment_lines = lines[start_i:end_i]
        marker_label = f"({letter})"
        path_letter = f"{para_n}-{letter.lower()}"

        prelude: list[str] = []
        first_roman_idx: int | None = None
        if len(segment_lines) > 1:
            for j in range(1, len(segment_lines)):
                if re.match(r"^\(([ivxlcdm]+)\)\s*", segment_lines[j], re.IGNORECASE):
                    first_roman_idx = j
                    break
                prelude.append(segment_lines[j])

        roman_rows: list[tuple[str, str]] = []
        if first_roman_idx is not None:
            idx = first_roman_idx
            while idx < len(segment_lines):
                mr = re.match(r"^\(([ivxlcdm]+)\)\s*(.*)$", segment_lines[idx], re.IGNORECASE)
                if mr and _is_roman_token(mr.group(1)):
                    rlab = "(" + mr.group(1).lower() + ")"
                    body_parts = [(mr.group(2) or "").strip()]
                    idx += 1
                    while idx < len(segment_lines):
                        nxt = segment_lines[idx]
                        if re.match(r"^\(([ivxlcdm]+)\)\s*", nxt, re.IGNORECASE) or re.match(
                            r"^\(([a-z])\)\s*", nxt, re.IGNORECASE
                        ):
                            break
                        body_parts.append(nxt)
                        idx += 1
                    roman_rows.append((rlab, _normalize_ws(" ".join(p for p in body_parts if p))))
                    continue
                idx += 1

        first_line_body = ""
        mf = re.match(r"^\(([a-z])\)\s*(.*)$", segment_lines[0], re.IGNORECASE)
        if mf:
            first_line_body = (mf.group(2) or "").strip()
        branch_body = _normalize_ws(
            f"{first_line_body} {' '.join(prelude)}".strip()
        )

        stem_comp = SourceComponent("stem", parent_intro, "stem")
        if roman_rows:
            for r_marker, r_body in roman_rows:
                r_body_c = _strip_trailing_list_joiners(r_body)
                path_key = slugify(f"{path_letter}-{r_marker.strip('()')}").replace("__", "_")
                standalone = _compose_effect(
                    stem=parent_intro, branch=branch_body, leaf=r_body_c
                )
                branch_comp = SourceComponent(
                    "branch", branch_body, f"point:({letter})"
                )
                leaf_comp = SourceComponent(
                    "leaf", r_body_c, f"point:({letter}):point:{r_marker}"
                )
                conds = tuple(
                    c
                    for c in (_strip_trailing_list_joiners(branch_body), r_body_c)
                    if c
                )
                drafts.append(
                    StructuredListLeafDraft(
                        marker_label=f"{marker_label}->{r_marker}",
                        path_key=path_key,
                        standalone_text=standalone,
                        parent_intro=parent_intro,
                        branch_context=branch_body,
                        item_tail=r_body_c[:400],
                        components=(stem_comp, branch_comp, leaf_comp),
                        is_derogation=is_derogation,
                        conditions=conds,
                        cross_reference_targets=_stem_cross_refs_for_exception(
                            parent_intro, f"{branch_body} {r_body_c}"
                        ),
                    )
                )
        else:
            continuation = " ".join(segment_lines[1:]) if len(segment_lines) > 1 else ""
            letter_body = _normalize_ws(f"{first_line_body} {continuation}".strip())
            letter_body = _strip_trailing_list_joiners(letter_body)
            path_key = slugify(path_letter)
            standalone = _compose_effect(stem=parent_intro, branch="", leaf=letter_body)
            leaf_comp = SourceComponent("leaf", letter_body, f"point:({letter})")
            drafts.append(
                StructuredListLeafDraft(
                    marker_label=marker_label,
                    path_key=path_key,
                    standalone_text=standalone,
                    parent_intro=parent_intro,
                    branch_context="",
                    item_tail=letter_body[:400],
                    components=(stem_comp, leaf_comp),
                    is_derogation=is_derogation,
                    conditions=(letter_body,) if letter_body else (),
                    cross_reference_targets=_stem_cross_refs_for_exception(
                        parent_intro, letter_body
                    ),
                )
            )

    return _dedupe_drafts(drafts)


def _draft_from_inline(text: str, base_locator: str) -> list[StructuredListLeafDraft]:
    primaries = _find_primary_spans(text)
    if len(primaries) < _MIN_PRIMARY_SIBLINGS:
        return []

    stem = _normalize_ws(text[: primaries[0][0]])
    # Drop leading ``(2)`` / ``2.`` from stem when present; keep legal effect wording.
    stem_body = _RE_PARA_OPENER.sub("", stem, count=1).strip() or stem
    if not stem_body:
        return []

    para_n = (
        _paragraph_n_from_locator(base_locator)
        or _paragraph_n_from_text(stem)
        or "1"
    )
    is_derogation = bool(_RE_SHALL_NOT_APPLY.search(stem_body))
    stem_comp = SourceComponent("stem", stem_body, "stem")

    drafts: list[StructuredListLeafDraft] = []
    for k, (start, end, letter) in enumerate(primaries):
        seg_end = primaries[k + 1][0] if k + 1 < len(primaries) else len(text)
        segment = text[end:seg_end]
        marker_label = f"({letter})"
        path_letter = f"{para_n}-{letter.lower()}"

        romans = _find_roman_spans(segment)
        if romans:
            branch_prelude = _normalize_ws(segment[: romans[0][0]])
            branch_prelude = _strip_trailing_list_joiners(branch_prelude)
            # Drop trailing em-dash / hyphen used before nested lists.
            branch_prelude = branch_prelude.rstrip("—–-").strip()
            branch_comp = SourceComponent(
                "branch", branch_prelude, f"point:({letter})"
            )
            for ri, (r_start, r_end, r_inner) in enumerate(romans):
                r_seg_end = romans[ri + 1][0] if ri + 1 < len(romans) else len(segment)
                r_body = _strip_trailing_list_joiners(segment[r_end:r_seg_end])
                if not r_body:
                    continue
                r_marker = f"({r_inner})"
                path_key = slugify(f"{path_letter}-{r_inner}").replace("__", "_")
                standalone = _compose_effect(
                    stem=stem_body, branch=branch_prelude, leaf=r_body
                )
                leaf_comp = SourceComponent(
                    "leaf", r_body, f"point:({letter}):point:{r_marker}"
                )
                conds = tuple(c for c in (branch_prelude, r_body) if c)
                drafts.append(
                    StructuredListLeafDraft(
                        marker_label=f"{marker_label}->{r_marker}",
                        path_key=path_key,
                        standalone_text=standalone,
                        parent_intro=stem_body,
                        branch_context=branch_prelude,
                        item_tail=r_body[:400],
                        components=(stem_comp, branch_comp, leaf_comp),
                        is_derogation=is_derogation,
                        conditions=conds,
                        cross_reference_targets=_stem_cross_refs_for_exception(
                            stem_body, f"{branch_prelude} {r_body}"
                        ),
                    )
                )
        else:
            letter_body = _strip_trailing_list_joiners(segment)
            if not letter_body:
                continue
            path_key = slugify(path_letter)
            standalone = _compose_effect(stem=stem_body, branch="", leaf=letter_body)
            leaf_comp = SourceComponent("leaf", letter_body, f"point:({letter})")
            drafts.append(
                StructuredListLeafDraft(
                    marker_label=marker_label,
                    path_key=path_key,
                    standalone_text=standalone,
                    parent_intro=stem_body,
                    branch_context="",
                    item_tail=letter_body[:400],
                    components=(stem_comp, leaf_comp),
                    is_derogation=is_derogation,
                    conditions=(letter_body,),
                    cross_reference_targets=_stem_cross_refs_for_exception(
                        stem_body, letter_body
                    ),
                )
            )

    return _dedupe_drafts(drafts)


def _dedupe_drafts(drafts: list[StructuredListLeafDraft]) -> list[StructuredListLeafDraft]:
    seen: set[str] = set()
    out: list[StructuredListLeafDraft] = []
    for d in drafts:
        key = _normalize_ws(d.standalone_text).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def terminal_path_keys(drafts: Sequence[StructuredListLeafDraft]) -> list[str]:
    return [d.path_key for d in drafts]


def drafts_cover_path(drafts: Sequence[StructuredListLeafDraft], path_key: str) -> bool:
    target = path_key.lower().replace("__", "_")
    return any(d.path_key.lower().replace("__", "_") == target for d in drafts)


def unmatched_terminal_diagnostics(
    *,
    expected: Sequence[StructuredListLeafDraft],
    covered_path_keys: Sequence[str],
    fragment_locator: str = "",
) -> list[dict[str, Any]]:
    """Emit coverage diagnostics for terminal leaves missing from extraction output."""
    covered = {k.lower().replace("__", "_") for k in covered_path_keys}
    diags: list[dict[str, Any]] = []
    for d in expected:
        key = d.path_key.lower().replace("__", "_")
        if key in covered:
            continue
        diags.append(
            {
                "code": COVERAGE_DIAGNOSTIC,
                "fragment_locator": fragment_locator,
                "structured_list_path": d.path_key,
                "list_marker": d.marker_label,
                "message": (
                    f"Structured list terminal {d.marker_label!r} "
                    f"(path {d.path_key}) uncovered by extraction"
                ),
            }
        )
    return diags


def leaf_components_traceable(
    draft: StructuredListLeafDraft,
    source_text: str,
    *,
    locate_fn,
) -> tuple[bool, list[dict[str, Any]]]:
    """True when every component text locates in source via ``locate_fn(text, source)``."""
    details: list[dict[str, Any]] = []
    all_ok = True
    for comp in draft.components:
        if not comp.text.strip():
            continue
        ok, strategy, diag = locate_fn(comp.text, source_text)
        details.append(
            {
                "role": comp.role,
                "locator_suffix": comp.locator_suffix,
                "ok": ok,
                "strategy": strategy,
                "diagnostics": diag,
            }
        )
        if not ok:
            all_ok = False
    return all_ok, details


def rows_include_standalone_derogation(rows: Sequence[dict[str, Any]]) -> bool:
    """Whether extraction already emitted standalone exception/derogation propositions."""
    for row in rows:
        pt = str(row.get("provision_type") or "").strip().lower()
        if pt == "exception":
            return True
        text = str(row.get("proposition_text") or "")
        if _RE_SHALL_NOT_APPLY.search(text):
            return True
        meta = row.get("_structured_list_meta")
        if isinstance(meta, dict) and meta.get("provision_type") == "exception":
            return True
    return False


def should_fold_exceptions_into_conditions(
    *,
    row: dict[str, Any],
    fragment_has_standalone_derogation: bool,
) -> bool:
    """Rule for exceptions[] → ``exception: …`` conditions.

    When an explicit source exception/derogation has already been emitted as one or
    more standalone derogation propositions for the fragment, do **not** also encode
    the same legal exception as an opaque ``exception: …`` condition on another
    proposition from that fragment.

    Subordinate ``exceptions[]`` still fold when no standalone derogation exists.
    On standalone derogation rows themselves, ``exceptions[]`` fold as ordinary
    factual conditions (no ``exception:`` prefix).
    """
    if not fragment_has_standalone_derogation:
        return True  # classic fold with prefix
    return False


def fold_exceptions_for_row(
    *,
    row: dict[str, Any],
    conditions: list[str],
    fragment_has_standalone_derogation: bool,
) -> list[str]:
    """Apply the exceptions[] folding rule; mutate/return conditions list."""
    exceptions = row.get("exceptions") or []
    if not exceptions:
        return conditions
    pt = str(row.get("provision_type") or "").strip().lower()
    text = str(row.get("proposition_text") or "")
    is_derogation_row = pt == "exception" or bool(_RE_SHALL_NOT_APPLY.search(text))

    if not fragment_has_standalone_derogation:
        for exc in exceptions:
            if isinstance(exc, str) and exc.strip():
                conditions.append(f"exception: {exc.strip()}")
        return conditions

    # Standalone derogations present: never add opaque exception: conditions.
    # On the derogation row, retain subordinate exception text as factual conditions.
    if is_derogation_row:
        for exc in exceptions:
            if isinstance(exc, str) and exc.strip():
                conditions.append(exc.strip())
    return conditions


def draft_to_v2_row(
    draft: StructuredListLeafDraft,
    *,
    source_locator: str,
) -> dict[str, Any]:
    """Build a v2-shaped row from a structured leaf draft (for guards / heuristic merge)."""
    # evidence_text: shortest contiguous leaf span (traceable); composition recorded separately.
    leaf_text = next((c.text for c in draft.components if c.role == "leaf"), draft.item_tail)
    return {
        "proposition_text": draft.standalone_text,
        "display_label": f"Structured list {draft.marker_label}",
        "subject": "",
        "rule": "shall not apply" if draft.is_derogation else "",
        "object": "",
        "conditions": list(draft.conditions),
        "exceptions": [],
        "temporal_condition": "",
        "provision_type": "exception" if draft.is_derogation else "core",
        "source_locator": source_locator,
        "evidence_text": leaf_text,
        "completeness_status": "complete",
        "confidence": "high",
        "reason": (
            "Deterministic structured-list leaf composition "
            f"(stem+branch+leaf); components: {[c.role for c in draft.components]}"
        ),
        "_structured_list_meta": draft.composition_meta,
        "_source_component_texts": [c.text for c in draft.components if c.text.strip()],
        "_composition_basis": COMPOSITION_BASIS,
    }


def _content_tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-z0-9%]+", _normalize_ws(text).lower())
    return {t for t in raw if t not in _CLAIM_STOPWORDS and len(t) > 1}


def _token_jaccard(a: str, b: str) -> float:
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _leaf_token_coverage(text: str, leaf: str) -> float:
    leaf_tokens = _content_tokens(leaf)
    if not leaf_tokens:
        return 0.0
    return len(leaf_tokens & _content_tokens(text)) / len(leaf_tokens)


def _extract_list_path_from_locator(locator: str) -> str | None:
    """Exact structured-list path from ``…:list:{path}`` locators (not substring)."""
    m = re.search(r"(?:^|:)list:([a-z0-9]+(?:-[a-z0-9]+)*)", (locator or "").lower())
    return m.group(1) if m else None


def _marker_compact(marker_label: str) -> str:
    return marker_label.lower().replace("->", "").replace(" ", "")


def _locator_has_exact_marker(locator: str, marker_label: str) -> bool:
    """True when locator contains marker ``(a)(i)`` without matching ``(a)(ii)`` via prefix."""
    compact = _marker_compact(marker_label)
    if not compact:
        return False
    loc = (locator or "").lower().replace(" ", "")
    idx = loc.find(compact)
    if idx < 0:
        return False
    after = loc[idx + len(compact) : idx + len(compact) + 1]
    # ``(a)(i)`` is a prefix of ``(a)(ii)`` — reject when the next char continues the roman.
    if after and after in "ivxlcdm":
        return False
    return True


def _row_matches_draft(row: dict[str, Any], draft: StructuredListLeafDraft) -> tuple[int, str]:
    """Return (score, reason) for associating a frontier row with a terminal draft."""
    loc = str(row.get("source_locator") or "")
    ptxt = _normalize_ws(str(row.get("proposition_text") or "")).lower()
    evidence = _normalize_ws(str(row.get("evidence_text") or "")).lower()
    leaf = next((c.text for c in draft.components if c.role == "leaf"), "")
    leaf_n = _normalize_ws(leaf).lower()
    path = draft.path_key.lower()

    meta = row.get("_structured_list_meta")
    if isinstance(meta, dict):
        meta_path = str(meta.get("structured_list_path") or "").strip().lower()
        if meta_path == path:
            return 200, "structured_list_meta_path"

    extracted = _extract_list_path_from_locator(loc)
    if extracted and extracted == path:
        return 180, "canonical_list_locator"

    if _locator_has_exact_marker(loc, draft.marker_label):
        return 160, "exact_marker_locator"

    if leaf_n and leaf_n in ptxt:
        return 140 + min(len(leaf_n), 40), "leaf_text_in_proposition"

    if leaf_n and leaf_n in evidence:
        return 120 + min(len(leaf_n), 40), "leaf_text_in_evidence"

    cov_prop = _leaf_token_coverage(ptxt, leaf)
    cov_ev = _leaf_token_coverage(evidence, leaf)
    cov = max(cov_prop, cov_ev)
    if cov >= 0.55:
        return int(100 + cov * 40), "leaf_token_overlap"

    return 0, ""


def _match_row_to_draft(
    row: dict[str, Any], drafts: Sequence[StructuredListLeafDraft]
) -> StructuredListLeafDraft | None:
    scored: list[tuple[int, str, StructuredListLeafDraft]] = []
    for d in drafts:
        score, reason = _row_matches_draft(row, d)
        if score > 0:
            scored.append((score, reason, d))
    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[2].path_key))
    return scored[0][2]


def _enrich_row_with_draft(row: dict[str, Any], draft: StructuredListLeafDraft) -> dict[str, Any]:
    out = dict(row)
    meta = dict(draft.composition_meta)
    existing_meta = out.get("_structured_list_meta")
    if isinstance(existing_meta, dict):
        # Draft path/components win for grounding; keep any extra audit keys from the row.
        meta = {**existing_meta, **meta}
    out["_structured_list_meta"] = meta
    out.setdefault("_source_component_texts", [c.text for c in draft.components if c.text.strip()])
    out.setdefault("_composition_basis", COMPOSITION_BASIS)
    if draft.is_derogation and not str(out.get("provision_type") or "").strip():
        out["provision_type"] = "exception"
    return out


def _same_legal_effect_shape(a: dict[str, Any], b: dict[str, Any], draft: StructuredListLeafDraft) -> bool:
    ta = _normalize_ws(str(a.get("proposition_text") or "")).lower()
    tb = _normalize_ws(str(b.get("proposition_text") or "")).lower()
    if draft.is_derogation or _RE_SHALL_NOT_APPLY.search(ta) or _RE_SHALL_NOT_APPLY.search(tb):
        return bool(_RE_SHALL_NOT_APPLY.search(ta) and _RE_SHALL_NOT_APPLY.search(tb))
    pa = str(a.get("provision_type") or "").strip().lower()
    pb = str(b.get("provision_type") or "").strip().lower()
    if pa and pb and pa == pb:
        return True
    return _token_jaccard(ta, tb) >= 0.5


def are_clear_structured_list_duplicates(
    row_a: dict[str, Any],
    row_b: dict[str, Any],
    draft: StructuredListLeafDraft,
) -> tuple[bool, str]:
    """Decide whether two path-aligned candidates duplicate the same terminal claim.

    Acceptance Article 49a ``2-a-i`` signals that establish duplicates (prop:de4afd050b06378b
    vs prop:939e14fac21b4b16):

    - both associated to the same deterministic terminal draft path ``2-a-i``;
    - both ``composition_basis == structured_list_leaf`` after draft enrichment;
    - identical ``source_component_locators`` (stem/branch/leaf) from that draft;
    - both exception/derogation ``shall not apply`` shapes targeting paragraph 1;
    - high content-token overlap on the leaf species list (mackerel, herring, …);
    - normalized proposition texts are paraphrases of the same composed stem+branch+leaf
      claim (deterministic composition vs LLM restatement), not independent operative rules;
    - evidence quotes both ground in the same leaf species span (one leaf-only, one
      branch+leaf).

    Matching ``structured_list_path`` alone is not sufficient — see
    ``structured_list_path_multiple_distinct_propositions``.
    """
    ta = _normalize_ws(str(row_a.get("proposition_text") or "")).lower()
    tb = _normalize_ws(str(row_b.get("proposition_text") or "")).lower()
    if not ta or not tb:
        return False, ""
    if ta == tb:
        return True, "identical_normalized_proposition_text"

    leaf = next((c.text for c in draft.components if c.role == "leaf"), "")
    j = _token_jaccard(ta, tb)
    leaf_a = _leaf_token_coverage(ta, leaf)
    leaf_b = _leaf_token_coverage(tb, leaf)
    same_effect = _same_legal_effect_shape(row_a, row_b, draft)
    draft_a = _token_jaccard(ta, draft.standalone_text)
    draft_b = _token_jaccard(tb, draft.standalone_text)
    # Both must look like restatements of the canonical terminal claim. Sharing leaf
    # tokens alone is not enough (a leaf can host more than one operative rule).
    both_draft_aligned = draft_a >= 0.65 and draft_b >= 0.65

    if j >= 0.85 and same_effect:
        return True, "high_proposition_text_overlap"
    if j >= 0.72 and same_effect and both_draft_aligned:
        return True, "high_proposition_text_overlap"
    if same_effect and both_draft_aligned and leaf_a >= 0.55 and leaf_b >= 0.55 and j >= 0.45:
        return True, "same_terminal_leaf_claim"
    if (
        same_effect
        and both_draft_aligned
        and (ta in tb or tb in ta)
        and min(leaf_a, leaf_b) >= 0.4
    ):
        return True, "proposition_text_containment"

    ea = _normalize_ws(str(row_a.get("evidence_text") or "")).lower()
    eb = _normalize_ws(str(row_b.get("evidence_text") or "")).lower()
    leaf_n = _normalize_ws(leaf).lower()
    shared_leaf_evidence = bool(
        leaf_n
        and (
            leaf_n in ea
            or leaf_n in eb
            or max(_leaf_token_coverage(ea, leaf), _leaf_token_coverage(eb, leaf)) >= 0.55
        )
    )
    if (
        same_effect
        and both_draft_aligned
        and shared_leaf_evidence
        and leaf_a >= 0.45
        and leaf_b >= 0.45
        and j >= 0.4
    ):
        return True, "shared_leaf_evidence_and_claim"

    return False, ""


def _canonical_list_locator(base_locator: str, path_key: str) -> str:
    if base_locator:
        return f"{base_locator}:list:{path_key}"
    return f"list:{path_key}"


def _candidate_quality_key(
    row: dict[str, Any],
    draft: StructuredListLeafDraft,
    *,
    base_locator: str,
) -> tuple:
    """Higher is better. Order-independent; avoids preferring mere verbosity."""
    loc = str(row.get("source_locator") or "")
    ptxt = _normalize_ws(str(row.get("proposition_text") or "")).lower()
    evidence = _normalize_ws(str(row.get("evidence_text") or "")).lower()
    leaf = next((c.text for c in draft.components if c.role == "leaf"), "")
    leaf_n = _normalize_ws(leaf).lower()
    path = draft.path_key.lower()

    extracted = _extract_list_path_from_locator(loc)
    canonical_locator = 1 if extracted == path else 0
    # Prefer the deterministic ``:list:{path}`` form over marker locators.
    list_locator_form = 1 if f"list:{path}" in loc.lower() else 0

    meta = row.get("_structured_list_meta") if isinstance(row.get("_structured_list_meta"), dict) else {}
    components = meta.get("source_component_locators") or row.get("_source_component_texts") or []
    has_components = 1 if components else 0

    leaf_in_evidence = 1 if leaf_n and leaf_n in evidence else 0
    # Prefer tight leaf evidence over sprawling branch+leaf quotes.
    evidence_tightness = 0
    if leaf_n and leaf_n in evidence:
        evidence_tightness = max(0, 2000 - abs(len(evidence) - len(leaf_n)))

    stem_n = _normalize_ws(draft.parent_intro.rstrip(":")).lower()
    has_stem = 1 if stem_n and stem_n[:48] in ptxt else (1 if "shall not apply" in ptxt else 0)
    branch_n = _normalize_ws(draft.branch_context).lower()
    has_branch = 1 if branch_n and branch_n[:40] in ptxt else 0

    xref_hits = sum(1 for x in draft.cross_reference_targets if _normalize_ws(x).lower() in ptxt)
    completeness = 1 if str(row.get("completeness_status") or "").strip().lower() == "complete" else 0
    provision = 1 if str(row.get("provision_type") or "").strip() else 0
    conds = [c for c in (row.get("conditions") or []) if str(c).strip()]
    # Prefer fewer redundant condition splits when quality is otherwise equal.
    cond_score = -len(conds)

    draft_overlap = _token_jaccard(ptxt, draft.standalone_text)
    # Soft preference for text close to the canonical draft, not longest paraphrase.
    draft_proximity = int(draft_overlap * 1000)

    reason = _normalize_ws(str(row.get("reason") or "")).lower()
    deterministic_reason = 1 if "deterministic structured-list leaf composition" in reason else 0

    # Stable lexical tie-break (must be last).
    return (
        canonical_locator,
        list_locator_form,
        has_components,
        leaf_in_evidence,
        evidence_tightness,
        has_stem,
        has_branch,
        xref_hits,
        completeness,
        provision,
        cond_score,
        draft_proximity,
        deterministic_reason,
        loc.lower(),
        ptxt,
    )


def select_structured_list_duplicate_winner(
    candidates: Sequence[dict[str, Any]],
    draft: StructuredListLeafDraft,
    *,
    base_locator: str,
) -> dict[str, Any]:
    """Deterministic winner for a clear-duplicate set (independent of input order)."""
    return max(
        candidates,
        key=lambda r: _candidate_quality_key(r, draft, base_locator=base_locator),
    )


def infer_structured_list_candidate_origin(row: Mapping[str, Any] | dict[str, Any]) -> str:
    """Classify how a retained/suppressed row entered structured-list reconciliation."""
    explicit = str(row.get("_structured_list_candidate_origin") or "").strip()
    if explicit:
        return explicit
    reason = _normalize_ws(str(row.get("reason") or "")).lower()
    if "deterministic structured-list leaf composition" in reason:
        return "deterministic_draft"
    if row.get("_filled_from_structured_list_draft"):
        return "deterministic_draft"
    return "llm"


def extraction_candidate_id(
    *,
    row: Mapping[str, Any] | dict[str, Any],
    structured_list_path: str,
    identity: StructuredListIdentityContext | None = None,
    candidate_origin: str | None = None,
) -> str:
    """Deterministic ``extractcand:<digest>`` identity (order-independent).

    Material identity excludes display summaries and list indices.
    """
    ident = identity or StructuredListIdentityContext()
    origin = candidate_origin or infer_structured_list_candidate_origin(row)
    meta = row.get("_structured_list_meta") if isinstance(row.get("_structured_list_meta"), dict) else {}
    components = meta.get("source_component_locators") or []
    locator_parts = sorted(
        {
            f"{c.get('role')}:{c.get('locator_suffix')}"
            for c in components
            if isinstance(c, dict) and (c.get("role") or c.get("locator_suffix"))
        }
    )
    path = str(structured_list_path or meta.get("structured_list_path") or "").strip().lower()
    payload = "\x1f".join(
        (
            str(ident.source_record_id or ""),
            str(ident.source_snapshot_id or ""),
            str(ident.source_fragment_id or ""),
            path,
            _normalize_ws(str(row.get("proposition_text") or "")).lower(),
            _normalize_ws(str(row.get("evidence_text") or "")).lower(),
            str(row.get("source_locator") or "").strip().lower(),
            origin,
            *locator_parts,
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"extractcand:{digest}"


def _stamp_candidate_id(
    row: dict[str, Any],
    *,
    path: str,
    identity: StructuredListIdentityContext | None,
) -> str:
    existing = str(row.get("_extraction_candidate_id") or "").strip()
    if existing.startswith("extractcand:"):
        return existing
    origin = infer_structured_list_candidate_origin(row)
    cid = extraction_candidate_id(
        row=row,
        structured_list_path=path,
        identity=identity,
        candidate_origin=origin,
    )
    row["_extraction_candidate_id"] = cid
    row["_structured_list_candidate_origin"] = origin
    return cid


def winner_selection_factors(
    winner: dict[str, Any],
    losers: Sequence[dict[str, Any]],
    draft: StructuredListLeafDraft,
    *,
    base_locator: str,
) -> list[str]:
    """Grounded quality dimensions where the winner outranked at least one loser."""
    wkey = _candidate_quality_key(winner, draft, base_locator=base_locator)
    factors: set[str] = set()
    for loser in losers:
        lkey = _candidate_quality_key(loser, draft, base_locator=base_locator)
        for idx, name in enumerate(_WINNER_FACTOR_NAMES):
            if idx >= len(wkey) or idx >= len(lkey):
                break
            if wkey[idx] > lkey[idx]:
                factors.add(name)
    if not factors:
        factors.add("stable_lexical_tie_break_locator")
    return sorted(factors)


def _component_locators_for_draft(draft: StructuredListLeafDraft) -> list[dict[str, Any]]:
    return [
        {"role": c.role, "locator_suffix": c.locator_suffix, "text": c.text}
        for c in draft.components
    ]


def _stem_branch_role(ptxt: str, drafts: Sequence[StructuredListLeafDraft]) -> str:
    """Return ``stem`` or ``branch`` for a row already classified as non-terminal."""
    if not drafts:
        return "non_terminal"

    def _norm(s: str) -> str:
        return _normalize_ws(s).lower()

    stem = _norm(drafts[0].parent_intro)
    if ptxt == stem or (stem and ptxt.startswith(stem) and len(ptxt) < len(stem) + 20):
        leaf_hits = 0
        for d in drafts:
            leaf = next((c.text for c in d.components if c.role == "leaf"), "")
            if leaf and _norm(leaf) in ptxt:
                leaf_hits += 1
        if leaf_hits == 0:
            return "stem"
    return "branch"


def reconcile_structured_list_path_candidates(
    *,
    candidates: Sequence[dict[str, Any]],
    draft: StructuredListLeafDraft,
    base_locator: str,
    fragment_locator: str = "",
    identity: StructuredListIdentityContext | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Collapse clear duplicates for one terminal; preserve genuinely distinct claims.

    Returns ``(retained_rows, diagnostics, decision_facts)``.
    """
    if len(candidates) <= 1:
        return list(candidates), [], []

    # Union-find style grouping via pairwise clear-duplicate relation.
    groups: list[list[dict[str, Any]]] = []
    for cand in candidates:
        placed = False
        for group in groups:
            if all(are_clear_structured_list_duplicates(cand, member, draft)[0] for member in group):
                group.append(cand)
                placed = True
                break
        if not placed:
            groups.append([cand])

    retained: list[dict[str, Any]] = []
    diags: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    frag = fragment_locator or base_locator
    ident = identity or StructuredListIdentityContext()

    for group in groups:
        if len(group) == 1:
            retained.append(group[0])
            continue
        winner = select_structured_list_duplicate_winner(
            group, draft, base_locator=base_locator
        )
        suppressed = [r for r in group if r is not winner]
        # Prove duplicate evidence using the first suppressed pair signal.
        _ok, basis = are_clear_structured_list_duplicates(winner, suppressed[0], draft)
        winner = dict(winner)
        winner_id = _stamp_candidate_id(winner, path=draft.path_key, identity=ident)
        suppressed_rows: list[dict[str, Any]] = []
        suppressed_ids: list[str] = []
        for loser in suppressed:
            loser_row = dict(loser)
            loser_id = _stamp_candidate_id(loser_row, path=draft.path_key, identity=ident)
            suppressed_rows.append(loser_row)
            suppressed_ids.append(loser_id)
        factors = winner_selection_factors(
            winner, suppressed_rows, draft, base_locator=base_locator
        )
        origins = {
            infer_structured_list_candidate_origin(winner),
            *(infer_structured_list_candidate_origin(r) for r in suppressed_rows),
        }
        if "llm" in origins and "deterministic_draft" in origins:
            winner["_structured_list_candidate_origin"] = "reconciled_llm_and_draft"
        group_id = f"sldupe:{draft.path_key}:{slugify(winner_id)[:24]}"
        dedupe_meta = {
            "duplicate_group_id": group_id,
            "dedupe_reason": "duplicate_structured_list_terminal",
            "structured_list_path": draft.path_key,
            "retained_candidate_id": winner_id,
            "suppressed_candidate_ids": suppressed_ids,
            "duplicate_basis": basis or "same_terminal_leaf_claim",
            "winner_selection_factors": factors,
        }
        winner["_structured_list_dedupe"] = dedupe_meta
        # Surface on composition meta for extraction_debug_meta propagation.
        meta = dict(winner.get("_structured_list_meta") or {})
        meta["structured_list_dedupe"] = dedupe_meta
        winner["_structured_list_meta"] = meta
        retained.append(winner)
        for loser_row, loser_id in zip(suppressed_rows, suppressed_ids, strict=True):
            diags.append(
                {
                    "code": DUPLICATE_SUPPRESSED_DIAGNOSTIC,
                    "fragment_locator": frag,
                    "structured_list_path": draft.path_key,
                    "list_marker": draft.marker_label,
                    "retained_candidate_id": winner_id,
                    "suppressed_candidate_id": loser_id,
                    "retained_source_locator": str(winner.get("source_locator") or ""),
                    "suppressed_source_locator": str(loser_row.get("source_locator") or ""),
                    "duplicate_basis": basis or "same_terminal_leaf_claim",
                    "dedupe_reason": "duplicate_structured_list_terminal",
                    "winner_selection_factors": factors,
                    "message": (
                        f"Suppressed duplicate structured-list terminal {draft.marker_label!r} "
                        f"(path {draft.path_key}); retained {winner_id!r}"
                    ),
                }
            )
            facts.append(
                {
                    "fact_kind": "suppress_duplicate_terminal",
                    "structured_list_path": draft.path_key,
                    "retained_candidate_id": winner_id,
                    "suppressed_candidate_id": loser_id,
                    "duplicate_basis": basis or "same_terminal_leaf_claim",
                    "winner_selection_factors": factors,
                    "source_record_id": ident.source_record_id,
                    "source_snapshot_id": ident.source_snapshot_id,
                    "source_fragment_id": ident.source_fragment_id,
                    "base_locator": frag,
                    "outcome": "suppressed_as_duplicate_terminal",
                }
            )

    if len(retained) > 1:
        retained_ids = [
            _stamp_candidate_id(r if isinstance(r, dict) else dict(r), path=draft.path_key, identity=ident)
            for r in retained
        ]
        # Ensure stamped ids live on retained row objects.
        for row, cid in zip(retained, retained_ids, strict=True):
            row["_extraction_candidate_id"] = cid
        diags.append(
            {
                "code": MULTIPLE_DISTINCT_DIAGNOSTIC,
                "fragment_locator": frag,
                "structured_list_path": draft.path_key,
                "list_marker": draft.marker_label,
                "candidate_ids": retained_ids,
                "candidate_source_locators": [
                    str(r.get("source_locator") or "") for r in retained
                ],
                "reason": (
                    "Multiple candidates share a structured-list terminal path but state "
                    "genuinely different operative claims; not safely collapsed."
                ),
                "message": (
                    f"Structured list path {draft.path_key} retained {len(retained)} "
                    "distinct propositions"
                ),
            }
        )
        facts.append(
            {
                "fact_kind": "preserve_distinct_terminal_claims",
                "structured_list_path": draft.path_key,
                "candidate_ids": retained_ids,
                "preserve_reason": "safe_duplicate_suppression_not_established",
                "source_record_id": ident.source_record_id,
                "source_snapshot_id": ident.source_snapshot_id,
                "source_fragment_id": ident.source_fragment_id,
                "base_locator": frag,
                "outcome": "retained_distinct_same_path_claims",
            }
        )

    return retained, diags, facts


def merge_structured_leaf_rows(
    *,
    existing_rows: list[dict[str, Any]],
    drafts: Sequence[StructuredListLeafDraft],
    base_locator: str,
    limit: int,
    identity: StructuredListIdentityContext | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Ensure every terminal draft is represented; reconcile duplicate path candidates.

    Flow: associate frontier rows with terminal paths → reconcile clear duplicates per
    path → fill missing terminals from drafts → append non-structured rows.

    Within one source fragment extraction, one structured terminal normally yields one
    retained row. Clear duplicates of the same leaf claim are collapsed deterministically;
    genuinely distinct claims sharing a path are preserved with a diagnostic.

    Returns ``(rows, diagnostics, decision_facts)``.
    """
    if not drafts:
        return existing_rows[:limit], [], []

    ident = identity or StructuredListIdentityContext()
    path_buckets: dict[str, list[dict[str, Any]]] = {d.path_key.lower(): [] for d in drafts}
    non_structured: list[dict[str, Any]] = []
    diags: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    associated_paths = [d.path_key for d in drafts]

    for row in existing_rows:
        ptxt = _normalize_ws(str(row.get("proposition_text") or "")).lower()
        if _is_stem_or_branch_only_row(ptxt, drafts):
            role = _stem_branch_role(ptxt, drafts)
            rejected = dict(row)
            # Path used for identity: associated primary path when known.
            path_for_id = associated_paths[0] if associated_paths else ""
            cand_id = _stamp_candidate_id(rejected, path=path_for_id, identity=ident)
            facts.append(
                {
                    "fact_kind": "reject_non_terminal_row",
                    "candidate_id": cand_id,
                    "component_role": role,
                    "associated_terminal_paths": list(associated_paths),
                    "rejection_reason": "represented_through_terminal_compositions",
                    "source_record_id": ident.source_record_id,
                    "source_snapshot_id": ident.source_snapshot_id,
                    "source_fragment_id": ident.source_fragment_id,
                    "base_locator": base_locator,
                    "outcome": "not_retained_as_standalone_proposition",
                }
            )
            continue
        matched = _match_row_to_draft(row, drafts)
        if matched is None:
            non_structured.append(dict(row))
            continue
        enriched = _enrich_row_with_draft(row, matched)
        _stamp_candidate_id(enriched, path=matched.path_key, identity=ident)
        path_buckets[matched.path_key.lower()].append(enriched)

    ordered: list[dict[str, Any]] = []
    for d in drafts:
        key = d.path_key.lower()
        candidates = path_buckets.get(key) or []
        if not candidates:
            filled = draft_to_v2_row(
                d, source_locator=_canonical_list_locator(base_locator, d.path_key)
            )
            filled["_filled_from_structured_list_draft"] = True
            filled["_structured_list_candidate_origin"] = "deterministic_draft"
            _stamp_candidate_id(filled, path=d.path_key, identity=ident)
            ordered.append(filled)
            continue
        retained, path_diags, path_facts = reconcile_structured_list_path_candidates(
            candidates=candidates,
            draft=d,
            base_locator=base_locator,
            fragment_locator=base_locator,
            identity=ident,
        )
        diags.extend(path_diags)
        facts.extend(path_facts)
        ordered.extend(retained)

    ordered.extend(non_structured)

    truncated = ordered[:limit]
    covered_after: set[str] = set()
    drafts_by_path = {d.path_key.lower(): d for d in drafts}
    for row in truncated:
        meta = row.get("_structured_list_meta")
        matched = _match_row_to_draft(row, drafts)
        if isinstance(meta, dict) and meta.get("structured_list_path"):
            covered_after.add(str(meta["structured_list_path"]).lower())
        if matched is not None:
            covered_after.add(matched.path_key.lower())
        if not isinstance(meta, dict) or not meta.get("structured_list_path"):
            continue
        path = str(meta["structured_list_path"])
        draft = drafts_by_path.get(path.lower())
        cid = _stamp_candidate_id(row, path=path, identity=ident)
        components = list(meta.get("source_component_locators") or [])
        if not components and draft is not None:
            components = _component_locators_for_draft(draft)
        origin = infer_structured_list_candidate_origin(row)
        facts.append(
            {
                "fact_kind": "compose_terminal_leaf",
                "candidate_id": cid,
                "structured_list_path": path,
                "composition_basis": str(meta.get("composition_basis") or COMPOSITION_BASIS),
                "source_component_locators": components,
                "candidate_origin": origin,
                "source_record_id": ident.source_record_id,
                "source_snapshot_id": ident.source_snapshot_id,
                "source_fragment_id": ident.source_fragment_id,
                "base_locator": base_locator,
                "outcome": "retained_as_terminal_proposition",
                "retained_candidate_id": cid,
            }
        )
        row["_structured_list_compose_captured"] = True
    coverage_diags = unmatched_terminal_diagnostics(
        expected=drafts,
        covered_path_keys=list(covered_after),
        fragment_locator=base_locator,
    )
    diags.extend(coverage_diags)
    return truncated, diags, facts


def _is_stem_or_branch_only_row(ptxt: str, drafts: Sequence[StructuredListLeafDraft]) -> bool:
    if not drafts:
        return False

    def _norm(s: str) -> str:
        return _normalize_ws(s).lower()

    stem = _norm(drafts[0].parent_intro)
    if ptxt == stem or (stem and ptxt.startswith(stem) and len(ptxt) < len(stem) + 20):
        # Likely stem-only if no leaf distinctive text.
        leaf_hits = 0
        for d in drafts:
            leaf = next((c.text for c in d.components if c.role == "leaf"), "")
            if leaf and _norm(leaf) in ptxt:
                leaf_hits += 1
        if leaf_hits == 0:
            return True
    # Intermediate branch (a) without a specific roman leaf.
    for d in drafts:
        branch = _norm(d.branch_context)
        if not branch:
            continue
        if ptxt == branch or (branch and branch in ptxt and len(ptxt) < len(branch) + 40):
            leaf = next((c.text for c in d.components if c.role == "leaf"), "")
            if leaf and _norm(leaf) not in ptxt:
                return True
    return False
