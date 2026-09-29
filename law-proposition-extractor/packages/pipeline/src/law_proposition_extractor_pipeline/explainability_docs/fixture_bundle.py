"""Load the offline Article 49a serialized acceptance bundle for docs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from law_proposition_extractor_pipeline.article_49a_legal_structure_acceptance import (
    identify_article_49a_propositions,
)

from .paths import fixture_dir

_SERIALIZED_KEYS: tuple[tuple[str, str], ...] = (
    ("propositions.json", "propositions"),
    ("sources.json", "sources"),
    ("source_snapshots.json", "source_snapshots"),
    ("source_fragments.slim.json", "source_fragments"),
    ("legal_rule_groups.json", "legal_rule_groups"),
    ("legal_rule_relationships.json", "legal_rule_relationships"),
    ("effective_law_statements.json", "effective_law_statements"),
    ("proposition_matcher_law_candidates.json", "proposition_matcher_law_candidates"),
    ("source_legal_effects.json", "source_legal_effects"),
    ("decision_explanations.json", "decision_explanations"),
)


def load_provenance(fixture: Path | None = None) -> dict[str, Any]:
    path = (fixture or fixture_dir()) / "PROVENANCE.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_serialized_bundle(fixture: Path | None = None) -> dict[str, Any]:
    """Load the committed serialized acceptance slice as a bundle dict."""
    base = fixture or fixture_dir()
    serialized = base / "serialized"
    bundle: dict[str, Any] = {}
    for filename, key in _SERIALIZED_KEYS:
        path = serialized / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing Article 49a serialized artifact: {filename}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        bundle[key] = payload
    return _normalise_bundle(bundle)


def _normalise_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Normalise list-vs-artifact shapes used by role resolution helpers."""
    out = dict(bundle)

    props = out.get("propositions")
    if isinstance(props, dict):
        out["propositions"] = props.get("propositions") or props.get("items") or []

    frags = out.get("source_fragments")
    if isinstance(frags, dict):
        out["source_fragments"] = frags.get("fragments") or frags.get("items") or []

    for key in ("sources", "source_snapshots"):
        value = out.get(key)
        if isinstance(value, dict):
            inner = value.get(key) or value.get("items") or []
            out[key] = inner

    els = out.get("effective_law_statements")
    if isinstance(els, list):
        out["effective_law_statements"] = {
            "schema_version": "1",
            "run_id": "run-001",
            "statements": els,
        }

    return out


def fixture_content_hash(fixture: Path | None = None) -> str:
    """Stable SHA-256 over PROVENANCE + serialized JSON filenames/contents."""
    base = fixture or fixture_dir()
    hasher = hashlib.sha256()
    paths: list[Path] = [base / "PROVENANCE.json"]
    serialized = base / "serialized"
    if serialized.is_dir():
        paths.extend(sorted(serialized.glob("*.json")))
    for path in paths:
        rel = path.relative_to(base).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def resolve_roles(bundle: dict[str, Any]) -> dict[str, str]:
    """Reuse acceptance semantic-role resolution (P1/P2/E1/E2/E3/P3)."""
    return identify_article_49a_propositions(bundle)


def prop_by_id(bundle: dict[str, Any], prop_id: str) -> dict[str, Any]:
    for prop in bundle.get("propositions") or []:
        if isinstance(prop, dict) and str(prop.get("id")) == prop_id:
            return prop
    raise KeyError(f"Proposition {prop_id!r} not found in bundle.")


def structured_list_path(prop: dict[str, Any]) -> str | None:
    meta = prop.get("extraction_debug_meta")
    if isinstance(meta, dict):
        path = meta.get("structured_list_path")
        return str(path) if path is not None else None
    return None
