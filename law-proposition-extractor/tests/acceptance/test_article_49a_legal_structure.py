"""Offline Article 49a legal-structure end-to-end acceptance (prompt 19-BR1)."""

from __future__ import annotations

from pathlib import Path

from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    assert_article_49a_legal_structure,
    run_article_49a_acceptance_pipeline,
)


def test_article_49a_legal_structure_end_to_end(tmp_path: Path) -> None:
    result = run_article_49a_acceptance_pipeline(work_dir=tmp_path)
    roles = result.proposition_ids
    assert set(roles) == {"P1", "P2", "E1", "E2", "E3", "P3"}
    # Re-assert on the exported bundle view (serialization path).
    assert_article_49a_legal_structure(result.bundle)
    for name in (
        "source_snapshots.json",
        "source_fragments.json",
        "propositions.json",
        "legal_rule_groups.json",
        "legal_rule_relationships.json",
        "effective_law_statements.json",
        "proposition_matcher_law_candidates.json",
        "source_legal_effects.json",
    ):
        assert (result.export_dir / name).is_file()
