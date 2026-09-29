"""Structured legal-action fidelity (evaluation-only; no production schema).

Action fidelity compares legal-action invariants (predicate, polarity, legal
effect, material objects)—not brittle modal surface strings alone.

Legacy gold contracts that only set ``required_action`` keep the historical
substring / token-overlap matcher. Structured evaluation runs only when an
``action_expectation`` is present on the gold row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .results import DimensionResult

Polarity = Literal["positive", "negative"]
Voice = Literal["active", "passive", "either"]

# Deterministic inflection tables for verbs used in the PF corpus.
_PREDICATE_FORMS: dict[str, frozenset[str]] = {
    "mix": frozenset({"mix", "mixes", "mixed", "mixing"}),
    "spread": frozenset({"spread", "spreads", "spreading"}),
    "measure": frozenset({"measure", "measures", "measured", "measuring"}),
    "record": frozenset({"record", "records", "recorded", "recording"}),
    "retain": frozenset({"retain", "retains", "retained", "retaining"}),
    "inspect": frozenset({"inspect", "inspects", "inspected", "inspecting"}),
    "identify": frozenset({"identify", "identifies", "identified", "identifying"}),
    "monitor": frozenset({"monitor", "monitors", "monitored", "monitoring"}),
    "store": frozenset({"store", "stores", "stored", "storing"}),
    "submit": frozenset({"submit", "submits", "submitted", "submitting"}),
    "enter": frozenset({"enter", "enters", "entered", "entering"}),
    "ensure": frozenset({"ensure", "ensures", "ensured", "ensuring"}),
    "apply": frozenset({"apply", "applies", "applied", "applying"}),
    "place": frozenset({"place", "places", "placed", "placing"}),
    "make": frozenset({"make", "makes", "made", "making"}),
    "keep": frozenset({"keep", "keeps", "kept", "keeping"}),
}

# Modals / deontic patterns that are NOT interchangeable with hard prohibition.
_WEAK_OR_DISTINCT_NEGATIVE = (
    r"\bshould\s+not\b",
    r"\bought\s+not\b",
    r"\bneed\s+not\b",
    r"\bneeds\s+not\b",
    r"\bis\s+not\s+required\s+to\b",
    r"\bare\s+not\s+required\s+to\b",
    r"\bdoes\s+not\s+have\s+to\b",
    r"\bdo\s+not\s+have\s+to\b",
    r"\bneed\s+not\s+be\b",
)
_PERMISSION_POSITIVE = (r"\bmay\b", r"\bmight\b")
_HARD_NEGATIVE = (
    r"\bmust\s+not\b",
    r"\bshall\s+not\b",
    r"\bis\s+prohibited\s+from\b",
    r"\bare\s+prohibited\s+from\b",
    r"\bprohibited\s+from\b",
)
_HARD_POSITIVE_OBLIGATION = (
    r"\bmust\b(?!\s+not\b)",
    r"\bshall\b(?!\s+not\b)",
)


@dataclass(frozen=True)
class ActionExpectation:
    """Optional structured action invariant for gold contracts."""

    predicates: tuple[str, ...]
    polarity: Polarity
    legal_effect: str
    voice: Voice = "either"
    required_object_markers: tuple[str, ...] = ()
    required_actor_markers: tuple[str, ...] = ()
    accepted_surface_forms: tuple[str, ...] = ()
    forbidden_surface_forms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicates": list(self.predicates),
            "polarity": self.polarity,
            "legal_effect": self.legal_effect,
            "voice": self.voice,
            "required_object_markers": list(self.required_object_markers),
            "required_actor_markers": list(self.required_actor_markers),
            "accepted_surface_forms": list(self.accepted_surface_forms),
            "forbidden_surface_forms": list(self.forbidden_surface_forms),
        }


def load_action_expectation(raw: Any) -> ActionExpectation | None:
    if not isinstance(raw, dict) or not raw:
        return None
    preds = raw.get("predicates") or raw.get("predicate")
    if isinstance(preds, str):
        pred_tuple = (preds.strip().lower(),)
    elif isinstance(preds, list):
        pred_tuple = tuple(str(p).strip().lower() for p in preds if str(p).strip())
    else:
        return None
    if not pred_tuple:
        return None
    polarity = str(raw.get("polarity") or "").strip().lower()
    if polarity not in {"positive", "negative"}:
        raise ValueError(f"action_expectation.polarity must be positive|negative; got {polarity!r}")
    legal_effect = str(raw.get("legal_effect") or "").strip().lower()
    if not legal_effect:
        raise ValueError("action_expectation.legal_effect is required")
    voice = str(raw.get("voice") or "either").strip().lower()
    if voice not in {"active", "passive", "either"}:
        raise ValueError(f"action_expectation.voice must be active|passive|either; got {voice!r}")

    def _markers(key: str) -> tuple[str, ...]:
        val = raw.get(key) or ()
        if isinstance(val, str):
            return (val,) if val.strip() else ()
        return tuple(str(x) for x in val if str(x).strip())

    return ActionExpectation(
        predicates=pred_tuple,
        polarity=polarity,  # type: ignore[arg-type]
        legal_effect=legal_effect,
        voice=voice,  # type: ignore[arg-type]
        required_object_markers=_markers("required_object_markers"),
        required_actor_markers=_markers("required_actor_markers"),
        accepted_surface_forms=_markers("accepted_surface_forms"),
        forbidden_surface_forms=_markers("forbidden_surface_forms"),
    )


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def predicate_forms(predicate: str) -> frozenset[str]:
    key = predicate.strip().lower()
    if key in _PREDICATE_FORMS:
        return _PREDICATE_FORMS[key]
    # Conservative fallback: bare stem + common English endings.
    return frozenset({key, key + "s", key + "ed", key + "ing", key.rstrip("e") + "ing"})


def _word_present(hay: str, word: str) -> bool:
    return bool(re.search(rf"\b{re.escape(word)}\b", hay, flags=re.IGNORECASE))


def _predicate_present(hay: str, predicate: str) -> bool:
    return any(_word_present(hay, form) for form in predicate_forms(predicate))


def _noun_forms(token: str) -> frozenset[str]:
    """Conservative English noun inflection for object/actor markers."""
    t = token.lower()
    forms = {t, t + "s", t + "es"}
    if len(t) > 1 and t.endswith("y") and t[-2] not in "aeiou":
        forms.add(t[:-1] + "ies")
    if t.endswith("ies") and len(t) > 3:
        forms.add(t[:-3] + "y")
    if t.endswith("es") and len(t) > 2:
        forms.add(t[:-2])
    if t.endswith("s") and not t.endswith("ss") and len(t) > 1:
        forms.add(t[:-1])
    return frozenset(f for f in forms if f)


def _marker_present(hay: str, marker: str) -> bool:
    """Match a material marker with light inflection on content tokens."""
    norm_hay = _norm(hay)
    norm_marker = _norm(marker)
    if norm_marker in norm_hay:
        return True
    # Phrase with pluralised final token, e.g. "other catch" → "other catches".
    parts = norm_marker.split()
    if len(parts) >= 2:
        head, last = " ".join(parts[:-1]), parts[-1]
        for form in _noun_forms(last) | predicate_forms(last):
            if f"{head} {form}" in norm_hay:
                return True
    tokens = [t for t in parts if t]
    if not tokens:
        return True
    for token in tokens:
        forms = _noun_forms(token) | predicate_forms(token)
        if not any(_word_present(norm_hay, f) for f in forms if f):
            return False
    return True


def detect_voice(hay: str, predicate: str) -> Voice | None:
    forms = predicate_forms(predicate)
    past = next((f for f in forms if f.endswith("ed") or f == "spread" or f == "kept"), None)
    gerund = next((f for f in forms if f.endswith("ing")), None)
    base = predicate.lower()
    # Passive: be/been/being + past participle, or "prohibited from being <gerund/past>"
    if past and re.search(
        rf"\b(?:be|been|being|is|are|was|were)\s+{re.escape(past)}\b",
        hay,
        flags=re.IGNORECASE,
    ):
        return "passive"
    if gerund and re.search(
        rf"\bprohibited\s+from\s+(?:being\s+)?{re.escape(gerund)}\b",
        hay,
        flags=re.IGNORECASE,
    ):
        return "passive"
    if past and re.search(
        rf"\bprohibited\s+from\s+(?:being\s+)?{re.escape(past)}\b",
        hay,
        flags=re.IGNORECASE,
    ):
        return "passive"
    # Active: modal/aux + base/3sg/gerund without "be <past>"
    if any(
        re.search(rf"\b(?:must|shall|should|may|need)\s+(?:not\s+)?{re.escape(f)}\b", hay, flags=re.IGNORECASE)
        for f in forms
        if f == base or f == base + "s" or f.endswith("ing")
    ):
        return "active"
    if _predicate_present(hay, predicate):
        # Ambiguous presence — treat as either-compatible.
        return None
    return None


def detect_polarity(hay: str, *, predicate: str) -> Polarity | None:
    """Detect deontic polarity for the predicate; do not trust a bare 'not' token."""
    forms = predicate_forms(predicate)
    # Weak / distinct-from-prohibition patterns first.
    for pat in _WEAK_OR_DISTINCT_NEGATIVE:
        if re.search(pat, hay, flags=re.IGNORECASE):
            # Only if the pattern scopes the predicate nearby.
            window = _window_around_predicate(hay, forms)
            if window and re.search(pat, window, flags=re.IGNORECASE):
                return "negative"  # flagged separately as weak modality
    for pat in _HARD_NEGATIVE:
        window = _window_around_predicate(hay, forms)
        target = window or hay
        if re.search(pat, target, flags=re.IGNORECASE):
            return "negative"
    # "is/are not required to <predicate>" already covered; positive obligation/permission:
    for pat in _HARD_POSITIVE_OBLIGATION:
        window = _window_around_predicate(hay, forms)
        target = window or hay
        if re.search(pat, target, flags=re.IGNORECASE):
            return "positive"
    for pat in _PERMISSION_POSITIVE:
        window = _window_around_predicate(hay, forms)
        target = window or hay
        if re.search(pat, target, flags=re.IGNORECASE) and not re.search(
            r"\bmay\s+not\b", target, flags=re.IGNORECASE
        ):
            return "positive"
    if re.search(r"\bmay\s+not\b", hay, flags=re.IGNORECASE):
        window = _window_around_predicate(hay, forms)
        if window and re.search(r"\bmay\s+not\b", window, flags=re.IGNORECASE):
            return "negative"
    return None


def _window_around_predicate(hay: str, forms: frozenset[str]) -> str | None:
    for form in sorted(forms, key=len, reverse=True):
        m = re.search(rf"\b{re.escape(form)}\b", hay, flags=re.IGNORECASE)
        if m:
            start = max(0, m.start() - 80)
            end = min(len(hay), m.end() + 40)
            return hay[start:end]
    return None


def _has_weak_modality(hay: str, predicate: str) -> bool:
    forms = predicate_forms(predicate)
    window = _window_around_predicate(hay, forms) or hay
    return any(re.search(pat, window, flags=re.IGNORECASE) for pat in _WEAK_OR_DISTINCT_NEGATIVE)


def _has_may_not(hay: str, predicate: str) -> bool:
    forms = predicate_forms(predicate)
    window = _window_around_predicate(hay, forms) or hay
    return bool(re.search(r"\bmay\s+not\b", window, flags=re.IGNORECASE))


def _operative_action_haystack(
    *,
    action: str,
    proposition_text: str,
    evidence: str,
) -> str:
    """Haystack for action meaning — excludes headings/labels by construction."""
    return _norm(f"{action} {proposition_text} {evidence}")


def _predicate_grounded_in_operative(
    *,
    predicate: str,
    evidence: str,
    operative_text: str,
    proposition_text: str,
    action: str,
    heading_text: str | None,
    label_text: str,
) -> bool:
    """Predicate must appear in operative source or proposition/action/evidence — not heading/label alone."""
    grounded = " ".join(
        [
            _norm(evidence),
            _norm(operative_text),
            _norm(proposition_text),
            _norm(action),
        ]
    )
    if _predicate_present(grounded, predicate):
        # Reject if the *only* occurrence is inside heading/label and not in operative/evidence/text/action.
        core = " ".join([_norm(evidence), _norm(operative_text), _norm(proposition_text), _norm(action)])
        if _predicate_present(core, predicate):
            return True
    # Explicit fail when only heading/label carries the verb.
    label_heading = " ".join([_norm(label_text), _norm(heading_text or "")])
    if _predicate_present(label_heading, predicate) and not _predicate_present(
        " ".join([_norm(evidence), _norm(operative_text), _norm(proposition_text), _norm(action)]),
        predicate,
    ):
        return False
    return _predicate_present(grounded, predicate)


def evaluate_structured_action_fidelity(
    *,
    expectation: ActionExpectation,
    prop: dict[str, Any],
    operative_text: str,
    heading_text: str | None,
    evidence: str,
    label_text: str = "",
) -> DimensionResult:
    action = str(prop.get("action") or "")
    text = str(prop.get("proposition_text") or "")
    effect = str(prop.get("legal_effect_type") or "").strip().lower()
    subject = str(prop.get("legal_subject") or "")
    hay = _operative_action_haystack(action=action, proposition_text=text, evidence=evidence)

    detected_predicates = [p for p in expectation.predicates if _predicate_present(hay, p)]
    primary = expectation.predicates[0]
    detected_polarity = detect_polarity(hay, predicate=primary)
    detected_voice = detect_voice(hay, primary)

    matched_objects = [m for m in expectation.required_object_markers if _marker_present(hay, m)]
    matched_actors = [
        m
        for m in expectation.required_actor_markers
        if _marker_present(hay, m) or _marker_present(subject, m)
    ]

    surface_basis: list[str] = []
    for form in expectation.accepted_surface_forms:
        if _norm(form) in hay:
            surface_basis.append(form)

    audit = {
        "expected_predicates": list(expectation.predicates),
        "detected_predicates": detected_predicates,
        "expected_polarity": expectation.polarity,
        "detected_polarity": detected_polarity,
        "expected_legal_effect": expectation.legal_effect,
        "actual_legal_effect": effect,
        "expected_voice": expectation.voice,
        "detected_voice": detected_voice,
        "required_object_markers": list(expectation.required_object_markers),
        "matched_object_markers": matched_objects,
        "required_actor_markers": list(expectation.required_actor_markers),
        "matched_actor_markers": matched_actors,
        "accepted_surface_basis": surface_basis,
        "evaluation_mode": "structured_action_expectation",
    }

    def _fail(detail: str) -> DimensionResult:
        return DimensionResult(
            dimension="action_fidelity",
            status="fail",
            detail=detail,
            expected=_format_expected(expectation),
            actual=action or text[:160],
            severity_policy="hard_failure",
            likely_pipeline_stage="extraction",
            audit=audit,
        )

    # Forbidden surfaces always fail.
    for bad in expectation.forbidden_surface_forms:
        if _norm(bad) in hay:
            return _fail(
                f"forbidden action surface form present: {bad!r} "
                f"(legal action fidelity requires rejecting this wording)"
            )

    # Legal-effect gate before modal indifference.
    if effect != expectation.legal_effect:
        return _fail(
            f"legal-action effect mismatch for action fidelity: expected "
            f"{expectation.legal_effect}, actual {effect or '(missing)'}"
        )

    # Predicate presence in operative action haystack.
    if len(detected_predicates) != len(expectation.predicates):
        missing = [p for p in expectation.predicates if p not in detected_predicates]
        return _fail(
            f"operative predicate missing or changed: expected {expectation.predicates}, "
            f"missing {missing}"
        )

    # Evidence / operative grounding — not heading or label alone.
    if not _predicate_grounded_in_operative(
        predicate=primary,
        evidence=evidence,
        operative_text=operative_text,
        proposition_text=text,
        action=action,
        heading_text=heading_text,
        label_text=label_text,
    ):
        return _fail(
            "action predicate is not grounded in operative source text or proposition "
            "evidence (heading/label-only action evidence is rejected)"
        )

    # Weak / distinct modality: never treat as hard prohibition equivalent.
    if expectation.polarity == "negative" and expectation.legal_effect == "prohibition":
        if _has_weak_modality(hay, primary):
            return _fail(
                "modal/polarity mismatch: weak or non-prohibitive negation "
                "(e.g. should not / need not / is not required) is not equivalent "
                "to a hard prohibition"
            )
        if _has_may_not(hay, primary) and "may not" not in {
            _norm(x) for x in expectation.accepted_surface_forms
        }:
            return _fail(
                "modal mismatch: 'may not' is not treated as equivalent to a hard "
                "prohibition unless the gold contract explicitly accepts it"
            )

    # Polarity must match after hard-modal confirmation.
    if detected_polarity != expectation.polarity:
        # Accepted surface forms may still satisfy when polarity detector is unsure
        # but an accepted form is present and legal effect already matched.
        if not surface_basis:
            return _fail(
                f"action polarity mismatch: expected {expectation.polarity}, "
                f"detected {detected_polarity or '(none)'}"
            )

    # Positive obligation must not be a prohibition surface, and vice versa.
    if expectation.polarity == "positive" and detected_polarity == "negative":
        return _fail("action polarity reversed relative to gold expectation")

    # Object markers (action-dimension material objects — separate from object_fidelity).
    if expectation.required_object_markers:
        missing_obj = [
            m for m in expectation.required_object_markers if m not in matched_objects
        ]
        if missing_obj:
            return _fail(
                f"material action object marker(s) missing: {missing_obj} "
                f"(action fidelity keeps actor/object checks distinct; objects must remain)"
            )

    if expectation.required_actor_markers:
        missing_act = [
            m for m in expectation.required_actor_markers if m not in matched_actors
        ]
        if missing_act:
            return _fail(
                f"material action actor marker(s) missing: {missing_act}"
            )

    # Voice: active/passive interchangeable only when expectation allows and roles preserved.
    if expectation.voice != "either" and detected_voice and detected_voice != expectation.voice:
        return _fail(
            f"action voice mismatch: expected {expectation.voice}, detected {detected_voice}"
        )

    # Build reviewer-facing pass explanation.
    voice_note = ""
    if detected_voice == "passive" or (
        detected_voice is None and re.search(r"\bbe\s+\w+ed\b|\bbeing\s+\w+", hay)
    ):
        voice_note = (
            " The live wording is a passive expression of the same prohibited action."
            if expectation.legal_effect == "prohibition"
            else " Active/passive voice difference is treated as non-material."
        )
    elif detected_voice == "active":
        voice_note = " The live wording is an active expression of the expected legal action."

    detail = (
        f"The gold contract expects the canonical action "
        f"`{'`/`'.join(expectation.predicates)}`, {expectation.polarity} polarity, "
        f"a {expectation.legal_effect} legal effect"
        + (
            f", and the relevant "
            f"{'/'.join(expectation.required_object_markers)} object"
            if expectation.required_object_markers
            else ""
        )
        + f". The live proposition states {action!r}"
        + (f" / {text[:120]!r}" if text and text != action else "")
        + "."
        + voice_note
        + " Modal surface form (shall/must) is disregarded only after confirming "
        "legal effect and polarity. Action fidelity therefore passes."
    )
    audit["accepted_surface_basis"] = surface_basis or [
        f"normalized:{primary}/{expectation.polarity}/{expectation.legal_effect}"
        + (f"/{detected_voice or expectation.voice}" )
    ]
    return DimensionResult(
        dimension="action_fidelity",
        status="pass",
        detail=detail,
        expected=_format_expected(expectation),
        actual=action or text[:160],
        severity_policy="hard_failure",
        likely_pipeline_stage="extraction",
        audit=audit,
    )


def _format_expected(expectation: ActionExpectation) -> str:
    return (
        f"predicates={list(expectation.predicates)}; polarity={expectation.polarity}; "
        f"legal_effect={expectation.legal_effect}; voice={expectation.voice}; "
        f"objects={list(expectation.required_object_markers)}"
    )


def evaluate_legacy_action_fidelity(
    *,
    required_action: str,
    prop: dict[str, Any],
) -> DimensionResult:
    """Historical substring / token-overlap matcher for simple ``required_action`` gold."""
    action = str(prop.get("action") or "")
    text = str(prop.get("proposition_text") or "")
    hay = f"{action} {text}"
    if _norm(required_action) in _norm(hay):
        return DimensionResult(
            dimension="action_fidelity",
            status="pass",
            detail="legacy required_action substring match",
            expected=required_action,
            actual=action or text[:160],
            audit={
                "evaluation_mode": "legacy_required_action",
                "required_action": required_action,
                "equivalence_basis": "normalized_substring",
            },
        )
    tokens = [t for t in _norm(required_action).split() if len(t) > 3]
    hit = sum(1 for t in tokens if t in _norm(hay))
    if tokens and hit / len(tokens) >= 0.6:
        return DimensionResult(
            dimension="action_fidelity",
            status="warning",
            detail="action paraphrased but token-overlap supports fidelity",
            expected=required_action,
            actual=action or text[:160],
            severity_policy="warning",
            likely_pipeline_stage="extraction",
            audit={
                "evaluation_mode": "legacy_required_action",
                "required_action": required_action,
                "equivalence_basis": "token_overlap",
            },
        )
    return DimensionResult(
        dimension="action_fidelity",
        status="fail",
        detail="required action not preserved",
        expected=required_action,
        actual=action or text[:160],
        severity_policy="hard_failure",
        likely_pipeline_stage="extraction",
        audit={
            "evaluation_mode": "legacy_required_action",
            "required_action": required_action,
            "equivalence_basis": None,
        },
    )
