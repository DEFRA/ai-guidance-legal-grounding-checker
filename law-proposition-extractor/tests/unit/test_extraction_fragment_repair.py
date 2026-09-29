"""Tests for targeted fragment repair merge."""

from __future__ import annotations

from law_proposition_extractor_domain import Proposition
from law_proposition_extractor_pipeline.extraction_fragment_repair import (
    FRAGMENT_REPAIR_COMMAND,
    merge_fragment_repair_into_bundle,
    npp_reg2_proposition_rows,
    proposition_belongs_to_fragment,
    summarize_npp_reg2_definition_anchors,
)


def _prop(
    *,
    pid: str,
    source_id: str = "src-a",
    fragment_id: str | None = "frag-a",
    locator: str = "regulation:2",
    text: str = "Example",
) -> dict:
    return {
        "id": pid,
        "source_record_id": source_id,
        "source_fragment_id": fragment_id,
        "fragment_locator": locator,
        "proposition_text": text,
        "legal_subject": "subject",
        "action": "must",
        "jurisdiction": "GB",
        "topic_id": "topic-1",
        "cluster_id": "cluster-1",
    }


def test_proposition_belongs_to_fragment_by_fragment_id() -> None:
    row = _prop(pid="p1")
    assert proposition_belongs_to_fragment(
        row,
        source_record_id="src-a",
        source_fragment_id="frag-a",
        fragment_locator="regulation:2",
    )
    assert not proposition_belongs_to_fragment(
        row,
        source_record_id="src-b",
        source_fragment_id="frag-a",
        fragment_locator="regulation:2",
    )


def test_merge_fragment_repair_replaces_matching_fragment_only() -> None:
    bundle = {
        "run": {"id": "run-001"},
        "propositions": [
            _prop(pid="keep-1", fragment_id="frag-other", locator="regulation:3"),
            _prop(pid="drop-1", text="old reg2"),
            _prop(pid="drop-2", text="old reg2 two"),
        ],
        "proposition_extraction_jobs": [
            {
                "source_record_id": "src-a",
                "source_fragment_id": "frag-a",
                "fragment_locator": "regulation:2",
                "proposition_count": 2,
            }
        ],
        "proposition_scope_links": [
            {"proposition_id": "drop-1", "scope_id": "scope-1"},
            {"proposition_id": "keep-1", "scope_id": "scope-2"},
        ],
    }
    new_prop = Proposition.model_validate(
        {
            **_prop(pid="new-1", text='Slurry means excreta produced by livestock.'),
            "review_status": "proposed",
        }
    )
    repair_metadata = {
        "repair_command": FRAGMENT_REPAIR_COMMAND,
        "fragment_locator": "regulation:2",
    }
    merged = merge_fragment_repair_into_bundle(
        bundle=bundle,
        source_record_id="src-a",
        source_fragment_id="frag-a",
        fragment_locator="regulation:2",
        new_propositions=[new_prop],
        repair_metadata=repair_metadata,
    )
    ids = {row["id"] for row in merged["propositions"]}
    assert "keep-1" in ids
    assert "new-1" in ids
    assert "drop-1" not in ids
    assert "drop-2" not in ids
    assert merged["proposition_inventory"]["proposition_count"] == 2
    assert merged["proposition_extraction_jobs"][0]["proposition_count"] == 1
    assert merged["proposition_extraction_jobs"][0]["fragment_repair_applied"] is True
    assert all(link["proposition_id"] != "drop-1" for link in merged["proposition_scope_links"])


def test_summarize_npp_reg2_definition_anchors() -> None:
    rows = [
        {
            "id": "p-slurry",
            "source_record_id": "lex-120b4f9c395b3f94",
            "fragment_locator": "regulation 2, paragraph 1, definition of 'slurry'",
            "proposition_text": 'Slurry means excreta produced by livestock.',
        },
        {
            "id": "p-spread",
            "source_record_id": "lex-120b4f9c395b3f94",
            "fragment_locator": "regulation:2",
            "proposition_text": 'Spreading, in relation to land, includes applying to the surface of the land.',
        },
    ]
    reg2_rows = npp_reg2_proposition_rows(rows)
    assert len(reg2_rows) == 2
    summary = summarize_npp_reg2_definition_anchors(rows)
    assert summary["anchors"]["slurry"]["present"] is True
    assert summary["anchors"]["spreading"]["present"] is True
    assert summary["anchors"]["organic manure"]["present"] is False
