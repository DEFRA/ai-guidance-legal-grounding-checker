"""Deterministic semantic-role matching for benchmark outputs.

Shares Article 49a resolution with the existing acceptance helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    identify_article_49a_propositions,
)

from .fixtures import ExpectedProposition, PropositionFidelityCase


@dataclass(frozen=True)
class RoleMatch:
    role: str
    proposition_id: str | None
    status: str  # matched | missing | ambiguous
    competing_candidate_ids: tuple[str, ...] = ()
    notes: str = ""


def _prop_id(prop: dict[str, Any]) -> str:
    return str(prop.get("id") or "")


def _debug_meta(prop: dict[str, Any]) -> dict[str, Any]:
    meta = prop.get("extraction_debug_meta")
    return meta if isinstance(meta, dict) else {}


def _structured_path(prop: dict[str, Any]) -> str | None:
    path = _debug_meta(prop).get("structured_list_path")
    return str(path) if path else None


def _locator(prop: dict[str, Any]) -> str:
    return str(prop.get("fragment_locator") or "")


def _effect(prop: dict[str, Any]) -> str:
    return str(prop.get("legal_effect_type") or "")


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _contains_all(haystack: str, needles: tuple[str, ...] | list[str]) -> bool:
    h = _norm(haystack)
    return all(_norm(n) in h for n in needles if str(n).strip())


def _score_candidate(prop: dict[str, Any], expected: ExpectedProposition) -> int:
    """Higher is better. Deterministic invariant scoring — not label text alone."""
    score = 0
    loc = _locator(prop)
    if expected.source_locator and (
        loc == expected.source_locator or loc.startswith(expected.source_locator)
    ):
        score += 40
    elif expected.source_locator and expected.source_locator in loc:
        score += 20

    path = _structured_path(prop)
    if expected.structured_list_path:
        if path == expected.structured_list_path:
            score += 50
        else:
            score -= 30

    if expected.legal_effect_type and _effect(prop) == expected.legal_effect_type:
        score += 25
    elif expected.legal_effect_type and _effect(prop):
        score -= 10

    blob = " ".join(
        [
            str(prop.get("proposition_text") or ""),
            str(prop.get("legal_subject") or ""),
            str(prop.get("action") or ""),
            " ".join(str(x) for x in (prop.get("conditions") or [])),
            str(_debug_meta(prop).get("evidence_quote") or ""),
        ]
    )
    if expected.required_actor and _norm(expected.required_actor) in _norm(
        str(prop.get("legal_subject") or "")
    ):
        score += 15
    elif expected.required_actor and _norm(expected.required_actor) in _norm(blob):
        score += 8

    if expected.required_action and _contains_all(
        str(prop.get("action") or "") + " " + str(prop.get("proposition_text") or ""),
        (expected.required_action,),
    ):
        score += 15
    elif expected.action_expectation is not None:
        action_blob = (
            str(prop.get("action") or "") + " " + str(prop.get("proposition_text") or "")
        ).lower()
        pred_hits = sum(
            1
            for pred in expected.action_expectation.predicates
            if pred in action_blob
            or any(f in action_blob for f in (pred + "ed", pred + "ing", pred + "es", pred + "s"))
        )
        if pred_hits == len(expected.action_expectation.predicates):
            score += 15
        if expected.action_expectation.legal_effect and _effect(prop) == (
            expected.action_expectation.legal_effect
        ):
            score += 5

    if expected.object and _norm(expected.object) in _norm(blob):
        score += 10

    for marker in expected.evidence_markers:
        if _norm(marker) in _norm(blob):
            score += 8

    for thr in expected.thresholds:
        if _norm(thr) in _norm(blob):
            score += 10

    return score


def match_roles_for_case(
    case: PropositionFidelityCase,
    propositions: list[dict[str, Any]],
    *,
    article_49a_bundle: dict[str, Any] | None = None,
) -> tuple[list[RoleMatch], list[dict[str, Any]]]:
    """Return (role matches, unexpected props). Never silently picks on ties."""
    if case.runner == "article_49a_pipeline":
        return _match_article_49a(case, propositions, article_49a_bundle)

    assigned: dict[str, str] = {}
    matches: list[RoleMatch] = []
    used_ids: set[str] = set()

    for expected in case.gold:
        scored: list[tuple[int, dict[str, Any]]] = []
        for prop in propositions:
            pid = _prop_id(prop)
            if not pid or pid in used_ids:
                continue
            scored.append((_score_candidate(prop, expected), prop))
        scored.sort(key=lambda item: (-item[0], _prop_id(item[1])))
        if not scored or scored[0][0] < 30:
            matches.append(
                RoleMatch(
                    role=expected.role,
                    proposition_id=None,
                    status="missing",
                    notes="no candidate met deterministic invariant threshold",
                )
            )
            continue
        top_score = scored[0][0]
        tied = [p for s, p in scored if s == top_score]
        if len(tied) > 1:
            # Exact duplicate rows (same locator/effect/text): keep lowest id,
            # leave the rest for unexpected reporting. Distinct competing
            # candidates remain ambiguous for human review.
            def _fingerprint(prop: dict[str, Any]) -> tuple[str, str, str, str]:
                return (
                    _locator(prop),
                    _effect(prop),
                    str(_structured_path(prop) or ""),
                    _norm(str(prop.get("proposition_text") or "")),
                )

            fingerprints = {_fingerprint(p) for p in tied}
            if len(fingerprints) == 1:
                winner = sorted(tied, key=_prop_id)[0]
                pid = _prop_id(winner)
                used_ids.add(pid)
                assigned[expected.role] = pid
                matches.append(
                    RoleMatch(
                        role=expected.role,
                        proposition_id=pid,
                        status="matched",
                        notes=f"score={top_score}; duplicate_rows_collapsed",
                    )
                )
                continue
            matches.append(
                RoleMatch(
                    role=expected.role,
                    proposition_id=None,
                    status="ambiguous",
                    competing_candidate_ids=tuple(_prop_id(p) for p in tied),
                    notes=(
                        "ambiguous deterministic match; human review required; "
                        f"score={top_score}"
                    ),
                )
            )
            continue
        winner = tied[0]
        pid = _prop_id(winner)
        used_ids.add(pid)
        assigned[expected.role] = pid
        matches.append(
            RoleMatch(
                role=expected.role,
                proposition_id=pid,
                status="matched",
                notes=f"score={top_score}",
            )
        )

    unexpected = [p for p in propositions if _prop_id(p) not in used_ids]
    return matches, unexpected


def _match_article_49a(
    case: PropositionFidelityCase,
    propositions: list[dict[str, Any]],
    bundle: dict[str, Any] | None,
) -> tuple[list[RoleMatch], list[dict[str, Any]]]:
    """Share identify_article_49a_propositions; map P1..P3 → semantic roles."""
    role_map = {
        g.article_49a_role: g.role for g in case.gold if g.article_49a_role
    }
    if not role_map:
        raise ValueError("Article 49a gold contracts must set article_49a_role")

    source_bundle = bundle if bundle is not None else {"propositions": propositions}
    opaque: dict[str, str] | None = None
    # Saved live-calibration artifacts may carry the opaque role map without
    # structured_list_path meta needed to re-identify from propositions alone.
    if isinstance(source_bundle, dict):
        raw_opaque = source_bundle.get("opaque_roles")
        if isinstance(raw_opaque, dict) and raw_opaque:
            opaque = {str(k): str(v) for k, v in raw_opaque.items() if str(v).strip()}
    if opaque is None:
        try:
            opaque = identify_article_49a_propositions(source_bundle)
        except AssertionError as exc:
            matches = [
                RoleMatch(
                    role=g.role,
                    proposition_id=None,
                    status="missing",
                    notes=f"article_49a resolver failed: {exc}",
                )
                for g in case.gold
            ]
            return matches, list(propositions)

    used: set[str] = set()
    matches: list[RoleMatch] = []
    for expected in case.gold:
        a49 = expected.article_49a_role
        if not a49 or a49 not in opaque:
            matches.append(
                RoleMatch(
                    role=expected.role,
                    proposition_id=None,
                    status="missing",
                    notes=f"missing Article 49a role {a49}",
                )
            )
            continue
        pid = opaque[a49]
        used.add(pid)
        matches.append(
            RoleMatch(
                role=expected.role,
                proposition_id=pid,
                status="matched",
                notes=(
                    f"via saved opaque_roles({a49})"
                    if isinstance(source_bundle, dict)
                    and isinstance(source_bundle.get("opaque_roles"), dict)
                    and source_bundle.get("opaque_roles")
                    else f"via identify_article_49a_propositions({a49})"
                ),
            )
        )

    unexpected = [
        p
        for p in propositions
        if str(p.get("fragment_locator") or "").startswith("article:49a")
        and _prop_id(p) not in used
    ]
    return matches, unexpected


def prop_by_id(
    propositions: list[dict[str, Any]], proposition_id: str | None
) -> dict[str, Any] | None:
    if not proposition_id:
        return None
    for prop in propositions:
        if _prop_id(prop) == proposition_id:
            return prop
    return None
