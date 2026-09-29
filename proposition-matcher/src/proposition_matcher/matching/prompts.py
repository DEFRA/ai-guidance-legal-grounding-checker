"""Prompt construction for the group-rerank matcher and summarisation.

Single source of truth for prompt text, built here and consumed by the batch
matching runner (`proposition-matcher.pipeline.batch_match`).

The matcher is *group-rerank*: a retrieval step surfaces a small survivor set of
candidate law propositions, then a SINGLE LLM call sees the guidance proposition
alongside all survivors and labels each one. This lets the model compare
candidates against each other and decline to anchor when nothing fits — the
failure mode that killed the older per-pair classifier.
"""

from __future__ import annotations

import json
from typing import Any

from .models import RELATIONSHIP_TYPES

SUMMARISE_SYSTEM = "You summarise legal compliance analysis concisely and clearly."

# The group-rerank user prompt carries the full instructions, so the system
# prompt only needs to set the role.
GROUP_RERANK_SYSTEM = (
    "You check whether GOV.UK guidance accurately reflects UK legal propositions, "
    "in precise, audit-friendly language."
)

# Useful labels first, UNGROUNDED last. A stable sort on this keeps the LLM's own
# within-bucket ordering while pushing UNGROUNDED matches (kept for audit) down.
LABEL_PRIORITY = {
    "GROUNDED": 0,
    "GUIDANCE_BROADER": 1,
    "CONFLICTS": 2,
    "GUIDANCE_INCOMPLETE": 3,
    "GUIDANCE_MISSING": 4,
    "UNGROUNDED": 5,
}


def law_citation(law: Any) -> str:
    """Human-readable citation for a proposition or Proposition Matcher law-candidate payload."""
    if isinstance(law, dict):
        presentation = law.get("presentation")
        if isinstance(presentation, dict):
            label = str(presentation.get("locator_label") or "").strip()
            if label:
                return label
        evidence = law.get("evidence")
        if isinstance(evidence, dict):
            locs = evidence.get("fragment_locators") or []
            if isinstance(locs, list):
                for loc in locs:
                    text = str(loc or "").strip()
                    if text:
                        return text
        return law.get("article_reference") or law.get("fragment_locator") or "—"
    citation = getattr(law, "citation", None)
    if citation:
        return citation
    return getattr(law, "article_reference", None) or getattr(law, "fragment_locator", None) or "—"


def _law_text_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("proposition_text") or payload.get("statement_text") or "")


GROUP_RERANK_PROMPT = """You are checking whether GOV.UK guidance accurately reflects UK legal propositions.

A retrieval step has surfaced the candidate law propositions below. They may not all be the right basis. Be willing to mark several as UNGROUNDED and anchor the guidance on at most one or two of them.

The guidance line is prefixed with `[regulatory_kind: <Z>]` — one of grant_condition, statutory_obligation, factual_statement, or unknown when Guidance Proposition Extractor did not assign one. Read each candidate law clause on its own terms — what kind of provision it is and what it requires — from its text.

Rules (apply the first that matches; earlier rules take precedence):

1. regulatory_kind = factual_statement, any law clause → UNGROUNDED. Factual or background guidance is not asserting a regulatory rule and cannot be anchored on a law clause.
2. The law clause only defines a term, or only sets out the instrument's scope, commencement, or a delegated power → UNGROUNDED, unless the guidance is specifically restating that same definition or scope. The operative obligation that USES a defined term is the better anchor, not the definition itself. Two scope clauses from different instruments describe parallel territorial reach and do NOT conflict — each is true within its own instrument.
3. The law clause sets a minimum standard (a floor): guidance that meets it is GROUNDED; guidance that exceeds it is GUIDANCE_BROADER; guidance that falls short is CONFLICTS or GUIDANCE_INCOMPLETE depending on whether it positively asserts a weaker rule or merely omits the stronger one.
4. The law clause caps what the regulator may demand (a ceiling) and the guidance asks for more — e.g. a grant scheme above the statutory minimum → GUIDANCE_BROADER, NOT CONFLICTS. A higher bar does not contradict a cap on what may be demanded.
5. The law clause is purely procedural: GROUNDED if the guidance describes the same procedural step; UNGROUNDED if the guidance is about a substantive obligation rather than the procedure.
6. Cross-framework matches (guidance from one statutory framework, law from an unrelated framework) that share only surface vocabulary → prefer UNGROUNDED over CONFLICTS.

Reserve CONFLICTS for cases where both the guidance and the law sit within the same regulatory framework AND substantively oppose each other on the same point.

Self-check before emitting the JSON: for each match, does the relationship label you are about to emit actually match the typed rule you invoked in your explanation? If your explanation argues for one label (for example "GUIDANCE_BROADER under the ceiling rule"), emit that label. Do not write reasoning that justifies one label and then emit a different one.

Choose one label per candidate:
- GROUNDED: guidance accurately reflects this law.
- UNGROUNDED: this law is not the right basis for the guidance.
- CONFLICTS: guidance contradicts this law. Use sparingly — only when both are within the same regulatory framework and substantively oppose each other.
- GUIDANCE_INCOMPLETE: guidance covers only part of what this law requires.
- GUIDANCE_BROADER: guidance adds requirements beyond what this law states, or raises a higher bar than the statutory minimum without contradicting it (e.g. a grant scheme exceeding the statutory floor or sitting above a statutory ceiling on demanded capacity).
- GUIDANCE_MISSING: the law states a requirement the guidance touches but skips.

GUIDANCE
{guidance_text}

CANDIDATE LAW PROPOSITIONS
{candidate_block}

Return JSON only:
{
  "best_anchor_id": "<the law_id you think is the right basis, or null if none>",
  "anchor_rationale": "<1-2 sentences explaining why you picked that anchor, or why none>",
  "matches": [
    {
      "law_id": "<exact id from the candidates above>",
      "relationship": "<one of the six labels>",
      "confidence": "<high|medium|low>",
      "explanation": "<1-2 sentences>",
      "correctness_score": <float 0.0-1.0>
    }
  ]
}
"""


def build_group_rerank_prompt(
    guidance_prop,
    candidates: list[tuple[Any, float]],
) -> str:
    """Build the single group-rerank prompt for one guidance proposition and its
    surviving law candidates.

    ``candidates`` is a list of ``(law_proposition, similarity_score)`` already
    ordered by descending similarity.
    """
    candidate_block = "\n".join(
        f"[{law.id}]  ({law_citation(law)})  {law.proposition_text}"
        for law, _ in candidates
    )

    regulatory_kind = getattr(guidance_prop, "regulatory_kind", "") or "unknown"
    guidance_block = (
        f"[regulatory_kind: {regulatory_kind}]\n"
        f"{guidance_prop.proposition_text}"
    )
    # Plain .replace, not .format — the JSON template in the prompt body uses
    # literal { } braces.
    return GROUP_RERANK_PROMPT.replace("{guidance_text}", guidance_block).replace(
        "{candidate_block}", candidate_block
    )


def parse_group_rerank_json(raw: str) -> dict:
    """Parse a group-rerank response. Returns ``{"matches": [...]}`` with each
    match's relationship normalised to RELATIONSHIP_TYPES (fallback UNGROUNDED).
    Raises ValueError when no JSON object is present — the caller decides how to
    handle a failed proposition; we never silently fabricate matches."""
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("no JSON object in group-rerank response")
    data = json.loads(raw[start:end])
    out_matches = []
    for m in data.get("matches", []) or []:
        relationship = str(m.get("relationship", "UNGROUNDED"))
        if relationship not in RELATIONSHIP_TYPES:
            relationship = "UNGROUNDED"
        out_matches.append(
            {
                "law_id": str(m.get("law_id", "")).strip(),
                "relationship": relationship,
                "confidence": str(m.get("confidence", "low")),
                "explanation": str(m.get("explanation", ""))[:500],
                "correctness_score": float(m.get("correctness_score", 0.0)),
            }
        )
    return {
        "best_anchor_id": data.get("best_anchor_id"),
        "anchor_rationale": str(data.get("anchor_rationale", "")),
        "matches": out_matches,
    }


def build_summarise_prompt(guidance_prop, classified_matches: list[dict]) -> str:
    """Prompt asking the model to summarise how a guidance proposition aligns
    with its classified law matches. Each classified match is a dict carrying
    ``relationship``, ``explanation`` and a ``law_proposition`` dict."""
    matches_text = "\n\n".join(
        f"- Relationship: {m.get('relationship')}\n"
        f"  Law: {_law_text_from_payload(m.get('law_proposition', {}) or {})}\n"
        f"  Citation: {law_citation(m.get('law_proposition', {}))}\n"
        f"  Explanation: {m.get('explanation', '')}"
        for m in classified_matches
    )
    return f"""You are summarising how a piece of GOV.UK guidance relates to relevant law propositions.

GUIDANCE PROPOSITION
Source: {guidance_prop.source_url}
Section: {guidance_prop.section_locator}
Text: {guidance_prop.proposition_text}

RELEVANT LAW MATCHES
{matches_text if matches_text else "No relevant law matches found."}

Write a concise 2-3 sentence summary (maximum 100 words) of how the guidance aligns with (or diverges from) the relevant law. Focus on practical implications for compliance."""
