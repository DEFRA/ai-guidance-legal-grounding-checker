"""COMPAT_LEGACY_NAME — compatibility behaviour for the descriptive-name rename."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compat.component_aliases import (  # noqa: E402
    deprecate,
    resolve_env,
    resolve_producer_component,
)
from compat.artifacts import resolve_proposition_matcher_law_candidates  # noqa: E402
from compat.producer import producer_metadata  # noqa: E402


def test_deprecate_warns_and_resolves():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        comp = deprecate("beatrice")
    assert comp.slug == "proposition-matcher"
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_resolve_producer_component_accepts_legacy_and_canonical():
    assert resolve_producer_component("Susan") == "guidance-proposition-extractor"
    assert resolve_producer_component("guidance-proposition-extractor") == (
        "guidance-proposition-extractor"
    )


def test_resolve_env_prefers_canonical_and_conflicts():
    env = {"LAW_DISCOVERY_LEX_BASE_URL": "https://a.example"}
    assert resolve_env("LAW_DISCOVERY_LEX_BASE_URL", legacy_name="ADA_LEX_BASE_URL", environ=env) == (
        "https://a.example"
    )
    env = {"ADA_LEX_BASE_URL": "https://legacy.example"}
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        assert (
            resolve_env(
                "LAW_DISCOVERY_LEX_BASE_URL",
                legacy_name="ADA_LEX_BASE_URL",
                environ=env,
            )
            == "https://legacy.example"
        )
    env = {
        "LAW_DISCOVERY_LEX_BASE_URL": "https://a.example",
        "ADA_LEX_BASE_URL": "https://b.example",
    }
    with pytest.raises(RuntimeError, match="Conflicting"):
        resolve_env(
            "LAW_DISCOVERY_LEX_BASE_URL",
            legacy_name="ADA_LEX_BASE_URL",
            environ=env,
        )


def test_dual_read_legacy_artifact_filename(tmp_path: Path):
    legacy = tmp_path / "beatrice_law_candidates.json"
    legacy.write_text(json.dumps({"candidates": []}))
    found = resolve_proposition_matcher_law_candidates(tmp_path)
    assert found == legacy
    canonical = tmp_path / "proposition_matcher_law_candidates.json"
    canonical.write_text(json.dumps({"candidates": [{"id": "x"}]}))
    found = resolve_proposition_matcher_law_candidates(tmp_path)
    assert found == canonical


def test_producer_metadata_canonical():
    meta = producer_metadata("audit-assembler")
    assert meta["producer_component"] == "audit-assembler"
    assert meta["source_kind"] == "pipeline"


def test_frozen_susan_id_prefix_unchanged():
    # Proposition Matcher mapping must keep the historic ID scheme.
    mapping = (
        ROOT
        / "proposition-matcher"
        / "src"
        / "proposition_matcher"
        / "pipeline"
        / "mapping.py"
    ).read_text()
    assert 'id=f"susan-{_slug(url)}-{i}"' in mapping
    assert 'extraction_method="susan"' in mapping
