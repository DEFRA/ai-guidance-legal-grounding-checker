from pathlib import Path

from law_proposition_extractor_pipeline.sources import SourceIngestionService  # type: ignore[import-untyped]


def _raw_source() -> dict[str, object]:
    return {
        "id": "src-eu-001",
        "title": "Example EU instrument",
        "jurisdiction": "EU",
        "citation": "EU-EXAMPLE-001",
        "kind": "regulation",
        "provenance": "demo.case_file",
        "as_of_date": "2026-04-01",
        "retrieved_at": "2026-04-27T18:00:00Z",
        "version_id": "eu-example-001@2026-04-01",
        "fragment_locator": "article:10",
        "review_status": "proposed",
        "text": "Article 10. Operators must maintain movement register records.",
        "metadata": {"cluster": "traceability"},
    }


def test_source_ingestion_fetches_and_caches_snapshots(tmp_path: Path) -> None:
    service = SourceIngestionService(cache_dir=tmp_path / "source-cache")
    result = service.ingest_sources([_raw_source()])

    assert len(result.sources) == 1
    assert len(result.snapshots) == 1
    assert len(result.fragments) == 1
    assert len(result.parse_traces) == 1
    assert len(result.reviews) == 1
    assert len(result.attempts) == 1
    assert result.traces[0]["decision"] == "fetched_then_cached"
    assert result.traces[0]["authority"] == "case_file"
    assert result.attempts[0].status == "success"
    assert result.attempts[0].method == "file_input"
    assert result.attempts[0].content_hash
    assert result.attempts[0].raw_artifact_uri
    assert result.reviews[0].metadata["cache_key"] == result.traces[0]["cache_key"]
    assert result.parse_traces[0].source_snapshot_id == result.snapshots[0].id
    assert result.parse_traces[0].output_fragment_ids == [result.fragments[0].id]
    assert result.parse_traces[0].status == "success"
    assert result.fragments[0].text_hash == result.fragments[0].fragment_hash
    assert result.fragments[0].fragment_id == result.fragments[0].id
    assert result.fragments[0].source_snapshot_id == result.snapshots[0].id


def test_source_ingestion_reuses_cache_for_same_authority_version_hash(tmp_path: Path) -> None:
    cache_dir = tmp_path / "source-cache"
    service = SourceIngestionService(cache_dir=cache_dir)

    first = service.ingest_sources([_raw_source()])
    second = service.ingest_sources([_raw_source()])

    assert first.traces[0]["decision"] == "fetched_then_cached"
    assert second.traces[0]["decision"] == "cache_hit"
    assert first.attempts[0].status == "success"
    assert second.attempts[0].status == "cache_hit"
    assert second.attempts[0].method == "cache"
    assert second.traces[0]["cache_key"] == first.traces[0]["cache_key"]
    assert second.snapshots[0].content_hash == first.snapshots[0].content_hash
