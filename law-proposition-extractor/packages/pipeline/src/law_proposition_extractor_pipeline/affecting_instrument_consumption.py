"""Run-scoped matching of affecting instruments to independently consumed sources.

Reconciles ``SourceLegalEffect.independent_consumption_status`` against the current
run's SourceRecord / SourceSnapshot inventory (and optional source-register entries).

Does not fetch instruments, expand the source family, apply amendments, or match on
title similarity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from law_proposition_extractor_domain import (
    AffectingInstrumentConsumptionStatus,
    ConsumptionMatchBasis,
)

from law_proposition_extractor_pipeline.sources.search_aliases import (
    eu_celex_to_legislation_authority_source_id,
    squash_ws,
)

# Representation / packaging suffixes (not part of instrument identity).
_REPRESENTATION_SUFFIXES = frozenset(
    {
        "data.xml",
        "data.htm",
        "data.html",
        "contents",
        "introduction",
        "pdfs",
        "pdf",
    }
)

# Manifestation / lifecycle suffixes (stripped for instrument-level identity only).
_MANIFESTATION_SUFFIXES = frozenset(
    {
        "made",
        "revised",
        "enacted",
        "prospective",
        "adopted",
        "current",
    }
)

_DATE_SEGMENT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CELEX_BODY_RE = re.compile(
    r"^(?P<body>[123]\d{4}[RLDMCA]\d{2,}(?:[A-Z]\(\d+\))?)$",
    re.IGNORECASE,
)
_SI_CITATION_RE = re.compile(
    r"(?i)\b(?P<series>S\.?\s*I\.?|UKSI|SSI|WSI|NISR|S\.?\s*R\.?)\s*"
    r"(?P<year>19\d{2}|20\d{2})\s*/\s*(?P<number>\d+)\b"
)
_EUR_CITATION_RE = re.compile(
    r"(?i)\b(?:Commission\s+)?Regulation\s*\((?:EU|EC|EEC)\)\s*(?:No\.?\s*)?"
    r"(?P<year>19\d{2}|20\d{2})\s*/\s*(?P<number>\d+)\b"
)
_EUR_SHORT_CITATION_RE = re.compile(
    r"(?i)\b(?P<series>EUR|EU)\s+(?P<year>19\d{2}|20\d{2})\s*/\s*(?P<number>\d+)\b"
)
_AUTHORITY_ID_RE = re.compile(
    r"^(?P<series>[a-z0-9]+)/(?P<year>\d{4})/(?P<number>\d+)$",
    re.IGNORECASE,
)
_SERIES_FROM_CITATION = {
    "s.i.": "uksi",
    "s.i": "uksi",
    "si": "uksi",
    "uksi": "uksi",
    "ssi": "ssi",
    "wsi": "wsi",
    "nisr": "nisr",
    "s.r.": "nisr",
    "s.r": "nisr",
    "sr": "nisr",
}


def normalize_authority_source_id(value: str) -> str | None:
    """Normalize ``series/year/number`` (zero-padded numbers collapsed)."""

    trimmed = value.strip().strip("/")
    match = _AUTHORITY_ID_RE.fullmatch(trimmed)
    if not match:
        return None
    series = match.group("series").lower()
    year = match.group("year")
    number = str(int(match.group("number")))
    return f"{series}/{year}/{number}"


def normalize_celex_identifier(value: str) -> str | None:
    """Normalize an explicit CELEX identifier (case/whitespace/URI wrappers)."""

    raw = squash_ws(value or "")
    if not raw:
        return None

    lowered = raw.lower()
    if "celex" in lowered or "eur-lex.europa.eu" in lowered or "eurlex" in lowered:
        try:
            parsed = urlparse(raw.strip())
        except ValueError:
            parsed = None
        if parsed and (parsed.scheme in {"http", "https"} or parsed.query):
            query = parse_qs(parsed.query)
            for key in ("uri", "CELEX", "celex"):
                for item in query.get(key, []):
                    candidate = _celex_token_from_text(unquote(item))
                    if candidate:
                        return candidate
            path_token = _celex_token_from_text(unquote(parsed.path.rsplit("/", 1)[-1]))
            if path_token:
                return path_token
        wrapped = _celex_token_from_text(raw)
        if wrapped:
            return wrapped
        return None

    return _celex_token_from_text(raw)


def _celex_token_from_text(value: str) -> str | None:
    text = squash_ws(value)
    text = re.sub(r"(?i)^celex\s*[:=]?\s*", "", text).strip()
    text = re.sub(r"\s+", "", text)
    match = _CELEX_BODY_RE.fullmatch(text)
    if not match:
        return None
    return match.group("body").upper()


def normalize_legislation_gov_uk_instrument_identity(value: str) -> str | None:
    """Normalize legislation.gov.uk URLs / paths to ``series/year/number``.

    Strips ``id/``, representation suffixes (``data.xml``, ``contents``), manifestation
    suffixes (``made``, ``revised``, point-in-time dates), and provision path segments.
    Query parameters are ignored. Deterministic.
    """

    raw = (value or "").strip()
    if not raw:
        return None

    path = raw
    if "://" in raw or raw.lower().startswith("www."):
        try:
            parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        except ValueError:
            return None
        host = (parsed.netloc or "").lower()
        if host and "legislation.gov.uk" not in host:
            return None
        path = parsed.path or ""
    elif "legislation.gov.uk" in raw.lower():
        # Bare host/path without scheme.
        try:
            parsed = urlparse(f"https://{raw.lstrip('/')}")
            path = parsed.path or ""
        except ValueError:
            return None

    segments = [seg for seg in path.strip("/").split("/") if seg]
    if segments and segments[0].lower() == "id":
        segments = segments[1:]

    while segments and segments[-1].lower() in _REPRESENTATION_SUFFIXES:
        segments.pop()
    while segments and (
        segments[-1].lower() in _MANIFESTATION_SUFFIXES or _DATE_SEGMENT_RE.fullmatch(segments[-1])
    ):
        segments.pop()

    if len(segments) < 3:
        return None
    return normalize_authority_source_id(f"{segments[0]}/{segments[1]}/{segments[2]}")


def parse_structured_citation_identity(citation: str) -> str | None:
    """Parse a citation into ``series/year/number`` when uniquely precise.

    Accepts forms such as ``S.I. 2019/739``, ``UKSI 2019/739``,
    ``Regulation (EU) 2015/812``. Does not match year/number alone or titles.
    """

    text = squash_ws(citation or "")
    if not text:
        return None

    si = _SI_CITATION_RE.search(text)
    if si:
        series_key = re.sub(r"\s+", "", si.group("series")).lower().rstrip(".")
        series = _SERIES_FROM_CITATION.get(series_key)
        if series is None and series_key.startswith("s.i"):
            series = "uksi"
        if series:
            return normalize_authority_source_id(
                f"{series}/{si.group('year')}/{si.group('number')}"
            )

    eur = _EUR_CITATION_RE.search(text)
    if eur:
        return normalize_authority_source_id(f"eur/{eur.group('year')}/{eur.group('number')}")

    eur_short = _EUR_SHORT_CITATION_RE.search(text)
    if eur_short:
        return normalize_authority_source_id(
            f"eur/{eur_short.group('year')}/{eur_short.group('number')}"
        )

    # Already-normalized authority id used as citation.
    return normalize_authority_source_id(text)


def instrument_identity_from_value(value: str) -> str | None:
    """Best-effort instrument identity from a URI, authority id, or CELEX token."""

    raw = (value or "").strip()
    if not raw:
        return None
    asid = normalize_legislation_gov_uk_instrument_identity(raw)
    if asid:
        return asid
    asid = normalize_authority_source_id(raw)
    if asid:
        return asid
    celex = normalize_celex_identifier(raw)
    if celex:
        mapped = eu_celex_to_legislation_authority_source_id(celex)
        if mapped:
            return mapped
        return f"celex:{celex}"
    return parse_structured_citation_identity(raw)


@dataclass(frozen=True)
class AffectingInstrumentSignals:
    """Normalized identity signals extracted from one effect (strongest first)."""

    authority_uri_identity: str | None = None
    authority_uri_raw: str | None = None
    authority_identifier: str | None = None
    celex_identifier: str | None = None
    citation_identity: str | None = None
    citation_raw: str | None = None

    def has_sufficient_identity(self) -> bool:
        return bool(
            self.authority_uri_identity
            or self.authority_identifier
            or self.celex_identifier
            or self.citation_identity
        )

    def ordered_identities(self) -> list[tuple[ConsumptionMatchBasis, str, str]]:
        """Return ``(basis, identity, effect_value)`` in match-precedence order."""

        rows: list[tuple[ConsumptionMatchBasis, str, str]] = []
        if self.authority_uri_identity and self.authority_uri_raw:
            rows.append(
                (
                    ConsumptionMatchBasis.CANONICAL_AUTHORITY_URI,
                    self.authority_uri_identity,
                    self.authority_uri_raw,
                )
            )
        if self.authority_identifier:
            rows.append(
                (
                    ConsumptionMatchBasis.AUTHORITY_IDENTIFIER,
                    self.authority_identifier,
                    self.authority_identifier,
                )
            )
        if self.celex_identifier:
            rows.append(
                (
                    ConsumptionMatchBasis.CELEX_IDENTIFIER,
                    self.celex_identifier
                    if self.celex_identifier.startswith("celex:")
                    else f"celex:{self.celex_identifier}",
                    self.celex_identifier,
                )
            )
            mapped = eu_celex_to_legislation_authority_source_id(
                self.celex_identifier.removeprefix("celex:")
            )
            if mapped:
                rows.append(
                    (
                        ConsumptionMatchBasis.CELEX_IDENTIFIER,
                        mapped,
                        self.celex_identifier,
                    )
                )
        if self.citation_identity and self.citation_raw:
            rows.append(
                (
                    ConsumptionMatchBasis.NORMALIZED_CITATION,
                    self.citation_identity,
                    self.citation_raw,
                )
            )
        return rows


def extract_affecting_instrument_signals(effect: dict[str, Any]) -> AffectingInstrumentSignals:
    """Extract identity signals from effect fields without mutating originals."""

    uri = _trim(effect.get("affecting_instrument_uri"))
    citation = _trim(effect.get("affecting_instrument_citation"))
    raw_meta = effect.get("metadata")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    raw_evidence = effect.get("source_evidence")
    evidence: dict[str, Any] = raw_evidence if isinstance(raw_evidence, dict) else {}

    uri_identity = normalize_legislation_gov_uk_instrument_identity(uri) if uri else None
    if uri and not uri_identity:
        # CELEX / EUR-Lex URI wrappers.
        celex_from_uri = normalize_celex_identifier(uri)
        if celex_from_uri:
            mapped = eu_celex_to_legislation_authority_source_id(celex_from_uri)
            uri_identity = mapped

    authority_identifier = None
    for key in ("affecting_instrument_authority_source_id", "authority_source_id"):
        candidate = _trim(meta.get(key)) or _trim(evidence.get(key)) or _trim(effect.get(key))
        if candidate:
            authority_identifier = normalize_authority_source_id(
                candidate
            ) or instrument_identity_from_value(candidate)
            if authority_identifier:
                break

    celex_raw = (
        _trim(effect.get("affecting_instrument_celex"))
        or _trim(meta.get("celex"))
        or _trim(meta.get("affecting_instrument_celex"))
        or _trim(evidence.get("celex"))
    )
    if not celex_raw and uri:
        celex_raw = normalize_celex_identifier(uri)
    celex_identifier = normalize_celex_identifier(celex_raw) if celex_raw else None

    citation_identity = parse_structured_citation_identity(citation) if citation else None

    return AffectingInstrumentSignals(
        authority_uri_identity=uri_identity,
        authority_uri_raw=uri,
        authority_identifier=authority_identifier,
        celex_identifier=celex_identifier,
        citation_identity=citation_identity,
        citation_raw=citation,
    )


@dataclass
class IndexedSource:
    source_record_id: str
    identities: set[str] = field(default_factory=set)
    title: str = ""
    citation: str = ""
    snapshot_ids: list[str] = field(default_factory=list)
    from_register: bool = False
    register_uri: str | None = None


@dataclass
class RunSourceInventory:
    """Run-scoped identity index for consumed sources and register entries."""

    by_record_id: dict[str, IndexedSource] = field(default_factory=dict)
    identity_to_record_ids: dict[str, list[str]] = field(default_factory=dict)
    usable: bool = False

    def record_ids_for_identity(self, identity: str) -> list[str]:
        return list(self.identity_to_record_ids.get(identity, []))


def build_run_source_inventory(
    *,
    source_records: list[dict[str, Any]] | None = None,
    source_snapshots: list[dict[str, Any]] | None = None,
    source_register_entries: list[dict[str, Any]] | None = None,
) -> RunSourceInventory:
    """Index SourceRecord / SourceSnapshot / optional register entries for matching."""

    inventory = RunSourceInventory()
    snapshots_by_record: dict[str, list[str]] = {}
    for snap in source_snapshots or []:
        if not isinstance(snap, dict):
            continue
        snap_id = _trim(snap.get("id"))
        record_id = _trim(snap.get("source_record_id"))
        if not snap_id or not record_id:
            continue
        snapshots_by_record.setdefault(record_id, []).append(snap_id)

    for record_id, snap_ids in snapshots_by_record.items():
        snapshots_by_record[record_id] = sorted(set(snap_ids))

    for row in source_records or []:
        if not isinstance(row, dict):
            continue
        record_id = _trim(row.get("id"))
        if not record_id:
            continue
        identities = _identities_from_source_row(row)
        indexed = IndexedSource(
            source_record_id=record_id,
            identities=identities,
            title=_trim(row.get("title")) or "",
            citation=_trim(row.get("citation")) or "",
            snapshot_ids=list(snapshots_by_record.get(record_id, [])),
            from_register=False,
        )
        inventory.by_record_id[record_id] = indexed
        inventory.usable = True

    # Snapshots whose parent record was not listed still contribute identities.
    for snap in source_snapshots or []:
        if not isinstance(snap, dict):
            continue
        record_id = _trim(snap.get("source_record_id"))
        snap_id = _trim(snap.get("id"))
        if not record_id or not snap_id:
            continue
        inventory.usable = True
        indexed = inventory.by_record_id.get(record_id)
        if indexed is None:
            identities = _identities_from_source_row(snap)
            # Also pull nested metadata identities.
            raw_meta = snap.get("metadata")
            meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
            identities |= _identities_from_mapping(meta)
            indexed = IndexedSource(
                source_record_id=record_id,
                identities=identities,
                title=_trim(snap.get("title")) or _trim(meta.get("title")) or "",
                citation=_trim(snap.get("citation")) or _trim(meta.get("citation")) or "",
                snapshot_ids=list(snapshots_by_record.get(record_id, [])),
            )
            inventory.by_record_id[record_id] = indexed
        else:
            indexed.identities |= _identities_from_source_row(snap)
            raw_meta = snap.get("metadata")
            meta = raw_meta if isinstance(raw_meta, dict) else {}
            indexed.identities |= _identities_from_mapping(meta)
            if snap_id not in indexed.snapshot_ids:
                indexed.snapshot_ids = sorted({*indexed.snapshot_ids, snap_id})

    for entry in source_register_entries or []:
        if not isinstance(entry, dict):
            continue
        uri = (
            _trim(entry.get("canonical_uri"))
            or _trim(entry.get("source_url"))
            or _trim(entry.get("uri"))
        )
        asid = normalize_legislation_gov_uk_instrument_identity(uri) if uri else None
        if not asid:
            asid = normalize_authority_source_id(_trim(entry.get("authority_source_id")) or "")
        if not asid:
            continue
        record_id = _trim(entry.get("source_id")) or _trim(entry.get("id")) or f"register:{asid}"
        inventory.usable = True
        existing = inventory.by_record_id.get(record_id)
        if existing is not None:
            existing.identities.add(asid)
            if uri:
                existing.register_uri = uri
            existing.from_register = existing.from_register or not existing.snapshot_ids
            continue
        inventory.by_record_id[record_id] = IndexedSource(
            source_record_id=record_id,
            identities={asid},
            title=_trim(entry.get("title")) or "",
            citation=_trim(entry.get("citation")) or "",
            snapshot_ids=[],
            from_register=True,
            register_uri=uri,
        )

    identity_map: dict[str, set[str]] = {}
    for record_id, indexed in inventory.by_record_id.items():
        for identity in indexed.identities:
            identity_map.setdefault(identity, set()).add(record_id)
    inventory.identity_to_record_ids = {
        identity: sorted(record_ids) for identity, record_ids in sorted(identity_map.items())
    }
    return inventory


def _identities_from_source_row(row: dict[str, Any]) -> set[str]:
    identities: set[str] = set()
    raw_meta = row.get("metadata")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    candidates = [
        row.get("authority_source_id"),
        meta.get("authority_source_id"),
        row.get("source_url"),
        meta.get("source_url"),
        meta.get("resolved_url"),
        meta.get("requested_url"),
        meta.get("canonical_uri"),
        row.get("citation"),
        meta.get("citation"),
        meta.get("celex"),
        row.get("celex"),
    ]
    law_discovery_meta = meta.get("ada_source_bundle")
    if isinstance(law_discovery_meta, dict):
        candidates.append(law_discovery_meta.get("canonical_uri"))
    for value in candidates:
        text = _trim(value)
        if not text:
            continue
        identity = instrument_identity_from_value(text)
        if identity:
            identities.add(identity)
        celex = normalize_celex_identifier(text)
        if celex:
            identities.add(f"celex:{celex}")
            mapped = eu_celex_to_legislation_authority_source_id(celex)
            if mapped:
                identities.add(mapped)
    return identities


def _identities_from_mapping(mapping: dict[str, Any]) -> set[str]:
    return _identities_from_source_row({"metadata": mapping, **mapping})


def reconcile_affecting_instrument_consumption(
    effects: list[dict[str, Any]],
    *,
    inventory: RunSourceInventory,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Enrich effects with run-scoped independent-consumption status (deterministic)."""

    diag_out = diagnostics if diagnostics is not None else []
    # Stable effect order for diagnostics; mutate copies in input order.
    enriched: list[dict[str, Any]] = []
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        enriched.append(
            _reconcile_one_effect(dict(effect), inventory=inventory, diagnostics=diag_out)
        )
    return enriched


def _reconcile_one_effect(
    effect: dict[str, Any],
    *,
    inventory: RunSourceInventory,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    effect_id = _trim(effect.get("id")) or ""
    owning_record_id = _trim(effect.get("source_record_id")) or ""
    signals = extract_affecting_instrument_signals(effect)

    if not inventory.usable:
        effect["independent_consumption_status"] = (
            AffectingInstrumentConsumptionStatus.NOT_ASSESSED.value
        )
        effect["consumption_match_basis"] = ConsumptionMatchBasis.INSUFFICIENT_IDENTITY.value
        effect["matched_source_record_id"] = None
        effect["matched_source_snapshot_ids"] = []
        effect["matched_instrument_identity"] = None
        effect["consumption_match_evidence"] = []
        return effect

    if not signals.has_sufficient_identity():
        effect["independent_consumption_status"] = (
            AffectingInstrumentConsumptionStatus.NOT_ASSESSED.value
        )
        effect["consumption_match_basis"] = ConsumptionMatchBasis.INSUFFICIENT_IDENTITY.value
        effect["matched_source_record_id"] = None
        effect["matched_source_snapshot_ids"] = []
        effect["matched_instrument_identity"] = None
        effect["consumption_match_evidence"] = []
        diagnostics.append(
            {
                "code": "affecting_instrument_identifier_insufficient",
                "effect_id": effect_id,
                "annotation_id": effect.get("annotation_id"),
                "message": (
                    "Affecting instrument lacks a precise URI, identifier, or "
                    "structured citation for independent-consumption matching."
                ),
            }
        )
        return effect

    ordered = signals.ordered_identities()
    evidence_rows: list[dict[str, Any]] = []
    seen_identity_keys: set[str] = set()
    unique_ordered: list[tuple[ConsumptionMatchBasis, str, str]] = []
    for basis, identity, effect_value in ordered:
        evidence_rows.append(
            {
                "basis": basis.value,
                "effect_value": effect_value,
                "normalized_identity": identity,
            }
        )
        key = f"{basis.value}|{identity}"
        if key in seen_identity_keys:
            continue
        seen_identity_keys.add(key)
        unique_ordered.append((basis, identity, effect_value))

    # Resolve each signal independently; detect ambiguity / strong-identity conflict.
    resolved: list[tuple[ConsumptionMatchBasis, str, str, str, IndexedSource]] = []
    for basis, identity, effect_value in unique_ordered:
        record_ids = [
            rid for rid in inventory.record_ids_for_identity(identity) if rid != owning_record_id
        ]
        if not record_ids:
            continue
        if len(record_ids) > 1:
            effect["independent_consumption_status"] = (
                AffectingInstrumentConsumptionStatus.NOT_MATCHED.value
            )
            effect["consumption_match_basis"] = ConsumptionMatchBasis.AMBIGUOUS_IDENTITY.value
            effect["matched_source_record_id"] = None
            effect["matched_source_snapshot_ids"] = []
            effect["matched_instrument_identity"] = identity
            effect["consumption_match_evidence"] = [
                {**row, "candidate_source_record_ids": record_ids}
                for row in evidence_rows
                if row["normalized_identity"] == identity
            ] or evidence_rows
            diag_code = (
                "affecting_instrument_register_match_ambiguous"
                if all(
                    inventory.by_record_id[rid].from_register
                    and not inventory.by_record_id[rid].snapshot_ids
                    for rid in record_ids
                )
                else "affecting_instrument_match_ambiguous"
            )
            diagnostics.append(
                {
                    "code": diag_code,
                    "effect_id": effect_id,
                    "annotation_id": effect.get("annotation_id"),
                    "normalized_identity": identity,
                    "candidate_source_record_ids": record_ids,
                    "message": (
                        "Multiple distinct source records claim the same normalized "
                        "instrument identity; no consumed match selected."
                    ),
                }
            )
            return effect
        resolved.append(
            (basis, identity, effect_value, record_ids[0], inventory.by_record_id[record_ids[0]])
        )

    # Strong-identifier conflict: distinct strong signals point at different records.
    strong_resolved = [row for row in resolved if _is_strong_basis(row[0])]
    strong_record_ids = {row[3] for row in strong_resolved}
    if len(strong_record_ids) > 1:
        effect["independent_consumption_status"] = (
            AffectingInstrumentConsumptionStatus.NOT_MATCHED.value
        )
        effect["consumption_match_basis"] = ConsumptionMatchBasis.AMBIGUOUS_IDENTITY.value
        effect["matched_source_record_id"] = None
        effect["matched_source_snapshot_ids"] = []
        effect["matched_instrument_identity"] = None
        effect["consumption_match_evidence"] = evidence_rows
        diagnostics.append(
            {
                "code": "affecting_instrument_identity_conflict",
                "effect_id": effect_id,
                "annotation_id": effect.get("annotation_id"),
                "candidate_source_record_ids": sorted(strong_record_ids),
                "message": (
                    "Conflicting strong affecting-instrument identifiers resolved to "
                    "different source records; no match selected."
                ),
            }
        )
        return effect

    if resolved:
        # Precedence: first resolved signal wins.
        basis, identity, effect_value, matched_id, indexed = resolved[0]
        snap_ids = list(indexed.snapshot_ids)
        evidence: dict[str, Any] = {
            "basis": basis.value,
            "effect_value": effect_value,
            "normalized_identity": identity,
            "matched_source_record_id": matched_id,
        }
        if indexed.title:
            evidence["matched_source_title"] = indexed.title
        if indexed.citation:
            evidence["matched_source_citation"] = indexed.citation
        if snap_ids:
            evidence["matched_source_snapshot_ids"] = snap_ids

        effective_basis = basis
        if not snap_ids and (indexed.from_register or indexed.register_uri):
            effective_basis = ConsumptionMatchBasis.SOURCE_REGISTER_URI
            evidence["basis"] = effective_basis.value
            if indexed.register_uri:
                evidence["register_uri"] = indexed.register_uri

        if snap_ids:
            effect["independent_consumption_status"] = (
                AffectingInstrumentConsumptionStatus.CONSUMED_IN_CURRENT_RUN.value
            )
            effect["consumption_match_basis"] = effective_basis.value
            effect["matched_source_record_id"] = matched_id
            effect["matched_source_snapshot_ids"] = snap_ids
            effect["matched_instrument_identity"] = identity
            effect["consumption_match_evidence"] = _dedupe_evidence([evidence, *evidence_rows])
            return effect

        effect["independent_consumption_status"] = (
            AffectingInstrumentConsumptionStatus.PRESENT_IN_SOURCE_REGISTER_BUT_NOT_CONSUMED.value
        )
        effect["consumption_match_basis"] = (
            ConsumptionMatchBasis.SOURCE_REGISTER_URI.value
            if (indexed.from_register or indexed.register_uri)
            else effective_basis.value
        )
        effect["matched_source_record_id"] = matched_id
        effect["matched_source_snapshot_ids"] = []
        effect["matched_instrument_identity"] = identity
        effect["consumption_match_evidence"] = _dedupe_evidence([evidence, *evidence_rows])
        if not indexed.from_register:
            diagnostics.append(
                {
                    "code": "affecting_instrument_source_record_missing_snapshot",
                    "effect_id": effect_id,
                    "annotation_id": effect.get("annotation_id"),
                    "matched_source_record_id": matched_id,
                    "normalized_identity": identity,
                    "message": (
                        "Matched a source record in the run, but no retained "
                        "SourceSnapshot was independently consumed for it."
                    ),
                }
            )
        return effect

    # Assessed no-match.
    primary_identity = unique_ordered[0][1] if unique_ordered else None
    effect["independent_consumption_status"] = (
        AffectingInstrumentConsumptionStatus.NOT_MATCHED.value
    )
    effect["consumption_match_basis"] = ConsumptionMatchBasis.NO_MATCH.value
    effect["matched_source_record_id"] = None
    effect["matched_source_snapshot_ids"] = []
    effect["matched_instrument_identity"] = primary_identity
    effect["consumption_match_evidence"] = evidence_rows
    return effect


def reconcile_source_legal_effects_artifact(
    artifact: dict[str, Any],
    *,
    source_records: list[dict[str, Any]] | None = None,
    source_snapshots: list[dict[str, Any]] | None = None,
    source_register_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reconcile consumption statuses onto a ``source_legal_effects`` artifact."""

    inventory = build_run_source_inventory(
        source_records=source_records,
        source_snapshots=source_snapshots,
        source_register_entries=source_register_entries,
    )
    effects_raw = artifact.get("effects")
    effects = (
        [row for row in effects_raw if isinstance(row, dict)]
        if isinstance(effects_raw, list)
        else []
    )
    diagnostics_raw = artifact.get("diagnostics")
    diagnostics: list[dict[str, Any]] = (
        [row for row in diagnostics_raw if isinstance(row, dict)]
        if isinstance(diagnostics_raw, list)
        else []
    )
    reconciled = reconcile_affecting_instrument_consumption(
        effects,
        inventory=inventory,
        diagnostics=diagnostics,
    )
    # Deterministic effect ordering preserved from builder; re-sort for safety.
    reconciled.sort(
        key=lambda row: (
            str(row.get("source_snapshot_id") or ""),
            str(row.get("annotation_label") or ""),
            str(row.get("annotation_id") or ""),
            str(row.get("id") or ""),
        )
    )
    diagnostics = _dedupe_diagnostics(diagnostics)
    diagnostics.sort(
        key=lambda row: (
            str(row.get("code") or ""),
            str(row.get("effect_id") or ""),
            str(row.get("annotation_id") or ""),
            str(row.get("message") or ""),
        )
    )
    artifact = dict(artifact)
    artifact["effects"] = reconciled
    artifact["diagnostics"] = diagnostics
    meta = (
        dict(artifact.get("metadata") or {}) if isinstance(artifact.get("metadata"), dict) else {}
    )
    meta["affecting_instrument_consumption_reconciled"] = True
    meta["consumption_inventory_source_record_count"] = len(inventory.by_record_id)
    meta["consumption_inventory_usable"] = inventory.usable
    artifact["metadata"] = meta
    return artifact


def _is_strong_basis(basis: ConsumptionMatchBasis) -> bool:
    return basis in {
        ConsumptionMatchBasis.CANONICAL_AUTHORITY_URI,
        ConsumptionMatchBasis.AUTHORITY_IDENTIFIER,
        ConsumptionMatchBasis.CELEX_IDENTIFIER,
    }


def _dedupe_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("basis") or ""),
            str(row.get("normalized_identity") or ""),
            str(row.get("effect_value") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _dedupe_diagnostics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = "|".join(
            [
                str(row.get("code") or ""),
                str(row.get("effect_id") or ""),
                str(row.get("annotation_id") or ""),
                str(row.get("normalized_identity") or ""),
                str(row.get("matched_source_record_id") or ""),
                str(row.get("message") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _trim(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def collect_source_register_entries_from_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect optional run-scoped Law Discovery / source-register entries when present."""

    entries: list[dict[str, Any]] = []
    for key in (
        "source_register_entries",
        "source_register",
        "ada_sources",
        "register_sources",
    ):
        raw = bundle.get(key)
        if isinstance(raw, list):
            entries.extend(row for row in raw if isinstance(row, dict))
        elif isinstance(raw, dict):
            for nested_key in ("entries", "sources", "items"):
                nested = raw.get(nested_key)
                if isinstance(nested, list):
                    entries.extend(row for row in nested if isinstance(row, dict))

    # Intake bundle sections that may be present on the case/export metadata.
    for section in (
        "principal_sources",
        "amending_sources",
        "revocation_sources",
        "contextual_sources",
        "rejected_sources",
    ):
        raw = bundle.get(section)
        if isinstance(raw, list):
            entries.extend(row for row in raw if isinstance(row, dict))

    meta = bundle.get("metadata")
    if isinstance(meta, dict):
        for key in ("source_register_entries", "ada_sources"):
            raw = meta.get(key)
            if isinstance(raw, list):
                entries.extend(row for row in raw if isinstance(row, dict))

    # Deterministic order for index construction.
    entries.sort(
        key=lambda row: (
            str(row.get("canonical_uri") or row.get("source_url") or row.get("uri") or ""),
            str(row.get("source_id") or row.get("id") or ""),
            str(row.get("authority_source_id") or ""),
        )
    )
    return entries
