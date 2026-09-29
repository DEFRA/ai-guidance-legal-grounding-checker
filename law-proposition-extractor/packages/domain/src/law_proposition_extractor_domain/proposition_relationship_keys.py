"""Source-scoped and semantic comparison keys for propositions (relationship identity)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .enums import LegalEffectType
from .proposition_labelling import slugify_label
from .territory_normalization import extract_territories_from_text, normalize_territory_name

_PLACEHOLDER_SUBJECT_RE = re.compile(
    r"^(?:these|this|the)\s+(?:regulations?|regulation|rules?|rule|order|instrument|directive)\b",
    re.IGNORECASE,
)

_BOILERPLATE_EFFECTS = frozenset(
    {
        LegalEffectType.CITATION,
        LegalEffectType.COMMENCEMENT,
    }
)

_SEMANTIC_EFFECTS = frozenset(
    {
        LegalEffectType.APPLICATION_SCOPE,
        LegalEffectType.EXTENT,
        LegalEffectType.DEFINITION,
        LegalEffectType.OBLIGATION,
        LegalEffectType.PROHIBITION,
        LegalEffectType.PERMISSION,
        LegalEffectType.POWER,
        LegalEffectType.RECORDKEEPING,
        LegalEffectType.NOTIFICATION,
        LegalEffectType.CERTIFICATION,
        LegalEffectType.INSPECTION,
        LegalEffectType.ENFORCEMENT,
        LegalEffectType.APPEAL,
        LegalEffectType.DEROGATION,
        LegalEffectType.CROSS_REFERENCE,
    }
)

_EXPLICIT_REF_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bregulation\s+(\d+[a-z]?)\b", re.IGNORECASE), "regulation"),
    (re.compile(r"\bschedule\s+(\d+[a-z]?)\b", re.IGNORECASE), "schedule"),
    (re.compile(r"\barticle\s+(\d+[a-z]?)\b", re.IGNORECASE), "article"),
    (re.compile(r"\bparagraph\s+(\d+[a-z]?)\b", re.IGNORECASE), "paragraph"),
    (re.compile(r"\bdirective\s+(\d{4}/\d+/EC)\b", re.IGNORECASE), "directive"),
    (re.compile(r"\bannex\s+([IVXLC]+|\d+[a-z]?)\b", re.IGNORECASE), "annex"),
]


@dataclass(frozen=True)
class RelationshipKeyBundle:
    source_scoped_key: str
    semantic_comparison_key: str
    explicit_cross_reference_targets: list[str]
    semantically_linkable: bool = False


def _key_token(value: str, *, max_len: int = 56) -> str:
    token = slugify_label(str(value or "")).replace("-", "_")
    if not token or token == "item":
        return ""
    return token[:max_len]


def _source_lex_anchor(source_record_id: str) -> str:
    sid = str(source_record_id or "").strip()
    if not sid:
        return "lex-unknown"
    digest = sha256(sid.encode("utf-8")).hexdigest()[:14]
    return f"lex-{digest}"


def is_placeholder_subject(subject: str) -> bool:
    return bool(_PLACEHOLDER_SUBJECT_RE.match(str(subject or "").strip()))


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


def _subject_token(proposition: Any) -> str:
    subject = str(getattr(proposition, "legal_subject", "") or "").strip()
    if subject and not is_placeholder_subject(subject):
        return _key_token(subject)
    affected = list(getattr(proposition, "affected_subjects", None) or [])
    for item in affected:
        tok = _key_token(str(item))
        if tok and not is_placeholder_subject(str(item)):
            return tok
    return ""


def _scope_object_token(proposition: Any, effect: LegalEffectType) -> str:
    text = str(getattr(proposition, "proposition_text", "") or "")
    action = str(getattr(proposition, "action", "") or "")
    affected = [str(x) for x in (getattr(proposition, "affected_subjects", None) or []) if str(x).strip()]

    if effect is LegalEffectType.APPLICATION_SCOPE:
        for src in (text, action):
            m = re.search(
                r"\bapply(?:s)?(?:\s+in relation)?\s+to\s+(.+?)(?:\.|;|$)",
                src,
                re.IGNORECASE,
            )
            if m:
                target = re.sub(r"\s+only$", "", m.group(1).strip(), flags=re.IGNORECASE)
                return _key_token(target)
        if affected:
            return _key_token(affected[0])
    if effect is LegalEffectType.DEFINITION:
        m = re.search(r"['\"]([^'\"]{1,120})['\"]\s+means\b", text, re.IGNORECASE)
        if m:
            return _key_token(m.group(1))
        return _subject_token(proposition)
    if effect is LegalEffectType.EXTENT:
        places = list(getattr(proposition, "extent", None) or [])
        if not places:
            places = extract_territories_from_text(text, context="extent")
        if places:
            return "_".join(_key_token(p) for p in places if _key_token(p))
    if effect in {
        LegalEffectType.OBLIGATION,
        LegalEffectType.PROHIBITION,
        LegalEffectType.PERMISSION,
        LegalEffectType.POWER,
        LegalEffectType.RECORDKEEPING,
        LegalEffectType.NOTIFICATION,
    }:
        sub = _subject_token(proposition)
        act = _key_token(action)
        if sub and act:
            return f"{sub}_{act}"[:80]
    act = _key_token(action)
    if act:
        return act
    if affected:
        return _key_token(affected[0])
    return _key_token(text[:80])


def _territory_token(proposition: Any, effect: LegalEffectType) -> str:
    territorial = list(getattr(proposition, "territorial_application", None) or [])
    if territorial:
        return "_".join(_key_token(normalize_territory_name(t) or t) for t in territorial if t)
    if effect is LegalEffectType.EXTENT:
        extent = list(getattr(proposition, "extent", None) or [])
        if extent:
            return "_".join(_key_token(normalize_territory_name(t) or t) for t in extent if t)
    return ""


def extract_explicit_cross_reference_targets(
    *,
    proposition_text: str,
    legal_effect_type: LegalEffectType,
) -> list[str]:
    """Parse explicit legal cross-reference locators from proposition text."""
    if legal_effect_type is not LegalEffectType.CROSS_REFERENCE:
        lowered = proposition_text.lower()
        if not any(
            phrase in lowered
            for phrase in (
                "pursuant to",
                "in accordance with",
                "referred to in",
                "as provided in",
                "as laid down in",
            )
        ):
            return []

    out: list[str] = []
    for pattern, kind in _EXPLICIT_REF_PATTERNS:
        for m in pattern.finditer(proposition_text):
            target = f"{kind} {m.group(1)}".strip().lower()
            if target not in out:
                out.append(target)
    return out[:12]


def build_relationship_keys(proposition: Any) -> RelationshipKeyBundle:
    effect = _resolve_effect(proposition)
    effect_token = _key_token(effect.value) or "unknown"
    anchor = _source_lex_anchor(str(getattr(proposition, "source_record_id", "") or ""))
    subject = _subject_token(proposition)
    scope_obj = _scope_object_token(proposition, effect)
    territory = _territory_token(proposition, effect)

    source_parts = [anchor, effect_token]
    if scope_obj:
        source_parts.append(scope_obj)
    elif subject:
        source_parts.append(subject)
    if territory:
        source_parts.append(territory)
    source_scoped_key = ":".join(p for p in source_parts if p)

    explicit = extract_explicit_cross_reference_targets(
        proposition_text=str(getattr(proposition, "proposition_text", "") or ""),
        legal_effect_type=effect,
    )

    semantically_linkable = effect in _SEMANTIC_EFFECTS and effect not in _BOILERPLATE_EFFECTS
    if effect in _BOILERPLATE_EFFECTS:
        return RelationshipKeyBundle(
            source_scoped_key=source_scoped_key,
            semantic_comparison_key="",
            explicit_cross_reference_targets=explicit,
            semantically_linkable=False,
        )

    if is_placeholder_subject(str(getattr(proposition, "legal_subject", "") or "")) and not scope_obj:
        return RelationshipKeyBundle(
            source_scoped_key=source_scoped_key,
            semantic_comparison_key="",
            explicit_cross_reference_targets=explicit,
            semantically_linkable=False,
        )

    semantic_parts = [effect_token]
    if scope_obj:
        semantic_parts.append(scope_obj)
    elif subject:
        semantic_parts.append(subject)
    if territory:
        semantic_parts.append(territory)
    semantic_comparison_key = ":".join(p for p in semantic_parts if p)

    return RelationshipKeyBundle(
        source_scoped_key=source_scoped_key,
        semantic_comparison_key=semantic_comparison_key,
        explicit_cross_reference_targets=explicit,
        semantically_linkable=semantically_linkable and bool(semantic_comparison_key),
    )


def apply_relationship_keys(model: Any) -> Any:
    """Populate relationship identity fields on a proposition (in place)."""
    bundle = build_relationship_keys(model)
    model.source_scoped_key = bundle.source_scoped_key
    model.semantic_comparison_key = bundle.semantic_comparison_key or None
    model.explicit_cross_reference_targets = list(bundle.explicit_cross_reference_targets)
    # Deprecated alias: coarse cross_reference_key was jurisdiction:subject:action and caused false links.
    model.cross_reference_key = bundle.source_scoped_key
    if not list(getattr(model, "cross_reference_targets", None) or []):
        model.cross_reference_targets = []
    return model


def should_auto_link_propositions(left: Any, right: Any) -> bool:
    """
    Whether two propositions should be auto-linked via cross_reference_targets.

    Never link across different sources or on generic legacy keys.
    """
    if str(getattr(left, "source_record_id", "")) != str(getattr(right, "source_record_id", "")):
        return False
    left_key = str(getattr(left, "source_scoped_key", "") or getattr(left, "cross_reference_key", ""))
    right_key = str(getattr(right, "source_scoped_key", "") or getattr(right, "cross_reference_key", ""))
    if not left_key or left_key != right_key:
        return False
    return left_key.startswith("lex-")


def build_cross_reference_key(proposition: Any) -> str:
    """Backward-compatible alias for source_scoped_key."""
    return build_relationship_keys(proposition).source_scoped_key
