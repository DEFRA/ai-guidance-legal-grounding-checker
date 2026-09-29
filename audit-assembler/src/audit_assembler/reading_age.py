"""Reading-age scoring for gov.uk pages.

Ported from the standalone ``reading-age/reading_age.py`` tool. The SMOG-based
scoring is unchanged — only the standalone CLI/CSV plumbing was dropped, leaving
a small library Audit Assembler calls per audited page.

The text is pulled from the gov.uk content API (cached on disk so re-runs are
free) and scored with SMOG, the gov/health-content readability standard.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import textstat
from bs4 import BeautifulSoup, NavigableString

CONTENT_API_BASE = "https://www.gov.uk/api/content"
USER_AGENT = "audit-assembler-reading-age/1.0 (andy@brightsquad.co.uk)"
REQUEST_DELAY = 0.25  # ~4 req/s, polite default
MAX_RETRIES = 5
READING_AGE_CAP = 25  # SMOG grade 20; matches academic post-graduate ceiling

# Block-level tags whose contents should end a sentence. Bulleted lists,
# table cells and headings carry semantic structure that .get_text() flattens
# into runaway prose — terminating each makes readability scoring honest.
_BLOCK_TAGS = (
    "li", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "td", "th", "tr", "dt", "dd", "div", "section", "article",
    "blockquote", "caption", "figcaption",
)


def to_api_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path or "/"
    return f"{CONTENT_API_BASE}{path}"


def _cache_path(cache_dir: Path, api_url: str) -> Path:
    return cache_dir / (hashlib.sha1(api_url.encode()).hexdigest() + ".json")


def fetch_content(api_url: str, session: requests.Session, cache_dir: Path) -> dict:
    cached = _cache_path(cache_dir, api_url)
    if cached.exists():
        return json.loads(cached.read_text())

    delay = 1.0
    resp = None
    for _ in range(MAX_RETRIES):
        resp = session.get(api_url, timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else delay
            time.sleep(wait)
            delay *= 2
            continue
        resp.raise_for_status()
        data = resp.json()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(data, ensure_ascii=False))
        time.sleep(REQUEST_DELAY)  # polite delay only on real network hits
        return data
    if resp is not None:
        resp.raise_for_status()
    return {}


def _collect_html(payload: dict) -> list[str]:
    """Return raw HTML fragments from a content-API payload (no recursion)."""
    details = payload.get("details", {}) or {}
    parts: list[str] = []

    body = details.get("body")
    if isinstance(body, str):
        parts.append(body)
    elif isinstance(body, list):
        for entry in body:
            if isinstance(entry, dict) and entry.get("content_type", "").startswith("text/html"):
                parts.append(entry.get("content", ""))

    for part in details.get("parts", []) or []:
        if isinstance(part, dict):
            parts.append(part.get("title", ""))
            parts.append(part.get("body", ""))

    for section in ("introduction", "summary", "description", "more_information"):
        value = details.get(section)
        if isinstance(value, str):
            parts.append(value)

    return [p for p in parts if p]


def _html_attachment_paths(payload: dict) -> list[str]:
    """Return relative gov.uk paths of HTML attachments worth following.

    Publication wrappers often hold the real content in an HTML attachment
    whose URL is a gov.uk path (PDFs live on assets.publishing.service.gov.uk
    and are skipped).
    """
    paths: list[str] = []
    for att in payload.get("details", {}).get("attachments", []) or []:
        url = att.get("url", "")
        if url.startswith("/") and not url.startswith("//"):
            paths.append(url)
    return paths


def extract_text(payload: dict, session: requests.Session, cache_dir: Path) -> str:
    html_parts = _collect_html(payload)

    for path in _html_attachment_paths(payload):
        try:
            sub = fetch_content(f"{CONTENT_API_BASE}{path}", session, cache_dir)
        except requests.HTTPError:
            continue
        html_parts.extend(_collect_html(sub))

    html = "\n".join(html_parts)
    if not html.strip():
        return ""
    return html_to_text(html)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(("script", "style")):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with(NavigableString(". "))
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.append(NavigableString(". "))
    text = soup.get_text(separator=" ", strip=True)
    # Collapse repeats from nested blocks (". . .  ." → ". ") and tidy spacing.
    text = re.sub(r"(?:\s*\.\s*){2,}", ". ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def reading_age(text: str) -> int | None:
    # SMOG is the gov/health-content standard; +5 maps US grade to UK age.
    # Capped at READING_AGE_CAP — there's no published GDS ceiling, so we use
    # the academic post-graduate convention (SMOG grade 20 ≈ age 25).
    if textstat.sentence_count(text) < 3:
        return None
    return min(READING_AGE_CAP, round(textstat.smog_index(text) + 5))


def score_text(text: str) -> dict:
    """Score already-extracted plain text. No network."""
    return {"word_count": len(text.split()), "reading_age": reading_age(text), "error": None}


def score_url(url: str, session: requests.Session, cache_dir: Path) -> dict:
    """Fetch the page via the gov.uk content API (cached), score it, and carry the
    authoritative page ``title`` from the same payload (the upstream corpus may
    not have one)."""
    try:
        payload = fetch_content(to_api_url(url), session, cache_dir)
        text = extract_text(payload, session, cache_dir)
        return {**score_text(text), "title": payload.get("title") or None}
    except Exception as exc:  # noqa: BLE001 — surface per-row, never abort the batch
        return {"word_count": 0, "reading_age": None, "error": str(exc), "title": None}


def score_urls(urls: list[str], cache_dir: Path, log=None) -> dict[str, dict]:
    """Score URLs, returning ``{url: {word_count, reading_age, error, title}}``."""
    out: dict[str, dict] = {}
    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        session.headers["Accept"] = "application/json"
        total = len(urls)
        for i, url in enumerate(urls, 1):
            url = (url or "").strip()
            if not url:
                continue
            result = score_url(url, session, cache_dir)
            if log is not None:
                print(
                    f"[{i}/{total}] {url} -> reading_age={result['reading_age']}",
                    file=log, flush=True,
                )
            out[url] = result
    return out
