"""Detect legal anchors in dense source fragments and verify proposition coverage."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from law_proposition_extractor_domain.proposition_notes import resolve_extraction_meta_for_proposition

NPP_2015_SOURCE_ID = "lex-120b4f9c395b3f94"

_REG2_LOCATOR_RE = re.compile(r"^regulation\s*:?\s*2\b", re.IGNORECASE)


def normalize_fragment_locator(locator: str | None) -> str:
    return str(locator or "").strip().lower()


def locator_matches_regulation_2(locator: str | None) -> bool:
    normalized = normalize_fragment_locator(locator)
    if normalized == "regulation:2":
        return True
    return bool(
        _REG2_LOCATOR_RE.match(normalized.replace(":", " "))
        or _REG2_LOCATOR_RE.match(normalized)
    )


def proposition_belongs_to_fragment(
    row: dict[str, Any],
    *,
    source_record_id: str,
    source_fragment_id: str | None,
    fragment_locator: str,
) -> bool:
    if str(row.get("source_record_id") or "") != source_record_id:
        return False
    frag_id = str(row.get("source_fragment_id") or "").strip() or None
    if source_fragment_id and frag_id == source_fragment_id:
        return True
    row_loc = str(row.get("fragment_locator") or "").strip()
    if row_loc and normalize_fragment_locator(row_loc) == normalize_fragment_locator(fragment_locator):
        return True
    if source_fragment_id and not frag_id:
        article = str(row.get("article_reference") or "")
        if locator_matches_regulation_2(fragment_locator) and locator_matches_regulation_2(article):
            return True
    return False


def npp_reg2_proposition_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("source_record_id") or "") != NPP_2015_SOURCE_ID:
            continue
        if locator_matches_regulation_2(str(row.get("fragment_locator") or "")):
            out.append(row)
            continue
        if locator_matches_regulation_2(str(row.get("article_reference") or "")):
            out.append(row)
    return out

AnchorCategory = Literal["definition", "table", "boilerplate", "exception"]
AnchorSeverity = Literal["critical", "important", "diagnostic"]

DENSE_FRAGMENT_MIN_CHARS = 800
DENSE_FRAGMENT_MIN_DEFINITION_ANCHORS = 3
MIN_USEFUL_ANCHOR_LABEL_LEN = 4

CORE_REGULATED_CONCEPTS: frozenset[str] = frozenset(
    {
        "slurry",
        "silage",
        "agricultural land",
        "fuel oil",
        "land manager",
        "construct",
        "storage system",
        "organic manure",
        "agricultural",
        "spreading",
    }
)

CRITICAL_BOILERPLATE_DETECTORS: frozenset[str] = frozenset(
    {"citation", "commencement", "extent", "application"}
)

LIVESTOCK_CATEGORY_LABELS: frozenset[str] = frozenset(
    {
        "cattle",
        "sheep",
        "goats",
        "deer",
        "horses",
        "poultry",
        "pigs",
        "dairy cow",
        "chicken",
        "turkey",
        "duck",
        "ostrich",
    }
)

_SHORT_LABEL_WHITELIST: frozenset[str] = frozenset(
    {"slurry", "silage", "fuel oil", "pigs", "deer", "goats", "sheep"}
)

_QUOTED_TERM = r'["\u201c]([^"\u201d]{2,80})["\u201d]'

_DEFINITION_DETECTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "definition_means",
        re.compile(rf"{_QUOTED_TERM}\s+means\b", re.IGNORECASE),
    ),
    (
        "definition_includes",
        re.compile(rf"{_QUOTED_TERM}\s+includes\b", re.IGNORECASE),
    ),
    (
        "definition_includes_qualified",
        re.compile(rf'{_QUOTED_TERM}[^;]{{0,160}}\bincludes\b', re.IGNORECASE),
    ),
    (
        "definition_same_meaning",
        re.compile(
            rf"{_QUOTED_TERM}\s+has the same meaning as\b",
            re.IGNORECASE,
        ),
    ),
    (
        "definition_meaning_given",
        re.compile(
            rf"{_QUOTED_TERM}\s+has the meaning given\b",
            re.IGNORECASE,
        ),
    ),
    (
        "definition_does_not_include",
        re.compile(
            rf"{_QUOTED_TERM}\s+does not include\b",
            re.IGNORECASE,
        ),
    ),
    (
        "unquoted_means",
        re.compile(
            r"\b([a-z][a-z0-9\s\-]{1,50}?)\s+means\b",
            re.IGNORECASE,
        ),
    ),
)

_TABLE_DETECTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "numeric_unit_cell",
        re.compile(
            r"\b(\d+(?:\.\d+)?\s*(?:kg|hectare|hectares|tonnes?|metres?|m)\b[^;]{0,40})",
            re.IGNORECASE,
        ),
    ),
    (
        "livestock_category",
        re.compile(
            r"\b(cattle|sheep|goats|deer|horses|poultry|pigs|dairy cow|chicken|turkey|duck|ostrich)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "table_row_label",
        re.compile(
            r"(?:^|[;\n])\s*([A-Z][a-z]+(?:\s+[a-z]+){0,4})\s+(?:produces|means|is)\s+",
            re.MULTILINE,
        ),
    ),
)

_BOILERPLATE_DETECTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("citation", re.compile(r"\bSI\s+\d{4}/\d+\b|\bstatutory instrument\b", re.IGNORECASE)),
    (
        "commencement",
        re.compile(
            r"\bcomes into force\b|\bcommencement\b|\bin force on\b",
            re.IGNORECASE,
        ),
    ),
    (
        "extent",
        re.compile(
            r"\bextends to\b|\bextent of\b|\bapply to england and wales\b",
            re.IGNORECASE,
        ),
    ),
    (
        "application",
        re.compile(
            r"\bthese regulations apply\b|\bapply to agricultural\b|\bapplies to\b",
            re.IGNORECASE,
        ),
    ),
)

_EXCEPTION_DETECTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("does_not_apply", re.compile(r"\bdoes not apply\b", re.IGNORECASE)),
    ("except", re.compile(r"\bexcept\b", re.IGNORECASE)),
    ("unless", re.compile(r"\bunless\b", re.IGNORECASE)),
    ("subject_to", re.compile(r"\bsubject to\b", re.IGNORECASE)),
    ("may_exceed", re.compile(r"\bmay exceed\b", re.IGNORECASE)),
    ("provided_that", re.compile(r"\bprovided that\b", re.IGNORECASE)),
)

NPP_REG2_REQUIRED_ANCHORS: frozenset[str] = frozenset(
    {"slurry", "organic manure", "agricultural", "spreading"}
)


@dataclass(frozen=True)
class DetectedAnchor:
    anchor_id: str
    category: AnchorCategory
    label: str
    source_excerpt: str
    search_terms: tuple[str, ...]
    severity: AnchorSeverity = "important"
    detector_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "category": self.category,
            "label": self.label,
            "source_excerpt": self.source_excerpt[:200],
            "search_terms": list(self.search_terms),
            "severity": self.severity,
            "detector_id": self.detector_id,
        }


@dataclass
class FragmentAnchorCoverage:
    source_record_id: str
    source_fragment_id: str | None
    fragment_locator: str
    dense: bool
    detected_count: int
    covered_count: int
    missing: list[DetectedAnchor] = field(default_factory=list)
    covered: list[DetectedAnchor] = field(default_factory=list)

    @property
    def all_covered(self) -> bool:
        return not self.missing

    def to_dict(self) -> dict[str, Any]:
        missing_by_severity = {
            "critical": sum(1 for a in self.missing if a.severity == "critical"),
            "important": sum(1 for a in self.missing if a.severity == "important"),
            "diagnostic": sum(1 for a in self.missing if a.severity == "diagnostic"),
        }
        return {
            "source_record_id": self.source_record_id,
            "source_fragment_id": self.source_fragment_id,
            "fragment_locator": self.fragment_locator,
            "dense": self.dense,
            "detected_count": self.detected_count,
            "covered_count": self.covered_count,
            "all_covered": self.all_covered,
            "missing_by_severity": missing_by_severity,
            "missing": [a.to_dict() for a in self.missing],
            "covered": [a.label for a in self.covered],
        }


def _slug_anchor(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")[:80]


def _normalise_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def _anchor_from_match(
    *,
    category: AnchorCategory,
    label: str,
    excerpt: str,
    detector_id: str,
    extra_terms: tuple[str, ...] = (),
    severity: AnchorSeverity | None = None,
) -> DetectedAnchor:
    term = _normalise_term(label)
    terms = tuple(dict.fromkeys((term, *extra_terms, excerpt[:60].lower())))
    anchor_id = f"{category}:{detector_id}:{_slug_anchor(term)}"
    return DetectedAnchor(
        anchor_id=anchor_id,
        category=category,
        label=term,
        source_excerpt=excerpt.strip(),
        search_terms=terms,
        detector_id=detector_id,
        severity=severity or "important",
    )


def _label_matches_core_concept(label: str) -> bool:
    lower = _normalise_term(label)
    if lower in CORE_REGULATED_CONCEPTS:
        return True
    return any(lower == req for req in NPP_REG2_REQUIRED_ANCHORS)


def _label_matches_npp_reg2_required(label: str) -> bool:
    lower = _normalise_term(label)
    return lower in NPP_REG2_REQUIRED_ANCHORS


def _is_regulation_1_locator(fragment_locator: str) -> bool:
    loc = normalize_fragment_locator(fragment_locator)
    return loc in {"regulation:1", "regulation 1"}


def _does_not_apply_is_substantive_carveout(excerpt: str) -> bool:
    """Critical only when the carve-out sits beside obligation/prohibition language."""
    lower = excerpt.lower()
    window = lower
    if len(lower) > 240:
        idx = lower.find("does not apply")
        if idx >= 0:
            window = lower[max(0, idx - 120) : idx + 120]
    obligation_markers = (
        "must",
        "shall",
        "prohibited",
        "required to",
        " offence",
        "guilty",
        " contraven",
        " fail to",
        " shall not",
        " must not",
    )
    return any(marker in window for marker in obligation_markers)


def _is_interpretation_locator(fragment_locator: str) -> bool:
    loc = normalize_fragment_locator(fragment_locator)
    return locator_matches_regulation_2(loc) or "interpretation" in loc


def _is_table_noise_excerpt(excerpt: str) -> bool:
    """Detect chopped OCR/HTML table artefacts in numeric cell excerpts."""
    if re.search(r"[<>]{1,2}|\d{4,}\s*\d{3,}|kg\s*\d|\d+\s*kg\s*\d", excerpt, re.IGNORECASE):
        return True
    return len(excerpt) > 80 and excerpt.count(" ") > 12


def classify_anchor_severity(
    anchor: DetectedAnchor,
    *,
    source_record_id: str,
    fragment_locator: str,
) -> AnchorSeverity:
    """Classify anchor severity for acceptance gating."""
    detector = anchor.detector_id
    label = anchor.label.lower()
    loc = normalize_fragment_locator(fragment_locator)

    if detector == "livestock_category" or label in LIVESTOCK_CATEGORY_LABELS:
        return "diagnostic"

    if anchor.category == "table":
        if detector == "numeric_unit_cell" or _is_table_noise_excerpt(anchor.source_excerpt):
            return "diagnostic"
        if detector == "table_row_label":
            return "important"
        return "diagnostic"

    if anchor.category == "boilerplate":
        if detector in CRITICAL_BOILERPLATE_DETECTORS and _is_regulation_1_locator(fragment_locator):
            return "critical"
        return "diagnostic"

    if anchor.category == "exception":
        if detector == "does_not_apply":
            if _does_not_apply_is_substantive_carveout(anchor.source_excerpt):
                return "critical"
            return "important"
        return "important"

    if anchor.category == "definition":
        if (
            source_record_id == NPP_2015_SOURCE_ID
            and locator_matches_regulation_2(fragment_locator)
            and (
                _label_matches_npp_reg2_required(label)
                or _label_matches_core_concept(label)
            )
        ):
            return "critical"
        if _is_interpretation_locator(fragment_locator):
            return "important"
        if len(label) < MIN_USEFUL_ANCHOR_LABEL_LEN and label not in _SHORT_LABEL_WHITELIST:
            return "diagnostic"
        return "important"

    if len(label) < MIN_USEFUL_ANCHOR_LABEL_LEN and label not in _SHORT_LABEL_WHITELIST:
        return "diagnostic"
    return "important"


def _with_severity(
    anchor: DetectedAnchor,
    *,
    source_record_id: str,
    fragment_locator: str,
) -> DetectedAnchor:
    severity = classify_anchor_severity(
        anchor,
        source_record_id=source_record_id,
        fragment_locator=fragment_locator,
    )
    if anchor.severity == severity:
        return anchor
    return DetectedAnchor(
        anchor_id=anchor.anchor_id,
        category=anchor.category,
        label=anchor.label,
        source_excerpt=anchor.source_excerpt,
        search_terms=anchor.search_terms,
        severity=severity,
        detector_id=anchor.detector_id,
    )


def _dedupe_anchor_key(
    anchor: DetectedAnchor,
    *,
    source_record_id: str,
    fragment_locator: str,
) -> tuple[str, str, str, str]:
    return (
        source_record_id,
        normalize_fragment_locator(fragment_locator),
        anchor.category,
        _normalise_term(anchor.label),
    )


def dedupe_anchors(
    anchors: list[DetectedAnchor],
    *,
    source_record_id: str,
    fragment_locator: str,
) -> list[DetectedAnchor]:
    """Dedupe anchors by source, locator, category, and normalised label."""
    seen: set[tuple[str, str, str, str]] = set()
    out: list[DetectedAnchor] = []
    for anchor in anchors:
        key = _dedupe_anchor_key(
            anchor,
            source_record_id=source_record_id,
            fragment_locator=fragment_locator,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(anchor)
    return out


def detect_anchors_from_fragment_text(fragment_text: str) -> list[DetectedAnchor]:
    """Detect legal anchors from dense fragment source text."""
    text = str(fragment_text or "").strip()
    if not text:
        return []

    anchors: list[DetectedAnchor] = []
    seen_ids: set[str] = set()

    def add(anchor: DetectedAnchor) -> None:
        if anchor.anchor_id in seen_ids:
            return
        seen_ids.add(anchor.anchor_id)
        anchors.append(anchor)

    for detector_id, pattern in _DEFINITION_DETECTORS:
        for match in pattern.finditer(text):
            term = match.group(1).strip()
            if len(term) < 2 or term.lower() in {"the", "a", "an"}:
                continue
            add(
                _anchor_from_match(
                    category="definition",
                    label=term,
                    excerpt=match.group(0),
                    detector_id=detector_id,
                )
            )

    locator_hints_table = "schedule" in text.lower() or "table" in text.lower()
    for detector_id, pattern in _TABLE_DETECTORS:
        for match in pattern.finditer(text):
            label = match.group(1).strip()
            if detector_id == "livestock_category" and label.lower() not in {
                "cattle",
                "sheep",
                "goats",
                "deer",
                "horses",
                "poultry",
                "pigs",
                "dairy cow",
                "chicken",
                "turkey",
                "duck",
                "ostrich",
            }:
                continue
            if detector_id == "table_row_label" and not locator_hints_table:
                continue
            add(
                _anchor_from_match(
                    category="table",
                    label=label,
                    excerpt=match.group(0),
                    detector_id=detector_id,
                )
            )

    for detector_id, pattern in _BOILERPLATE_DETECTORS:
        if match := pattern.search(text):
            add(
                _anchor_from_match(
                    category="boilerplate",
                    label=detector_id.replace("_", " "),
                    excerpt=match.group(0),
                    detector_id=detector_id,
                )
            )

    for detector_id, pattern in _EXCEPTION_DETECTORS:
        if match := pattern.search(text):
            add(
                _anchor_from_match(
                    category="exception",
                    label=detector_id.replace("_", " "),
                    excerpt=match.group(0),
                    detector_id=detector_id,
                    extra_terms=(match.group(0).lower(),),
                )
            )

    return anchors


def is_dense_fragment(fragment_text: str, detected: list[DetectedAnchor]) -> bool:
    text = str(fragment_text or "")
    definition_count = sum(1 for a in detected if a.category == "definition")
    return len(text) >= DENSE_FRAGMENT_MIN_CHARS or definition_count >= DENSE_FRAGMENT_MIN_DEFINITION_ANCHORS


def filter_anchors_for_acceptance(
    anchors: list[DetectedAnchor],
    *,
    source_record_id: str,
    fragment_locator: str,
) -> list[DetectedAnchor]:
    """
    Subset of detected anchors that acceptance gates on (avoids requiring every
    dictionary definition in interpretation-heavy fragments).
    """
    non_definition = [a for a in anchors if a.category != "definition"]
    definitions = [a for a in anchors if a.category == "definition"]

    if (
        source_record_id == NPP_2015_SOURCE_ID
        and locator_matches_regulation_2(fragment_locator)
    ):
        priority_defs: list[DetectedAnchor] = []
        for required in NPP_REG2_REQUIRED_ANCHORS:
            for anchor in definitions:
                if required in anchor.label.lower():
                    priority_defs.append(anchor)
                    break
        return non_definition + priority_defs

    locator_lower = fragment_locator.lower()
    schedule_or_table = "schedule" in locator_lower or "table" in locator_lower
    filtered_defs: list[DetectedAnchor] = []
    for anchor in definitions:
        label = anchor.label.lower()
        if len(label) > 40:
            continue
        if re.search(r"directive|regulation \(ec\)|council regulation", label):
            continue
        filtered_defs.append(anchor)

    tables = [a for a in anchors if a.category == "table"] if schedule_or_table else []
    cap = 12 if schedule_or_table else 8
    return non_definition + tables + filtered_defs[:cap]


def proposition_coverage_haystack(row: dict[str, Any]) -> str:
    """Fields where anchor terms may appear for coverage checks."""
    parts = [
        str(row.get("proposition_text") or ""),
        str(row.get("label") or ""),
        str(row.get("short_name") or ""),
        str(row.get("legal_subject") or ""),
        str(row.get("action") or ""),
        str(row.get("object_text") or ""),
    ]
    for key in ("affected_subjects", "conditions", "exceptions", "required_documents"):
        raw = row.get(key)
        if isinstance(raw, list):
            parts.extend(str(x) for x in raw)
    meta = resolve_extraction_meta_for_proposition(
        notes=str(row.get("notes") or ""),
        extraction_debug_meta=row.get("extraction_debug_meta")
        if isinstance(row.get("extraction_debug_meta"), dict)
        else None,
    )
    if isinstance(meta, dict):
        eq = str(meta.get("evidence_quote") or meta.get("evidence_text") or "")
        if eq:
            parts.append(eq)
    notes = str(row.get("notes") or "")
    if notes:
        parts.append(notes)
    return " ".join(parts)


def anchor_is_covered(anchor: DetectedAnchor, haystack: str) -> bool:
    hay = haystack.lower()
    for term in anchor.search_terms:
        token = str(term).strip().lower()
        if len(token) >= 2 and token in hay:
            return True
    return False


def check_fragment_anchor_coverage(
    *,
    source_record_id: str,
    source_fragment_id: str | None,
    fragment_locator: str,
    fragment_text: str,
    proposition_rows: list[dict[str, Any]],
) -> FragmentAnchorCoverage:
    detected = detect_anchors_from_fragment_text(fragment_text)
    dense = is_dense_fragment(fragment_text, detected)
    if not dense:
        return FragmentAnchorCoverage(
            source_record_id=source_record_id,
            source_fragment_id=source_fragment_id,
            fragment_locator=fragment_locator,
            dense=False,
            detected_count=len(detected),
            covered_count=len(detected),
        )

    required = filter_anchors_for_acceptance(
        detected,
        source_record_id=source_record_id,
        fragment_locator=fragment_locator,
    )
    required = dedupe_anchors(
        required,
        source_record_id=source_record_id,
        fragment_locator=fragment_locator,
    )
    required = [
        _with_severity(
            anchor,
            source_record_id=source_record_id,
            fragment_locator=fragment_locator,
        )
        for anchor in required
    ]
    haystacks = [proposition_coverage_haystack(row) for row in proposition_rows]
    covered_list: list[DetectedAnchor] = []
    missing_list: list[DetectedAnchor] = []
    for anchor in required:
        if any(anchor_is_covered(anchor, hay) for hay in haystacks):
            covered_list.append(anchor)
        else:
            missing_list.append(anchor)

    return FragmentAnchorCoverage(
        source_record_id=source_record_id,
        source_fragment_id=source_fragment_id,
        fragment_locator=fragment_locator,
        dense=True,
        detected_count=len(required),
        covered_count=len(covered_list),
        missing=missing_list,
        covered=covered_list,
    )


def _rows_for_fragment(
    rows: list[dict[str, Any]],
    *,
    source_record_id: str,
    source_fragment_id: str | None,
    fragment_locator: str,
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and proposition_belongs_to_fragment(
            row,
            source_record_id=source_record_id,
            source_fragment_id=source_fragment_id,
            fragment_locator=fragment_locator,
        )
    ]


def _aggregate_missing_by_severity(
    reports: list[FragmentAnchorCoverage],
) -> dict[str, int]:
    totals = {"critical": 0, "important": 0, "diagnostic": 0}
    for report in reports:
        for anchor in report.missing:
            totals[anchor.severity] = totals.get(anchor.severity, 0) + 1
    return totals


def _top_fragments_by_missing_severity(
    reports: list[FragmentAnchorCoverage],
    severity: AnchorSeverity,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, FragmentAnchorCoverage]] = []
    for report in reports:
        count = sum(1 for a in report.missing if a.severity == severity)
        if count:
            ranked.append((count, report))
    ranked.sort(key=lambda item: (-item[0], normalize_fragment_locator(item[1].fragment_locator)))
    out: list[dict[str, Any]] = []
    for count, report in ranked[:limit]:
        missing_labels = [a.label for a in report.missing if a.severity == severity][:8]
        out.append(
            {
                "fragment_locator": report.fragment_locator,
                "source_record_id": report.source_record_id,
                "missing_count": count,
                "sample_missing": missing_labels,
            }
        )
    return out


def _diagnostic_table_noise_summary(
    reports: list[FragmentAnchorCoverage],
) -> dict[str, Any]:
    livestock_missing = 0
    numeric_missing = 0
    schedule_duplicates = 0
    by_fragment: dict[str, dict[str, int]] = {}

    for report in reports:
        frag_key = normalize_fragment_locator(report.fragment_locator)
        frag_counts = by_fragment.setdefault(frag_key, {"livestock": 0, "numeric": 0, "other": 0})
        for anchor in report.missing:
            if anchor.severity != "diagnostic":
                continue
            if anchor.detector_id == "livestock_category":
                livestock_missing += 1
                frag_counts["livestock"] += 1
            elif anchor.detector_id == "numeric_unit_cell":
                numeric_missing += 1
                frag_counts["numeric"] += 1
            else:
                frag_counts["other"] += 1
        if "schedule" in frag_key and frag_counts["livestock"] + frag_counts["numeric"] > 3:
            schedule_duplicates += frag_counts["livestock"] + frag_counts["numeric"]

    top_noisy = sorted(
        (
            {"fragment_locator": loc, **counts}
            for loc, counts in by_fragment.items()
            if counts["livestock"] + counts["numeric"] + counts["other"] > 0
        ),
        key=lambda item: -(item["livestock"] + item["numeric"] + item["other"]),
    )[:8]

    return {
        "livestock_category_missing": livestock_missing,
        "numeric_table_cell_missing": numeric_missing,
        "schedule_table_noise_count": schedule_duplicates,
        "top_noisy_fragments": top_noisy,
    }


def summarize_export_fragment_anchor_coverage(
    bundle: dict[str, Any],
    *,
    propositions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check anchor coverage for all dense fragments in an export bundle."""
    props = propositions if propositions is not None else [
        row for row in (bundle.get("propositions") or []) if isinstance(row, dict)
    ]
    fragments = [
        row for row in (bundle.get("source_fragments") or []) if isinstance(row, dict)
    ]
    fragment_reports: list[FragmentAnchorCoverage] = []
    for frag in fragments:
        sid = str(frag.get("source_record_id") or "").strip()
        if not sid:
            continue
        frag_id = str(frag.get("id") or "").strip() or None
        locator = str(frag.get("locator") or frag.get("fragment_locator") or "").strip()
        text = str(frag.get("fragment_text") or "")
        frag_rows = _rows_for_fragment(
            props,
            source_record_id=sid,
            source_fragment_id=frag_id,
            fragment_locator=locator,
        )
        report = check_fragment_anchor_coverage(
            source_record_id=sid,
            source_fragment_id=frag_id,
            fragment_locator=locator,
            fragment_text=text,
            proposition_rows=frag_rows,
        )
        if report.dense:
            fragment_reports.append(report)

    missing_fragments = [r for r in fragment_reports if not r.all_covered]
    missing_by_severity = _aggregate_missing_by_severity(missing_fragments)
    npp_reg2 = _summarize_npp_reg2_from_coverage(fragment_reports, props)

    all_critical_covered = missing_by_severity.get("critical", 0) == 0
    all_important_covered = (
        missing_by_severity.get("critical", 0) == 0
        and missing_by_severity.get("important", 0) == 0
    )

    return {
        "fragments_checked": len(fragment_reports),
        "dense_fragments": len(fragment_reports),
        "fragments_with_missing_anchors": [r.to_dict() for r in missing_fragments],
        "missing_anchor_count": sum(len(r.missing) for r in missing_fragments),
        "missing_by_severity": missing_by_severity,
        "missing_critical_count": missing_by_severity.get("critical", 0),
        "missing_important_count": missing_by_severity.get("important", 0),
        "missing_diagnostic_count": missing_by_severity.get("diagnostic", 0),
        "all_dense_anchors_covered": not missing_fragments,
        "all_critical_anchors_covered": all_critical_covered,
        "all_important_anchors_covered": all_important_covered,
        "top_fragments_missing_critical": _top_fragments_by_missing_severity(
            missing_fragments, "critical"
        ),
        "top_fragments_missing_important": _top_fragments_by_missing_severity(
            missing_fragments, "important"
        ),
        "diagnostic_table_noise_summary": _diagnostic_table_noise_summary(missing_fragments),
        "npp_reg2": npp_reg2,
        # Back-compat flat anchor map used by acceptance status
        "anchors": npp_reg2.get("anchors", {}),
        "all_present": npp_reg2.get("all_present", True),
        "reg2_proposition_count": npp_reg2.get("reg2_proposition_count", 0),
    }


def _summarize_npp_reg2_from_coverage(
    fragment_reports: list[FragmentAnchorCoverage],
    all_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """NPP 2015 regulation 2 anchor summary for regression and legacy consumers."""
    reg2_report: FragmentAnchorCoverage | None = None
    for report in fragment_reports:
        if report.source_record_id != NPP_2015_SOURCE_ID:
            continue
        if locator_matches_regulation_2(report.fragment_locator):
            reg2_report = report
            break

    reg2_rows = [
        row
        for row in all_rows
        if str(row.get("source_record_id") or "") == NPP_2015_SOURCE_ID
        and (
            locator_matches_regulation_2(str(row.get("fragment_locator") or ""))
            or locator_matches_regulation_2(str(row.get("article_reference") or ""))
        )
    ]

    if reg2_report is None and not reg2_rows:
        return {
            "reg2_proposition_count": 0,
            "anchors": {
                name: {"present": True, "proposition_ids": [], "count": 0}
                for name in sorted(NPP_REG2_REQUIRED_ANCHORS)
            },
            "all_present": True,
            "fragment_coverage": None,
        }

    def _matches_required(anchor: DetectedAnchor, required: str) -> bool:
        req = required.lower()
        if req in anchor.label.lower():
            return True
        return any(req in str(t).lower() for t in anchor.search_terms)

    anchors: dict[str, dict[str, Any]] = {}
    for name in sorted(NPP_REG2_REQUIRED_ANCHORS):
        present = False
        proposition_ids: list[str] = []
        if reg2_report is not None:
            related = [
                a
                for a in reg2_report.covered + reg2_report.missing
                if _matches_required(a, name)
            ]
            if related:
                present = any(a in reg2_report.covered for a in related)
        if not present:
            for row in reg2_rows:
                hay = proposition_coverage_haystack(row)
                if name in hay.lower():
                    present = True
                    pid = str(row.get("id") or "")
                    if pid:
                        proposition_ids.append(pid)
        anchors[name] = {
            "present": present,
            "proposition_ids": proposition_ids[:10],
            "count": len(proposition_ids),
        }

    return {
        "reg2_proposition_count": len(reg2_rows),
        "anchors": anchors,
        "all_present": all(info["present"] for info in anchors.values()),
        "fragment_coverage": reg2_report.to_dict() if reg2_report else None,
    }


def fragments_needing_llm_repair(coverage_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Return dense fragments with missing anchors, ordered for repair (NPP reg2 first)."""
    raw = coverage_summary.get("fragments_with_missing_anchors") or []
    if not isinstance(raw, list):
        return []

    def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        sid = str(item.get("source_record_id") or "")
        loc = normalize_fragment_locator(str(item.get("fragment_locator") or ""))
        missing_by = item.get("missing_by_severity") if isinstance(item.get("missing_by_severity"), dict) else {}
        critical = int(missing_by.get("critical") or 0)
        important = int(missing_by.get("important") or 0)
        priority = 0 if sid == NPP_2015_SOURCE_ID and loc in {"regulation:2", "regulation 2"} else 1
        return (priority, -(critical * 100 + important), loc)

    return sorted([x for x in raw if isinstance(x, dict)], key=sort_key)


def summarize_npp_reg2_definition_anchors(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Proposition-haystack check for required NPP 2015 regulation 2 definition anchors."""
    reg2_rows = npp_reg2_proposition_rows(rows)
    anchors: dict[str, dict[str, Any]] = {}
    for name in sorted(NPP_REG2_REQUIRED_ANCHORS):
        hits: list[str] = []
        for row in reg2_rows:
            hay = proposition_coverage_haystack(row)
            if name in hay.lower():
                pid = str(row.get("id") or "")
                if pid:
                    hits.append(pid)
        anchors[name] = {
            "present": bool(hits),
            "proposition_ids": hits[:10],
            "count": len(hits),
        }
    return {
        "reg2_proposition_count": len(reg2_rows),
        "anchors": anchors,
        "all_present": all(info["present"] for info in anchors.values()),
    }


def check_structured_list_terminal_coverage(
    *,
    fragment_text: str,
    fragment_locator: str,
    proposition_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify every structured-list terminal leaf is covered by a proposition.

    Returns diagnostics with code ``structured_list_terminal_uncovered`` for missing
    terminals. Empty ``expected_terminals`` when the fragment has no clear list structure.
    """
    from law_proposition_extractor_pipeline.structured_list_decomposition import (
        COVERAGE_DIAGNOSTIC,
        draft_structured_list_leaves,
        unmatched_terminal_diagnostics,
    )

    drafts = draft_structured_list_leaves(fragment_text, fragment_locator)
    if not drafts:
        return {
            "fragment_locator": fragment_locator,
            "expected_terminals": [],
            "covered_terminals": [],
            "missing_terminals": [],
            "diagnostics": [],
            "all_covered": True,
        }

    covered: list[str] = []
    for row in proposition_rows:
        meta = row.get("extraction_debug_meta") if isinstance(row.get("extraction_debug_meta"), dict) else {}
        path = str(meta.get("structured_list_path") or "").strip()
        if path:
            covered.append(path)
            continue
        loc = str(row.get("fragment_locator") or "").lower()
        ptxt = str(row.get("proposition_text") or "").lower()
        for d in drafts:
            leaf = next((c.text for c in d.components if c.role == "leaf"), "")
            if leaf and leaf.lower() in ptxt:
                covered.append(d.path_key)
                break
            if d.path_key.lower() in loc.replace(":", "-"):
                covered.append(d.path_key)
                break

    diags = unmatched_terminal_diagnostics(
        expected=drafts,
        covered_path_keys=covered,
        fragment_locator=fragment_locator,
    )
    missing = [d["structured_list_path"] for d in diags]
    return {
        "fragment_locator": fragment_locator,
        "expected_terminals": [d.path_key for d in drafts],
        "covered_terminals": sorted(set(covered)),
        "missing_terminals": missing,
        "diagnostics": diags,
        "all_covered": not diags,
        "diagnostic_code": COVERAGE_DIAGNOSTIC,
    }
