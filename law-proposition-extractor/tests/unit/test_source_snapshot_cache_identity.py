"""Snapshot file cache must not key only on content_hash — legal identity is part of the key."""

from __future__ import annotations

from pathlib import Path

from law_proposition_extractor_pipeline.sources.adapters import SourcePayload
from law_proposition_extractor_pipeline.sources.cache import SnapshotCache, build_cache_key


def _payload(jurisdiction: str, citation: str) -> SourcePayload:
    return SourcePayload(
        title="Instrument",
        jurisdiction=jurisdiction,
        citation=citation,
        kind="regulation",
        authoritative_text="identical text body",
        authoritative_locator="article:10",
        provenance="test",
        as_of_date=None,
        retrieved_at=None,
        source_url=f"https://example.test/{jurisdiction}",
        review_status="proposed",
        metadata={},
    )


def test_build_cache_key_varies_with_cache_identity_key() -> None:
    k_eu = build_cache_key("case_file", "v1", "deadbeef", cache_identity_key="eu|eu-cite")
    k_uk = build_cache_key("case_file", "v1", "deadbeef", cache_identity_key="uk|uk-cite")
    assert k_eu != k_uk


def test_snapshot_cache_get_is_scoped_to_cache_identity_key(tmp_path: Path) -> None:
    cache = SnapshotCache(tmp_path)
    body_hash = "abcd" * 16
    cache.put(
        authority="case_file",
        version_id="v1",
        content_hash=body_hash,
        cache_identity_key="eu|eu-same",
        payload=_payload("EU", "EU-SAME"),
    )
    hit = cache.get(
        authority="case_file",
        version_id="v1",
        content_hash=body_hash,
        cache_identity_key="eu|eu-same",
    )
    miss = cache.get(
        authority="case_file",
        version_id="v1",
        content_hash=body_hash,
        cache_identity_key="uk|uk-same",
    )
    assert hit is not None
    assert hit.payload.jurisdiction == "EU"
    assert miss is None
