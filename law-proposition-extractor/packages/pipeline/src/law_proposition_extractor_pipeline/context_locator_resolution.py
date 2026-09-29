"""Deterministic locator resolution aligned with Review Workbench context-locator-resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

LocatorKind = Literal[
    "regulation",
    "schedule",
    "article",
    "part",
    "annex",
    "paragraph",
    "rule",
    "sub-paragraph",
]

LOCATOR_KINDS: frozenset[str] = frozenset(
    {"regulation", "schedule", "article", "part", "annex", "paragraph", "rule"}
)

STRUCTURAL_CONTAINER_KINDS: frozenset[str] = frozenset(
    {"regulation", "schedule", "article", "part", "annex", "rule"}
)

INSTRUMENT_SUB_KINDS: frozenset[str] = frozenset({"regulation", "article", "schedule", "rule"})

REGULATION_LOCATOR_RE = re.compile(
    r"^(?P<kind>regulation|schedule|article|paragraph|annex|part|rule)\s*:?\s*"
    r"(?P<num>\d+[a-z]?)"
    r"(?:\s*\((?P<sub>[^)]+)\))?$",
    re.IGNORECASE,
)

COLON_PATH_RE = re.compile(
    r"^(?P<parent_kind>regulation|schedule|article|part|annex|rule):"
    r"(?P<parent_num>\d+[a-z]?):"
    r"(?P<child_kind>paragraph):"
    r"(?P<child_num>\d+[a-z]?)"
    r"(?:\((?P<child_sub>[^)]+)\))?$",
    re.IGNORECASE,
)

NESTED_COLON_PARAGRAPH_PATH_RE = re.compile(
    r"^(?P<parent_kind>regulation|schedule|article|part|annex|rule):"
    r"(?P<parent_num>\d+[a-z]?):"
    r"paragraph:(?P<paragraph_rest>.+)$",
    re.IGNORECASE,
)

NESTED_NUM_TOKEN_RE = re.compile(r"^(\d+[a-z]?)(?:\((.+)\))?$", re.IGNORECASE)

INSTRUMENT_PARENTHETICAL_RE = re.compile(
    r"^(?P<kind>regulation|schedule|article|part|rule)\s+"
    r"(?P<num>\d+[a-z]?)\((?P<inner>.+)\)$",
    re.IGNORECASE,
)

SCHEDULE_PARAGRAPH_TEXT_RE = re.compile(
    r"^(?:schedule|sch\.?)\s*(?P<schedule>\d+[a-z]?)"
    r"(?:\s*[,;]?\s*|\s+)(?:para(?:graph)?s?\s+)(?P<paragraph>\d+[a-z]?)"
    r"(?:\s*\((?P<sub>.+)\))?$",
    re.IGNORECASE,
)

REGULATION_SUB_TEXT_RE = re.compile(
    r"^(?:regulation|reg\.?|rule)\s*(?P<regulation>\d+[a-z]?)(?:\s*\((?P<sub>[^)]+)\))?$",
    re.IGNORECASE,
)

BARE_PARAGRAPH_RE = re.compile(
    r"^(?:para(?:graph)?s?)\s+(?P<num>\d+[a-z]?)(?:\s*\((?P<sub>.+)\))?$",
    re.IGNORECASE,
)

PARAGRAPH_OF_INSTRUMENT_RE = re.compile(
    r"^(?:para(?:graph)?s?)\s+"
    r"(?:"
    r"\((?P<num_paren>\d+[a-z]?)\)"  # paragraph (1) of Article 49a
    r"|"
    r"(?P<num>\d+[a-z]?)(?:\s*\((?P<sub>.+)\))?"  # paragraph 1 / paragraph 1(a) of …
    r")"
    r"\s+of\s+"
    r"(?P<kind>article|regulation|schedule|rule)\s+(?P<parent>\d+[a-z]?)$",
    re.IGNORECASE,
)

INSTRUMENT_COMMA_PARAGRAPH_RE = re.compile(
    r"^(?P<kind>article|regulation|schedule|rule)\s+(?P<num>\d+[a-z]?)\s*,\s*"
    r"(?:para(?:graph)?s?\s+)?(?P<para>\d+[a-z]?)(?:\s*\((?P<sub>.+)\))?$",
    re.IGNORECASE,
)

INSTRUMENT_CHAINED_PARENS_RE = re.compile(
    r"^(?P<kind>regulation|schedule|article|part|rule)\s+"
    r"(?P<num>\d+[a-z]?)"
    r"(?P<parens>(?:\([^()]+\))+)$",
    re.IGNORECASE,
)

LOCATOR_ANNOTATION_SUFFIX_RE = re.compile(
    r"\s*\((?:first|second|third|fourth|fifth)\s+sentence\b[^)]*\)$",
    re.IGNORECASE,
)

PARAGRAPH_RANGE_RE = re.compile(
    r"^(?:para(?:graph)?s?)\s+(?P<from>\d+[a-z]?)\s*(?:to|–|-)\s*(?P<to>\d+[a-z]?)$",
    re.IGNORECASE,
)

SUB_PARAGRAPH_RE = re.compile(r"^sub-?para(?:graph)?s?\s*\((?P<sub>[^)]+)\)$", re.IGNORECASE)

PAREN_PARAGRAPH_RE = re.compile(r"^(?:para(?:graph)?s?)\s*\((?P<sub>[^)]+)\)$", re.IGNORECASE)

BARE_POINT_RE = re.compile(r"^points?\s*\((?P<sub>[^)]+)\)$", re.IGNORECASE)

_NUMERIC_PARAGRAPH_NUM_RE = re.compile(r"^\d+[a-z]?$", re.IGNORECASE)

PART_OF_SCHEDULE_TEXT_RE = re.compile(
    r"^part\s+(?P<part>\d+[a-z]?)\s+of\s+(?:the\s+)?(?:schedule|sch\.?)\s*(?P<schedule>\d+[a-z]?)$",
    re.IGNORECASE,
)

PARTS_OF_SCHEDULE_TEXT_RE = re.compile(
    r"^parts\s+(?P<parts>.+?)\s+of\s+(?:the\s+)?(?:schedule|sch\.?)\s*(?P<schedule>\d+[a-z]?)$",
    re.IGNORECASE,
)

YEAR_LIKE_RE = re.compile(r"^(19|20)\d{2}$")

EXTERNAL_INSTRUMENT_LOCATOR_RE = re.compile(
    r"\b(?:regulation|reg\.?|article|schedule|part|rule)\s+\d+[a-z]?(?:\s*\([^)]+\))?\s+of\s+the\s+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LocatorSegment:
    kind: str
    num: str
    sub: str | None = None


@dataclass
class LocatorStructuralContext:
    segments: list[LocatorSegment] = field(default_factory=list)
    source_record_id: str | None = None


@dataclass(frozen=True)
class ParsedLocatorSingle:
    kind: Literal["single"] = "single"
    display: str = ""
    segments: tuple[LocatorSegment, ...] = ()


@dataclass(frozen=True)
class ParsedLocatorRange:
    kind: Literal["range"] = "range"
    display: str = ""
    from_num: int = 0
    to_num: int = 0
    segment_kind: Literal["paragraph"] = "paragraph"
    inherited_parent: LocatorSegment | None = None


ParsedLocatorReference = ParsedLocatorSingle | ParsedLocatorRange


@dataclass(frozen=True)
class ContainerLocatorTarget:
    display: str
    segments: tuple[LocatorSegment, ...]


@dataclass
class ResolvedContextFragment:
    fragment_id: str
    locator: str


ResolutionBasis = Literal[
    "explicit",
    "structural_relative",
    "instrument_wide",
    "unresolved",
]


@dataclass
class ContextLocatorResolution:
    resolved: bool
    review_status: Literal["accepted", "ambiguous", "unresolved"]
    resolution_status: Literal["resolved", "ambiguous", "unresolved", "partially_resolved"]
    proposition_ids: list[str]
    matched_fragment_ids: list[str]
    resolution_mode: Literal["exact", "container", "partial"] | None = None
    resolved_locator: str | None = None
    unresolved_child: str | None = None
    resolution_basis: ResolutionBasis | None = None


def _is_locator_kind(value: str) -> bool:
    return value in LOCATOR_KINDS


def _parse_nested_num_token(token: str) -> tuple[str, str | None] | None:
    match = NESTED_NUM_TOKEN_RE.match(str(token or "").strip().lower())
    if not match:
        return None
    sub = (match.group(2) or "").strip()
    return match.group(1), sub or None


def _format_nested_num_token(num: str, sub: str | None) -> str:
    if sub:
        return f"{num}({sub})"
    return num


def _paragraph_path_matches_prefix(
    frag_num: str,
    frag_sub: str | None,
    prefix_num: str,
    prefix_sub: str | None,
) -> bool:
    frag_label = _format_nested_num_token(frag_num.lower(), frag_sub.lower() if frag_sub else None)
    prefix_label = _format_nested_num_token(prefix_num.lower(), prefix_sub.lower() if prefix_sub else None)
    if frag_label == prefix_label:
        return True
    if prefix_sub is None:
        return frag_label == prefix_num.lower() or frag_label.startswith(f"{prefix_num.lower()}(")
    return frag_label.startswith(f"{prefix_label}(")


def _segment_matches_prefix(candidate: LocatorSegment, prefix: LocatorSegment) -> bool:
    if candidate.kind != prefix.kind or candidate.num != prefix.num:
        return False
    if prefix.kind == "paragraph":
        return _paragraph_path_matches_prefix(
            candidate.num,
            candidate.sub,
            prefix.num,
            prefix.sub,
        )
    return prefix.sub is None or candidate.sub == prefix.sub


def _strip_locator_annotations(raw: str) -> str:
    """Remove non-structural suffixes such as ``(first sentence)``."""
    cleaned = LOCATOR_ANNOTATION_SUFFIX_RE.sub("", str(raw or "").strip()).strip()
    return cleaned


def _split_chained_parens(parens: str) -> list[str]:
    return [part.strip().lower() for part in re.findall(r"\(([^()]+)\)", parens) if part.strip()]


def _nest_sub_labels(parts: list[str]) -> str | None:
    if not parts:
        return None
    nested = parts[0]
    for part in parts[1:]:
        nested = f"{nested}({part})"
    return nested


def _parse_parenthetical_instrument_segments(kind: str, num: str, inner: str) -> list[LocatorSegment]:
    kind = kind.lower()
    num = num.lower()
    inner = inner.strip().lower()
    # Repair chained capture ``2)(b`` from greedy single-group regexes.
    if ")(" in inner and "(" not in inner.split(")(", 1)[0]:
        parts = [p for p in inner.split(")(") if p]
        return _segments_from_instrument_paren_parts(kind, num, parts)
    if kind == "schedule":
        para_num, para_sub = _parse_nested_num_token(inner) or (inner, None)
        return [
            LocatorSegment(kind="schedule", num=num),
            LocatorSegment(kind="paragraph", num=para_num, sub=para_sub),
        ]
    if "(" not in inner:
        if kind in {"article", "regulation", "rule"} and _NUMERIC_PARAGRAPH_NUM_RE.match(inner):
            return [
                LocatorSegment(kind=kind, num=num),
                LocatorSegment(kind="paragraph", num=inner, sub=None),
            ]
        return [LocatorSegment(kind=kind, num=num, sub=inner)]
    para_num, para_sub = _parse_nested_num_token(inner) or (inner, None)
    if para_num and kind in {"article", "regulation", "rule", "schedule"}:
        return [
            LocatorSegment(kind=kind, num=num),
            LocatorSegment(kind="paragraph", num=para_num, sub=para_sub),
        ]
    return [LocatorSegment(kind=kind, num=num, sub=inner)]


def _segments_from_instrument_paren_parts(
    kind: str,
    num: str,
    parts: list[str],
) -> list[LocatorSegment]:
    kind = kind.lower()
    num = num.lower()
    if not parts:
        return [LocatorSegment(kind=kind, num=num)]
    if kind == "schedule":
        nested = _nest_sub_labels(parts) or parts[0]
        para_num, para_sub = _parse_nested_num_token(nested) or (parts[0], _nest_sub_labels(parts[1:]))
        return [
            LocatorSegment(kind="schedule", num=num),
            LocatorSegment(kind="paragraph", num=para_num, sub=para_sub),
        ]
    first = parts[0]
    if _NUMERIC_PARAGRAPH_NUM_RE.match(first):
        return [
            LocatorSegment(kind=kind, num=num),
            LocatorSegment(kind="paragraph", num=first, sub=_nest_sub_labels(parts[1:])),
        ]
    return [LocatorSegment(kind=kind, num=num, sub=_nest_sub_labels(parts))]


def _parse_colon_paragraph_path_segments(raw: str) -> list[LocatorSegment] | None:
    nested = NESTED_COLON_PARAGRAPH_PATH_RE.match(raw)
    if nested:
        para_num, para_sub = _parse_nested_num_token(nested.group("paragraph_rest")) or (
            nested.group("paragraph_rest").lower(),
            None,
        )
        return [
            LocatorSegment(
                kind=nested.group("parent_kind").lower(),
                num=nested.group("parent_num").lower(),
            ),
            LocatorSegment(kind="paragraph", num=para_num, sub=para_sub),
        ]
    return None


def _segment_key(segment: LocatorSegment) -> str:
    sub = f"({segment.sub})" if segment.sub else ""
    return f"{segment.kind} {segment.num}{sub}".lower()


def _capitalize_locator_kind(kind: str) -> str:
    return kind[0].upper() + kind[1:] if kind else kind


def _format_container_locator_label(segments: list[LocatorSegment]) -> str:
    parts = [
        f"{_capitalize_locator_kind(seg.kind)} {seg.num}{f'({seg.sub})' if seg.sub else ''}"
        for seg in segments
    ]
    return ", ".join(parts)


def _format_container_child_label(
    parent_segments: list[LocatorSegment],
    child_segment: LocatorSegment,
) -> str:
    parent_label = _format_container_locator_label(parent_segments)
    child_label = (
        f"{_capitalize_locator_kind(child_segment.kind)} {child_segment.num}"
        f"{f'({child_segment.sub})' if child_segment.sub else ''}"
    )
    return f"{parent_label}, {child_label}"


def _is_structural_container_kind(kind: str) -> bool:
    return kind in STRUCTURAL_CONTAINER_KINDS


def _parse_part_number_list(text: str) -> list[str]:
    return [
        part.strip().lower()
        for part in re.split(r"\s*(?:,|and|or)\s*", text, flags=re.IGNORECASE)
        if re.fullmatch(r"\d+[a-z]?", part.strip().lower())
    ]


def _is_year_like(num: str) -> bool:
    return bool(YEAR_LIKE_RE.match(num.strip()))


def normalize_cross_reference_locator(locator: str | None) -> str:
    """Normalise a cross-reference locator phrase for deterministic matching."""
    raw = str(locator or "").strip().lower()
    if not raw:
        return ""
    base = raw.split("|chunk:", 1)[0].strip()
    base = re.sub(r"\s+", " ", base)

    nested_colon_path = _parse_colon_paragraph_path_segments(base)
    if nested_colon_path:
        return build_canonical_locator(nested_colon_path)

    colon_path = COLON_PATH_RE.match(base)
    if colon_path:
        sub = (colon_path.group("child_sub") or "").strip().lower()
        parent_kind = colon_path.group("parent_kind").lower()
        parent_num = colon_path.group("parent_num").lower()
        child_num = colon_path.group("child_num").lower()
        if sub:
            return f"{parent_kind} {parent_num}({child_num}({sub}))"
        return f"{parent_kind} {parent_num}({child_num})"

    schedule_paragraph = SCHEDULE_PARAGRAPH_TEXT_RE.match(base)
    if schedule_paragraph:
        sub = (schedule_paragraph.group("sub") or "").strip().lower()
        schedule = schedule_paragraph.group("schedule").lower()
        paragraph = schedule_paragraph.group("paragraph").lower()
        if sub:
            return f"schedule {schedule}({paragraph}({sub}))"
        return f"schedule {schedule}({paragraph})"

    colon_match = re.match(
        r"^(regulation|schedule|article|paragraph|annex|part|rule):(.+)$",
        base,
    )
    if colon_match:
        kind = colon_match.group(1)
        rest = colon_match.group(2).strip()
        paragraph_match = re.match(r"^(\d+[a-z]?):paragraph:(.+)$", rest)
        if paragraph_match:
            para_num, para_sub = _parse_nested_num_token(paragraph_match.group(2)) or (
                paragraph_match.group(2).lower(),
                None,
            )
            segments = [
                LocatorSegment(kind=kind, num=paragraph_match.group(1).lower()),
                LocatorSegment(kind="paragraph", num=para_num, sub=para_sub),
            ]
            return build_canonical_locator(segments)
        part_match = re.match(r"^(\d+[a-z]?):part:(\d+[a-z]?)$", rest)
        if part_match:
            return f"schedule {part_match.group(1)} part {part_match.group(2)}"
        sub_match = re.match(r"^(\d+[a-z]?)(?:\(([^)]+)\))?$", rest)
        if sub_match:
            num = sub_match.group(1)
            sub = sub_match.group(2)
            if sub:
                return f"{kind} {num}({sub.strip()})"
            return f"{kind} {num}"

    para_alias = re.match(r"^para(?:graph)?s?\s+(\d+[a-z]?)(?:\s*\((.+)\))?$", base, re.I)
    if para_alias:
        sub = (para_alias.group(2) or "").strip().lower()
        if sub:
            return f"paragraph {para_alias.group(1).lower()}({sub})"
        return f"paragraph {para_alias.group(1).lower()}"

    space_base = base.replace(":", " ")
    space_match = REGULATION_LOCATOR_RE.match(space_base)
    if space_match:
        kind = space_match.group("kind").lower()
        num = space_match.group("num").lower()
        sub = space_match.group("sub")
        if sub:
            return f"{kind} {num}({sub.strip().lower()})"
        return f"{kind} {num}"
    return base


def _locator_parts(locator: str) -> LocatorSegment | None:
    norm = normalize_cross_reference_locator(locator)
    match = REGULATION_LOCATOR_RE.match(norm)
    if not match:
        return None
    sub = match.group("sub")
    return LocatorSegment(
        kind=match.group("kind").lower(),
        num=match.group("num").lower(),
        sub=sub.strip().lower() if sub else None,
    )


def parse_colon_locator_segments(locator: str | None) -> list[LocatorSegment] | None:
    raw = _strip_locator_annotations(
        str(locator or "").strip().lower().split("|chunk:", 1)[0].strip()
    )
    if ":" not in raw:
        return None

    nested_paragraph_path = _parse_colon_paragraph_path_segments(raw)
    if nested_paragraph_path:
        return nested_paragraph_path

    paragraph_path = COLON_PATH_RE.match(raw)
    if paragraph_path:
        return [
            LocatorSegment(
                kind=paragraph_path.group("parent_kind").lower(),
                num=paragraph_path.group("parent_num").lower(),
            ),
            LocatorSegment(
                kind="paragraph",
                num=paragraph_path.group("child_num").lower(),
                sub=(paragraph_path.group("child_sub") or "").strip().lower() or None,
            ),
        ]

    tokens = raw.split(":")
    if len(tokens) < 2 or len(tokens) % 2 != 0:
        return None

    segments: list[LocatorSegment] = []
    for index in range(0, len(tokens), 2):
        kind = tokens[index]
        num_token = tokens[index + 1]
        if not _is_locator_kind(kind):
            return None
        parsed_num = _parse_nested_num_token(num_token)
        if not parsed_num:
            return None
        segments.append(
            LocatorSegment(
                kind=kind,
                num=parsed_num[0],
                sub=parsed_num[1],
            )
        )
    return segments or None


def parse_locator_structural_context(locator: str | None) -> LocatorStructuralContext | None:
    raw = _strip_locator_annotations(str(locator or "").strip())
    if not raw:
        return None

    colon_segments = parse_colon_locator_segments(raw)
    if colon_segments:
        return LocatorStructuralContext(segments=colon_segments)

    colon_path = COLON_PATH_RE.match(raw)
    if colon_path:
        return LocatorStructuralContext(
            segments=[
                LocatorSegment(
                    kind=colon_path.group("parent_kind").lower(),
                    num=colon_path.group("parent_num").lower(),
                ),
                LocatorSegment(
                    kind="paragraph",
                    num=colon_path.group("child_num").lower(),
                    sub=(colon_path.group("child_sub") or "").strip().lower() or None,
                ),
            ]
        )

    # ``paragraph 1 of Article 49a`` / ``paragraph (1) of Article 49a``.
    paragraph_of = PARAGRAPH_OF_INSTRUMENT_RE.match(raw)
    if paragraph_of:
        para_num = (paragraph_of.group("num") or paragraph_of.group("num_paren") or "").lower()
        if para_num and not _is_year_like(para_num):
            return LocatorStructuralContext(
                segments=[
                    LocatorSegment(
                        kind=paragraph_of.group("kind").lower(),
                        num=paragraph_of.group("parent").lower(),
                    ),
                    LocatorSegment(
                        kind="paragraph",
                        num=para_num,
                        sub=(paragraph_of.group("sub") or "").strip().lower() or None,
                    ),
                ]
            )

    # Prefer chained parens before the greedy single-inner matcher so
    # ``Article 49a(2)(b)`` becomes article + paragraph 2(b), not ``2)(b``.
    chained = INSTRUMENT_CHAINED_PARENS_RE.match(raw)
    if not chained:
        chained = INSTRUMENT_CHAINED_PARENS_RE.match(normalize_cross_reference_locator(raw))
    if chained:
        paren_parts = _split_chained_parens(chained.group("parens"))
        if paren_parts:
            return LocatorStructuralContext(
                segments=_segments_from_instrument_paren_parts(
                    chained.group("kind"),
                    chained.group("num"),
                    paren_parts,
                )
            )

    comma_paragraph = INSTRUMENT_COMMA_PARAGRAPH_RE.match(raw)
    if comma_paragraph:
        return LocatorStructuralContext(
            segments=[
                LocatorSegment(
                    kind=comma_paragraph.group("kind").lower(),
                    num=comma_paragraph.group("num").lower(),
                ),
                LocatorSegment(
                    kind="paragraph",
                    num=comma_paragraph.group("para").lower(),
                    sub=(comma_paragraph.group("sub") or "").strip().lower() or None,
                ),
            ]
        )

    schedule_paragraph = SCHEDULE_PARAGRAPH_TEXT_RE.match(raw)
    if schedule_paragraph:
        return LocatorStructuralContext(
            segments=[
                LocatorSegment(kind="schedule", num=schedule_paragraph.group("schedule").lower()),
                LocatorSegment(
                    kind="paragraph",
                    num=schedule_paragraph.group("paragraph").lower(),
                    sub=(schedule_paragraph.group("sub") or "").strip().lower() or None,
                ),
            ]
        )

    regulation_sub = REGULATION_SUB_TEXT_RE.match(raw)
    if regulation_sub:
        return LocatorStructuralContext(
            segments=[
                LocatorSegment(
                    kind="regulation",
                    num=regulation_sub.group("regulation").lower(),
                    sub=(regulation_sub.group("sub") or "").strip().lower() or None,
                )
            ]
        )

    instrument_parenthetical = INSTRUMENT_PARENTHETICAL_RE.match(
        normalize_cross_reference_locator(raw)
    )
    if instrument_parenthetical:
        return LocatorStructuralContext(
            segments=_parse_parenthetical_instrument_segments(
                instrument_parenthetical.group("kind"),
                instrument_parenthetical.group("num"),
                instrument_parenthetical.group("inner"),
            )
        )

    parts = _locator_parts(normalize_cross_reference_locator(raw))
    if parts:
        return LocatorStructuralContext(segments=[parts])

    colon_base = re.match(
        r"^(regulation|schedule|article|part|annex|rule):(\d+[a-z]?)$",
        raw.lower().split("|chunk:", 1)[0].strip(),
    )
    if colon_base:
        return LocatorStructuralContext(
            segments=[LocatorSegment(kind=colon_base.group(1), num=colon_base.group(2))]
        )
    return None


def _locator_segment_path(locator: str) -> list[LocatorSegment] | None:
    return parse_colon_locator_segments(locator) or (
        parse_locator_structural_context(locator).segments
        if parse_locator_structural_context(locator)
        else None
    )


def _segment_path_has_prefix(path: list[LocatorSegment], prefix: list[LocatorSegment]) -> bool:
    if len(path) < len(prefix):
        return False
    return all(
        _segment_matches_prefix(path[index], segment)
        for index, segment in enumerate(prefix)
    )


def _segment_path_is_descendant(path: list[LocatorSegment], prefix: list[LocatorSegment]) -> bool:
    if len(path) < len(prefix):
        return False
    if not _segment_path_has_prefix(path, prefix):
        return False
    if len(path) == len(prefix):
        last_path = path[-1]
        last_prefix = prefix[-1]
        if last_path.kind == "paragraph" and last_prefix.kind == "paragraph":
            frag_label = _format_nested_num_token(last_path.num, last_path.sub)
            prefix_label = _format_nested_num_token(last_prefix.num, last_prefix.sub)
            return frag_label != prefix_label and frag_label.startswith(f"{prefix_label}(")
        return False
    return True


def build_canonical_locator(segments: list[LocatorSegment]) -> str:
    if not segments:
        return ""
    if len(segments) == 1:
        only = segments[0]
        if only.sub:
            return f"{only.kind} {only.num}({only.sub})"
        return f"{only.kind} {only.num}"

    parent = segments[0]
    child = segments[-1]
    if parent.kind in {"schedule", "regulation", "article", "part", "rule"} and child.kind == "paragraph":
        if child.sub:
            return f"{parent.kind} {parent.num}({child.num}({child.sub}))"
        return f"{parent.kind} {parent.num}({child.num})"

    return " ".join(_segment_key(seg) for seg in segments)


def _expand_numeric_range(from_num: int, to_num: int) -> list[int]:
    if not (from_num == from_num and to_num == to_num):  # NaN guard
        return []
    start = min(from_num, to_num)
    end = max(from_num, to_num)
    if end - start > 50:
        return []
    return list(range(start, end + 1))


def parse_locator_reference(text: str | None) -> ParsedLocatorReference | None:
    raw = str(text or "").strip()
    if not raw:
        return None

    # Explicit ``paragraph 1 of Article 14`` / ``paragraph (1) of Article 14``
    # before bare ``paragraph 1``.
    paragraph_of = PARAGRAPH_OF_INSTRUMENT_RE.match(raw)
    if paragraph_of:
        para_num = (paragraph_of.group("num") or paragraph_of.group("num_paren") or "").lower()
        if para_num and not _is_year_like(para_num):
            return ParsedLocatorSingle(
                display=raw,
                segments=(
                    LocatorSegment(
                        kind=paragraph_of.group("kind").lower(),
                        num=paragraph_of.group("parent").lower(),
                    ),
                    LocatorSegment(
                        kind="paragraph",
                        num=para_num,
                        sub=(paragraph_of.group("sub") or "").strip().lower() or None,
                    ),
                ),
            )

    schedule_paragraph = SCHEDULE_PARAGRAPH_TEXT_RE.match(raw)
    if schedule_paragraph:
        return ParsedLocatorSingle(
            display=raw,
            segments=(
                LocatorSegment(kind="schedule", num=schedule_paragraph.group("schedule").lower()),
                LocatorSegment(
                    kind="paragraph",
                    num=schedule_paragraph.group("paragraph").lower(),
                    sub=(schedule_paragraph.group("sub") or "").strip().lower() or None,
                ),
            ),
        )

    regulation_sub = REGULATION_SUB_TEXT_RE.match(raw)
    if regulation_sub:
        return ParsedLocatorSingle(
            display=raw,
            segments=(
                LocatorSegment(
                    kind="regulation",
                    num=regulation_sub.group("regulation").lower(),
                    sub=(regulation_sub.group("sub") or "").strip().lower() or None,
                ),
            ),
        )

    range_match = PARAGRAPH_RANGE_RE.match(raw)
    if range_match:
        from_num = int(range_match.group("from"))
        to_num = int(range_match.group("to"))
        if (
            not _is_year_like(range_match.group("from"))
            and not _is_year_like(range_match.group("to"))
            and _expand_numeric_range(from_num, to_num)
        ):
            return ParsedLocatorRange(display=raw, from_num=from_num, to_num=to_num)

    sub_paragraph = SUB_PARAGRAPH_RE.match(raw)
    if sub_paragraph:
        return ParsedLocatorSingle(
            display=raw,
            segments=(LocatorSegment(kind="sub-paragraph", num=sub_paragraph.group("sub").strip().lower()),),
        )

    bare_point = BARE_POINT_RE.match(raw)
    if bare_point:
        return ParsedLocatorSingle(
            display=raw,
            segments=(LocatorSegment(kind="point", num=bare_point.group("sub").strip().lower()),),
        )

    paren_paragraph = PAREN_PARAGRAPH_RE.match(raw)
    if paren_paragraph:
        return ParsedLocatorSingle(
            display=raw,
            segments=(LocatorSegment(kind="paragraph", num=paren_paragraph.group("sub").strip().lower()),),
        )

    bare_paragraph = BARE_PARAGRAPH_RE.match(raw)
    if bare_paragraph and not _is_year_like(bare_paragraph.group("num")):
        return ParsedLocatorSingle(
            display=raw,
            segments=(
                LocatorSegment(
                    kind="paragraph",
                    num=bare_paragraph.group("num").lower(),
                    sub=(bare_paragraph.group("sub") or "").strip().lower() or None,
                ),
            ),
        )

    # Compact ``Article 49a(2)`` / ``Article 49a(2)(a)`` → article + paragraph segments
    # (same expansion as structural-context parsing; avoid article.sub='2' collapse).
    chained = INSTRUMENT_CHAINED_PARENS_RE.match(raw) or INSTRUMENT_CHAINED_PARENS_RE.match(
        normalize_cross_reference_locator(raw)
    )
    if chained:
        paren_parts = _split_chained_parens(chained.group("parens"))
        if paren_parts:
            segments = _segments_from_instrument_paren_parts(
                chained.group("kind"),
                chained.group("num"),
                paren_parts,
            )
            if segments and not _is_year_like(segments[0].num):
                return ParsedLocatorSingle(display=raw, segments=tuple(segments))

    instrument_parenthetical = INSTRUMENT_PARENTHETICAL_RE.match(
        normalize_cross_reference_locator(raw)
    )
    if instrument_parenthetical:
        segments = _parse_parenthetical_instrument_segments(
            instrument_parenthetical.group("kind"),
            instrument_parenthetical.group("num"),
            instrument_parenthetical.group("inner"),
        )
        if segments and not _is_year_like(segments[0].num):
            return ParsedLocatorSingle(display=raw, segments=tuple(segments))

    parts = _locator_parts(normalize_cross_reference_locator(raw))
    if parts and not _is_year_like(parts.num):
        return ParsedLocatorSingle(display=raw, segments=(parts,))
    return None


def _parent_segment_for_inheritance(context: LocatorStructuralContext) -> LocatorSegment | None:
    if not context.segments:
        return None
    for segment in context.segments:
        if segment.kind in {"schedule", "regulation", "article", "part", "rule"}:
            return segment
    if len(context.segments) == 1:
        return context.segments[0]
    return context.segments[-2] if len(context.segments) >= 2 else context.segments[0]


def _enclosing_paragraph_segment(context: LocatorStructuralContext) -> LocatorSegment | None:
    for segment in reversed(context.segments):
        if segment.kind == "paragraph":
            return segment
    return None


def _is_numeric_paragraph_ref(segment: LocatorSegment) -> bool:
    return segment.kind == "paragraph" and bool(_NUMERIC_PARAGRAPH_NUM_RE.match(segment.num))


def apply_structural_context_to_reference(
    context: LocatorStructuralContext | None,
    reference: ParsedLocatorReference,
) -> ParsedLocatorReference:
    """Qualify bare relative refs using enclosing provision segments.

    Resolution order for callers remains: explicit fully-qualified reference →
    this structural qualification → instrument-wide fallback.
    """
    if context is None or not context.segments:
        return reference

    if isinstance(reference, ParsedLocatorRange):
        parent = _parent_segment_for_inheritance(context)
        return ParsedLocatorRange(
            display=reference.display,
            from_num=reference.from_num,
            to_num=reference.to_num,
            inherited_parent=parent,
        )

    ref_segment = reference.segments[0] if reference.segments else None
    if ref_segment is None:
        return reference

    # Explicit instrument/container references stay unchanged.
    if ref_segment.kind in STRUCTURAL_CONTAINER_KINDS or (
        _is_locator_kind(ref_segment.kind)
        and ref_segment.kind not in {"paragraph", "sub-paragraph"}
        and ref_segment.kind != "point"
    ):
        return reference

    container = _parent_segment_for_inheritance(context)
    current_paragraph = _enclosing_paragraph_segment(context)

    # Bare ``paragraph N`` / ``paragraph N(a)`` → enclosing article/regulation/...
    if _is_numeric_paragraph_ref(ref_segment) and container is not None:
        return ParsedLocatorSingle(
            display=reference.display,
            segments=(
                LocatorSegment(kind=container.kind, num=container.num),
                LocatorSegment(
                    kind="paragraph",
                    num=ref_segment.num,
                    sub=ref_segment.sub,
                ),
            ),
        )

    # Bare ``subparagraph (a)`` / lettered ``paragraph (a)`` / ``point (ii)``.
    if ref_segment.kind in {"sub-paragraph", "point"} or (
        ref_segment.kind == "paragraph" and not _is_numeric_paragraph_ref(ref_segment)
    ):
        if container is not None and current_paragraph is not None:
            if ref_segment.kind == "point" and current_paragraph.sub:
                nested_sub = f"{current_paragraph.sub}({ref_segment.num})"
            else:
                nested_sub = ref_segment.num
            return ParsedLocatorSingle(
                display=reference.display,
                segments=(
                    LocatorSegment(kind=container.kind, num=container.num),
                    LocatorSegment(
                        kind="paragraph",
                        num=current_paragraph.num,
                        sub=nested_sub,
                    ),
                ),
            )
        if container is not None and container.kind in {"regulation", "article", "rule"}:
            # Legacy compact form when no paragraph context is available.
            return ParsedLocatorSingle(
                display=reference.display,
                segments=(
                    LocatorSegment(kind=container.kind, num=container.num, sub=ref_segment.num),
                ),
            )

    if ref_segment.kind == "paragraph" and container is not None and container.kind in {
        "schedule",
        "regulation",
        "article",
        "part",
        "rule",
    }:
        return ParsedLocatorSingle(
            display=reference.display,
            segments=(
                LocatorSegment(kind=container.kind, num=container.num),
                LocatorSegment(kind="paragraph", num=ref_segment.num, sub=ref_segment.sub),
            ),
        )
    return reference


def expand_parsed_locator_reference(reference: ParsedLocatorReference) -> list[ParsedLocatorSingle]:
    if isinstance(reference, ParsedLocatorSingle):
        return [reference]

    numbers = _expand_numeric_range(reference.from_num, reference.to_num)
    parent = reference.inherited_parent
    result: list[ParsedLocatorSingle] = []
    for num in numbers:
        if parent:
            result.append(
                ParsedLocatorSingle(
                    display=f"paragraph {num}",
                    segments=(
                        parent,
                        LocatorSegment(kind="paragraph", num=str(num), sub=None),
                    ),
                )
            )
        else:
            result.append(
                ParsedLocatorSingle(
                    display=f"paragraph {num}",
                    segments=(LocatorSegment(kind="paragraph", num=str(num), sub=None),),
                )
            )
    return result


def resolve_locator_targets(locator_text: str, context: LocatorStructuralContext | None) -> list[str]:
    parsed = parse_locator_reference(locator_text)
    if parsed is None:
        return [locator_text]

    contextualised = apply_structural_context_to_reference(context, parsed)
    expanded = expand_parsed_locator_reference(contextualised)
    targets = [
        build_canonical_locator(list(entry.segments))
        for entry in expanded
        if build_canonical_locator(list(entry.segments)).strip()
    ]
    return targets or [locator_text]


def _cross_form_instrument_sub_match(
    fragment_path: list[LocatorSegment],
    target_path: list[LocatorSegment],
) -> bool:
    if len(target_path) != 1:
        return False
    target = target_path[0]
    if not target.sub or target.kind not in INSTRUMENT_SUB_KINDS:
        return False

    fragment_regulation = next(
        (seg for seg in fragment_path if seg.kind == target.kind and seg.num == target.num),
        None,
    )
    if fragment_regulation is None:
        return False

    fragment_paragraph = next((seg for seg in fragment_path if seg.kind == "paragraph"), None)
    if fragment_paragraph:
        return fragment_paragraph.num == target.sub and (
            fragment_paragraph.sub is None or fragment_paragraph.sub == target.sub
        )
    return fragment_regulation.sub == target.sub


def locator_matches_target(fragment_locator: str, target_locator: str) -> bool:
    prop_norm = normalize_cross_reference_locator(fragment_locator)
    target_norm = normalize_cross_reference_locator(target_locator)
    if not prop_norm or not target_norm:
        return False
    if prop_norm == target_norm:
        return True

    prop_path = parse_locator_structural_context(fragment_locator)
    target_path = parse_locator_structural_context(target_locator)
    if prop_path and target_path:
        prop_canonical = build_canonical_locator(prop_path.segments)
        target_canonical = build_canonical_locator(target_path.segments)
        if prop_canonical and target_canonical and prop_canonical == target_canonical:
            return True
        if _segment_path_has_prefix(prop_path.segments, target_path.segments):
            return True
        if _cross_form_instrument_sub_match(prop_path.segments, target_path.segments):
            return True

    prop_parts = _locator_parts(prop_norm)
    target_parts = _locator_parts(target_norm)
    if prop_parts is None or target_parts is None:
        return prop_norm.startswith(f"{target_norm}(") or prop_norm.startswith(f"{target_norm} ")
    if prop_parts.kind != target_parts.kind or prop_parts.num != target_parts.num:
        return False
    if target_parts.sub is None:
        return True
    if prop_parts.kind == "paragraph":
        return _paragraph_path_matches_prefix(
            prop_parts.num,
            prop_parts.sub,
            target_parts.num,
            target_parts.sub,
        )
    return prop_parts.sub == target_parts.sub


def parse_container_locator_targets(locator: str | None) -> list[ContainerLocatorTarget] | None:
    raw = str(locator or "").strip()
    if not raw:
        return None

    parts_of_schedule = PARTS_OF_SCHEDULE_TEXT_RE.match(raw)
    if parts_of_schedule:
        schedule = parts_of_schedule.group("schedule").lower()
        part_nums = _parse_part_number_list(parts_of_schedule.group("parts"))
        if len(part_nums) < 2:
            return None
        parent = LocatorSegment(kind="schedule", num=schedule)
        return [
            ContainerLocatorTarget(
                display=_format_container_child_label([parent], LocatorSegment(kind="part", num=part)),
                segments=(parent, LocatorSegment(kind="part", num=part)),
            )
            for part in part_nums
        ]

    part_of_schedule = PART_OF_SCHEDULE_TEXT_RE.match(raw)
    if part_of_schedule:
        schedule = part_of_schedule.group("schedule").lower()
        part = part_of_schedule.group("part").lower()
        parent = LocatorSegment(kind="schedule", num=schedule)
        return [
            ContainerLocatorTarget(
                display=_format_container_child_label([parent], LocatorSegment(kind="part", num=part)),
                segments=(parent, LocatorSegment(kind="part", num=part)),
            )
        ]

    colon_segments = parse_colon_locator_segments(raw)
    if colon_segments:
        last = colon_segments[-1]
        if last.kind == "part" or (
            len(colon_segments) == 1 and _is_structural_container_kind(last.kind)
        ):
            return [
                ContainerLocatorTarget(
                    display=_format_container_locator_label(colon_segments),
                    segments=tuple(colon_segments),
                )
            ]

    parsed = parse_locator_reference(raw)
    if isinstance(parsed, ParsedLocatorSingle) and len(parsed.segments) == 1:
        segment = parsed.segments[0]
        if _is_structural_container_kind(segment.kind) and segment.sub is None:
            return [
                ContainerLocatorTarget(
                    display=_format_container_locator_label([segment]),
                    segments=(segment,),
                )
            ]
    return None


def _fragment_row_id(fragment: dict[str, Any]) -> str:
    return str(fragment.get("id") or fragment.get("fragment_id") or "").strip()


def _fragments_for_source(
    source_record_id: str,
    source_fragments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        frag
        for frag in source_fragments
        if str(frag.get("source_record_id") or "").strip() == source_record_id
    ]


def _match_fragments_in_source(
    source_record_id: str,
    locator: str,
    source_fragments: list[dict[str, Any]],
) -> list[ResolvedContextFragment]:
    matches: list[ResolvedContextFragment] = []
    seen: set[str] = set()
    for fragment in _fragments_for_source(source_record_id, source_fragments):
        fragment_locator = str(fragment.get("locator") or "").strip()
        if not fragment_locator or not locator_matches_target(fragment_locator, locator):
            continue
        fragment_id = _fragment_row_id(fragment)
        if not fragment_id or fragment_id in seen:
            continue
        seen.add(fragment_id)
        matches.append(ResolvedContextFragment(fragment_id=fragment_id, locator=fragment_locator))
    return matches


def _match_fragments_for_container_target(
    source_record_id: str,
    target: ContainerLocatorTarget,
    source_fragments: list[dict[str, Any]],
) -> list[ResolvedContextFragment]:
    matches: list[ResolvedContextFragment] = []
    seen: set[str] = set()
    target_segments = list(target.segments)
    canonical = build_canonical_locator(target_segments)

    for fragment in _fragments_for_source(source_record_id, source_fragments):
        fragment_locator = str(fragment.get("locator") or "").strip()
        if not fragment_locator:
            continue
        path = _locator_segment_path(fragment_locator)
        matches_target = (
            path is not None and _segment_path_has_prefix(path, target_segments)
        ) or locator_matches_target(fragment_locator, canonical)
        if not matches_target:
            continue
        fragment_id = _fragment_row_id(fragment)
        if not fragment_id or fragment_id in seen:
            continue
        seen.add(fragment_id)
        matches.append(ResolvedContextFragment(fragment_id=fragment_id, locator=fragment_locator))
    return matches


def _resolve_container_locator_targets(
    targets: list[ContainerLocatorTarget],
    *,
    source_record_id: str,
    source_fragments: list[dict[str, Any]],
) -> list[ResolvedContextFragment] | None:
    if not targets:
        return None

    if len(targets) == 1:
        matches = _match_fragments_for_container_target(
            source_record_id, targets[0], source_fragments
        )
        return matches or None

    resolved: list[ResolvedContextFragment] = []
    seen: set[str] = set()
    for target in targets:
        for fragment in _match_fragments_for_container_target(
            source_record_id, target, source_fragments
        ):
            if fragment.fragment_id not in seen:
                seen.add(fragment.fragment_id)
                resolved.append(fragment)
    return resolved or None


def _instrument_sub_reference(parsed: ParsedLocatorReference) -> LocatorSegment | None:
    if not isinstance(parsed, ParsedLocatorSingle) or len(parsed.segments) != 1:
        return None
    segment = parsed.segments[0]
    if not segment.sub or segment.kind not in INSTRUMENT_SUB_KINDS:
        return None
    return segment


def _search_targets_for_instrument_sub(segment: LocatorSegment) -> list[str]:
    parent = build_canonical_locator([LocatorSegment(kind=segment.kind, num=segment.num, sub=None)])
    if not segment.sub:
        return [parent]
    colon_paragraph_child = f"{segment.kind}:{segment.num}:paragraph:{segment.sub}"
    exact = build_canonical_locator([segment])
    paragraph_child = build_canonical_locator(
        [
            LocatorSegment(kind=segment.kind, num=segment.num, sub=None),
            LocatorSegment(kind="paragraph", num=segment.sub, sub=None),
        ]
    )
    return list(dict.fromkeys([colon_paragraph_child, exact, paragraph_child, parent]))


def _match_parent_only_fragments_in_source(
    source_record_id: str,
    parent_locator: str,
    source_fragments: list[dict[str, Any]],
) -> list[ResolvedContextFragment]:
    parent_path = parse_locator_structural_context(parent_locator)
    matches = _match_fragments_in_source(source_record_id, parent_locator, source_fragments)
    if parent_path is None:
        return matches
    return [
        frag
        for frag in matches
        if (path := _locator_segment_path(frag.locator)) is not None
        and len(path) == len(parent_path.segments)
    ]


def _resolve_instrument_sub_locator(
    locator: str,
    *,
    source_record_id: str,
    source_fragments: list[dict[str, Any]],
) -> ContextLocatorResolution | None:
    parsed = parse_locator_reference(locator)
    segment = _instrument_sub_reference(parsed) if parsed else None
    if segment is None:
        return None

    targets = _search_targets_for_instrument_sub(segment)
    parent_target = targets[-1]

    for target in targets[:-1]:
        exact_matches = _match_fragments_in_source(source_record_id, target, source_fragments)
        if len(exact_matches) == 1:
            return _resolution_from_fragments(
                exact_matches,
                resolution_mode="exact",
                resolved_locator=target,
            )
        if len(exact_matches) > 1:
            return _resolution_from_fragments(
                exact_matches,
                review_status="ambiguous",
                resolution_status="ambiguous",
                resolution_mode="exact",
                resolved_locator=target,
            )

    parent_matches = _match_parent_only_fragments_in_source(
        source_record_id, parent_target, source_fragments
    )
    if len(parent_matches) == 1:
        return _resolution_from_fragments(
            parent_matches,
            resolution_status="partially_resolved",
            resolution_mode="partial",
            resolved_locator=parent_target,
            unresolved_child=f"paragraph ({segment.sub})",
        )
    if len(parent_matches) > 1:
        return _resolution_from_fragments(
            parent_matches,
            review_status="ambiguous",
            resolution_status="ambiguous",
            resolution_mode="partial",
            resolved_locator=parent_target,
        )
    return None


def _match_bare_paragraph_fragments_in_source(
    source_record_id: str,
    paragraph_num: str,
    paragraph_sub: str | None,
    source_fragments: list[dict[str, Any]],
) -> list[ResolvedContextFragment]:
    matches: list[ResolvedContextFragment] = []
    seen: set[str] = set()
    prefix_segment = LocatorSegment(kind="paragraph", num=paragraph_num.lower(), sub=paragraph_sub)
    for fragment in _fragments_for_source(source_record_id, source_fragments):
        fragment_locator = str(fragment.get("locator") or "").strip()
        path = parse_locator_structural_context(fragment_locator)
        if path is None:
            continue
        paragraph = next((seg for seg in path.segments if seg.kind == "paragraph"), None)
        if paragraph is None or not _segment_matches_prefix(paragraph, prefix_segment):
            continue
        fragment_id = _fragment_row_id(fragment)
        if not fragment_id or fragment_id in seen:
            continue
        seen.add(fragment_id)
        matches.append(ResolvedContextFragment(fragment_id=fragment_id, locator=fragment_locator))
    return matches


def _match_fragments_by_segment_path(
    source_record_id: str,
    target_segments: list[LocatorSegment],
    source_fragments: list[dict[str, Any]],
    *,
    descendants_only: bool = False,
) -> list[ResolvedContextFragment]:
    matches: list[ResolvedContextFragment] = []
    seen: set[str] = set()
    target_canonical = build_canonical_locator(target_segments)
    for fragment in _fragments_for_source(source_record_id, source_fragments):
        fragment_locator = str(fragment.get("locator") or "").strip()
        if not fragment_locator:
            continue
        path = _locator_segment_path(fragment_locator)
        matches_target = False
        if path is not None:
            if descendants_only:
                matches_target = _segment_path_is_descendant(path, target_segments)
            else:
                matches_target = _segment_path_has_prefix(path, target_segments)
        if not matches_target:
            matches_target = locator_matches_target(fragment_locator, target_canonical)
        if not matches_target:
            continue
        fragment_id = _fragment_row_id(fragment)
        if not fragment_id or fragment_id in seen:
            continue
        seen.add(fragment_id)
        matches.append(ResolvedContextFragment(fragment_id=fragment_id, locator=fragment_locator))
    return matches


def _proposition_locator_fragments(
    propositions: list[dict[str, Any]],
    *,
    source_record_id: str,
) -> list[ResolvedContextFragment]:
    fragments: list[ResolvedContextFragment] = []
    seen: set[str] = set()
    for prop in propositions:
        if str(prop.get("source_record_id") or "").strip() != source_record_id:
            continue
        prop_id = str(prop.get("id") or "").strip()
        prop_locator = str(prop.get("fragment_locator") or prop.get("article_reference") or "").strip()
        if not prop_id or not prop_locator or prop_id in seen:
            continue
        seen.add(prop_id)
        fragments.append(ResolvedContextFragment(fragment_id=prop_id, locator=prop_locator))
    return fragments


def _match_propositions_by_segment_path(
    source_record_id: str,
    target_segments: list[LocatorSegment],
    propositions: list[dict[str, Any]],
    *,
    descendants_only: bool = False,
) -> list[str]:
    matched: list[str] = []
    seen: set[str] = set()
    target_canonical = build_canonical_locator(target_segments)
    for fragment in _proposition_locator_fragments(
        propositions,
        source_record_id=source_record_id,
    ):
        path = _locator_segment_path(fragment.locator)
        matches_target = False
        if path is not None:
            if descendants_only:
                matches_target = _segment_path_is_descendant(path, target_segments)
            else:
                matches_target = _segment_path_has_prefix(path, target_segments)
        if not matches_target:
            matches_target = locator_matches_target(fragment.locator, target_canonical)
        if not matches_target or fragment.fragment_id in seen:
            continue
        seen.add(fragment.fragment_id)
        matched.append(fragment.fragment_id)
    return matched


def _proposition_locator_for_id(
    propositions: list[dict[str, Any]],
    prop_id: str,
) -> str:
    for prop in propositions:
        if str(prop.get("id") or "").strip() != prop_id:
            continue
        return str(prop.get("fragment_locator") or prop.get("article_reference") or "").strip()
    return ""


def _is_exact_segment_path_match(path: list[LocatorSegment], target_segments: list[LocatorSegment]) -> bool:
    if len(path) != len(target_segments):
        return False
    for candidate, target in zip(path, target_segments, strict=True):
        if candidate.kind != target.kind or candidate.num != target.num:
            return False
        if target.kind == "paragraph":
            if _format_nested_num_token(candidate.num, candidate.sub) != _format_nested_num_token(
                target.num,
                target.sub,
            ):
                return False
        elif target.sub is not None and candidate.sub != target.sub:
            return False
    return True


def _resolve_contextual_paragraph_target(
    target_segments: list[LocatorSegment],
    *,
    source_record_id: str,
    source_fragments: list[dict[str, Any]],
    propositions: list[dict[str, Any]],
    resolved_locator: str,
) -> ContextLocatorResolution | None:
    exact_fragments = [
        frag
        for frag in _match_fragments_by_segment_path(
            source_record_id,
            target_segments,
            source_fragments,
        )
        if (path := _locator_segment_path(frag.locator)) is not None
        and _is_exact_segment_path_match(path, target_segments)
    ]
    exact_prop_ids = [
        prop_id
        for prop_id in _match_propositions_by_segment_path(
            source_record_id,
            target_segments,
            propositions,
        )
        if (path := _locator_segment_path(_proposition_locator_for_id(propositions, prop_id)))
        and _is_exact_segment_path_match(path, target_segments)
    ]

    if len(exact_fragments) == 1:
        prop_ids = proposition_ids_for_fragments(
            exact_fragments,
            propositions,
            source_record_id=source_record_id,
        )
        if not prop_ids:
            prop_ids = exact_prop_ids
        return _resolution_from_fragments(
            exact_fragments,
            review_status="accepted",
            resolution_status="resolved" if prop_ids else "unresolved",
            resolution_mode="exact",
            resolved_locator=resolved_locator,
            proposition_ids=prop_ids,
        )

    container_fragments = _match_fragments_by_segment_path(
        source_record_id,
        target_segments,
        source_fragments,
    )
    container_prop_ids = _match_propositions_by_segment_path(
        source_record_id,
        target_segments,
        propositions,
    )
    if not container_fragments and not container_prop_ids:
        return None

    prop_ids = proposition_ids_for_fragments(
        container_fragments,
        propositions,
        source_record_id=source_record_id,
    )
    for prop_id in container_prop_ids:
        if prop_id not in prop_ids:
            prop_ids.append(prop_id)

    synthetic_fragments = list(container_fragments)
    existing_locators = {frag.locator for frag in synthetic_fragments}
    for prop_id in container_prop_ids:
        prop_locator = _proposition_locator_for_id(propositions, prop_id)
        if prop_locator and prop_locator not in existing_locators:
            synthetic_fragments.append(
                ResolvedContextFragment(fragment_id=prop_id, locator=prop_locator)
            )
            existing_locators.add(prop_locator)

    mode: Literal["exact", "container", "partial"] = (
        "container"
        if len(synthetic_fragments) > 1
        or any(
            (path := _locator_segment_path(frag.locator)) is not None
            and _segment_path_is_descendant(path, target_segments)
            for frag in synthetic_fragments
        )
        else "exact"
    )
    return _resolution_from_fragments(
        synthetic_fragments,
        review_status="accepted",
        resolution_status="resolved" if prop_ids else "unresolved",
        resolution_mode=mode,
        resolved_locator=resolved_locator,
        proposition_ids=prop_ids,
    )


def _is_bare_relative_reference(locator: str) -> bool:
    # Explicit ``paragraph N of Article X`` is fully qualified, not bare-relative.
    if PARAGRAPH_OF_INSTRUMENT_RE.match(str(locator or "").strip()):
        return False
    parsed = parse_locator_reference(locator)
    if parsed is None:
        return False
    if isinstance(parsed, ParsedLocatorRange):
        return True
    segment = parsed.segments[0] if parsed.segments else None
    if segment is None:
        return False
    if len(parsed.segments) > 1:
        return False
    return segment.kind in {"paragraph", "sub-paragraph", "point"}


def _is_external_instrument_locator(locator: str) -> bool:
    return bool(EXTERNAL_INSTRUMENT_LOCATOR_RE.search(locator))


def _resolution_from_fragments(
    fragments: list[ResolvedContextFragment],
    *,
    review_status: Literal["accepted", "ambiguous", "unresolved"] | None = None,
    resolution_status: Literal["resolved", "ambiguous", "unresolved", "partially_resolved"] | None = None,
    resolution_mode: Literal["exact", "container", "partial"] | None = None,
    resolved_locator: str | None = None,
    unresolved_child: str | None = None,
    proposition_ids: list[str] | None = None,
    resolution_basis: ResolutionBasis | None = None,
) -> ContextLocatorResolution:
    if review_status is None:
        if len(fragments) == 0:
            review_status = "unresolved"
        elif len(fragments) == 1:
            review_status = "accepted"
        else:
            review_status = "ambiguous"

    if resolution_status is None:
        if review_status == "accepted":
            resolution_status = "resolved"
        elif review_status == "ambiguous":
            resolution_status = "ambiguous"
        else:
            resolution_status = "unresolved"

    if resolution_basis is None:
        if review_status == "unresolved" and not fragments:
            resolution_basis = "unresolved"
        else:
            resolution_basis = "explicit"

    return ContextLocatorResolution(
        resolved=review_status == "accepted",
        review_status=review_status,
        resolution_status=resolution_status,
        proposition_ids=list(proposition_ids or []),
        matched_fragment_ids=[frag.fragment_id for frag in fragments],
        resolution_mode=resolution_mode,
        resolved_locator=resolved_locator,
        unresolved_child=unresolved_child,
        resolution_basis=resolution_basis,
    )


def proposition_ids_for_fragments(
    fragments: list[ResolvedContextFragment],
    propositions: list[dict[str, Any]],
    *,
    source_record_id: str,
) -> list[str]:
    """Map resolved source fragments to proposition ids in the same source."""
    if not fragments:
        return []

    fragment_ids = {frag.fragment_id for frag in fragments}
    fragment_locators = {frag.locator for frag in fragments}
    normalized_locators = {normalize_cross_reference_locator(frag.locator) for frag in fragments}

    matched: list[str] = []
    seen: set[str] = set()
    for prop in propositions:
        if str(prop.get("source_record_id") or "").strip() != source_record_id:
            continue
        prop_id = str(prop.get("id") or "").strip()
        if not prop_id or prop_id in seen:
            continue

        source_fragment_id = str(prop.get("source_fragment_id") or "").strip()
        if source_fragment_id and source_fragment_id in fragment_ids:
            seen.add(prop_id)
            matched.append(prop_id)
            continue

        prop_locator = str(prop.get("fragment_locator") or prop.get("article_reference") or "").strip()
        if not prop_locator:
            continue
        prop_norm = normalize_cross_reference_locator(prop_locator)
        if prop_locator in fragment_locators or prop_norm in normalized_locators:
            seen.add(prop_id)
            matched.append(prop_id)
            continue
        for frag in fragments:
            if locator_matches_target(prop_locator, frag.locator):
                seen.add(prop_id)
                matched.append(prop_id)
                break
    return matched


def resolve_context_locator(
    locator: str,
    *,
    source_record_id: str,
    source_fragments: list[dict[str, Any]],
    structural_context: LocatorStructuralContext | None = None,
    propositions: list[dict[str, Any]] | None = None,
) -> ContextLocatorResolution:
    """Resolve a locator to fragments (and optionally proposition ids) within a source."""
    locator = str(locator or "").strip() or "unknown locator"
    propositions = propositions or []

    if _is_external_instrument_locator(locator):
        return ContextLocatorResolution(
            resolved=False,
            review_status="unresolved",
            resolution_status="unresolved",
            proposition_ids=[],
            matched_fragment_ids=[],
            resolution_basis="unresolved",
        )

    container_targets = (
        None if _is_bare_relative_reference(locator) else parse_container_locator_targets(locator)
    )
    if container_targets:
        container_fragments = _resolve_container_locator_targets(
            container_targets,
            source_record_id=source_record_id,
            source_fragments=source_fragments,
        )
        if container_fragments:
            prop_ids = proposition_ids_for_fragments(
                container_fragments, propositions, source_record_id=source_record_id
            )
            is_broad_container = len(container_targets) == 1 and len(container_targets[0].segments) == 1 and (
                _is_structural_container_kind(container_targets[0].segments[0].kind)
                and container_targets[0].segments[0].sub is None
            )
            mode: Literal["exact", "container", "partial"] = (
                "container"
                if (is_broad_container and len(container_fragments) > 1)
                or len(container_targets) > 1
                else "exact"
            )
            return _resolution_from_fragments(
                container_fragments,
                review_status="accepted",
                resolution_status="resolved" if prop_ids else "unresolved",
                resolution_mode=mode,
                proposition_ids=prop_ids,
            )

    direct_matches = _match_fragments_in_source(source_record_id, locator, source_fragments)

    if len(direct_matches) == 1 and not _is_bare_relative_reference(locator):
        prop_ids = proposition_ids_for_fragments(
            direct_matches, propositions, source_record_id=source_record_id
        )
        return _resolution_from_fragments(
            direct_matches,
            review_status="accepted",
            resolution_status="resolved" if prop_ids else "unresolved",
            resolution_mode="exact",
            proposition_ids=prop_ids,
        )

    if len(direct_matches) > 1 and not _is_bare_relative_reference(locator):
        fallback_container = container_targets or parse_container_locator_targets(locator)
        if fallback_container:
            container_fragments = _resolve_container_locator_targets(
                fallback_container,
                source_record_id=source_record_id,
                source_fragments=source_fragments,
            )
            if container_fragments:
                prop_ids = proposition_ids_for_fragments(
                    container_fragments, propositions, source_record_id=source_record_id
                )
                return _resolution_from_fragments(
                    container_fragments,
                    review_status="accepted",
                    resolution_status="resolved" if prop_ids else "unresolved",
                    resolution_mode="container",
                    proposition_ids=prop_ids,
                )
        prop_ids = proposition_ids_for_fragments(
            direct_matches, propositions, source_record_id=source_record_id
        )
        return _resolution_from_fragments(
            direct_matches,
            review_status="ambiguous",
            resolution_status="ambiguous",
            proposition_ids=prop_ids,
        )

    if not _is_bare_relative_reference(locator):
        instrument_sub = _resolve_instrument_sub_locator(
            locator,
            source_record_id=source_record_id,
            source_fragments=source_fragments,
        )
        if instrument_sub is not None:
            if instrument_sub.matched_fragment_ids:
                fragment_by_id = {
                    _fragment_row_id(frag): frag
                    for frag in _fragments_for_source(source_record_id, source_fragments)
                }
                resolved_frags = [
                    ResolvedContextFragment(
                        fragment_id=fid,
                        locator=str(fragment_by_id[fid].get("locator") or "").strip(),
                    )
                    for fid in instrument_sub.matched_fragment_ids
                    if fid in fragment_by_id
                ]
                prop_ids = proposition_ids_for_fragments(
                    resolved_frags,
                    propositions,
                    source_record_id=source_record_id,
                )
                instrument_sub.proposition_ids = prop_ids
                if prop_ids:
                    instrument_sub.resolved = True
                    instrument_sub.review_status = "accepted"
                    if instrument_sub.resolution_mode == "partial":
                        instrument_sub.resolution_status = "partially_resolved"
                    else:
                        instrument_sub.resolution_status = "resolved"
            return instrument_sub

    parsed = parse_locator_reference(locator)
    should_apply_context = (
        structural_context is not None
        and bool(structural_context.segments)
        and (_is_bare_relative_reference(locator) or isinstance(parsed, ParsedLocatorRange))
    )

    if should_apply_context and structural_context is not None:
        contextualised = (
            apply_structural_context_to_reference(structural_context, parsed)
            if parsed is not None
            else None
        )
        expanded = expand_parsed_locator_reference(contextualised) if contextualised else []
        target_locators = (
            [build_canonical_locator(list(entry.segments)) for entry in expanded]
            if expanded
            else resolve_locator_targets(locator, structural_context)
        )

        if len(target_locators) > 1:
            all_fragments: list[ResolvedContextFragment] = []
            ambiguous = False
            for target_locator in target_locators:
                child_matches = _match_fragments_in_source(
                    source_record_id, target_locator, source_fragments
                )
                if len(child_matches) != 1:
                    ambiguous = True
                all_fragments.extend(child_matches)
            deduped: list[ResolvedContextFragment] = []
            seen: set[str] = set()
            for frag in all_fragments:
                if frag.fragment_id not in seen:
                    seen.add(frag.fragment_id)
                    deduped.append(frag)
            prop_ids = proposition_ids_for_fragments(
                deduped, propositions, source_record_id=source_record_id
            )
            all_resolved = not ambiguous and len(deduped) == len(target_locators)
            return _resolution_from_fragments(
                deduped,
                review_status="accepted" if all_resolved and deduped else "ambiguous" if deduped else "unresolved",
                resolution_status=(
                    "resolved"
                    if all_resolved and prop_ids
                    else "ambiguous"
                    if deduped
                    else "unresolved"
                ),
                resolution_mode="exact",
                resolved_locator=", ".join(target_locators),
                proposition_ids=prop_ids,
                resolution_basis="structural_relative",
            )

        resolved_locator = target_locators[0] if target_locators else locator
        target_segments = (
            list(expanded[0].segments)
            if expanded and expanded[0].segments
            else (parse_locator_structural_context(resolved_locator).segments if parse_locator_structural_context(resolved_locator) else [])
        )
        if target_segments:
            contextual_resolution = _resolve_contextual_paragraph_target(
                target_segments,
                source_record_id=source_record_id,
                source_fragments=source_fragments,
                propositions=propositions,
                resolved_locator=resolved_locator,
            )
            if contextual_resolution is not None:
                contextual_resolution.resolution_basis = "structural_relative"
                return contextual_resolution

        contextual_matches = _match_fragments_in_source(
            source_record_id, resolved_locator, source_fragments
        )
        if len(contextual_matches) == 1:
            prop_ids = proposition_ids_for_fragments(
                contextual_matches, propositions, source_record_id=source_record_id
            )
            return _resolution_from_fragments(
                contextual_matches,
                review_status="accepted",
                resolution_status="resolved" if prop_ids else "unresolved",
                proposition_ids=prop_ids,
                resolved_locator=resolved_locator,
                resolution_basis="structural_relative",
            )
        if len(contextual_matches) > 1:
            prop_ids = proposition_ids_for_fragments(
                contextual_matches, propositions, source_record_id=source_record_id
            )
            return _resolution_from_fragments(
                contextual_matches,
                review_status="accepted",
                resolution_status="resolved" if prop_ids else "ambiguous",
                resolution_mode="container",
                proposition_ids=prop_ids,
                resolved_locator=resolved_locator,
                resolution_basis="structural_relative",
            )

    # Fully qualified parsed references (e.g. ``paragraph 1 of Article 14``).
    if (
        not should_apply_context
        and isinstance(parsed, ParsedLocatorSingle)
        and parsed.segments
        and not _is_bare_relative_reference(locator)
    ):
        target_segments = list(parsed.segments)
        resolved_locator = build_canonical_locator(target_segments) or locator
        if any(seg.kind == "paragraph" for seg in target_segments):
            contextual_resolution = _resolve_contextual_paragraph_target(
                target_segments,
                source_record_id=source_record_id,
                source_fragments=source_fragments,
                propositions=propositions,
                resolved_locator=resolved_locator,
            )
            if contextual_resolution is not None:
                contextual_resolution.resolution_basis = "explicit"
                return contextual_resolution
        qualified_matches = _match_fragments_in_source(
            source_record_id,
            resolved_locator,
            source_fragments,
        )
        if len(qualified_matches) == 1:
            prop_ids = proposition_ids_for_fragments(
                qualified_matches, propositions, source_record_id=source_record_id
            )
            return _resolution_from_fragments(
                qualified_matches,
                review_status="accepted",
                resolution_status="resolved" if prop_ids else "unresolved",
                proposition_ids=prop_ids,
                resolved_locator=resolved_locator,
                resolution_basis="explicit",
            )
        if len(qualified_matches) > 1:
            prop_ids = proposition_ids_for_fragments(
                qualified_matches, propositions, source_record_id=source_record_id
            )
            return _resolution_from_fragments(
                qualified_matches,
                review_status="ambiguous",
                resolution_status="ambiguous",
                proposition_ids=prop_ids,
                resolved_locator=resolved_locator,
                resolution_basis="explicit",
            )

    if (
        not should_apply_context
        and isinstance(parsed, ParsedLocatorSingle)
        and _is_bare_relative_reference(locator)
    ):
        bare_paragraph = next(
            (seg for seg in parsed.segments if seg.kind == "paragraph"),
            None,
        )
        if bare_paragraph is not None:
            bare_matches = _match_bare_paragraph_fragments_in_source(
                source_record_id,
                bare_paragraph.num,
                bare_paragraph.sub,
                source_fragments,
            )
            if len(bare_matches) == 1:
                prop_ids = proposition_ids_for_fragments(
                    bare_matches, propositions, source_record_id=source_record_id
                )
                return _resolution_from_fragments(
                    bare_matches,
                    review_status="accepted",
                    resolution_status="resolved" if prop_ids else "unresolved",
                    proposition_ids=prop_ids,
                    resolution_basis="instrument_wide",
                )
            if len(bare_matches) > 1:
                prop_ids = proposition_ids_for_fragments(
                    bare_matches, propositions, source_record_id=source_record_id
                )
                return _resolution_from_fragments(
                    bare_matches,
                    review_status="ambiguous",
                    resolution_status="ambiguous",
                    proposition_ids=prop_ids,
                    resolution_basis="instrument_wide",
                )

    return ContextLocatorResolution(
        resolved=False,
        review_status="unresolved",
        resolution_status="unresolved",
        proposition_ids=[],
        matched_fragment_ids=[],
        resolution_basis="unresolved",
    )


def structural_context_for_proposition(
    prop: dict[str, Any],
    source_fragments: list[dict[str, Any]] | None = None,
) -> LocatorStructuralContext | None:
    """Derive enclosing provision context for relative locator qualification.

    Preference order:
    1. Canonical locator on the proposition's ``source_fragment_id`` (and parents)
    2. Parsed ``fragment_locator`` / ``article_reference`` on the proposition

    Free-text extraction locators such as ``article 49a, paragraph 2(b)`` often fail
    to parse; the source-fragment hierarchy supplies the reliable structural path.
    """
    source_id = str(prop.get("source_record_id") or "").strip() or None
    locator_candidates: list[str] = []

    frag_id = str(prop.get("source_fragment_id") or "").strip()
    if frag_id and source_fragments:
        by_id = {
            str(row.get("id") or row.get("fragment_id") or "").strip(): row
            for row in source_fragments
            if isinstance(row, dict)
        }
        seen_ids: set[str] = set()
        current_id: str | None = frag_id
        while current_id and current_id not in seen_ids:
            seen_ids.add(current_id)
            row = by_id.get(current_id)
            if row is None:
                break
            if source_id and str(row.get("source_record_id") or "").strip() not in {"", source_id}:
                break
            loc = str(row.get("locator") or "").strip()
            if loc:
                locator_candidates.append(loc)
            parent_id = str(row.get("parent_fragment_id") or "").strip()
            current_id = parent_id or None

    for key in ("fragment_locator", "article_reference"):
        value = str(prop.get(key) or "").strip()
        if value:
            locator_candidates.append(value)

    for locator in locator_candidates:
        parsed = parse_locator_structural_context(locator)
        if parsed is not None and parsed.segments:
            return LocatorStructuralContext(
                segments=list(parsed.segments),
                source_record_id=source_id,
            )

    if locator_candidates or source_id:
        return LocatorStructuralContext(segments=[], source_record_id=source_id)
    return None
