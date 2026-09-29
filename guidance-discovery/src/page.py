"""
Guidance Discovery — the page contract.

Both stages pass around the same dict shape, and stage 2's output *is* Guidance Relevance Filter's
input. These TypedDicts document that contract in one place so the keys aren't
re-spelled by hand in every script. (Defined in Guidance Discovery only — Guidance Relevance Filter is untouched
and still just reads plain JSON.)
"""

from typing import Any, NotRequired, TypedDict


def organisation_slug(org: Any) -> str:
    """GOV.UK org slug from a Search API hit or Content API link object."""
    if isinstance(org, str):
        return org.rstrip("/").rsplit("/", 1)[-1]
    if not isinstance(org, dict):
        return ""
    if org.get("slug"):
        return str(org["slug"])
    path = org.get("link") or org.get("base_path") or ""
    return str(path).rstrip("/").rsplit("/", 1)[-1] if path else ""


def organisation_slugs(orgs: Any) -> list[str]:
    """Deduped slugs from a Search/Content API organisations list (or a single object)."""
    if not orgs:
        return []
    if isinstance(orgs, dict):
        orgs = [orgs]
    slugs: list[str] = []
    seen: set[str] = set()
    for org in orgs:
        slug = organisation_slug(org)
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def primary_organisation_slug(orgs: Any) -> str:
    slugs = organisation_slugs(orgs)
    return slugs[0] if slugs else ""


class MetaData(TypedDict):
    title: str
    description: str
    updated_at: str
    document_type: str
    view_count: int
    # Search API slugs (same vocabulary as filters.ORGANISATIONS). Stage 2
    # backfills from Content API links when missing; HTML chapters inherit.
    organisations: list[str]
    primary_publishing_organisation: str
    # Search API: True when the page is withdrawn (still published, unlisted
    # from public search). Stamped by stage 1; HTML chapters default False.
    is_withdrawn: bool
    # Added by stage 2 (fetch_body). None when the fetch failed; "" when the
    # page genuinely has no body. Absent on stage 1's discovery-only output.
    body_text: NotRequired[str | None]
    # Added by stage 2 after a successful Content API fetch. URLs of HTML
    # attachment chapters expanded from this page's `links.children`. Empty
    # list means we looked and found none — so a re-run can skip this parent.
    # Absent on old cache entries; stage 2 re-fetches publication parents
    # that lack it so chapters are discovered once.
    html_publication_urls: NotRequired[list[str]]
    # Added by stage 2 after a failed Content API fetch (body_text is None).
    # ``http_status`` for a non-200 response; ``error`` for a network/retry
    # exhaustion. Absent on successful fetches.
    fetch_error: NotRequired[dict]


class PageItem(TypedDict):
    url: str
    content_id: str
    meta_data: MetaData
