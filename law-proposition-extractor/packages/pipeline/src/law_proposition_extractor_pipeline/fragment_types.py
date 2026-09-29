from __future__ import annotations


def fragment_type_from_locator(locator: str | None) -> str:
    value = str(locator or "").strip().lower()
    if not value:
        return "unknown"
    if value == "document:full":
        return "document"
    if "|chunk:" in value or value.startswith("chunk:"):
        return "chunk"
    if value.startswith("article:"):
        return "article"
    if value.startswith("regulation:"):
        return "regulation"
    if value.startswith("rule:"):
        return "rule"
    if value.startswith("schedule:"):
        return "schedule"
    if value.startswith("annex:"):
        return "annex"
    if value.startswith("section:"):
        return "section"
    if value.startswith("part:"):
        return "part"
    if value.startswith("chapter:"):
        return "chapter"
    if value.startswith("title:"):
        return "title"
    if value.startswith("division:"):
        return "division"
    if value.startswith("recital:"):
        return "recital"
    return "unknown"
