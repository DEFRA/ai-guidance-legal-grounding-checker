"""Committed mapping: Guidance Proposition Extractor run output -> proposition-matcher GuidanceProposition.

Guidance Proposition Extractor emits ``{url, content_id?, meta_data: {propositions: [{proposition_text,
actor, regulatory_kind, source_paragraphs, section_locators, ...}]}}``.

``proposition_text`` is a derived rewrite for matching; ``source_paragraphs``
are the citation pin. The group-rerank matcher reads ``proposition_text`` /
``source_url`` and the ``regulatory_kind`` tag; citation fields are carried
through for durable provenance in ``results.json``.
"""

from __future__ import annotations

import hashlib

from proposition_matcher.guidance import GuidanceProposition


def _slug(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def guidance_from_guidance_proposition_extractor_entry(entry: dict) -> list[GuidanceProposition]:
    url = entry["url"]
    md = entry.get("meta_data", {}) or {}
    content_id = entry.get("content_id") or ""
    out: list[GuidanceProposition] = []
    for i, sp in enumerate(md.get("propositions", []) or [], 1):
        paras = sp.get("source_paragraphs") or []
        if isinstance(paras, str):
            paras = [paras]
        locators = sp.get("section_locators") or []
        if isinstance(locators, str):
            locators = [locators] if locators else []
        out.append(
            GuidanceProposition(
                id=f"susan-{_slug(url)}-{i}",
                section_locator="; ".join(locators),
                proposition_text=sp["proposition_text"],
                legal_subject=sp.get("actor") or "you",
                conditions=[],
                required_documents=[],
                source_url=url,
                extraction_method="susan",
                source_paragraphs=paras,
                regulatory_kind=sp.get("regulatory_kind") or "",
                content_id=content_id,
            )
        )
    return out


def guidance_from_guidance_proposition_extractor_output(entries: list[dict]) -> list[GuidanceProposition]:
    """Flatten a whole Guidance Proposition Extractor ``output.json`` into GuidanceProposition objects."""
    out: list[GuidanceProposition] = []
    for entry in entries:
        out.extend(guidance_from_guidance_proposition_extractor_entry(entry))
    return out


# DEPRECATED aliases — COMPAT_LEGACY_NAME remove in rename+1
guidance_from_susan_entry = guidance_from_guidance_proposition_extractor_entry
guidance_from_susan_output = guidance_from_guidance_proposition_extractor_output
