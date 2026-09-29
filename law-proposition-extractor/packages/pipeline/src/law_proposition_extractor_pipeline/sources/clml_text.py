"""Structure-aware text extraction for legislation.gov.uk CLML XML."""

from __future__ import annotations

import re
from xml.etree import ElementTree

_CLML_NUMBER_TAGS = frozenset({"Pnumber", "Number"})
_CLML_BLOCK_TAGS = frozenset(
    {
        "P",
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
        "Text",
        "Intro",
        "Lead",
        "Pblock",
        "Block",
    }
)
_RE_PROVISION_PARA_TAG = re.compile(r"^P\d*para$", re.IGNORECASE)
_CLML_SKIP_TAGS = frozenset(
    {
        "Title",
        "Commentary",
        "Footnote",
        "Footnotes",
        "Commentaries",
        "Table",
        "Row",
        "Entry",
    }
)
_RE_PARAGRAPH_NUMBER = re.compile(r"^\d+[A-Za-z]?\.?$")
_RE_SUBPARAGRAPH_NUMBER = re.compile(r"^\d+[A-Za-z]?$")
_RE_LIST_LABEL = re.compile(r"^[a-zA-Z]\.?$")
_RE_PAREN_LABEL = re.compile(r"^\([a-zA-Z]\)$")
_CLML_PROVISION_PARENT_TAGS = frozenset({"P1"})
_CLML_PARAGRAPH_PARENT_TAGS = frozenset({"P2"})
_CLML_LIST_PARENT_TAGS = frozenset({"P3"})


def _local_name(tag_name: str) -> str:
    if "}" in tag_name:
        return tag_name.split("}", maxsplit=1)[1]
    return tag_name


def _inline_text(node: ElementTree.Element) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in list(node):
        child_name = _local_name(child.tag)
        if child_name in _CLML_BLOCK_TAGS:
            if child.tail:
                parts.append(child.tail)
            continue
        parts.append(_inline_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _has_block_children(node: ElementTree.Element) -> bool:
    return any(_local_name(child.tag) in _CLML_BLOCK_TAGS for child in list(node))


class _ClmlTextBuilder:
    def __init__(self) -> None:
        self._buffer = ""

    def append(self, piece: str) -> None:
        if not piece or not piece.strip():
            return
        trailing_space = piece.endswith(" ") and not piece.endswith("  ")
        text = piece.lstrip()
        if trailing_space and not text.endswith(" "):
            text = f"{text} "
        if not self._buffer:
            self._buffer = text
            return
        if self._buffer[-1].isdigit() and text.startswith("("):
            self._buffer += text.lstrip()
            return
        if self._needs_space(self._buffer, text):
            self._buffer = f"{self._buffer} {text.lstrip()}"
        else:
            self._buffer += text

    def append_paragraph_marker(self, raw: str, *, before_text: bool) -> None:
        text = raw.strip()
        if before_text:
            marker = text if text.endswith(".") else f"{text}."
            self.append(f"{marker} ")
            return
        core = text.rstrip(".")
        if self._buffer and self._buffer[-1].isdigit() and core.isdigit():
            self._buffer += core
            return
        self.append(core)

    def append_subparagraph_marker(self, raw: str) -> None:
        core = raw.strip().rstrip(".")
        marker = core if _RE_PAREN_LABEL.match(core) else f"({core})"
        if self._buffer and self._buffer[-1].isdigit():
            self._buffer += marker
            return
        self.append(marker)

    def append_list_marker(self, raw: str) -> None:
        core = raw.strip().rstrip(".")
        if _RE_PAREN_LABEL.match(core):
            marker = core
        else:
            marker = f"({core.lower()})"
        self.append(marker)

    def finish(self) -> str:
        return " ".join(self._buffer.split()).strip()

    @staticmethod
    def _needs_space(left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left[-1].isspace() or right[0].isspace():
            return False
        if right.startswith("("):
            return True
        if left.endswith(("—", "–", "-", ",", ";", ":")):
            return True
        if left.endswith(")") and right[0].isalnum():
            return True
        if left[-1].isdigit() and right[0].isalpha():
            return True
        if left[-1].isalpha() and right[0].isalpha():
            return True
        return False


def _append_number_for_child(
    builder: _ClmlTextBuilder,
    raw: str,
    *,
    parent_tag: str,
    child_tag: str,
) -> None:
    text = raw.strip()
    if not text:
        return

    prose_child = (
        child_tag == "Text"
        or child_tag in {"Intro", "Lead"}
        or _RE_PROVISION_PARA_TAG.match(child_tag)
    )
    if prose_child:
        if parent_tag in _CLML_PROVISION_PARENT_TAGS:
            builder.append_paragraph_marker(text, before_text=True)
            return
        if parent_tag in _CLML_PARAGRAPH_PARENT_TAGS:
            builder.append_subparagraph_marker(text)
            return
        if parent_tag in _CLML_LIST_PARENT_TAGS:
            builder.append_list_marker(text)
            return
        builder.append_subparagraph_marker(text)
        return

    if child_tag in _CLML_BLOCK_TAGS:
        if _RE_LIST_LABEL.match(text):
            builder.append_list_marker(text)
            return
        if _RE_SUBPARAGRAPH_NUMBER.match(text.rstrip(".")) and parent_tag in {
            "P3",
            "P4",
            "P5",
            "P6",
        }:
            builder.append_subparagraph_marker(text)
            return
        if _RE_PARAGRAPH_NUMBER.match(text):
            builder.append_paragraph_marker(text, before_text=False)
            return

    if _RE_PAREN_LABEL.match(text):
        builder.append(text)
        return
    if _RE_LIST_LABEL.match(text):
        builder.append_list_marker(text)
        return
    if _RE_SUBPARAGRAPH_NUMBER.match(text.rstrip(".")):
        builder.append_subparagraph_marker(text)
        return
    builder.append_paragraph_marker(text, before_text=True)


def _serialize_clml_element(node: ElementTree.Element) -> str:
    node_name = _local_name(node.tag)
    if not list(node):
        return _inline_text(node).strip()
    if node_name == "Text" and not _has_block_children(node):
        return _inline_text(node).strip()
    if node_name not in _CLML_BLOCK_TAGS:
        return _inline_text(node).strip()

    builder = _ClmlTextBuilder()
    pending_number: str | None = None
    for child in list(node):
        child_name = _local_name(child.tag)
        if child_name in _CLML_NUMBER_TAGS:
            pending_number = _inline_text(child).strip()
            continue
        if child_name in _CLML_SKIP_TAGS:
            continue
        if pending_number is not None:
            number_child_tag = (
                "Text"
                if _RE_PROVISION_PARA_TAG.match(child_name)
                else child_name
            )
            _append_number_for_child(
                builder,
                pending_number,
                parent_tag=node_name,
                child_tag=number_child_tag,
            )
            pending_number = None
        if child_name in _CLML_BLOCK_TAGS:
            builder.append(_serialize_clml_element(child))
            continue
        builder.append(_inline_text(child))

    if pending_number is not None:
        _append_number_for_child(
            builder,
            pending_number,
            parent_tag=node_name,
            child_tag="Text",
        )

    return builder.finish()


def serialize_clml_text(node: ElementTree.Element) -> str:
    """Render CLML subtree text with readable numbering and list-label boundaries."""
    return _serialize_clml_element(node)
