"""MODEL.md metadata generation."""

from __future__ import annotations

import json
from pathlib import Path

from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.proposition_normalisation import PROPOSITION_NORMALISATION_METADATA
from law_proposition_extractor_pipeline.run_model_md import (
    MODEL_MD_FILENAME,
    build_run_model_metadata,
    render_model_md,
)
from law_proposition_extractor_pipeline.run_persistence import build_persisted_run_config, persist_run_outputs


def _slurry_case() -> dict:
    return {
        "topic": {"name": "slurry manure agricultural effluent", "description": "Law Discovery intake"},
        "cluster": {"name": "slurry_manure_agricultural_effluent"},
        "ada_intake_ref": {
            "bundle_id": "6dac82d0-6ab6-45d9-95f5-4a79e135c699",
            "category_id": "slurry_manure_agricultural_effluent",
        },
        "model_metadata": {
            "description": "Slurry",
            "input_pipeline": "Proposition Matcher",
            "input_asset": "plough-chicken",
            "notes": "Frontier extraction, principal-only sources.",
            "additional_cost_estimates": {"co2_kg": None, "water_litres": None},
        },
        "sources": [{"id": "src-1", "authority": "legislation_gov_uk"}],
    }


def test_build_run_model_metadata_respects_case_overrides() -> None:
    bundle = build_demo_bundle(use_llm=False)
    bundle["stage_traces"] = [
        {
            "stage_name": "proposition extraction",
            "duration_ms": 120_000,
            "inputs": {"extraction_mode_effective": "frontier"},
            "outputs": {"extraction_elapsed_seconds": 118.5},
        }
    ]
    bundle["extraction_llm_call_traces"] = [
        {
            "model_alias": "frontier_extract",
            "estimated_input_tokens": 5000,
            "llm_call_attempted": True,
            "llm_call_succeeded": True,
        },
        {
            "model_alias": "frontier_extract",
            "estimated_input_tokens": 3000,
            "llm_cache_hit": True,
            "llm_call_attempted": False,
            "llm_call_succeeded": True,
        },
    ]
    meta = build_run_model_metadata(bundle=bundle, case_data=_slurry_case())
    assert meta["description"] == "Slurry"
    assert meta["input_pipeline"] == "Proposition Matcher"
    assert meta["input_asset"] == "plough-chicken"
    assert meta["operator_notes"] == "Frontier extraction, principal-only sources."
    assert meta["models_used"][0]["alias"] == "frontier_extract"
    assert meta["models_used"][0]["live_calls"] == 1
    assert meta["models_used"][0]["cached_results"] == 1
    assert "anthropic/claude-sonnet-4-5-20250929" in meta["models_used"][0]["provider_model"]
    assert meta["approx_cost"]["estimated_input_tokens_total"] == 8000
    assert meta["approx_cost"]["estimated_input_tokens_live_only"] == 5000
    assert meta["approx_cost"]["estimated_input_tokens_cached_only"] == 3000


def _bundle_with_frontier_traces() -> dict:
    bundle = build_demo_bundle(use_llm=False)
    bundle["stage_traces"] = [
        {
            "stage_name": "proposition extraction",
            "duration_ms": 120_000,
            "inputs": {"extraction_mode_effective": "frontier"},
            "outputs": {},
        }
    ]
    bundle["extraction_llm_call_traces"] = [
        {
            "model_alias": "frontier_extract",
            "estimated_input_tokens": 5000,
            "llm_call_attempted": True,
            "llm_call_succeeded": True,
            "response_model": "frontier_extract",
        },
    ]
    return bundle


def test_render_model_md_contains_sections() -> None:
    bundle = _bundle_with_frontier_traces()
    bundle["run_quality_summary"] = {"status": "fail", "warning_count": 3}
    md = render_model_md(
        build_run_model_metadata(bundle=bundle, case_data=_slurry_case())
    )
    assert "# Model & run metadata" in md
    assert "> **Run quality:** fail — 3 warnings." in md
    assert "## Indicative cost estimate" in md
    assert "Lower-bound indicative USD" in md
    assert "not a total run cost" in md
    assert "Estimated input tokens (cached calls only)" not in md
    assert "## Models used" in md
    assert "Provider model" in md
    assert "anthropic/claude-sonnet-4-5-20250929" in md
    assert "Proposition Matcher" in md
    assert "plough-chicken" in md
    assert "Sources / bundled propositions" in md
    assert "### Operator notes" in md
    assert "## Approximate cost" not in md


def test_model_md_proposition_normalisation_quality_not_recorded() -> None:
    bundle = _bundle_with_frontier_traces()
    md = render_model_md(build_run_model_metadata(bundle=bundle, case_data=_slurry_case()))
    assert "Proposition normalisation quality: not recorded" in md
    assert "warnings do not necessarily invalidate a run" in md


def test_model_md_proposition_normalisation_quality_from_bundle() -> None:
    bundle = _bundle_with_frontier_traces()
    bundle["proposition_normalisation_quality"] = {
        "warning_count": 12,
        "error_count": 2,
        "by_check": {
            "legacy_category_conflict": {"warnings": 10, "errors": 0},
            "scope_application_conflict": {"warnings": 1, "errors": 0},
            "dangerous_legacy_relationship_key": {"warnings": 0, "errors": 2},
            "debug_leakage": {"warnings": 1, "errors": 0},
        },
    }
    md = render_model_md(build_run_model_metadata(bundle=bundle, case_data=_slurry_case()))
    assert "**Proposition normalisation quality:**" in md
    assert "- Warnings: 12" in md
    assert "- Errors: 2" in md
    assert "- Legacy category conflicts: 10" in md
    assert "- Missing territorial application on application-scope rows: 1" in md
    assert "- Dangerous legacy keys: 2" in md
    assert "- Debug leakage: 1" in md


def test_model_md_proposition_normalisation_quality_from_json_file(tmp_path: Path) -> None:
    bundle = _bundle_with_frontier_traces()
    (tmp_path / "normalisation_quality.json").write_text(
        json.dumps(
            {
                "warning_count": 3,
                "error_count": 0,
                "by_check": {
                    "legacy_category_conflict": {"warnings": 3, "errors": 0},
                },
            }
        ),
        encoding="utf-8",
    )
    md = render_model_md(
        build_run_model_metadata(
            bundle=bundle,
            case_data=_slurry_case(),
            output_dir=tmp_path,
        )
    )
    assert "- Warnings: 3" in md
    assert "- Legacy category conflicts: 3" in md


def test_model_md_records_proposition_normalisation_when_present() -> None:
    bundle = _bundle_with_frontier_traces()
    bundle["pipeline_case_inputs"] = {
        "pipeline_version": "0.1.0",
        "proposition_normalisation": dict(PROPOSITION_NORMALISATION_METADATA),
    }
    meta = build_run_model_metadata(bundle=bundle, case_data=_slurry_case())
    md = render_model_md(meta)
    assert "Proposition normalisation" in md
    assert "v1" in md
    assert "classification" in md
    assert meta["proposition_normalisation_line"].startswith("**Proposition normalisation:**")


def test_render_model_md_omits_absolute_output_directory(tmp_path: Path) -> None:
    abs_dir = tmp_path / "nested" / "run-out"
    abs_dir.mkdir(parents=True)
    md = render_model_md(
        build_run_model_metadata(
            bundle=_bundle_with_frontier_traces(),
            case_data=_slurry_case(),
            output_dir=abs_dir,
        )
    )
    assert str(abs_dir) not in md
    assert "**Output directory**" not in md


def test_render_model_md_shows_cached_input_tokens_when_present() -> None:
    bundle = _bundle_with_frontier_traces()
    bundle["extraction_llm_call_traces"] = [
        {
            "model_alias": "frontier_extract",
            "estimated_input_tokens": 1000,
            "llm_cache_hit": True,
            "llm_call_attempted": False,
            "llm_call_succeeded": True,
        },
    ]
    md = render_model_md(build_run_model_metadata(bundle=bundle, case_data=_slurry_case()))
    assert "Estimated input tokens (cached calls only)" in md


def test_persist_run_outputs_writes_model_md(tmp_path: Path) -> None:
    case_data = _slurry_case()
    bundle = build_demo_bundle(use_llm=False)
    run_config = build_persisted_run_config(
        bundle=bundle,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="fallback",
        case_data=case_data,
    )
    persist_run_outputs(
        output=tmp_path / "run-dir",
        case_data=case_data,
        bundle=bundle,
        run_config=run_config,
    )
    model_md = tmp_path / "run-dir" / MODEL_MD_FILENAME
    assert model_md.is_file()
    assert "Slurry" in model_md.read_text(encoding="utf-8")
    stamped_bundle = json.loads((tmp_path / "run-dir" / "run_bundle.json").read_text(encoding="utf-8"))
    assert isinstance(stamped_bundle.get("run_model_metadata"), dict)


def test_export_bundle_writes_model_md(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path), case_data=_slurry_case())
    assert (tmp_path / MODEL_MD_FILENAME).is_file()
    md_text = (tmp_path / MODEL_MD_FILENAME).read_text(encoding="utf-8")
    assert "Slurry" in md_text
    assert (tmp_path / "normalisation_quality.json").is_file()
    assert "**Proposition normalisation quality:**" in md_text or "not recorded" in md_text
