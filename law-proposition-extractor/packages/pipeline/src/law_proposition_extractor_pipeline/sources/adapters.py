import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .clml_heading import (
    collect_heading_provenance,
    extract_direct_descriptive_title,
    extract_direct_number_label,
    normalize_heading_whitespace,
    serialize_clml_heading_text,
)
from .clml_text import serialize_clml_text
from .legislation_effects import parse_source_legal_effects
from .legislation_manifestation import resolve_manifestation_provenance


@dataclass(frozen=True)
class SourceFetchRequest:
    authority: str
    authority_source_id: str
    version_id: str
    expected_content_hash: str | None
    raw_source: dict[str, Any]


@dataclass(frozen=True)
class SourcePayload:
    title: str
    jurisdiction: str
    citation: str
    kind: str
    authoritative_text: str
    authoritative_locator: str
    provenance: str
    as_of_date: Any | None
    retrieved_at: Any | None
    source_url: str | None
    review_status: Any
    metadata: dict[str, Any]
    # Optional authority manifestation fields (legislation.gov.uk); copied onto SourceSnapshot.
    manifestation_type: Any | None = None
    manifestation_basis: Any | None = None
    requested_as_of_date: Any | None = None
    resolved_as_of_date: Any | None = None
    source_revision_date: Any | None = None
    requested_manifestation: Any | None = None
    resolved_manifestation: Any | None = None
    manifestation_evidence: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class AdapterFetchResult:
    payload: SourcePayload
    trace_metadata: dict[str, Any]


class AuthorityAdapter(Protocol):
    authority_name: str

    def fetch(self, request: SourceFetchRequest) -> AdapterFetchResult: ...


class CaseFileAuthorityAdapter:
    """
    Adapter for inline case-file sources.

    This is intentionally simple so that a future legislation.gov.uk adapter can
    implement the same `fetch` contract and be swapped in through the registry.
    """

    authority_name = "case_file"

    def fetch(self, request: SourceFetchRequest) -> AdapterFetchResult:
        raw = request.raw_source
        locator = raw.get("authoritative_locator") or raw.get("fragment_locator") or "document:full"
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        return AdapterFetchResult(
            payload=SourcePayload(
                title=raw["title"],
                jurisdiction=raw["jurisdiction"],
                citation=raw["citation"],
                kind=raw["kind"],
                authoritative_text=str(raw.get("text", "")),
                authoritative_locator=locator,
                provenance=str(raw.get("provenance", "demo.case_file")),
                as_of_date=raw.get("as_of_date"),
                retrieved_at=raw.get("retrieved_at"),
                source_url=raw.get("source_url"),
                review_status=raw.get("review_status", "proposed"),
                metadata=metadata,
            ),
            trace_metadata={"source_kind": "inline_case_file"},
        )


def _local_name(tag_name: str) -> str:
    if "}" in tag_name:
        return tag_name.split("}", maxsplit=1)[1]
    return tag_name


def _first_text(root: ElementTree.Element, candidates: set[str]) -> str | None:
    for node in root.iter():
        if _local_name(node.tag) in candidates:
            text = "".join(node.itertext()).strip()
            if text:
                return " ".join(text.split())
    return None


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split()).strip()


def _looks_like_noise_text(value: str) -> bool:
    lowered = value.lower()
    if len(lowered) < 4:
        return True
    noise_markers = (
        "changes to legislation",
        "no changes have been applied",
        "introductory text",
        "opening options",
        "more resources",
        "correction slips",
        "impact assessments",
        "explanatory memorandum",
        "explanatory notes",
        "policy notes",
        "show timeline",
        "geographical extent",
        "commencement information",
        "extent information",
        "annotations",
        "table of contents",
        "print options",
    )
    if any(marker in lowered for marker in noise_markers):
        return True
    if lowered.startswith("status:"):
        return True
    return False


def _extract_locator_from_node(node: ElementTree.Element) -> str | None:
    for key in (
        "id",
        "eId",
        "eid",
        "EId",
        "URI",
        "uri",
        "DocumentURI",
        "documentURI",
        "href",
        "Ref",
    ):
        value = node.attrib.get(key)
        if value:
            return f"xml:{value.strip()}"
    return None


def _infer_locator_from_text(value: str) -> str | None:
    patterns = (
        (r"\b(article)\s+(\d+[a-z]?)\b", "article"),
        (r"\b(section)\s+(\d+[a-z]?)\b", "section"),
        (r"\b(regulation)\s+(\d+[a-z]?)\b", "regulation"),
        (r"\b(paragraph)\s+(\d+[a-z]?)\b", "paragraph"),
        (r"\b(schedule)\s+(\d+[a-z]?)\b", "schedule"),
    )
    for pattern, locator_name in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return f"{locator_name}:{match.group(2).lower()}"
    return None


def _is_operative_locator(locator: str | None) -> bool:
    if not locator:
        return False
    lowered = locator.lower()
    if any(marker in lowered for marker in ("introduction", "preamble", "recital", "note")):
        return False
    return any(
        marker in lowered
        for marker in (
            "article",
            "section",
            "regulation",
            "paragraph",
            "schedule",
            "chapter",
            "part",
        )
    )


def _looks_operative_legal_text(value: str, locator: str | None = None) -> bool:
    if _is_operative_locator(locator):
        return True
    lowered = value.lower()
    if lowered.startswith("whereas "):
        return False
    if any(trigger in lowered for trigger in ("must", "shall", "may", "must not", "shall not")):
        return True
    heading_markers = ("article ", "section ", "regulation ", "paragraph ", "schedule ")
    if any(lowered.startswith(marker) for marker in heading_markers):
        return True
    return False


def _extract_text_chunks(root: ElementTree.Element) -> list[tuple[str, str]]:
    text_nodes = {
        "P",
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
        "Text",
    }
    non_operative_ancestors = {
        "ExplanatoryNotes",
        "Commentaries",
        "Footnotes",
        "Annotations",
        "Contents",
        "TableOfContents",
        "Metadata",
    }

    chunks: list[tuple[str, str]] = []

    def walk(
        node: ElementTree.Element, ancestor_names: tuple[str, ...], inherited_locator: str | None
    ) -> None:
        node_name = _local_name(node.tag)
        current_locator = _extract_locator_from_node(node) or inherited_locator
        next_ancestors = (*ancestor_names, node_name)
        has_non_operative_ancestor = any(
            ancestor in non_operative_ancestors for ancestor in next_ancestors
        )

        if node_name in text_nodes and not has_non_operative_ancestor:
            value = _normalize_whitespace(serialize_clml_text(node))
            if value and not _looks_like_noise_text(value):
                locator = current_locator or _infer_locator_from_text(value) or "document:full"
                chunks.append((locator, value))

        for child in list(node):
            walk(child, next_ancestors, current_locator)

    walk(root, tuple(), None)
    return chunks


_RE_ROOT_PROVISION_ID = re.compile(
    r"^(regulation|article|rule|schedule|annex)-([a-z0-9]+)$",
    re.IGNORECASE,
)
_RE_CONTAINER_ID = re.compile(
    r"^(part|chapter|title|division)-([a-z0-9]+)$",
    re.IGNORECASE,
)
_RE_SCHEDULE_PARAGRAPH_ID = re.compile(
    r"^schedule-([a-z0-9]+)-paragraph-([a-z0-9]+)$",
    re.IGNORECASE,
)
_RE_SCHEDULE_NUMERIC_PARAGRAPH_ID = re.compile(
    r"^schedule-([a-z0-9]+)-([a-z0-9]+)$",
    re.IGNORECASE,
)
_RE_PROVISION_PARAGRAPH_ID = re.compile(
    r"^(regulation|article|rule)-([a-z0-9]+)-(\d+[a-z]?)$",
    re.IGNORECASE,
)
_RE_PROVISION_SUBPARAGRAPH_ID = re.compile(
    r"^(regulation|article|rule)-([a-z0-9]+)-(\d+[a-z]?)-([a-z0-9]+)$",
    re.IGNORECASE,
)
_RE_TARGET_CITATION = re.compile(
    r"\b(Regulation|Article|Rule|Schedule|Annex)\s+([0-9]+[A-Za-z]?)\b"
)
_CONTAINER_KINDS = frozenset({"part", "chapter", "title", "division"})


def _classify_fragment_kind(locator: str, text: str) -> str:
    lowered_locator = locator.lower()
    lowered_text = text.lower()
    if re.match(r"^schedule:[^:]+$", lowered_locator):
        return "schedule"
    amendment_markers = (
        "amend",
        "amended",
        "substitute",
        "insert",
        "omit",
        "revoke",
        "replace",
        "for ",
    )
    if any(marker in lowered_text for marker in amendment_markers):
        return "amendment_provision"
    operative_markers = ("must", "shall", "may", "must not", "shall not")
    if any(marker in lowered_text for marker in operative_markers):
        return "operative_provision"
    return "unknown"


def _possible_target_citation(text: str) -> str | None:
    match = _RE_TARGET_CITATION.search(text)
    if not match:
        return None
    return f"{match.group(1).lower()}:{match.group(2).lower()}"


def _match_structural_node_id(
    node_id: str,
) -> tuple[str, str, bool, str | None] | None:
    """Map a CLML @id to (locator, source_path, is_container, id_implied_parent).

    `id_implied_parent` captures paragraph→provision encoding from the id itself.
    It is used only when XML nesting does not already supply a fragment ancestor
    (common for flat schedule/paragraph CLML siblings).
    """
    cleaned = node_id.strip()
    if not cleaned:
        return None

    match_container = _RE_CONTAINER_ID.match(cleaned)
    if match_container:
        unit_kind = match_container.group(1).lower()
        unit_number = match_container.group(2).lower()
        return f"{unit_kind}:{unit_number}", f"{unit_kind}/{unit_number}", True, None

    match_root = _RE_ROOT_PROVISION_ID.match(cleaned)
    if match_root:
        unit_kind = match_root.group(1).lower()
        unit_number = match_root.group(2).lower()
        return f"{unit_kind}:{unit_number}", f"{unit_kind}/{unit_number}", False, None

    match_subpara = _RE_PROVISION_SUBPARAGRAPH_ID.match(cleaned)
    if match_subpara:
        unit_kind = match_subpara.group(1).lower()
        unit_number = match_subpara.group(2).lower()
        para_number = match_subpara.group(3).lower()
        point_number = match_subpara.group(4).lower()
        locator = (
            f"{unit_kind}:{unit_number}:paragraph:{para_number}:subparagraph:{point_number}"
        )
        source_path = (
            f"{unit_kind}/{unit_number}/paragraph/{para_number}/subparagraph/{point_number}"
        )
        id_parent = f"{unit_kind}:{unit_number}:paragraph:{para_number}"
        return locator, source_path, False, id_parent

    match_provision_para = _RE_PROVISION_PARAGRAPH_ID.match(cleaned)
    if match_provision_para:
        unit_kind = match_provision_para.group(1).lower()
        unit_number = match_provision_para.group(2).lower()
        para_number = match_provision_para.group(3).lower()
        locator = f"{unit_kind}:{unit_number}:paragraph:{para_number}"
        source_path = f"{unit_kind}/{unit_number}/paragraph/{para_number}"
        return locator, source_path, False, f"{unit_kind}:{unit_number}"

    match_para = _RE_SCHEDULE_PARAGRAPH_ID.match(cleaned)
    if match_para:
        schedule_number = match_para.group(1).lower()
        para_number = match_para.group(2).lower()
        locator = f"schedule:{schedule_number}:paragraph:{para_number}"
        source_path = f"schedule/{schedule_number}/paragraph/{para_number}"
        return locator, source_path, False, f"schedule:{schedule_number}"

    match_numeric_para = _RE_SCHEDULE_NUMERIC_PARAGRAPH_ID.match(cleaned)
    if match_numeric_para:
        schedule_number = match_numeric_para.group(1).lower()
        para_number = match_numeric_para.group(2).lower()
        # Avoid treating schedule root ids as paragraphs.
        if _RE_ROOT_PROVISION_ID.match(cleaned):
            return None
        locator = f"schedule:{schedule_number}:paragraph:{para_number}"
        source_path = f"schedule/{schedule_number}/paragraph/{para_number}"
        return locator, source_path, False, f"schedule:{schedule_number}"

    return None


_PROVISION_GROUP_TAGS = frozenset({"P1group", "P2group", "P3group"})
_ROOT_PROVISION_KINDS = frozenset(
    {"article", "regulation", "rule", "schedule", "annex", "section"}
)


def _container_number_and_title(
    node: ElementTree.Element, *, locator: str
) -> tuple[str, str | None, dict[str, Any] | None]:
    """Return (fragment_text/number_label, descriptive title, structural_heading dict).

    Number and descriptive Title are captured separately. ``fragment_text`` keeps
    the short number/label for containers (existing non-operative behaviour).
    """
    number_label = extract_direct_number_label(node)
    title_text, change_ids, commentary_refs, source_element = extract_direct_descriptive_title(
        node
    )
    # Preserve legacy short container body when Number precedes Title.
    fragment_text: str
    if number_label:
        fragment_text = number_label
    elif title_text:
        fragment_text = title_text
        number_label = None
    else:
        fragment_text = ""
        for child in list(node):
            if _local_name(child.tag) != "Subtitle":
                continue
            value = normalize_heading_whitespace(serialize_clml_heading_text(child))
            if value and not _looks_like_noise_text(value):
                fragment_text = value
                break
        if not fragment_text:
            kind, _, number = locator.partition(":")
            label = kind.capitalize() if kind else "Container"
            fragment_text = f"{label} {number}".strip()
        number_label = fragment_text

    structural_heading: dict[str, Any] | None = None
    if title_text:
        locator_kind = locator.split(":", maxsplit=1)[0].lower()
        structural_heading = {
            "kind": locator_kind,
            "text": title_text,
            "number_label": number_label,
            "owner_locator": locator,
            "source_element": source_element or "Title",
            "change_ids": list(change_ids),
            "commentary_refs": list(commentary_refs),
        }
    return fragment_text, number_label, structural_heading


def _direct_root_provision_children(
    group: ElementTree.Element,
) -> list[ElementTree.Element]:
    """Direct children that are root-level structural provisions (article/…)."""
    out: list[ElementTree.Element] = []
    for child in list(group):
        node_id = (
            child.attrib.get("id")
            or child.attrib.get("eId")
            or child.attrib.get("eid")
            or ""
        ).strip()
        if not node_id:
            continue
        matched = _match_structural_node_id(node_id)
        if matched is None:
            continue
        locator, _source_path, is_container, _id_parent = matched
        if is_container:
            continue
        kind = locator.split(":", maxsplit=1)[0].lower()
        if kind in _ROOT_PROVISION_KINDS and locator.count(":") == 1:
            out.append(child)
    return out


def _safe_group_title_for_provision(
    group: ElementTree.Element,
    *,
    provision_node: ElementTree.Element,
    provision_locator: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Assign a P*group/Title heading only under the safe single-owner rule.

    Safe when:
    - heading Title is a direct child of the group;
    - provision is a direct child of the same group;
    - exactly one compatible direct root provision child owns the heading.

    Multi-provision titled groups are not assigned; a diagnostic is returned.
    """
    if _local_name(group.tag) not in _PROVISION_GROUP_TAGS:
        return None, None
    title_children = [c for c in list(group) if _local_name(c.tag) == "Title"]
    if len(title_children) != 1:
        return None, None
    if provision_node not in list(group):
        return None, None
    root_provisions = _direct_root_provision_children(group)
    if len(root_provisions) == 0:
        return None, None
    if len(root_provisions) > 1:
        return (
            None,
            "multi_provision_group_title_unassigned:"
            f"{provision_locator}:direct_provisions={len(root_provisions)}",
        )
    if root_provisions[0] is not provision_node:
        return None, None
    title_el = title_children[0]
    text = serialize_clml_heading_text(title_el)
    if not text:
        return None, None
    change_ids, commentary_refs = collect_heading_provenance(title_el)
    number_label = extract_direct_number_label(provision_node)
    kind = provision_locator.split(":", maxsplit=1)[0].lower()
    return (
        {
            "kind": kind,
            "text": text,
            "number_label": number_label,
            "owner_locator": provision_locator,
            "source_element": "Title",
            "change_ids": list(change_ids),
            "commentary_refs": list(commentary_refs),
        },
        None,
    )


_DIRECT_TITLE_PROVISION_KINDS = frozenset({"schedule", "annex"})
_OPERATIVE_BODY_CHILD_TAGS = frozenset(
    {
        "P1para",
        "P2para",
        "P3para",
        "P4para",
        "Text",
        "Intro",
        "Lead",
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
    }
)


def _direct_provision_title_heading(
    node: ElementTree.Element,
    *,
    provision_locator: str,
) -> dict[str, Any] | None:
    """Capture a Schedule/Annex Title that lives on the provision itself.

    Used when there is no owning P*group Title. Does not assign instrument titles
    or multi-provision cross-headings.
    """
    kind = provision_locator.split(":", maxsplit=1)[0].lower()
    if kind not in _DIRECT_TITLE_PROVISION_KINDS:
        return None
    title_text, change_ids, commentary_refs, source_element = extract_direct_descriptive_title(
        node
    )
    if not title_text:
        return None
    number_label = extract_direct_number_label(node)
    return {
        "kind": kind,
        "text": title_text,
        "number_label": number_label,
        "owner_locator": provision_locator,
        "source_element": source_element or "Title",
        "change_ids": list(change_ids),
        "commentary_refs": list(commentary_refs),
    }


def _operative_root_provision_text(
    node: ElementTree.Element,
    *,
    locator: str,
) -> str:
    """Serialize operative provision text without splicing legislative Titles.

    Schedule/Annex elements are not CLML block tags, so the generic serializer
    falls back to inline text that would otherwise include Title children.
    Prefer para/body descendants; strip Number/Title prefixes as a fallback.
    """
    kind = locator.split(":", maxsplit=1)[0].lower()
    raw = _normalize_whitespace(serialize_clml_text(node))
    if kind not in _DIRECT_TITLE_PROVISION_KINDS and _local_name(node.tag) not in {
        "Schedule",
        "Annex",
    }:
        return raw

    title_text, _, _, _ = extract_direct_descriptive_title(node)
    number_label = extract_direct_number_label(node)
    if not title_text and not number_label:
        return raw

    body_parts: list[str] = []
    for child in list(node):
        child_name = _local_name(child.tag)
        if child_name in {"Title", "Number", "Pnumber"}:
            continue
        if child_name not in _OPERATIVE_BODY_CHILD_TAGS and not child_name.startswith("P"):
            continue
        part = _normalize_whitespace(serialize_clml_text(child))
        if part:
            body_parts.append(part)
    if body_parts:
        return " ".join(body_parts)

    cleaned = raw
    if number_label and cleaned.startswith(number_label):
        cleaned = cleaned[len(number_label) :].strip()
    if title_text and cleaned.startswith(title_text):
        cleaned = cleaned[len(title_text) :].strip()
    return cleaned or raw


def _build_legislation_structural_fragments(
    *,
    root: ElementTree.Element,
    source_url: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build structural fragment rows using XML traversal ancestry for parents.

    Parent assignment comes from the nearest active ancestor node that itself
    created a structural fragment. Sibling top-level provisions therefore share
    a container parent (or null) and never parent each other.

    Legislative headings (P1group/Title, container descriptive Title) are stored
    as first-class structural metadata — never spliced into operative fragment text.
    """
    document_uri = root.attrib.get("DocumentURI", "").strip().rstrip("/")
    if source_url.endswith("/data.xml"):
        source_base_url = source_url[: -len("/data.xml")]
    else:
        source_base_url = source_url.rstrip("/")

    order_index = 0
    structural_rows: list[dict[str, Any]] = []
    known_locators: set[str] = set()
    provision_links: list[str] = []

    def walk(
        node: ElementTree.Element,
        ancestor_locators: list[str],
        parent: ElementTree.Element | None,
    ) -> None:
        nonlocal order_index
        node_id = (
            node.attrib.get("id")
            or node.attrib.get("eId")
            or node.attrib.get("eid")
            or ""
        ).strip()
        matched = _match_structural_node_id(node_id) if node_id else None
        pushed = False

        if matched is not None:
            locator, source_path, is_container, id_implied_parent = matched
            if locator not in known_locators:
                number_label: str | None = None
                structural_heading: dict[str, Any] | None = None
                heading_diagnostic: str | None = None
                if is_container:
                    node_text, number_label, structural_heading = _container_number_and_title(
                        node, locator=locator
                    )
                else:
                    number_label = extract_direct_number_label(node)
                    if parent is not None:
                        structural_heading, heading_diagnostic = _safe_group_title_for_provision(
                            parent,
                            provision_node=node,
                            provision_locator=locator,
                        )
                    if structural_heading is None:
                        structural_heading = _direct_provision_title_heading(
                            node, provision_locator=locator
                        )
                    node_text = _operative_root_provision_text(node, locator=locator)
                accept = bool(node_text) and (
                    is_container or not _looks_like_noise_text(node_text)
                )
                if accept:
                    # Prefer XML ancestry. Fall back to id-encoded parents for flat
                    # CLML siblings (e.g. schedule paragraph next to schedule root).
                    # Never invent a parent for top-level provisions (id_implied_parent
                    # is None for those), so sibling articles stay unnested.
                    stack_parent = ancestor_locators[-1] if ancestor_locators else None
                    if stack_parent:
                        parent_locator = stack_parent
                    elif id_implied_parent and id_implied_parent in known_locators:
                        parent_locator = id_implied_parent
                    else:
                        parent_locator = None
                    known_locators.add(locator)
                    legislation_uri = f"{document_uri}/{source_path}" if document_uri else None
                    legislation_url = f"{source_base_url}/{source_path}"
                    locator_kind = locator.split(":", maxsplit=1)[0].lower()
                    fragment_kind = (
                        locator_kind
                        if locator_kind in _CONTAINER_KINDS
                        else _classify_fragment_kind(locator, node_text)
                    )
                    target_citation = (
                        None if is_container else _possible_target_citation(node_text)
                    )
                    metadata: dict[str, Any] = {
                        "source_path": source_path,
                        "legislation_uri": legislation_uri,
                        "fragment_kind": fragment_kind,
                        "possible_target_citation": target_citation,
                    }
                    if heading_diagnostic:
                        metadata["structural_heading_diagnostic"] = heading_diagnostic
                    row: dict[str, Any] = {
                        "locator": locator,
                        "text": node_text,
                        "parent_locator": parent_locator,
                        "order_index": order_index,
                        "metadata": metadata,
                    }
                    if number_label:
                        row["number_label"] = number_label
                    if structural_heading is not None:
                        row["structural_heading"] = structural_heading
                    structural_rows.append(row)
                    provision_links.append(f"{legislation_url}/data.xml")
                    order_index += 1
                    ancestor_locators.append(locator)
                    pushed = True

        for child in list(node):
            walk(child, ancestor_locators, node)

        if pushed:
            ancestor_locators.pop()

    walk(root, [], None)
    return structural_rows, provision_links


def _jurisdiction_from_series(series: str) -> str:
    series_lower = series.lower()
    if series_lower in {"asp", "ssi"}:
        return "Scotland"
    if series_lower in {"anaw", "wsi", "asc"}:
        return "Wales"
    if series_lower in {"nia", "nisr"}:
        return "Northern Ireland"
    return "UK"


class LegislationGovUkAuthorityAdapter:
    authority_name = "legislation_gov_uk"

    def __init__(
        self,
        *,
        fetch_xml: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
    ) -> None:
        self.fetch_xml = fetch_xml or self._fetch_xml_from_network

    def fetch(self, request: SourceFetchRequest) -> AdapterFetchResult:
        raw = request.raw_source
        source_url = str(
            raw.get("source_url")
            or f"https://www.legislation.gov.uk/{request.authority_source_id.strip('/')}/data.xml"
        )
        xml_text, http_meta = self.fetch_xml(source_url)
        root = ElementTree.fromstring(xml_text)
        resolved_url = str(http_meta.get("resolved_url") or source_url)
        manifestation = resolve_manifestation_provenance(
            requested_url=source_url,
            resolved_url=resolved_url,
            xml_root=root,
        )
        parts = [part for part in request.authority_source_id.split("/") if part]
        if len(parts) < 3:
            raise ValueError(
                "legislation_gov_uk authority_source_id must look like '<series>/<year>/<number>'."
            )

        series = parts[0]
        citation_fallback = f"{series.upper()} {parts[1]}/{parts[2]}"
        title = _first_text(root, {"title", "Title", "DocumentTitle"}) or citation_fallback
        long_title = _first_text(root, {"LongTitle"})
        structural_fragments, provision_links = _build_legislation_structural_fragments(
            root=root,
            source_url=source_url,
        )
        # Placeholder ids: finalized after SourceIngestionService assigns snapshot/record ids.
        draft_effects = parse_source_legal_effects(
            root,
            source_record_id="__pending__",
            source_snapshot_id="__pending__",
        )
        selected_chunks = (
            [(row["locator"], row["text"]) for row in structural_fragments]
            if structural_fragments
            else []
        )
        extracted_chunks = _extract_text_chunks(root)
        locator_scoped_chunks = [
            (locator, value)
            for locator, value in extracted_chunks
            if _is_operative_locator(locator)
        ]
        operative_chunks = [
            (locator, value)
            for locator, value in extracted_chunks
            if _looks_operative_legal_text(value, locator)
        ]
        if not selected_chunks:
            selected_chunks = locator_scoped_chunks or operative_chunks or extracted_chunks
        authoritative_text = "\n".join(value for _, value in selected_chunks).strip()
        fragment_locators = [locator for locator, _ in selected_chunks]
        if not authoritative_text:
            fallback = _normalize_whitespace("".join(root.itertext()))
            if not fallback:
                raise ValueError(
                    "No authoritative text extracted from legislation.gov.uk XML payload."
                )
            authoritative_text = fallback
            fragment_locators = ["document:full"]
        resolved_locator = (
            str(raw.get("authoritative_locator") or raw.get("fragment_locator")).strip()
            if raw.get("authoritative_locator") or raw.get("fragment_locator")
            else ""
        )
        locator = resolved_locator or fragment_locators[0] or "document:full"
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        snapshot_fields = manifestation.as_snapshot_fields()
        # Case-provided as_of_date wins only when manifestation did not resolve a PIT date.
        as_of_date = snapshot_fields.get("as_of_date")
        if as_of_date is None and raw.get("as_of_date") is not None:
            as_of_date = raw.get("as_of_date")
        metadata = {
            **metadata,
            "authority_source_id": request.authority_source_id,
            "source_url": source_url,
            "requested_url": source_url,
            "resolved_url": resolved_url,
            "series": series,
            "http_meta": {
                key: value
                for key, value in http_meta.items()
                if key
                in {
                    "status",
                    "content_type",
                    "response_bytes",
                    "resolved_url",
                    "requested_url",
                }
            },
            "fragment_locators": fragment_locators,
            "structural_fragments": structural_fragments,
            "provision_data_xml_links": provision_links,
            "extracted_chunk_count": len(selected_chunks),
            "structural_fragment_count": len(structural_fragments),
            "locator_scoped_chunk_count": len(locator_scoped_chunks),
            "operative_chunk_count": len(operative_chunks),
            **manifestation.as_metadata(),
            **draft_effects.as_metadata(),
        }
        if long_title:
            metadata["long_title"] = long_title

        payload = SourcePayload(
            title=str(raw.get("title") or title),
            jurisdiction=str(raw.get("jurisdiction") or _jurisdiction_from_series(series)),
            citation=str(raw.get("citation") or citation_fallback),
            kind=str(raw.get("kind") or series.lower()),
            authoritative_text=authoritative_text,
            authoritative_locator=locator,
            provenance=str(raw.get("provenance", "authority.legislation_gov_uk")),
            as_of_date=as_of_date,
            retrieved_at=raw.get("retrieved_at") or datetime.now(UTC),
            source_url=source_url,
            review_status=raw.get("review_status", "proposed"),
            metadata=metadata,
            manifestation_type=snapshot_fields.get("manifestation_type"),
            manifestation_basis=snapshot_fields.get("manifestation_basis"),
            requested_as_of_date=snapshot_fields.get("requested_as_of_date"),
            resolved_as_of_date=snapshot_fields.get("resolved_as_of_date"),
            source_revision_date=snapshot_fields.get("source_revision_date"),
            requested_manifestation=snapshot_fields.get("requested_manifestation"),
            resolved_manifestation=snapshot_fields.get("resolved_manifestation"),
            manifestation_evidence=snapshot_fields.get("manifestation_evidence") or [],
        )
        return AdapterFetchResult(
            payload=payload,
            trace_metadata={
                "source_kind": "authority_fetch",
                "source_url": source_url,
                "resolved_url": resolved_url,
                "http_status": http_meta.get("status"),
                "response_bytes": http_meta.get("response_bytes"),
                "parser": "legislation_gov_uk_data_xml_v1",
                "manifestation_type": (
                    manifestation.manifestation_type.value
                    if manifestation.manifestation_type
                    else None
                ),
            },
        )

    def _fetch_xml_from_network(self, source_url: str) -> tuple[str, dict[str, Any]]:
        request = Request(source_url, headers={"Accept": "application/xml, text/xml;q=0.9"})
        with urlopen(request, timeout=20) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            resolved = getattr(response, "geturl", lambda: source_url)()
            return body.decode(charset, errors="replace"), {
                "status": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "response_bytes": len(body),
                "requested_url": source_url,
                "resolved_url": resolved or source_url,
            }
