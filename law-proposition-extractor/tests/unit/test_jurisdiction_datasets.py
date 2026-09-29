"""Analysis scope, proposition dataset metadata, and dataset comparison without re-extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from law_proposition_extractor_pipeline.dataset_comparison_run import run_proposition_dataset_comparison
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.proposition_dataset import (
    attach_proposition_dataset_metadata,
    canonical_jurisdiction_label,
    filter_registry_case_sources_by_scope,
    merge_export_bundles_for_dataset_comparison,
)
from law_proposition_extractor_pipeline.runner import run_registry_sources
from law_proposition_extractor_pipeline.sources import SourceRegistryService


def _ref(
    *,
    authority_source_id: str,
    source_id: str,
    jurisdiction: str,
    citation: str,
    text: str,
) -> dict[str, object]:
    return {
        "authority": "case_file",
        "authority_source_id": authority_source_id,
        "id": source_id,
        "title": f"{jurisdiction} source",
        "jurisdiction": jurisdiction,
        "citation": citation,
        "kind": "regulation",
        "text": text,
        "authoritative_locator": "article:10",
        "version_id": "v1",
    }


def test_filter_registry_case_sources_by_scope_eu_only() -> None:
    rows = [
        {"id": "a", "jurisdiction": "EU"},
        {"id": "b", "jurisdiction": "UK"},
    ]
    out = filter_registry_case_sources_by_scope(rows, "eu")
    assert [r["id"] for r in out] == ["a"]


def test_canonical_jurisdiction_label() -> None:
    assert canonical_jurisdiction_label("gb") == "UK"


def test_eu_only_registry_run_has_eu_dataset_metadata(tmp_path: Path) -> None:
    reg = str(tmp_path / "reg.json")
    cache = str(tmp_path / "cache")
    derived = str(tmp_path / "derived")
    registry = SourceRegistryService(registry_path=reg, source_cache_dir=cache)
    eu = registry.register_reference(
        reference=_ref(
            authority_source_id="eu-1",
            source_id="src-eu",
            jurisdiction="EU",
            citation="EU-1",
            text="Article 10. Operators must maintain a register.",
        ),
        refresh=True,
    )
    bundle = run_registry_sources(
        registry_ids=[eu["registry_id"]],
        topic_name="EU only",
        analysis_mode="single_jurisdiction",
        analysis_scope="eu",
        source_registry_path=reg,
        source_cache_dir=cache,
        derived_cache_dir=derived,
        use_llm=False,
    )
    attach_proposition_dataset_metadata(bundle)
    ds = bundle.get("proposition_dataset") or {}
    assert ds.get("jurisdiction_scope") == "EU"


def test_auto_mode_multi_jurisdiction_no_divergence(tmp_path: Path) -> None:
    reg = str(tmp_path / "reg.json")
    cache = str(tmp_path / "cache")
    derived = str(tmp_path / "derived")
    registry = SourceRegistryService(registry_path=reg, source_cache_dir=cache)
    eu = registry.register_reference(
        reference=_ref(
            authority_source_id="eu-1",
            source_id="src-eu",
            jurisdiction="EU",
            citation="EU-1",
            text="Article 10. Operators must maintain a movement register.",
        ),
        refresh=True,
    )
    uk = registry.register_reference(
        reference=_ref(
            authority_source_id="uk-1",
            source_id="src-uk",
            jurisdiction="UK",
            citation="UK-1",
            text="Article 10. UK statute text differs so registry cache stays distinct.",
        ),
        refresh=True,
    )
    bundle = run_registry_sources(
        registry_ids=[eu["registry_id"], uk["registry_id"]],
        topic_name="Inventory only",
        analysis_mode="auto",
        analysis_scope="selected_sources",
        source_registry_path=reg,
        source_cache_dir=cache,
        derived_cache_dir=derived,
        use_llm=False,
    )
    assert bundle["run"]["workflow_mode"] == "single_jurisdiction"


def test_divergence_requires_explicit_jurisdictions_for_selected_sources(
    tmp_path: Path,
) -> None:
    reg = str(tmp_path / "reg.json")
    cache = str(tmp_path / "cache")
    derived = str(tmp_path / "derived")
    registry = SourceRegistryService(registry_path=reg, source_cache_dir=cache)
    eu = registry.register_reference(
        reference=_ref(
            authority_source_id="eu-1",
            source_id="src-eu",
            jurisdiction="EU",
            citation="EU-1",
            text="Article 10. Operators must maintain a movement register.",
        ),
        refresh=True,
    )
    uk = registry.register_reference(
        reference=_ref(
            authority_source_id="uk-1",
            source_id="src-uk",
            jurisdiction="UK",
            citation="UK-1",
            text="Article 10. UK statute text differs so registry cache stays distinct.",
        ),
        refresh=True,
    )
    with pytest.raises(ValueError, match="comparison_jurisdiction"):
        run_registry_sources(
            registry_ids=[eu["registry_id"], uk["registry_id"]],
            topic_name="Divergence",
            analysis_mode="divergence",
            analysis_scope="selected_sources",
            source_registry_path=reg,
            source_cache_dir=cache,
            derived_cache_dir=derived,
            use_llm=False,
        )


def test_dataset_comparison_skips_extraction(tmp_path: Path) -> None:
    out = str(tmp_path / "out")
    Path(out).mkdir(parents=True, exist_ok=True)
    reg = str(tmp_path / "reg.json")
    cache = str(tmp_path / "cache")
    derived = str(tmp_path / "derived")
    registry = SourceRegistryService(registry_path=reg, source_cache_dir=cache)

    def _one_run(sid: str, juris: str) -> dict:
        body = (
            "Article 10. EU operators must maintain a movement register before dispatch."
            if juris == "EU"
            else "Article 10. UK operators must maintain a movement register before dispatch."
        )
        ref = registry.register_reference(
            reference=_ref(
                authority_source_id=f"{juris}-{sid}",
                source_id=sid,
                jurisdiction=juris,
                citation=f"{juris}-C",
                text=body,
            ),
            refresh=True,
        )
        return run_registry_sources(
            registry_ids=[ref["registry_id"]],
            topic_name=f"{juris} dataset",
            analysis_mode="single_jurisdiction",
            analysis_scope="selected_sources",
            source_registry_path=reg,
            source_cache_dir=cache,
            derived_cache_dir=derived,
            use_llm=False,
        )

    left_b = _one_run("src-eu-only", "EU")
    right_b = _one_run("src-uk-only", "UK")
    export_bundle(left_b, output_dir=out)
    export_bundle(right_b, output_dir=out)
    attach_proposition_dataset_metadata(left_b)
    attach_proposition_dataset_metadata(right_b)

    cmp_bundle = run_proposition_dataset_comparison(
        left_bundle=left_b,
        right_bundle=right_b,
        comparison_run_id="cmp-test-1",
        topic_name="Cmp",
        use_llm=False,
        divergence_reasoning="none",
        extraction_mode="heuristic",
        extraction_fallback="fallback",
        proposition_index=0,
        source_cache_dir=cache,
        derived_cache_dir=derived,
        pairing_settings=None,
        comparison_jurisdiction_a="EU",
        comparison_jurisdiction_b="UK",
    )
    traces = [t for t in cmp_bundle.get("stage_traces", []) if t.get("stage_name") == "proposition extraction"]
    assert traces
    assert traces[0].get("strategy_used") == "skipped_preloaded_propositions"
    assert cmp_bundle.get("dataset_comparison_run")
    hook = traces[0].get("inputs", {}).get("derived_artifact_cache") or {}
    assert hook.get("cache_status") == "skipped_preloaded_propositions"


def test_merge_bundles_rejects_id_collision() -> None:
    left = {"source_records": [{"id": "x"}], "propositions": [{"id": "p1"}]}
    right = {"source_records": [{"id": "x"}], "propositions": [{"id": "p2"}]}
    with pytest.raises(ValueError, match="overlapping"):
        merge_export_bundles_for_dataset_comparison(left, right)
