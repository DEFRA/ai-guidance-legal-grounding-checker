import re
from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Protocol, Sequence
from urllib.parse import quote_plus, urlparse

from .search_aliases import (
    authority_source_ids_hinted_for_query,
    squash_ws,
    summarise_query_resolution,
)
from urllib.request import Request, urlopen
from xml.etree import ElementTree


class SourceSearchError(ValueError):
    """Raised when source discovery/search fails."""


@dataclass(frozen=True)
class SourceSearchCandidate:
    title: str
    citation: str
    source_identifier: str
    authority_source_id: str
    jurisdiction: str
    authority: str
    canonical_source_url: str
    provenance: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceSearchProvider(Protocol):
    provider_name: str

    def search(self, *, query: str, limit: int = 10) -> list[SourceSearchCandidate]: ...


def _merge_candidates_by_authority(rows: Sequence[SourceSearchCandidate]) -> list[SourceSearchCandidate]:
    seen: dict[str, SourceSearchCandidate] = {}
    for row in rows:
        key = row.authority_source_id.lower()
        seen.setdefault(key, row)
    return list(seen.values())


def registry_entries_as_search_candidates(entries: Sequence[dict[str, Any]], *, raw_query: str) -> list[SourceSearchCandidate]:
    hints = authority_source_ids_hinted_for_query(raw_query)
    hint_lower = [h.strip().lower() for h in hints]
    normalized_query = squash_ws(raw_query.strip().lower())
    out: list[SourceSearchCandidate] = []

    seen: set[str] = set()

    def _authority_url(aid_l: str) -> str | None:
        if not aid_l:
            return None
        for prefix in ("eur/", "ukpga/", "uksi/", "asc/", "wsi/", "ssi/", "nia/", "nisr/", "asp/", "anaw/"):
            if aid_l.startswith(prefix):
                return f"https://www.legislation.gov.uk/{aid_l.strip('/')}"
        return None

    for entry in entries:
        reference = entry.get("reference") if isinstance(entry.get("reference"), dict) else None
        if not reference:
            continue
        authority_source_id = str(reference.get("authority_source_id", "")).strip()
        authority_source_lower = authority_source_id.lower()

        tit = str(reference.get("title") or "").lower()
        cit = str(reference.get("citation") or "").lower()

        matched = False
        for h in hint_lower:
            if h and h == authority_source_lower:
                matched = True
                break

        if not matched and normalized_query:
            matched = (
                normalized_query == authority_source_lower
                or normalized_query in authority_source_lower
                or normalized_query in tit
                or normalized_query in cit
            )

        if not matched:
            continue

        if authority_source_lower in seen:
            continue
        canonical = reference.get("source_url") or ""
        inferred = _authority_url(authority_source_lower)
        canonical_url = str(canonical).strip() or (inferred if inferred else "")

        out.append(
            SourceSearchCandidate(
                title=str(reference.get("title") or authority_source_id or "Untitled registry source"),
                citation=str(reference.get("citation") or ""),
                source_identifier=str(authority_source_id or ""),
                authority_source_id=str(authority_source_id or ""),
                jurisdiction=str(reference.get("jurisdiction") or ""),
                authority=str(reference.get("authority") or "registry"),
                canonical_source_url=str(canonical_url),
                provenance="registry.match",
            )
        )
        if authority_source_lower:
            seen.add(authority_source_lower)

    return out


def _local_name(tag_name: str) -> str:
    if "}" in tag_name:
        return tag_name.split("}", maxsplit=1)[1]
    return tag_name


def _first_text(root: ElementTree.Element, candidates: set[str]) -> str | None:
    for node in root.iter():
        if _local_name(node.tag) in candidates:
            text = "".join(node.itertext()).strip()
            if text:
                return " ".join(text.split())
    return None


def _jurisdiction_from_series(series: str) -> str:
    series_lower = series.lower()
    if series_lower in {"asp", "ssi"}:
        return "Scotland"
    if series_lower in {"anaw", "wsi", "asc"}:
        return "Wales"
    if series_lower in {"nia", "nisr"}:
        return "Northern Ireland"
    if series_lower == "eur":
        return "EU"
    return "UK"


def _normalize_authority_source_id(value: str) -> str | None:
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


def _source_id_from_legislation_url(value: str) -> str | None:
    try:
        parsed = urlparse(value.strip())
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
    return _normalize_authority_source_id(path)


class LegislationGovUkSourceSearchProvider:
    provider_name = "legislation_gov_uk"
    _series_order: ClassVar[list[str]] = [
        "eur",
        "ukpga",
        "uksi",
        "asp",
        "ssi",
        "wsi",
        "nisr",
        "nia",
        "anaw",
    ]

    def __init__(
        self,
        *,
        fetch_xml: Any | None = None,
        fetch_html: Any | None = None,
    ) -> None:
        self.fetch_xml = fetch_xml or self._fetch_xml_from_network
        self.fetch_html = fetch_html or self._fetch_html_from_network

    def search(self, *, query: str, limit: int = 10) -> list[SourceSearchCandidate]:
        search_query = query.strip()
        if len(search_query) < 2:
            raise SourceSearchError("Source search query must be at least 2 characters.")
        limited = min(max(limit, 1), 25)
        try:
            by_url = _source_id_from_legislation_url(search_query)
            if by_url:
                resolved = self._resolve_candidate(authority_source_id=by_url)
                return [resolved] if resolved else []

            hinted_ids = authority_source_ids_hinted_for_query(search_query)
            hinted_results: list[SourceSearchCandidate] = []
            for authority_source_id in hinted_ids:
                resolved = self._resolve_candidate(authority_source_id=authority_source_id)
                if resolved is None:
                    continue
                hinted_results.append(resolved)
                if len(hinted_results) >= limited:
                    return hinted_results

            identifier_candidates = self._resolve_identifier_candidates(search_query, limit=limited)
            if identifier_candidates:
                merged = _merge_candidates_by_authority(identifier_candidates + hinted_results)[:limited]
                return merged

            title_limit = max(1, limited - len(hinted_results))
            title_hits = self._search_by_title(search_query, limit=title_limit) if title_limit > 0 else []
            merged_title = _merge_candidates_by_authority(list(hinted_results) + list(title_hits))
            return merged_title[:limited]
        except SourceSearchError:
            raise
        except Exception as exc:
            raise SourceSearchError(
                "legislation.gov.uk search failed; try identifier/citation or URL form."
            ) from exc

    def _resolve_identifier_candidates(
        self, query: str, *, limit: int
    ) -> list[SourceSearchCandidate]:
        normalized = query.strip().lower()
        full_id = _normalize_authority_source_id(normalized)
        if full_id:
            candidate = self._resolve_candidate(authority_source_id=full_id)
            return [candidate] if candidate else []

        match = re.match(r"^(?P<year>\d{4})/(?P<number>\d+)$", normalized)
        if not match:
            return []
        year = match.group("year")
        number = str(int(match.group("number")))
        resolved: list[SourceSearchCandidate] = []
        for series in self._series_order:
            authority_source_id = f"{series}/{year}/{number}"
            candidate = self._resolve_candidate(authority_source_id=authority_source_id)
            if candidate is None:
                continue
            resolved.append(candidate)
            if len(resolved) >= limit:
                break
        return resolved

    def _search_by_title(self, query: str, *, limit: int) -> list[SourceSearchCandidate]:
        search_url = f"https://www.legislation.gov.uk/all?title={quote_plus(query)}"
        html = self.fetch_html(search_url)
        hrefs = re.findall(
            r'href="(?P<href>/id/[a-z0-9]+/\d{4}/\d+|/[a-z0-9]+/\d{4}/\d+)"',
            html,
            flags=re.IGNORECASE,
        )
        authority_source_ids: list[str] = []
        seen: set[str] = set()
        for href in hrefs:
            source_id = _source_id_from_legislation_url(f"https://www.legislation.gov.uk{href}")
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            authority_source_ids.append(source_id)
            if len(authority_source_ids) >= limit:
                break

        candidates: list[SourceSearchCandidate] = []
        for authority_source_id in authority_source_ids:
            candidate = self._resolve_candidate(authority_source_id=authority_source_id)
            if candidate is None:
                continue
            candidates.append(candidate)
        return candidates

    def _resolve_candidate(self, *, authority_source_id: str) -> SourceSearchCandidate | None:
        source_url = f"https://www.legislation.gov.uk/{authority_source_id}"
        xml_url = f"{source_url}/data.xml"
        try:
            xml_text = self.fetch_xml(xml_url)
            root = ElementTree.fromstring(xml_text)
        except Exception:
            return None
        title = (
            _first_text(root, {"title", "Title", "DocumentTitle", "dc:title"})
            or authority_source_id.upper()
        )
        parts = authority_source_id.split("/")
        citation = f"{parts[0].upper()} {parts[1]}/{parts[2]}"
        return SourceSearchCandidate(
            title=title,
            citation=citation,
            source_identifier=authority_source_id,
            authority_source_id=authority_source_id,
            jurisdiction=_jurisdiction_from_series(parts[0]),
            authority="legislation_gov_uk",
            canonical_source_url=source_url,
            provenance="search.legislation_gov_uk",
        )

    def _fetch_xml_from_network(self, source_url: str) -> str:
        request = Request(source_url, headers={"Accept": "application/xml, text/xml;q=0.9"})
        with urlopen(request, timeout=20) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset, errors="replace")

    def _fetch_html_from_network(self, source_url: str) -> str:
        request = Request(
            source_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "law-proposition-extractor-source-search/0.1",
            },
        )
        with urlopen(request, timeout=20) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset, errors="replace")


class SourceSearchService:
    def __init__(self, providers: dict[str, SourceSearchProvider] | None = None) -> None:
        provider_registry = providers or {}
        if "legislation_gov_uk" not in provider_registry:
            provider_registry = {
                **provider_registry,
                "legislation_gov_uk": LegislationGovUkSourceSearchProvider(),
            }
        self.providers = provider_registry

    def search(
        self,
        *,
        query: str,
        provider: str = "legislation_gov_uk",
        limit: int = 10,
        registry_entries: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        selected_provider = self.providers.get(provider)
        if selected_provider is None:
            known = ", ".join(sorted(self.providers))
            raise SourceSearchError(
                f"Unknown source search provider {provider!r}. Known providers: {known}."
            )
        provider_candidates = selected_provider.search(query=query, limit=limit)
        merged = list(provider_candidates)
        registry_hits: list[SourceSearchCandidate] = []
        if registry_entries:
            registry_hits = registry_entries_as_search_candidates(
                list(registry_entries),
                raw_query=query,
            )
            merged = _merge_candidates_by_authority(registry_hits + merged)[:limit]
        hints = authority_source_ids_hinted_for_query(query)
        return {
            "provider": provider,
            "query": query,
            "count": len(merged),
            "candidates": [candidate.to_dict() for candidate in merged],
            "query_resolution": summarise_query_resolution(query, hints),
            "registry_match_count": len(registry_hits),
        }
