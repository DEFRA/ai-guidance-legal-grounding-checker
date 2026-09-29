from datetime import UTC, date, datetime

from law_proposition_extractor_domain import (
    Cluster,
    ComparisonRun,
    ConfidenceLevel,
    DivergenceAssessment,
    DivergenceFinding,
    DivergenceObservation,
    DivergenceType,
    Proposition,
    PropositionExtractionTrace,
    ReviewStatus,
    RunArtifact,
    SourceParseTrace,
    SourceFragment,
    SourceRecord,
    SourceSnapshot,
)


def test_divergence_assessment_defaults() -> None:
    assessment = DivergenceAssessment(
        id="div-001",
        proposition_id="prop-001",
        comparator_proposition_id="prop-002",
        jurisdiction_a="EU",
        jurisdiction_b="UK",
    )

    assert assessment.divergence_type == DivergenceType.UNKNOWN
    assert assessment.confidence == ConfidenceLevel.MEDIUM
    assert assessment.review_status == ReviewStatus.PROPOSED


def test_source_provenance_models_capture_versioned_text() -> None:
    record = SourceRecord(
        id="src-eu-001",
        title="EU Instrument",
        jurisdiction="EU",
        citation="EU-001",
        kind="regulation",
        authoritative_text="Article 10...",
        authoritative_locator="article:10",
        provenance="legislation.gov.uk",
        as_of_date=date(2026, 4, 1),
        content_hash="abc123",
        review_status=ReviewStatus.PROPOSED,
    )
    snapshot = SourceSnapshot(
        id="snap-src-eu-001-v1",
        source_record_id=record.id,
        version_id="v1",
        authoritative_text=record.authoritative_text,
        authoritative_locator=record.authoritative_locator,
        provenance=record.provenance,
        as_of_date=record.as_of_date,
        retrieved_at=datetime(2026, 4, 27, 18, 0, tzinfo=UTC),
        content_hash=record.content_hash or "",
    )
    fragment = SourceFragment(
        id="frag-src-eu-001-001",
        source_record_id=record.id,
        source_snapshot_id=snapshot.id,
        locator="article:10(1)",
        fragment_text="Operators must maintain a movement register.",
        fragment_hash="def456",
        review_status=ReviewStatus.ACCEPTED,
    )
    artifact = RunArtifact(
        id="artifact-run-001-assessments",
        run_id="run-001",
        artifact_type="divergence_assessments",
        provenance="pipeline.compare",
        content_hash="ghi789",
    )

    assert record.authoritative_locator == "article:10"
    assert snapshot.version_id == "v1"
    assert fragment.locator == "article:10(1)"
    assert fragment.fragment_id == fragment.id
    assert fragment.text_hash == fragment.fragment_hash
    assert artifact.artifact_type == "divergence_assessments"


def test_source_parse_trace_model_captures_parser_execution() -> None:
    parse_trace = SourceParseTrace(
        id="parse-trace-snap-src-eu-001-v1",
        source_record_id="src-eu-001",
        source_snapshot_id="snap-src-eu-001-v1",
        parser_name="case_file_parser",
        parser_version="v1",
        started_at=datetime(2026, 4, 27, 18, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 27, 18, 0, tzinfo=UTC),
        status="success",
        input_content_hash="abc123",
        output_fragment_ids=["frag-src-eu-001-001"],
        fragment_count=1,
        warning_count=0,
        error_count=0,
        warnings=[],
        errors=[],
        metrics={"fragment_count": 1},
    )

    assert parse_trace.status == "success"
    assert parse_trace.fragment_count == 1
    assert parse_trace.output_fragment_ids == ["frag-src-eu-001-001"]


def test_divergence_observation_defaults_finding_id_and_supports_assessment_alias() -> None:
    observation = DivergenceObservation(
        id="obs-001",
        proposition_id="prop-001",
        comparator_proposition_id="prop-002",
        jurisdiction_a="EU",
        jurisdiction_b="UK",
    )
    finding = DivergenceFinding(
        id=observation.finding_id or "missing",
        proposition_id=observation.proposition_id,
        comparator_proposition_id=observation.comparator_proposition_id,
        jurisdiction_a=observation.jurisdiction_a,
        jurisdiction_b=observation.jurisdiction_b,
    )
    assessment = DivergenceAssessment.model_validate(observation.model_dump(mode="json"))

    assert observation.finding_id == "finding-prop-001-prop-002"
    assert finding.id == observation.finding_id
    assert assessment.finding_id == observation.finding_id
    assert assessment.review_status == ReviewStatus.PROPOSED
    assert observation.supporting_source_fragment_ids == []
    assert observation.primary_source_fragment_id is None
    assert observation.comparator_source_fragment_id is None


def test_proposition_extraction_trace_model() -> None:
    trace = PropositionExtractionTrace(
        id="extract-trace:a1b2c3d4e5f67890",
        proposition_id="prop-001",
        proposition_key="instr-1:art-10:p001",
        source_record_id="src-001",
        source_snapshot_id="snap-001",
        source_fragment_id="frag-001",
        extraction_method="heuristic",
        extractor_name="law_proposition_extractor_pipeline.extract.heuristic",
        extractor_version="v1",
        status="success",
        evidence_text="Operators must keep records.",
        evidence_locator="article:10",
        confidence="medium",
        reason="Normative sentence selection.",
    )
    assert trace.extraction_method == "heuristic"
    assert trace.confidence == "medium"
    assert trace.proposition_key == "instr-1:art-10:p001"


def test_proposition_defaults_for_single_jurisdiction_inventory() -> None:
    proposition = Proposition(
        id="prop-001",
        topic_id="topic-001",
        source_record_id="src-001",
        jurisdiction="UK",
        proposition_text="Operators must keep records.",
        legal_subject="operator",
        action="keep records",
    )

    assert proposition.review_status == ReviewStatus.PROPOSED
    assert proposition.categories == []
    assert proposition.tags == []
    assert proposition.proposition_key is None
    assert proposition.proposition_version_id is None
    assert proposition.observed_in_run_id is None
    assert proposition.source_snapshot_id is None
    assert proposition.label == ""
    assert proposition.short_name == ""
    assert proposition.slug == ""
    assert proposition.proposition_tier.value == "substantive_rule"
    assert proposition.legal_effect_type.value == "recordkeeping"
    assert proposition.source_jurisdiction == "UK"
    assert proposition.territorial_application == []
    assert proposition.extent == []
    assert proposition.is_compliance_relevant is True
    assert proposition.is_comparison_anchor is True
    assert proposition.review_notes is None
    assert proposition.extraction_trace_id is None


def test_legacy_source_document_aliases_still_validate_during_migration() -> None:
    proposition = Proposition.model_validate(
        {
            "id": "prop-legacy-001",
            "topic_id": "topic-001",
            "source_document_id": "src-legacy-001",
            "jurisdiction": "UK",
            "proposition_text": "Operators must keep records.",
            "legal_subject": "operator",
            "action": "keep records",
        }
    )
    cluster = Cluster.model_validate(
        {
            "id": "cluster-001",
            "topic_id": "topic-001",
            "name": "legacy cluster",
            "source_document_ids": ["src-legacy-001"],
        }
    )
    run = ComparisonRun.model_validate(
        {
            "id": "run-001",
            "topic_id": "topic-001",
            "source_document_ids": ["src-legacy-001"],
        }
    )

    assert proposition.source_record_id == "src-legacy-001"
    assert cluster.source_record_ids == ["src-legacy-001"]
    assert run.source_record_ids == ["src-legacy-001"]
