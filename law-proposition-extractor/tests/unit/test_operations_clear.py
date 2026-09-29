"""Tests for dev/admin operations clearing."""

import json
from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.demo import build_demo_bundle
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.operations_clear import (
    EMPTY_SOURCE_REGISTRY_PAYLOAD,
    ClearOperationsConfirmationError,
    execute_clear_operations_all,
    execute_clear_operations_runs_only,
    plan_clear_operations_runs_only,
)


def test_plan_clear_operations_runs_only_lists_export_paths(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))
    registry = tmp_path.parent / "reg.json"

    deletes, preserves = plan_clear_operations_runs_only(tmp_path, source_registry_path=registry)

    assert str(registry.resolve()) in preserves
    assert any("runs" in p for p in deletes)


def test_clear_operations_runs_only_preserves_registry_file(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    registry_file = tmp_path.parent / "source-registry-api.json"
    registry_file.write_text(
        json.dumps({"version": "0.1", "sources": [{"registry_id": "keep-me"}]}, indent=2),
        encoding="utf-8",
    )

    execute_clear_operations_runs_only(
        export_dir=tmp_path,
        source_registry_path=str(registry_file),
        dry_run=False,
        confirm=True,
    )

    assert tmp_path.exists() and not any(tmp_path.iterdir())

    restored = json.loads(registry_file.read_text(encoding="utf-8"))
    assert restored.get("sources") == [{"registry_id": "keep-me"}]


def test_clear_operations_all_resets_registry_and_removes_bundle(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    registry_file = tmp_path.parent / "reg-all.json"
    registry_file.write_text(
        json.dumps({"version": "0.1", "sources": [{"registry_id": "gone"}]}, indent=2),
        encoding="utf-8",
    )

    cache = tmp_path.parent / "snapshot-cache-test"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "x.json").write_text("{}", encoding="utf-8")

    derived = tmp_path.parent / "derived-cache-test"
    derived.mkdir(parents=True, exist_ok=True)
    (derived / "y.bin").write_text("blob", encoding="utf-8")

    outcome = execute_clear_operations_all(
        export_dir=tmp_path,
        source_registry_path=str(registry_file),
        source_cache_dir=str(cache),
        derived_cache_dir=str(derived),
        dry_run=False,
        confirm=True,
    )

    assert not any(tmp_path.iterdir())
    assert json.loads(registry_file.read_text(encoding="utf-8")) == EMPTY_SOURCE_REGISTRY_PAYLOAD
    assert cache.exists() and not any(cache.iterdir())
    assert derived.exists() and not any(derived.iterdir())
    assert outcome.registry_reset_written is True


def test_dry_run_deletes_nothing(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    registry_file = tmp_path.parent / "reg-dry.json"
    registry_file.write_text(
        json.dumps({"version": "0.1", "sources": [{"registry_id": "stay"}]}, indent=2),
        encoding="utf-8",
    )

    before = list(tmp_path.rglob("*"))

    execute_clear_operations_runs_only(
        export_dir=tmp_path,
        source_registry_path=str(registry_file),
        dry_run=True,
        confirm=False,
    )

    after = list(tmp_path.rglob("*"))
    assert len(after) == len(before)

    execute_clear_operations_all(
        export_dir=tmp_path,
        source_registry_path=str(registry_file),
        source_cache_dir=tmp_path.parent / "nocache-a",
        derived_cache_dir=tmp_path.parent / "nocache-b",
        dry_run=True,
        confirm=False,
    )

    assert list(tmp_path.rglob("*")) == after


def test_confirm_required_for_non_dry_execution(tmp_path: Path) -> None:
    bundle = build_demo_bundle(use_llm=False)
    export_bundle(bundle=bundle, output_dir=str(tmp_path))

    registry_file = tmp_path.parent / "reg-confirm.json"
    registry_file.write_text(json.dumps({"version": "0.1", "sources": []}), encoding="utf-8")

    with pytest.raises(ClearOperationsConfirmationError):
        execute_clear_operations_runs_only(
            export_dir=tmp_path,
            source_registry_path=str(registry_file),
            dry_run=False,
            confirm=False,
        )
