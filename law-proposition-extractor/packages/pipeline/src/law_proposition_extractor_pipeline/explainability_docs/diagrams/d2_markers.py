"""Replace GENERATED sections marked with D2 `#` comments."""

from __future__ import annotations

import re

from ..markers import MarkerError

_BEGIN = re.compile(r"^#\s*BEGIN GENERATED:\s*(?P<name>[A-Za-z0-9._-]+)\s*$", re.M)
_END_TMPL = r"^#\s*END GENERATED:\s*{name}\s*$"


def replace_d2_generated_section(document: str, section_name: str, body: str) -> str:
    begin_re = re.compile(
        rf"^#\s*BEGIN GENERATED:\s*{re.escape(section_name)}\s*$", re.M
    )
    end_re = re.compile(_END_TMPL.format(name=re.escape(section_name)), re.M)

    begin_matches = list(begin_re.finditer(document))
    if len(begin_matches) != 1:
        raise MarkerError(
            f"Expected exactly one BEGIN GENERATED marker for D2 section "
            f"{section_name!r}; found {len(begin_matches)}."
        )
    end_matches = list(end_re.finditer(document))
    if len(end_matches) != 1:
        raise MarkerError(
            f"Expected exactly one END GENERATED marker for D2 section "
            f"{section_name!r}; found {len(end_matches)}."
        )
    begin = begin_matches[0]
    end = end_matches[0]
    if end.start() <= begin.end():
        raise MarkerError(
            f"Malformed D2 GENERATED markers for {section_name!r}: END before BEGIN."
        )

    normalised = body.strip("\n")
    begin_line = begin.group(0)
    end_line = end.group(0)
    replacement = (
        f"{begin_line}\n{normalised}\n{end_line}"
        if normalised
        else f"{begin_line}\n{end_line}"
    )
    return document[: begin.start()] + replacement + document[end.end() :]


def assert_d2_markers_balanced(document: str) -> None:
    begins = list(_BEGIN.finditer(document))
    seen: set[str] = set()
    for begin in begins:
        name = begin.group("name")
        if name in seen:
            raise MarkerError(f"Duplicate D2 BEGIN GENERATED marker for {name!r}.")
        seen.add(name)
        end_re = re.compile(_END_TMPL.format(name=re.escape(name)), re.M)
        ends = list(end_re.finditer(document))
        if len(ends) != 1:
            raise MarkerError(
                f"Expected exactly one D2 END GENERATED for {name!r}; found {len(ends)}."
            )
        if ends[0].start() <= begin.end():
            raise MarkerError(f"D2 END GENERATED for {name!r} appears before BEGIN.")
