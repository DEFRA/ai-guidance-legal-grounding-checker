"""The re-adjudication prompt (shipped: v5 — brief + Proposition Matcher's reason + scope note).

Proposition Matcher classifies one guidance proposition against one law proposition in
isolation, so it over-reports gaps and conflicts: the resolving text is usually in
a sibling proposition on the same page. Match Adjudicator re-reads each flagged finding with the
whole page's guidance plus Proposition Matcher's stated reason, and decides whether the
verdict still holds.
"""

from __future__ import annotations

# Statuses Match Adjudicator may return. Proposition Matcher's flagged verdicts are CONFLICTS /
# GUIDANCE_INCOMPLETE; Match Adjudicator can keep them or downgrade to GROUNDED.
ALLOWED_NEW = ("GROUNDED", "CONFLICTS", "GUIDANCE_INCOMPLETE")

PROMPT = """You are a senior legal-content auditor for DEFRA, the UK government department.

You have been given one piece of guidance that, compared against a single law
proposition, was given a verdict of either CONFLICTS or GUIDANCE_INCOMPLETE, along
with the specific reason for that verdict. Alongside it you are given the other
guidance propositions surrounding it on the same page.

That verdict was reached by looking at this one proposition in isolation. Your job
is to review it in the light of the wider guidance and decide whether it still
holds.

Before judging coverage, check whether the guidance and the law are actually about
the same specific requirement. They may have been paired only because they sound
similar but are actually about different subjects or different law.

Focus on the SPECIFIC concern in the reason, and check whether the surrounding
guidance resolves THAT specific concern:

- If the specific requirement the reason says is missing (or the specific point it
  says conflicts) is in fact covered by a neighbouring proposition, the verdict no
  longer holds — set new_status to GROUNDED. The neighbour must cover the same
  specific requirement, not merely state a related general duty.
- If the guidance and the law in fact concern different activities, the verdict
  may also not hold.
- Otherwise, if nothing in the surrounding guidance resolves the specific concern,
  the original verdict stands and new_status equals old_status.

GUIDANCE PROPOSITION:
{guidance_text}

LAW PROPOSITION:
{law_text}

VERDICT: {old_status}
REASON FOR VERDICT: {explanation}

SURROUNDING GUIDANCE ON THIS PAGE:
{page_block}

Return ONLY a JSON object:
{{"new_status": "<GROUNDED | CONFLICTS | GUIDANCE_INCOMPLETE>", "reason": "<one line>"}}"""


def build_prompt(
    *, guidance_text: str, law_text: str, old_status: str, explanation: str | None,
    siblings: list[str],
) -> str:
    """Render the prompt for one flagged finding against its page siblings."""
    page_block = (
        "\n".join(f"- {s}" for s in siblings) if siblings else "(no other guidance on page)"
    )
    return PROMPT.format(
        guidance_text=guidance_text,
        law_text=law_text,
        old_status=old_status,
        explanation=explanation or "(no reason provided)",
        page_block=page_block,
    )
