"""Deterministic linking of propositions to governed legal scopes (taxonomy-backed)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Literal

from law_proposition_extractor_domain import (
    LegalScope,
    LegalScopeReviewCandidate,
    Proposition,
    PropositionScopeLink,
    SourceRecord,
)

from .intake import content_hash

_SEED_PATH = Path(__file__).resolve().parent / "legal_scopes_seed.json"

EvidenceFieldName = Literal[
    "proposition_text",
    "legal_subject",
    "affected_subjects",
    "required_documents",
    "conditions",
    "proposition_label",
    "source_fragment_text",
    "source_title",
    "source_citation",
    "source_context",
]

FIELD_ORDER: list[EvidenceFieldName] = [
    "proposition_text",
    "legal_subject",
    "affected_subjects",
    "required_documents",
    "conditions",
    "source_fragment_text",
    "source_citation",
    "source_title",
    "proposition_label",
    "source_context",
]

# Max distance between source term match and inferred proposition grounding (chars in normalized haystack).
_NEAR_ANCHOR_CHARS = 250
_EXCERPT_RADIUS = 100


def seed_taxonomy_path() -> Path:
    return _SEED_PATH


def load_seed_legal_scopes(*, path: Path | None = None) -> list[LegalScope]:
    seed_file = path or _SEED_PATH
    raw = json.loads(seed_file.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("legal scope seed must be a JSON array")
    return [LegalScope.model_validate(item) for item in raw]


def register_unknown_scope_review_candidate(
    candidates: list[LegalScopeReviewCandidate],
    *,
    run_id: str,
    suggested_slug: str,
    reason: str,
    evidence: list[str],
    raw_label: str = "",
    source: Literal[
        "external_suggestion",
        "deterministic_unknown_token",
        "llm_suggestion",
        "import",
        "other",
    ] = "other",
    signals: dict[str, Any] | None = None,
) -> LegalScopeReviewCandidate:
    """Record a non-canonical scope suggestion for governance review (does not mutate taxonomy)."""
    rid = f"lscr:{content_hash(f'{run_id}|{suggested_slug}|{reason}')[:16]}"
    cand = LegalScopeReviewCandidate(
        id=rid,
        run_id=run_id,
        suggested_slug=suggested_slug.strip(),
        raw_label=raw_label,
        source=source,
        reason=reason,
        evidence=list(evidence),
        signals=dict(signals or {}),
    )
    candidates.append(cand)
    return cand


def register_scope_link_quality_candidate(
    candidates: list[LegalScopeReviewCandidate],
    *,
    run_id: str,
    proposition_id: str,
    scope_slug: str,
    scope_id: str,
    scope_label: str,
    kind: str,
    detail: str,
    evidence_snippets: list[str],
    related_scope_ids: list[str] | None = None,
) -> LegalScopeReviewCandidate:
    """Record an optional governance review cue for deterministic scope linkage (taxonomy unchanged)."""
    basis = f"{run_id}|{proposition_id}|{scope_id}|{kind}|{'|'.join(related_scope_ids or [])}"
    rid = f"lscr:{content_hash(basis)[:16]}"
    sig: dict[str, Any] = {
        "review_subtype": "scope_link_quality",
        "proposition_id": proposition_id,
        "canonical_scope_id": scope_id,
        "review_kind": kind,
    }
    if related_scope_ids:
        sig["related_scope_ids"] = related_scope_ids
    cand = LegalScopeReviewCandidate(
        id=rid,
        run_id=run_id,
        suggested_slug=scope_slug.strip(),
        raw_label=scope_label,
        source="other",
        reason=detail,
        evidence=list(evidence_snippets),
        signals=sig,
    )
    candidates.append(cand)
    return cand


def _normalize_haystack(text: str) -> str:
    return " ".join(text.lower().split())


def _term_match_span(term: str, haystack: str) -> tuple[int, int] | None:
    """Return (start, end) of first whole-word or phrase match in haystack, or None."""
    t = term.strip().lower()
    if not t:
        return None
    if " " in t:
        parts = re.split(r"\s+", t)
        pattern = r"\s+".join(re.escape(p) for p in parts)
        m = re.search(pattern, haystack, re.IGNORECASE)
    else:
        m = re.search(rf"\b{re.escape(t)}\b", haystack, re.IGNORECASE)
    if m is None:
        return None
    return m.start(), m.end()


def _excerpt(haystack: str, start: int, end: int, *, radius: int = _EXCERPT_RADIUS) -> str:
    lo = max(0, start - radius)
    hi = min(len(haystack), end + radius)
    chunk = haystack[lo:hi].strip()
    if lo > 0:
        chunk = "…" + chunk
    if hi < len(haystack):
        chunk = chunk + "…"
    return chunk


def _ancestor_chain(scope_id: str, by_id: dict[str, LegalScope]) -> list[str]:
    out: list[str] = []
    current = by_id.get(scope_id)
    while current and current.parent_scope_id:
        pid = current.parent_scope_id
        out.append(pid)
        current = by_id.get(pid)
    return out


def _match_terms_for_scope(scope: LegalScope) -> list[str]:
    terms: list[str] = []
    slug_readable = scope.slug.replace("_", " ").strip()
    if slug_readable:
        terms.append(slug_readable)
        terms.extend(slug_readable.split())
    label = scope.label.strip()
    if label:
        terms.append(label.lower())
    terms.extend(s.lower() for s in scope.synonyms if s.strip())
    seen: set[str] = set()
    unique: list[str] = []
    for t in terms:
        tt = t.strip()
        if tt and tt not in seen:
            seen.add(tt)
            unique.append(tt)
    unique.sort(key=len, reverse=True)
    return unique


def _proposition_label_haystack(p: Proposition) -> str:
    parts = [
        p.label,
        p.short_name,
        p.proposition_tier.value,
        p.legal_effect_type.value,
        " ".join(p.tags),
    ]
    return _normalize_haystack(" ".join(parts))


def _structured_field_haystacks(p: Proposition) -> list[tuple[EvidenceFieldName, str]]:
    return [
        ("legal_subject", _normalize_haystack(p.legal_subject)),
        ("affected_subjects", _normalize_haystack(" ".join(p.affected_subjects))),
        ("required_documents", _normalize_haystack(" ".join(p.required_documents))),
        ("conditions", _normalize_haystack(" ".join(p.conditions))),
    ]


def _estimate_anchor_offset(norm_prop: str, norm_auth: str) -> int | None:
    """Locate approximate proposition grounding inside normalized authoritative body."""
    if not norm_prop or not norm_auth:
        return None
    words = [w for w in norm_prop.split() if len(w) >= 5]
    for w in sorted(words, key=len, reverse=True):
        span = _term_match_span(w, norm_auth)
        if span:
            return (span[0] + span[1]) // 2
    stripped = norm_prop.strip()
    for ln in (96, 72, 48, 32, 24, 16, 12):
        if ln > len(stripped):
            continue
        needle = stripped[:ln]
        idx = norm_auth.find(needle)
        if idx >= 0:
            return idx + ln // 2
    pref = stripped[:24] if stripped else ""
    if pref:
        idx2 = norm_auth.find(pref)
        if idx2 >= 0:
            return idx2 + 12
    return None


def _classify_authoritative_match(
    term: str,
    *,
    authoritative_raw: str,
    norm_authoritative: str,
    anchor_override: int | None,
) -> tuple[EvidenceFieldName | None, str, tuple[int, int] | None]:
    """Return authoritative field tier, excerpt, and token span in *norm_authoritative*."""
    _ = authoritative_raw
    span = _term_match_span(term, norm_authoritative)
    if span is None:
        return None, "", None
    excerpt = _excerpt(norm_authoritative, span[0], span[1])

    anch = anchor_override if anchor_override is not None else len(norm_authoritative) // 2
    midpoint = (span[0] + span[1]) / 2.0
    if abs(midpoint - anch) <= _NEAR_ANCHOR_CHARS:
        return "source_fragment_text", excerpt, span
    return "source_context", excerpt, span


@dataclass
class ExplicitHit:
    matched_term: str
    evidence_field: EvidenceFieldName
    relevance: Literal["direct", "indirect", "contextual"]
    link_confidence: Literal["high", "medium", "low"]
    evidence_by_field: dict[str, str] = dc_field(default_factory=dict)
    excerpts: list[str] = dc_field(default_factory=list)
    # Character span (start, end) in the normalized surface where `matched_term` was found,
    # when available (proposition text, label haystack, or authoritative body).
    match_span: tuple[int, int] | None = None


_SPECIES_EXCLUSION_LOOKBACK = 360

_OTHER_SPECIES_CROSS_REF_RE = re.compile(
    r"(?:\bother than those referred to in points\b"
    r"|\bspecies other than those referred to\b"
    r"|\banimal species other than those referred to\b"
    r"|\bspecies other than\b)",
    re.IGNORECASE,
)

_POSITIVE_EQUINE_SUBJECT_RE = re.compile(
    r"\b("
    r"kept animals of the equine species"
    r"|animals of the equine species"
    r"|operators of kept animals of the equine species"
    r"|the equine species"
    r"|equidae"
    r"|\bequus\b"
    r"|\bhorses?\b"
    r")\b",
    re.IGNORECASE,
)

_SPECIES_EXCLUSION_BEFORE_TOKEN_RE = re.compile(
    r"(\bother than\b"
    r"|\bthan those referred to in points\b"
    r"|\b(excluding|with the exception of)\b)",
    re.IGNORECASE,
)


def _normalized_proposition_text(proposition: Proposition) -> str:
    return _normalize_haystack(proposition.proposition_text)


def _positive_equine_subject(norm_prop: str) -> bool:
    """True when the proposition is principally about equidae / kept equine animals."""
    return bool(_POSITIVE_EQUINE_SUBJECT_RE.search(norm_prop))


def _other_species_cross_ref_proposition(norm_prop: str) -> bool:
    """Art 109(1)(e) / (2)-style: obligation or power about *other* species via points (a)–(d)."""
    return bool(_OTHER_SPECIES_CROSS_REF_RE.search(norm_prop))


def _token_in_species_exclusion_phrase(norm_haystack: str, token_start: int) -> bool:
    if token_start < 0:
        return False
    window = norm_haystack[max(0, token_start - _SPECIES_EXCLUSION_LOOKBACK) : token_start]
    return bool(_SPECIES_EXCLUSION_BEFORE_TOKEN_RE.search(window))


def _apply_equine_exclusion_downgrade(
    hit: ExplicitHit,
    *,
    proposition: Proposition,
    norm_authoritative: str,
) -> bool:
    """Downgrade direct/indirect equine hits when the species term is only cross-ref / list context.

    Returns True when relevance/confidence were adjusted.
    """
    norm_prop = _normalized_proposition_text(proposition)
    if _positive_equine_subject(norm_prop):
        return False

    cross_ref = _other_species_cross_ref_proposition(norm_prop)
    span_excl = False
    if hit.match_span is not None:
        start, _end = hit.match_span
        if hit.evidence_field == "proposition_text":
            span_excl = _token_in_species_exclusion_phrase(norm_prop, start)
        elif hit.evidence_field == "proposition_label":
            span_excl = _token_in_species_exclusion_phrase(
                _proposition_label_haystack(proposition), start
            )
        elif hit.evidence_field in ("source_fragment_text", "source_context") and norm_authoritative:
            span_excl = _token_in_species_exclusion_phrase(norm_authoritative, start)

    if not cross_ref and not span_excl:
        return False

    if hit.relevance == "contextual" and hit.link_confidence == "low":
        return False

    hit.relevance = "contextual"
    hit.link_confidence = "medium"
    return True


def _emit_hit_for_evidence_field(
    ev: EvidenceFieldName,
    *,
    excerpt: str,
    matched_term: str,
    extra_excerpts: dict[str, str],
) -> ExplicitHit | None:
    excerpts = [excerpt] if excerpt else []
    excerpts.extend(extra_excerpts.values())
    evidence_by_field = dict(extra_excerpts)
    if excerpt and ev:
        evidence_by_field[ev] = excerpt

    if ev == "proposition_text":
        return ExplicitHit(
            matched_term=matched_term,
            evidence_field=ev,
            relevance="direct",
            link_confidence="high",
            evidence_by_field=evidence_by_field,
            excerpts=excerpts[:4],
        )
    if ev == "proposition_label":
        return ExplicitHit(
            matched_term=matched_term,
            evidence_field=ev,
            relevance="contextual",
            link_confidence="medium",
            evidence_by_field=evidence_by_field,
            excerpts=excerpts[:4],
        )
    if ev in {"legal_subject", "affected_subjects", "required_documents", "conditions"}:
        return ExplicitHit(
            matched_term=matched_term,
            evidence_field=ev,
            relevance="direct",
            link_confidence="high",
            evidence_by_field=evidence_by_field,
            excerpts=excerpts[:4],
        )
    if ev == "source_fragment_text":
        return ExplicitHit(
            matched_term=matched_term,
            evidence_field=ev,
            relevance="direct",
            link_confidence="high",
            evidence_by_field=evidence_by_field,
            excerpts=excerpts[:4],
        )
    if ev == "source_citation":
        return ExplicitHit(
            matched_term=matched_term,
            evidence_field=ev,
            relevance="contextual",
            link_confidence="medium",
            evidence_by_field=evidence_by_field,
            excerpts=excerpts[:4],
        )
    if ev == "source_title":
        return ExplicitHit(
            matched_term=matched_term,
            evidence_field=ev,
            relevance="contextual",
            link_confidence="medium",
            evidence_by_field=evidence_by_field,
            excerpts=excerpts[:4],
        )
    if ev == "source_context":
        return ExplicitHit(
            matched_term=matched_term,
            evidence_field=ev,
            relevance="contextual",
            link_confidence="low",
            evidence_by_field=evidence_by_field,
            excerpts=excerpts[:4],
        )
    return None


def _first_field_hit_for_term(
    term: str,
    *,
    proposition: Proposition,
    norm_prop_text: str,
    norm_label: str,
    norm_title: str,
    norm_citation: str,
    authoritative: str,
    norm_auth: str,
    anchor: int | None,
) -> ExplicitHit | None:
    """Strongest matching evidence field for this synonym term."""
    span = _term_match_span(term, norm_prop_text)
    if span:
        ex = _excerpt(norm_prop_text, span[0], span[1])
        hit = _emit_hit_for_evidence_field(
            "proposition_text", excerpt=ex, matched_term=term, extra_excerpts={}
        )
        if hit:
            hit.match_span = span
        return hit

    for field_name, field_haystack in _structured_field_haystacks(proposition):
        span = _term_match_span(term, field_haystack)
        if not span:
            continue
        ex = _excerpt(field_haystack, span[0], span[1])
        hit = _emit_hit_for_evidence_field(
            field_name, excerpt=ex, matched_term=term, extra_excerpts={}
        )
        if hit:
            hit.match_span = span
        return hit

    if norm_auth:
        auth_field, ex, auth_span = _classify_authoritative_match(
            term,
            authoritative_raw=authoritative,
            norm_authoritative=norm_auth,
            anchor_override=anchor,
        )
        if auth_field is not None and ex:
            auth_hit = _emit_hit_for_evidence_field(
                auth_field, excerpt=ex, matched_term=term, extra_excerpts={}
            )
            if auth_hit:
                if auth_span is not None:
                    auth_hit.match_span = auth_span
                return auth_hit

    span = _term_match_span(term, norm_citation)
    if span:
        ex = _excerpt(norm_citation, span[0], span[1])
        return _emit_hit_for_evidence_field(
            "source_citation", excerpt=ex, matched_term=term, extra_excerpts={}
        )

    span = _term_match_span(term, norm_title)
    if span:
        ex = _excerpt(norm_title, span[0], span[1])
        return _emit_hit_for_evidence_field(
            "source_title", excerpt=ex, matched_term=term, extra_excerpts={}
        )

    span = _term_match_span(term, norm_label)
    if span:
        ex = _excerpt(norm_label, span[0], span[1])
        hit = _emit_hit_for_evidence_field(
            "proposition_label", excerpt=ex, matched_term=term, extra_excerpts={}
        )
        if hit:
            hit.match_span = span
        return hit

    return None


def _find_best_hit_for_scope(
    scope: LegalScope,
    terms: list[str],
    *,
    proposition: Proposition,
    source: SourceRecord | None,
) -> ExplicitHit | None:
    _ = scope
    norm_prop_text = _normalize_haystack(proposition.proposition_text)
    norm_label = _proposition_label_haystack(proposition)
    norm_title = _normalize_haystack(source.title) if source else ""
    norm_citation = _normalize_haystack(source.citation) if source else ""
    authoritative = source.authoritative_text if source else ""
    norm_auth = _normalize_haystack(authoritative[:8000])
    anchor = _estimate_anchor_offset(norm_prop_text, norm_auth) if norm_auth else None

    best: tuple[int, ExplicitHit] | None = None

    for term in terms:
        hit = _first_field_hit_for_term(
            term,
            proposition=proposition,
            norm_prop_text=norm_prop_text,
            norm_label=norm_label,
            norm_title=norm_title,
            norm_citation=norm_citation,
            authoritative=authoritative,
            norm_auth=norm_auth,
            anchor=anchor,
        )
        if not hit:
            continue
        rank = FIELD_ORDER.index(hit.evidence_field)
        if best is None or rank < best[0]:
            best = (rank, hit)
        if rank == 0:
            break

    return best[1] if best else None


def _link_id(proposition_id: str, scope_id: str, inheritance: str, suffix: str) -> str:
    basis = f"{proposition_id}|{scope_id}|{inheritance}|{suffix}"
    return f"psl:{content_hash(basis)[:16]}"


@dataclass(frozen=True)
class ScopeArtifacts:
    legal_scopes: list[LegalScope]
    proposition_scope_links: list[PropositionScopeLink]
    scope_inventory: dict[str, Any]
    scope_review_candidates: list[LegalScopeReviewCandidate]


def build_scope_artifacts_for_run(
    *,
    run_id: str,
    propositions: list[Proposition],
    sources: list[SourceRecord],
    seed_path: Path | None = None,
) -> ScopeArtifacts:
    """Match proposition + source facets against seed synonyms with field-aware determinism."""
    legal_scopes = load_seed_legal_scopes(path=seed_path)
    by_id = {s.id: s for s in legal_scopes}
    slug_by_id = {s.id: s.slug for s in legal_scopes}
    label_by_id = {s.id: s.label for s in legal_scopes}
    scope_terms: dict[str, list[str]] = {
        scope.id: _match_terms_for_scope(scope) for scope in legal_scopes
    }
    source_by_id = {s.id: s for s in sources}
    candidates: list[LegalScopeReviewCandidate] = []

    links: list[PropositionScopeLink] = []

    scored = sorted(
        legal_scopes,
        key=lambda s: max((len(t) for t in scope_terms[s.id]), default=0),
        reverse=True,
    )

    for proposition in propositions:
        src_rec = source_by_id.get(proposition.source_record_id)
        matched_explicit: set[str] = set()
        hits_by_scope: dict[str, ExplicitHit] = {}

        for scope in scored:
            if scope.status != "active":
                continue
            hit = _find_best_hit_for_scope(
                scope,
                scope_terms[scope.id],
                proposition=proposition,
                source=src_rec,
            )
            if not hit:
                continue
            if scope.id in matched_explicit:
                continue
            matched_explicit.add(scope.id)
            hits_by_scope[scope.id] = hit

        # Post-process sibling species ambiguity (explicit species-level hits).
        explicit_species_scopes = [
            sid
            for sid in matched_explicit
            if by_id[sid].scope_type == "species" and by_id[sid].parent_scope_id
        ]
        by_parent: dict[str, list[str]] = {}
        for sid in explicit_species_scopes:
            pid = by_id[sid].parent_scope_id or ""
            if pid:
                by_parent.setdefault(pid, []).append(sid)
        for _parent_id, grp in by_parent.items():
            if len(grp) >= 2:
                register_scope_link_quality_candidate(
                    candidates,
                    run_id=run_id,
                    proposition_id=proposition.id,
                    scope_slug=slug_by_id[grp[0]],
                    scope_id=grp[0],
                    scope_label=label_by_id[grp[0]],
                    kind="sibling_species_ambiguity",
                    detail=(
                        "Multiple sibling species scopes matched deterministically "
                        "for the same proposition; reconcile applicability: " + repr(sorted(grp))
                    ),
                    evidence_snippets=[
                        hits_by_scope[s].excerpts[0] for s in grp if hits_by_scope[s].excerpts
                    ],
                    related_scope_ids=sorted(grp),
                )

        for sid in matched_explicit:
            hh = hits_by_scope[sid]
            norm_auth_body = ""
            if src_rec and src_rec.authoritative_text:
                norm_auth_body = _normalize_haystack(str(src_rec.authoritative_text)[:8000])
            exclusion_downgrade = False
            cross_ref_excl_note = False
            if sid == "equine":
                np = _normalized_proposition_text(proposition)
                cross_ref_excl_note = _other_species_cross_ref_proposition(np) and not _positive_equine_subject(np)
                exclusion_downgrade = _apply_equine_exclusion_downgrade(
                    hh,
                    proposition=proposition,
                    norm_authoritative=norm_auth_body,
                )
            # Weak-only evidence ⇒ optional review cue
            if hh.evidence_field == "source_context" and hh.link_confidence == "low":
                register_scope_link_quality_candidate(
                    candidates,
                    run_id=run_id,
                    proposition_id=proposition.id,
                    scope_slug=slug_by_id[sid],
                    scope_id=sid,
                    scope_label=label_by_id[sid],
                    kind="weak_source_context_only",
                    detail="Scope match relied only on broad source body context (low confidence).",
                    evidence_snippets=list(hh.excerpts[:2]),
                )

            sig: dict[str, Any] = {
                "matched_term": hh.matched_term,
                "evidence_field": hh.evidence_field,
                "evidence_by_field": {k: v for k, v in hh.evidence_by_field.items()},
            }
            if exclusion_downgrade or cross_ref_excl_note:
                sig["species_exclusion_context"] = True
            evidence_list = list(hh.excerpts[:3])
            if hh.evidence_by_field:
                for k in (
                    "proposition_text",
                    "legal_subject",
                    "affected_subjects",
                    "required_documents",
                    "conditions",
                    "proposition_label",
                    "source_fragment_text",
                    "source_title",
                    "source_citation",
                    "source_context",
                ):
                    excerpt_v = (hh.evidence_by_field.get(k) or "")[:400]
                    if excerpt_v:
                        sig.setdefault("evidence_excerpts_detail", {})
                        sig["evidence_excerpts_detail"][k] = excerpt_v[:240]

            reason = (
                f"Matched term {hh.matched_term!r} in {hh.evidence_field} "
                f"({hh.relevance} applicability, classifier confidence tier)."
            )
            if exclusion_downgrade:
                reason += (
                    " Downranked: equine token appears only as a species exclusion list, "
                    "cross-reference to listed points, or otherwise not as the direct legal subject."
                )
            elif cross_ref_excl_note:
                reason += (
                    " Cross-reference/other-species obligation: equine appears only as a listed "
                    "point of comparison, not as the proposition's direct legal subject."
                )

            links.append(
                PropositionScopeLink(
                    id=_link_id(proposition.id, sid, "explicit", hh.matched_term),
                    proposition_id=proposition.id,
                    proposition_key=proposition.proposition_key,
                    scope_id=sid,
                    relevance=hh.relevance,
                    inheritance="explicit",
                    confidence=hh.link_confidence,
                    method="deterministic",
                    reason=reason,
                    evidence=evidence_list,
                    signals=sig,
                )
            )

        inherited_pairs: set[tuple[str, str]] = set()

        for narrow_id in list(matched_explicit):
            hh_n = hits_by_scope.get(narrow_id)
            for ancestor_id in _ancestor_chain(narrow_id, by_id):
                if ancestor_id in matched_explicit:
                    continue
                pair_key = (proposition.id, ancestor_id)
                if pair_key in inherited_pairs:
                    continue
                inherited_pairs.add(pair_key)

                child_was_weak = hh_n is not None and hh_n.link_confidence == "low"

                inh_confidence: Literal["high", "medium", "low"] = (
                    "low" if child_was_weak else "medium"
                )
                inh_relevance: Literal["direct", "indirect", "contextual"] = "contextual"

                sig_inf: dict[str, Any] = {
                    "narrower_scope_id": narrow_id,
                    "narrower_evidence_field": hh_n.evidence_field if hh_n else None,
                    "narrower_confidence": hh_n.link_confidence if hh_n else None,
                    "inheritance_basis": "taxonomy_ancestor",
                }

                if child_was_weak:
                    register_scope_link_quality_candidate(
                        candidates,
                        run_id=run_id,
                        proposition_id=proposition.id,
                        scope_slug=slug_by_id[ancestor_id],
                        scope_id=ancestor_id,
                        scope_label=label_by_id[ancestor_id],
                        kind="inherited_from_weak_child",
                        detail=(
                            "Ancestor scope link is inherited from a low-confidence or "
                            f"contextual-only child match ({narrow_id!r})."
                        ),
                        evidence_snippets=[f"narrower_scope:{narrow_id}"],
                        related_scope_ids=[narrow_id, ancestor_id],
                    )

                links.append(
                    PropositionScopeLink(
                        id=_link_id(proposition.id, ancestor_id, "inherited", narrow_id),
                        proposition_id=proposition.id,
                        proposition_key=proposition.proposition_key,
                        scope_id=ancestor_id,
                        relevance=inh_relevance,
                        inheritance="inherited",
                        confidence=inh_confidence,
                        method="deterministic",
                        reason=(
                            "Taxonomy ancestor inherited from narrower matched scope "
                            f"{narrow_id!r} for browsing context."
                        ),
                        evidence=[f"narrower_scope:{narrow_id}"],
                        signals=sig_inf,
                    )
                )

    inventory = _build_scope_inventory(
        legal_scopes=legal_scopes,
        proposition_scope_links=links,
        run_id=run_id,
    )

    return ScopeArtifacts(
        legal_scopes=legal_scopes,
        proposition_scope_links=links,
        scope_inventory=inventory,
        scope_review_candidates=candidates,
    )


def _build_scope_inventory(
    *,
    legal_scopes: list[LegalScope],
    proposition_scope_links: list[PropositionScopeLink],
    run_id: str,
) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for s in legal_scopes:
        by_type[s.scope_type] = by_type.get(s.scope_type, 0) + 1

    rel_counts: dict[str, int] = {}
    inh_counts: dict[str, int] = {}
    explicit_n = 0
    inherited_n = 0
    for link in proposition_scope_links:
        rel_counts[link.relevance] = rel_counts.get(link.relevance, 0) + 1
        inh_counts[link.inheritance] = inh_counts.get(link.inheritance, 0) + 1
        if link.inheritance == "explicit":
            explicit_n += 1
        if link.inheritance == "inherited":
            inherited_n += 1

    scope_hit_counts: dict[str, int] = {}
    for link in proposition_scope_links:
        scope_hit_counts[link.scope_id] = scope_hit_counts.get(link.scope_id, 0) + 1

    return {
        "inventory_version": "0.1",
        "run_id": run_id,
        "taxonomy_seed_version": "law-proposition-extractor.v1",
        "scope_count": len(legal_scopes),
        "scope_counts_by_type": by_type,
        "proposition_scope_link_count": len(proposition_scope_links),
        "explicit_link_count": explicit_n,
        "inherited_link_count": inherited_n,
        "link_counts_by_relevance": rel_counts,
        "link_counts_by_inheritance": inh_counts,
        "link_counts_by_scope_id": scope_hit_counts,
    }
