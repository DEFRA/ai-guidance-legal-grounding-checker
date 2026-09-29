from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from law_discovery.ai import CandidateTriageAssessment
from law_discovery.cli import app
from law_discovery.discovery_service import apply_triage_assessment_to_candidate
from law_discovery.models import (
    CandidateSource,
    CandidateTriageMetadata,
    CategoryBrief,
    DiscoveryRun,
    SourceRegister,
)
from law_discovery.triage_helpers import (
    ai_register_review_status,
    discovery_run_has_ai_triage,
    format_top_candidate_line,
    normalize_triage_assessment,
    select_top_candidates,
)

runner = CliRunner()


def _triage_metadata(
    *,
    review_priority: str = "likely_accept",
    recommended_action: str = "accept_candidate",
    confidence_after_ai: str = "high",
) -> CandidateTriageMetadata:
    return CandidateTriageMetadata(
        relevance="high",
        review_priority=review_priority,  # type: ignore[arg-type]
        relationship_to_category="directly_regulates",
        confidence_after_ai=confidence_after_ai,  # type: ignore[arg-type]
        recommended_action=recommended_action,  # type: ignore[arg-type]
        rationale="Test rationale.",
    )


def test_discovery_run_has_ai_triage_requires_structured_field() -> None:
    assert not discovery_run_has_ai_triage(
        [CandidateSource(source_id="a", title="A", notes="AI triage rationale: x")]
    )
    assert discovery_run_has_ai_triage(
        [CandidateSource(source_id="b", title="B", ai_triage=_triage_metadata())]
    )


def test_apply_triage_stores_ai_triage_and_updates_confidence() -> None:
    candidate = CandidateSource(
        source_id="lex-1",
        title="Slurry regs",
        confidence="high",
    )
    assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="low",
        review_priority="likely_reject",
        relationship_to_category="possibly_relevant",
        confidence_after_ai="low",
        rationale="Unrelated local act.",
        recommended_action="reject_candidate",
    )

    updated = apply_triage_assessment_to_candidate(candidate, assessment)

    assert updated.ai_triage is not None
    assert updated.ai_triage.review_priority == "likely_reject"
    assert updated.confidence == "low"
    assert updated.ai_triage.confidence_after_ai == "low"


def test_likely_reject_does_not_remain_high_confidence() -> None:
    candidate = CandidateSource(
        source_id="lex-1",
        title="Local Act",
        confidence="high",
    )
    assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="not_relevant",
        review_priority="likely_reject",
        relationship_to_category="unknown",
        confidence_after_ai="high",
        rationale="False positive.",
        recommended_action="reject_candidate",
    )

    updated = apply_triage_assessment_to_candidate(candidate, assessment)

    assert updated.confidence == "low"
    assert updated.ai_triage is not None
    assert updated.ai_triage.confidence_after_ai == "low"
    assert updated.ai_triage.review_priority == "likely_reject"
    assert updated.ai_triage.assessment_confidence == "high"


def test_reject_candidate_normalizes_high_relevance_confidence() -> None:
    assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="low",
        review_priority="likely_reject",
        relationship_to_category="possibly_relevant",
        confidence_after_ai="high",
        rationale="Adjacent but not core.",
        recommended_action="reject_candidate",
    )

    normalized = normalize_triage_assessment(assessment)

    assert normalized.confidence_after_ai == "low"
    assert normalized.assessment_confidence == "high"


def test_likely_accept_high_relevance_keeps_high_confidence() -> None:
    assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="high",
        review_priority="likely_accept",
        relationship_to_category="directly_regulates",
        confidence_after_ai="high",
        rationale="Core instrument.",
        recommended_action="accept_candidate",
    )

    normalized = normalize_triage_assessment(assessment)
    updated = apply_triage_assessment_to_candidate(
        CandidateSource(source_id="lex-1", title="NVZ Regulations"),
        assessment,
    )

    assert normalized.confidence_after_ai == "high"
    assert updated.confidence == "high"


def test_park_contextual_low_relevance_allows_low_or_medium() -> None:
    for confidence in ("low", "medium"):
        assessment = CandidateTriageAssessment(
            source_id="lex-1",
            relevance="low",
            review_priority="park_contextual",
            relationship_to_category="explains",
            confidence_after_ai=confidence,  # type: ignore[arg-type]
            rationale="Contextual guidance.",
            recommended_action="park",
        )

        normalized = normalize_triage_assessment(assessment)

        assert normalized.confidence_after_ai == confidence


def test_needs_human_review_uncertain_allows_unknown_or_medium() -> None:
    for confidence in ("unknown", "medium"):
        assessment = CandidateTriageAssessment(
            source_id="lex-1",
            relevance="uncertain",
            review_priority="needs_human_review",
            relationship_to_category="possibly_relevant",
            confidence_after_ai=confidence,  # type: ignore[arg-type]
            rationale="Thin evidence.",
            recommended_action="needs_more_research",
        )

        normalized = normalize_triage_assessment(assessment)

        assert normalized.confidence_after_ai == confidence


def test_uncertain_relevance_downgrades_high_confidence() -> None:
    assessment = CandidateTriageAssessment(
        source_id="lex-1",
        relevance="uncertain",
        review_priority="needs_human_review",
        relationship_to_category="unknown",
        confidence_after_ai="high",
        rationale="Ambiguous title.",
        recommended_action="needs_more_research",
    )

    normalized = normalize_triage_assessment(assessment)

    assert normalized.confidence_after_ai == "unknown"


def test_select_top_candidates_prefers_likely_accept_over_likely_reject() -> None:
    likely_accept = CandidateSource(
        source_id="a",
        title="NVZ Regulations",
        ai_triage=_triage_metadata(review_priority="likely_accept"),
    )
    likely_reject = CandidateSource(
        source_id="b",
        title="Local Road Act",
        confidence="high",
        ai_triage=_triage_metadata(
            review_priority="likely_reject",
            recommended_action="reject_candidate",
            confidence_after_ai="low",
        ),
    )

    top = select_top_candidates([likely_reject, likely_accept], limit=5)

    assert top[0].source_id == "a"
    assert all(
        c.ai_triage is not None and c.ai_triage.review_priority != "likely_reject"
        for c in top
        if c.source_id != "b"
    )


def test_format_top_candidate_line_includes_triage_fields() -> None:
    candidate = CandidateSource(
        source_id="a",
        title="NVZ Regulations",
        ai_triage=_triage_metadata(),
    )

    line = format_top_candidate_line(candidate)

    assert "likely_accept" in line
    assert "accept_candidate" in line
    assert "NVZ Regulations" in line


def test_ai_register_review_status_buckets() -> None:
    accept = CandidateSource(
        source_id="a",
        title="Core",
        ai_triage=_triage_metadata(),
    )
    reject = CandidateSource(
        source_id="b",
        title="Noise",
        ai_triage=_triage_metadata(
            review_priority="likely_reject",
            recommended_action="reject_candidate",
            confidence_after_ai="low",
        ),
    )
    park = CandidateSource(
        source_id="c",
        title="Context",
        ai_triage=_triage_metadata(
            review_priority="park_contextual",
            recommended_action="park",
            confidence_after_ai="medium",
        ),
    )
    review = CandidateSource(
        source_id="d",
        title="Unclear",
        ai_triage=_triage_metadata(
            review_priority="needs_human_review",
            recommended_action="needs_more_research",
            confidence_after_ai="unknown",
        ),
    )

    assert ai_register_review_status(accept) == "accepted"
    assert ai_register_review_status(reject) == "rejected"
    assert ai_register_review_status(park) == "parked"
    assert ai_register_review_status(review) == "needs_more_research"


def _triaged_run(tmp_path: Path) -> tuple[Path, DiscoveryRun]:
    run = DiscoveryRun(
        run_id="law-discovery-run-triage",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        category=CategoryBrief(
            category_id="slurry",
            label="Slurry",
            description="Test",
        ),
        query_plan=[],
        candidate_sources=[
            CandidateSource(
                source_id="accept",
                title="NVZ Action Programme",
                ai_triage=_triage_metadata(),
            ),
            CandidateSource(
                source_id="reject",
                title="Local Corporation Act",
                ai_triage=_triage_metadata(
                    review_priority="likely_reject",
                    recommended_action="reject_candidate",
                    confidence_after_ai="low",
                ),
            ),
            CandidateSource(
                source_id="park",
                title="EU contextual",
                ai_triage=_triage_metadata(
                    review_priority="needs_human_review",
                    recommended_action="park",
                    confidence_after_ai="medium",
                ),
            ),
        ],
    )
    path = tmp_path / "run.json"
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return path, run


def test_make_register_accept_ai_likely_accept(tmp_path: Path) -> None:
    run_path, _run = _triaged_run(tmp_path)
    register_path = tmp_path / "register.json"

    result = runner.invoke(
        app,
        [
            "make-register",
            str(run_path),
            "--output",
            str(register_path),
            "--accept-ai-likely-accept",
        ],
    )
    assert result.exit_code == 0, result.stderr
    register = SourceRegister.model_validate_json(register_path.read_text(encoding="utf-8"))
    assert [s.source_id for s in register.accepted_sources] == ["accept"]
    assert [s.source_id for s in register.rejected_sources] == ["reject"]
    assert [s.source_id for s in register.parked_sources] == ["park"]
    assert register.metadata.get("accept_ai_likely_accept") is True


def test_make_register_accept_ai_fails_without_triage(tmp_path: Path) -> None:
    run = DiscoveryRun(
        run_id="law-discovery-run-plain",
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
        category=CategoryBrief(category_id="x", label="X", description="Test"),
        query_plan=[],
        candidate_sources=[
            CandidateSource(source_id="a", title="Example", confidence="high"),
        ],
    )
    run_path = tmp_path / "run.json"
    run_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "make-register",
            str(run_path),
            "--output",
            str(tmp_path / "register.json"),
            "--accept-ai-likely-accept",
        ],
    )
    assert result.exit_code != 0
    assert "no AI triage metadata" in result.stderr


def test_make_register_rejects_both_accept_flags(tmp_path: Path) -> None:
    run_path, _run = _triaged_run(tmp_path)
    result = runner.invoke(
        app,
        [
            "make-register",
            str(run_path),
            "--output",
            str(tmp_path / "register.json"),
            "--accept-high-confidence",
            "--accept-ai-likely-accept",
        ],
    )
    assert result.exit_code != 0
    assert "not both" in result.stderr
