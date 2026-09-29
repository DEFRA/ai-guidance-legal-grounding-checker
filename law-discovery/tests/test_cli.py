from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from law_discovery.cli import app
from law_discovery.models import (
    CandidateSource,
    CategoryBrief,
    DiscoveryRun,
    RelatedSourceExpansionRun,
    SourceBundle,
    SourceRegister,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def clear_ai_and_lex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAW_DISCOVERY_AI_MODEL", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_LEX_BASE_URL", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_LEX_API_KEY", raising=False)


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Law Discovery" in result.stdout
    assert "build-query-plan" in result.stdout
    assert "check-ai" in result.stdout
    assert "discover" in result.stdout
    assert "export-for-law-proposition-extractor" in result.stdout
    assert "expand-related-sources" in result.stdout
    assert "make-source-bundle" in result.stdout
    assert "make-law-proposition-extractor-intake-bundle" in result.stdout
    assert "export-bundle-for-law-proposition-extractor" in result.stdout


def test_make_law_proposition_extractor_intake_bundle_help_includes_filter_flags() -> None:
    result = runner.invoke(app, ["make-law-proposition-extractor-intake-bundle", "--help"])
    assert result.exit_code == 0
    assert "exclude-jurisdict" in result.stdout
    assert "priority-policy" in result.stdout


def test_build_query_plan_with_example_category(examples_dir: Path) -> None:
    category_path = examples_dir / "equine-identification.category.json"
    result = runner.invoke(app, ["build-query-plan", str(category_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert any(item["query"] == "horse passport" for item in payload)


def test_discover_help_includes_quiet_and_plain() -> None:
    result = runner.invoke(app, ["discover", "--help"])
    assert result.exit_code == 0
    assert "--quiet" in result.stdout
    assert "--plain" in result.stdout


def test_discover_help_includes_ai_triage_flags() -> None:
    result = runner.invoke(app, ["discover", "--help"])
    assert result.exit_code == 0
    assert "--use-ai-triage" in result.stdout
    assert "--apply-ai-review-s" in result.stdout
    assert "--ai-triage-batch-s" in result.stdout


def test_discover_no_network_plain_writes_valid_output_and_shows_progress(
    examples_dir: Path,
    tmp_path: Path,
) -> None:
    category_path = examples_dir / "equine-identification.category.json"
    output_path = tmp_path / "discovery-run.json"
    result = runner.invoke(
        app,
        [
            "discover",
            str(category_path),
            "--output",
            str(output_path),
            "--no-network",
            "--plain",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert output_path.exists()
    run = DiscoveryRun.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert run.category.category_id == "equine_identification"
    assert "[law-discovery]" in result.stderr
    assert "Built" in result.stderr
    assert "discovery-run.json" in result.stderr
    assert "[law-discovery] wrote" in result.stderr


def test_discover_no_network_quiet_writes_valid_output_without_progress(
    examples_dir: Path,
    tmp_path: Path,
) -> None:
    category_path = examples_dir / "equine-identification.category.json"
    output_path = tmp_path / "discovery-run.json"
    result = runner.invoke(
        app,
        [
            "discover",
            str(category_path),
            "--output",
            str(output_path),
            "--no-network",
            "--quiet",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert output_path.exists()
    run = DiscoveryRun.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert run.category.category_id == "equine_identification"
    assert "[law-discovery]" not in result.stderr
    assert "Law Discovery Source Discovery" not in result.stderr
    assert result.stdout == ""


def test_discover_without_lex_config_fails_cleanly(examples_dir: Path, tmp_path: Path) -> None:
    category_path = examples_dir / "equine-identification.category.json"
    output_path = tmp_path / "discovery-run.json"
    result = runner.invoke(
        app,
        [
            "discover",
            str(category_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code != 0
    assert "LAW_DISCOVERY_LEX_BASE_URL" in result.stderr
    assert "--no-network" in result.stderr
    assert "Traceback" not in result.stderr + result.stdout


def test_discover_no_network_writes_valid_discovery_run(
    examples_dir: Path,
    tmp_path: Path,
) -> None:
    category_path = examples_dir / "equine-identification.category.json"
    output_path = tmp_path / "discovery-run.json"
    result = runner.invoke(
        app,
        [
            "discover",
            str(category_path),
            "--output",
            str(output_path),
            "--no-network",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output_path.exists()
    run = DiscoveryRun.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert run.category.category_id == "equine_identification"
    assert run.candidate_sources == []
    assert any("network discovery was disabled" in warning.lower() for warning in run.warnings)


def test_make_register_writes_valid_source_register(tmp_path: Path) -> None:
    run = DiscoveryRun(
        run_id="law-discovery-run-test",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        category=CategoryBrief(
            category_id="equine_identification",
            label="Equine identification",
            description="Test",
        ),
        query_plan=[],
        candidate_sources=[
            CandidateSource(
                source_id="high-1",
                title="Equine Identification Regulations",
                confidence="high",
            ),
            CandidateSource(
                source_id="low-1",
                title="Other Act",
                confidence="low",
            ),
        ],
    )
    run_path = tmp_path / "run.json"
    run_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    register_path = tmp_path / "register.json"

    result = runner.invoke(
        app,
        [
            "make-register",
            str(run_path),
            "--output",
            str(register_path),
            "--accept-high-confidence",
        ],
    )
    assert result.exit_code == 0, result.stdout
    register = SourceRegister.model_validate_json(register_path.read_text(encoding="utf-8"))
    assert register.register_id == "law-discovery-register-equine_identification"
    assert len(register.accepted_sources) == 1
    assert len(register.parked_sources) == 1
    assert register.rejected_sources == []


def test_export_for_judit_writes_valid_json(tmp_path: Path) -> None:
    register = SourceRegister(
        register_id="law-discovery-register-equine_identification",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        accepted_sources=[
            CandidateSource(
                source_id="uksi/2018/123",
                title="Equine Identification (England) Regulations 2018",
                citation="SI 2018/123",
                source_type="uksi",
                review_status="accepted",
            )
        ],
    )
    register_path = tmp_path / "register.json"
    register_path.write_text(register.model_dump_json(indent=2), encoding="utf-8")
    output_path = tmp_path / "law-proposition-extractor-handoff.json"

    result = runner.invoke(
        app,
        [
            "export-for-law-proposition-extractor",
            str(register_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["export_type"] == "ada_selected_sources_for_judit"
    assert payload["export_version"] == "0.1"
    assert len(payload["sources"]) == 1


def test_export_for_judit_with_example_register(examples_dir: Path, tmp_path: Path) -> None:
    register_path = examples_dir / "equine-identification.source-register.example.json"
    output_path = tmp_path / "law-proposition-extractor-handoff.json"
    result = runner.invoke(
        app,
        [
            "export-for-law-proposition-extractor",
            str(register_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["export_type"] == "ada_selected_sources_for_judit"
    assert len(payload["sources"]) >= 1


def test_expand_category_missing_ai_config_fails_cleanly(
    examples_dir: Path,
    tmp_path: Path,
) -> None:
    category_path = examples_dir / "equine-identification.category.json"
    output_path = tmp_path / "expansion.json"
    result = runner.invoke(
        app,
        [
            "expand-category",
            str(category_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code != 0
    assert "AI configuration is required" in result.stderr
    assert "Traceback" not in result.stderr + result.stdout


def test_expand_related_sources_no_network_writes_valid_run(tmp_path: Path) -> None:
    register = SourceRegister(
        register_id="reg-1",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
        accepted_sources=[
            CandidateSource(
                source_id="uksi/2009/1741",
                title="Horse Passports Regulations 2009",
                review_status="accepted",
            )
        ],
    )
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Test",
    )
    register_path = tmp_path / "register.json"
    category_path = tmp_path / "category.json"
    register_path.write_text(register.model_dump_json(indent=2), encoding="utf-8")
    category_path.write_text(category.model_dump_json(indent=2), encoding="utf-8")
    output_path = tmp_path / "related.json"

    result = runner.invoke(
        app,
        [
            "expand-related-sources",
            str(register_path),
            str(category_path),
            "--output",
            str(output_path),
            "--no-network",
        ],
    )
    assert result.exit_code == 0, result.stderr
    run = RelatedSourceExpansionRun.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert len(run.seed_sources) == 1
    assert run.related_sources == []


def test_review_related_source_updates_run(tmp_path: Path) -> None:
    run = RelatedSourceExpansionRun(
        run_id="rel-run",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        category_id="slurry_manure_agricultural_effluent",
        seed_sources=[],
        related_sources=[
            CandidateSource(
                source_id="orphan-2010",
                title=(
                    "The Water Resources (Control of Pollution) (Silage, Slurry and "
                    "Agricultural Fuel Oil) (England) Regulations 2010"
                ),
                review_status="needs_more_research",
            )
        ],
        relationships=[],
    )
    run_path = tmp_path / "related.json"
    run_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    output_path = tmp_path / "related-reviewed.json"

    result = runner.invoke(
        app,
        [
            "review-related-source",
            str(run_path),
            "orphan-2010",
            "--status",
            "accepted",
            "--relationship-to-category",
            "directly_regulates",
            "--notes",
            "Successor SSAFO instrument for England.",
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0, result.stderr
    updated = RelatedSourceExpansionRun.model_validate_json(
        output_path.read_text(encoding="utf-8")
    )
    source = updated.related_sources[0]
    assert source.review_status == "accepted"
    assert source.relationship_to_category == "directly_regulates"
    assert source.notes == "Successor SSAFO instrument for England."


def test_make_source_bundle_writes_valid_bundle(tmp_path: Path) -> None:
    register = SourceRegister(
        register_id="reg-1",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
        accepted_sources=[
            CandidateSource(
                source_id="principal",
                title="Horse Passports Regulations 2009",
                relationship_to_category="directly_regulates",
                review_status="accepted",
            )
        ],
    )
    register_path = tmp_path / "register.json"
    register_path.write_text(register.model_dump_json(indent=2), encoding="utf-8")
    output_path = tmp_path / "bundle.json"

    result = runner.invoke(
        app,
        ["make-source-bundle", str(register_path), "--output", str(output_path)],
    )
    assert result.exit_code == 0, result.stdout
    bundle = SourceBundle.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert len(bundle.principal_sources) == 1


def test_check_ai_help_includes_options() -> None:
    result = runner.invoke(app, ["check-ai", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.stdout
    assert "--litellm-base-url" in result.stdout
    assert "--litellm-api-key" in result.stdout


def test_check_ai_missing_config_fails_cleanly() -> None:
    result = runner.invoke(app, ["check-ai"])
    assert result.exit_code != 0
    assert "AI configuration is required" in result.stderr
    assert "Traceback" not in result.stderr + result.stdout


def test_check_ai_success_with_test_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic_ai.models.test import TestModel

    test_model = TestModel(custom_output_args={"ok": True, "message": "hello"})
    monkeypatch.setattr("law_discovery.ai.build_litellm_model", lambda _settings: test_model)

    result = runner.invoke(
        app,
        [
            "check-ai",
            "--model",
            "test-model",
            "--litellm-base-url",
            "http://localhost:4000/v1",
            "--litellm-api-key",
            "secret-key",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "test-model" in result.stdout
    assert "http://localhost:4000/v1" in result.stdout
    assert '"ok":true' in result.stdout.replace(" ", "") or '"ok": true' in result.stdout
    assert "hello" in result.stdout
    assert "secret-key" not in result.stdout
    assert "secret-key" not in result.stderr
    assert "AI connection check passed" in result.stdout


def test_check_ai_connection_failure_reports_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenAgent:
        def run_sync(self, *_args: object, **_kwargs: object) -> None:
            msg = "simulated connection failure"
            raise RuntimeError(msg)

    monkeypatch.setattr("law_discovery.ai.build_ai_check_agent", lambda _settings: BrokenAgent())

    result = runner.invoke(
        app,
        [
            "check-ai",
            "--model",
            "test-model",
            "--litellm-base-url",
            "http://localhost:4000/v1",
        ],
    )
    assert result.exit_code != 0
    assert "RuntimeError" in result.stderr
    assert "simulated connection failure" in result.stderr
    assert "Traceback" not in result.stderr + result.stdout
