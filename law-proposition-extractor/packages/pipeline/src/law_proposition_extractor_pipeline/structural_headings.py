"""Structural legislative heading inheritance (no proposition creation)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from law_proposition_extractor_domain import (
    SourceFragment,
    StructuralHeading,
    StructuralHeadingContext,
    StructuralHeadingKind,
)

_PROVISION_KINDS = frozenset(
    {
        StructuralHeadingKind.ARTICLE,
        StructuralHeadingKind.REGULATION,
        StructuralHeadingKind.RULE,
        StructuralHeadingKind.SCHEDULE,
        StructuralHeadingKind.ANNEX,
        StructuralHeadingKind.SECTION,
        StructuralHeadingKind.PROVISION,
    }
)

_CONTAINER_KINDS = frozenset(
    {
        StructuralHeadingKind.PART,
        StructuralHeadingKind.TITLE,
        StructuralHeadingKind.CHAPTER,
        StructuralHeadingKind.DIVISION,
    }
)


def heading_kind_from_locator(locator: str) -> StructuralHeadingKind:
    kind = str(locator or "").split(":", maxsplit=1)[0].strip().lower()
    try:
        return StructuralHeadingKind(kind)
    except ValueError:
        if kind in {"annex"}:
            return StructuralHeadingKind.ANNEX
        return StructuralHeadingKind.UNKNOWN


def format_structural_heading_display(
    *,
    number_label: str | None,
    heading_text: str | None,
) -> str:
    """Format ``NUMBER — heading`` with graceful fallbacks."""
    number = " ".join(str(number_label or "").replace("\xa0", " ").split()).strip()
    heading = " ".join(str(heading_text or "").replace("\xa0", " ").split()).strip()
    if number and heading:
        return f"{number} — {heading}"
    return number or heading


def structural_heading_to_context(
    heading: StructuralHeading,
    *,
    fallback_number_label: str | None = None,
) -> StructuralHeadingContext:
    return StructuralHeadingContext(
        kind=heading.kind,
        number_label=heading.number_label or fallback_number_label,
        heading_text=heading.text,
        owner_locator=heading.owner_locator,
        owner_fragment_id=heading.owner_fragment_id,
        change_ids=heading.change_ids,
        commentary_refs=heading.commentary_refs,
    )


def _fragment_as_mapping(fragment: SourceFragment | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(fragment, SourceFragment):
        return fragment.model_dump(mode="json")
    return dict(fragment)


def _parse_heading(raw: Any) -> StructuralHeading | None:
    if raw is None:
        return None
    if isinstance(raw, StructuralHeading):
        return raw
    if isinstance(raw, Mapping):
        try:
            return StructuralHeading.model_validate(raw)
        except Exception:
            return None
    return None


def resolve_structural_heading_contexts(
    fragment: SourceFragment | Mapping[str, Any],
    fragments_by_id: Mapping[str, SourceFragment | Mapping[str, Any]],
) -> list[StructuralHeadingContext]:
    """Return outermost→nearest structural heading path for ``fragment``.

    Follows validated parent links only within the same source record/snapshot.
    Does not infer headings from locator strings or proposition labels.
    """
    start = _fragment_as_mapping(fragment)
    start_id = str(start.get("id") or start.get("fragment_id") or "").strip()
    source_record_id = str(start.get("source_record_id") or "").strip()
    source_snapshot_id = str(start.get("source_snapshot_id") or "").strip()

    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: dict[str, Any] | None = start
    while current is not None:
        fid = str(current.get("id") or current.get("fragment_id") or "").strip()
        if fid:
            if fid in seen:
                break
            seen.add(fid)
        if source_record_id and str(current.get("source_record_id") or "") != source_record_id:
            break
        if source_snapshot_id and str(current.get("source_snapshot_id") or "") != source_snapshot_id:
            break
        chain.append(current)
        parent_id = str(current.get("parent_fragment_id") or "").strip()
        if not parent_id or parent_id not in fragments_by_id:
            break
        current = _fragment_as_mapping(fragments_by_id[parent_id])

    # Outermost first.
    chain.reverse()
    contexts: list[StructuralHeadingContext] = []
    seen_owners: set[str] = set()
    for row in chain:
        heading = _parse_heading(row.get("structural_heading"))
        if heading is None:
            continue
        owner_key = (
            str(heading.owner_locator or row.get("locator") or "").strip()
            or str(row.get("id") or "").strip()
            or heading.text
        )
        if owner_key in seen_owners:
            continue
        seen_owners.add(owner_key)
        number_label = heading.number_label or (
            str(row.get("number_label") or "").strip() or None
        )
        contexts.append(
            structural_heading_to_context(heading, fallback_number_label=number_label)
        )
    # Ensure direct fragment heading is present once even if parent walk skipped it.
    if start_id and start.get("structural_heading") is not None:
        direct = _parse_heading(start.get("structural_heading"))
        if direct is not None:
            owner_key = (
                str(direct.owner_locator or start.get("locator") or "").strip()
                or start_id
            )
            if owner_key not in seen_owners:
                contexts.append(
                    structural_heading_to_context(
                        direct,
                        fallback_number_label=str(start.get("number_label") or "").strip()
                        or None,
                    )
                )
    return contexts


def nearest_provision_heading(
    fragment: SourceFragment | Mapping[str, Any],
    fragments_by_id: Mapping[str, SourceFragment | Mapping[str, Any]],
) -> StructuralHeadingContext | None:
    """Nearest article/regulation/… heading for UI chrome."""
    contexts = resolve_structural_heading_contexts(fragment, fragments_by_id)
    for ctx in reversed(contexts):
        if ctx.kind in _PROVISION_KINDS:
            return ctx
    for ctx in reversed(contexts):
        if ctx.kind not in _CONTAINER_KINDS:
            return ctx
    return contexts[-1] if contexts else None


def structural_heading_contexts_for_export(
    contexts: Sequence[StructuralHeadingContext],
) -> list[dict[str, Any]]:
    """Serialize heading contexts for extraction jobs / API (omit empty optionals)."""
    out: list[dict[str, Any]] = []
    for ctx in contexts:
        row: dict[str, Any] = {
            "kind": str(ctx.kind.value if isinstance(ctx.kind, StructuralHeadingKind) else ctx.kind),
            "heading_text": ctx.heading_text,
        }
        if ctx.number_label:
            row["number_label"] = ctx.number_label
        if ctx.owner_locator:
            row["owner_locator"] = ctx.owner_locator
        if ctx.owner_fragment_id:
            row["owner_fragment_id"] = ctx.owner_fragment_id
        if ctx.change_ids:
            row["change_ids"] = list(ctx.change_ids)
        if ctx.commentary_refs:
            row["commentary_refs"] = list(ctx.commentary_refs)
        out.append(row)
    return out


def format_heading_contexts_for_prompt(
    contexts: Sequence[StructuralHeadingContext | Mapping[str, Any]],
) -> str:
    """Render labelled non-operative structural context for extraction prompts."""
    lines: list[str] = []
    for ctx in contexts:
        if isinstance(ctx, StructuralHeadingContext):
            number = ctx.number_label
            text = ctx.heading_text
        else:
            number = str(ctx.get("number_label") or "").strip() or None
            text = str(ctx.get("heading_text") or ctx.get("text") or "").strip()
        display = format_structural_heading_display(number_label=number, heading_text=text)
        if display:
            lines.append(f"- {display}")
    return "\n".join(lines)


def parse_structural_heading_contexts(
    raw: Any,
) -> list[StructuralHeadingContext]:
    """Load heading contexts from job JSON; tolerate absent/legacy payloads."""
    if not isinstance(raw, list):
        return []
    out: list[StructuralHeadingContext] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        try:
            out.append(StructuralHeadingContext.model_validate(item))
        except Exception:
            continue
    return out
