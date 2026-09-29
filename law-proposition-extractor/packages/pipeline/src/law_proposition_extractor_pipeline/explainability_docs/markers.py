"""Replace only marked GENERATED sections in Markdown documents."""

from __future__ import annotations

import re

_BEGIN = re.compile(r"<!--\s*BEGIN GENERATED:\s*(?P<name>[A-Za-z0-9._-]+)\s*-->")
_END_TMPL = r"<!--\s*END GENERATED:\s*{name}\s*-->"


class MarkerError(ValueError):
    """Raised when generated-section markers are missing or malformed."""


def replace_generated_section(document: str, section_name: str, body: str) -> str:
    """Replace the body between BEGIN/END markers for ``section_name``.

    Preserves hand-written text outside the markers. The replacement body should
    not include the markers themselves. Leading/trailing newlines of the body
    are normalised so the result is deterministic.
    """
    begin_re = re.compile(rf"<!--\s*BEGIN GENERATED:\s*{re.escape(section_name)}\s*-->")
    end_re = re.compile(_END_TMPL.format(name=re.escape(section_name)))

    begin_matches = list(begin_re.finditer(document))
    if len(begin_matches) == 0:
        raise MarkerError(f"Missing BEGIN GENERATED marker for section {section_name!r}.")
    if len(begin_matches) > 1:
        raise MarkerError(f"Duplicate BEGIN GENERATED markers for section {section_name!r}.")
    end_matches = list(end_re.finditer(document))
    if len(end_matches) == 0:
        raise MarkerError(f"Missing END GENERATED marker for section {section_name!r}.")
    if len(end_matches) > 1:
        raise MarkerError(f"Duplicate END GENERATED markers for section {section_name!r}.")

    begin = begin_matches[0]
    end = end_matches[0]
    if end.start() <= begin.end():
        raise MarkerError(
            f"Malformed GENERATED markers for section {section_name!r}: END appears before BEGIN."
        )

    normalised = body.strip("\n")
    replacement = (
        f"{begin.group(0)}\n{normalised}\n{end.group(0)}"
        if normalised
        else f"{begin.group(0)}\n{end.group(0)}"
    )
    return document[: begin.start()] + replacement + document[end.end() :]


def list_generated_sections(document: str) -> list[str]:
    """Return GENERATED section names in document order."""
    return [m.group("name") for m in _BEGIN.finditer(document)]


def assert_markers_balanced(document: str) -> None:
    """Fail clearly when BEGIN/END pairs are missing counterparts."""
    begins = list(_BEGIN.finditer(document))
    seen: set[str] = set()
    for begin in begins:
        name = begin.group("name")
        if name in seen:
            raise MarkerError(f"Duplicate BEGIN GENERATED marker for {name!r}.")
        seen.add(name)
        end_re = re.compile(_END_TMPL.format(name=re.escape(name)))
        ends = list(end_re.finditer(document))
        if len(ends) != 1:
            raise MarkerError(
                f"Expected exactly one END GENERATED marker for {name!r}; found {len(ends)}."
            )
        if ends[0].start() <= begin.end():
            raise MarkerError(f"END GENERATED for {name!r} appears before its BEGIN.")
