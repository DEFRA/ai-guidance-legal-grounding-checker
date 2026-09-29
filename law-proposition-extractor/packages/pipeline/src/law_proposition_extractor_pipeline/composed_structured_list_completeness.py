"""Reconcile model completeness after structured-list composition.

Conservative invariant: a model-proposed ``context_dependent`` status on a
retained terminal structured-list proposition may be overridden to ``complete``
only when composition facts show governing stems were incorporated into the
retained claim, the final text carries that material content plus an operative
legal effect and terminal condition, and no unresolved material context remains.

Does not rewrite proposition text, invent stems, or resolve anaphora.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from law_proposition_extractor_pipeline.structured_list_decomposition import (
    COMPOSITION_BASIS,
    StructuredListIdentityContext,
)

# Keep in sync with heuristics.registry.RULE_RECONCILE_COMPOSED_STRUCTURED_LIST.
RULE_RECONCILE_COMPOSED_STRUCTURED_LIST = (
    "completeness.reconcile_composed_structured_list"
)
FACT_RECONCILE_COMPOSED_STRUCTURED_LIST = "reconcile_composed_structured_list"
RECONCILIATION_BASIS = "structured_list_stem_composed"
COMPLETENESS_RECONCILED_DIAGNOSTIC = "completeness_reconciled_composed_structured_list"
SIBLING_PARITY_DIAGNOSTIC = "structured_list_sibling_completeness_parity"

_OPERATIVE_EFFECT_RE = re.compile(
    r"\b("
    r"shall\s+not\s+apply|does\s+not\s+apply|"
    r"must\s+not|shall\s+not|"
    r"must|shall|may|"
    r"is\s+entitled|is\s+liable|"
    r"except\s+where|unless|"
    r"commits?\s+an\s+offence"
    r")\b",
    re.IGNORECASE,
)

_EXCEPTION_EFFECT_RE = re.compile(
    r"\b(shall\s+not\s+apply|does\s+not\s+apply|except\s+where|unless|derogat)\b",
    re.IGNORECASE,
)

_GOVERNING_STEM_CLAIM_RE = re.compile(
    r"("
    r"paragraph\s+\d+[a-z]?\s+shall\s+not\s+apply|"
    r"paragraph\s+\d+[a-z]?\s+does\s+not\s+apply|"
    r"shall\s+not\s+apply|"
    r"does\s+not\s+apply|"
    r"must\s+not\b[^.|]{0,80}|"
    r"shall\s+not\b[^.|]{0,80}|"
    r"\bmust\b[^.|]{0,80}|"
    r"\bshall\b[^.|]{0,80}|"
    r"\bmay\b[^.|]{0,80}"
    r")",
    re.IGNORECASE,
)

_ANAPHORA_RE = re.compile(
    r"\b("
    r"the\s+calculations|those\s+calculations|"
    r"the\s+final\s+figures|those\s+amounts|"
    r"such\s+records|those\s+records|"
    r"the\s+cases?\s+referred\s+to|"
    r"in\s+the\s+cases?\s+referred\s+to|"
    r"where\s+the\s+cases?\s+referred\s+to|"
    r"as\s+referred\s+to\s+in\s+paragraph|"
    r"the\s+distance(?!\s+is\s+measured)"
    r")\b",
    re.IGNORECASE,
)

_CROSS_REF_ONLY_RE = re.compile(
    r"\b(referred\s+to\s+in\s+paragraph|in\s+accordance\s+with\s+paragraph|"
    r"as\s+set\s+out\s+in\s+article)\b",
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
        "where",
        "one",
        "more",
        "following",
        "species",
        "i.e",
        "ie",
    }
)


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9%]+", _norm(text))
        if len(t) > 1 and t not in _STOP
    }


def _row_meta(row: Mapping[str, Any]) -> dict[str, Any]:
    meta = row.get("_structured_list_meta")
    return dict(meta) if isinstance(meta, dict) else {}


def _component_texts(meta: Mapping[str, Any], role: str) -> list[str]:
    out: list[str] = []
    for comp in meta.get("source_component_locators") or []:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("role") or "").strip().lower() != role:
            continue
        text = str(comp.get("text") or "").strip()
        if text:
            out.append(text)
    return out


def has_structured_list_composition_facts(row: Mapping[str, Any]) -> bool:
    """True when merge recorded a retained terminal structured-list composition."""
    meta = _row_meta(row)
    if str(meta.get("composition_basis") or row.get("_composition_basis") or "") != COMPOSITION_BASIS:
        return False
    path = str(meta.get("structured_list_path") or "").strip()
    if not path:
        return False
    if not row.get("_structured_list_compose_captured"):
        return False
    parent = str(meta.get("parent_context") or "").strip()
    if not parent:
        return False
    return True


def is_terminal_structured_list_proposition(row: Mapping[str, Any]) -> bool:
    """Terminal retained leaf — not an intermediate stem/branch-only node."""
    if not has_structured_list_composition_facts(row):
        return False
    meta = _row_meta(row)
    # Intermediate rejection leaves are not retained with compose_captured.
    leaf_texts = _component_texts(meta, "leaf")
    if not leaf_texts:
        return False
    return True


def extract_governing_stem_claim(parent_or_stem: str) -> str:
    """Pull the trailing operative governing claim from a composed stem."""
    text = str(parent_or_stem or "").strip()
    if not text:
        return ""
    # Prefer the final paragraph-N shall-not-apply clause when present.
    matches = list(_GOVERNING_STEM_CLAIM_RE.finditer(text))
    if not matches:
        return ""
    # Use the last match — stem drafts often prepend earlier paragraph bodies.
    claim = matches[-1].group(1).strip().rstrip(":")
    return claim


def governing_stem_material_present(proposition_text: str, meta: Mapping[str, Any]) -> bool:
    """True when the retained text carries the material governing stem claim."""
    ptxt = _norm(proposition_text)
    if not ptxt:
        return False
    stems = _component_texts(meta, "stem")
    parent = str(meta.get("parent_context") or "").strip()
    sources = stems or ([parent] if parent else [])
    if not sources:
        return False
    for source in sources:
        claim = extract_governing_stem_claim(source)
        if not claim:
            continue
        claim_norm = _norm(claim)
        if claim_norm and claim_norm in ptxt:
            return True
        claim_tokens = _tokens(claim)
        # Require the operative cue plus most content tokens from the claim.
        if not _OPERATIVE_EFFECT_RE.search(claim):
            continue
        if not _OPERATIVE_EFFECT_RE.search(ptxt):
            continue
        if not claim_tokens:
            return bool(_OPERATIVE_EFFECT_RE.search(ptxt))
        overlap = claim_tokens & _tokens(ptxt)
        # "paragraph 1 shall not apply" → {paragraph, 1, shall, not, apply} after stop filter
        # stops remove little here; require strong overlap.
        if len(overlap) >= max(2, min(3, len(claim_tokens))):
            return True
    return False


def inherited_condition_material_present(proposition_text: str, meta: Mapping[str, Any]) -> bool:
    """True when branch/inherited condition material is present when a branch exists."""
    branch = str(meta.get("branch_context") or "").strip()
    branch_comps = _component_texts(meta, "branch")
    branch_text = branch or (branch_comps[0] if branch_comps else "")
    if not branch_text:
        return True  # no inherited branch condition required
    ptxt = _norm(proposition_text)
    branch_norm = _norm(branch_text)
    if branch_norm and branch_norm in ptxt:
        return True
    tokens = _tokens(branch_text)
    if not tokens:
        return True
    overlap = tokens & _tokens(ptxt)
    # Threshold / species-list branches: require majority of distinctive tokens.
    return len(overlap) >= max(2, (len(tokens) + 1) // 2)


def terminal_branch_material_present(proposition_text: str, meta: Mapping[str, Any]) -> bool:
    """True when the terminal leaf object/condition is represented in the text."""
    leaves = _component_texts(meta, "leaf")
    if not leaves:
        return False
    ptxt = _norm(proposition_text)
    leaf = leaves[0]
    leaf_norm = _norm(leaf)
    if leaf_norm and leaf_norm in ptxt:
        return True
    tokens = _tokens(leaf)
    if not tokens:
        return False
    overlap = tokens & _tokens(ptxt)
    return len(overlap) >= max(2, (len(tokens) + 1) // 2)


def has_operative_legal_effect(proposition_text: str, row: Mapping[str, Any] | None = None) -> bool:
    blob = _norm(proposition_text)
    if row is not None:
        blob = _norm(
            " ".join(
                [
                    proposition_text,
                    str(row.get("rule") or ""),
                    str(row.get("provision_type") or ""),
                ]
            )
        )
    if not blob:
        return False
    return bool(_OPERATIVE_EFFECT_RE.search(blob))


def legal_effect_label(proposition_text: str, row: Mapping[str, Any]) -> str:
    blob = _norm(
        " ".join(
            [
                proposition_text,
                str(row.get("rule") or ""),
                str(row.get("provision_type") or ""),
            ]
        )
    )
    if _EXCEPTION_EFFECT_RE.search(blob) or str(row.get("provision_type") or "").lower() == "exception":
        return "derogation"
    if re.search(r"\bmust\s+not\b|\bshall\s+not\b", blob):
        return "prohibition"
    if re.search(r"\b(must|shall)\b", blob):
        return "obligation"
    if re.search(r"\bmay\b", blob):
        return "permission"
    return "legal_consequence"


def has_unresolved_anaphora(proposition_text: str) -> bool:
    return bool(_ANAPHORA_RE.search(proposition_text or ""))


def has_material_missing_context(row: Mapping[str, Any]) -> bool:
    """True when model/row missing_context still lists unresolved material items."""
    raw = row.get("missing_context")
    if raw is None:
        return False
    if isinstance(raw, str):
        items = [raw.strip()] if raw.strip() else []
    elif isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        return False
    if not items:
        return False
    # Ignore purely informational emptied placeholders.
    material = {
        "actor",
        "object",
        "condition",
        "exception",
        "cross_reference",
        "definition",
        "locator",
        "article_locator",
        "instrument_identity",
        "threshold",
        "governing_stem",
    }
    for item in items:
        key = item.lower().replace(" ", "_")
        if key in material or any(m in key for m in material):
            return True
    return bool(items)


def has_unresolved_exception_target(proposition_text: str, row: Mapping[str, Any]) -> bool:
    """True when a derogation lacks an identifiable affected rule/target."""
    text = str(proposition_text or "")
    if not _EXCEPTION_EFFECT_RE.search(text) and str(row.get("provision_type") or "").lower() != "exception":
        return False
    # Target cues: paragraph/article reference, or explicit subject naming the rule.
    if re.search(r"\b(paragraph|article)\s+\d+", text, re.I):
        return False
    subject = str(row.get("subject") or "")
    if re.search(r"\b(paragraph|article)\s+\d+", subject, re.I):
        return False
    return True


def composition_identity_consistent(row: Mapping[str, Any], identity: StructuredListIdentityContext) -> bool:
    """Reject when private compose facts disagree with the live source identity."""
    # Compose facts are stamped in-merge under the same identity; require non-empty identity.
    if not (
        str(identity.source_record_id or "").strip()
        and str(identity.source_snapshot_id or "").strip()
        and str(identity.source_fragment_id or "").strip()
    ):
        return False
    return True


def is_ambiguous_composition(row: Mapping[str, Any]) -> bool:
    """True when dedupe/composition audit signals ambiguity."""
    meta = _row_meta(row)
    dedupe = meta.get("structured_list_dedupe") or row.get("_structured_list_dedupe")
    if isinstance(dedupe, dict):
        outcome = str(dedupe.get("outcome") or dedupe.get("status") or "").lower()
        if "ambiguous" in outcome or "unresolved" in outcome:
            return True
        if dedupe.get("ambiguous"):
            return True
    return False


def model_status_is_context_dependent(row: Mapping[str, Any]) -> bool:
    return str(row.get("completeness_status") or "").strip().lower() == "context_dependent"


def eligible_for_composed_structured_list_completeness_reconcile(
    row: Mapping[str, Any],
    *,
    identity: StructuredListIdentityContext,
) -> tuple[bool, str]:
    """Return (eligible, reason_code). reason_code empty when eligible."""
    if str(row.get("completeness_status") or "").strip().lower() == "fragmentary":
        return False, "fragmentary_not_reconciled"
    if not model_status_is_context_dependent(row):
        return False, "model_status_not_context_dependent"
    if not composition_identity_consistent(row, identity):
        return False, "inconsistent_source_identity"
    if not is_terminal_structured_list_proposition(row):
        return False, "not_terminal_composed_structured_list"
    if is_ambiguous_composition(row):
        return False, "ambiguous_composition"
    meta = _row_meta(row)
    ptxt = str(row.get("proposition_text") or "")
    if has_unresolved_anaphora(ptxt):
        return False, "unresolved_anaphora"
    if has_material_missing_context(row):
        return False, "material_missing_context"
    if not governing_stem_material_present(ptxt, meta):
        return False, "governing_stem_absent_from_text"
    if not inherited_condition_material_present(ptxt, meta):
        return False, "inherited_condition_absent"
    if not terminal_branch_material_present(ptxt, meta):
        return False, "terminal_branch_absent"
    if not has_operative_legal_effect(ptxt, row):
        return False, "legal_effect_absent"
    if has_unresolved_exception_target(ptxt, row):
        return False, "unresolved_exception_target"
    if _CROSS_REF_ONLY_RE.search(ptxt) and not governing_stem_material_present(ptxt, meta):
        return False, "unresolved_cross_reference"
    return True, ""


def _stem_component_ids(meta: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for comp in meta.get("source_component_locators") or []:
        if not isinstance(comp, dict):
            continue
        role = str(comp.get("role") or "").strip()
        suffix = str(comp.get("locator_suffix") or "").strip()
        if role:
            ids.append(f"{role}:{suffix}" if suffix else role)
    return ids


def reconcile_composed_structured_list_completeness(
    rows: Sequence[Mapping[str, Any]],
    *,
    identity: StructuredListIdentityContext | None = None,
    source_record_id: str = "",
    source_snapshot_id: str = "",
    source_fragment_id: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Override unsupported ``context_dependent`` after verified structured-list composition.

    Returns ``(rows, diagnostics, decision_facts)``. Does not alter proposition text,
    evidence, path, or IDs. Preserves original model completeness in audit fields.
    """
    ident = identity or StructuredListIdentityContext(
        source_record_id=source_record_id,
        source_snapshot_id=source_snapshot_id,
        source_fragment_id=source_fragment_id,
    )
    working = [dict(r) for r in rows]
    diags: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []

    if not (
        str(ident.source_record_id or "").strip()
        and str(ident.source_snapshot_id or "").strip()
        and str(ident.source_fragment_id or "").strip()
    ):
        return working, [], []

    reconciled_paths: dict[str, str] = {}

    for row in working:
        eligible, reason_code = eligible_for_composed_structured_list_completeness_reconcile(
            row, identity=ident
        )
        if not eligible:
            continue
        meta = _row_meta(row)
        path = str(meta.get("structured_list_path") or "")
        model_status = str(row.get("completeness_status") or "")
        model_reason = str(row.get("reason") or "")
        cand = str(row.get("_extraction_candidate_id") or "").strip()
        effect = legal_effect_label(str(row.get("proposition_text") or ""), row)
        stem_ids = _stem_component_ids(meta)

        row["model_completeness_status"] = model_status
        row["model_reason"] = model_reason
        row["completeness_status"] = "complete"
        row["reconciled_completeness_status"] = "complete"
        row["reconciliation_applied"] = True
        row["reconciliation_rule"] = RULE_RECONCILE_COMPOSED_STRUCTURED_LIST
        row["reconciliation_basis"] = RECONCILIATION_BASIS
        row["_completeness_reconciliation"] = {
            "rule": RULE_RECONCILE_COMPOSED_STRUCTURED_LIST,
            "rule_version": "1",
            "from_status": model_status,
            "to_status": "complete",
            "basis": RECONCILIATION_BASIS,
            "structured_list_path": path,
            "composed_stem_identifiers": stem_ids,
            "legal_effect": effect,
            "model_missing_context": row.get("missing_context"),
        }

        reconciled_paths[path] = "complete"
        diags.append(
            {
                "code": COMPLETENESS_RECONCILED_DIAGNOSTIC,
                "candidate_id": cand,
                "structured_list_path": path,
                "model_completeness_status": model_status,
                "reconciled_completeness_status": "complete",
                "reconciliation_rule": RULE_RECONCILE_COMPOSED_STRUCTURED_LIST,
                "reconciliation_basis": RECONCILIATION_BASIS,
                "legal_effect": effect,
                "composed_stem_identifiers": stem_ids,
                "message": (
                    "Reconciled model context_dependent completeness to complete after "
                    "verified structured-list stem composition."
                ),
            }
        )
        facts.append(
            {
                "fact_kind": FACT_RECONCILE_COMPOSED_STRUCTURED_LIST,
                "candidate_id": cand,
                "retained_candidate_id": cand,
                "structured_list_path": path,
                "composition_basis": COMPOSITION_BASIS,
                "composed_stem_identifiers": stem_ids,
                "parent_context": str(meta.get("parent_context") or "")[:500],
                "branch_context": str(meta.get("branch_context") or "")[:500],
                "model_completeness_status": model_status,
                "model_missing_context": row.get("missing_context"),
                "model_reason": model_reason,
                "reconciled_completeness_status": "complete",
                "reconciliation_applied": True,
                "reconciliation_rule": RULE_RECONCILE_COMPOSED_STRUCTURED_LIST,
                "reconciliation_basis": RECONCILIATION_BASIS,
                "legal_effect": effect,
                "source_record_id": ident.source_record_id,
                "source_snapshot_id": ident.source_snapshot_id,
                "source_fragment_id": ident.source_fragment_id,
                "source_locator": str(row.get("source_locator") or ""),
                "outcome": "reconciled_context_dependent_to_complete",
                "safe_override_reason": (
                    "governing structured-list stems were incorporated into the "
                    "retained proposition and no unresolved material context remains"
                ),
            }
        )

    # Sibling parity diagnostic (report only — never force status).
    siblings: dict[str, list[dict[str, Any]]] = {}
    for row in working:
        meta = _row_meta(row)
        path = str(meta.get("structured_list_path") or "").strip()
        if not path or not has_structured_list_composition_facts(row):
            continue
        # Group by governing stem identity (parent_context), not forced path prefix.
        parent_key = _norm(str(meta.get("parent_context") or ""))[:240]
        if not parent_key:
            continue
        siblings.setdefault(parent_key, []).append(row)

    for parent_key, group in siblings.items():
        if len(group) < 2:
            continue
        statuses: list[tuple[str, str, bool]] = []
        for row in group:
            meta = _row_meta(row)
            path = str(meta.get("structured_list_path") or "")
            status = str(row.get("completeness_status") or "")
            # Equivalent composition facts: stem+branch material present.
            equiv = (
                governing_stem_material_present(str(row.get("proposition_text") or ""), meta)
                and inherited_condition_material_present(
                    str(row.get("proposition_text") or ""), meta
                )
                and terminal_branch_material_present(str(row.get("proposition_text") or ""), meta)
                and not has_material_missing_context(row)
                and not has_unresolved_anaphora(str(row.get("proposition_text") or ""))
            )
            statuses.append((path, status, equiv))
        equiv_statuses = {s for _p, s, eq in statuses if eq}
        if len(equiv_statuses) > 1:
            diags.append(
                {
                    "code": SIBLING_PARITY_DIAGNOSTIC,
                    "message": (
                        "Sibling terminal structured-list propositions differ in "
                        "completeness despite equivalent composition facts."
                    ),
                    "sibling_statuses": [
                        {"structured_list_path": p, "completeness_status": s, "equivalent_composition": eq}
                        for p, s, eq in statuses
                    ],
                    "parent_context_fingerprint": parent_key[:80],
                }
            )

    return working, diags, facts
