#!/usr/bin/env python3

import csv
import json
import math
import re
import sys
import time
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


BASE = "https://www.gov.uk"
KEYWORDS = "slurry"
PAGE_SIZE = 10
SLEEP_SECONDS = 0.25


@dataclass
class SearchResult:
    title: str
    url: str
    path: str
    page: int


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._in_a = False
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return

        attrs = dict(attrs)
        href = attrs.get("href")
        if not href:
            return

        self._in_a = True
        self._href = href
        self._text = []

    def handle_data(self, data):
        if self._in_a:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self._in_a:
            return

        title = clean_text(" ".join(self._text))
        href = self._href

        if title and href:
            self.links.append((title, href))

        self._in_a = False
        self._href = None
        self._text = []


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def fetch(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Law Discovery/Law Proposition Extractor GOV.UK discovery script; personal research use",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(req, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def extract_total(html: str) -> int:
    m = re.search(r"([\d,]+)\s+results", clean_text(html), flags=re.I)
    if not m:
        raise RuntimeError("Could not find total result count")
    return int(m.group(1).replace(",", ""))


def parse_page(page: int) -> tuple[int, list[SearchResult]]:
    url = f"{BASE}/search/all?{urlencode({'keywords': KEYWORDS, 'page': page})}"
    html = fetch(url)
    total = extract_total(html)

    parser = LinkExtractor()
    parser.feed(html)

    results: list[SearchResult] = []

    for title, href in parser.links:
        # Ignore navigation, filters, footer, cookie links, and pagination.
        if href.startswith("#"):
            continue
        if "Next page" in title or "Previous page" in title:
            continue
        if title in {
            "GOV.UK",
            "Menu",
            "Search GOV.UK",
            "Home",
            "Benefits",
            "Births, death, marriages and care",
            "Business and self-employed",
            "Childcare and parenting",
            "Citizenship and living in the UK",
            "Crime, justice and the law",
            "Disabled people",
            "Driving and transport",
            "Education and learning",
            "Employing people",
            "Environment and countryside",
            "Housing and local services",
            "Money and tax",
            "Passports, travel and living abroad",
            "Visas and immigration",
            "Working, jobs and pensions",
            "Departments",
            "News",
            "Guidance and regulation",
            "Research and statistics",
            "Policy papers and consultations",
            "Transparency",
            "How government works",
            "Get involved",
            "Cookies",
            "Accessibility statement",
            "Contact",
            "Terms and conditions",
            "Rhestr o Wasanaethau Cymraeg",
            "Government Digital Service",
        }:
            continue

        full_url = urljoin(BASE, href)
        parsed = urlparse(full_url)

        # Keep only normal GOV.UK content URLs.
        if parsed.netloc != "www.gov.uk":
            continue

        path = parsed.path

        # Drop site furniture.
        if path in {
            "/",
            "/search/all",
            "/help",
            "/contact",
            "/government/organisations/government-digital-service",
        }:
            continue

        # Search result links are normally content paths, not top-level nav pages.
        results.append(
            SearchResult(
                title=title,
                url=full_url,
                path=path,
                page=page,
            )
        )

    # The filtering above should leave exactly 10 on most pages.
    # If it does not, print diagnostics rather than silently lying.
    if len(results) == 0:
        print(f"\nNo results extracted on page {page}. Links seen:", file=sys.stderr)
        for title, href in parser.links[:80]:
            print(f"- {title!r} -> {href!r}", file=sys.stderr)

    return total, results


def scrape_all() -> list[SearchResult]:
    total, first_results = parse_page(1)
    total_pages = math.ceil(total / PAGE_SIZE)

    print(f"Reported total: {total}", file=sys.stderr)
    print(f"Pages: {total_pages}", file=sys.stderr)

    seen = set()
    all_results: list[SearchResult] = []

    def add(results: list[SearchResult]) -> None:
        for result in results:
            if result.url in seen:
                continue
            seen.add(result.url)
            all_results.append(result)

    add(first_results)
    print(f"Page 1: {len(first_results)} results", file=sys.stderr)

    for page in range(2, total_pages + 1):
        time.sleep(SLEEP_SECONDS)

        _, results = parse_page(page)
        print(f"Page {page}: {len(results)} results", file=sys.stderr)

        if not results:
            print(f"Stopping early: page {page} returned no extracted results", file=sys.stderr)
            break

        add(results)

    print(f"Unique URLs collected: {len(all_results)}", file=sys.stderr)
    return all_results


def write_jsonl(results: list[SearchResult], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def write_csv(results: list[SearchResult], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "url", "path", "page"])
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


if __name__ == "__main__":
    results = scrape_all()
    write_jsonl(results, "govuk-slurry-search-all.jsonl")
    write_csv(results, "govuk-slurry-search-all.csv")
