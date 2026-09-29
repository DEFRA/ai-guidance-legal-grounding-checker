"""Compare prompt-lab extraction runs against fixture review targets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain.enums import LegalEffectType
from law_proposition_extractor_domain.proposition_notes import parse_extraction_meta

from .beatrice_export_view import PROPOSITION_MATCHER_EXCLUDED_BOILERPLATE
from .extract import evidence_locates_verbatim_after_normalisation
from .extraction_workbench import PROPOSITIONS_NORMALISED_JSON, PROPOSITIONS_RAW_JSON, load_prompt_lab_fixture

PROMPT_EVAL_JSON = "prompt_eval.json"
PROMPT_EVAL_MD = "PROMPT_EVAL.md"

EvaluationMode = Literal["targeted", "exhaustive", "minimum", "table_rows"]
MatchKind = Literal[
    "none",
    "exact",
    "contained_in_actual",
    "classification_mismatch",
    "bundled_match",
]

_LEGAL_EFFECT_EQUIVALENCES: dict[frozenset[str], frozenset[str]] = {
    frozenset({"permission", "application_scope"}): frozenset({"permission", "application_scope", "power"}),
    frozenset({"definition", "derogation"}): frozenset({"definition", "derogation"}),
    frozenset({"derogation", "application_scope"}): frozenset({"derogation", "application_scope"}),
    frozenset({"obligation", "prohibition"}): frozenset({"obligation", "prohibition"}),
    frozenset({"prohibition", "derogation"}): frozenset({"prohibition", "derogation", "obligation"}),
}

_EXCLUSIVE_MATCH_KINDS = frozenset({"exact"})
_DEFAULT_EVALUATION_BY_MODE: dict[str, dict[str, Any]] = {
    "targeted": {
        "strict_proposition_count": False,
        "allow_extra_actual": True,
    },
    "minimum": {
        "strict_proposition_count": False,
        "allow_extra_actual": True,
    },
    "exhaustive": {
        "strict_proposition_count": True,
        "allow_extra_actual": False,
    },
    "table_rows": {
        "strict_proposition_count": False,
        "allow_extra_actual": True,
    },
}

_BOILERPLATE_EFFECTS = frozenset(
    {
        LegalEffectType.CITATION.value,
        LegalEffectType.COMMENCEMENT.value,
        LegalEffectType.EXTENT.value,
        LegalEffectType.APPLICATION_SCOPE.value,
    }
)
_MODAL_RE = re.compile(
    r"\b(must not|must|shall not|shall|may not|may|is prohibited|are prohibited|prohibited)\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass
class ExpectedPropositionMatch:
    expected_index: int
    expected: dict[str, Any]
    matched_actual_index: int | None = None
    matched_actual_id: str | None = None
    legal_effect_ok: bool = False
    tier_ok: bool = False
    evidence_ok: bool = False
    subject_ok: bool = False
    action_ok: bool = False
    conditions_ok: bool = True
    matched: bool = False
    match_score: float = 0.0
    match_kind: MatchKind = "none"
    contained_evidence_ok: bool = False
    classification_mismatch: bool = False
    suggested_failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_index": self.expected_index,
            "expected": self.expected,
            "matched_actual_index": self.matched_actual_index,
            "matched_actual_id": self.matched_actual_id,
            "legal_effect_ok": self.legal_effect_ok,
            "tier_ok": self.tier_ok,
            "evidence_ok": self.evidence_ok,
            "subject_ok": self.subject_ok,
            "action_ok": self.action_ok,
            "conditions_ok": self.conditions_ok,
            "matched": self.matched,
            "match_score": round(self.match_score, 3),
            "match_kind": self.match_kind,
            "contained_evidence_ok": self.contained_evidence_ok,
            "classification_mismatch": self.classification_mismatch,
            "suggested_failure_reason": self.suggested_failure_reason,
        }


@dataclass
class ActualPropositionsLoad:
    rows: list[dict[str, Any]]
    source_file: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class PromptEvalResult:
    case_id: str
    label: str
    fixture_path: str
    run_dir: str
    passed: bool
    actual_count: int
    expected_count: int
    matched_expected_count: int
    eval_status: str = "pass"
    checks: dict[str, Any] = field(default_factory=dict)
    expected_matches: list[ExpectedPropositionMatch] = field(default_factory=list)
    extra_actual: list[dict[str, Any]] = field(default_factory=list)
    missing_effects: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "label": self.label,
            "fixture_path": self.fixture_path,
            "run_dir": self.run_dir,
            "passed": self.passed,
            "eval_status": self.eval_status,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "actual_count": self.actual_count,
            "expected_count": self.expected_count,
            "matched_expected_count": self.matched_expected_count,
            "warnings": self.warnings,
            "summary": self.summary,
            "checks": self.checks,
            "expected_matches": [m.to_dict() for m in self.expected_matches],
            "extra_actual": self.extra_actual,
            "missing_effects": self.missing_effects,
        }


def _evaluation_config(fixture: dict[str, Any]) -> dict[str, Any]:
    nested = fixture.get("evaluation")
    cfg: dict[str, Any] = dict(nested) if isinstance(nested, dict) else {}
    if "strict_proposition_count" in fixture:
        cfg.setdefault("strict_proposition_count", fixture["strict_proposition_count"])
    if "expected_checkable_count" in fixture:
        cfg.setdefault("expected_checkable_count", fixture["expected_checkable_count"])
    mode_raw = str(cfg.get("mode") or "exhaustive").strip().lower()
    if mode_raw not in _DEFAULT_EVALUATION_BY_MODE:
        mode_raw = "exhaustive"
    cfg["mode"] = mode_raw
    for key, value in _DEFAULT_EVALUATION_BY_MODE[mode_raw].items():
        cfg.setdefault(key, value)
    if "allow_extra_actual" in cfg:
        cfg["allow_extra_actual"] = bool(cfg["allow_extra_actual"])
    if cfg.get("max_extra_actual") is not None:
        cfg["max_extra_actual"] = int(cfg["max_extra_actual"])
    return cfg


def _normalize_text(value: str) -> str:
    text = str(value or "").lower().strip()
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
    text = re.sub(r"\b(\d+)(st|nd|rd|th)\b", r"\1", text)
    return _NON_ALNUM.sub(" ", text).strip()


def _token_set(value: str) -> set[str]:
    return {t for t in _normalize_text(value).split() if len(t) > 1}


def _fuzzy_contains(needle: str, haystack: str) -> bool:
    n = _normalize_text(needle)
    h = _normalize_text(haystack)
    if not n:
        return True
    if not h:
        return False
    if n in h:
        return True
    n_tokens = _token_set(n)
    if not n_tokens:
        return True
    h_tokens = _token_set(h)
    overlap = len(n_tokens & h_tokens) / len(n_tokens)
    return overlap >= 0.6


def _field_str(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _evidence_text(prop: dict[str, Any]) -> str:
    meta = parse_extraction_meta(prop.get("notes"))
    if meta and isinstance(meta.get("evidence_quote"), str):
        quote = str(meta["evidence_quote"]).strip()
        if quote:
            return quote
    debug = prop.get("extraction_debug_meta")
    if isinstance(debug, dict):
        quote = str(debug.get("evidence_quote") or "").strip()
        if quote:
            return quote
    return _field_str(prop, "proposition_text")


def _actual_text_blob(actual: dict[str, Any]) -> str:
    conditions, exceptions = _conditions_and_exceptions(actual)
    parts = [
        _evidence_text(actual),
        _field_str(actual, "proposition_text"),
        _field_str(actual, "legal_subject"),
        _field_str(actual, "action"),
        *conditions,
        *exceptions,
        *[str(s) for s in (actual.get("affected_subjects") or []) if str(s).strip()],
        str(actual.get("notes") or ""),
    ]
    return " ".join(p for p in parts if p)


def _legal_effects_equivalent(
    expected_effect: str,
    actual_effect: str,
    *,
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> bool:
    if not expected_effect or expected_effect == actual_effect:
        return True
    for pair, allowed in _LEGAL_EFFECT_EQUIVALENCES.items():
        if expected_effect in pair and actual_effect in allowed:
            if pair == frozenset({"definition", "derogation"}):
                blob = _actual_text_blob(actual).lower()
                if _field_str(expected, "action") == "means" or " means " in blob:
                    return True
                continue
            return True
    return False


def _contained_in_actual_fields(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """True when expected markers appear anywhere in the actual proposition envelope."""
    hay = _actual_text_blob(actual)
    needles: list[str] = []
    for key in ("evidence_quote", "legal_subject", "action", "proposition_text"):
        value = _field_str(expected, key)
        if value:
            needles.append(value)
    for item in expected.get("conditions") or []:
        if str(item).strip():
            needles.append(str(item))
    for item in expected.get("exceptions") or []:
        if str(item).strip():
            needles.append(str(item))
    if not needles:
        return False
    evidence_needle = _field_str(expected, "evidence_quote")
    if evidence_needle and not _fuzzy_contains(evidence_needle, hay):
        return False
    other_needles = [n for n in needles if n != evidence_needle and len(_normalize_text(n)) > 8]
    if not other_needles:
        return bool(evidence_needle)
    return any(_fuzzy_contains(needle, hay) for needle in other_needles)


def _conditions_and_exceptions(prop: dict[str, Any]) -> tuple[list[str], list[str]]:
    conditions = prop.get("conditions") or []
    if not isinstance(conditions, list):
        conditions = []
    conditions = [str(c).strip() for c in conditions if str(c).strip()]
    exceptions: list[str] = []
    notes = str(prop.get("notes") or "")
    for line in notes.splitlines():
        line = line.strip()
        if line.lower().startswith("exception:"):
            exceptions.append(line.split(":", 1)[-1].strip())
    return conditions, exceptions


def _modal_verb_count(text: str) -> int:
    return len(_MODAL_RE.findall(text))


def _is_checkable_row(prop: dict[str, Any]) -> bool:
    effect = _field_str(prop, "legal_effect_type")
    if effect in {e.value for e in PROPOSITION_MATCHER_EXCLUDED_BOILERPLATE}:
        return False
    if prop.get("is_compliance_relevant") is not True:
        return False
    try:
        return LegalEffectType(effect) in {
            LegalEffectType.OBLIGATION,
            LegalEffectType.PROHIBITION,
            LegalEffectType.PERMISSION,
            LegalEffectType.RECORDKEEPING,
            LegalEffectType.NOTIFICATION,
            LegalEffectType.CERTIFICATION,
            LegalEffectType.INSPECTION,
            LegalEffectType.ENFORCEMENT,
            LegalEffectType.APPEAL,
            LegalEffectType.DEROGATION,
        }
    except ValueError:
        return False


def _read_proposition_file(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], f"invalid JSON in {path.name}: {exc}"
    if not isinstance(payload, list):
        return [], f"{path.name} must be a JSON array"
    return [x for x in payload if isinstance(x, dict)], None


def load_actual_propositions_with_meta(
    run_dir: str | Path,
    *,
    prefer_normalised: bool = True,
) -> ActualPropositionsLoad:
    """Load proposition rows from a workbench run; never raises."""
    root = Path(run_dir).expanduser().resolve()
    warnings: list[str] = []
    norm_path = root / PROPOSITIONS_NORMALISED_JSON
    raw_path = root / PROPOSITIONS_RAW_JSON

    if prefer_normalised and norm_path.is_file():
        rows, err = _read_proposition_file(norm_path)
        if err:
            warnings.append(err)
        elif rows:
            return ActualPropositionsLoad(rows=rows, source_file=norm_path.name, warnings=warnings)
        elif prefer_normalised:
            warnings.append(f"{PROPOSITIONS_NORMALISED_JSON} is empty")

    if raw_path.is_file():
        rows, err = _read_proposition_file(raw_path)
        if err:
            warnings.append(err)
            return ActualPropositionsLoad(rows=[], source_file=None, warnings=warnings, error=err)
        if rows:
            if prefer_normalised and norm_path.is_file():
                warnings.append(f"fell back to {PROPOSITIONS_RAW_JSON} after normalised load issue")
            return ActualPropositionsLoad(rows=rows, source_file=raw_path.name, warnings=warnings)
        warnings.append(f"{PROPOSITIONS_RAW_JSON} is empty")

    if not norm_path.is_file() and not raw_path.is_file():
        error = (
            f"no propositions file in {root} (expected {PROPOSITIONS_NORMALISED_JSON} or "
            f"{PROPOSITIONS_RAW_JSON})"
        )
        return ActualPropositionsLoad(rows=[], warnings=warnings, error=error)

    if not warnings:
        warnings.append("proposition files present but contained no usable rows")
    return ActualPropositionsLoad(
        rows=[],
        source_file=norm_path.name if norm_path.is_file() else raw_path.name,
        warnings=warnings,
    )


def load_actual_propositions(
    run_dir: str | Path,
    *,
    prefer_normalised: bool = True,
) -> list[dict[str, Any]]:
    loaded = load_actual_propositions_with_meta(run_dir, prefer_normalised=prefer_normalised)
    if loaded.error and not loaded.rows:
        raise FileNotFoundError(loaded.error)
    return loaded.rows


def _score_expected_against_actual(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    source_fragment_text: str | None = None,
    table_rows_mode: bool = False,
    evaluation_mode: EvaluationMode = "exhaustive",
) -> tuple[float, ExpectedPropositionMatch]:
    exp_effect = _field_str(expected, "legal_effect_type")
    act_effect = _field_str(actual, "legal_effect_type")
    exp_tier = _field_str(expected, "proposition_tier")
    act_tier = _field_str(actual, "proposition_tier")

    legal_effect_ok = (not exp_effect) or exp_effect == act_effect
    effect_equivalent = _legal_effects_equivalent(
        exp_effect,
        act_effect,
        expected=expected,
        actual=actual,
    )
    classification_mismatch = bool(exp_effect and act_effect and not legal_effect_ok and effect_equivalent)
    tier_ok = (not exp_tier) or exp_tier == act_tier

    evidence_needle = _field_str(expected, "evidence_quote")
    evidence_hay = f"{_evidence_text(actual)} {_field_str(actual, 'proposition_text')}"
    evidence_ok = _fuzzy_contains(evidence_needle, evidence_hay)
    if (
        not evidence_ok
        and table_rows_mode
        and evidence_needle
        and source_fragment_text
    ):
        for candidate in (
            evidence_needle,
            _evidence_text(actual),
            _field_str(actual, "proposition_text"),
        ):
            if not candidate.strip():
                continue
            ok, _strategy, _diag = evidence_locates_verbatim_after_normalisation(
                candidate, source_fragment_text
            )
            if ok:
                evidence_ok = True
                break

    exp_conditions = [str(c).strip() for c in (expected.get("conditions") or []) if str(c).strip()]
    exp_exceptions = [str(c).strip() for c in (expected.get("exceptions") or []) if str(c).strip()]
    act_conditions, act_exceptions = _conditions_and_exceptions(actual)
    conditions_blob = " ".join([*act_conditions, *act_exceptions])

    contained_evidence_ok = False
    if evidence_needle and _fuzzy_contains(evidence_needle, conditions_blob):
        contained_evidence_ok = True
        evidence_ok = True
    elif not evidence_ok and evidence_needle:
        contained_evidence_ok = _contained_in_actual_fields(expected, actual)
        if contained_evidence_ok:
            evidence_ok = True

    subject_ok = _fuzzy_contains(_field_str(expected, "legal_subject"), _field_str(actual, "legal_subject"))
    action_ok = _fuzzy_contains(_field_str(expected, "action"), _field_str(actual, "action"))
    if not subject_ok and contained_evidence_ok:
        subject_ok = _fuzzy_contains(_field_str(expected, "legal_subject"), _actual_text_blob(actual))
    if not action_ok and contained_evidence_ok:
        action_ok = _fuzzy_contains(_field_str(expected, "action"), _actual_text_blob(actual))

    conditions_ok = True
    if exp_conditions or exp_exceptions:
        conditions_ok = bool(act_conditions or act_exceptions)
        if not conditions_ok:
            blob = _actual_text_blob(actual)
            for marker in (*exp_conditions, *exp_exceptions):
                if _fuzzy_contains(marker, blob):
                    conditions_ok = True
                    break

    score = 0.0
    if legal_effect_ok or effect_equivalent:
        score += 0.35
    if tier_ok or classification_mismatch:
        score += 0.15
    if evidence_ok:
        score += 0.30
    if subject_ok:
        score += 0.10
    if action_ok:
        score += 0.10
    if conditions_ok:
        score += 0.05 if (exp_conditions or exp_exceptions) else 0.0

    effect_ok_for_match = legal_effect_ok or effect_equivalent
    exact_match = (
        legal_effect_ok
        and tier_ok
        and evidence_ok
        and not contained_evidence_ok
        and not classification_mismatch
    )
    if exact_match:
        match_kind: MatchKind = "exact"
    elif contained_evidence_ok and evidence_ok:
        match_kind = "contained_in_actual"
    elif (
        effect_ok_for_match
        and evidence_ok
        and classification_mismatch
        and evaluation_mode in {"minimum", "targeted", "table_rows"}
    ):
        match_kind = "classification_mismatch"
    elif (
        classification_mismatch
        and evidence_ok
        and evaluation_mode == "exhaustive"
    ):
        match_kind = "classification_mismatch"
    elif (
        evidence_ok
        and (contained_evidence_ok or len(act_conditions) > 1)
        and (subject_ok or action_ok or conditions_ok)
        and score >= 0.55
    ):
        match_kind = "bundled_match"
    elif effect_ok_for_match and evidence_ok and (subject_ok or action_ok) and (tier_ok or score >= 0.55):
        match_kind = "exact"
    else:
        match_kind = "none"

    matched = match_kind != "none" and evidence_ok and (
        effect_ok_for_match or match_kind in {"contained_in_actual", "bundled_match"}
    )
    if match_kind == "classification_mismatch" and evaluation_mode == "exhaustive":
        matched = False
    if match_kind == "bundled_match" and evaluation_mode == "exhaustive":
        matched = False

    failure: str | None = None
    if not matched:
        parts: list[str] = []
        if not effect_ok_for_match:
            parts.append(f"expected legal_effect_type {exp_effect!r}, got {act_effect!r}")
        elif classification_mismatch and evaluation_mode == "exhaustive":
            parts.append(
                f"classification mismatch (expected {exp_effect!r}, got {act_effect!r}); "
                "text/evidence align"
            )
        if not evidence_ok:
            parts.append("evidence quote not found in actual evidence or proposition text")
        if not tier_ok and exp_tier and not classification_mismatch:
            parts.append(f"expected tier {exp_tier!r}, got {act_tier!r}")
        if not subject_ok:
            parts.append("legal_subject weak or missing")
        if not action_ok:
            parts.append("action weak or missing")
        if not conditions_ok:
            parts.append("expected conditions/exceptions not reflected in actual output")
        if match_kind == "bundled_match" and evaluation_mode == "exhaustive":
            parts.append("bundled actual row (strict granularity required in exhaustive mode)")
        failure = "; ".join(parts) if parts else "no close match"

    detail = ExpectedPropositionMatch(
        expected_index=-1,
        expected=expected,
        legal_effect_ok=legal_effect_ok or effect_equivalent,
        tier_ok=tier_ok or classification_mismatch,
        evidence_ok=evidence_ok,
        subject_ok=subject_ok,
        action_ok=action_ok,
        conditions_ok=conditions_ok,
        matched=matched,
        match_score=score,
        match_kind=match_kind,
        contained_evidence_ok=contained_evidence_ok,
        classification_mismatch=classification_mismatch,
        suggested_failure_reason=failure,
    )
    return score, detail


def _unmatched_expected_row(
    expected: dict[str, Any],
    *,
    exp_idx: int,
    reason: str,
) -> ExpectedPropositionMatch:
    exp_effect = _field_str(expected, "legal_effect_type")
    return ExpectedPropositionMatch(
        expected_index=exp_idx,
        expected=expected,
        legal_effect_ok=False,
        tier_ok=False,
        evidence_ok=False,
        subject_ok=False,
        action_ok=False,
        conditions_ok=False,
        matched=False,
        match_score=0.0,
        suggested_failure_reason=reason
        if reason
        else (
            f"no actual proposition matched expected legal_effect_type {exp_effect!r}"
            if exp_effect
            else "no_actual_propositions"
        ),
    )


def _match_expected_to_actual(
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    *,
    source_fragment_text: str | None = None,
    table_rows_mode: bool = False,
    evaluation_mode: EvaluationMode = "exhaustive",
) -> list[ExpectedPropositionMatch]:
    if not actual_rows:
        reason = "no_actual_propositions" if expected_rows else "no_expected_propositions"
        return [
            _unmatched_expected_row(expected, exp_idx=exp_idx, reason=reason)
            for exp_idx, expected in enumerate(expected_rows)
        ]

    used_actual: set[int] = set()
    results: list[ExpectedPropositionMatch] = []

    for exp_idx, expected in enumerate(expected_rows):
        best_score = -1.0
        best_detail: ExpectedPropositionMatch | None = None
        best_act_idx: int | None = None

        for act_idx, actual in enumerate(actual_rows):
            if act_idx in used_actual:
                continue
            score, detail = _score_expected_against_actual(
                expected,
                actual,
                source_fragment_text=source_fragment_text,
                table_rows_mode=table_rows_mode,
                evaluation_mode=evaluation_mode,
            )
            if score > best_score:
                best_score = score
                best_detail = detail
                best_act_idx = act_idx

        if best_detail is None or not best_detail.matched:
            for act_idx, actual in enumerate(actual_rows):
                score, detail = _score_expected_against_actual(
                    expected,
                    actual,
                    source_fragment_text=source_fragment_text,
                    table_rows_mode=table_rows_mode,
                    evaluation_mode=evaluation_mode,
                )
                if detail.match_kind in {"contained_in_actual", "classification_mismatch", "bundled_match"}:
                    if score > best_score or (best_detail is not None and not best_detail.matched):
                        best_score = score
                        best_detail = detail
                        best_act_idx = act_idx

        if best_detail is None:
            best_detail = _unmatched_expected_row(
                expected,
                exp_idx=exp_idx,
                reason="no_actual_propositions",
            )
        else:
            best_detail.expected_index = exp_idx
            if best_detail.matched and best_act_idx is not None:
                if best_detail.match_kind in _EXCLUSIVE_MATCH_KINDS:
                    used_actual.add(best_act_idx)
                best_detail.matched_actual_index = best_act_idx
                best_detail.matched_actual_id = _field_str(actual_rows[best_act_idx], "id") or None
                best_detail.suggested_failure_reason = None
            elif best_detail.suggested_failure_reason is None:
                best_detail.suggested_failure_reason = (
                    "no actual proposition matched this expected row"
                )
        results.append(best_detail)

    return results


def _check_proposition_count(
    *,
    actual_count: int,
    expected_count: int,
    mode: EvaluationMode,
    strict: bool,
    max_extra_actual: int | None,
) -> dict[str, Any]:
    passed = True
    status = "ok"
    detail = f"actual={actual_count}, expected={expected_count}, mode={mode}"
    if mode == "exhaustive":
        if strict:
            passed = actual_count == expected_count
            if not passed:
                status = "exact_count_mismatch"
        elif actual_count < expected_count:
            passed = False
            status = "too_few"
        elif actual_count > expected_count:
            passed = False
            status = "too_many"
    elif mode in {"targeted", "minimum", "table_rows"}:
        if expected_count and actual_count == 0:
            passed = False
            status = "no_actual_propositions"
        elif max_extra_actual is not None and actual_count > expected_count + max_extra_actual:
            passed = False
            status = "too_many_extras"
    return {
        "passed": passed,
        "status": status,
        "strict": strict,
        "mode": mode,
        "detail": detail,
    }


def _check_extra_actual(
    *,
    extra_count: int,
    mode: EvaluationMode,
    allow_extra_actual: bool,
    max_extra_actual: int | None,
) -> dict[str, Any]:
    if extra_count == 0:
        return {
            "passed": True,
            "status": "none",
            "extra_count": 0,
            "allow_extra_actual": allow_extra_actual,
            "mode": mode,
            "detail": "no extra actual propositions",
        }
    detail = f"{extra_count} extra actual propositions"
    if mode in {"targeted", "minimum", "table_rows"}:
        if max_extra_actual is not None and extra_count > max_extra_actual:
            return {
                "passed": False,
                "status": "too_many_extras",
                "extra_count": extra_count,
                "allow_extra_actual": True,
                "mode": mode,
                "detail": f"{detail} (exceeds max_extra_actual={max_extra_actual})",
            }
        return {
            "passed": True,
            "status": "extras_allowed",
            "extra_count": extra_count,
            "allow_extra_actual": True,
            "mode": mode,
            "detail": f"{detail} (allowed by {mode} mode)",
        }
    if allow_extra_actual:
        return {
            "passed": True,
            "status": "extras_allowed",
            "extra_count": extra_count,
            "allow_extra_actual": True,
            "mode": mode,
            "detail": f"{detail} (allowed by fixture)",
        }
    return {
        "passed": False,
        "status": "unexpected_extras",
        "extra_count": extra_count,
        "allow_extra_actual": False,
        "mode": mode,
        "detail": f"{detail} (not allowed in exhaustive mode)",
    }


def _check_effect_and_tier_coverage(
    *,
    expected_rows: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    expected_effects = {_field_str(e, "legal_effect_type") for e in expected_rows if _field_str(e, "legal_effect_type")}
    actual_effects = {_field_str(a, "legal_effect_type") for a in actual_rows if _field_str(a, "legal_effect_type")}
    missing_effects = sorted(expected_effects - actual_effects)

    expected_tiers = {_field_str(e, "proposition_tier") for e in expected_rows if _field_str(e, "proposition_tier")}
    actual_tiers = {_field_str(a, "proposition_tier") for a in actual_rows if _field_str(a, "proposition_tier")}
    missing_tiers = sorted(expected_tiers - actual_tiers)

    effect_check = {
        "passed": not missing_effects,
        "missing": missing_effects,
        "expected": sorted(expected_effects),
        "actual": sorted(actual_effects),
    }
    tier_check = {
        "passed": not missing_tiers,
        "missing": missing_tiers,
        "expected": sorted(expected_tiers),
        "actual": sorted(actual_tiers),
    }
    return effect_check, tier_check, missing_effects


def _check_boilerplate_misclassified(actual_rows: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for idx, row in enumerate(actual_rows):
        effect = _field_str(row, "legal_effect_type")
        text = _field_str(row, "proposition_text")
        if effect == LegalEffectType.OBLIGATION.value and any(
            kw in _normalize_text(text)
            for kw in (
                "may be cited",
                "come into force",
                "extend to",
                "citation",
                "commencement",
            )
        ):
            findings.append(
                {
                    "actual_index": idx,
                    "proposition_id": _field_str(row, "id"),
                    "reason": "boilerplate language classified as obligation",
                }
            )
        if effect in _BOILERPLATE_EFFECTS and row.get("is_compliance_relevant") is True:
            findings.append(
                {
                    "actual_index": idx,
                    "proposition_id": _field_str(row, "id"),
                    "reason": f"{effect} marked compliance-relevant (checkable)",
                }
            )
    return {"passed": not findings, "findings": findings}


def _check_over_compression(
    actual_rows: list[dict[str, Any]],
    expected_rows: list[dict[str, Any]],
    *,
    mode: EvaluationMode,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    expected_effects = [_field_str(e, "legal_effect_type") for e in expected_rows if _field_str(e, "legal_effect_type")]
    distinct_expected_effects = len(set(expected_effects))

    for idx, row in enumerate(actual_rows):
        text = _field_str(row, "proposition_text")
        modals = _modal_verb_count(text)
        if modals >= 2:
            findings.append(
                {
                    "actual_index": idx,
                    "proposition_id": _field_str(row, "id"),
                    "modal_verb_count": modals,
                    "reason": "single proposition contains multiple modal verbs (possible over-compression)",
                }
            )

    if distinct_expected_effects >= 3 and len(actual_rows) == 1:
        findings.append(
            {
                "actual_index": 0,
                "proposition_id": _field_str(actual_rows[0], "id") if actual_rows else "",
                "reason": (
                    f"only one proposition returned but fixture expects {distinct_expected_effects} "
                    "distinct legal effects"
                ),
            }
        )

    warn_only = mode in {"targeted", "minimum", "table_rows"}
    return {
        "passed": not findings or warn_only,
        "findings": findings,
        "warn_only": warn_only,
    }


def _check_unexpected_checkable(
    actual_rows: list[dict[str, Any]],
    *,
    expected_checkable_count: int | None,
) -> dict[str, Any]:
    checkable = [row for row in actual_rows if _is_checkable_row(row)]
    unexpected: list[dict[str, Any]] = []
    for idx, row in enumerate(actual_rows):
        effect = _field_str(row, "legal_effect_type")
        if effect in _BOILERPLATE_EFFECTS and _is_checkable_row(row):
            unexpected.append(
                {
                    "actual_index": idx,
                    "proposition_id": _field_str(row, "id"),
                    "legal_effect_type": effect,
                    "reason": "boilerplate effect should not be checkable",
                }
            )

    passed = True
    detail: dict[str, Any] = {
        "checkable_count": len(checkable),
        "unexpected_boilerplate_checkable": unexpected,
    }
    if expected_checkable_count is not None:
        detail["expected_checkable_count"] = expected_checkable_count
        passed = len(checkable) == expected_checkable_count and not unexpected
    elif unexpected:
        passed = False
    return {"passed": passed, **detail}


def _eval_result_load_error(
    *,
    fixture_data: dict[str, Any],
    fixture_path: str,
    run_dir: str | Path,
    load: ActualPropositionsLoad,
) -> PromptEvalResult:
    expected_rows = list(fixture_data.get("expected_propositions") or [])
    reason = load.error or "failed_to_load_actual_propositions"
    matches = _match_expected_to_actual(expected_rows, [])
    return PromptEvalResult(
        case_id=str(fixture_data.get("case_id") or ""),
        label=str(fixture_data.get("label") or ""),
        fixture_path=fixture_path,
        run_dir=str(Path(run_dir).resolve()),
        passed=False,
        eval_status="error",
        actual_count=0,
        expected_count=len(expected_rows),
        matched_expected_count=0,
        checks={
            "load": {"passed": False, "error": reason, "warnings": load.warnings},
            "expected_row_matches": {
                "passed": False,
                "matched": 0,
                "expected": len(expected_rows),
            },
        },
        expected_matches=matches,
        warnings=list(load.warnings),
        summary={
            "pass": False,
            "eval_status": "error",
            "reason": reason,
            "suggested_focus": ["load_error", "no_actual_propositions"],
        },
    )


def evaluate_prompt_lab_extraction(
    *,
    fixture: dict[str, Any] | str | Path,
    run_dir: str | Path,
    prefer_normalised: bool = True,
) -> PromptEvalResult:
    """Compare actual run output against a prompt-lab fixture (does not raise on empty/missing actuals)."""
    fixture_path = str(fixture) if isinstance(fixture, (str, Path)) else ""
    try:
        fixture_data = (
            load_prompt_lab_fixture(fixture) if not isinstance(fixture, dict) else fixture
        )
    except ValueError as exc:
        return PromptEvalResult(
            case_id="",
            label="",
            fixture_path=fixture_path,
            run_dir=str(Path(run_dir).resolve()),
            passed=False,
            eval_status="error",
            actual_count=0,
            expected_count=0,
            matched_expected_count=0,
            checks={"fixture": {"passed": False, "error": str(exc)}},
            summary={"pass": False, "eval_status": "error", "reason": str(exc)},
        )

    cfg = _evaluation_config(fixture_data)
    mode = str(cfg.get("mode") or "exhaustive")
    strict_count = bool(cfg.get("strict_proposition_count"))
    allow_extra_actual = bool(cfg.get("allow_extra_actual", False))
    max_extra_actual = cfg.get("max_extra_actual")
    if max_extra_actual is not None:
        max_extra_actual = int(max_extra_actual)
    expected_checkable = cfg.get("expected_checkable_count")
    if expected_checkable is not None:
        expected_checkable = int(expected_checkable)
    source_fragment_text = str(fixture_data.get("fragment_text") or "").strip() or None
    table_rows_mode = mode == "table_rows"

    load = load_actual_propositions_with_meta(run_dir, prefer_normalised=prefer_normalised)
    expected_rows = list(fixture_data.get("expected_propositions") or [])
    if not all(isinstance(x, dict) for x in expected_rows):
        return PromptEvalResult(
            case_id=str(fixture_data.get("case_id") or ""),
            label=str(fixture_data.get("label") or ""),
            fixture_path=fixture_path,
            run_dir=str(Path(run_dir).resolve()),
            passed=False,
            eval_status="error",
            actual_count=len(load.rows),
            expected_count=0,
            matched_expected_count=0,
            warnings=list(load.warnings),
            checks={"fixture": {"passed": False, "error": "expected_propositions must be objects"}},
            summary={"pass": False, "eval_status": "error", "reason": "invalid fixture"},
        )

    if load.error and not load.rows:
        return _eval_result_load_error(
            fixture_data=fixture_data,
            fixture_path=fixture_path,
            run_dir=run_dir,
            load=load,
        )

    actual_rows = load.rows
    warnings = list(load.warnings)

    matches = _match_expected_to_actual(
        expected_rows,
        actual_rows,
        source_fragment_text=source_fragment_text,
        table_rows_mode=table_rows_mode,
        evaluation_mode=mode,  # type: ignore[arg-type]
    )
    matched_count = sum(1 for m in matches if m.matched)
    used_actual = {
        m.matched_actual_index
        for m in matches
        if m.matched_actual_index is not None and m.match_kind in _EXCLUSIVE_MATCH_KINDS
    }

    extra_actual: list[dict[str, Any]] = []
    for idx, row in enumerate(actual_rows):
        if idx not in used_actual:
            extra_actual.append(
                {
                    "actual_index": idx,
                    "proposition_id": _field_str(row, "id"),
                    "legal_effect_type": _field_str(row, "legal_effect_type"),
                    "proposition_tier": _field_str(row, "proposition_tier"),
                    "proposition_text": _field_str(row, "proposition_text")[:240],
                    "is_compliance_relevant": row.get("is_compliance_relevant"),
                }
            )

    count_check = _check_proposition_count(
        actual_count=len(actual_rows),
        expected_count=len(expected_rows),
        mode=mode,  # type: ignore[arg-type]
        strict=strict_count,
        max_extra_actual=max_extra_actual,
    )
    extra_check = _check_extra_actual(
        extra_count=len(extra_actual),
        mode=mode,  # type: ignore[arg-type]
        allow_extra_actual=allow_extra_actual,
        max_extra_actual=max_extra_actual,
    )
    effect_check, tier_check, missing_effects = _check_effect_and_tier_coverage(
        expected_rows=expected_rows,
        actual_rows=actual_rows,
    )
    if matched_count == len(expected_rows) and expected_rows:
        effect_check = {**effect_check, "passed": True, "missing": []}
        tier_check = {**tier_check, "passed": True, "missing": []}
        missing_effects = []
    boilerplate_check = _check_boilerplate_misclassified(actual_rows)
    compression_check = _check_over_compression(
        actual_rows,
        expected_rows,
        mode=mode,  # type: ignore[arg-type]
    )
    checkable_check = _check_unexpected_checkable(
        actual_rows,
        expected_checkable_count=expected_checkable,
    )

    match_check_passed = matched_count == len(expected_rows)
    no_actual_check = {
        "passed": bool(actual_rows) or not expected_rows,
        "reason": None if actual_rows else "no_actual_propositions",
    }
    checks = {
        "load": {
            "passed": True,
            "source_file": load.source_file,
            "warnings": warnings,
        },
        "evaluation_mode": {
            "passed": True,
            "mode": mode,
            "strict_proposition_count": strict_count,
            "allow_extra_actual": allow_extra_actual,
            "max_extra_actual": max_extra_actual,
        },
        "proposition_count": count_check,
        "extra_actual": extra_check,
        "no_actual_propositions": no_actual_check,
        "expected_row_matches": {
            "passed": match_check_passed,
            "matched": matched_count,
            "expected": len(expected_rows),
        },
        "legal_effect_coverage": effect_check,
        "tier_coverage": tier_check,
        "boilerplate_classification": boilerplate_check,
        "over_compression": compression_check,
        "checkable_count": checkable_check,
    }

    if extra_check.get("status") == "extras_allowed" and extra_check.get("extra_count"):
        warnings.append(str(extra_check.get("detail") or "extra actual propositions allowed"))
    if compression_check.get("findings") and compression_check.get("warn_only"):
        warnings.append(
            f"over_compression findings present ({len(compression_check['findings'])}); "
            f"warn-only in {mode} mode"
        )
    for match in matches:
        if match.classification_mismatch and match.matched:
            warnings.append(
                f"expected[{match.expected_index}]: classification_mismatch "
                f"({match.match_kind}); gold legal_effect accepted via equivalence"
            )
        elif match.match_kind == "contained_in_actual" and match.matched:
            warnings.append(
                f"expected[{match.expected_index}]: contained_in_actual match "
                "(expected row found inside actual conditions/evidence envelope)"
            )
        elif match.match_kind == "bundled_match" and match.matched:
            warnings.append(
                f"expected[{match.expected_index}]: bundled_match "
                "(expected row satisfied by a multi-condition actual proposition)"
            )

    passed = all(
        bool(c.get("passed"))
        for c in checks.values()
        if isinstance(c, dict) and "passed" in c
    )
    eval_status = "pass" if passed else "fail"

    result = PromptEvalResult(
        case_id=str(fixture_data.get("case_id") or ""),
        label=str(fixture_data.get("label") or ""),
        fixture_path=fixture_path,
        run_dir=str(Path(run_dir).resolve()),
        passed=passed,
        eval_status=eval_status,
        actual_count=len(actual_rows),
        expected_count=len(expected_rows),
        matched_expected_count=matched_count,
        checks=checks,
        expected_matches=matches,
        extra_actual=extra_actual,
        missing_effects=missing_effects,
        warnings=warnings,
        summary={
            "pass": passed,
            "eval_status": eval_status,
            "evaluation_mode": mode,
            "allow_extra_actual": allow_extra_actual,
            "matched_expected": f"{matched_count}/{len(expected_rows)}",
            "extra_actual_count": len(extra_actual),
            "suggested_focus": _suggested_focus(checks, matches),
        },
    )
    return result


def _suggested_focus(
    checks: dict[str, Any],
    matches: list[ExpectedPropositionMatch],
) -> list[str]:
    focus: list[str] = []
    if not checks.get("proposition_count", {}).get("passed"):
        focus.append("proposition_count")
    if not checks.get("extra_actual", {}).get("passed"):
        focus.append("extra_actual")
    if not checks.get("legal_effect_coverage", {}).get("passed"):
        focus.append("missing_legal_effects")
    if not checks.get("boilerplate_classification", {}).get("passed"):
        focus.append("boilerplate_misclassification")
    if not checks.get("over_compression", {}).get("passed"):
        focus.append("over_compression")
    if not checks.get("checkable_count", {}).get("passed"):
        focus.append("unexpected_checkable")
    for m in matches:
        if not m.matched and m.suggested_failure_reason:
            focus.append(f"expected[{m.expected_index}]")
    return focus[:12]


def build_prompt_eval_markdown(result: PromptEvalResult) -> str:
    if result.eval_status == "error":
        status = "ERROR"
    elif result.passed:
        status = "PASS"
    else:
        status = "FAIL"
    lines = [
        "# Prompt-lab evaluation",
        "",
        f"**Result:** {status}",
        "",
        f"- **Case:** `{result.case_id}` — {result.label}",
        f"- **Run directory:** `{result.run_dir}`",
        f"- **Propositions:** {result.actual_count} actual / {result.expected_count} expected "
        f"({result.matched_expected_count} matched)",
        "",
        "## Summary",
        "",
    ]
    for key, value in result.summary.items():
        if isinstance(value, list):
            lines.append(f"- **{key}:** {', '.join(str(v) for v in value) or '—'}")
        else:
            lines.append(f"- **{key}:** {value}")

    if result.warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in result.warnings:
            lines.append(f"- {warning}")

    lines.extend(["", "## Checks", ""])
    eval_mode = result.summary.get("evaluation_mode")
    if eval_mode:
        allow_extras = result.summary.get("allow_extra_actual")
        lines.append(
            f"- **Evaluation mode:** `{eval_mode}` "
            f"(extra actual propositions {'allowed' if allow_extras else 'not allowed'})"
        )
        lines.append("")
    for name, check in result.checks.items():
        if not isinstance(check, dict):
            continue
        mark = "ok" if check.get("passed") else "FAIL"
        lines.append(f"- **{name}:** {mark}")
        if check.get("detail"):
            lines.append(f"  - {check['detail']}")
        if check.get("status"):
            lines.append(f"  - status: {check['status']}")
        if check.get("missing"):
            lines.append(f"  - missing: {', '.join(check['missing'])}")
        for finding in (check.get("findings") or check.get("unexpected_boilerplate_checkable") or [])[:5]:
            if isinstance(finding, dict):
                lines.append(f"  - {finding.get('reason', finding)}")

    lines.extend(["", "## Expected proposition matches", ""])
    for m in result.expected_matches:
        mark = "matched" if m.matched else "MISS"
        effect = _field_str(m.expected, "legal_effect_type")
        lines.append(f"### [{mark}] expected #{m.expected_index + 1} — `{effect}`")
        if m.matched_actual_id:
            lines.append(f"- Matched actual: `{m.matched_actual_id}` (score {m.match_score:.2f})")
        flags = []
        if not m.legal_effect_ok:
            flags.append("legal_effect")
        if not m.tier_ok:
            flags.append("tier")
        if not m.evidence_ok:
            flags.append("evidence")
        if not m.subject_ok:
            flags.append("subject")
        if not m.action_ok:
            flags.append("action")
        if not m.conditions_ok:
            flags.append("conditions")
        if flags:
            lines.append(f"- Weak: {', '.join(flags)}")
        if m.suggested_failure_reason:
            lines.append(f"- **Suggested reason:** {m.suggested_failure_reason}")
        lines.append("")

    if result.extra_actual:
        lines.extend(["## Extra actual propositions", ""])
        allow = result.summary.get("allow_extra_actual")
        if allow:
            lines.append(
                f"_{len(result.extra_actual)} extra row(s); allowed by "
                f"{result.summary.get('evaluation_mode', 'fixture')} mode._"
            )
            lines.append("")
        for row in result.extra_actual:
            lines.append(
                f"- `{row.get('proposition_id', '?')}` "
                f"({row.get('legal_effect_type')}, {row.get('proposition_tier')}): "
                f"{row.get('proposition_text', '')[:120]}"
            )
        lines.append("")

    if result.missing_effects:
        lines.extend(["## Missing legal effects", ""])
        for effect in result.missing_effects:
            lines.append(f"- `{effect}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def evaluate_and_write_prompt_lab_run(
    *,
    fixture: dict[str, Any] | str | Path,
    run_dir: str | Path,
    prefer_normalised: bool = True,
    reapply_normalisation: bool = False,
) -> tuple[PromptEvalResult, Path, Path]:
    """Evaluate a workbench run directory and write prompt_eval artifacts."""
    if reapply_normalisation:
        from .extraction_workbench import reapply_normalisation_to_run_dir

        reapply_normalisation_to_run_dir(run_dir)
    result = evaluate_prompt_lab_extraction(
        fixture=fixture,
        run_dir=run_dir,
        prefer_normalised=prefer_normalised,
    )
    json_path, md_path = write_prompt_eval_outputs(result, run_dir)
    return result, json_path, md_path


def write_prompt_eval_outputs(
    result: PromptEvalResult,
    run_dir: str | Path,
) -> tuple[Path, Path]:
    root = Path(run_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / PROMPT_EVAL_JSON
    md_path = root / PROMPT_EVAL_MD
    json_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(build_prompt_eval_markdown(result), encoding="utf-8")
    return json_path, md_path
