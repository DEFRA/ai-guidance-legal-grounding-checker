"""Tests for repealed / structurally-empty fragment detection."""

import pytest
from law_proposition_extractor_pipeline.proposition_explorer_grouping import (
    should_suppress_coarse_parent_proposition_in_default_view,
)
from law_proposition_extractor_pipeline.repealed_provisions import is_repealed_or_empty_fragment


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Article 5. . . . . . . . . . . . . . .",
        "Article 11. . . . . . . . . . . . . . .",
        "(2). . . . . . . . . . . . . . . . . .",
        "(3) . . .",
        ". . . . . . . .",
        "5.",
        "(2)",
        "ANNEX II",
        "Annex I",
        "SCHEDULE 2",
        "Part IV",
        "(a)",
        "(iv)",
    ],
)
def test_repealed_or_empty_detected(text: str) -> None:
    assert is_repealed_or_empty_fragment(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Article 5 establishes a system to prevent IUU fishing.",
        "Imports are prohibited.",
        "(1) This Regulation establishes a system to prevent, deter and eliminate IUU fishing.",
        "Masters of third country fishing vessels must notify the competent authorities.",
        "SCHEDULE 1Fisheries statements and management plans: preparation and publication.",
        "(a) a unique code is assigned to each animal.",
        "Annex I, CN code 0301 10 covers live ornamental fish.",
    ],
)
def test_genuine_content_not_suppressed(text: str) -> None:
    assert is_repealed_or_empty_fragment(text) is False


def _row(text: str, locator: str = "article:5") -> dict:
    return {
        "original_artifact": {
            "id": f"prop-{abs(hash(text)) % 10000}",
            "fragment_locator": locator,
            "proposition_text": text,
        },
        "effective_status": "needs_review",
    }


def test_suppresses_repealed_placeholder_in_default_view() -> None:
    repealed = _row("Article 5. . . . . . . . . . .")
    assert should_suppress_coarse_parent_proposition_in_default_view(repealed, [repealed]) is True


def test_does_not_suppress_real_proposition() -> None:
    real = _row(
        "This Regulation establishes a system for control and enforcement.",
        locator="article:1:paragraph:1",
    )
    assert should_suppress_coarse_parent_proposition_in_default_view(real, [real]) is False
