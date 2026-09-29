"""Split monolithic source fragments into article- or size-bounded slices before extraction."""

from __future__ import annotations

import re
from collections.abc import Callable
from hashlib import sha256
from law_proposition_extractor_domain import ReviewDecision, SourceFragment, StructuralHeading

from law_proposition_extractor_pipeline.fragment_types import fragment_type_from_locator
from law_proposition_extractor_pipeline.extract import (
    _hard_split_text,
    _is_placeholder_locator,
    _split_paragraph_overlap_chunks,
)

_RE_ARTICLE_ENUM = re.compile(
    r"(?mi)^(Article|ARTICLE)\s+(\d+[a-z]?)\b[^\n]*$",
)
_RE_SECTION_ENUM = re.compile(
    r"(?mi)^(Section|SECTION)\s+(\d+[.:]?)\s*[^\n]*$",
)
_RE_XML_ARTICLE_SPLIT = re.compile(r"(?i)(?=<(?:[\w:-]*)article\b[^>]*>)")
_RE_XML_ARTICLE_NUM = re.compile(
    r"""n\s*=\s*["'](\d+)["']|\bnum\s*=\s*["'](\d+)["']|\bnumber\s*=\s*["'](\d+)["']""",
    re.IGNORECASE,
)
_RE_LIST_ITEM_SPLIT = re.compile(
    r"(?mi)(?=^(?:\(\w+\)|\[\w+\]|[a-z]\)|\d+\)|\([ivxlcdm]+\)|\([a-z]\))\s+)"
)


def content_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _normalized_placeholder_locator(locator: str) -> bool:
    return _is_placeholder_locator(locator)


def max_fragment_body_chars_for_llm_budget(*, max_extract_input_tokens: int, safety_margin: int = 2048) -> int:
    """Approximate max fragment characters aligned with extraction prompt budgeting."""
    avail = max(256, max_extract_input_tokens - safety_margin)
    overhead_tokens_est = 520
    body_tokens = max(128, avail - overhead_tokens_est)
    return max(4096, int(body_tokens * 3))


def _sanitize_loc_prefix(locator: str) -> str:
    loc = (locator or "").strip()
    if _normalized_placeholder_locator(loc):
        return "document:full"
    return loc


def _slice_xml_articles(text: str, parent_locator: str) -> list[tuple[str, str]] | None:
    stripped = text.strip()
    if "<article" not in stripped.lower():
        return None
    raw_parts = [p.strip() for p in _RE_XML_ARTICLE_SPLIT.split(stripped) if p.strip()]
    if len(raw_parts) < 2:
        return None
    out: list[tuple[str, str]] = []
    for i, part in enumerate(raw_parts):
        header = part[:240]
        m = _RE_XML_ARTICLE_NUM.search(header)
        if m:
            article_no = next((g for g in m.groups() if g), str(i + 1))
        else:
            article_no = str(i + 1)
        out.append((f"article:{article_no}", part))
    return out


def _slice_plain_articles(text: str, parent_locator: str) -> list[tuple[str, str]] | None:
    stripped = text.strip()
    matches = list(_RE_ARTICLE_ENUM.finditer(stripped))
    if len(matches) < 2:
        return None
    parts: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(stripped)
        body = stripped[start:end].strip()
        article_no = m.group(2)
        parts.append((f"article:{article_no}", body))
    return parts


def _slice_plain_sections(text: str, parent_locator: str) -> list[tuple[str, str]] | None:
    stripped = text.strip()
    matches = list(_RE_SECTION_ENUM.finditer(stripped))
    if len(matches) < 2:
        return None
    parts: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(stripped)
        body = stripped[start:end].strip()
        sec_no = re.sub(r"\s+", "", m.group(2))
        parts.append((f"section:{sec_no}", body))
    return parts


def _split_list_items(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    items = [part.strip() for part in _RE_LIST_ITEM_SPLIT.split(stripped) if part.strip()]
    return items if len(items) >= 2 else [stripped]


def _chunk_text_with_fallback(text: str, *, max_body_chars: int, overlap_chars: int) -> list[str]:
    piece = text.strip()
    if not piece:
        return []
    if len(piece) <= max_body_chars:
        return [piece]
    list_parts = _split_list_items(piece)
    if len(list_parts) >= 2:
        return list_parts
    paragraph_parts = _split_paragraph_overlap_chunks(piece, max_body_chars, overlap_chars)
    if len(paragraph_parts) >= 2:
        return [part.strip() for part in paragraph_parts if part.strip()]
    bounded = _hard_split_text(piece, max_body_chars, overlap_chars)
    return [part.strip() for part in bounded if part.strip()]


def plan_text_slices(
    full_text: str,
    parent_locator: str,
    *,
    max_body_chars: int,
    overlap_chars: int = 0,
) -> list[tuple[str, str, str]]:
    """Return (locator, text, strategy) slices covering full_text."""
    stripped = full_text.strip()
    if not stripped:
        return []
    prefix = _sanitize_loc_prefix(parent_locator)
    max_body_chars = max(2048, max_body_chars)
    ov = max(0, overlap_chars)

    initial: list[tuple[str, str, str]] | None = None
    for planner in (_slice_xml_articles, _slice_plain_articles, _slice_plain_sections):
        candidate = planner(stripped, parent_locator)
        if candidate and len(candidate) >= 2:
            if planner is _slice_xml_articles:
                strat_name = "article_xml"
            elif planner is _slice_plain_articles:
                strat_name = "article_plain"
            else:
                strat_name = "section_plain"
            initial = [(loc, txt, strat_name) for loc, txt in candidate]
            break
    if initial is None:
        initial = [(prefix, stripped, "monolith")]

    refined: list[tuple[str, str, str]] = []
    for loc, txt, strat in initial:
        base_loc = loc if loc.strip() else prefix
        piece = txt.strip()
        if not piece:
            continue
        if len(piece) <= max_body_chars:
            refined.append((base_loc, piece, strat))
            continue
        sub = _split_paragraph_overlap_chunks(piece, max_body_chars, ov)
        if len(sub) <= 1 and len(piece) > max_body_chars:
            sub = _hard_split_text(piece, max_body_chars, ov)
        if len(sub) == 1:
            refined.append((base_loc, sub[0], f"{strat}|bounded"))
        else:
            for idx, chunk in enumerate(sub):
                refined.append((f"{base_loc}|chunk:{idx:03d}", chunk.strip(), f"{strat}|chunk"))

    return [row for row in refined if row[1].strip()]


def _has_multi_slice_structure(text: str, parent_locator: str) -> bool:
    stripped = text.strip()
    for planner in (_slice_xml_articles, _slice_plain_articles, _slice_plain_sections):
        candidate = planner(stripped, parent_locator)
        if candidate and len(candidate) >= 2:
            return True
    return False


def expand_monolithic_source_fragment(
    fragment: SourceFragment,
    *,
    max_body_chars: int,
    overlap_chars: int = 0,
    slugify: Callable[[str], str],
) -> list[SourceFragment]:
    """Return one or more fragments; oversized bodies are split for extraction-sized prompts."""
    text = fragment.fragment_text.strip()
    if not text:
        return [fragment]

    meta_raw = dict(fragment.metadata) if isinstance(fragment.metadata, dict) else {}
    structural_entries_raw = meta_raw.get("structural_fragments")
    has_structural_plan = isinstance(structural_entries_raw, list) and len(structural_entries_raw) >= 2

    oversized = len(text) > max_body_chars
    placeholder_parent = _normalized_placeholder_locator(fragment.locator)
    structured_big_placeholder = (
        placeholder_parent
        and len(text) >= 8000
        and _has_multi_slice_structure(text, fragment.locator)
    )
    if not oversized and not structured_big_placeholder and not has_structural_plan:
        return [fragment]
    if isinstance(structural_entries_raw, list) and structural_entries_raw:
        structured_rows: list[dict[str, object]] = []
        for row in structural_entries_raw:
            if not isinstance(row, dict):
                continue
            loc = str(row.get("locator") or "").strip()
            body = str(row.get("text") or "").strip()
            if not loc or not body:
                continue
            structured_rows.append(row)
        if len(structured_rows) >= 2:
            slug_base = slugify(fragment.source_record_id)
            root_parent_id = fragment.id
            structured_out: list[SourceFragment] = []
            first_id_by_locator: dict[str, str] = {}
            next_order = 0
            base_meta = {k: v for k, v in meta_raw.items() if k != "structural_fragments"}
            sorted_rows = sorted(
                structured_rows,
                key=lambda row: int(str(row.get("order_index") or "0"))
                if str(row.get("order_index") or "0").strip().isdigit()
                else 0,
            )
            for row in sorted_rows:
                locator = str(row.get("locator") or "").strip()
                parent_locator = str(row.get("parent_locator") or "").strip() or None
                strategy = "legislation_structural"
                per_row_meta = row.get("metadata")
                row_meta = per_row_meta if isinstance(per_row_meta, dict) else {}
                body = str(row.get("text") or "").strip()
                chunks = _chunk_text_with_fallback(
                    body,
                    max_body_chars=max_body_chars,
                    overlap_chars=overlap_chars,
                )
                if not chunks:
                    continue
                # Structural parent comes from explicit ancestry (parent_locator), never
                # from the monolithic root id. The root is replaced by expanded rows and
                # often shares frag-…-001 with the first article, which previously made
                # every top-level provision appear to parent to article:1.
                parent_fragment_id = (
                    first_id_by_locator.get(parent_locator) if parent_locator else None
                )
                for chunk_idx, chunk in enumerate(chunks):
                    suffix = f"{next_order + 1:03d}"
                    fid = f"frag-{slug_base}-{suffix}"
                    chunk_locator = locator
                    if len(chunks) > 1:
                        chunk_locator = f"{locator}|chunk:{chunk_idx + 1:03d}"
                    frag_hash = content_hash(chunk)
                    meta = dict(base_meta)
                    meta.update(row_meta)
                    meta.update(
                        {
                            "fragmentation_strategy": strategy if len(chunks) == 1 else f"{strategy}|chunk",
                            "fragmentation_parent_fragment_id": root_parent_id,
                        }
                    )
                    number_label_raw = row.get("number_label")
                    number_label = (
                        str(number_label_raw).strip() if number_label_raw else None
                    ) or None
                    # Authoritative heading lives on the first chunk for this locator.
                    structural_heading = None
                    if chunk_idx == 0 and isinstance(row.get("structural_heading"), dict):
                        heading_payload = dict(row["structural_heading"])
                        heading_payload.setdefault("owner_locator", locator)
                        heading_payload["owner_fragment_id"] = fid
                        if number_label and not heading_payload.get("number_label"):
                            heading_payload["number_label"] = number_label
                        try:
                            structural_heading = StructuralHeading.model_validate(
                                heading_payload
                            )
                        except Exception:
                            structural_heading = None
                    structured_out.append(
                        SourceFragment(
                            id=fid,
                            fragment_id=fid,
                            source_record_id=fragment.source_record_id,
                            source_snapshot_id=fragment.source_snapshot_id,
                            fragment_type=fragment_type_from_locator(chunk_locator),
                            locator=chunk_locator,
                            fragment_text=chunk,
                            fragment_hash=frag_hash,
                            text_hash=frag_hash,
                            char_start=None,
                            char_end=None,
                            parent_fragment_id=parent_fragment_id,
                            order_index=next_order,
                            review_status=fragment.review_status,
                            number_label=number_label,
                            structural_heading=structural_heading,
                            metadata=meta,
                        )
                    )
                    if locator not in first_id_by_locator:
                        first_id_by_locator[locator] = fid
                    next_order += 1
            if len(structured_out) >= 2:
                return structured_out

    slices = plan_text_slices(
        text,
        fragment.locator,
        max_body_chars=max_body_chars,
        overlap_chars=overlap_chars if oversized else 0,
    )
    if len(slices) <= 1:
        return [fragment]

    slug_base = slugify(fragment.source_record_id)
    parent_id = fragment.id
    sliced_out: list[SourceFragment] = []
    for order_idx, (locator, body, strategy) in enumerate(slices):
        suffix = f"{order_idx + 1:03d}"
        fid = f"frag-{slug_base}-{suffix}"
        frag_hash = content_hash(body)
        meta = {k: v for k, v in meta_raw.items() if k != "structural_fragments"}
        meta.update(
            {
                "fragmentation_strategy": strategy,
                "fragmentation_parent_fragment_id": parent_id,
            }
        )
        sliced_out.append(
            SourceFragment(
                id=fid,
                fragment_id=fid,
                source_record_id=fragment.source_record_id,
                source_snapshot_id=fragment.source_snapshot_id,
                fragment_type=fragment_type_from_locator(locator),
                locator=locator,
                fragment_text=body,
                fragment_hash=frag_hash,
                text_hash=frag_hash,
                char_start=None,
                char_end=None,
                # Root monolith is replaced by these slices; do not invent a
                # sibling→sibling parent via the reused frag-…-001 id.
                parent_fragment_id=None,
                order_index=order_idx,
                review_status=fragment.review_status,
                metadata=meta,
            )
        )
    return sliced_out


def reviews_for_expanded_fragments(
    template: ReviewDecision,
    fragments: list[SourceFragment],
    *,
    slugify: Callable[[str], str],
) -> list[ReviewDecision]:
    rows: list[ReviewDecision] = []
    for frag in fragments:
        rid = f"review-{slugify(frag.id)}"
        rows.append(
            ReviewDecision(
                id=rid,
                target_type="source_fragment",
                target_id=frag.id,
                previous_status=None,
                new_status=template.new_status,
                reviewer=template.reviewer,
                note=template.note,
                metadata={
                    **(template.metadata or {}),
                    "fragmentation_parent_review_id": template.id,
                    "source_fragment_id": frag.id,
                    "source_record_id": frag.source_record_id,
                    "source_snapshot_id": frag.source_snapshot_id,
                },
            )
        )
    return rows
