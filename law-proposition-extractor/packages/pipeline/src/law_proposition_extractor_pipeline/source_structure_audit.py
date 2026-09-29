"""Typed structural-source audit (inspection/test object, not a run export)."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from law_proposition_extractor_domain import SourceFragment, StructuralHeading, StructuralHeadingKind

from .source_fragmentation import content_hash
from .structural_headings import (
    format_structural_heading_display,
    resolve_structural_heading_contexts,
)

_MULTI_PROVISION_DIAG = "multi_provision_group_title_unassigned"
_PROVISION_ROOT_RE = re.compile(
    r"^(article|regulation|rule|schedule|annex|section):[^:]+$",
    re.IGNORECASE,
)


def _as_mapping(fragment: SourceFragment | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(fragment, SourceFragment):
        return fragment.model_dump(mode="json")
    return dict(fragment)


def _fragment_id(row: Mapping[str, Any]) -> str:
    return str(row.get("id") or row.get("fragment_id") or "").strip()


def _locator(row: Mapping[str, Any]) -> str:
    return str(row.get("locator") or "").strip()


def _heading_dict(row: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = row.get("structural_heading")
    if isinstance(raw, StructuralHeading):
        return raw.model_dump(mode="json")
    if isinstance(raw, Mapping):
        return dict(raw)
    return None


def operative_text_digest(text: str, *, limit: int = 16) -> str:
    digest = hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()
    return digest[:limit]


def text_preview(text: str, *, limit: int = 100) -> str:
    compact = " ".join(str(text or "").replace("\xa0", " ").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"


_CONTAINER_LOCATOR_KINDS = frozenset({"part", "title", "chapter", "division"})


def heading_leaks_into_operative_text(
    *,
    fragment_text: str,
    heading_text: str | None,
    number_label: str | None = None,
    locator: str | None = None,
) -> bool:
    """True when a captured legislative heading is spliced into operative text.

    Containers intentionally store short number labels (or, when Number is absent,
    the Title itself) as ``fragment_text``. That container representation is not
    a leak. A leak is descriptive heading text appearing inside a headed
    provision's operative body.
    """
    body = " ".join(str(fragment_text or "").replace("\xa0", " ").split()).strip()
    heading = " ".join(str(heading_text or "").replace("\xa0", " ").split()).strip()
    if not body or not heading:
        return False
    kind = str(locator or "").split(":", maxsplit=1)[0].strip().lower()
    # Containers often equal their number_label, or equal Title when Number is absent.
    number = " ".join(str(number_label or "").replace("\xa0", " ").split()).strip()
    if kind in _CONTAINER_LOCATOR_KINDS:
        if number and body == number:
            return False
        if body == heading:
            return False
    if body == heading:
        return True
    # Require a substantial heading phrase (≥ 12 chars) to avoid number-only noise.
    if len(heading) < 12:
        return False
    return heading in body


@dataclass(frozen=True)
class StructuralDiagnostic:
    code: str
    message: str
    locator: str | None = None
    fragment_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.locator:
            row["locator"] = self.locator
        if self.fragment_id:
            row["fragment_id"] = self.fragment_id
        if self.details:
            row["details"] = dict(self.details)
        return row


@dataclass
class FragmentStructureRow:
    fragment_id: str
    locator: str
    structural_kind: str
    parent_fragment_id: str | None
    parent_locator: str | None
    number_label: str | None
    direct_heading_text: str | None
    direct_heading_kind: str | None
    inherited_heading_path: list[str]
    operative_text_preview: str
    operative_text_digest: str
    child_fragment_ids: list[str]
    child_locators: list[str]
    heading_diagnostic: str | None
    operative_text_heading_leak: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "fragment_id": self.fragment_id,
            "locator": self.locator,
            "structural_kind": self.structural_kind,
            "parent_fragment_id": self.parent_fragment_id,
            "parent_locator": self.parent_locator,
            "number_label": self.number_label,
            "direct_heading_text": self.direct_heading_text,
            "direct_heading_kind": self.direct_heading_kind,
            "inherited_heading_path": list(self.inherited_heading_path),
            "operative_text_preview": self.operative_text_preview,
            "operative_text_digest": self.operative_text_digest,
            "child_fragment_ids": list(self.child_fragment_ids),
            "child_locators": list(self.child_locators),
            "heading_diagnostic": self.heading_diagnostic,
            "operative_text_heading_leak": self.operative_text_heading_leak,
        }


@dataclass
class UnassignedHeading:
    diagnostic: str
    locator: str
    fragment_id: str
    title_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        row = {
            "diagnostic": self.diagnostic,
            "locator": self.locator,
            "fragment_id": self.fragment_id,
        }
        if self.title_preview:
            row["title_preview"] = self.title_preview
        return row


@dataclass
class StructuralSourceAudit:
    """Inspection/test audit for a parsed structural source tree."""

    source_record_id: str
    source_snapshot_id: str
    instrument_title: str | None
    manifestation: str | None
    fragment_count: int
    root_fragments: list[str]
    heading_count: int
    heading_counts_by_kind: dict[str, int]
    unassigned_headings: list[UnassignedHeading]
    parentage_issues: list[StructuralDiagnostic]
    duplicate_locator_issues: list[StructuralDiagnostic]
    operative_text_heading_leaks: list[StructuralDiagnostic]
    cross_source_parent_issues: list[StructuralDiagnostic]
    cycle_issues: list[StructuralDiagnostic]
    diagnostics: list[StructuralDiagnostic]
    fragment_rows: list[FragmentStructureRow] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_record_id": self.source_record_id,
            "source_snapshot_id": self.source_snapshot_id,
            "instrument_title": self.instrument_title,
            "manifestation": self.manifestation,
            "fragment_count": self.fragment_count,
            "root_fragments": list(self.root_fragments),
            "heading_count": self.heading_count,
            "heading_counts_by_kind": dict(self.heading_counts_by_kind),
            "unassigned_headings": [u.to_dict() for u in self.unassigned_headings],
            "parentage_issues": [d.to_dict() for d in self.parentage_issues],
            "duplicate_locator_issues": [d.to_dict() for d in self.duplicate_locator_issues],
            "operative_text_heading_leaks": [
                d.to_dict() for d in self.operative_text_heading_leaks
            ],
            "cross_source_parent_issues": [
                d.to_dict() for d in self.cross_source_parent_issues
            ],
            "cycle_issues": [d.to_dict() for d in self.cycle_issues],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "fragment_rows": [r.to_dict() for r in self.fragment_rows],
            "observations": dict(self.observations),
            "passed": self.passed,
        }


def structural_rows_to_fragments(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_record_id: str = "src-structural-audit",
    source_snapshot_id: str = "snap-structural-audit",
) -> list[SourceFragment]:
    """Convert adapter structural rows into SourceFragment domain objects."""
    id_by_locator: dict[str, str] = {}
    for index, row in enumerate(rows):
        locator = str(row.get("locator") or "").strip()
        if not locator:
            continue
        id_by_locator[locator] = f"frag-{source_record_id}-{index + 1:03d}"

    fragments: list[SourceFragment] = []
    for index, row in enumerate(rows):
        locator = str(row.get("locator") or "").strip()
        if not locator:
            continue
        fid = id_by_locator[locator]
        parent_locator = str(row.get("parent_locator") or "").strip() or None
        parent_id = id_by_locator.get(parent_locator) if parent_locator else None
        text = str(row.get("text") or "")
        number_label_raw = row.get("number_label")
        number_label = str(number_label_raw).strip() if number_label_raw else None
        heading = None
        if isinstance(row.get("structural_heading"), dict):
            payload = dict(row["structural_heading"])
            payload.setdefault("owner_locator", locator)
            payload["owner_fragment_id"] = fid
            if number_label and not payload.get("number_label"):
                payload["number_label"] = number_label
            try:
                heading = StructuralHeading.model_validate(payload)
            except Exception:
                heading = None
        meta = dict(row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {}
        fragments.append(
            SourceFragment(
                id=fid,
                fragment_id=fid,
                source_record_id=source_record_id,
                source_snapshot_id=source_snapshot_id,
                locator=locator,
                fragment_text=text,
                fragment_hash=content_hash(text),
                parent_fragment_id=parent_id,
                order_index=int(row.get("order_index") or index),
                number_label=number_label,
                structural_heading=heading,
                metadata=meta,
            )
        )
    return fragments


def _detect_cycles(
    fragments_by_id: Mapping[str, Mapping[str, Any]],
) -> list[StructuralDiagnostic]:
    issues: list[StructuralDiagnostic] = []
    for start_id, start in fragments_by_id.items():
        seen: set[str] = set()
        current_id: str | None = start_id
        while current_id:
            if current_id in seen:
                issues.append(
                    StructuralDiagnostic(
                        code="cyclic_parent_chain",
                        message=f"Cyclic parent chain involving {start_id}",
                        fragment_id=start_id,
                        locator=_locator(start),
                        details={"cycle_member": current_id},
                    )
                )
                break
            seen.add(current_id)
            parent_id = str(
                fragments_by_id[current_id].get("parent_fragment_id") or ""
            ).strip()
            if not parent_id:
                break
            if parent_id not in fragments_by_id:
                break
            current_id = parent_id
    return issues


def audit_structural_fragments(
    fragments: Sequence[SourceFragment | Mapping[str, Any]],
    *,
    source_record_id: str | None = None,
    source_snapshot_id: str | None = None,
    instrument_title: str | None = None,
    manifestation: str | None = None,
) -> StructuralSourceAudit:
    """Audit hierarchy, heading ownership, and operative-text boundaries."""
    rows = [_as_mapping(f) for f in fragments]
    by_id = {_fragment_id(r): r for r in rows if _fragment_id(r)}
    by_locator = {_locator(r): r for r in rows if _locator(r)}

    record_id = source_record_id or (
        str(rows[0].get("source_record_id") or "src-structural-audit") if rows else "src-unknown"
    )
    snapshot_id = source_snapshot_id or (
        str(rows[0].get("source_snapshot_id") or "snap-structural-audit")
        if rows
        else "snap-unknown"
    )

    parentage_issues: list[StructuralDiagnostic] = []
    cross_source: list[StructuralDiagnostic] = []
    duplicate_locator_issues: list[StructuralDiagnostic] = []
    leaks: list[StructuralDiagnostic] = []
    diagnostics: list[StructuralDiagnostic] = []
    unassigned: list[UnassignedHeading] = []

    locator_counts = Counter(_locator(r) for r in rows if _locator(r))
    for locator, count in sorted(locator_counts.items()):
        if count > 1:
            duplicate_locator_issues.append(
                StructuralDiagnostic(
                    code="duplicate_locator",
                    message=f"Locator {locator} appears {count} times",
                    locator=locator,
                    details={"count": count},
                )
            )

    children_by_parent: dict[str, list[str]] = {}
    for row in rows:
        fid = _fragment_id(row)
        parent_id = str(row.get("parent_fragment_id") or "").strip()
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(fid)

    for row in rows:
        fid = _fragment_id(row)
        locator = _locator(row)
        parent_id = str(row.get("parent_fragment_id") or "").strip() or None
        if parent_id and parent_id not in by_id:
            parentage_issues.append(
                StructuralDiagnostic(
                    code="missing_parent_fragment",
                    message=f"Parent fragment {parent_id} missing for {locator}",
                    locator=locator,
                    fragment_id=fid,
                    details={"parent_fragment_id": parent_id},
                )
            )
            continue
        if parent_id:
            parent = by_id[parent_id]
            if str(parent.get("source_record_id") or "") != str(
                row.get("source_record_id") or ""
            ) or str(parent.get("source_snapshot_id") or "") != str(
                row.get("source_snapshot_id") or ""
            ):
                cross_source.append(
                    StructuralDiagnostic(
                        code="cross_source_parent",
                        message=(
                            f"Parent {parent_id} crosses source/snapshot boundary "
                            f"for {locator}"
                        ),
                        locator=locator,
                        fragment_id=fid,
                        details={"parent_fragment_id": parent_id},
                    )
                )
            # Sibling root provisions must not parent each other.
            if _PROVISION_ROOT_RE.match(locator) and _PROVISION_ROOT_RE.match(
                _locator(parent)
            ):
                parentage_issues.append(
                    StructuralDiagnostic(
                        code="sibling_provision_parented",
                        message=(
                            f"Root provision {locator} is parented to sibling-like "
                            f"provision {_locator(parent)}"
                        ),
                        locator=locator,
                        fragment_id=fid,
                        details={"parent_locator": _locator(parent)},
                    )
                )

        diag = None
        meta = row.get("metadata")
        if isinstance(meta, dict):
            diag = meta.get("structural_heading_diagnostic")
        if diag and _MULTI_PROVISION_DIAG in str(diag):
            unassigned.append(
                UnassignedHeading(
                    diagnostic=str(diag),
                    locator=locator,
                    fragment_id=fid,
                )
            )

        heading = _heading_dict(row)
        heading_text = str(heading.get("text") or "").strip() if heading else None
        if heading_leaks_into_operative_text(
            fragment_text=str(row.get("fragment_text") or ""),
            heading_text=heading_text,
            number_label=str(row.get("number_label") or "").strip() or None,
            locator=locator,
        ):
            leaks.append(
                StructuralDiagnostic(
                    code="operative_text_heading_leak",
                    message=(
                        f"Legislative heading leaked into operative fragment_text "
                        f"for {locator}"
                    ),
                    locator=locator,
                    fragment_id=fid,
                    details={"heading_text": heading_text},
                )
            )

    cycle_issues = _detect_cycles(by_id)

    heading_kinds: Counter[str] = Counter()
    fragment_rows: list[FragmentStructureRow] = []
    for row in sorted(rows, key=lambda r: (int(r.get("order_index") or 0), _locator(r))):
        fid = _fragment_id(row)
        locator = _locator(row)
        heading = _heading_dict(row)
        if heading:
            kind = str(heading.get("kind") or StructuralHeadingKind.UNKNOWN.value)
            heading_kinds[kind] += 1
        contexts = resolve_structural_heading_contexts(row, by_id)
        path = [
            format_structural_heading_display(
                number_label=c.number_label, heading_text=c.heading_text
            )
            for c in contexts
        ]
        path = [p for p in path if p]
        parent_id = str(row.get("parent_fragment_id") or "").strip() or None
        parent_locator = _locator(by_id[parent_id]) if parent_id and parent_id in by_id else None
        child_ids = list(children_by_parent.get(fid) or [])
        child_locators = [
            _locator(by_id[cid]) for cid in child_ids if cid in by_id and _locator(by_id[cid])
        ]
        kind = locator.split(":", maxsplit=1)[0].lower() if locator else "unknown"
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        heading_diag = None
        if isinstance(meta, dict):
            raw_diag = meta.get("structural_heading_diagnostic")
            heading_diag = str(raw_diag) if raw_diag else None
        leak = heading_leaks_into_operative_text(
            fragment_text=str(row.get("fragment_text") or ""),
            heading_text=str(heading.get("text") or "").strip() if heading else None,
            number_label=str(row.get("number_label") or "").strip() or None,
            locator=locator,
        )
        # Inherited-heading depth / overlap observations (diagnostic only).
        body = str(row.get("fragment_text") or "")
        heading_text = str(heading.get("text") or "").strip() if heading else ""
        fragment_rows.append(
            FragmentStructureRow(
                fragment_id=fid,
                locator=locator,
                structural_kind=kind,
                parent_fragment_id=parent_id,
                parent_locator=parent_locator,
                number_label=str(row.get("number_label") or "").strip() or None,
                direct_heading_text=heading_text or None,
                direct_heading_kind=(
                    str(heading.get("kind") or "").strip() or None if heading else None
                ),
                inherited_heading_path=path,
                operative_text_preview=text_preview(body),
                operative_text_digest=operative_text_digest(body),
                child_fragment_ids=child_ids,
                child_locators=child_locators,
                heading_diagnostic=heading_diag,
                operative_text_heading_leak=leak,
            )
        )

    root_fragments = [
        r.locator for r in fragment_rows if not r.parent_fragment_id and r.locator
    ]

    diagnostics.extend(parentage_issues)
    diagnostics.extend(cross_source)
    diagnostics.extend(duplicate_locator_issues)
    diagnostics.extend(leaks)
    diagnostics.extend(cycle_issues)

    observations = {
        "heading_body_token_overlap_count": sum(
            1
            for r in fragment_rows
            if r.direct_heading_text
            and r.direct_heading_text.lower()[:20]
            in (r.operative_text_preview or "").lower()
        ),
        "headed_provisions": sum(1 for r in fragment_rows if r.direct_heading_text),
        "inherited_heading_depth_max": max(
            (len(r.inherited_heading_path) for r in fragment_rows), default=0
        ),
        "note": (
            "Observations are diagnostic only. No heading-materiality or "
            "completeness conclusion is implied."
        ),
    }

    passed = not any(
        (
            parentage_issues,
            cross_source,
            duplicate_locator_issues,
            leaks,
            cycle_issues,
        )
    )

    return StructuralSourceAudit(
        source_record_id=record_id,
        source_snapshot_id=snapshot_id,
        instrument_title=instrument_title,
        manifestation=manifestation,
        fragment_count=len(fragment_rows),
        root_fragments=root_fragments,
        heading_count=sum(heading_kinds.values()),
        heading_counts_by_kind=dict(sorted(heading_kinds.items())),
        unassigned_headings=unassigned,
        parentage_issues=parentage_issues,
        duplicate_locator_issues=duplicate_locator_issues,
        operative_text_heading_leaks=leaks,
        cross_source_parent_issues=cross_source,
        cycle_issues=cycle_issues,
        diagnostics=diagnostics,
        fragment_rows=fragment_rows,
        observations=observations,
        passed=passed,
    )


def assert_no_heading_leak(audit: StructuralSourceAudit) -> None:
    if audit.operative_text_heading_leaks:
        details = "; ".join(
            f"{d.locator}: {d.details.get('heading_text')}"
            for d in audit.operative_text_heading_leaks
        )
        raise AssertionError(
            "Source-fidelity failure: legislative heading leaked into operative "
            f"fragment_text ({details})"
        )


def assert_hierarchy_sound(audit: StructuralSourceAudit) -> None:
    if audit.cycle_issues:
        raise AssertionError(
            "Source-fidelity failure: cyclic structural hierarchy accepted "
            f"({[d.locator for d in audit.cycle_issues]})"
        )
    if audit.cross_source_parent_issues:
        raise AssertionError(
            "Source-fidelity failure: cross-source parent link accepted "
            f"({[d.locator for d in audit.cross_source_parent_issues]})"
        )
    if audit.parentage_issues:
        raise AssertionError(
            "Source-fidelity failure: parentage issues "
            f"({[d.code + ':' + str(d.locator) for d in audit.parentage_issues]})"
        )
