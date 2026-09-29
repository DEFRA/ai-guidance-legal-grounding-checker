"""Unit tests for joining candidate locators onto Matcher law.json rows."""

from audit_assembler.law_candidates import (
    load_candidates,
    locator_from_law_row,
    merge_law_candidate_locators,
)


def test_load_candidates_accepts_wrap_and_bare_list():
    assert load_candidates({"candidates": [{"id": "a"}]}) == [{"id": "a"}]
    assert load_candidates([{"id": "a"}]) == [{"id": "a"}]


def test_locator_from_law_row_prefers_fragment_then_citation():
    assert locator_from_law_row({"fragment_locator": "regulation:1"}) == "regulation:1"
    assert (
        locator_from_law_row(
            {
                "citation": (
                    "the Nitrate Pollution Prevention Regulations 2015, regulation 36(6)"
                )
            }
        )
        == "regulation 36(6)"
    )


def test_merge_joins_presentation_locator_without_overwriting():
    law_input = [
        {"id": "bcand:1", "proposition_text": "A", "graph_node": "lex-1"},
        {
            "id": "bcand:2",
            "proposition_text": "B",
            "graph_node": "lex-1",
            "fragment_locator": "regulation:9",
        },
        {"id": "bcand:missing", "proposition_text": "C", "graph_node": "lex-1"},
    ]
    candidates = [
        {
            "id": "bcand:1",
            "presentation": {
                "locator_label": "regulation:31:paragraph:6:subparagraph:a"
            },
            "evidence": {
                "fragment_locators": ["regulation:31:paragraph:6:subparagraph:a"]
            },
        },
        {
            "id": "bcand:2",
            "presentation": {"locator_label": "regulation:99"},
        },
    ]
    warnings: list[str] = []
    merged = merge_law_candidate_locators(law_input, candidates, warnings)
    assert merged[0]["fragment_locator"] == "regulation:31:paragraph:6:subparagraph:a"
    assert merged[1]["fragment_locator"] == "regulation:9"
    assert "fragment_locator" not in merged[2]
    assert any("joined fragment_locator" in w for w in warnings)
    assert any("no locator" in w for w in warnings)
