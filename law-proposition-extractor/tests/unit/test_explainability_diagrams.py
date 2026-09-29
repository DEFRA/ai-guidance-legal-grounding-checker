"""Explainability diagram suite: D2 sources, SVG freshness, Article 49a contracts."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from law_proposition_extractor_pipeline.explainability_docs.diagrams import check, generate
from law_proposition_extractor_pipeline.explainability_docs.diagrams.article_49a import (
    assert_article_49a_d2_contract,
    render_article_49a_walkthrough_d2,
)
from law_proposition_extractor_pipeline.explainability_docs.diagrams.divergence import (
    assert_divergence_d2_truthfulness,
    load_divergence_status_manifest,
)
from law_proposition_extractor_pipeline.explainability_docs.diagrams.paths import (
    DIAGRAM_IDS,
    d2_path,
    diagrams_index_path,
    svg_path,
)
from law_proposition_extractor_pipeline.explainability_docs.diagrams.render import find_d2_binary
from law_proposition_extractor_pipeline.explainability_docs.fixture_bundle import (
    load_serialized_bundle,
    resolve_roles,
    structured_list_path,
)
from law_proposition_extractor_pipeline.explainability_docs.paths import repo_root


def test_d2_binary_available() -> None:
    assert Path(find_d2_binary()).is_file()


def test_every_expected_d2_and_svg_exists() -> None:
    for diagram_id in DIAGRAM_IDS:
        assert d2_path(diagram_id).is_file(), f"missing {diagram_id}.d2"
        assert svg_path(diagram_id).is_file(), f"missing {diagram_id}.svg"


def test_diagrams_index_exists() -> None:
    assert diagrams_index_path().is_file()


def test_article_49a_semantic_roles_and_paths() -> None:
    bundle = load_serialized_bundle()
    roles = resolve_roles(bundle)
    assert set(roles) == {"P1", "P2", "E1", "E2", "E3", "P3"}
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


def test_article_49a_d2_contract() -> None:
    d2_text = render_article_49a_walkthrough_d2()
    assert_article_49a_d2_contract(d2_text)
    assert "ordinary reference" in d2_text
    assert "NOT an exception_to target" in d2_text
    assert "Model-proposed candidate" in d2_text
    assert "[LLM]" in d2_text and "[DET]" in d2_text
    visible = "\n".join(
        line for line in d2_text.splitlines() if not line.lstrip().startswith("#")
    )
    assert re.search(r"\bprop:[0-9a-f]+\b", visible) is None


def test_pipeline_diagram_stage_order_and_method_markers() -> None:
    text = d2_path("source-to-statement-pipeline").read_text(encoding="utf-8")
    order = [
        "SourceRecord",
        "SourceSnapshot",
        "SourceFragment",
        "Extraction selection",
        "Structural extraction frontier",
        "Model extraction proposal",
        "Deterministic validation",
        "Proposition",
        "Legal-effect classification",
        "LegalRuleGroup",
        "typed legal relationship",
        "EffectiveLawStatement",
        "required context",
        "Proposition Matcher candidate",
        "Workbench review",
    ]
    positions = [text.find(label) for label in order]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions)
    for token in ("[CFG]", "[DET]", "[LLM]", "[HUM]", "CRITICAL BOUNDARY"):
        assert token in text


def test_provenance_diagram_four_boundaries() -> None:
    text = d2_path("source-version-and-effects").read_text(encoding="utf-8")
    for phrase in (
        "retrieval timestamp ≠ legal as-of date",
        "revised manifestation ≠ Law Proposition Extractor independently applied every amendment",
        "source-effect annotation ≠ independently consumed affecting instrument",
        "consumed affecting instrument ≠ verified amendment application",
    ):
        assert phrase in text


def test_divergence_diagram_labels_unimplemented_truthfully() -> None:
    text = d2_path("divergence-workflow").read_text(encoding="utf-8")
    assert_divergence_d2_truthfulness(text)
    manifest = load_divergence_status_manifest()
    planned = [m["label"] for m in manifest["mechanisms"] if m["status"] == "planned"]
    assert "dynamic-reference" in planned
    assert "territorial" in planned
    assert "revocation/replacement" in planned


def test_no_absolute_paths_or_file_refs_in_outputs() -> None:
    banned = ("file://", "/Users/", "/home/", "/private/var/", "C:\\")
    for diagram_id in DIAGRAM_IDS:
        for path in (d2_path(diagram_id), svg_path(diagram_id)):
            text = path.read_text(encoding="utf-8")
            for token in banned:
                assert token not in text, f"{path.name} contains {token}"


def test_check_passes_and_is_deterministic() -> None:
    first = check()
    assert first.ok, first.message
    second = check()
    assert second.ok, second.message
    # Generation itself is deterministic: two generate dry-runs produce identical D2.
    from law_proposition_extractor_pipeline.explainability_docs.diagrams import build_d2_text

    for diagram_id in DIAGRAM_IDS:
        assert build_d2_text(diagram_id) == build_d2_text(diagram_id)


def test_check_detects_stale_svg() -> None:
    # Mutate a committed SVG briefly; check must detect staleness without writes
    # beyond this test's own restore.
    svg = svg_path("law-proposition-extractor-system-map")
    original = svg.read_bytes()
    try:
        svg.write_bytes(original + b"<!-- stale -->")
        result = check()
        assert not result.ok
        assert any("law-proposition-extractor-system-map.svg" in s for s in result.stale)
    finally:
        svg.write_bytes(original)
    assert check().ok


def test_check_does_not_modify_working_tree() -> None:
    root = repo_root()
    before = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "docs/assets/diagrams/explainability",
            "docs/assets/generated/diagrams/explainability",
            "docs/explainability/diagrams.md",
        ],
        cwd=root,
        text=True,
    )
    assert check().ok
    after = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "docs/assets/diagrams/explainability",
            "docs/assets/generated/diagrams/explainability",
            "docs/explainability/diagrams.md",
        ],
        cwd=root,
        text=True,
    )
    assert before == after


def test_generate_idempotent_offline() -> None:
    first = generate()
    assert first is not None
    second = generate()
    assert second.written_d2 == ()
    assert second.written_svg == ()
    assert check().ok


def test_diagrams_md_local_links_resolve() -> None:
    path = diagrams_index_path()
    text = path.read_text(encoding="utf-8")
    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    base = path.parent
    for _label, target in link_re.findall(text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        resolved = (base / path_part).resolve()
        assert resolved.exists(), f"diagrams.md link {target!r} does not resolve"


def test_diagram_svgs_embedded_in_diagrams_md() -> None:
    text = diagrams_index_path().read_text(encoding="utf-8")
    for diagram_id in DIAGRAM_IDS:
        assert f"{diagram_id}.svg" in text


def test_no_network_or_llm_in_diagram_modules() -> None:
    package = (
        repo_root()
        / "packages"
        / "pipeline"
        / "src"
        / "law_proposition_extractor_pipeline"
        / "explainability_docs"
        / "diagrams"
    )
    banned = ("openai", "anthropic", "httpx", "requests.get", "urllib.request")
    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in source, f"{path.name} references {token}"


def test_check_runtime_reasonable_for_ci() -> None:
    result = check()
    assert result.ok, result.message
    # Soft budget: full check (generate + D2 render) should stay under 90s locally/CI.
    assert result.check_seconds < 90, result.message
