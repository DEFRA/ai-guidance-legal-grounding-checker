from __future__ import annotations

import json

import httpx
import pytest

from law_discovery.lex_adapter import (
    LexAdapter,
    LexAdapterError,
    LexSearchResult,
    infer_source_type_from_uri,
    normalise_legislation_uri,
    normalise_lex_result_to_candidate,
)
from law_discovery.models import CategoryBrief, DiscoveryQuery


@pytest.fixture(autouse=True)
def clear_lex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAW_DISCOVERY_LEX_BASE_URL", raising=False)
    monkeypatch.delenv("LAW_DISCOVERY_LEX_API_KEY", raising=False)


def test_infer_source_type_from_uri_detects_uksi() -> None:
    assert (
        infer_source_type_from_uri("https://www.legislation.gov.uk/uksi/2009/1741")
        == "uksi"
    )


def test_infer_source_type_from_uri_detects_ukpga() -> None:
    assert (
        infer_source_type_from_uri("https://www.legislation.gov.uk/ukpga/2006/45")
        == "ukpga"
    )


def test_infer_source_type_from_uri_detects_eur() -> None:
    assert (
        infer_source_type_from_uri("https://www.legislation.gov.uk/eur/2015/262")
        == "assimilated_eu_law"
    )


def test_normalise_lex_result_to_candidate_creates_candidate_source() -> None:
    category = CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Horse identification rules",
        jurisdiction_hints=["England"],
    )
    query = DiscoveryQuery(query="horse passport", query_type="synonym")
    result = LexSearchResult(
        raw={"title": "Horse Passports Regulations 2009"},
        title="Horse Passports Regulations 2009",
        uri="https://www.legislation.gov.uk/uksi/2009/1741",
        citation="SI 2009/1741",
        snippet="Regulations relating to horse passports.",
        source_type="uksi",
    )

    candidate = normalise_lex_result_to_candidate(result, category, query)

    assert candidate.title == "Horse Passports Regulations 2009"
    assert candidate.source_system == "lex"
    assert candidate.source_type == "uksi"
    assert candidate.canonical_uri == "http://www.legislation.gov.uk/id/uksi/2009/1741"
    assert candidate.citation == "SI 2009/1741"
    assert candidate.match_basis == ["lex_search"]
    assert candidate.matched_terms == ["horse passport"]
    assert candidate.confidence == "unknown"
    assert candidate.review_status == "unreviewed"
    assert candidate.relationship_to_category == "unknown"
    assert candidate.jurisdiction_extent == ["England"]
    assert len(candidate.evidence) == 2


def test_source_id_is_deterministic() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test",
        description="Desc",
    )
    query = DiscoveryQuery(query="horse passport", query_type="synonym")
    result = LexSearchResult(
        raw={},
        title="Horse Passports Regulations 2009",
        uri="https://www.legislation.gov.uk/uksi/2009/1741",
        citation="SI 2009/1741",
    )

    first = normalise_lex_result_to_candidate(result, category, query)
    second = normalise_lex_result_to_candidate(result, category, query)

    assert first.source_id == second.source_id
    assert first.source_id.startswith("lex-")


def test_source_id_stable_across_legislation_uri_variants() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test",
        description="Desc",
    )
    query = DiscoveryQuery(query="slurry", query_type="synonym")
    variants = [
        "http://www.legislation.gov.uk/id/uksi/2015/668",
        "https://www.legislation.gov.uk/id/uksi/2015/668",
        "https://www.legislation.gov.uk/uksi/2015/668",
        "https://www.legislation.gov.uk/uksi/2015/668/data.xml",
        "http://www.legislation.gov.uk/uksi/2015/0668",
    ]
    ids = {
        normalise_lex_result_to_candidate(
            LexSearchResult(
                raw={},
                title="Nitrate Pollution Prevention Regulations 2015",
                uri=uri,
                citation="SI 2015/668",
            ),
            category,
            query,
        ).source_id
        for uri in variants
    }
    assert len(ids) == 1
    assert ids.pop().startswith("lex-")
    canonicals = {
        normalise_legislation_uri(uri)
        for uri in variants
    }
    assert canonicals == {"http://www.legislation.gov.uk/id/uksi/2015/668"}


def test_missing_lex_base_url_raises_when_search_called() -> None:
    adapter = LexAdapter()
    with pytest.raises(LexAdapterError, match="LAW_DISCOVERY_LEX_BASE_URL"):
        adapter.search("horse passport")


def test_require_base_url_includes_no_network_hint() -> None:
    adapter = LexAdapter()
    with pytest.raises(LexAdapterError, match="--no-network"):
        adapter.require_base_url()


def test_search_uses_post_legislation_search_with_json_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content.decode("utf-8"))
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": (
                            "The Animal By-Products (Enforcement) (England) Regulations 2013"
                        ),
                        "type": "uksi",
                        "year": 2013,
                        "number": 2952,
                        "score": 0.92,
                    }
                ],
                "total": 1,
            },
        )

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    results = adapter.search("animal by-products", limit=10)

    assert captured["method"] == "POST"
    assert captured["path"] == "/legislation/search"
    assert captured["json"] == {"query": "animal by-products", "limit": 10}
    assert captured["authorization"] == "Bearer test-key"
    assert len(results) == 1
    assert (
        results[0].title
        == "The Animal By-Products (Enforcement) (England) Regulations 2013"
    )
    assert results[0].source_type == "uksi"
    assert results[0].score == 0.92


def test_search_maps_uksi_type_to_candidate_source_type() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": (
                            "The Animal By-Products (Enforcement) (England) Regulations 2013"
                        ),
                        "type": "uksi",
                        "year": 2013,
                        "number": 2952,
                        "score": 0.92,
                    }
                ],
                "total": 1,
            },
        )

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        transport=httpx.MockTransport(handler),
    )
    category = CategoryBrief(
        category_id="animal_by_products",
        label="Animal by-products",
        description="Traceability and controls",
    )
    query = DiscoveryQuery(query="animal by-products", query_type="synonym")

    results = adapter.search("animal by-products")
    candidate = normalise_lex_result_to_candidate(results[0], category, query)

    assert candidate.source_type == "uksi"


def test_search_rejects_unexpected_response_shape() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LexAdapterError, match="results"):
        adapter.search("animal by-products")


def _success_json() -> dict[str, object]:
    return {"results": [{"title": "Example Regulations 2010"}]}


def test_search_retries_429_with_retry_after_then_succeeds() -> None:
    call_count = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, headers={"Retry-After": "5"})
        return httpx.Response(200, json=_success_json())

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )

    results = adapter.search("horse passport")

    assert call_count == 2
    assert sleeps == [5.0]
    assert len(results) == 1
    assert results[0].title == "Example Regulations 2010"


def test_search_retries_503_with_exponential_backoff_then_succeeds() -> None:
    call_count = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=_success_json())

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        transport=httpx.MockTransport(handler),
        backoff_seconds=2.0,
        sleep=sleeps.append,
    )

    results = adapter.search("horse passport")

    assert call_count == 2
    assert sleeps == [2.0]
    assert len(results) == 1


def test_search_does_not_retry_404() -> None:
    call_count = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(404)

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )

    with pytest.raises(LexAdapterError, match="HTTP 404"):
        adapter.search("missing query")

    assert call_count == 1
    assert sleeps == []


def test_search_retries_timeout_then_succeeds() -> None:
    call_count = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(200, json=_success_json())

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )

    results = adapter.search("horse passport")

    assert call_count == 2
    assert sleeps == [1.0]
    assert len(results) == 1


def test_search_raises_after_all_retries_exhausted() -> None:
    call_count = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503)

    adapter = LexAdapter(
        base_url="https://lex.example.test",
        transport=httpx.MockTransport(handler),
        max_retries=3,
        sleep=sleeps.append,
    )

    with pytest.raises(LexAdapterError) as exc_info:
        adapter.search("horse passport")

    assert call_count == 4
    assert sleeps == [1.0, 2.0, 4.0]
    message = str(exc_info.value)
    assert "4 attempt(s)" in message
    assert "horse passport" in message
    assert "/legislation/search" in message
    assert "HTTP 503" in message
