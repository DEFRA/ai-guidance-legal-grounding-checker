"""Post-extraction proposition label enrichment."""

from __future__ import annotations

from law_proposition_extractor_domain import Proposition, apply_proposition_label_enrichment


def apply_post_extraction_labelling_pass(propositions: list[Proposition]) -> list[Proposition]:
    for proposition in propositions:
        apply_proposition_label_enrichment(proposition)
    return propositions
