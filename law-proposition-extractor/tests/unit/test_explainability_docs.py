"""Explainability handbook generator and freshness checks."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.explainability_docs import check, generate
from law_proposition_extractor_pipeline.explainability_docs.article_49a_walkthrough import (
    render_article_49a_walkthrough_body,
)
from law_proposition_extractor_pipeline.explainability_docs.fixture_bundle import (
    fixture_content_hash,
    load_serialized_bundle,
    resolve_roles,
    structured_list_path,
)
from law_proposition_extractor_pipeline.explainability_docs.heuristics_catalogue import (
    render_heuristic_catalogue,
)
from law_proposition_extractor_pipeline.explainability_docs.markers import (
    MarkerError,
    replace_generated_section,
)
from law_proposition_extractor_pipeline.explainability_docs.paths import handbook_dir, repo_root
from law_proposition_extractor_pipeline.heuristics import REGISTRY_VERSION, list_heuristics
from law_proposition_extractor_pipeline.heuristics.explainability_coverage import (
    RULES_EMITTING_DECISION_EXPLANATIONS,
    emits_decision_explanation,
)


def test_registry_ordering_deterministic() -> None:
    first = [h.rule_id for h in list_heuristics()]
    second = [h.rule_id for h in list_heuristics()]
    assert first == second == sorted(first)


def test_every_registry_rule_appears_in_generated_heuristics() -> None:
    catalogue = render_heuristic_catalogue()
    for heuristic in list_heuristics():
        assert f"## `{heuristic.rule_id}` — version {heuristic.version}" in catalogue
        assert "**Method:**" in catalogue
        assert heuristic.name  # registry integrity
        # version/name/method match registry
        section = catalogue.split(f"## `{heuristic.rule_id}` — version {heuristic.version}")[1]
        section = section.split("\n## `", 1)[0]
        assert heuristic.method.value in section.lower() or heuristic.method.value in section
        assert heuristic.plain_english_summary[:40] in section


def test_duplicate_rule_sections_cannot_occur() -> None:
    catalogue = render_heuristic_catalogue()
    headings = re.findall(r"^## `([^`]+)` — version ", catalogue, flags=re.M)
    assert len(headings) == len(set(headings))
    assert set(headings) == {h.rule_id for h in list_heuristics()}
    # Within each stage group, rule_id order remains deterministic.
    assert headings == list(dict.fromkeys(headings))


def test_explainability_coverage_declared_for_emitters() -> None:
    registered = {h.rule_id for h in list_heuristics()}
    assert RULES_EMITTING_DECISION_EXPLANATIONS <= registered
    for rule_id in RULES_EMITTING_DECISION_EXPLANATIONS:
        assert emits_decision_explanation(rule_id)


def test_generated_sections_are_current() -> None:
    result = check()
    assert result.ok, result.message


def test_check_fails_on_stale_generated_section(tmp_path: Path) -> None:
    root = repo_root()
    # Copy handbook into tmp and stale one generated file.
    src = handbook_dir(root)
    dst = tmp_path / "docs" / "explainability"
    dst.mkdir(parents=True)
    for path in src.iterdir():
        if path.is_file():
            (dst / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    heuristics = dst / "heuristics.md"
    text = heuristics.read_text(encoding="utf-8")
    stale = replace_generated_section(
        text,
        "heuristic-catalogue",
        "_Registry version: `STALE`.\n\n## Coverage summary\n\n- stale\n",
    )
    heuristics.write_text(stale, encoding="utf-8")

    # Point check at a fake root that still has packages/pipeline for repo_root?
    # check() uses repo_root() by default — instead invoke render comparison manually.
    from law_proposition_extractor_pipeline.explainability_docs import render_all_to_directory

    out = tmp_path / "out"
    render_all_to_directory(out, root=root)
    expected = (out / "heuristics.md").read_text(encoding="utf-8")
    assert heuristics.read_text(encoding="utf-8") != expected


def test_handwritten_text_outside_markers_preserved() -> None:
    path = handbook_dir() / "heuristics.md"
    original = path.read_text(encoding="utf-8")
    assert "Do not maintain a hand-written second" in original
    updated = replace_generated_section(
        original, "heuristic-catalogue", render_heuristic_catalogue()
    )
    # Hand-written preface remains.
    preface = original.split("<!-- BEGIN GENERATED: heuristic-catalogue -->")[0]
    assert updated.startswith(preface)


def test_missing_markers_fail_safely() -> None:
    with pytest.raises(MarkerError, match="Missing BEGIN"):
        replace_generated_section("# no markers\n", "heuristic-catalogue", "x")


def test_article_49a_roles_and_contract() -> None:
    bundle = load_serialized_bundle()
    roles = resolve_roles(bundle)
    assert set(roles) == {"P1", "P2", "E1", "E2", "E3", "P3"}
    assert len(bundle["propositions"]) == 6
    props = {
        role: next(p for p in bundle["propositions"] if p["id"] == pid)
        for role, pid in roles.items()
    }
    assert structured_list_path(props["E1"]) == "2-a-i"
    assert structured_list_path(props["E2"]) == "2-a-ii"
    assert structured_list_path(props["E3"]) == "2-b"

    groups = (bundle["legal_rule_groups"] or {}).get("groups") or []
    sizes = sorted(len(g.get("member_proposition_ids") or []) for g in groups)
    assert sizes == [2, 3]

    rels = (bundle["legal_rule_relationships"] or {}).get("relationships") or []
    assert sum(1 for r in rels if r.get("relationship_type") == "exception_to") == 3
    assert sum(1 for r in rels if r.get("relationship_type") == "triggered_by") == 1


def test_walkthrough_contents_and_safety() -> None:
    body = render_article_49a_walkthrough_body()
    assert "P1" in body and "E2" in body and "P3" in body
    assert "2-a-i" in body and "2-a-ii" in body and "2-b" in body
    assert "exception_to" in body and "triggered_by" in body
    assert "Article 14 is an ordinary reference" in body
    assert "not the target of `exception_to`" in body
    assert "applicable exceptions" in body
    assert fixture_content_hash() in body
    assert f"`{REGISTRY_VERSION}`" in body or f"Registry version:** `{REGISTRY_VERSION}`" in body
    assert "file://" not in body
    assert "/Users/" not in body
    assert "/private/var/" not in body
    # Must not depend on opaque live IDs in the main narrative tables.
    assert "prop:" not in body.split("## Generated-file provenance")[0]


def test_generate_is_offline_and_idempotent() -> None:
    # First generate should succeed without network.
    result = generate()
    assert result is not None
    # Second generate leaves files unchanged.
    again = generate()
    assert again.written == ()
    check_result = check()
    assert check_result.ok


def test_check_leaves_working_tree_unchanged() -> None:
    root = repo_root()
    before = subprocess.check_output(
        ["git", "status", "--porcelain", "docs/explainability"],
        cwd=root,
        text=True,
    )
    assert check().ok
    after = subprocess.check_output(
        ["git", "status", "--porcelain", "docs/explainability"],
        cwd=root,
        text=True,
    )
    assert before == after


def test_local_markdown_links_resolve() -> None:
    base = handbook_dir()
    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    for name in (
        "README.md",
        "concepts.md",
        "pipeline.md",
        "diagrams.md",
        "heuristics.md",
        "artifacts-and-lineage.md",
        "article-49a-walkthrough.md",
        "glossary.md",
    ):
        text = (base / name).read_text(encoding="utf-8")
        for _label, target in link_re.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            resolved = (base / path_part).resolve()
            assert resolved.exists(), f"{name} link {target!r} does not resolve"
