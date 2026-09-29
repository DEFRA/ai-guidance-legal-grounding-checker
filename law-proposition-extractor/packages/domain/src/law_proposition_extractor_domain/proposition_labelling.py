"""Deterministic proposition label / short_name / slug generation for explorer cards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .enums import LegalEffectType
from .territory_normalization import extract_territories_from_text, split_territory_list

_GENERIC_DISPLAY_LABELS = frozenset(
    {
        "territorial application",
        "territorial extent",
        "extent",
        "citation",
        "commencement",
        "commencement date",
        "application scope",
        "application",
        "definition",
        "short title",
        "proposition",
    }
)

_MAX_LABEL_LEN = 160
_MAX_SHORT_NAME_LEN = 120
_MAX_SLUG_LEN = 96
_MAX_CITATION_TITLE_LEN = 100

_MONTHS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass(frozen=True)
class PropositionLabelBundle:
    label: str
    short_name: str
    slug: str
    display_class: str | None = None


def slugify_label(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def is_generic_display_label(value: str) -> bool:
    norm = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not norm:
        return True
    if norm in _GENERIC_DISPLAY_LABELS:
        return True
    return norm.startswith("territorial ") and norm.endswith("application")


def should_preserve_existing_label(value: str) -> bool:
    """Keep reviewer- or LLM-supplied labels that are already specific."""
    text = str(value or "").strip()
    if not text:
        return False
    return not is_generic_display_label(text)


def _truncate(text: str, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _sentence_title(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return s
    return s[0].upper() + s[1:] if len(s) > 1 else s.upper()


def _resolve_effect(proposition: Any) -> LegalEffectType:
    raw = getattr(proposition, "legal_effect_type", None)
    if isinstance(raw, LegalEffectType):
        return raw
    if raw:
        try:
            return LegalEffectType(str(raw))
        except ValueError:
            pass
    return LegalEffectType.UNKNOWN


def _application_target(
    proposition_text: str,
    action: str,
    affected_subjects: list[str],
    territorial_application: list[str],
) -> str:
    for src in (proposition_text, action):
        m = re.search(
            r"\bapply(?:s)?(?:\s+in relation)?\s+to\s+(.+?)(?:\.|;|$)",
            src,
            re.IGNORECASE,
        )
        if m:
            target = re.sub(r"\s+only$", "", m.group(1).strip(), flags=re.IGNORECASE)
            if target:
                return target
    if affected_subjects:
        return str(affected_subjects[0]).strip()
    if territorial_application:
        return f"territory: {', '.join(territorial_application)}"
    return ""


def _extent_phrase(proposition_text: str, action: str, extent: list[str]) -> str:
    if extent:
        return " and ".join(extent)
    for src in (proposition_text, action):
        places = extract_territories_from_text(src, context="extent")
        if places:
            return " and ".join(places)
        m = re.search(r"\bextends?\s+to\s+(.+?)(?:\.|;|$)", src, re.IGNORECASE)
        if m:
            segment = m.group(1).strip(" .,;")
            listed = split_territory_list(segment)
            if listed:
                return " and ".join(listed)
            return segment
    return ""


def _parse_commencement_date(text: str) -> tuple[str, str | None]:
    m = re.search(
        r"\bcome into force on\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return "", None
    day = int(m.group(1))
    month_name = m.group(2)
    year = int(m.group(3))
    month_num = _MONTHS.get(month_name.lower())
    display = f"{day} {month_name.title()} {year}"
    iso = f"{year}-{month_num:02d}-{day:02d}" if month_num else None
    return display, iso


def _citation_title(proposition_text: str, action: str) -> str:
    for src in (proposition_text, action):
        m = re.search(r"\bmay be cited as\s+(?:the\s+)?(.+?)(?:\.|;|$)", src, re.IGNORECASE)
        if m:
            return _truncate(m.group(1).strip(), _MAX_CITATION_TITLE_LEN)
        m = re.search(r"\bcited as\s+(?:the\s+)?(.+?)(?:\.|;|$)", src, re.IGNORECASE)
        if m:
            return _truncate(m.group(1).strip(), _MAX_CITATION_TITLE_LEN)
    return ""


def _labels_application_scope(proposition: Any) -> PropositionLabelBundle:
    text = str(getattr(proposition, "proposition_text", "") or "")
    action = str(getattr(proposition, "action", "") or "")
    affected = list(getattr(proposition, "affected_subjects", None) or [])
    territorial = list(getattr(proposition, "territorial_application", None) or [])
    target = _application_target(text, action, affected, territorial)
    target = _truncate(target, _MAX_SHORT_NAME_LEN)
    label = _truncate(f"Application to {target}", _MAX_LABEL_LEN)
    short_name = _truncate(_sentence_title(target), _MAX_SHORT_NAME_LEN)
    slug = slugify_label(f"application-{target}")[:_MAX_SLUG_LEN]
    return PropositionLabelBundle(label=label, short_name=short_name, slug=slug, display_class="Territorial application")


def _labels_extent(proposition: Any) -> PropositionLabelBundle:
    text = str(getattr(proposition, "proposition_text", "") or "")
    action = str(getattr(proposition, "action", "") or "")
    extent = list(getattr(proposition, "extent", None) or [])
    places = _extent_phrase(text, action, extent)
    label = _truncate(f"Extent to {places}", _MAX_LABEL_LEN)
    short_name = _truncate(f"{places} extent", _MAX_SHORT_NAME_LEN)
    slug = slugify_label(f"extent-{places}")[:_MAX_SLUG_LEN]
    return PropositionLabelBundle(label=label, short_name=short_name, slug=slug, display_class="Territorial extent")


def _labels_commencement(proposition: Any) -> PropositionLabelBundle:
    text = str(getattr(proposition, "proposition_text", "") or "")
    display_date, iso = _parse_commencement_date(text)
    if not display_date:
        display_date = _truncate(text, 80)
        slug = slugify_label(f"commencement-{display_date}")[:_MAX_SLUG_LEN]
        return PropositionLabelBundle(
            label=_truncate(f"Commencement — {display_date}", _MAX_LABEL_LEN),
            short_name=_truncate(f"Commencement: {display_date}", _MAX_SHORT_NAME_LEN),
            slug=slug,
            display_class="Commencement",
        )
    label = _truncate(f"Commencement on {display_date}", _MAX_LABEL_LEN)
    short_name = _truncate(f"Commencement: {display_date}", _MAX_SHORT_NAME_LEN)
    slug_base = f"commencement-{iso}" if iso else f"commencement-{display_date}"
    slug = slugify_label(slug_base)[:_MAX_SLUG_LEN]
    return PropositionLabelBundle(label=label, short_name=short_name, slug=slug, display_class="Commencement")


def _labels_citation(proposition: Any) -> PropositionLabelBundle:
    text = str(getattr(proposition, "proposition_text", "") or "")
    action = str(getattr(proposition, "action", "") or "")
    title = _citation_title(text, action)
    if not title:
        title = _truncate(text, _MAX_CITATION_TITLE_LEN)
    label = _truncate(f"Citation as {title}", _MAX_LABEL_LEN)
    short_name = "Citation"
    slug = slugify_label(f"citation-{title}")[:_MAX_SLUG_LEN]
    return PropositionLabelBundle(label=label, short_name=short_name, slug=slug, display_class="Citation")


def _labels_definition(proposition: Any) -> PropositionLabelBundle:
    text = str(getattr(proposition, "proposition_text", "") or "")
    subject = str(getattr(proposition, "legal_subject", "") or "").strip()
    m = re.search(r"['\"]([^'\"]{1,80})['\"]\s+means\b", text, re.IGNORECASE)
    term = m.group(1).strip() if m else subject
    term = _truncate(term, 80)
    label = _truncate(f"Definition of {term}", _MAX_LABEL_LEN)
    short_name = _truncate(f"Definition: {term}", _MAX_SHORT_NAME_LEN)
    slug = slugify_label(f"definition-{term}")[:_MAX_SLUG_LEN]
    return PropositionLabelBundle(label=label, short_name=short_name, slug=slug, display_class="Definition")


def _labels_fallback(proposition: Any) -> PropositionLabelBundle:
    ls = str(getattr(proposition, "legal_subject", "") or "").strip()
    act = str(getattr(proposition, "action", "") or "").strip()
    if ls or act:
        short_name = _truncate(" ".join(p for p in (ls, act) if p), _MAX_SHORT_NAME_LEN)
    else:
        short_name = _truncate(
            str(getattr(proposition, "proposition_text", "") or "").strip(),
            _MAX_SHORT_NAME_LEN,
        ) or "Proposition"
    label = _truncate(short_name, _MAX_LABEL_LEN)
    slug = slugify_label(label)[:_MAX_SLUG_LEN]
    return PropositionLabelBundle(label=label, short_name=short_name, slug=slug)


def derive_proposition_labels(proposition: Any) -> PropositionLabelBundle:
    """Build specific label, short_name, and slug from classified proposition content."""
    effect = _resolve_effect(proposition)
    if effect is LegalEffectType.APPLICATION_SCOPE:
        return _labels_application_scope(proposition)
    if effect is LegalEffectType.EXTENT:
        return _labels_extent(proposition)
    if effect is LegalEffectType.COMMENCEMENT:
        return _labels_commencement(proposition)
    if effect is LegalEffectType.CITATION:
        return _labels_citation(proposition)
    if effect is LegalEffectType.DEFINITION:
        return _labels_definition(proposition)
    return _labels_fallback(proposition)


def apply_proposition_label_enrichment(model: Any) -> Any:
    """Replace generic extraction labels with specific card titles (in place)."""
    existing_label = str(getattr(model, "label", "") or "").strip()
    existing_short = str(getattr(model, "short_name", "") or "").strip()
    existing_slug = str(getattr(model, "slug", "") or "").strip()

    bundle = derive_proposition_labels(model)
    display_class = bundle.display_class or (
        existing_label if is_generic_display_label(existing_label) else None
    )

    if not should_preserve_existing_label(existing_label):
        model.label = bundle.label
    if not should_preserve_existing_label(existing_short):
        model.short_name = bundle.short_name
    if not existing_slug or not should_preserve_existing_label(existing_label):
        model.slug = bundle.slug

    if display_class:
        dbg = getattr(model, "extraction_debug_meta", None)
        if not isinstance(dbg, dict):
            dbg = {}
        else:
            dbg = dict(dbg)
        dbg.setdefault("display_label", display_class)
        model.extraction_debug_meta = dbg

    return model
