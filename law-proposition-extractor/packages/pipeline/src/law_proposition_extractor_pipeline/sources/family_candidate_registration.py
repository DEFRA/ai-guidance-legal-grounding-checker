"""Register discovered SourceFamilyCandidate rows via the normal registry + refresh path."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from law_proposition_extractor_pipeline.sources.registry import SourceRegistryError, SourceRegistryService
from law_proposition_extractor_pipeline.sources.service import slugify
from law_proposition_extractor_pipeline.sources.source_family_discovery import discover_related_for_registry_entry


def _norm_asid(value: str) -> str:
    return value.strip().strip("/").lower()


def _candidate_metadata(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    return raw if isinstance(raw, dict) else {}


def resolve_authority(row: dict[str, Any]) -> str | None:
    md = _candidate_metadata(row)
    explicit = row.get("authority") or md.get("authority")
    if explicit:
        return str(explicit).strip()
    url = str(row.get("url") or "").strip().lower()
    if "legislation.gov.uk" in url:
        return "legislation_gov_uk"
    asid = str(row.get("candidate_source_id") or "").strip().lower()
    prefixes = (
        "eur/",
        "ukpga/",
        "uksi/",
        "asc/",
        "wsi/",
        "ssi/",
        "nia/",
        "nisr/",
        "asp/",
        "anaw/",
    )
    if any(asid.startswith(p) for p in prefixes):
        return "legislation_gov_uk"
    return None


def _legislation_authority_source_id(row: dict[str, Any]) -> str | None:
    url = str(row.get("url") or "").strip()
    if url:
        parsed = urlparse(url)
        if "legislation.gov.uk" in (parsed.netloc or "").lower():
            segments = [seg for seg in parsed.path.split("/") if seg and seg.lower() != "data.xml"]
            if len(segments) >= 3:
                return "/".join(segments).lower()
    csid = str(row.get("candidate_source_id") or "").strip()
    if csid:
        parts = [p for p in csid.split("/") if p]
        if len(parts) >= 3:
            return csid.strip("/").lower()
    return None


def locator_fields_present(row: dict[str, Any]) -> bool:
    """url OR (authority + citation/celex/eli)."""
    if str(row.get("url") or "").strip():
        return True
    auth = resolve_authority(row)
    if not auth:
        return False
    return bool(
        str(row.get("citation") or "").strip()
        or str(row.get("celex") or "").strip()
        or str(row.get("eli") or "").strip()
    )


def candidate_can_auto_register(row: dict[str, Any]) -> tuple[bool, str]:
    title = str(row.get("title") or "").strip()
    if not title:
        return False, "missing title"
    sr = str(row.get("source_role") or "").strip().lower()
    if not sr or sr == "unknown":
        return False, "source_role required (not unknown)"
    rel = str(row.get("relationship_to_target") or "").strip().lower()
    if not rel or rel == "unknown":
        return False, "relationship_to_target required (not unknown)"
    if not locator_fields_present(row):
        return False, "need url or authority with citation/celex/eli"
    if build_candidate_reference(row, target_registry_id="") is None:
        return False, "cannot auto-register (manual review needed)"
    return True, ""


def _jurisdiction_hint(series: str) -> str:
    s = series.lower()
    if s == "eur":
        return "EU"
    if s in {"ukpga", "uksi", "asc", "wsi", "ssi", "nia", "nisr", "asp", "anaw"}:
        return "UK"
    return "EU"


def build_candidate_reference(
    row: dict[str, Any],
    *,
    target_registry_id: str,
) -> dict[str, Any] | None:
    """Build a legislation.gov.uk registry reference when fetch metadata can be resolved."""
    asid = _legislation_authority_source_id(row)
    if not asid:
        return None
    parts = [p for p in asid.split("/") if p]
    series = parts[0] if parts else ""
    title = str(row.get("title") or "").strip()
    citation = str(row.get("citation") or "").strip() or str(row.get("celex") or "").strip()
    base = f"https://www.legislation.gov.uk/{asid.strip('/')}"
    reference: dict[str, Any] = {
        "authority": "legislation_gov_uk",
        "authority_source_id": asid,
        "id": f"src-{slugify(asid)}",
        "title": title,
        "jurisdiction": _jurisdiction_hint(series),
        "citation": citation or asid,
        "kind": "legislation",
        "source_url": f"{base}/data.xml",
        "version_id": "latest",
        "provenance": "registry.source_family_candidate",
        "metadata": {
            "source_family_candidate": {
                "id": row.get("id"),
                "target_registry_id": target_registry_id,
                "source_role": row.get("source_role"),
                "relationship_to_target": row.get("relationship_to_target"),
            }
        },
    }
    return reference


def find_existing_registry_id(
    registry: SourceRegistryService,
    *,
    authority: str,
    authority_source_id: str,
) -> str | None:
    want_auth = authority.strip().lower()
    want_asid = _norm_asid(authority_source_id)
    for item in registry.list_entries():
        ref = item.get("reference") if isinstance(item.get("reference"), dict) else {}
        ra = str(ref.get("authority", "")).strip().lower()
        rsid = _norm_asid(str(ref.get("authority_source_id") or ""))
        if ra == want_auth and rsid == want_asid:
            return str(item.get("registry_id") or "")
    return None


def register_family_candidates(
    registry: SourceRegistryService,
    *,
    target_registry_id: str,
    candidate_ids: list[str],
) -> dict[str, Any]:
    """
    Resolve candidates from a fresh discover_related_for_registry_entry(target), then
    register via register_reference(refresh=True) or classify as duplicate / manual review.
    """
    entry = registry.inspect_entry(target_registry_id)
    discovered = discover_related_for_registry_entry(entry)
    raw_candidates = list(discovered.get("candidates") or [])
    by_id: dict[str, dict[str, Any]] = {}
    for item in raw_candidates:
        if isinstance(item, dict) and item.get("id") is not None:
            by_id[str(item["id"])] = item

    registered: list[dict[str, Any]] = []
    already_registered: list[dict[str, Any]] = []
    manual_review_needed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for cid in candidate_ids:
        cid_str = str(cid).strip()
        if not cid_str:
            continue
        row = by_id.get(cid_str)
        if row is None:
            errors.append({"candidate_id": cid_str, "message": "candidate_id not found for target"})
            continue

        ok, reason = candidate_can_auto_register(row)
        if not ok:
            manual_review_needed.append({"candidate_id": cid_str, "reason": reason})
            continue

        ref = build_candidate_reference(row, target_registry_id=target_registry_id)
        if ref is None:
            manual_review_needed.append(
                {"candidate_id": cid_str, "reason": "cannot auto-register (manual review needed)"}
            )
            continue

        authority = str(ref["authority"])
        asid = str(ref["authority_source_id"])
        existing = find_existing_registry_id(registry, authority=authority, authority_source_id=asid)
        if existing:
            already_registered.append({"candidate_id": cid_str, "registry_id": existing})
            continue

        try:
            created = registry.register_reference(reference=ref, refresh=True)
            rid = str(created.get("registry_id") or "")
            registered.append({"candidate_id": cid_str, "registry_id": rid})
        except SourceRegistryError as exc:
            errors.append({"candidate_id": cid_str, "message": str(exc)})

    return {
        "registered": registered,
        "already_registered": already_registered,
        "manual_review_needed": manual_review_needed,
        "errors": errors,
    }
