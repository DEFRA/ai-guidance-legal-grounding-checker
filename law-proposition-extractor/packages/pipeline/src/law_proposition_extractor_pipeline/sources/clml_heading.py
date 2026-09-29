"""Focused CLML heading-text extraction (separate from operative serialization)."""

from __future__ import annotations

from xml.etree import ElementTree

# Bodies / non-heading structures that must never contribute heading text.
_HEADING_SKIP_TAGS = frozenset(
    {
        "Commentary",
        "Commentaries",
        "Footnote",
        "Footnotes",
        "Table",
        "Row",
        "Entry",
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
        "P1para",
        "P2para",
        "P3para",
        "P4para",
        "P1group",
        "P2group",
        "P3group",
        "EUBody",
        "EUTitle",
        "Part",
        "Chapter",
        "Schedule",
    }
)

# Change wrappers whose textual content is included; attributes retained as provenance.
_CHANGE_WRAPPER_TAGS = frozenset(
    {
        "Addition",
        "Substitution",
        "Repeal",
        "Omit",
        "Insertion",
    }
)


def _local_name(tag_name: str) -> str:
    if "}" in tag_name:
        return tag_name.split("}", maxsplit=1)[1]
    return tag_name


def normalize_heading_whitespace(text: str) -> str:
    return " ".join(str(text or "").replace("\xa0", " ").split()).strip()


def collect_heading_provenance(
    node: ElementTree.Element,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Collect ChangeId / CommentaryRef identifiers in document order (deduped)."""
    change_ids: list[str] = []
    commentary_refs: list[str] = []
    seen_change: set[str] = set()
    seen_commentary: set[str] = set()

    def walk(el: ElementTree.Element, *, allow_nested_title: bool) -> None:
        name = _local_name(el.tag)
        if name in _HEADING_SKIP_TAGS:
            return
        if name == "Title" and not allow_nested_title:
            return
        change_id = (el.attrib.get("ChangeId") or "").strip()
        if change_id and change_id not in seen_change:
            seen_change.add(change_id)
            change_ids.append(change_id)
        commentary = (el.attrib.get("CommentaryRef") or "").strip()
        if commentary and commentary not in seen_commentary:
            seen_commentary.add(commentary)
            commentary_refs.append(commentary)
        # Standalone commentary reference elements.
        ref = (el.attrib.get("Ref") or "").strip()
        if name == "CommentaryRef" and ref and ref not in seen_commentary:
            seen_commentary.add(ref)
            commentary_refs.append(ref)
        for child in list(el):
            child_name = _local_name(child.tag)
            nested_ok = allow_nested_title and child_name != "Title"
            if child_name == "Title" and not allow_nested_title:
                continue
            walk(child, allow_nested_title=nested_ok)

    walk(node, allow_nested_title=True)
    return tuple(change_ids), tuple(commentary_refs)


def serialize_clml_heading_text(node: ElementTree.Element) -> str:
    """Serialize heading subtree text without operative descendants or commentary bodies.

    Includes text inside Addition/Substitution wrappers. Excludes nested Title
    elements and non-heading structural containers. Does not emit amendment labels.
    """
    parts: list[str] = []

    def walk(el: ElementTree.Element, *, skip_nested_titles: bool) -> None:
        name = _local_name(el.tag)
        if name in _HEADING_SKIP_TAGS:
            return
        if el.text:
            parts.append(el.text)
        for child in list(el):
            child_name = _local_name(child.tag)
            if child_name in _HEADING_SKIP_TAGS:
                if child.tail:
                    parts.append(child.tail)
                continue
            if skip_nested_titles and child_name == "Title":
                if child.tail:
                    parts.append(child.tail)
                continue
            if child_name == "CommentaryRef":
                # Reference marker only — no commentary body text.
                if child.tail:
                    parts.append(child.tail)
                continue
            # Descend into change wrappers and ordinary inline content.
            walk(child, skip_nested_titles=True)
            if child.tail:
                parts.append(child.tail)

    # Process the root element itself (including when it is Title), but never
    # pull text from nested Title siblings/descendants.
    walk(node, skip_nested_titles=True)
    return normalize_heading_whitespace("".join(parts))


def extract_direct_number_label(node: ElementTree.Element) -> str | None:
    """Return normalized text from the first direct Number/Pnumber child, if any."""
    for child in list(node):
        name = _local_name(child.tag)
        if name in {"Number", "Pnumber"}:
            value = serialize_clml_heading_text(child)
            if value:
                return value
    return None


def extract_direct_descriptive_title(
    node: ElementTree.Element,
) -> tuple[str | None, tuple[str, ...], tuple[str, ...], str | None]:
    """Return (text, change_ids, commentary_refs, source_element) for a direct Title child."""
    for child in list(node):
        if _local_name(child.tag) != "Title":
            continue
        text = serialize_clml_heading_text(child)
        if not text:
            continue
        change_ids, commentary_refs = collect_heading_provenance(child)
        return text, change_ids, commentary_refs, "Title"
    return None, (), (), None
