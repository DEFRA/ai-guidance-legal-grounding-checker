"""Post-extraction deterministic proposition classification pass."""

from __future__ import annotations

from law_proposition_extractor_domain import Proposition, apply_post_extraction_classification


def apply_post_extraction_classification_pass(
    propositions: list[Proposition],
) -> list[Proposition]:
    """
    Classify propositions after LLM/heuristic extraction and before record assembly/export.

    Mutates each proposition in place and returns the same list for chaining.
    """
    for proposition in propositions:
        apply_post_extraction_classification(proposition)
    return propositions
