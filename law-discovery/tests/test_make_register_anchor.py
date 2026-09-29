from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from law_discovery.cli import app
from law_discovery.models import CandidateSource, CategoryBrief, DiscoveryRun, SourceRegister, load_category_brief

runner = CliRunner()


def _equine_passports_category(examples_dir: Path) -> CategoryBrief:
    return load_category_brief(examples_dir / "categories" / "equine_passports.category.json")


def _write_run(tmp_path: Path, category: CategoryBrief, candidates: list[CandidateSource]) -> Path:
    run = DiscoveryRun(
        run_id="law-discovery-run-anchor-test",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        category=category,
        query_plan=[],
        candidate_sources=candidates,
    )
    run_path = tmp_path / "run.json"
    run_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run_path


def test_make_register_only_auto_accepts_anchor_passing_high_confidence(
    tmp_path: Path, examples_dir: Path
) -> None:
    category = _equine_passports_category(examples_dir)
    run_path = _write_run(
        tmp_path,
        category,
        [
            CandidateSource(
                source_id="anchor-pass",
                title="The Equine Identification (England) Regulations 2018",
                confidence="high",
            ),
            CandidateSource(
                source_id="anchor-fail",
                title="Coal Mines Act 1911",
                confidence="high",
                matched_terms=["horse"],
            ),
            CandidateSource(
                source_id="low",
                title="Other Act",
                confidence="low",
            ),
        ],
    )
    register_path = tmp_path / "register.json"

    result = runner.invoke(
        app,
        [
            "make-register",
            str(run_path),
            "--output",
            str(register_path),
            "--accept-high-confidence",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.stderr

    register = SourceRegister.model_validate_json(register_path.read_text(encoding="utf-8"))
    assert [s.source_id for s in register.accepted_sources] == ["anchor-pass"]
    assert register.metadata["high_confidence_anchor_pass"] == 1
    assert register.metadata["high_confidence_anchor_fail"] == 1
    assert register.metadata["auto_accepted"] == 1
    assert register.metadata["held_for_review"] == 1

    held = next(s for s in register.parked_sources if s.source_id == "anchor-fail")
    assert held.review_status == "needs_more_research"


def test_make_register_warns_when_many_auto_accepts_without_yes(
    tmp_path: Path, examples_dir: Path
) -> None:
    category = _equine_passports_category(examples_dir)
    candidates = [
        CandidateSource(
            source_id=f"core-{index}",
            title=f"The Equine Identification (England) Regulations {2010 + index}",
            confidence="high",
        )
        for index in range(51)
    ]
    run_path = _write_run(tmp_path, category, candidates)
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
    assert result.exit_code != 0
    assert "51" in result.stderr or "50" in result.stderr
    assert "Equine Identification" in result.stderr
    assert not register_path.exists()


def test_make_register_proceeds_with_yes_when_many_auto_accepts(
    tmp_path: Path, examples_dir: Path
) -> None:
    category = _equine_passports_category(examples_dir)
    candidates = [
        CandidateSource(
            source_id=f"core-{index}",
            title=f"The Equine Identification (England) Regulations {2010 + index}",
            confidence="high",
        )
        for index in range(51)
    ]
    run_path = _write_run(tmp_path, category, candidates)
    register_path = tmp_path / "register.json"

    result = runner.invoke(
        app,
        [
            "make-register",
            str(run_path),
            "--output",
            str(register_path),
            "--accept-high-confidence",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.stderr
    register = SourceRegister.model_validate_json(register_path.read_text(encoding="utf-8"))
    assert register.metadata["auto_accepted"] == 51
