from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from law_discovery.models import (
    CandidateSource,
    CategoryBrief,
    DiscoveryQuery,
    EvidenceSnippet,
    SourceType,
)

_LEGISLATION_SEARCH_PATH = "/legislation/search"
_LEGISLATION_SECTION_SEARCH_PATH = "/legislation/section/search"

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_NON_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({400, 401, 403, 404})

_RECOGNISED_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "act",
        "ukpga",
        "uksi",
        "assimilated_eu_law",
        "retained_eu_law",
        "case_law",
        "guidance",
        "explanatory_note",
        "explanatory_memorandum",
        "form",
        "register",
        "unknown",
    }
)


class LexAdapterError(Exception):
    """Raised when Lex adapter configuration or search fails."""


class LexSearchResult(BaseModel):
    raw: dict[str, Any]
    title: str | None = None
    uri: str | None = None
    citation: str | None = None
    snippet: str | None = None
    source_type: str | None = None
    score: float | None = None


class LexAdapter:
    """Thin adapter over Lex API / Lex Graph search."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int = 20,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 20.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("LAW_DISCOVERY_LEX_BASE_URL") or "").rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("LAW_DISCOVERY_LEX_API_KEY")
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._sleep = sleep or time.sleep

    def require_base_url(self) -> str:
        if not self.base_url:
            msg = (
                "LAW_DISCOVERY_LEX_BASE_URL is required for network discovery. "
                "Set LAW_DISCOVERY_LEX_BASE_URL, pass --lex-base-url, or use --no-network."
            )
            raise LexAdapterError(msg)
        return self.base_url

    def search(self, query: str, limit: int = 10) -> list[LexSearchResult]:
        payload = self._post_json(
            _LEGISLATION_SEARCH_PATH,
            {"query": query, "limit": limit},
            query=query,
        )
        raw_results = _extract_results(payload)
        return [_map_raw_to_lex_search_result(raw) for raw in raw_results]

    def _post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        query: str | None = None,
    ) -> Any:
        base_url = self.require_base_url()
        endpoint = f"{base_url}{path}"
        query_label = query or str(body.get("query", ""))

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        client_kwargs: dict[str, Any] = {"timeout": self.timeout_seconds}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        max_attempts = self.max_retries + 1
        last_error: str | None = None
        last_status_code: int | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(**client_kwargs) as client:
                    response = client.post(
                        endpoint,
                        json=body,
                        headers=headers,
                    )
                    if response.status_code in _NON_RETRYABLE_STATUS_CODES:
                        response.raise_for_status()
                    elif response.status_code in _RETRYABLE_STATUS_CODES:
                        if attempt < max_attempts:
                            wait = _wait_seconds_for_retry(
                                response,
                                attempt,
                                self.backoff_seconds,
                                self.max_backoff_seconds,
                            )
                            self._sleep(wait)
                            continue
                        last_status_code = response.status_code
                        last_error = (
                            f"HTTP {response.status_code} {response.reason_phrase}"
                        )
                        break

                    response.raise_for_status()
                    return response.json()
            except httpx.TimeoutException as exc:
                if attempt < max_attempts:
                    wait = _exponential_backoff_seconds(
                        attempt,
                        self.backoff_seconds,
                        self.max_backoff_seconds,
                    )
                    self._sleep(wait)
                    last_error = str(exc)
                    continue
                last_error = str(exc)
                break
            except httpx.TransportError as exc:
                if attempt < max_attempts:
                    wait = _exponential_backoff_seconds(
                        attempt,
                        self.backoff_seconds,
                        self.max_backoff_seconds,
                    )
                    self._sleep(wait)
                    last_error = str(exc)
                    continue
                last_error = str(exc)
                break
            except httpx.HTTPStatusError as exc:
                last_status_code = exc.response.status_code
                last_error = (
                    f"HTTP {exc.response.status_code} {exc.response.reason_phrase}"
                )
                break
            except ValueError as exc:
                msg = f"Lex search returned invalid JSON: {exc}"
                raise LexAdapterError(msg) from exc

        status_part = f" (HTTP {last_status_code})" if last_status_code is not None else ""
        msg = (
            f"Lex search failed after {max_attempts} attempt(s) for query "
            f"{query_label!r} at {endpoint}{status_part}: {last_error}"
        )
        raise LexAdapterError(msg)


def _exponential_backoff_seconds(
    attempt: int,
    backoff_seconds: float,
    max_backoff_seconds: float,
) -> float:
    wait = backoff_seconds * (2 ** (attempt - 1))
    return min(wait, max_backoff_seconds)


def _parse_retry_after_seconds(retry_after: str) -> float | None:
    try:
        return float(retry_after)
    except ValueError:
        return None


def _wait_seconds_for_retry(
    response: httpx.Response,
    attempt: int,
    backoff_seconds: float,
    max_backoff_seconds: float,
) -> float:
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            parsed = _parse_retry_after_seconds(retry_after)
            if parsed is not None:
                return min(parsed, max_backoff_seconds)
    return _exponential_backoff_seconds(attempt, backoff_seconds, max_backoff_seconds)


def _extract_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        results = payload
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        results = payload["results"]
    else:
        msg = "Lex search response must be a list or an object with a 'results' list."
        raise LexAdapterError(msg)

    normalised: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            normalised.append(item)
    return normalised


def _first_str(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_score(raw: dict[str, Any]) -> float | None:
    for key in ("score", "relevance_score"):
        value = raw.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _map_raw_to_lex_search_result(raw: dict[str, Any]) -> LexSearchResult:
    return LexSearchResult(
        raw=raw,
        title=_first_str(raw, "title", "name"),
        uri=_first_str(raw, "uri", "url", "canonical_uri", "legislation_id", "id"),
        citation=_first_str(raw, "citation", "reference"),
        snippet=_first_str(raw, "snippet", "text", "summary"),
        source_type=_first_str(raw, "source_type", "type", "legislation_type"),
        score=_first_score(raw),
    )


def infer_source_type_from_uri(uri: str | None) -> str:
    if not uri:
        return "unknown"
    normalised = uri.lower()
    if "/uksi/" in normalised:
        return "uksi"
    if "/ukpga/" in normalised:
        return "ukpga"
    if "/eur/" in normalised:
        return "assimilated_eu_law"
    return "unknown"


def _normalise_authority_source_id(value: str) -> str | None:
    trimmed = value.strip().strip("/")
    match = re.match(
        r"^(?P<series>[a-z0-9]+)/(?P<year>\d{4})/(?P<number>\d+)$",
        trimmed,
        re.IGNORECASE,
    )
    if not match:
        return None
    series = match.group("series").lower()
    year = match.group("year")
    number = str(int(match.group("number")))
    return f"{series}/{year}/{number}"


def normalise_legislation_uri(uri: str | None) -> str | None:
    """Collapse legislation.gov.uk URI variants to ``http://www.legislation.gov.uk/id/{asid}``."""
    if not uri or not str(uri).strip():
        return None
    try:
        parsed = urlparse(str(uri).strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if "legislation.gov.uk" not in parsed.netloc.lower():
        return None
    path = parsed.path.strip("/")
    if path.startswith("id/"):
        path = path[3:]
    if path.endswith("/data.xml"):
        path = path[: -len("/data.xml")]
    if path.endswith("/made"):
        path = path[: -len("/made")]
    asid = _normalise_authority_source_id(path)
    if not asid:
        return None
    return f"http://www.legislation.gov.uk/id/{asid}"


def _recognise_source_type(raw: str | None) -> SourceType:
    if not raw:
        return "unknown"
    normalised = raw.lower()
    if normalised in _RECOGNISED_SOURCE_TYPES:
        return normalised  # type: ignore[return-value]
    if "uksi" in normalised:
        return "uksi"
    if "ukpga" in normalised or normalised == "act":
        return "ukpga"
    if "guidance" in normalised:
        return "guidance"
    if "case" in normalised:
        return "case_law"
    return "unknown"


def _resolve_source_type(result: LexSearchResult) -> SourceType:
    from_uri = infer_source_type_from_uri(result.uri)
    if from_uri != "unknown":
        return from_uri  # type: ignore[return-value]
    return _recognise_source_type(result.source_type)


def _stable_source_id(
    uri: str | None,
    title: str,
    citation: str | None,
    query: str,
) -> str:
    identity_uri = normalise_legislation_uri(uri) or uri
    if identity_uri:
        digest = hashlib.sha256(identity_uri.encode("utf-8")).hexdigest()[:16]
    else:
        payload = f"{title}|{citation or ''}|{query}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"lex-{digest}"


def normalise_lex_result_to_candidate(
    result: LexSearchResult,
    category: CategoryBrief,
    query: DiscoveryQuery,
) -> CandidateSource:
    title = result.title or "Untitled Lex result"
    canonical_uri = normalise_legislation_uri(result.uri) or result.uri
    evidence: list[EvidenceSnippet] = []
    if result.title:
        evidence.append(EvidenceSnippet(evidence_type="title", text=result.title, uri=canonical_uri))
    if result.snippet:
        evidence.append(
            EvidenceSnippet(
                evidence_type="text_snippet",
                text=result.snippet,
                uri=canonical_uri,
            )
        )

    return CandidateSource(
        source_id=_stable_source_id(result.uri, title, result.citation, query.query),
        title=title,
        citation=result.citation,
        source_type=_resolve_source_type(result),
        canonical_uri=canonical_uri,
        source_system="lex",
        jurisdiction_extent=list(category.jurisdiction_hints),
        relationship_to_category="unknown",
        match_basis=["lex_search"],
        matched_terms=[query.query],
        evidence=evidence,
        confidence="unknown",
        review_status="unreviewed",
    )
