"""Parse explicit legislation.gov.uk CLML amendment/effect annotations.

Records only what the consumed source reports. Never applies amendments,
reconstructs history, or claims affecting instruments were independently consumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from typing import Any
from xml.etree import ElementTree

from law_proposition_extractor_domain import (
    AffectingInstrumentConsumptionStatus,
    OutstandingEffectsStatus,
    SourceEffectCategory,
    SourceEffectRepresentationStatus,
    SourceEffectStatus,
    SourceFragment,
    SourceLegalEffect,
    SourceLegalEffectLink,
)

_CHANGE_ELEMENTS = frozenset({"Addition", "Substitution", "Repeal", "Omit"})
_AMENDMENT_COMMENTARY_TYPES = frozenset({"F"})
_EDITORIAL_COMMENTARY_TYPES = frozenset({"X"})
_COMMENCEMENT_COMMENTARY_TYPES = frozenset({"C", "E", "I", "M"})
_DATE_IN_TEXT_RE = re.compile(r"\((\d{1,2})\.(\d{1,2})\.(\d{4})\)")
_EFFECTS_APPLIED_REL = "http://www.legislation.gov.uk/def/legislation/EffectsApplied"

_RE_ROOT_PROVISION_ID = re.compile(
    r"^(regulation|article|rule|schedule|annex)-([a-z0-9]+)$",
    re.IGNORECASE,
)
_RE_PROVISION_PARAGRAPH_ID = re.compile(
    r"^(regulation|article|rule)-([a-z0-9]+)-(\d+[a-z]?)$",
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


def _local_name(tag_name: str) -> str:
    if "}" in tag_name:
        return tag_name.split("}", maxsplit=1)[1]
    return tag_name


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _stable_digest(*parts: str) -> str:
    raw = "|".join(parts)
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def source_effect_id(
    *,
    source_snapshot_id: str,
    annotation_id: str,
    effect_description: str = "",
) -> str:
    return "sourceeffect:" + _stable_digest(
        source_snapshot_id,
        annotation_id,
        _normalize_whitespace(effect_description),
    )


def source_effect_link_id(
    *,
    effect_id: str,
    affected_locator: str | None,
    source_fragment_id: str | None,
) -> str:
    return "sourceeffectlink:" + _stable_digest(
        effect_id,
        affected_locator or "",
        source_fragment_id or "",
    )


def locator_from_clml_id(node_id: str | None) -> str | None:
    """Map a CLML @id / SectionRef to Law Proposition Extractor structural locator when reliable."""
    if not node_id:
        return None
    cleaned = node_id.strip()
    if not cleaned:
        return None

    match_root = _RE_ROOT_PROVISION_ID.match(cleaned)
    if match_root:
        return f"{match_root.group(1).lower()}:{match_root.group(2).lower()}"

    match_para = _RE_PROVISION_PARAGRAPH_ID.match(cleaned)
    if match_para:
        return (
            f"{match_para.group(1).lower()}:{match_para.group(2).lower()}"
            f":paragraph:{match_para.group(3).lower()}"
        )

    match_sched = _RE_SCHEDULE_PARAGRAPH_ID.match(cleaned)
    if match_sched:
        return f"schedule:{match_sched.group(1).lower()}:paragraph:{match_sched.group(2).lower()}"

    match_sched_num = _RE_SCHEDULE_NUMERIC_PARAGRAPH_ID.match(cleaned)
    if match_sched_num:
        return (
            f"schedule:{match_sched_num.group(1).lower()}"
            f":paragraph:{match_sched_num.group(2).lower()}"
        )

    # Walk up compound ids like article-49a-2-a → article:49a:paragraph:2
    parts = cleaned.split("-")
    for end in range(len(parts) - 1, 2, -1):
        candidate = "-".join(parts[:end])
        resolved = locator_from_clml_id(candidate)
        if resolved is not None:
            return resolved
    return None


def normalize_effect_category(raw: str | None) -> SourceEffectCategory:
    if not raw:
        return SourceEffectCategory.UNKNOWN
    lowered = raw.strip().lower()
    mapping = {
        "addition": SourceEffectCategory.INSERTION,
        "insertion": SourceEffectCategory.INSERTION,
        "inserted": SourceEffectCategory.INSERTION,
        "words inserted": SourceEffectCategory.INSERTION,
        "substitution": SourceEffectCategory.SUBSTITUTION,
        "substituted": SourceEffectCategory.SUBSTITUTION,
        "words substituted": SourceEffectCategory.SUBSTITUTION,
        "omit": SourceEffectCategory.OMISSION,
        "omission": SourceEffectCategory.OMISSION,
        "omitted": SourceEffectCategory.OMISSION,
        "words omitted": SourceEffectCategory.OMISSION,
        "repeal": SourceEffectCategory.REPEAL,
        "repealed": SourceEffectCategory.REPEAL,
        "revocation": SourceEffectCategory.REVOCATION,
        "revoked": SourceEffectCategory.REVOCATION,
        "commencement": SourceEffectCategory.COMMENCEMENT,
        "extent": SourceEffectCategory.EXTENT,
        "editorial": SourceEffectCategory.EDITORIAL_NOTE,
        "editorial_note": SourceEffectCategory.EDITORIAL_NOTE,
        "corrigendum": SourceEffectCategory.EDITORIAL_NOTE,
    }
    if lowered in mapping:
        return mapping[lowered]
    if "substitut" in lowered:
        return SourceEffectCategory.SUBSTITUTION
    if "insert" in lowered or "addition" in lowered:
        return SourceEffectCategory.INSERTION
    if "omit" in lowered:
        return SourceEffectCategory.OMISSION
    if "repeal" in lowered:
        return SourceEffectCategory.REPEAL
    if "revok" in lowered:
        return SourceEffectCategory.REVOCATION
    return SourceEffectCategory.UNKNOWN


def _parse_effect_date_from_text(text: str) -> date | None:
    match = _DATE_IN_TEXT_RE.search(text)
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _is_amendment_commentary_text(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "inserted by",
        "substituted by",
        "omitted by",
        "repealed by",
        "revoked by",
        "amended by",
        "words in ",
        "words substituted",
        "words omitted",
        "words inserted",
    )
    return any(marker in lowered for marker in markers)


@dataclass
class _CommentaryRecord:
    annotation_id: str
    annotation_label: str | None
    commentary_type: str
    description: str
    affecting_instrument_uri: str | None = None
    affecting_instrument_citation: str | None = None
    affecting_instrument_title: str | None = None
    affecting_instrument_provision: str | None = None
    citation_section_refs: list[str] = field(default_factory=list)
    effect_date: date | None = None
    raw_category_hints: list[str] = field(default_factory=list)


@dataclass
class ParsedSourceLegalEffects:
    """Intermediate inventory before final fragment IDs are known."""

    effects: list[SourceLegalEffect] = field(default_factory=list)
    # provisional links keyed by effect_id → sorted unique locators (may be empty)
    effect_locators: dict[str, list[str]] = field(default_factory=dict)
    outstanding_effects_status: OutstandingEffectsStatus = (
        OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN
    )
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    unresolved_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "source_legal_effects_draft": {
                "effects": [effect.model_dump(mode="json") for effect in self.effects],
                "effect_locators": {
                    effect_id: list(locators)
                    for effect_id, locators in sorted(self.effect_locators.items())
                },
                "outstanding_effects_status": self.outstanding_effects_status.value,
                "diagnostics": list(self.diagnostics),
                "unresolved_refs": list(self.unresolved_refs),
                "metadata": dict(self.metadata),
            }
        }


def _parent_map(root: ElementTree.Element) -> dict[ElementTree.Element, ElementTree.Element]:
    parents: dict[ElementTree.Element, ElementTree.Element] = {}
    for parent in root.iter():
        for child in list(parent):
            parents[child] = parent
    return parents


def _ancestor_provision_locator(
    node: ElementTree.Element,
    parents: dict[ElementTree.Element, ElementTree.Element],
) -> str | None:
    current: ElementTree.Element | None = node
    while current is not None:
        node_id = (current.attrib.get("id") or "").strip()
        locator = locator_from_clml_id(node_id) if node_id else None
        if locator is not None:
            return locator
        current = parents.get(current)
    return None


def _extract_commentary_records(root: ElementTree.Element) -> list[_CommentaryRecord]:
    records: list[_CommentaryRecord] = []
    f_index = 0
    for node in root.iter():
        if _local_name(node.tag) != "Commentary":
            continue
        annotation_id = (node.attrib.get("id") or "").strip()
        if not annotation_id:
            continue
        commentary_type = (node.attrib.get("Type") or "").strip()
        description = _normalize_whitespace("".join(node.itertext()))
        label: str | None = None
        if commentary_type in _AMENDMENT_COMMENTARY_TYPES:
            f_index += 1
            label = f"F{f_index}"

        affecting_uri: str | None = None
        affecting_citation: str | None = None
        affecting_title: str | None = None
        affecting_provision: str | None = None
        section_refs: list[str] = []

        for child in node.iter():
            name = _local_name(child.tag)
            if name == "Citation":
                uri = (child.attrib.get("URI") or "").strip() or None
                title = (child.attrib.get("Title") or "").strip() or None
                year = (child.attrib.get("Year") or "").strip()
                number = (child.attrib.get("Number") or "").strip()
                text = _normalize_whitespace("".join(child.itertext()))
                if affecting_uri is None and uri:
                    affecting_uri = uri
                    affecting_title = title or text or None
                    if year and number:
                        class_name = (child.attrib.get("Class") or "").strip()
                        if "StatutoryInstrument" in class_name:
                            affecting_citation = f"S.I. {year}/{number}"
                        else:
                            affecting_citation = f"{year}/{number}"
                    elif text:
                        affecting_citation = text
            elif name == "CitationSubRef":
                section_ref = (child.attrib.get("SectionRef") or "").strip()
                if section_ref:
                    section_refs.append(section_ref)
                if child.attrib.get("Operative", "").lower() == "true":
                    prov_text = _normalize_whitespace("".join(child.itertext()))
                    if prov_text and affecting_provision is None:
                        affecting_provision = prov_text

        records.append(
            _CommentaryRecord(
                annotation_id=annotation_id,
                annotation_label=label,
                commentary_type=commentary_type,
                description=description,
                affecting_instrument_uri=affecting_uri,
                affecting_instrument_citation=affecting_citation,
                affecting_instrument_title=affecting_title,
                affecting_instrument_provision=affecting_provision,
                citation_section_refs=section_refs,
                effect_date=_parse_effect_date_from_text(description),
            )
        )
    return records


def _collect_change_refs(
    root: ElementTree.Element,
    parents: dict[ElementTree.Element, ElementTree.Element],
) -> dict[str, set[str]]:
    """Map CommentaryRef → set of affected structural locators from inline change markers."""
    refs: dict[str, set[str]] = {}
    for node in root.iter():
        name = _local_name(node.tag)
        if name not in _CHANGE_ELEMENTS:
            continue
        commentary_ref = (node.attrib.get("CommentaryRef") or "").strip()
        if not commentary_ref:
            continue
        locator = _ancestor_provision_locator(node, parents)
        refs.setdefault(commentary_ref, set())
        if locator:
            refs[commentary_ref].add(locator)
    return refs


def _collect_change_element_types(
    root: ElementTree.Element,
) -> dict[str, set[str]]:
    types: dict[str, set[str]] = {}
    for node in root.iter():
        name = _local_name(node.tag)
        if name not in _CHANGE_ELEMENTS:
            continue
        commentary_ref = (node.attrib.get("CommentaryRef") or "").strip()
        if commentary_ref:
            types.setdefault(commentary_ref, set()).add(name)
    return types


def _outstanding_status(root: ElementTree.Element) -> tuple[OutstandingEffectsStatus, list[ElementTree.Element]]:
    containers = [n for n in root.iter() if _local_name(n.tag) == "UnappliedEffects"]
    if not containers:
        return OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN, []
    effects: list[ElementTree.Element] = []
    for container in containers:
        for child in list(container):
            if _local_name(child.tag) == "UnappliedEffect":
                effects.append(child)
    if effects:
        return OutstandingEffectsStatus.SOURCE_REPORTS_PRESENT, effects
    return OutstandingEffectsStatus.SOURCE_REPORTS_NONE, []


def _effects_applied_link_present(root: ElementTree.Element) -> bool:
    for node in root.iter():
        if _local_name(node.tag) != "link":
            continue
        rel = (node.attrib.get("rel") or "").strip()
        if rel == _EFFECTS_APPLIED_REL:
            return True
    return False


def parse_source_legal_effects(
    root: ElementTree.Element,
    *,
    source_record_id: str,
    source_snapshot_id: str,
) -> ParsedSourceLegalEffects:
    """Extract source-reported legal effects from CLML without fragment linkage."""
    parents = _parent_map(root)
    commentaries = _extract_commentary_records(root)
    commentary_by_id = {item.annotation_id: item for item in commentaries}
    change_refs = _collect_change_refs(root, parents)
    change_types = _collect_change_element_types(root)
    outstanding_status, unapplied_nodes = _outstanding_status(root)

    effects: list[SourceLegalEffect] = []
    effect_locators: dict[str, list[str]] = {}
    diagnostics: list[dict[str, Any]] = []
    seen_effect_keys: set[str] = set()

    # Commentary-backed amendment / editorial / commencement annotations.
    for commentary in commentaries:
        ctype = commentary.commentary_type
        referenced = commentary.annotation_id in change_refs
        is_amendment_type = ctype in _AMENDMENT_COMMENTARY_TYPES
        is_editorial = ctype in _EDITORIAL_COMMENTARY_TYPES
        is_commencement = ctype in _COMMENCEMENT_COMMENTARY_TYPES

        if is_amendment_type and not (
            referenced or _is_amendment_commentary_text(commentary.description)
        ):
            # Type=F without amendment content and without inline refs — skip as bare footnote.
            continue
        if not (is_amendment_type or is_editorial or is_commencement):
            continue
        if is_editorial and not referenced and not _is_amendment_commentary_text(
            commentary.description
        ):
            # Editorial note without amendment markers — record as editorial, not amendment.
            pass

        raw_hints = sorted(change_types.get(commentary.annotation_id, set()))
        if is_commencement:
            category = SourceEffectCategory.COMMENCEMENT
            raw_category = ctype or "C"
        elif is_editorial and not referenced:
            category = SourceEffectCategory.EDITORIAL_NOTE
            raw_category = ctype or "X"
        elif raw_hints:
            # Prefer most specific change marker (Substitution over enclosing Addition).
            preferred = (
                "Substitution"
                if "Substitution" in raw_hints
                else "Repeal"
                if "Repeal" in raw_hints
                else "Omit"
                if "Omit" in raw_hints
                else raw_hints[0]
            )
            category = normalize_effect_category(preferred)
            raw_category = preferred
        elif _is_amendment_commentary_text(commentary.description):
            lowered = commentary.description.lower()
            if "insert" in lowered:
                preferred = "insertion"
            elif "substitut" in lowered:
                preferred = "substitution"
            elif "omit" in lowered:
                preferred = "omission"
            elif "repeal" in lowered:
                preferred = "repeal"
            else:
                preferred = ctype or "unknown"
            category = normalize_effect_category(preferred)
            raw_category = preferred
        elif is_editorial:
            category = SourceEffectCategory.EDITORIAL_NOTE
            raw_category = ctype or "X"
        else:
            category = SourceEffectCategory.UNKNOWN
            raw_category = ctype or None

        # Non-amendment editorial footnotes must not become amendment categories.
        if is_editorial and category not in {
            SourceEffectCategory.EDITORIAL_NOTE,
            SourceEffectCategory.UNKNOWN,
        }:
            # Corrigendum text often says "Substituted by Corrigendum..." — keep editorial.
            category = SourceEffectCategory.EDITORIAL_NOTE
            raw_category = ctype or "X"

        if category == SourceEffectCategory.EDITORIAL_NOTE and not is_amendment_type:
            # Explicit editorial / corrigendum commentary — keep, but not as amendment effect
            # for inventory purposes when Type is X. Still record the annotation.
            pass

        # Skip pure Footnote-element style notes: handled separately (never reached here).
        effect_key = commentary.annotation_id
        if effect_key in seen_effect_keys:
            continue
        seen_effect_keys.add(effect_key)

        # Drop Type=X editorial from "amendment effect" inventory when not referenced
        # by change markers — still record so diagnostics can distinguish.
        include_as_effect = True
        if (
            category == SourceEffectCategory.EDITORIAL_NOTE
            and not referenced
            and not is_amendment_type
        ):
            # Record editorial annotations that look like corrigenda with instrument cites.
            include_as_effect = bool(commentary.affecting_instrument_uri) or bool(
                commentary.description
            )

        if not include_as_effect:
            continue

        # Only emit amendment/commencement/editorial-with-cite; bare F without content skipped above.
        if (
            category == SourceEffectCategory.EDITORIAL_NOTE
            and not is_amendment_type
            and not _is_amendment_commentary_text(commentary.description)
            and not commentary.affecting_instrument_uri
        ):
            continue

        # For Type=X editorial: do not classify as amendment effect in tests —
        # keep category editorial_note.
        eid = source_effect_id(
            source_snapshot_id=source_snapshot_id,
            annotation_id=commentary.annotation_id,
            effect_description=commentary.description,
        )
        representation = SourceEffectRepresentationStatus.ANNOTATION_PRESENT
        if referenced:
            representation = SourceEffectRepresentationStatus.REVISED_TEXT_REFERENCE_PRESENT

        effect = SourceLegalEffect(
            id=eid,
            source_record_id=source_record_id,
            source_snapshot_id=source_snapshot_id,
            annotation_id=commentary.annotation_id,
            annotation_label=commentary.annotation_label,
            effect_category=category,
            raw_effect_category=raw_category,
            effect_description=commentary.description or None,
            affecting_instrument_uri=commentary.affecting_instrument_uri,
            affecting_instrument_citation=commentary.affecting_instrument_citation,
            affecting_instrument_title=commentary.affecting_instrument_title,
            affecting_instrument_provision=commentary.affecting_instrument_provision,
            effect_date=commentary.effect_date,
            effect_status=SourceEffectStatus.SOURCE_STATUS_UNKNOWN,
            source_representation_status=representation,
            independent_consumption_status=AffectingInstrumentConsumptionStatus.NOT_ASSESSED,
            source_evidence={
                "kind": "clml_commentary",
                "annotation_id": commentary.annotation_id,
                "annotation_label": commentary.annotation_label,
                "source_element": "Commentary",
                "raw_effect_type": raw_category,
                "commentary_type": ctype,
                "description": commentary.description,
                "source_location": "CLML Commentaries/Commentary",
                "change_elements": raw_hints,
            },
        )
        effects.append(effect)

        locators: set[str] = set(change_refs.get(commentary.annotation_id, set()))
        for section_ref in commentary.citation_section_refs:
            resolved = locator_from_clml_id(section_ref)
            if resolved:
                locators.add(resolved)
        effect_locators[eid] = sorted(locators)

    # Explicit UnappliedEffect metadata rows.
    for node in unapplied_nodes:
        effect_id_attr = (
            (node.attrib.get("EffectId") or "").strip()
            or (node.attrib.get("URI") or "").strip()
            or _normalize_whitespace("".join(node.itertext()))[:80]
        )
        if not effect_id_attr:
            continue
        if effect_id_attr in seen_effect_keys:
            continue
        seen_effect_keys.add(effect_id_attr)

        raw_type = (node.attrib.get("Type") or "").strip() or None
        category = normalize_effect_category(raw_type)
        description_parts = [
            raw_type or "",
            (node.attrib.get("AffectedProvisions") or "").strip(),
            (node.attrib.get("AffectingProvisions") or "").strip(),
            (node.attrib.get("Notes") or "").strip(),
        ]
        description = _normalize_whitespace(" ".join(p for p in description_parts if p))
        affected_provisions = (node.attrib.get("AffectedProvisions") or "").strip()
        # Do not guess paragraph locators from prose AffectedProvisions like "Art. 49c".
        affected_locator: str | None = None

        eid = source_effect_id(
            source_snapshot_id=source_snapshot_id,
            annotation_id=effect_id_attr,
            effect_description=description,
        )
        affecting_uri = (node.attrib.get("AffectingURI") or "").strip() or None
        affecting_year = (node.attrib.get("AffectingYear") or "").strip()
        affecting_number = (node.attrib.get("AffectingNumber") or "").strip()
        citation = None
        if affecting_year and affecting_number:
            citation = f"S.I. {affecting_year}/{affecting_number}"
        title_nodes = [
            _normalize_whitespace("".join(child.itertext()))
            for child in list(node)
            if _local_name(child.tag) == "AffectingTitle"
        ]
        title = title_nodes[0] if title_nodes else None

        effects.append(
            SourceLegalEffect(
                id=eid,
                source_record_id=source_record_id,
                source_snapshot_id=source_snapshot_id,
                annotation_id=effect_id_attr,
                annotation_label=None,
                effect_category=category,
                raw_effect_category=raw_type,
                effect_description=description or None,
                affected_locator=affected_locator,
                affecting_instrument_uri=affecting_uri,
                affecting_instrument_citation=citation,
                affecting_instrument_title=title,
                affecting_instrument_provision=(
                    (node.attrib.get("AffectingProvisions") or "").strip() or None
                ),
                effect_date=None,
                effect_status=SourceEffectStatus.SOURCE_MARKS_OUTSTANDING,
                source_representation_status=(
                    SourceEffectRepresentationStatus.EFFECT_METADATA_PRESENT
                ),
                independent_consumption_status=(
                    AffectingInstrumentConsumptionStatus.NOT_ASSESSED
                ),
                source_evidence={
                    "kind": "clml_unapplied_effect",
                    "annotation_id": effect_id_attr,
                    "source_element": "UnappliedEffect",
                    "raw_effect_type": raw_type,
                    "description": description,
                    "affected_provisions": affected_provisions or None,
                    "source_location": "CLML Metadata/UnappliedEffects",
                    "requires_applied": node.attrib.get("RequiresApplied"),
                    "notes": (node.attrib.get("Notes") or "").strip() or None,
                },
                metadata={
                    "affected_provisions_raw": affected_provisions or None,
                    "row": node.attrib.get("Row"),
                },
            )
        )
        effect_locators[eid] = []

    # Unresolved CommentaryRef diagnostics (refs that point nowhere).
    for ref in sorted(change_refs):
        if ref not in commentary_by_id:
            diagnostics.append(
                {
                    "code": "source_effect_reference_unresolved",
                    "annotation_id": ref,
                    "message": f"CommentaryRef {ref!r} has no matching Commentary/@id",
                }
            )

    # Also scan for CommentaryRef attributes that are not resolved.
    for node in root.iter():
        ref = (node.attrib.get("CommentaryRef") or "").strip()
        if ref and ref not in commentary_by_id and ref not in change_refs:
            diagnostics.append(
                {
                    "code": "source_effect_reference_unresolved",
                    "annotation_id": ref,
                    "message": f"CommentaryRef {ref!r} unresolved",
                }
            )

    # Deduplicate diagnostics.
    deduped: list[dict[str, Any]] = []
    seen_diag: set[str] = set()
    for item in diagnostics:
        key = f"{item.get('code')}|{item.get('annotation_id')}|{item.get('message')}"
        if key in seen_diag:
            continue
        seen_diag.add(key)
        deduped.append(item)

    # Deterministic effect ordering.
    effects.sort(key=lambda item: (item.annotation_label or "", item.annotation_id or "", item.id))

    return ParsedSourceLegalEffects(
        effects=effects,
        effect_locators=effect_locators,
        outstanding_effects_status=outstanding_status,
        diagnostics=deduped,
        unresolved_refs=sorted(
            {
                str(item.get("annotation_id"))
                for item in deduped
                if item.get("code") == "source_effect_reference_unresolved"
            }
        ),
        metadata={
            "effects_applied_link_present": _effects_applied_link_present(root),
            "commentary_count": len(commentaries),
            "unapplied_effect_count": len(unapplied_nodes),
        },
    )


def link_effects_to_fragments(
    parsed: ParsedSourceLegalEffects,
    fragments: list[SourceFragment],
) -> tuple[list[SourceLegalEffect], list[SourceLegalEffectLink], list[dict[str, Any]]]:
    """Attach final exported fragment IDs to parsed effects."""
    # Prefer exact locator match within the same snapshot; ignore chunk suffixes.
    by_locator: dict[str, list[SourceFragment]] = {}
    for frag in fragments:
        locator = frag.locator.split("|", maxsplit=1)[0].strip()
        if locator:
            by_locator.setdefault(locator, []).append(frag)

    links: list[SourceLegalEffectLink] = []
    diagnostics = list(parsed.diagnostics)
    updated_effects: list[SourceLegalEffect] = []

    for effect in parsed.effects:
        locators = list(parsed.effect_locators.get(effect.id, []))
        # Prefer primary affected locator on the effect when set.
        if effect.affected_locator and effect.affected_locator not in locators:
            locators = [effect.affected_locator, *locators]
        locators = sorted(set(locators))

        linked_fragment_ids: list[str] = []
        if not locators:
            link = SourceLegalEffectLink(
                id=source_effect_link_id(
                    effect_id=effect.id,
                    affected_locator=None,
                    source_fragment_id=None,
                ),
                effect_id=effect.id,
                source_record_id=effect.source_record_id,
                source_snapshot_id=effect.source_snapshot_id,
                source_fragment_id=None,
                affected_locator=None,
                linkage_status="unresolved",
                source_evidence={
                    "kind": "effect_link",
                    "reason": "no_structural_locator",
                },
            )
            # Outstanding metadata-only rows may intentionally lack structural locators.
            if effect.source_representation_status != (
                SourceEffectRepresentationStatus.EFFECT_METADATA_PRESENT
            ):
                diagnostics.append(
                    {
                        "code": "source_effect_affected_fragment_unresolved",
                        "effect_id": effect.id,
                        "annotation_id": effect.annotation_id,
                        "message": "No affected structural locator established from CLML",
                    }
                )
            links.append(link)
            updated_effects.append(effect)
            continue

        primary_fragment_id: str | None = None
        primary_locator: str | None = None
        for locator in locators:
            matches = by_locator.get(locator) or []
            if not matches:
                links.append(
                    SourceLegalEffectLink(
                        id=source_effect_link_id(
                            effect_id=effect.id,
                            affected_locator=locator,
                            source_fragment_id=None,
                        ),
                        effect_id=effect.id,
                        source_record_id=effect.source_record_id,
                        source_snapshot_id=effect.source_snapshot_id,
                        source_fragment_id=None,
                        affected_locator=locator,
                        linkage_status="locator_only",
                        source_evidence={
                            "kind": "effect_link",
                            "reason": "locator_without_exported_fragment",
                        },
                    )
                )
                diagnostics.append(
                    {
                        "code": "source_effect_affected_fragment_unresolved",
                        "effect_id": effect.id,
                        "annotation_id": effect.annotation_id,
                        "affected_locator": locator,
                        "message": f"Locator {locator!r} not present in exported fragments",
                    }
                )
                continue

            # Deterministic: lowest fragment id for this locator.
            frag = sorted(matches, key=lambda item: item.id)[0]
            linked_fragment_ids.append(frag.id)
            if primary_fragment_id is None:
                primary_fragment_id = frag.id
                primary_locator = locator
            links.append(
                SourceLegalEffectLink(
                    id=source_effect_link_id(
                        effect_id=effect.id,
                        affected_locator=locator,
                        source_fragment_id=frag.id,
                    ),
                    effect_id=effect.id,
                    source_record_id=effect.source_record_id,
                    source_snapshot_id=effect.source_snapshot_id,
                    source_fragment_id=frag.id,
                    affected_locator=locator,
                    linkage_status="linked",
                    source_evidence={
                        "kind": "effect_link",
                        "annotation_id": effect.annotation_id,
                        "annotation_label": effect.annotation_label,
                    },
                )
            )

        updated_effects.append(
            effect.model_copy(
                update={
                    "affected_locator": primary_locator or effect.affected_locator,
                    "affected_source_fragment_id": primary_fragment_id,
                }
            )
        )

    # Stable ordering.
    links.sort(key=lambda item: (item.effect_id, item.affected_locator or "", item.id))
    updated_effects.sort(
        key=lambda item: (item.annotation_label or "", item.annotation_id or "", item.id)
    )

    # Deduplicate diagnostics again.
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in diagnostics:
        key = (
            f"{item.get('code')}|{item.get('effect_id')}|{item.get('annotation_id')}|"
            f"{item.get('affected_locator')}|{item.get('message')}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return updated_effects, links, deduped


def finalize_source_legal_effects(
    parsed: ParsedSourceLegalEffects,
    fragments: list[SourceFragment],
) -> dict[str, Any]:
    """Return serializable inventory with fragment links for one snapshot."""
    effects, links, diagnostics = link_effects_to_fragments(parsed, fragments)

    # Annotate fragments with optional back-refs (same-snapshot only).
    effect_ids_by_fragment: dict[str, list[str]] = {}
    for link in links:
        if link.source_fragment_id and link.linkage_status == "linked":
            effect_ids_by_fragment.setdefault(link.source_fragment_id, []).append(link.effect_id)
    for frag in fragments:
        ids = sorted(set(effect_ids_by_fragment.get(frag.id, [])))
        if ids:
            frag.source_legal_effect_ids = sorted(set(frag.source_legal_effect_ids) | set(ids))

    return {
        "effects": [item.model_dump(mode="json") for item in effects],
        "effect_links": [item.model_dump(mode="json") for item in links],
        "outstanding_effects_status": parsed.outstanding_effects_status.value,
        "diagnostics": diagnostics,
        "metadata": dict(parsed.metadata),
    }


def parsed_effects_from_metadata(metadata: dict[str, Any]) -> ParsedSourceLegalEffects | None:
    draft = metadata.get("source_legal_effects_draft")
    if not isinstance(draft, dict):
        return None
    effects_raw = draft.get("effects")
    effects: list[SourceLegalEffect] = []
    if isinstance(effects_raw, list):
        for row in effects_raw:
            if isinstance(row, dict):
                effects.append(SourceLegalEffect.model_validate(row))
    locators_raw = draft.get("effect_locators")
    effect_locators: dict[str, list[str]] = {}
    if isinstance(locators_raw, dict):
        for key, value in locators_raw.items():
            if isinstance(value, list):
                effect_locators[str(key)] = [str(item) for item in value]
    status_raw = draft.get("outstanding_effects_status")
    try:
        status = OutstandingEffectsStatus(str(status_raw))
    except ValueError:
        status = OutstandingEffectsStatus.SOURCE_STATUS_UNKNOWN
    diagnostics = draft.get("diagnostics")
    return ParsedSourceLegalEffects(
        effects=effects,
        effect_locators=effect_locators,
        outstanding_effects_status=status,
        diagnostics=list(diagnostics) if isinstance(diagnostics, list) else [],
        unresolved_refs=list(draft.get("unresolved_refs") or []),
        metadata=dict(draft.get("metadata") or {}),
    )
