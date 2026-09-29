"""Parse explicit legislation.gov.uk manifestation / version semantics.

Conservative, evidence-based classification only. Never infers that Law Proposition Extractor
applied amendments, and never treats intake ``version_id`` as legislative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

from law_proposition_extractor_domain import SourceManifestationBasis, SourceManifestationType

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ORIGINAL_SEGMENTS = frozenset({"enacted", "made", "adopted", "created"})
_PROSPECTIVE_SEGMENTS = frozenset({"prospective"})
_REVISED_SEGMENTS = frozenset({"revised", "current"})
# Path segments that identify the instrument itself, not a manifestation.
_INSTRUMENT_TYPES = frozenset(
    {
        "ukpga",
        "ukla",
        "ukcm",
        "asp",
        "asc",
        "anaw",
        "mwa",
        "uksi",
        "ssi",
        "wsi",
        "nisr",
        "nisi",
        "ukci",
        "ukmo",
        "uksro",
        "eur",
        "eudn",
        "eudr",
        "eut",
    }
)
_DATA_TAIL_RE = re.compile(
    r"/(?:data\.(?:xml|xht|htm|html|rdf|akn|csv|pdf)|contents(?:/data\.(?:xml|xht))?)$",
    re.IGNORECASE,
)
_PROVISION_PATH_HINTS = frozenset(
    {
        "section",
        "article",
        "regulation",
        "schedule",
        "part",
        "chapter",
        "annex",
        "paragraph",
        "introduction",
        "signature",
        "body",
        "contents",
        "resources",
        "annexes",
        "schedules",
    }
)


def _local_name(tag_name: str) -> str:
    if "}" in tag_name:
        return tag_name.split("}", maxsplit=1)[1]
    return tag_name


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    match = _DATE_RE.fullmatch(value.strip())
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _evidence(
    *,
    kind: str,
    field_name: str,
    value: str,
    source_location: str,
) -> dict[str, str]:
    return {
        "kind": kind,
        "field": field_name,
        "value": value,
        "source_location": source_location,
    }


@dataclass(frozen=True)
class RequestManifestationHints:
    requested_url: str | None
    requested_manifestation: SourceManifestationType | None
    requested_as_of_date: date | None
    evidence: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class SourceManifestationHints:
    document_uri: str | None
    document_status: str | None
    dct_valid: date | None
    root_restrict_start_date: date | None
    dc_modified: date | None
    resolved_manifestation: SourceManifestationType | None
    resolved_as_of_date: date | None
    source_revision_date: date | None
    evidence: list[dict[str, str]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ManifestationProvenance:
    manifestation_type: SourceManifestationType
    manifestation_basis: SourceManifestationBasis
    requested_manifestation: SourceManifestationType | None
    resolved_manifestation: SourceManifestationType | None
    requested_as_of_date: date | None
    resolved_as_of_date: date | None
    source_revision_date: date | None
    requested_url: str | None
    resolved_url: str | None
    evidence: list[dict[str, str]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def as_snapshot_fields(self) -> dict[str, Any]:
        """Fields to attach to SourceSnapshot (and optional as_of_date bridge)."""
        # Legal as_of_date only when the authority resolved a point-in-time date.
        as_of = (
            self.resolved_as_of_date
            if self.manifestation_type == SourceManifestationType.POINT_IN_TIME
            else None
        )
        return {
            "manifestation_type": self.manifestation_type,
            "manifestation_basis": self.manifestation_basis,
            "requested_manifestation": self.requested_manifestation,
            "resolved_manifestation": self.resolved_manifestation,
            "requested_as_of_date": self.requested_as_of_date,
            "resolved_as_of_date": self.resolved_as_of_date,
            "source_revision_date": self.source_revision_date,
            "manifestation_evidence": list(self.evidence),
            "as_of_date": as_of,
        }

    def as_metadata(self) -> dict[str, Any]:
        return {
            "manifestation": {
                "type": self.manifestation_type.value,
                "basis": self.manifestation_basis.value,
                "requested_manifestation": (
                    self.requested_manifestation.value if self.requested_manifestation else None
                ),
                "resolved_manifestation": (
                    self.resolved_manifestation.value if self.resolved_manifestation else None
                ),
                "requested_as_of_date": (
                    self.requested_as_of_date.isoformat() if self.requested_as_of_date else None
                ),
                "resolved_as_of_date": (
                    self.resolved_as_of_date.isoformat() if self.resolved_as_of_date else None
                ),
                "source_revision_date": (
                    self.source_revision_date.isoformat() if self.source_revision_date else None
                ),
                "requested_url": self.requested_url,
                "resolved_url": self.resolved_url,
                "evidence": list(self.evidence),
                "conflicts": list(self.conflicts),
            },
            # Captured at resolve time — explanation export must not re-parse XML.
            "manifestation_decision_facts": self.as_decision_facts(),
        }

    def as_decision_facts(self, *, source_snapshot_id: str = "") -> list[dict[str, Any]]:
        """Facts for DecisionExplanation emission (no XML re-parse)."""
        outcome = f"classified_as_{self.manifestation_type.value}"
        classify: dict[str, Any] = {
            "fact_kind": "classify_manifestation",
            "source_snapshot_id": source_snapshot_id or None,
            "manifestation_type": self.manifestation_type.value,
            "manifestation_basis": self.manifestation_basis.value,
            "outcome": outcome,
            "requested_manifestation": (
                self.requested_manifestation.value if self.requested_manifestation else None
            ),
            "resolved_manifestation": (
                self.resolved_manifestation.value if self.resolved_manifestation else None
            ),
            "requested_as_of_date": (
                self.requested_as_of_date.isoformat() if self.requested_as_of_date else None
            ),
            "resolved_as_of_date": (
                self.resolved_as_of_date.isoformat() if self.resolved_as_of_date else None
            ),
            "source_revision_date": (
                self.source_revision_date.isoformat() if self.source_revision_date else None
            ),
            "requested_url": self.requested_url,
            "resolved_url": self.resolved_url,
            "winning_evidence_basis": self.manifestation_basis.value,
            "conflicts": list(self.conflicts),
            "evidence": list(self.evidence),
            "parser_version": "legislation_manifestation_v1",
        }
        facts = [classify]
        # Explicit conservative boundary: non-PIT (or unresolved) as-of stays null.
        if self.manifestation_type != SourceManifestationType.POINT_IN_TIME or (
            self.resolved_as_of_date is None and self.requested_as_of_date is None
        ):
            if self.resolved_as_of_date is None:
                facts.append(
                    {
                        "fact_kind": "preserve_as_of_unknown",
                        "source_snapshot_id": source_snapshot_id or None,
                        "outcome": "legal_as_of_not_established",
                        "manifestation_type": self.manifestation_type.value,
                        "requested_as_of_date": None,
                        "resolved_as_of_date": None,
                        "source_revision_date": (
                            self.source_revision_date.isoformat()
                            if self.source_revision_date
                            else None
                        ),
                        "requested_url": self.requested_url,
                        "resolved_url": self.resolved_url,
                        "note": (
                            "Retrieval and source revision dates are not treated "
                            "as the legal as-of date for this run."
                        ),
                    }
                )
        return facts


def _strip_data_tail(path: str) -> str:
    cleaned = _DATA_TAIL_RE.sub("", path)
    return cleaned.rstrip("/") or "/"


def _instrument_and_version_segments(path: str) -> tuple[list[str], str | None]:
    """Return (instrument_segments, version_segment_or_none)."""
    parts = [part for part in path.strip("/").split("/") if part]
    if not parts:
        return [], None

    # Drop trailing representation tokens already stripped; keep provision paths out.
    version: str | None = None
    instrument: list[str] = []

    # Typical: /eur/2009/1224[/version]
    # or /ukpga/1981/54[/version]
    if parts[0].lower() in _INSTRUMENT_TYPES and len(parts) >= 3:
        instrument = parts[:3]
        remainder = parts[3:]
    else:
        # Fallback: treat last date/keyword as version when present.
        instrument = parts
        remainder = []

    for segment in remainder:
        lower = segment.lower()
        if lower in _PROVISION_PATH_HINTS:
            break
        if _parse_iso_date(segment) is not None:
            version = segment
            break
        if lower in _ORIGINAL_SEGMENTS | _PROSPECTIVE_SEGMENTS | _REVISED_SEGMENTS:
            version = lower
            break
        # Unknown non-provision segment — stop rather than guess.
        break

    return instrument, version


def parse_legislation_request_url(url: str | None) -> RequestManifestationHints:
    """Derive requested manifestation hints from a legislation.gov.uk URL."""
    raw = (url or "").strip()
    if not raw:
        return RequestManifestationHints(
            requested_url=None,
            requested_manifestation=None,
            requested_as_of_date=None,
            evidence=[],
        )

    try:
        parsed = urlparse(raw)
    except ValueError:
        return RequestManifestationHints(
            requested_url=raw,
            requested_manifestation=None,
            requested_as_of_date=None,
            evidence=[],
        )

    host = (parsed.hostname or "").lower()
    if host and "legislation.gov.uk" not in host:
        return RequestManifestationHints(
            requested_url=raw,
            requested_manifestation=None,
            requested_as_of_date=None,
            evidence=[],
        )

    path = _strip_data_tail(parsed.path or "")
    _instrument, version = _instrument_and_version_segments(path)
    evidence: list[dict[str, str]] = []
    requested: SourceManifestationType | None = None
    as_of: date | None = None

    if version:
        as_of = _parse_iso_date(version)
        if as_of is not None:
            requested = SourceManifestationType.POINT_IN_TIME
            evidence.append(
                _evidence(
                    kind="request_url",
                    field_name="path_version_date",
                    value=version,
                    source_location="request_url",
                )
            )
        elif version in _ORIGINAL_SEGMENTS:
            requested = SourceManifestationType.ORIGINAL
            evidence.append(
                _evidence(
                    kind="request_url",
                    field_name="path_version_keyword",
                    value=version,
                    source_location="request_url",
                )
            )
        elif version in _PROSPECTIVE_SEGMENTS:
            requested = SourceManifestationType.PROSPECTIVE
            evidence.append(
                _evidence(
                    kind="request_url",
                    field_name="path_version_keyword",
                    value=version,
                    source_location="request_url",
                )
            )
        elif version in _REVISED_SEGMENTS:
            requested = SourceManifestationType.REVISED
            evidence.append(
                _evidence(
                    kind="request_url",
                    field_name="path_version_keyword",
                    value=version,
                    source_location="request_url",
                )
            )

    # Unqualified /type/year/number/data.xml does not imply original or revised.
    return RequestManifestationHints(
        requested_url=raw,
        requested_manifestation=requested,
        requested_as_of_date=as_of,
        evidence=evidence,
    )


def _find_ukm_metadata(root: ElementTree.Element) -> ElementTree.Element | None:
    for child in list(root):
        if _local_name(child.tag) == "Metadata":
            return child
    return None


def _document_status_from_metadata(meta: ElementTree.Element) -> tuple[str | None, str | None]:
    """Return (status_value, source_path) from ukm:DocumentStatus only."""
    for node in meta.iter():
        if _local_name(node.tag) != "DocumentStatus":
            continue
        value = (node.attrib.get("Value") or "").strip()
        if value:
            return value, "ukm:DocumentStatus/@Value"
        text = "".join(node.itertext()).strip()
        if text:
            return text, "ukm:DocumentStatus"
    return None, None


def _first_metadata_text(meta: ElementTree.Element, local_names: set[str]) -> tuple[str | None, str | None]:
    for node in meta:
        name = _local_name(node.tag)
        if name in local_names:
            text = "".join(node.itertext()).strip()
            if text:
                return text, f"CLML Metadata/{name}"
    # Also allow direct children deeper one level (DocumentClassification wrappers).
    for node in meta.iter():
        if node is meta:
            continue
        name = _local_name(node.tag)
        if name in local_names and node is not None:
            # Skip if this is nested under Body-equivalent — we only walk Metadata.
            text = "".join(node.itertext()).strip()
            if text and name in {"valid", "identifier", "modified"}:
                # Only accept dct:valid / dc:identifier / dc:modified under Metadata tree.
                return text, f"CLML Metadata/{name}"
    return None, None


def _version_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    try:
        path = _strip_data_tail(urlparse(uri).path or "")
    except ValueError:
        return None
    _instrument, version = _instrument_and_version_segments(path)
    return version


def parse_legislation_manifestation_metadata(
    root: ElementTree.Element,
) -> SourceManifestationHints:
    """Parse whole-instrument manifestation signals from legislation.gov.uk CLML."""
    evidence: list[dict[str, str]] = []
    conflicts: list[str] = []

    document_uri = (root.attrib.get("DocumentURI") or "").strip() or None
    root_restrict = _parse_iso_date(root.attrib.get("RestrictStartDate"))
    if root.attrib.get("RestrictStartDate"):
        # Record presence but do not auto-classify from RestrictStartDate alone.
        evidence.append(
            _evidence(
                kind="source_metadata",
                field_name="Legislation/@RestrictStartDate",
                value=str(root.attrib.get("RestrictStartDate")),
                source_location="CLML root attribute",
            )
        )

    meta = _find_ukm_metadata(root)
    document_status: str | None = None
    dct_valid: date | None = None
    dc_modified: date | None = None
    identifier: str | None = None

    if meta is not None:
        document_status, status_loc = _document_status_from_metadata(meta)
        if document_status and status_loc:
            evidence.append(
                _evidence(
                    kind="source_metadata",
                    field_name="DocumentStatus",
                    value=document_status,
                    source_location=status_loc,
                )
            )

        valid_text, valid_loc = _first_metadata_text(meta, {"valid"})
        dct_valid = _parse_iso_date(valid_text)
        if valid_text and valid_loc:
            evidence.append(
                _evidence(
                    kind="source_metadata",
                    field_name="dct:valid",
                    value=valid_text,
                    source_location=valid_loc,
                )
            )

        modified_text, modified_loc = _first_metadata_text(meta, {"modified"})
        dc_modified = _parse_iso_date(modified_text)
        if modified_text and modified_loc:
            evidence.append(
                _evidence(
                    kind="source_metadata",
                    field_name="dc:modified",
                    value=modified_text,
                    source_location=modified_loc,
                )
            )

        identifier_text, ident_loc = _first_metadata_text(meta, {"identifier"})
        identifier = identifier_text
        if identifier_text and ident_loc:
            evidence.append(
                _evidence(
                    kind="source_metadata",
                    field_name="dc:identifier",
                    value=identifier_text,
                    source_location=ident_loc,
                )
            )

    if document_uri:
        evidence.append(
            _evidence(
                kind="source_metadata",
                field_name="DocumentURI",
                value=document_uri,
                source_location="Legislation/@DocumentURI",
            )
        )

    uri_for_version = document_uri or identifier
    version_segment = _version_from_uri(uri_for_version)

    resolved: SourceManifestationType | None = None
    resolved_as_of: date | None = None
    revision_date: date | None = None

    status_lower = (document_status or "").strip().lower()
    version_date = _parse_iso_date(version_segment) if version_segment else None

    if version_segment and version_segment in _ORIGINAL_SEGMENTS:
        resolved = SourceManifestationType.ORIGINAL
    elif version_segment and version_segment in _PROSPECTIVE_SEGMENTS:
        resolved = SourceManifestationType.PROSPECTIVE
    elif version_date is not None:
        resolved = SourceManifestationType.POINT_IN_TIME
        resolved_as_of = version_date
        if dct_valid and dct_valid != version_date:
            conflicts.append(
                f"DocumentURI date {version_date.isoformat()} differs from dct:valid {dct_valid.isoformat()}"
            )
        elif dct_valid:
            resolved_as_of = dct_valid
    elif status_lower == "revised":
        resolved = SourceManifestationType.REVISED
        # dct:valid / root RestrictStartDate on current revised = revision stamp, not legal as-of.
        revision_date = dct_valid or root_restrict
    elif status_lower == "final" and version_segment in _ORIGINAL_SEGMENTS:
        resolved = SourceManifestationType.ORIGINAL
    elif status_lower == "final":
        # "final" without enacted/adopted/made URI is weak — do not guess original.
        if version_segment is None:
            pass
        else:
            conflicts.append(f"DocumentStatus=final with unrecognised version segment {version_segment!r}")

    # DocumentStatus=final with enacted/adopted already handled via version_segment.
    if status_lower == "final" and resolved is None and version_segment in _ORIGINAL_SEGMENTS:
        resolved = SourceManifestationType.ORIGINAL

    # Strong conflict: status revised but URI says original.
    if status_lower == "revised" and version_segment in _ORIGINAL_SEGMENTS:
        conflicts.append("DocumentStatus=revised conflicts with original version URI segment")
        resolved = None
        resolved_as_of = None

    if status_lower in {"revised", "final"} and version_segment in _PROSPECTIVE_SEGMENTS:
        # Prefer explicit prospective URI.
        resolved = SourceManifestationType.PROSPECTIVE

    return SourceManifestationHints(
        document_uri=document_uri,
        document_status=document_status,
        dct_valid=dct_valid,
        root_restrict_start_date=root_restrict,
        dc_modified=dc_modified,
        resolved_manifestation=resolved,
        resolved_as_of_date=resolved_as_of,
        source_revision_date=revision_date,
        evidence=evidence,
        conflicts=conflicts,
    )


def _compatible_request_and_source(
    requested: SourceManifestationType,
    source: SourceManifestationType,
) -> bool:
    if requested == source:
        return True
    # Point-in-time URLs return revised historical text; that is consistent.
    if (
        requested == SourceManifestationType.POINT_IN_TIME
        and source == SourceManifestationType.POINT_IN_TIME
    ):
        return True
    return False


def resolve_manifestation_provenance(
    *,
    requested_url: str | None,
    resolved_url: str | None = None,
    xml_root: ElementTree.Element | None = None,
) -> ManifestationProvenance:
    """Combine request URL and CLML metadata into snapshot manifestation provenance."""
    request_hints = parse_legislation_request_url(requested_url)
    resolved_url_hints = (
        parse_legislation_request_url(resolved_url)
        if resolved_url and resolved_url != requested_url
        else None
    )
    source_hints = (
        parse_legislation_manifestation_metadata(xml_root)
        if xml_root is not None
        else SourceManifestationHints(
            document_uri=None,
            document_status=None,
            dct_valid=None,
            root_restrict_start_date=None,
            dc_modified=None,
            resolved_manifestation=None,
            resolved_as_of_date=None,
            source_revision_date=None,
        )
    )

    evidence: list[dict[str, str]] = []
    evidence.extend(request_hints.evidence)
    if resolved_url_hints is not None:
        for item in resolved_url_hints.evidence:
            evidence.append({**item, "source_location": "resolved_url"})
    evidence.extend(source_hints.evidence)

    conflicts = list(source_hints.conflicts)
    requested = request_hints.requested_manifestation
    if (
        resolved_url_hints is not None
        and resolved_url_hints.requested_manifestation is not None
        and requested is not None
        and resolved_url_hints.requested_manifestation != requested
    ):
        conflicts.append(
            "requested URL manifestation differs from resolved URL manifestation"
        )

    # Prefer explicit source metadata; fall back to resolved URL only when source is absent.
    source_resolved = source_hints.resolved_manifestation
    resolved = source_resolved
    resolved_as_of = source_hints.resolved_as_of_date
    revision_date = source_hints.source_revision_date
    basis = SourceManifestationBasis.UNAVAILABLE

    if source_resolved is not None:
        basis = (
            SourceManifestationBasis.REQUEST_AND_SOURCE_METADATA
            if requested is not None
            else SourceManifestationBasis.SOURCE_METADATA
        )
    elif resolved_url_hints is not None and resolved_url_hints.requested_manifestation is not None:
        resolved = resolved_url_hints.requested_manifestation
        if resolved == SourceManifestationType.POINT_IN_TIME:
            resolved_as_of = resolved_url_hints.requested_as_of_date
        basis = SourceManifestationBasis.RESOLVED_URL
    elif requested is not None:
        # Request-only: retain requested_* for audit; do not claim resolved classification.
        resolved = None
        basis = SourceManifestationBasis.REQUEST_URL

    if (
        requested is not None
        and source_resolved is not None
        and not _compatible_request_and_source(requested, source_resolved)
    ):
        conflicts.append(
            f"requested manifestation {requested.value} conflicts with "
            f"source manifestation {source_resolved.value}"
        )
        resolved = None
        resolved_as_of = None
        basis = SourceManifestationBasis.REQUEST_AND_SOURCE_METADATA

    if conflicts and resolved is None:
        evidence.append(
            _evidence(
                kind="conflict",
                field_name="manifestation",
                value="; ".join(conflicts),
                source_location="manifestation_resolution",
            )
        )

    if resolved is not None:
        manifestation_type = resolved
    else:
        manifestation_type = SourceManifestationType.UNKNOWN

    requested_as_of = request_hints.requested_as_of_date
    if (
        requested_as_of is None
        and resolved_url_hints is not None
        and resolved_url_hints.requested_as_of_date is not None
    ):
        requested_as_of = resolved_url_hints.requested_as_of_date

    # Legal as-of only for point-in-time manifestations.
    if manifestation_type == SourceManifestationType.POINT_IN_TIME:
        if resolved_as_of is None:
            resolved_as_of = requested_as_of
    else:
        resolved_as_of = None

    return ManifestationProvenance(
        manifestation_type=manifestation_type,
        manifestation_basis=basis,
        requested_manifestation=requested,
        resolved_manifestation=resolved,
        requested_as_of_date=requested_as_of,
        resolved_as_of_date=resolved_as_of,
        source_revision_date=revision_date,
        requested_url=request_hints.requested_url,
        resolved_url=resolved_url or request_hints.requested_url,
        evidence=evidence,
        conflicts=conflicts,
    )
