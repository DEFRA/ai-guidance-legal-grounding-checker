"""Duplicate proposition identity checks for export bundles (deterministic)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def _str_field(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def find_duplicate_proposition_ids(
    propositions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return groups where the same ``id`` appears on more than one proposition row."""
    by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in propositions:
        if not isinstance(row, dict):
            continue
        pid = _str_field(row, "id")
        if not pid:
            continue
        by_id[pid].append(
            {
                "source_record_id": _str_field(row, "source_record_id"),
                "source_fragment_id": _str_field(row, "source_fragment_id"),
                "fragment_locator": _str_field(row, "fragment_locator")
                or _str_field(row, "article_reference"),
                "proposition_key": _str_field(row, "proposition_key"),
            }
        )
    out: list[dict[str, Any]] = []
    for pid in sorted(by_id):
        members = by_id[pid]
        if len(members) <= 1:
            continue
        out.append({"id": pid, "count": len(members), "members": members})
    return out


def find_duplicate_proposition_keys(
    propositions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Duplicate ``proposition_key`` within the same source is an error; cross-source is a warning."""
    by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in propositions:
        if not isinstance(row, dict):
            continue
        key = _str_field(row, "proposition_key")
        sid = _str_field(row, "source_record_id")
        if not key:
            continue
        by_key[(sid, key)].append(
            {
                "proposition_id": _str_field(row, "id"),
                "source_fragment_id": _str_field(row, "source_fragment_id"),
                "fragment_locator": _str_field(row, "fragment_locator"),
            }
        )
    out: list[dict[str, Any]] = []
    for (sid, key), members in sorted(by_key.items()):
        if len(members) <= 1:
            continue
        out.append(
            {
                "source_record_id": sid,
                "proposition_key": key,
                "count": len(members),
                "members": members,
                "severity": "error",
            }
        )
    return out


def find_duplicate_proposition_version_ids(
    propositions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_ver: dict[str, list[str]] = defaultdict(list)
    for row in propositions:
        if not isinstance(row, dict):
            continue
        ver = _str_field(row, "proposition_version_id")
        pid = _str_field(row, "id")
        if not ver:
            continue
        by_ver[ver].append(pid)
    out: list[dict[str, Any]] = []
    for ver in sorted(by_ver):
        pids = by_ver[ver]
        if len(pids) <= 1:
            continue
        out.append({"proposition_version_id": ver, "count": len(pids), "proposition_ids": pids})
    return out


def seq_token_from_proposition_key(proposition_key: str) -> str:
    match = re.search(r":p(\d+)$", proposition_key.strip())
    if match:
        return match.group(1)
    return "001"


def reconstruct_staging_proposition_id(row: dict[str, Any]) -> str:
    """Rebuild a pre-opaque staging id so ``_build_proposition_records`` can re-hash."""
    from .intake import slugify

    sid = slugify(_str_field(row, "source_record_id"))
    frag_id = _str_field(row, "source_fragment_id")
    if frag_id:
        stem = f"{sid}-{slugify(frag_id)}"
    else:
        loc = _str_field(row, "fragment_locator") or _str_field(row, "article_reference")
        stem = f"{sid}-{slugify(loc)}" if loc else sid
    seq = seq_token_from_proposition_key(_str_field(row, "proposition_key"))
    try:
        seq_num = max(1, int(seq))
    except ValueError:
        seq_num = 1
    return f"prop-{stem}-{seq_num:03d}"


def proposition_identity_match_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    """Match rows across reidentity when ``proposition_key`` may be regenerated."""
    text = re.sub(r"\s+", " ", _str_field(row, "proposition_text")).lower()
    seq = seq_token_from_proposition_key(_str_field(row, "proposition_key"))
    return (
        _str_field(row, "source_record_id"),
        _str_field(row, "source_fragment_id"),
        seq,
        text,
    )
