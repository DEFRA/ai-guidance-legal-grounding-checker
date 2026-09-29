"""Deterministic suppression of dependent measurement qualifications.

Conservative invariant (extraction stage): a candidate may be suppressed as a
dependent qualification only when it shares source identity with a governing
operative proposition, lacks an independent legal effect, has linked/overlapping
evidence, and its measurement/threshold content is preserved on the retained row.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from law_proposition_extractor_pipeline.structured_list_decomposition import StructuredListIdentityContext

DEPENDENT_QUALIFICATION_SUPPRESSED_DIAGNOSTIC = (
    "dependent_qualification_measurement_suppressed"
)

FACT_SUPPRESS_DEPENDENT_QUALIFICATION = "suppress_dependent_qualification"

_MEASUREMENT_CUES = (
    "measured from",
    "is measured",
    "are measured",
    "measurement of",
    "measuring the",
    "distance is measured",
)

_INDEPENDENT_EFFECT_RE = re.compile(
    r"\b("
    r"must\s+not|shall\s+not|must|shall|may|is\s+entitled|"
    r"commits?\s+an\s+offence|is\s+liable|shall\s+be\s+guilty|"
    r"except\s+where|unless|shall\s+not\s+apply|does\s+not\s+apply|"
    r"must\s+record|shall\s+record|must\s+keep|shall\s+keep|"
    r"may\s+inspect|may\s+enter|may\s+require"
    r")\b",
    re.IGNORECASE,
)

_ACTOR_CUES = re.compile(
    r"\b("
    r"occupier|operator|person|keeper|master|owner|authority|"
    r"inspector|competent\s+authority|member\s+state|farmer|"
    r"producer|holder|skipper|captain"
    r")\b",
    re.IGNORECASE,
)

_EXCEPTION_CUES = re.compile(
    r"\b(except|unless|derogat|shall\s+not\s+apply|does\s+not\s+apply)\b",
    re.IGNORECASE,
)

_THRESHOLD_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(metres?|meters?|m|kg|kilograms?|%|percent)\b",
    re.IGNORECASE,
)

_STOP = frozenset(
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
        "from",
        "is",
        "are",
        "be",
        "by",
        "as",
        "that",
        "this",
        "distance",
        "spreading",
    }
)


@dataclass(frozen=True)
class DependentQualificationIdentity:
    source_record_id: str = ""
    source_snapshot_id: str = ""
    source_fragment_id: str = ""


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", _norm(text))
        if len(t) > 2 and t not in _STOP
    }


def _row_blob(row: Mapping[str, Any]) -> str:
    parts = [
        str(row.get("proposition_text") or ""),
        str(row.get("subject") or ""),
        str(row.get("rule") or ""),
        str(row.get("object") or ""),
        " ".join(str(x) for x in (row.get("conditions") or [])),
        str(row.get("evidence_text") or ""),
    ]
    return _norm(" ".join(parts))


def _thresholds(text: str) -> set[str]:
    found: set[str] = set()
    for match in _THRESHOLD_RE.finditer(text or ""):
        num = match.group(1)
        unit = match.group(2).lower()
        if unit.startswith("meter"):
            unit = "metre" if not unit.endswith("s") else "metres"
        found.add(f"{num} {unit}")
        found.add(num)
    # bare numeric mentions like "10-metre"
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)-?(?:metre|meter|m)\b", text or "", re.I):
        found.add(match.group(1))
    return found


def has_independent_legal_effect(row: Mapping[str, Any]) -> bool:
    """True when the row states an independently reviewable legal claim."""
    blob = _row_blob(row)
    if not blob:
        return False
    if _EXCEPTION_CUES.search(blob):
        return True
    if not _INDEPENDENT_EFFECT_RE.search(blob):
        return False
    # Any matched operative modal/exception/power cue means the row is not a
    # pure measurement qualification. Ambiguous actor-less modals are retained
    # (treated as independent) so suppression stays conservative.
    return True


def is_measurement_qualification_row(row: Mapping[str, Any]) -> bool:
    """True when the row only describes how a distance/threshold is measured."""
    blob = _row_blob(row)
    if not blob:
        return False
    if not any(cue in blob for cue in _MEASUREMENT_CUES):
        return False
    if has_independent_legal_effect(row):
        return False
    # Restatement-only meta ("Paragraph 1 restates…") is also non-operative, but
    # this rule targets measurement qualifications specifically.
    return True


def _locators_linked(a: str, b: str) -> bool:
    la = _norm(a).replace(" ", "")
    lb = _norm(b).replace(" ", "")
    if not la or not lb:
        return False
    if la == lb:
        return True
    # Parent/child: regulation:12 vs regulation:12(2) / regulation:12:paragraph:2
    compact_a = re.sub(r"[^a-z0-9:]", "", la)
    compact_b = re.sub(r"[^a-z0-9:]", "", lb)
    if compact_a.startswith(compact_b) or compact_b.startswith(compact_a):
        return True
    # regulation:12(2) ↔ regulation:12:paragraph:2 style
    base_a = re.split(r"[\(:]", la, maxsplit=1)[0]
    base_b = re.split(r"[\(:]", lb, maxsplit=1)[0]
    return bool(base_a and base_a == base_b)


def _evidence_relationship(
    dependent: Mapping[str, Any],
    governing: Mapping[str, Any],
    *,
    source_text: str,
) -> str | None:
    dep_ev = _norm(str(dependent.get("evidence_text") or ""))
    gov_ev = _norm(str(governing.get("evidence_text") or ""))
    if dep_ev and gov_ev and dep_ev in gov_ev:
        return "dependent_evidence_contained_in_governing"
    if dep_ev and gov_ev and gov_ev in dep_ev:
        return "governing_evidence_contained_in_dependent"
    dep_tok = _tokens(dep_ev)
    gov_tok = _tokens(gov_ev)
    if dep_tok and gov_tok and len(dep_tok & gov_tok) >= 3:
        return "material_evidence_token_overlap"
    src = _norm(source_text)
    if (
        dep_ev
        and gov_ev
        and src
        and dep_ev in src
        and gov_ev in src
        and _locators_linked(
            str(dependent.get("source_locator") or ""),
            str(governing.get("source_locator") or ""),
        )
    ):
        return "same_fragment_linked_source_spans"
    return None


def _measurement_basis_phrase(row: Mapping[str, Any]) -> str:
    evidence = str(row.get("evidence_text") or "").strip()
    if evidence:
        return evidence
    text = str(row.get("proposition_text") or "").strip()
    # Prefer the measurement clause if present.
    lower = text.lower()
    for cue in ("measured from", "is measured"):
        idx = lower.find(cue)
        if idx >= 0:
            # walk back to clause start
            start = text.rfind(".", 0, idx)
            start = 0 if start < 0 else start + 1
            return text[start:].strip(" .")
    return text


def _content_preserved(governing: Mapping[str, Any], *, measurement_basis: str, thresholds: set[str]) -> bool:
    blob = _row_blob(governing)
    basis_norm = _norm(measurement_basis)
    if basis_norm and basis_norm not in blob:
        # allow key measurement tokens
        basis_tokens = _tokens(measurement_basis)
        if not basis_tokens or not basis_tokens.issubset(_tokens(blob)):
            return False
    if thresholds:
        gov_thr = _thresholds(blob)
        # require at least one shared numeric threshold token
        if not (thresholds & gov_thr):
            return False
    return True


def _ensure_preservation(
    governing: dict[str, Any],
    *,
    measurement_basis: str,
    thresholds: set[str],
) -> tuple[dict[str, Any], list[str]]:
    """Copy governing and ensure measurement/threshold content is represented."""
    out = dict(governing)
    preserved_fields: list[str] = []
    conditions = [str(x) for x in (out.get("conditions") or []) if str(x).strip()]
    blob_before = _row_blob(out)
    basis = measurement_basis.strip()
    if basis and _norm(basis) not in blob_before:
        conditions.append(basis)
        preserved_fields.append("conditions")
        out["conditions"] = conditions
    # Thresholds already in proposition text are enough; record for diagnostics.
    thr_in_text = _thresholds(blob_before)
    if thresholds & thr_in_text:
        preserved_fields.append("proposition_text_threshold")
    elif thresholds:
        # Surface a compact threshold condition when somehow absent.
        sample = sorted(thresholds, key=len, reverse=True)[0]
        label = f"threshold: {sample}"
        if _norm(label) not in _norm(" ".join(conditions)):
            conditions.append(label)
            out["conditions"] = conditions
            preserved_fields.append("conditions_threshold")
    if not preserved_fields and _content_preserved(
        out, measurement_basis=basis, thresholds=thresholds
    ):
        preserved_fields.append("already_present")
    return out, preserved_fields


def stamp_dependent_qualification_candidate_id(
    row: dict[str, Any],
    *,
    identity: DependentQualificationIdentity | StructuredListIdentityContext,
) -> str:
    existing = str(row.get("_extraction_candidate_id") or "").strip()
    if existing.startswith("extractcand:"):
        return existing
    payload = "\x1f".join(
        (
            str(getattr(identity, "source_record_id", "") or ""),
            str(getattr(identity, "source_snapshot_id", "") or ""),
            str(getattr(identity, "source_fragment_id", "") or ""),
            _norm(str(row.get("source_locator") or "")),
            _norm(str(row.get("proposition_text") or "")),
            _norm(str(row.get("evidence_text") or "")),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    cid = f"extractcand:{digest}"
    row["_extraction_candidate_id"] = cid
    return cid


def _governing_operative_rank(row: Mapping[str, Any]) -> tuple:
    """Operative strength signals used for governor uniqueness (no lexical tie-break)."""
    blob = _row_blob(row)
    has_prohibition = 1 if re.search(r"\bmust\s+not\b|\bshall\s+not\b", blob) else 0
    has_obligation = 1 if re.search(r"\b(must|shall)\b(?!\s+not\b)", blob) else 0
    has_actor = 1 if _ACTOR_CUES.search(blob) else 0
    thr_n = len(_thresholds(blob))
    return (has_prohibition, has_obligation, has_actor, thr_n)


def _governing_tie_break(row: Mapping[str, Any]) -> tuple:
    """Stable lexical order — used only after a unique operative winner exists."""
    return (
        -len(str(row.get("source_locator") or "")),
        _norm(str(row.get("source_locator") or "")),
        _norm(str(row.get("proposition_text") or "")),
        str(row.get("_extraction_candidate_id") or ""),
    )


def reconcile_dependent_qualification_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_text: str,
    identity: DependentQualificationIdentity | StructuredListIdentityContext | None = None,
    source_record_id: str = "",
    source_snapshot_id: str = "",
    source_fragment_id: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Suppress dependent measurement qualifications into a governing operative row.

    Returns ``(retained_rows, diagnostics, decision_facts)``.
    Input order does not affect which row wins; output order follows first-seen
    retained governors then other retained rows in stable candidate-id order.
    """
    ident = identity or DependentQualificationIdentity(
        source_record_id=source_record_id,
        source_snapshot_id=source_snapshot_id,
        source_fragment_id=source_fragment_id,
    )
    # Require complete source identity — never suppress across unknown identity.
    if not (
        str(getattr(ident, "source_record_id", "") or "").strip()
        and str(getattr(ident, "source_snapshot_id", "") or "").strip()
        and str(getattr(ident, "source_fragment_id", "") or "").strip()
    ):
        return [dict(r) for r in rows], [], []

    working: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        stamp_dependent_qualification_candidate_id(item, identity=ident)
        working.append(item)

    # Stable processing order by candidate id (order-independent decisions).
    ordered = sorted(
        working,
        key=lambda r: str(r.get("_extraction_candidate_id") or ""),
    )

    dependents = [r for r in ordered if is_measurement_qualification_row(r)]
    if not dependents:
        return working, [], []

    governors = [
        r
        for r in ordered
        if has_independent_legal_effect(r) and not is_measurement_qualification_row(r)
    ]
    if not governors:
        return working, [], []

    suppressed_ids: set[str] = set()
    retained_by_id: dict[str, dict[str, Any]] = {
        str(r["_extraction_candidate_id"]): dict(r) for r in working
    }
    diags: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []

    for dep in dependents:
        dep_id = str(dep["_extraction_candidate_id"])
        if dep_id in suppressed_ids:
            continue
        dep_thr = _thresholds(_row_blob(dep))
        # Also pull thresholds from potential governors for linkage.
        candidates: list[tuple[tuple, dict[str, Any], str]] = []
        for gov in governors:
            gov_id = str(gov["_extraction_candidate_id"])
            if gov_id == dep_id or gov_id in suppressed_ids:
                continue
            # Live identity: same record/snapshot/fragment (already scoped).
            rel = _evidence_relationship(dep, gov, source_text=source_text)
            if not rel:
                continue
            gov_thr = _thresholds(_row_blob(gov))
            # Prefer governors that share a numeric threshold; allow empty dep thr
            # when measurement refers to "the distance" under a thresholded rule.
            if dep_thr and gov_thr and not (dep_thr & gov_thr):
                continue
            if not gov_thr and not dep_thr:
                continue
            if not gov_thr:
                continue
            candidates.append((_governing_operative_rank(gov), gov, rel))

        if not candidates:
            continue
        # Ambiguity: more than one equally ranked governor → do not silently suppress.
        candidates.sort(
            key=lambda item: (item[0], _governing_tie_break(item[1])),
            reverse=True,
        )
        best_rank = candidates[0][0]
        tied = [c for c in candidates if c[0] == best_rank]
        if len(tied) != 1:
            continue
        _rank, gov, rel = tied[0]
        gov_id = str(gov["_extraction_candidate_id"])
        current_gov = retained_by_id.get(gov_id) or dict(gov)
        basis = _measurement_basis_phrase(dep)
        thr = dep_thr | _thresholds(_row_blob(current_gov))
        enriched, preserved_fields = _ensure_preservation(
            current_gov,
            measurement_basis=basis,
            thresholds=thr,
        )
        if not _content_preserved(
            enriched, measurement_basis=basis, thresholds=_thresholds(_row_blob(current_gov)) | dep_thr
        ):
            # Safety: never suppress if we cannot preserve material content.
            continue
        retained_by_id[gov_id] = enriched
        suppressed_ids.add(dep_id)
        retained_by_id.pop(dep_id, None)

        diags.append(
            {
                "code": DEPENDENT_QUALIFICATION_SUPPRESSED_DIAGNOSTIC,
                "suppressed_candidate_id": dep_id,
                "retained_candidate_id": gov_id,
                "source_fragment_id": str(getattr(ident, "source_fragment_id", "") or ""),
                "evidence_relationship": rel,
                "dependency_basis": "measurement_qualification_of_governing_threshold",
                "preserved_measurement_basis": basis,
                "preserved_thresholds": sorted(thr),
                "preserved_fields": preserved_fields,
                "message": (
                    "Suppressed dependent measurement qualification; "
                    f"retained {gov_id!r} with preserved measurement basis."
                ),
            }
        )
        facts.append(
            {
                "fact_kind": FACT_SUPPRESS_DEPENDENT_QUALIFICATION,
                "suppressed_candidate_id": dep_id,
                "retained_candidate_id": gov_id,
                "source_record_id": str(getattr(ident, "source_record_id", "") or ""),
                "source_snapshot_id": str(getattr(ident, "source_snapshot_id", "") or ""),
                "source_fragment_id": str(getattr(ident, "source_fragment_id", "") or ""),
                "evidence_relationship": rel,
                "dependency_basis": "measurement_qualification_of_governing_threshold",
                "preserved_measurement_basis": basis,
                "preserved_thresholds": sorted(thr),
                "preserved_fields": preserved_fields,
                "suppressed_source_locator": str(dep.get("source_locator") or ""),
                "retained_source_locator": str(enriched.get("source_locator") or ""),
                "outcome": "suppressed_as_dependent_qualification",
            }
        )

    # Emit retained rows in original input order, skipping suppressed ids.
    retained: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in working:
        cid = str(row.get("_extraction_candidate_id") or "")
        if cid in suppressed_ids or cid in seen:
            continue
        seen.add(cid)
        retained.append(retained_by_id.get(cid, row))
    return retained, diags, facts
