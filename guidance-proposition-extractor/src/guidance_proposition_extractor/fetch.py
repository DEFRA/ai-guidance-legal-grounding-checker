"""
Fetch GOV.UK pages via the Content API and parse them into both a flat
text view and a structured (locator, [paragraphs]) breakdown.

Guidance Proposition Extractor's extractor uses the structured form so each proposition can be
attributed to a specific H2 section.

Optional disk cache: pass a directory to ``fetch`` to persist parsed
pages across runs. With no cache_dir, every fetch hits gov.uk.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx

BASE_URL = "https://www.gov.uk"
_SKIP_TAGS = {"nav", "aside", "footer", "header", "script", "style"}


@dataclass
class FetchedPage:
    url: str
    title: str
    description: str
    body_text: str
    sections: list[tuple[str, list[str]]]  # (section_locator, [paragraphs])

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "FetchedPage":
        return cls(
            url=data["url"],
            title=data["title"],
            description=data["description"],
            body_text=data["body_text"],
            sections=[(loc, paras) for loc, paras in data["sections"]],
        )


class _BodyParser(HTMLParser):
    """Group <p>/<li> text under the enclosing H2 section."""

    def __init__(self) -> None:
        super().__init__()
        self.sections: list[tuple[str, list[str]]] = []
        self._current_id = "intro"
        self._current_lines: list[str] = []
        self._skip_depth = 0
        self._in_li = False
        self._li_buf: list[str] = []
        self._in_p = False
        self._p_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        attr_dict = dict(attrs)
        if tag == "h2":
            self._flush()
            self._current_id = attr_dict.get("id") or ""
            self._current_lines = []
        elif tag == "li":
            self._in_li = True
            self._li_buf = []
        elif tag == "p":
            self._in_p = True
            self._p_buf = []

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "li" and self._in_li:
            self._in_li = False
            text = _normalise(" ".join(self._li_buf))
            if text:
                self._current_lines.append(text)
        elif tag == "p" and self._in_p:
            self._in_p = False
            text = _normalise(" ".join(self._p_buf))
            if text:
                self._current_lines.append(text)

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_li:
            self._li_buf.append(text)
        elif self._in_p:
            self._p_buf.append(text)

    def _flush(self) -> None:
        if self._current_lines:
            self.sections.append((self._current_id or "section", list(self._current_lines)))

    def close(self):
        super().close()
        self._flush()


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_body(html: str, locator_prefix: str = "section") -> list[tuple[str, list[str]]]:
    parser = _BodyParser()
    parser.feed(html)
    parser.close()
    return [(f"{locator_prefix}:{sid}", lines) for sid, lines in parser.sections]


def _content_api_url(url: str) -> str:
    path = urlparse(url).path
    return f"{BASE_URL}/api/content{path}"


def _cache_path(cache_dir: Path, url: str) -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    return cache_dir / f"{h}.json"


def fetch(url: str, *, timeout: float = 30.0, cache_dir: Path | None = None) -> FetchedPage:
    """Fetch a page from gov.uk Content API.

    Args:
        url: A gov.uk page URL (with or without trailing slash).
        timeout: HTTP timeout in seconds.
        cache_dir: Optional directory for disk-caching parsed pages.

    Raises:
        httpx.HTTPError on network failure.
    """
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = _cache_path(cache_dir, url)
        if cached.exists():
            try:
                return FetchedPage.from_json(json.loads(cached.read_text()))
            except Exception:
                pass  # corrupt cache — refetch

    api_url = _content_api_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(api_url)
        response.raise_for_status()
        data = response.json()

    title = data.get("title", "")
    description = data.get("description", "")
    details = data.get("details", {})

    sections: list[tuple[str, list[str]]] = []
    if "body" in details:
        sections = _parse_body(details["body"])
    elif "parts" in details:
        for part in details["parts"]:
            slug = part.get("slug", "")
            body_html = part.get("body", "")
            if not body_html:
                continue
            for loc, lines in _parse_body(body_html, locator_prefix=f"part:{slug}:section"):
                sections.append((loc, lines))

    body_text = "\n\n".join("\n".join(lines) for _, lines in sections)
    page = FetchedPage(
        url=url,
        title=title,
        description=description,
        body_text=body_text,
        sections=sections,
    )

    if cache_dir is not None:
        _cache_path(cache_dir, url).write_text(json.dumps(page.to_json(), indent=2))

    return page
