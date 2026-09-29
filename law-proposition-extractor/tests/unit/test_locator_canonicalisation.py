"""Tests for paragraph/list locator canonicalisation and text-discriminated grouping keys."""

import pytest
from law_proposition_extractor_pipeline.proposition_explorer_grouping import (
    canonical_lineage_key_for_grouping,
    group_key_core_for_proposition_row,
)


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        ("article:6:paragraph:1", "article:6:para:1"),
        ("article:6:paragraph:1(a)", "article:6:list:1-a"),
        ("article:6:paragraph:1(a)(i)", "article:6:list:1-a-i"),
        ("section:3:paragraph:2", "section:3:para:2"),
        ("ARTICLE:12:PARAGRAPH:4", "article:12:para:4"),
    ],
)
def test_paragraph_locator_canonicalises(locator: str, expected: str) -> None:
    assert canonical_lineage_key_for_grouping(locator) == expected


def _row(text: str, locator: str) -> dict:
    return {"original_artifact": {"id": text[:8], "fragment_locator": locator, "proposition_text": text}}


def test_distinct_rules_in_one_paragraph_do_not_merge() -> None:
    a = _row("Nationals shall not support IUU fishing.", "article:39:paragraph:1")
    b = _row("Nationals shall not engage in IUU fishing.", "article:39:paragraph:1")
    assert group_key_core_for_proposition_row(a) != group_key_core_for_proposition_row(b)


def test_same_paragraph_same_text_merges_across_versions() -> None:
    eu = _row("A vessel shall be presumed engaged in IUU fishing.", "article:3:paragraph:1")
    uk = _row("A vessel shall be presumed engaged in IUU fishing.", "article:3:paragraph:1")
    assert group_key_core_for_proposition_row(eu) == group_key_core_for_proposition_row(uk)


def test_precise_list_path_keys_directly_without_text() -> None:
    key = group_key_core_for_proposition_row(_row("anything", "article:6:paragraph:1(a)"))
    assert key == "article:6:list:1-a"


def test_freetext_paragraph_distinct_rules_separate() -> None:
    a = _row("The CMO comprises professional organisations.", "Article 1(2)")
    b = _row("The CMO comprises marketing standards.", "Article 1(2)")
    assert group_key_core_for_proposition_row(a) != group_key_core_for_proposition_row(b)
