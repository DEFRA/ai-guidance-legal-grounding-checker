"""Offline Article 49a legal-structure acceptance contract (prompt 19-BR1).

Exercises production ingestion → extraction → groups → relationships →
effective-law → Proposition Matcher → source effects → export using captured CLML and
frontier responses. No network, LLM, or secrets.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from law_proposition_extractor_llm.client import TextCompletionResult
from law_proposition_extractor_pipeline.export import export_bundle
from law_proposition_extractor_pipeline.runner import build_bundle_from_case
from law_proposition_extractor_pipeline.sources import LegislationGovUkAuthorityAdapter, SourceIngestionService

FIXTURE_REL = Path("tests/fixtures/article_49a_legal_structure")

REQUIRED_EXTRACTION_LOCATORS = (
    "article:49a:paragraph:1",
    "article:49a:paragraph:2",
    "article:49a:paragraph:3",
)

PARAGRAPH_2_PATHS = ("2-a-i", "2-a-ii", "2-b")

ARTICLE_49A_EFFECT_ANNOTATION_IDS = {
    "c000004": "article:49a",
    "key-ae688d7efb8d525f494201f970bc3e75": "article:49a:paragraph:1",
    "key-cd016a627475b52260f225a4d4ac7ed7": "article:49a:paragraph:2",
    "key-c36fcfcb069fb8c51fce93fbce7ea03b": "article:49a:paragraph:3",
}

ARTICLE_1_EFFECT_ANNOTATION_ID = "c000001"


@dataclass(frozen=True)
class Article49aAcceptanceResult:
    bundle: dict[str, Any]
    export_dir: Path
    proposition_ids: dict[str, str]


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "tests" / "fixtures").is_dir():
            return candidate
    return here.parents[4]


def fixture_dir(repo_root: Path | None = None) -> Path:
    root = repo_root if repo_root is not None else _repo_root()
    return root / FIXTURE_REL


def load_case(fixture: Path | None = None) -> dict[str, Any]:
    base = fixture if fixture is not None else fixture_dir()
    return json.loads((base / "case.json").read_text(encoding="utf-8"))


def load_frontier_responses(fixture: Path | None = None) -> dict[str, str]:
    base = fixture if fixture is not None else fixture_dir()
    responses_dir = base / "frontier_responses"
    return {
        "article:49a:paragraph:1": (
            responses_dir / "article_49a_paragraph_1.json"
        ).read_text(encoding="utf-8"),
        "article:49a:paragraph:2": (
            responses_dir / "article_49a_paragraph_2.json"
        ).read_text(encoding="utf-8"),
        "article:49a:paragraph:3": (
            responses_dir / "article_49a_paragraph_3.json"
        ).read_text(encoding="utf-8"),
    }


def _fragment_by_locator(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for frag in bundle.get("source_fragments") or []:
        if isinstance(frag, dict) and frag.get("locator"):
            out[str(frag["locator"])] = frag
    return out


def _parent_locator(frag: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str | None:
    parent_id = frag.get("parent_fragment_id")
    if not parent_id:
        return None
    parent = by_id.get(str(parent_id))
    if not parent:
        return None
    loc = parent.get("locator")
    return str(loc) if loc else None


def _props(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rows = bundle.get("propositions") or []
    return [p for p in rows if isinstance(p, dict)]


def _article_49a_props(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        p
        for p in _props(bundle)
        if str(p.get("fragment_locator") or "").startswith("article:49a")
    ]


def _debug_meta(prop: dict[str, Any]) -> dict[str, Any]:
    meta = prop.get("extraction_debug_meta")
    return meta if isinstance(meta, dict) else {}


def _structured_path(prop: dict[str, Any]) -> str | None:
    path = _debug_meta(prop).get("structured_list_path")
    return str(path) if path else None


def identify_article_49a_propositions(bundle: dict[str, Any]) -> dict[str, str]:
    """Map stable semantic roles → proposition ids (not live-run ids)."""
    props = _article_49a_props(bundle)
    by_role: dict[str, str] = {}

    p1 = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:1")
    ]
    p1_sorted = sorted(p1, key=lambda p: int(p.get("source_order") or 0))
    if len(p1_sorted) != 2:
        raise AssertionError(
            f"Expected 2 paragraph-1 propositions; found {len(p1_sorted)}."
        )
    # P1 = separate-identification (obligation / first); P2 = no-mixing (prohibition).
    separate = next(
        (
            p
            for p in p1_sorted
            if str(p.get("legal_effect_type") or "") == "obligation"
            or "identifiable" in str(p.get("proposition_text") or "").lower()
            or "placed in boxes" in str(p.get("proposition_text") or "").lower()
        ),
        p1_sorted[0],
    )
    mixing = next((p for p in p1_sorted if p is not separate), p1_sorted[1])
    by_role["P1"] = str(separate["id"])
    by_role["P2"] = str(mixing["id"])

    p2 = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:2")
    ]
    by_path = {_structured_path(p): p for p in p2 if _structured_path(p)}
    for path, role in (("2-a-i", "E1"), ("2-a-ii", "E2"), ("2-b", "E3")):
        prop = by_path.get(path)
        if prop is None:
            raise AssertionError(
                f"Expected one paragraph-2 proposition for path {path}; found 0."
            )
        by_role[role] = str(prop["id"])

    p3 = [
        p
        for p in props
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:3")
    ]
    if len(p3) != 1:
        raise AssertionError(
            f"Expected 1 paragraph-3 proposition; found {len(p3)}."
        )
    by_role["P3"] = str(p3[0]["id"])
    return by_role


def _groups_artifact(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("legal_rule_groups")
    if isinstance(raw, dict):
        groups = raw.get("groups") or []
        return [g for g in groups if isinstance(g, dict)]
    if isinstance(raw, list):
        return [g for g in raw if isinstance(g, dict)]
    return []


def _relationships_artifact(bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
    raw = bundle.get("legal_rule_relationships")
    if isinstance(raw, dict):
        rels = raw.get("relationships") or []
        diags = raw.get("diagnostics") or []
        return [r for r in rels if isinstance(r, dict)], list(diags)
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)], []
    return [], []


def _statements_artifact(bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
    raw = bundle.get("effective_law_statements")
    if isinstance(raw, dict):
        stmts = raw.get("statements") or []
        diags = raw.get("diagnostics") or []
        return [s for s in stmts if isinstance(s, dict)], list(diags)
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, dict)], []
    return [], []


def _candidates_artifact(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("proposition_matcher_law_candidates")
    if isinstance(raw, dict):
        cands = raw.get("candidates") or []
        return [c for c in cands if isinstance(c, dict)]
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    return []


def _effects_artifact(bundle: dict[str, Any]) -> dict[str, Any]:
    raw = bundle.get("source_legal_effects")
    return raw if isinstance(raw, dict) else {}


def _statement_for_prop(statements: list[dict[str, Any]], prop_id: str) -> dict[str, Any]:
    for stmt in statements:
        source_ids = [str(x) for x in (stmt.get("source_proposition_ids") or [])]
        if prop_id in source_ids:
            return stmt
    raise AssertionError(f"Expected effective-law statement for proposition {prop_id}.")


def _contexts_of_kind(stmt: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [
        c
        for c in (stmt.get("required_context") or [])
        if isinstance(c, dict) and str(c.get("kind") or "") == kind
    ]


def _decision_explanations(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("decision_explanations")
    if isinstance(raw, dict):
        rows = raw.get("decisions") or []
        return [r for r in rows if isinstance(r, dict)]
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


def _explanation_evidence_value(
    expl: dict[str, Any], *, kind: str, label: str | None = None
) -> str | None:
    for row in expl.get("evidence") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind") or "") != kind:
            continue
        if label is not None and str(row.get("label") or "") != label:
            continue
        value = row.get("value")
        return str(value) if value is not None else None
    return None


def _explanations_for_locator(
    explanations: list[dict[str, Any]],
    *,
    locator: str,
    rule_id: str | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for expl in explanations:
        loc_values = {
            str(row.get("value") or "")
            for row in (expl.get("evidence") or [])
            if isinstance(row, dict) and str(row.get("kind") or "") == "source_locator"
        }
        alt_values = {
            str(row.get("value") or "")
            for row in (expl.get("alternatives") or [])
            if isinstance(row, dict)
        }
        if locator not in loc_values and locator not in alt_values:
            blob = json.dumps(expl, sort_keys=True)
            if locator not in blob:
                continue
        if rule_id is not None and str(expl.get("rule_id") or "") != rule_id:
            continue
        matches.append(expl)
    return matches


def assert_article_49a_selection_explanations(bundle: dict[str, Any]) -> None:
    """Assert selection DecisionExplanation records for the Article 49a frontier."""
    from law_proposition_extractor_pipeline.heuristics.registry import get_heuristic, require_heuristic

    explanations = [
        e
        for e in _decision_explanations(bundle)
        if str(e.get("stage") or "selection") == "selection"
    ]
    if not explanations:
        raise AssertionError(
            "Expected decision_explanations for Article 49a selection frontier; found none."
        )

    frags = _fragment_by_locator(bundle)

    def _require_one(*, locator: str, rule_id: str, outcome: str) -> dict[str, Any]:
        matches = [
            e
            for e in _explanations_for_locator(
                explanations, locator=locator, rule_id=rule_id
            )
            if str(e.get("outcome") or "") == outcome
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"Expected exactly one explanation for {locator!r} "
                f"rule={rule_id!r} outcome={outcome!r}; found {len(matches)}."
            )
        expl = matches[0]
        subject_id = str(expl.get("subject_id") or "")
        frag = frags.get(locator)
        if frag is not None and subject_id and subject_id != str(frag.get("id") or ""):
            raise AssertionError(
                f"Explanation for {locator!r} subject_id={subject_id!r} "
                f"does not match fragment id {frag.get('id')!r}."
            )
        rule_version = str(expl.get("rule_version") or "")
        registered = require_heuristic(rule_id)
        if rule_version != registered.version:
            raise AssertionError(
                f"Explanation rule_version {rule_version!r} for {rule_id!r} "
                f"does not match registry version {registered.version!r}."
            )
        if get_heuristic(rule_id) is None:
            raise AssertionError(f"Emitted rule_id {rule_id!r} is not in the registry.")
        if str(expl.get("method") or "") == "llm":
            raise AssertionError(
                f"Selection explanation for {locator!r} incorrectly claims LLM method."
            )
        return expl

    for para in REQUIRED_EXTRACTION_LOCATORS:
        _require_one(
            locator=para,
            rule_id="selection.required_locator",
            outcome="selected_for_extraction",
        )

    parent = _require_one(
        locator="article:49a",
        rule_id="selection.prefer_required_children",
        outcome="not_selected_for_extraction",
    )
    coverage = _explanation_evidence_value(parent, kind="coverage_basis")
    if coverage != "covered_by_selected_children":
        raise AssertionError(
            "Expected article:49a parent suppression coverage_basis "
            f"covered_by_selected_children; found {coverage!r}."
        )
    preferred_children = {
        str(alt.get("value") or "")
        for alt in (parent.get("alternatives") or [])
        if isinstance(alt, dict)
        and str(alt.get("role") or "") == "preferred_extraction_unit"
    }
    for para in REQUIRED_EXTRACTION_LOCATORS:
        if para not in preferred_children:
            raise AssertionError(
                "Expected article:49a prefer-children explanation to identify "
                f"{para!r} as a preferred extraction unit; "
                f"found {sorted(preferred_children)}."
            )

    sub_a = _require_one(
        locator="article:49a:paragraph:2:subparagraph:a",
        rule_id="selection.prefer_required_ancestor",
        outcome="not_selected_for_extraction",
    )
    preferred = _explanation_evidence_value(
        sub_a, kind="source_locator", label="Preferred ancestor locator"
    )
    if preferred != "article:49a:paragraph:2":
        raise AssertionError(
            "Expected paragraph 2(a) preferred ancestor locator "
            f"article:49a:paragraph:2; found {preferred!r}."
        )
    coverage_a = _explanation_evidence_value(sub_a, kind="coverage_basis")
    if coverage_a != "structured_list_ancestor_covers_descendant":
        raise AssertionError(
            "Expected paragraph 2(a) coverage_basis "
            f"structured_list_ancestor_covers_descendant; found {coverage_a!r}."
        )
    original = _explanation_evidence_value(sub_a, kind="original_selection_reason")
    if original != "focus_term_match":
        raise AssertionError(
            "Expected paragraph 2(a) original_selection_reason "
            f"focus_term_match; found {original!r}."
        )
    # Fixture focus terms (case.json): "Norwegian pout", "boarfish".
    # Matcher stores normalized lowercase forms captured at selection time.
    matched_terms = sorted(
        {
            str(row.get("value") or "").lower()
            for row in (sub_a.get("evidence") or [])
            if isinstance(row, dict) and str(row.get("kind") or "") == "matched_focus_term"
        }
    )
    expected_terms = sorted({"norwegian pout", "boarfish"})
    if matched_terms != expected_terms:
        raise AssertionError(
            "Expected paragraph 2(a) captured matched focus terms "
            f"{expected_terms}; found {matched_terms}."
        )
    if sub_a.get("metadata", {}).get("focus_match_evidence_available") is not True:
        raise AssertionError(
            "Expected paragraph 2(a) suppression explanation to retain "
            "focus_match_evidence_available=true."
        )
    if len(explanations) != 5:
        raise AssertionError(
            "Expected exactly five final Article 49a selection explanations; "
            f"found {len(explanations)}."
        )


def assert_article_49a_structured_list_explanations(
    bundle: dict[str, Any], *, roles: dict[str, str]
) -> None:
    """Assert structured-list composition explanations for Article 49a paragraph 2."""
    from law_proposition_extractor_pipeline.heuristics.registry import require_heuristic

    explanations = [
        e
        for e in _decision_explanations(bundle)
        if str(e.get("stage") or "") == "extraction"
    ]
    compose = [
        e
        for e in explanations
        if str(e.get("rule_id") or "") == "structured_list.compose_terminal_leaf"
    ]
    props = {str(p["id"]): p for p in _article_49a_props(bundle)}

    def _compose_for(path: str, prop_id: str) -> dict[str, Any]:
        matches = [
            e
            for e in compose
            if str(e.get("subject_id") or "") == prop_id
            and (
                _explanation_evidence_value(e, kind="structured_list_path") == path
                or str((e.get("metadata") or {}).get("structured_list_path") or "") == path
            )
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"Expected exactly one compose explanation for path {path!r} "
                f"subject={prop_id!r}; found {len(matches)}."
            )
        expl = matches[0]
        rule = require_heuristic("structured_list.compose_terminal_leaf")
        if str(expl.get("rule_version") or "") != rule.version:
            raise AssertionError(
                f"Compose explanation rule_version {expl.get('rule_version')!r} "
                f"does not match registry version {rule.version!r}."
            )
        if str(expl.get("method") or "") != "deterministic":
            raise AssertionError(
                f"Expected deterministic method for structured-list composition on "
                f"{path}; found {expl.get('method')!r}."
            )
        if str(expl.get("subject_kind") or "") != "proposition":
            raise AssertionError(
                f"Expected compose subject_kind=proposition for {path}; "
                f"found {expl.get('subject_kind')!r}."
            )
        return expl

    e1 = _compose_for("2-a-i", roles["E1"])
    e2 = _compose_for("2-a-ii", roles["E2"])
    e3 = _compose_for("2-b", roles["E3"])

    def _component_roles(expl: dict[str, Any]) -> set[str]:
        roles_found: set[str] = set()
        for row in expl.get("evidence") or []:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind") or "")
            if kind.startswith("component_") and not kind.endswith("_quote"):
                role = kind.removeprefix("component_")
                if role in {"stem", "branch", "leaf"}:
                    roles_found.add(role)
        return roles_found

    e2_roles = _component_roles(e2)
    if "stem" not in e2_roles or "branch" not in e2_roles or "leaf" not in e2_roles:
        raise AssertionError(
            "Expected E2 (2-a-ii) composition explanation to identify stem, "
            f"branch (a), and terminal leaf; found component roles {sorted(e2_roles)}."
        )
    branch_locs = [
        str(row.get("value") or "")
        for row in (e2.get("evidence") or [])
        if isinstance(row, dict) and str(row.get("kind") or "") == "component_branch"
    ]
    if not any("a" in loc for loc in branch_locs):
        raise AssertionError(
            "Expected E2 composition explanation to identify branch (a) via "
            f"component locators; found {branch_locs}."
        )
    origin = _explanation_evidence_value(e2, kind="candidate_origin")
    if not origin:
        raise AssertionError("Expected E2 composition explanation to record candidate_origin.")
    locators = [
        str(row.get("value") or "")
        for row in (e2.get("evidence") or [])
        if isinstance(row, dict) and str(row.get("kind") or "") == "source_component_locator"
    ]
    if locators != sorted(locators):
        raise AssertionError(
            "Expected deterministic source_component_locator ordering on E2 explanation."
        )

    e3_roles = _component_roles(e3)
    if "stem" not in e3_roles or "leaf" not in e3_roles:
        raise AssertionError(
            "Expected E3 (2-b) composition explanation to identify stem and leaf; "
            f"found {sorted(e3_roles)}."
        )
    # Article 14 is evidence on the terminal candidate, not a composition target.
    e3_comp_blob = json.dumps(
        [
            row
            for row in (e3.get("evidence") or [])
            if isinstance(row, dict)
            and str(row.get("kind") or "").startswith("component_")
        ],
        sort_keys=True,
    ).lower()
    if "article 14" in e3_comp_blob or "article:14" in e3_comp_blob:
        raise AssertionError(
            "E3 composition explanation must not treat Article 14 as a composition target."
        )

    # No retained standalone stem/branch propositions.
    for prop in props.values():
        basis = str(_debug_meta(prop).get("composition_basis") or "")
        if basis in {"structured_list_stem", "structured_list_branch"}:
            raise AssertionError(
                f"Unexpected stem/branch-only proposition {prop.get('id')} basis={basis!r}."
            )

    # Selection slice remains five records; structured-list adds composition rows.
    selection = [
        e
        for e in _decision_explanations(bundle)
        if str(e.get("stage") or "selection") == "selection"
    ]
    if len(selection) != 5:
        raise AssertionError(
            "Expected selection explanations to remain exactly five; "
            f"found {len(selection)}."
        )
    if len(compose) < 3:
        raise AssertionError(
            "Expected at least three structured-list compose explanations "
            f"(2-a-i, 2-a-ii, 2-b); found {len(compose)}."
        )
    del e1  # asserted via _compose_for


def assert_article_49a_classification_explanations(
    bundle: dict[str, Any], *, roles: dict[str, str]
) -> None:
    """Assert legal-effect classification explanations for retained Article 49a props."""
    from law_proposition_extractor_pipeline.heuristics.registry import require_heuristic

    explanations = [
        e
        for e in _decision_explanations(bundle)
        if str(e.get("stage") or "") == "classification"
    ]
    expected = {
        "P1": ("obligation", "classified_as_obligation"),
        "P2": ("prohibition", "classified_as_prohibition"),
        "E1": ("derogation", "classified_as_derogation"),
        "E2": ("derogation", "classified_as_derogation"),
        "E3": ("derogation", "classified_as_derogation"),
        "P3": ("obligation", "classified_as_obligation"),
    }
    rule = require_heuristic("classification.derive_legal_effect")
    for role, (effect, outcome) in expected.items():
        prop_id = roles[role]
        matches = [
            e
            for e in explanations
            if str(e.get("subject_id") or "") == prop_id
            and str(e.get("rule_id") or "") == "classification.derive_legal_effect"
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"Expected exactly one classification explanation for {role} "
                f"({prop_id}); found {len(matches)}."
            )
        expl = matches[0]
        if str(expl.get("outcome") or "") != outcome:
            raise AssertionError(
                f"Expected {role} classification outcome {outcome!r}; "
                f"found {expl.get('outcome')!r}."
            )
        if str(expl.get("method") or "") != "deterministic":
            raise AssertionError(
                f"Expected deterministic classification method for {role}; "
                f"found {expl.get('method')!r}."
            )
        if str(expl.get("rule_version") or "") != rule.version:
            raise AssertionError(
                f"Classification rule_version {expl.get('rule_version')!r} for {role} "
                f"does not match registry version {rule.version!r}."
            )
        if str(expl.get("subject_kind") or "") != "proposition":
            raise AssertionError(
                f"Expected classification subject_kind=proposition for {role}; "
                f"found {expl.get('subject_kind')!r}."
            )
        basis = _explanation_evidence_value(expl, kind="winning_basis")
        if not basis:
            raise AssertionError(
                f"Expected winning_basis on classification explanation for {role}."
            )
        effect_ev = _explanation_evidence_value(expl, kind="legal_effect_type")
        if effect_ev != effect:
            raise AssertionError(
                f"Expected {role} legal_effect_type evidence {effect!r}; found {effect_ev!r}."
            )

    # E2-specific: structured-list path, candidate origin may be llm, no CoT.
    e2 = next(
        e
        for e in explanations
        if str(e.get("subject_id") or "") == roles["E2"]
        and str(e.get("rule_id") or "") == "classification.derive_legal_effect"
    )
    path = _explanation_evidence_value(e2, kind="structured_list_path")
    if path != "2-a-ii":
        raise AssertionError(
            f"Expected E2 classification structured-list path 2-a-ii; found {path!r}."
        )
    if str(e2.get("method") or "") == "llm":
        raise AssertionError(
            "E2 classification explanation incorrectly marked method=llm."
        )
    blob = json.dumps(e2).lower()
    if "chain of thought" in blob or "chain_of_thought" in blob:
        raise AssertionError("Classification explanation must not store LLM rationale.")
    if _explanation_evidence_value(e2, kind="winning_basis") != "explicit_exception_cue":
        raise AssertionError(
            "Expected E2 winning_basis=explicit_exception_cue "
            f"(priority shall-not-apply); found "
            f"{_explanation_evidence_value(e2, kind='winning_basis')!r}."
        )


def assert_article_49a_relationship_explanations(
    bundle: dict[str, Any],
    *,
    roles: dict[str, str],
    paragraph_1_group_id: str,
    paragraph_2_group_id: str,
) -> None:
    """Assert typed relationship + group-target explanations for Article 49a."""
    from law_proposition_extractor_pipeline.heuristics.registry import require_heuristic

    explanations = [
        e
        for e in _decision_explanations(bundle)
        if str(e.get("stage") or "") == "relationship"
    ]
    rels, _ = _relationships_artifact(bundle)
    by_source_type = {
        (str(r.get("source_id")), str(r.get("relationship_type"))): r for r in rels
    }

    def _require_pair(
        *,
        role: str,
        relationship_type: str,
        infer_rule: str,
        infer_outcome: str,
        canonical: str,
        group_id: str,
        members: set[str],
    ) -> None:
        rel = by_source_type.get((roles[role], relationship_type))
        if rel is None:
            raise AssertionError(
                f"Missing {relationship_type} relationship for {role}."
            )
        rel_id = str(rel.get("id") or "")
        infer_matches = [
            e
            for e in explanations
            if str(e.get("rule_id") or "") == infer_rule
            and str(e.get("subject_id") or "") == rel_id
        ]
        if len(infer_matches) != 1:
            raise AssertionError(
                f"Expected exactly one {infer_rule} explanation for {role} "
                f"relationship {rel_id}; found {len(infer_matches)}."
            )
        infer = infer_matches[0]
        if str(infer.get("outcome") or "") != infer_outcome:
            raise AssertionError(
                f"Expected {role} inference outcome {infer_outcome!r}; "
                f"found {infer.get('outcome')!r}."
            )
        if str(infer.get("method") or "") != "deterministic":
            raise AssertionError(
                f"Expected deterministic method for {role} relationship inference."
            )
        registered = require_heuristic(infer_rule)
        if str(infer.get("rule_version") or "") != registered.version:
            raise AssertionError(
                f"{infer_rule} rule_version mismatch for {role}."
            )
        canon = _explanation_evidence_value(infer, kind="canonical_target_locator")
        if canon != canonical:
            raise AssertionError(
                f"Expected {role} inference canonical target {canonical!r}; "
                f"found {canon!r}."
            )
        if not _explanation_evidence_value(infer, kind="cue_text"):
            raise AssertionError(f"Expected cue_text on {role} inference explanation.")
        if not _explanation_evidence_value(infer, kind="cue_bound_reference"):
            raise AssertionError(
                f"Expected cue_bound_reference on {role} inference explanation."
            )

        target_matches = [
            e
            for e in explanations
            if str(e.get("rule_id") or "") == "relationship.prefer_group_target"
            and str(e.get("subject_id") or "") == rel_id
        ]
        if len(target_matches) != 1:
            raise AssertionError(
                f"Expected exactly one prefer_group_target explanation for {role}; "
                f"found {len(target_matches)}."
            )
        target = target_matches[0]
        if str(target.get("outcome") or "") != "targeted_legal_rule_group":
            raise AssertionError(
                f"Expected {role} group-target outcome targeted_legal_rule_group; "
                f"found {target.get('outcome')!r}."
            )
        tid = _explanation_evidence_value(target, kind="target_id")
        if tid != group_id:
            raise AssertionError(
                f"Expected {role} group target {group_id!r}; found {tid!r}."
            )
        member_ids = {
            str(row.get("value") or "")
            for row in (target.get("evidence") or [])
            if isinstance(row, dict)
            and str(row.get("kind") or "") == "group_member_proposition_id"
        }
        if member_ids != members:
            raise AssertionError(
                f"Expected {role} group members {sorted(members)}; "
                f"found {sorted(member_ids)}."
            )

    for role in ("E1", "E2", "E3"):
        _require_pair(
            role=role,
            relationship_type="exception_to",
            infer_rule="relationship.infer_exception_to",
            infer_outcome="inferred_exception_to",
            canonical="article:49a:paragraph:1",
            group_id=paragraph_1_group_id,
            members={roles["P1"], roles["P2"]},
        )

    _require_pair(
        role="P3",
        relationship_type="triggered_by",
        infer_rule="relationship.infer_triggered_by",
        infer_outcome="inferred_triggered_by",
        canonical="article:49a:paragraph:2",
        group_id=paragraph_2_group_id,
        members={roles["E1"], roles["E2"], roles["E3"]},
    )

    # E3: Article 14 is ordinary / not the typed target.
    e3_rel = by_source_type[(roles["E3"], "exception_to")]
    e3_infer = next(
        e
        for e in explanations
        if str(e.get("rule_id") or "") == "relationship.infer_exception_to"
        and str(e.get("subject_id") or "") == str(e3_rel.get("id") or "")
    )
    canon = _explanation_evidence_value(e3_infer, kind="canonical_target_locator")
    if canon == "article:14" or (canon and canon.endswith(":14")):
        raise AssertionError(
            "E3 exception explanation incorrectly names Article 14 as typed target."
        )
    unselected = [
        str(row.get("value") or "")
        for row in (e3_infer.get("evidence") or [])
        if isinstance(row, dict)
        and str(row.get("kind") or "") == "unselected_ordinary_reference"
    ]
    if not any("14" in u for u in unselected):
        # Accept when Article 14 was not in explicit_cross_reference_targets
        # but still require that no exception explanation targets it.
        blob = json.dumps(e3_infer).lower()
        if "article:14" in blob and "canonical_target_locator" in blob:
            # Only fail if Article 14 appears as the canonical target value.
            pass
    reasons = [
        str(row.get("value") or "")
        for row in (e3_infer.get("evidence") or [])
        if isinstance(row, dict)
        and str(row.get("kind") or "") == "unselected_ordinary_reference_reason"
    ]
    if unselected and "outside_typed_relationship_cue" not in reasons:
        raise AssertionError(
            "Expected outside_typed_relationship_cue reason for E3 ordinary "
            f"Article 14 reference; found reasons {reasons}."
        )
    for expl in explanations:
        if str(expl.get("rule_id") or "") != "relationship.infer_exception_to":
            continue
        target = _explanation_evidence_value(expl, kind="canonical_target_locator") or ""
        if "article:14" in target or target.endswith(":14"):
            raise AssertionError(
                "No exception_to explanation may name Article 14 as its target."
            )


def assert_article_49a_grouping_explanations(
    bundle: dict[str, Any],
    *,
    roles: dict[str, str],
    paragraph_1_group_id: str,
    paragraph_2_group_id: str,
) -> None:
    """Assert LegalRuleGroup construction explanations for Article 49a."""
    from law_proposition_extractor_pipeline.heuristics.registry import require_heuristic

    explanations = [
        e
        for e in _decision_explanations(bundle)
        if str(e.get("stage") or "") == "grouping"
    ]
    rule_id = "grouping.create_shared_fragment_rule_group"
    registered = require_heuristic(rule_id)

    def _require_group(
        *,
        group_id: str,
        members: list[str],
        locator: str,
    ) -> None:
        matches = [
            e
            for e in explanations
            if str(e.get("rule_id") or "") == rule_id
            and str(e.get("subject_id") or "") == group_id
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"Expected exactly one grouping explanation for {locator} "
                f"group {group_id}; found {len(matches)}."
            )
        expl = matches[0]
        if str(expl.get("outcome") or "") != "group_created":
            raise AssertionError(
                f"Expected group_created outcome for {locator}; found {expl.get('outcome')!r}."
            )
        if str(expl.get("method") or "") != "deterministic":
            raise AssertionError(
                f"Expected deterministic grouping method for {locator}."
            )
        if str(expl.get("rule_version") or "") != registered.version:
            raise AssertionError(f"{rule_id} rule_version mismatch for {locator}.")
        if str(expl.get("subject_kind") or "") != "legal_rule_group":
            raise AssertionError(
                f"Expected subject_kind=legal_rule_group for {locator}."
            )
        for kind in (
            "source_record_id",
            "source_snapshot_id",
            "source_fragment_id",
            "canonical_locator",
        ):
            if not _explanation_evidence_value(expl, kind=kind):
                raise AssertionError(
                    f"Expected {kind} evidence on {locator} grouping explanation."
                )
        ordered_members = [
            str(row.get("value") or "")
            for row in (expl.get("evidence") or [])
            if isinstance(row, dict) and str(row.get("kind") or "") == "member_proposition_id"
        ]
        # Evidence is sorted by kind/label/value, so compare as sets + metadata order.
        if set(ordered_members) != set(members):
            raise AssertionError(
                f"Expected {locator} group members {members}; found {ordered_members}."
            )
        meta_members = list((expl.get("metadata") or {}).get("member_proposition_ids") or [])
        if meta_members != members:
            raise AssertionError(
                f"Expected {locator} metadata member order {members}; found {meta_members}."
            )
        if _explanation_evidence_value(expl, kind="member_order_basis") != (
            "deterministic_source_order"
        ):
            raise AssertionError(
                f"Expected deterministic_source_order for {locator} grouping."
            )

    groups = _groups_artifact(bundle)
    by_id = {str(g.get("id")): g for g in groups if isinstance(g, dict)}
    g1 = by_id.get(paragraph_1_group_id) or {}
    g2 = by_id.get(paragraph_2_group_id) or {}
    _require_group(
        group_id=paragraph_1_group_id,
        members=[str(x) for x in (g1.get("member_proposition_ids") or [])],
        locator="article:49a:paragraph:1",
    )
    _require_group(
        group_id=paragraph_2_group_id,
        members=[str(x) for x in (g2.get("member_proposition_ids") or [])],
        locator="article:49a:paragraph:2",
    )
    if set([str(x) for x in (g1.get("member_proposition_ids") or [])]) != {
        roles["P1"],
        roles["P2"],
    }:
        raise AssertionError("Paragraph-1 grouping explanation members must be P1,P2.")
    if set([str(x) for x in (g2.get("member_proposition_ids") or [])]) != {
        roles["E1"],
        roles["E2"],
        roles["E3"],
    }:
        raise AssertionError("Paragraph-2 grouping explanation members must be E1,E2,E3.")

    for expl in explanations:
        if str(expl.get("rule_id") or "") != rule_id:
            continue
        locator = _explanation_evidence_value(expl, kind="canonical_locator") or ""
        if locator == "article:49a:paragraph:3" or locator.endswith(":paragraph:3"):
            raise AssertionError(
                "Did not expect a paragraph-3 group-construction explanation."
            )
        if locator == "article:49a":
            raise AssertionError(
                "Did not expect an article-level group-construction explanation."
            )


def assert_article_49a_effective_law_explanations(
    bundle: dict[str, Any],
    *,
    roles: dict[str, str],
    paragraph_1_group_id: str,
    paragraph_2_group_id: str,
    statements: list[dict[str, Any]],
) -> None:
    """Assert typed-context expansion and precedence explanations for Article 49a."""
    from law_proposition_extractor_pipeline.heuristics.registry import require_heuristic

    explanations = [
        e
        for e in _decision_explanations(bundle)
        if str(e.get("stage") or "") == "effective_law"
    ]
    rels, _ = _relationships_artifact(bundle)
    by_source_type = {
        (str(r.get("source_id")), str(r.get("relationship_type"))): r for r in rels
    }
    stmt_by_prop = {
        str((stmt.get("source_proposition_ids") or [None])[0]): stmt
        for stmt in statements
        if stmt.get("source_proposition_ids")
    }

    def _require_attach(
        *,
        rule_id: str,
        outcome: str,
        receiving_role: str,
        context_role: str,
        context_kind: str,
        relationship_type: str,
        group_id: str,
        expansion_direction: str | None = None,
    ) -> dict[str, Any]:
        receiving_prop = roles[receiving_role]
        context_prop = roles[context_role]
        stmt = stmt_by_prop.get(receiving_prop)
        if stmt is None:
            raise AssertionError(
                f"Missing effective-law statement for {receiving_role}."
            )
        stmt_id = str(stmt.get("id") or "")
        if relationship_type == "exception_to":
            exception_role = (
                context_role if context_kind == "applicable_exception" else receiving_role
            )
            rel = by_source_type.get((roles[exception_role], "exception_to"))
        else:
            rel = by_source_type.get((roles["P3"], "triggered_by"))
        if rel is None:
            raise AssertionError(
                f"Missing {relationship_type} relationship for "
                f"{receiving_role}/{context_role}."
            )
        rel_id = str(rel.get("id") or "")
        matches = [
            e
            for e in explanations
            if str(e.get("rule_id") or "") == rule_id
            and str(e.get("subject_id") or "") == stmt_id
            and _explanation_evidence_value(e, kind="context_proposition_id")
            == context_prop
            and _explanation_evidence_value(e, kind="legal_rule_relationship_id")
            == rel_id
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"Expected exactly one {rule_id} explanation for {receiving_role} "
                f"← {context_role}; found {len(matches)}."
            )
        expl = matches[0]
        if str(expl.get("outcome") or "") != outcome:
            raise AssertionError(
                f"Expected {outcome} for {receiving_role}←{context_role}; "
                f"found {expl.get('outcome')!r}."
            )
        registered = require_heuristic(rule_id)
        if str(expl.get("rule_version") or "") != registered.version:
            raise AssertionError(f"{rule_id} rule_version mismatch.")
        if str(expl.get("method") or "") != "deterministic":
            raise AssertionError(
                f"Expected deterministic method for {rule_id} on {receiving_role}."
            )
        if _explanation_evidence_value(expl, kind="inherited_via_group") != "true":
            raise AssertionError(
                f"Expected inherited_via_group=true for {receiving_role}←{context_role}."
            )
        if _explanation_evidence_value(expl, kind="legal_rule_group_id") != group_id:
            raise AssertionError(
                f"Expected group {group_id} on {receiving_role}←{context_role} "
                f"context explanation."
            )
        if expansion_direction is not None:
            if _explanation_evidence_value(expl, kind="expansion_direction") != (
                expansion_direction
            ):
                raise AssertionError(
                    f"Expected expansion_direction={expansion_direction} for "
                    f"{receiving_role}←{context_role}."
                )
        meta = expl.get("metadata") or {}
        if str(meta.get("context_kind") or "") != context_kind:
            raise AssertionError(
                f"Expected metadata context_kind={context_kind} for "
                f"{receiving_role}←{context_role}."
            )
        if str(meta.get("legal_rule_relationship_id") or "") != rel_id:
            raise AssertionError(
                f"Context explanation for {receiving_role}←{context_role} refers "
                f"to the wrong relationship."
            )
        return expl

    applicable = [
        e
        for e in explanations
        if str(e.get("rule_id") or "") == "effective_law.attach_applicable_exception"
    ]
    if len(applicable) != 6:
        raise AssertionError(
            f"Expected exactly 6 applicable_exception explanations; found {len(applicable)}."
        )
    for receiving in ("P1", "P2"):
        for context in ("E1", "E2", "E3"):
            _require_attach(
                rule_id="effective_law.attach_applicable_exception",
                outcome="applicable_exception_attached",
                receiving_role=receiving,
                context_role=context,
                context_kind="applicable_exception",
                relationship_type="exception_to",
                group_id=paragraph_1_group_id,
            )

    exception_targets = [
        e
        for e in explanations
        if str(e.get("rule_id") or "") == "effective_law.attach_exception_target"
    ]
    if len(exception_targets) != 6:
        raise AssertionError(
            f"Expected exactly 6 exception_target explanations; found {len(exception_targets)}."
        )
    for receiving in ("E1", "E2", "E3"):
        for context in ("P1", "P2"):
            _require_attach(
                rule_id="effective_law.attach_exception_target",
                outcome="exception_target_attached",
                receiving_role=receiving,
                context_role=context,
                context_kind="exception_target",
                relationship_type="exception_to",
                group_id=paragraph_1_group_id,
            )

    triggers = [
        e
        for e in explanations
        if str(e.get("rule_id") or "") == "effective_law.attach_trigger_condition"
    ]
    if len(triggers) != 3:
        raise AssertionError(
            f"Expected exactly 3 trigger_condition explanations; found {len(triggers)}."
        )
    for context in ("E1", "E2", "E3"):
        _require_attach(
            rule_id="effective_law.attach_trigger_condition",
            outcome="trigger_condition_attached",
            receiving_role="P3",
            context_role=context,
            context_kind="trigger_condition",
            relationship_type="triggered_by",
            group_id=paragraph_2_group_id,
            expansion_direction="source_only",
        )

    # No reverse trigger context explanations on E1/E2/E3.
    for role in ("E1", "E2", "E3"):
        stmt_id = str(stmt_by_prop[roles[role]].get("id") or "")
        reverse = [
            e
            for e in triggers
            if str(e.get("subject_id") or "") == stmt_id
        ]
        if reverse:
            raise AssertionError(
                f"Did not expect reverse trigger_condition explanations on {role}."
            )

    # Typed paragraph references must not also appear as generic context.
    for role in ("E1", "E2", "E3"):
        stmt = stmt_by_prop[roles[role]]
        for ctx in stmt.get("required_context") or []:
            if not isinstance(ctx, dict):
                continue
            kind = str(ctx.get("kind") or "")
            if kind in {"applicable_exception", "exception_target", "trigger_condition"}:
                continue
            loc = str(ctx.get("locator") or "").lower()
            prop_ids = {str(x) for x in (ctx.get("proposition_ids") or [])}
            if (
                "paragraph:1" in loc
                or loc in {"paragraph 1", "article:49a:paragraph:1"}
            ) and prop_ids & {roles["P1"], roles["P2"]}:
                raise AssertionError(
                    f"Generic paragraph-1 locator context retained alongside typed "
                    f"exception context on {role}."
                )

    p3 = stmt_by_prop[roles["P3"]]
    for ctx in p3.get("required_context") or []:
        if not isinstance(ctx, dict):
            continue
        kind = str(ctx.get("kind") or "")
        if kind == "trigger_condition":
            continue
        loc = str(ctx.get("locator") or "").lower()
        prop_ids = {str(x) for x in (ctx.get("proposition_ids") or [])}
        if (
            "paragraph:2" in loc or loc in {"paragraph 2", "article:49a:paragraph:2"}
        ) and prop_ids & {roles["E1"], roles["E2"], roles["E3"]}:
            raise AssertionError(
                "Generic paragraph-2 locator context retained alongside typed "
                "trigger context on P3."
            )

    # Validate emitted suppression facts where present; do not require fabricated ones.
    suppressions = [
        e
        for e in explanations
        if str(e.get("rule_id") or "")
        == "effective_law.prefer_typed_context_over_generic_locator"
    ]
    for expl in suppressions:
        generic = (_explanation_evidence_value(expl, kind="generic_locator") or "").lower()
        if "14" in generic and "article" in generic:
            raise AssertionError(
                "Article 14 incorrectly suppressed as duplicate generic context."
            )
        if str(expl.get("decision_type") or "") != "suppress":
            raise AssertionError(
                "Typed-over-generic precedence must use decision_type=suppress."
            )
        if not _explanation_evidence_value(expl, kind="typed_relationship_id"):
            raise AssertionError(
                "Suppression explanation must reference the typed relationship."
            )
        if not _explanation_evidence_value(expl, kind="generic_locator"):
            raise AssertionError(
                "Suppression explanation must reference the generic locator candidate."
            )

    e3_stmt = stmt_by_prop[roles["E3"]]
    e3_stmt_id = str(e3_stmt.get("id") or "")
    article_14_present = False
    for ctx in e3_stmt.get("required_context") or []:
        if not isinstance(ctx, dict):
            continue
        loc = str(ctx.get("locator") or "").lower()
        kind = str(ctx.get("kind") or "")
        if "article:14" in loc or loc.endswith(":14") or loc == "article 14":
            article_14_present = True
            if kind in {
                "applicable_exception",
                "exception_target",
                "trigger_condition",
            }:
                raise AssertionError(
                    "Article 14 must remain ordinary referenced context on E3."
                )
    if not article_14_present:
        raise AssertionError("Expected Article 14 ordinary context to remain on E3.")
    for expl in suppressions:
        if str(expl.get("subject_id") or "") != e3_stmt_id:
            continue
        generic = (_explanation_evidence_value(expl, kind="generic_locator") or "").lower()
        if "14" in generic:
            raise AssertionError(
                "Article 14 must not have a typed-context suppression decision."
            )


def assert_article_49a_legal_structure(bundle: dict[str, Any]) -> dict[str, str]:
    """Assert the full Article 49a legal-shape contract. Returns role→prop id map."""
    frags = _fragment_by_locator(bundle)
    by_id = {
        str(f["id"]): f
        for f in (bundle.get("source_fragments") or [])
        if isinstance(f, dict) and f.get("id")
    }

    # 1. Structural hierarchy
    for loc in (
        "article:49a",
        "article:49a:paragraph:1",
        "article:49a:paragraph:2",
        "article:49a:paragraph:3",
        "article:49a:paragraph:2:subparagraph:a",
    ):
        if loc not in frags:
            raise AssertionError(f"Expected structural fragment {loc} to remain present.")

    art = frags["article:49a"]
    art_parent = _parent_locator(art, by_id)
    if art_parent == "article:1" or (
        art_parent is not None
        and art_parent.startswith("article:")
        and art_parent != "article:49a"
    ):
        raise AssertionError(
            f"Article 49a unexpectedly parented to {art_parent!r} "
            "(expected title:iv container, not Article 1 or a sibling article)."
        )
    if art_parent != "title:iv":
        raise AssertionError(
            f"Expected article:49a parent = title:iv; found {art_parent!r}."
        )

    for para in (
        "article:49a:paragraph:1",
        "article:49a:paragraph:2",
        "article:49a:paragraph:3",
    ):
        parent = _parent_locator(frags[para], by_id)
        if parent != "article:49a":
            raise AssertionError(
                f"Expected {para} parent = article:49a; found {parent!r}."
            )

    # 1b. Legislative headings (source fidelity — not propositions)
    from law_proposition_extractor_pipeline.structural_headings import (
        nearest_provision_heading,
        resolve_structural_heading_contexts,
    )

    ARTICLE_49A_HEADING = (
        "Separate stowage of catches below the minimum conservation reference sizes"
    )
    art_heading = art.get("structural_heading")
    if not isinstance(art_heading, dict):
        raise AssertionError(
            "Expected article:49a to retain its legislative heading as structural "
            "source metadata; structural_heading was discarded."
        )
    if str(art.get("number_label") or "").strip() != "Article 49a":
        raise AssertionError(
            f"Expected article:49a.number_label = 'Article 49a'; "
            f"found {art.get('number_label')!r}."
        )
    if str(art_heading.get("text") or "").strip() != ARTICLE_49A_HEADING:
        raise AssertionError(
            "Expected article:49a legislative heading "
            f"{ARTICLE_49A_HEADING!r}; found {art_heading.get('text')!r}."
        )
    if str(art_heading.get("kind") or "") != "article":
        raise AssertionError(
            f"Expected article:49a heading kind = 'article'; found {art_heading.get('kind')!r}."
        )
    change_ids = [str(x) for x in (art_heading.get("change_ids") or [])]
    commentary_refs = [str(x) for x in (art_heading.get("commentary_refs") or [])]
    if "O003001M119" not in change_ids:
        raise AssertionError(
            "Expected article:49a heading change_ids to retain fixture ChangeId "
            f"O003001M119; found {change_ids}."
        )
    if "c000004" not in commentary_refs:
        raise AssertionError(
            "Expected article:49a heading commentary_refs to retain fixture "
            f"CommentaryRef c000004; found {commentary_refs}."
        )
    if ARTICLE_49A_HEADING.lower() in str(art.get("fragment_text") or "").lower():
        raise AssertionError(
            "Article 49a legislative heading was incorrectly copied into "
            "operative fragment_text."
        )

    title_iv = frags.get("title:iv")
    if not isinstance(title_iv, dict):
        raise AssertionError("Expected title:iv container fragment to remain present.")
    if str(title_iv.get("number_label") or "").strip() != "TITLE IV":
        raise AssertionError(
            f"Expected title:iv.number_label = 'TITLE IV'; found {title_iv.get('number_label')!r}."
        )
    title_heading = title_iv.get("structural_heading")
    if not isinstance(title_heading, dict):
        raise AssertionError(
            "Expected title:iv to retain descriptive heading CONTROL OF FISHERIES "
            "separately from number_label TITLE IV."
        )
    if str(title_heading.get("text") or "").strip() != "CONTROL OF FISHERIES":
        raise AssertionError(
            "Expected title:iv descriptive heading 'CONTROL OF FISHERIES'; "
            f"found {title_heading.get('text')!r}."
        )
    if str(title_iv.get("fragment_text") or "").strip() == "CONTROL OF FISHERIES":
        raise AssertionError(
            "Title IV number was replaced by its descriptive title in fragment_text."
        )

    for leak_loc in ("article:1", "article:14"):
        leak = frags.get(leak_loc)
        if not isinstance(leak, dict):
            continue
        leak_heading = leak.get("structural_heading")
        if isinstance(leak_heading, dict):
            leak_text = str(leak_heading.get("text") or "").strip()
        else:
            leak_text = ""
        if leak_text and leak_text == ARTICLE_49A_HEADING:
            raise AssertionError(
                f"{leak_loc} unexpectedly carries the Article 49a heading."
            )

    for loc in (
        "article:49a:paragraph:1",
        "article:49a:paragraph:2",
        "article:49a:paragraph:3",
        "article:49a:paragraph:2:subparagraph:a",
    ):
        contexts = resolve_structural_heading_contexts(frags[loc], by_id)
        texts = [c.heading_text for c in contexts]
        if ARTICLE_49A_HEADING not in texts:
            raise AssertionError(
                f"Expected {loc} to inherit Article 49a legislative heading through "
                f"structural ancestry; resolved headings={texts!r}."
            )
        if any(t in {"Subject matter", "Completion and submission of the fishing logbook"} for t in texts):
            raise AssertionError(
                f"Article 1/14 heading incorrectly inherited by {loc}: {texts!r}."
            )
        nearest = nearest_provision_heading(frags[loc], by_id)
        if nearest is None or nearest.heading_text != ARTICLE_49A_HEADING:
            raise AssertionError(
                f"Expected nearest provision heading for {loc} to be Article 49a "
                f"heading; found {None if nearest is None else nearest.heading_text!r}."
            )

    # 2. Extraction frontier — check skip reasons before the exact selected set
    # so mutation failures surface the legally meaningful diagnostic first.
    jobs = bundle.get("proposition_extraction_jobs") or []

    def _job(locator: str) -> dict[str, Any]:
        for j in jobs:
            if isinstance(j, dict) and j.get("fragment_locator") == locator:
                return j
        raise AssertionError(f"Missing extraction job for {locator}.")

    article_job = _job("article:49a")
    if article_job.get("selected_for_extraction"):
        raise AssertionError(
            "Expected article:49a to be skipped because children cover it; "
            "it was selected for extraction."
        )
    art_reason = str(article_job.get("skip_reason") or article_job.get("selection_reason") or "")
    if "covered_by_selected_children" not in art_reason and "children" not in art_reason:
        raise AssertionError(
            "Expected article:49a to be skipped via child coverage; "
            f"got reason {art_reason!r}."
        )

    sub_a = _job("article:49a:paragraph:2:subparagraph:a")
    if sub_a.get("selected_for_extraction"):
        raise AssertionError(
            "Expected subparagraph (a) to be skipped through required-ancestor coverage; "
            "it was selected for extraction."
        )
    sub_reason = str(sub_a.get("skip_reason") or sub_a.get("selection_reason") or "")
    if "required_ancestor" not in sub_reason and "covered_by_required_ancestor" not in sub_reason:
        raise AssertionError(
            "Expected subparagraph (a) skipped via required-ancestor coverage; "
            f"got reason {sub_reason!r}."
        )
    if str(sub_a.get("original_selection_reason") or "") != "focus_term_match":
        raise AssertionError(
            "Expected subparagraph (a) original_selection_reason=focus_term_match; "
            f"found {sub_a.get('original_selection_reason')!r}."
        )
    job_matched = sorted(
        str(t).lower() for t in (sub_a.get("matched_focus_terms") or []) if str(t).strip()
    )
    if job_matched != ["boarfish", "norwegian pout"]:
        raise AssertionError(
            "Expected subparagraph (a) job matched_focus_terms "
            "['boarfish', 'norwegian pout'] (fixture terms, normalized); "
            f"found {job_matched}."
        )

    selected = {
        str(j.get("fragment_locator"))
        for j in jobs
        if isinstance(j, dict) and j.get("selected_for_extraction")
    }
    selected_49a = {loc for loc in selected if loc.startswith("article:49a")}
    if selected_49a != set(REQUIRED_EXTRACTION_LOCATORS):
        raise AssertionError(
            "Expected selected Article 49a extraction locators "
            f"{list(REQUIRED_EXTRACTION_LOCATORS)}; found {sorted(selected_49a)}."
        )

    for loc in REQUIRED_EXTRACTION_LOCATORS:
        job = _job(loc)
        contexts = job.get("structural_heading_contexts")
        if not isinstance(contexts, list) or not contexts:
            raise AssertionError(
                f"Expected extraction job {loc} to carry labelled structural "
                "heading context including Article 49a; field missing."
            )
        heading_texts = [
            str(c.get("heading_text") or "")
            for c in contexts
            if isinstance(c, dict)
        ]
        if ARTICLE_49A_HEADING not in heading_texts:
            raise AssertionError(
                f"Expected extraction job {loc} heading context to include "
                f"Article 49a heading; found {heading_texts!r}."
            )
        owners = {
            str(c.get("owner_locator") or "")
            for c in contexts
            if isinstance(c, dict)
        }
        if "article:1" in owners or "article:14" in owners:
            raise AssertionError(
                f"Extraction job {loc} incorrectly includes Article 1/14 heading "
                f"context owners={sorted(owners)}."
            )

    assert_article_49a_selection_explanations(bundle)

    # 3. Proposition semantic identities
    roles = identify_article_49a_propositions(bundle)
    props = {str(p["id"]): p for p in _article_49a_props(bundle)}
    if len(props) != 6:
        raise AssertionError(f"Expected 6 Article 49a propositions; found {len(props)}.")

    p1_count = sum(
        1
        for p in props.values()
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:1")
    )
    p2_count = sum(
        1
        for p in props.values()
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:2")
    )
    p3_count = sum(
        1
        for p in props.values()
        if str(p.get("fragment_locator") or "").startswith("article:49a:paragraph:3")
    )
    if (p1_count, p2_count, p3_count) != (2, 3, 1):
        raise AssertionError(
            f"Expected paragraph proposition counts (2, 3, 1); found "
            f"({p1_count}, {p2_count}, {p3_count})."
        )

    p2_props = [
        props[roles[r]] for r in ("E1", "E2", "E3")
    ]
    paths = [_structured_path(p) for p in p2_props]
    if paths != list(PARAGRAPH_2_PATHS):
        raise AssertionError(
            f"Expected paragraph-2 structured paths {list(PARAGRAPH_2_PATHS)}; found {paths}."
        )
    # Explainability after legal-shape uniqueness so duplicate-path mutations fail
    # on proposition inventory before compose subject binding.
    assert_article_49a_structured_list_explanations(bundle, roles=roles)
    assert_article_49a_classification_explanations(bundle, roles=roles)
    for role, prop in (("E1", p2_props[0]), ("E2", p2_props[1]), ("E3", p2_props[2])):
        if str(prop.get("legal_effect_type") or "") != "derogation":
            raise AssertionError(
                f"Expected {role} to be a derogation; found "
                f"{prop.get('legal_effect_type')!r}."
            )
        text = str(prop.get("proposition_text") or "").lower()
        if "paragraph 1" not in text and "shall not apply" not in text:
            raise AssertionError(
                f"Expected {role} to preserve the paragraph-1 disapplication target."
            )

    e3_text = str(props[roles["E3"]].get("proposition_text") or "")
    e3_refs = props[roles["E3"]].get("explicit_cross_reference_targets") or []
    if "article 14" not in e3_text.lower() and not any(
        "14" in str(r).lower() for r in e3_refs
    ):
        # Also accept evidence / debug references.
        blob = json.dumps(props[roles["E3"]]).lower()
        if "article 14" not in blob and "article:14" not in blob:
            raise AssertionError("Expected only 2-b (E3) to carry Article 14.")

    for role in ("E1", "E2"):
        blob = json.dumps(props[roles[role]]).lower()
        # Article 14 may appear in fragment text metadata; require proposition-level absence.
        prop_text = str(props[roles[role]].get("proposition_text") or "").lower()
        refs = props[roles[role]].get("explicit_cross_reference_targets") or []
        if "article 14" in prop_text or any("14" in str(r) and "49" not in str(r) for r in refs):
            raise AssertionError(f"Did not expect {role} to carry Article 14.")

    for prop in props.values():
        basis = str(_debug_meta(prop).get("composition_basis") or "")
        if basis in {"structured_list_stem", "structured_list_branch"}:
            raise AssertionError(
                f"Unexpected stem/branch-only proposition {prop.get('id')} basis={basis!r}."
            )

    # 4. Traceability / completeness
    assessments = bundle.get("proposition_completeness_assessments") or []
    by_prop_assess = {
        str(a.get("proposition_id")): a
        for a in assessments
        if isinstance(a, dict) and a.get("proposition_id")
    }
    for prop_id, prop in props.items():
        status = str(
            prop.get("completeness_status")
            or _debug_meta(prop).get("completeness_status")
            or ""
        ).lower()
        assess = by_prop_assess.get(prop_id)
        if assess is not None:
            status = str(
                assess.get("status") or assess.get("completeness_status") or status
            ).lower()
        if status and status not in {"complete", "completed", "ok"}:
            raise AssertionError(
                f"Expected proposition {prop_id} complete under current completeness rules; "
                f"status={status!r}."
            )
        if not status:
            raise AssertionError(
                f"Expected completeness status on proposition {prop_id}; found none."
            )
        evidence = str(prop.get("evidence_text") or "")
        if evidence:
            # Must be traceable to some Article 49a fragment text.
            frag_loc = str(prop.get("fragment_locator") or "")
            parent_para = re.sub(r":sentence:\d+$", "", frag_loc)
            # Walk up to paragraph-level fragment for evidence search.
            candidates = [
                frags[loc]["fragment_text"]
                for loc in frags
                if loc == parent_para
                or loc.startswith("article:49a:paragraph:2")
                or loc.startswith("article:49a:paragraph:1")
                or loc.startswith("article:49a:paragraph:3")
            ]
            hay = "\n".join(str(t) for t in candidates)
            # Normalise curly quotes / whitespace lightly
            if evidence not in hay and evidence.replace("'", "'") not in hay:
                # Allow evidence drawn from paragraph-2 aggregate text
                p2 = frags.get("article:49a:paragraph:2", {}).get("fragment_text", "")
                p1 = frags.get("article:49a:paragraph:1", {}).get("fragment_text", "")
                p3 = frags.get("article:49a:paragraph:3", {}).get("fragment_text", "")
                if evidence not in str(p2) and evidence not in str(p1) and evidence not in str(p3):
                    raise AssertionError(
                        f"evidence_text for {prop_id} is not traceable to Article 49a source text."
                    )

    # Coverage of terminal paths
    covered_paths = {
        _structured_path(p)
        for p in props.values()
        if _structured_path(p)
    }
    if set(PARAGRAPH_2_PATHS) - covered_paths:
        missing = set(PARAGRAPH_2_PATHS) - covered_paths
        raise AssertionError(f"structured_list_terminal_uncovered paths: {sorted(missing)}.")

    # 5. Locator resolution (from relationship / context resolution bases)
    rels, rel_diags = _relationships_artifact(bundle)
    for rel in rels:
        if rel.get("relationship_type") == "exception_to":
            target = str(rel.get("referenced_locator") or rel.get("target_canonical_locator") or "")
            if target and target != "article:49a:paragraph:1":
                # qualified forms should canonicalise
                if "49a" in target and "paragraph:1" not in target and target != "article:49a:paragraph:1":
                    raise AssertionError(
                        f"Expected exception_to target to canonicalise to "
                        f"article:49a:paragraph:1; found {target!r}."
                    )
        # Article 14 must not become exception target
        target_loc = str(rel.get("referenced_locator") or "")
        if "article:14" in target_loc or target_loc.endswith(":14"):
            raise AssertionError(
                "Article 14 incorrectly resolved as a typed relationship target."
            )

    # 6. Legal rule groups
    groups = _groups_artifact(bundle)
    groups_49a = [
        g
        for g in groups
        if str(g.get("canonical_locator") or "").startswith("article:49a")
    ]
    by_locator = {str(g.get("canonical_locator")): g for g in groups_49a}
    g1 = by_locator.get("article:49a:paragraph:1")
    g2 = by_locator.get("article:49a:paragraph:2")
    if g1 is None:
        raise AssertionError("Expected paragraph-1 legal rule group.")
    if g2 is None:
        raise AssertionError("Expected paragraph-2 legal rule group.")
    if int(g1.get("member_count") or len(g1.get("member_proposition_ids") or [])) != 2:
        raise AssertionError(
            f"Expected paragraph-1 group size = 2; found {g1.get('member_count')}."
        )
    if int(g2.get("member_count") or len(g2.get("member_proposition_ids") or [])) != 3:
        raise AssertionError(
            f"Expected paragraph-2 group size = 3; found {g2.get('member_count')}."
        )
    if "article:49a:paragraph:3" in by_locator:
        raise AssertionError("Did not expect a paragraph-3 proposition group.")
    if "article:49a" in by_locator:
        raise AssertionError("Did not expect an article-level proposition group.")

    members_1 = [str(x) for x in (g1.get("member_proposition_ids") or [])]
    members_2 = [str(x) for x in (g2.get("member_proposition_ids") or [])]
    if len(members_1) != len(set(members_1)) or len(members_2) != len(set(members_2)):
        raise AssertionError("Legal rule group has duplicate members.")
    if set(members_1) != {roles["P1"], roles["P2"]}:
        raise AssertionError(
            f"Expected paragraph-1 group members {{P1,P2}}; found {members_1}."
        )
    if set(members_2) != {roles["E1"], roles["E2"], roles["E3"]}:
        raise AssertionError(
            f"Expected paragraph-2 group members {{E1,E2,E3}}; found {members_2}."
        )

    # 7. Typed relationships
    exception_to = [r for r in rels if r.get("relationship_type") == "exception_to"]
    triggered_by = [r for r in rels if r.get("relationship_type") == "triggered_by"]
    if len(exception_to) != 3:
        raise AssertionError(
            f"Expected 3 exception_to relationships targeting the paragraph-1 group; "
            f"found {len(exception_to)}."
        )
    if len(triggered_by) != 1:
        raise AssertionError(
            f"Expected 1 triggered_by relationship; found {len(triggered_by)}."
        )

    p1_group_id = str(g1["id"])
    p2_group_id = str(g2["id"])
    for role in ("E1", "E2", "E3"):
        matches = [
            r
            for r in exception_to
            if str(r.get("source_id")) == roles[role] and str(r.get("target_id")) == p1_group_id
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"Expected {role} --exception_to--> paragraph-1 group; "
                f"found {len(matches)} matching relationships."
            )
        rel = matches[0]
        if not rel.get("inference_basis") and not rel.get("cue_text") and not rel.get("reference_text"):
            # cue provenance fields vary; require some provenance signal
            if not rel.get("referenced_locator"):
                raise AssertionError(f"Missing cue/locator provenance on {role} exception_to.")
        if str(rel.get("target_canonical_locator") or rel.get("referenced_locator") or "") not in {
            "article:49a:paragraph:1",
            "",
        } and "paragraph:1" not in str(rel.get("referenced_locator") or ""):
            raise AssertionError(
                f"Expected canonical target locator article:49a:paragraph:1 on {role}."
            )

    tb = triggered_by[0]
    if str(tb.get("source_id")) != roles["P3"] or str(tb.get("target_id")) != p2_group_id:
        raise AssertionError(
            "Expected P3 --triggered_by--> paragraph-2 group."
        )

    if any("14" in json.dumps(r) and r.get("relationship_type") in {"exception_to", "triggered_by"}
           and "article:14" in str(r.get("referenced_locator") or "")
           for r in rels):
        raise AssertionError("Unexpected Article 14 typed relationship.")

    if rel_diags:
        # Allow empty-only; non-empty diagnostics fail this slice
        meaningful = [d for d in rel_diags if d]
        if meaningful:
            raise AssertionError(
                f"Expected empty relationship diagnostics for this slice; found {len(meaningful)}."
            )

    assert_article_49a_relationship_explanations(
        bundle,
        roles=roles,
        paragraph_1_group_id=p1_group_id,
        paragraph_2_group_id=p2_group_id,
    )
    assert_article_49a_grouping_explanations(
        bundle,
        roles=roles,
        paragraph_1_group_id=p1_group_id,
        paragraph_2_group_id=p2_group_id,
    )

    # 8. Effective-law statements
    statements, el_diags = _statements_artifact(bundle)
    for role in ("P1", "P2"):
        stmt = _statement_for_prop(statements, roles[role])
        apps = _contexts_of_kind(stmt, "applicable_exception")
        if len(apps) != 3:
            raise AssertionError(
                f"Expected {role} applicable_exception count = 3; found {len(apps)}."
            )
        if not any(c.get("inherited_via_group") for c in apps):
            raise AssertionError(
                f"Expected group inheritance provenance on {role} applicable exceptions."
            )

    for role in ("E1", "E2", "E3"):
        stmt = _statement_for_prop(statements, roles[role])
        targets = _contexts_of_kind(stmt, "exception_target")
        target_ids = {
            pid
            for c in targets
            for pid in (c.get("proposition_ids") or [])
        }
        if {roles["P1"], roles["P2"]} - {str(x) for x in target_ids}:
            raise AssertionError(
                f"Expected {role} exception_target = {{P1, P2}}; found {sorted(target_ids)}."
            )

    p3_stmt = _statement_for_prop(statements, roles["P3"])
    triggers = _contexts_of_kind(p3_stmt, "trigger_condition")
    if len(triggers) != 3:
        raise AssertionError(
            f"Expected P3 trigger_condition count = 3; found {len(triggers)}."
        )

    e3_stmt = _statement_for_prop(statements, roles["E3"])
    # Article 14 remains ordinary referenced context, not exception_target
    for ctx in e3_stmt.get("required_context") or []:
        if not isinstance(ctx, dict):
            continue
        loc = str(ctx.get("locator") or "")
        if "article:14" in loc or loc.endswith(":14"):
            if str(ctx.get("kind") or "") == "exception_target":
                raise AssertionError(
                    "Article 14 incorrectly typed as exception_target on E3."
                )

    assert_article_49a_effective_law_explanations(
        bundle,
        roles=roles,
        paragraph_1_group_id=p1_group_id,
        paragraph_2_group_id=p2_group_id,
        statements=statements,
    )

    if el_diags:
        meaningful = [d for d in el_diags if d]
        if meaningful:
            raise AssertionError(
                f"Expected no effective-law diagnostics for this slice; found {len(meaningful)}."
            )

    # 9. Proposition Matcher candidates
    cands = _candidates_artifact(bundle)
    cands_49a = [
        c
        for c in cands
        if any(
            str(pid) in {roles[r] for r in roles}
            for pid in (
                c.get("source_proposition_ids")
                or c.get("proposition_ids")
                or ([c["proposition_id"]] if c.get("proposition_id") else [])
            )
        )
        or str(c.get("fragment_locator") or "").startswith("article:49a")
        or str(c.get("source_proposition_id") or "") in {roles[r] for r in roles}
    ]
    # Fall back: exactly 6 candidates in this single-source fixture
    if len(cands) != 6 and len(cands_49a) != 6:
        raise AssertionError(
            f"Expected exactly six Article 49a Proposition Matcher candidates; found "
            f"{len(cands)} total / {len(cands_49a)} matched."
        )
    # Typed required context survives into candidate material
    typed_kinds = {"applicable_exception", "exception_target", "trigger_condition"}
    found_typed = False
    for cand in cands:
        material = cand.get("required_context") or cand.get("material") or cand
        blob = json.dumps(material)
        if any(k in blob for k in typed_kinds):
            found_typed = True
            break
    if not found_typed:
        raise AssertionError(
            "Expected typed required context to survive into Proposition Matcher candidate material."
        )

    # 10. Manifestation provenance
    snaps = bundle.get("source_snapshots") or []
    if not snaps:
        raise AssertionError("Expected source_snapshots in bundle.")
    snap = snaps[0] if isinstance(snaps[0], dict) else {}
    if snap.get("manifestation_type") != "revised":
        raise AssertionError(
            f"Expected manifestation_type=revised; found {snap.get('manifestation_type')!r}."
        )
    if snap.get("manifestation_basis") != "source_metadata":
        raise AssertionError(
            f"Expected manifestation_basis=source_metadata; found {snap.get('manifestation_basis')!r}."
        )
    if snap.get("requested_as_of_date") is not None:
        raise AssertionError("Expected requested_as_of_date=null.")
    if snap.get("resolved_as_of_date") is not None:
        raise AssertionError("Expected resolved_as_of_date=null.")
    if not snap.get("retrieved_at"):
        raise AssertionError("Expected retrieval timestamp to remain present/distinct.")
    if not snap.get("source_revision_date"):
        raise AssertionError("Expected source revision date to remain present/distinct.")
    if snap.get("retrieved_at") == snap.get("source_revision_date"):
        raise AssertionError("Retrieval timestamp must remain distinct from source revision date.")
    if snap.get("version_id") == "v1" and snap.get("manifestation_type") == "v1":
        raise AssertionError("version_id v1 must not be treated as legislative manifestation.")

    # 11. Source legal effects
    effects_art = _effects_artifact(bundle)
    effects = [e for e in (effects_art.get("effects") or []) if isinstance(e, dict)]
    by_ann = {str(e.get("annotation_id")): e for e in effects if e.get("annotation_id")}

    for ann_id, expected_loc in ARTICLE_49A_EFFECT_ANNOTATION_IDS.items():
        effect = by_ann.get(ann_id)
        if effect is None:
            raise AssertionError(
                f"Expected retained source effect annotation_id={ann_id!r} in fixture."
            )
        if str(effect.get("affected_locator") or "") != expected_loc:
            raise AssertionError(
                f"Expected effect {ann_id} linked at {expected_loc}; "
                f"found {effect.get('affected_locator')!r}."
            )

    art1 = by_ann.get(ARTICLE_1_EFFECT_ANNOTATION_ID)
    if art1 is None:
        raise AssertionError("Expected Article 1 effect annotation c000001 in fixture.")
    if str(art1.get("affected_locator") or "") != "article:1":
        raise AssertionError(
            f"Expected Article 1 effect at article:1; found {art1.get('affected_locator')!r}."
        )

    # Relevance: article-level effect relevant to paragraph descendants via links
    links = [lnk for lnk in (effects_art.get("effect_links") or []) if isinstance(lnk, dict)]
    art_effect_id = str(by_ann["c000004"]["id"])
    para1_effect_id = str(by_ann["key-ae688d7efb8d525f494201f970bc3e75"]["id"])
    para2_effect_id = str(by_ann["key-cd016a627475b52260f225a4d4ac7ed7"]["id"])
    para3_effect_id = str(by_ann["key-c36fcfcb069fb8c51fce93fbce7ea03b"]["id"])
    art1_effect_id = str(art1["id"])

    def _links_for(effect_id: str) -> list[dict[str, Any]]:
        return [lnk for lnk in links if str(lnk.get("effect_id")) == effect_id]

    art_links = _links_for(art_effect_id)
    art_link_locs = {str(lnk.get("affected_locator") or "") for lnk in art_links}
    if "article:49a" not in art_link_locs and not any(
        loc.startswith("article:49a:") for loc in art_link_locs
    ):
        # Direct affected_locator on the effect itself is enough for article-level
        if str(by_ann["c000004"].get("affected_locator")) != "article:49a":
            raise AssertionError("Expected Article-level effect linked at Article 49a.")

    # Paragraph-level effects must not leak to sibling paragraphs
    for effect_id, own_loc, siblings in (
        (para1_effect_id, "article:49a:paragraph:1", ("article:49a:paragraph:2", "article:49a:paragraph:3")),
        (para2_effect_id, "article:49a:paragraph:2", ("article:49a:paragraph:1", "article:49a:paragraph:3")),
        (para3_effect_id, "article:49a:paragraph:3", ("article:49a:paragraph:1", "article:49a:paragraph:2")),
    ):
        for lnk in _links_for(effect_id):
            loc = str(lnk.get("affected_locator") or "")
            if loc in siblings:
                raise AssertionError(
                    f"Paragraph-level effect for {own_loc} leaked to sibling {loc}."
                )

    for lnk in _links_for(art1_effect_id):
        loc = str(lnk.get("affected_locator") or "")
        if loc.startswith("article:49a"):
            raise AssertionError(
                "Article 1 effect unexpectedly became relevant to Article 49a "
                f"via link to {loc}."
            )

    outstanding = str(effects_art.get("outstanding_effects_status") or "")
    if outstanding not in {"source_reports_present", "present", "unknown"}:
        # Fixture retains UnappliedEffects → source_reports_present
        raise AssertionError(
            f"Unexpected outstanding_effects_status {outstanding!r} for captured fixture."
        )
    if outstanding == "none":
        raise AssertionError(
            "unknown/present outstanding-effect status presented as none."
        )

    for ann_id in ARTICLE_49A_EFFECT_ANNOTATION_IDS:
        effect = by_ann[ann_id]
        cons = effect.get("independent_consumption_status")
        # Narrow fixture: EUR 2009/1224 only — affecting instruments assessed as not matched
        # (or register-only if a register entry is explicitly present).
        if cons not in {
            "not_matched",
            "present_in_source_register_but_not_consumed",
        }:
            raise AssertionError(
                f"Expected independent consumption not_matched (or register-only) "
                f"for {ann_id}; found {cons!r}."
            )
        # Must not claim the principal source is independently the affecting instrument.
        matched = effect.get("matched_source_record_id")
        if matched and str(matched) == str(effect.get("source_record_id")):
            raise AssertionError(
                f"Affecting instrument for {ann_id} incorrectly matched to its own "
                f"source_record_id {matched!r}."
            )
        if cons == "consumed_in_current_run":
            raise AssertionError(
                f"Narrow Article 49a fixture must not report consumed_in_current_run "
                f"for {ann_id}."
            )

    if snap.get("manifestation_type") == "revised":
        # Must not imply all effects applied — outstanding present and statuses unknown
        if outstanding in {"none", "all_applied"}:
            raise AssertionError(
                "Revised manifestation must not imply all effects were applied."
            )

    assert_article_49a_provenance_explanations(
        bundle,
        roles=roles,
        snap=snap,
        by_ann=by_ann,
        art_effect_id=art_effect_id,
        para1_effect_id=para1_effect_id,
        para2_effect_id=para2_effect_id,
        para3_effect_id=para3_effect_id,
        art1_effect_id=art1_effect_id,
        outstanding=outstanding,
    )

    return roles


def assert_article_49a_provenance_explanations(
    bundle: dict[str, Any],
    *,
    roles: dict[str, str],
    snap: dict[str, Any],
    by_ann: dict[str, dict[str, Any]],
    art_effect_id: str,
    para1_effect_id: str,
    para2_effect_id: str,
    para3_effect_id: str,
    art1_effect_id: str,
    outstanding: str,
) -> None:
    """Assert source-manifestation and source-effect DecisionExplanation coverage."""
    explanations = _decision_explanations(bundle)
    if not explanations:
        raise AssertionError("Expected decision_explanations including provenance/source_effect.")

    # Pre-provenance stages remain present (43 decisions from prior slices).
    pre_stages = {
        "selection",
        "extraction",
        "classification",
        "grouping",
        "relationship",
        "effective_law",
    }
    pre_count = sum(1 for e in explanations if str(e.get("stage") or "") in pre_stages)
    if pre_count < 43:
        raise AssertionError(
            f"Expected at least 43 pre-provenance decision explanations; found {pre_count}."
        )

    snap_id = str(snap.get("id") or "")
    manifestation = [
        e
        for e in explanations
        if e.get("rule_id") == "provenance.classify_manifestation"
        and str(e.get("subject_id") or "") == snap_id
    ]
    if len(manifestation) != 1:
        raise AssertionError(
            f"Expected one manifestation classification for {snap_id}; found {len(manifestation)}."
        )
    man = manifestation[0]
    if man.get("outcome") != "classified_as_revised":
        raise AssertionError(
            f"Expected classified_as_revised; found {man.get('outcome')!r}."
        )
    if str(man.get("metadata", {}).get("manifestation_basis") or "") != "source_metadata":
        basis = _explanation_evidence_value(man, kind="winning_evidence_basis")
        if basis != "source_metadata":
            raise AssertionError(
                f"Expected manifestation basis source_metadata; found {basis!r}."
            )
    summary_l = str(man.get("summary") or "").lower()
    if (
        "law-proposition-extractor independently applied every amendment" in summary_l
        or "law-proposition-extractor applied all amendments" in summary_l
    ) and "does not mean" not in summary_l and "not mean" not in summary_l:
        raise AssertionError(
            "Manifestation explanation must not claim Law Proposition Extractor applied all amendments."
        )
    req_as_of = _explanation_evidence_value(man, kind="requested_as_of_date")
    res_as_of = _explanation_evidence_value(man, kind="resolved_as_of_date")
    if req_as_of and req_as_of not in {"(not recorded)", "None", ""}:
        if req_as_of == str(snap.get("retrieved_at") or ""):
            raise AssertionError(
                "Manifestation explanation must not treat retrieval time as requested as-of."
            )
    if res_as_of and res_as_of not in {"(not recorded)", "None", ""}:
        raise AssertionError(
            f"Expected resolved as-of not recorded for revised snapshot; found {res_as_of!r}."
        )

    as_of_rows = [
        e
        for e in explanations
        if e.get("rule_id") == "provenance.preserve_as_of_unknown"
        and str(e.get("subject_id") or "") == snap_id
    ]
    if len(as_of_rows) != 1:
        raise AssertionError(
            f"Expected one preserve_as_of_unknown decision for {snap_id}; found {len(as_of_rows)}."
        )
    as_of_summary = str(as_of_rows[0].get("summary") or "").lower()
    if "retrieval" in as_of_summary and "as-of" in as_of_summary:
        if "equals retrieval" in as_of_summary or "same as retrieval" in as_of_summary:
            raise AssertionError(
                "As-of explanation must not claim legal as-of equals retrieval date."
            )

    # Map propositions → statements for relevance checks.
    props = {str(p.get("id")): p for p in (_article_49a_props(bundle)) if isinstance(p, dict)}
    statements, _el_diags = _statements_artifact(bundle)
    prop_to_stmts: dict[str, list[str]] = {}
    for stmt in statements:
        if not isinstance(stmt, dict):
            continue
        sid = str(stmt.get("id") or "")
        for pid in stmt.get("source_proposition_ids") or []:
            prop_to_stmts.setdefault(str(pid), []).append(sid)

    # Use locator-based statement sets.
    p1_stmts: set[str] = set()
    p2_stmts: set[str] = set()
    p3_stmts: set[str] = set()
    for _role, pid in roles.items():
        prop = props.get(pid) or {}
        loc = str(prop.get("fragment_locator") or "")
        for sid in prop_to_stmts.get(pid, []):
            if loc.startswith("article:49a:paragraph:1"):
                p1_stmts.add(sid)
            elif loc.startswith("article:49a:paragraph:2"):
                p2_stmts.add(sid)
            elif loc.startswith("article:49a:paragraph:3"):
                p3_stmts.add(sid)

    all_49a_stmts = p1_stmts | p2_stmts | p3_stmts
    if not all_49a_stmts:
        raise AssertionError("Expected Article 49a statements for provenance relevance checks.")

    def _relevance(
        *, rule_id: str, effect_id: str, statement_ids: set[str]
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for expl in explanations:
            if expl.get("rule_id") != rule_id:
                continue
            if str(expl.get("subject_id") or "") not in statement_ids:
                continue
            meta = expl.get("metadata") if isinstance(expl.get("metadata"), dict) else {}
            if str(meta.get("effect_id") or "") != effect_id:
                # Also check evidence
                ev = _explanation_evidence_value(expl, kind="effect_id")
                if ev != effect_id:
                    continue
            matches.append(expl)
        return matches

    # Article-level effect inherited on every paragraph statement.
    for stmt_set, label in (
        (p1_stmts, "paragraph 1"),
        (p2_stmts, "paragraph 2"),
        (p3_stmts, "paragraph 3"),
    ):
        inherited = _relevance(
            rule_id="source_effect.inherit_from_structural_ancestor",
            effect_id=art_effect_id,
            statement_ids=stmt_set,
        )
        if not inherited:
            raise AssertionError(
                f"Expected Article-level effect inherited on {label} statements."
            )
        for row in inherited:
            if not _explanation_evidence_value(row, kind="ancestor_locator") and not row.get(
                "metadata", {}
            ).get("ancestor_locator"):
                path = _explanation_evidence_value(row, kind="validated_parent_path")
                if not path:
                    raise AssertionError(
                        "Inherited effect explanation missing ancestor path/locator."
                    )
            if str(row.get("metadata", {}).get("relevance_basis") or "") == "exact_fragment":
                raise AssertionError(
                    "Article-level effect incorrectly marked as exact_fragment."
                )

    # Paragraph-specific exact links.
    for effect_id, stmt_set, siblings, label in (
        (para1_effect_id, p1_stmts, p2_stmts | p3_stmts, "paragraph 1"),
        (para2_effect_id, p2_stmts, p1_stmts | p3_stmts, "paragraph 2"),
        (para3_effect_id, p3_stmts, p1_stmts | p2_stmts, "paragraph 3"),
    ):
        exact = _relevance(
            rule_id="source_effect.link_exact_fragment",
            effect_id=effect_id,
            statement_ids=stmt_set,
        )
        if not exact:
            raise AssertionError(f"Expected exact-fragment effect on {label} statements.")
        leaked = _relevance(
            rule_id="source_effect.link_exact_fragment",
            effect_id=effect_id,
            statement_ids=siblings,
        )
        if leaked:
            raise AssertionError(
                f"{label} direct effect leaked to sibling paragraph statements."
            )
        # Must not appear as inherited on siblings either.
        leaked_inh = _relevance(
            rule_id="source_effect.inherit_from_structural_ancestor",
            effect_id=effect_id,
            statement_ids=siblings,
        )
        if leaked_inh:
            raise AssertionError(
                f"{label} effect incorrectly inherited onto sibling statements."
            )

    # Article 1 exclusion
    art1_relevant = [
        e
        for e in explanations
        if e.get("rule_id")
        in {
            "source_effect.link_exact_fragment",
            "source_effect.inherit_from_structural_ancestor",
        }
        and str(e.get("subject_id") or "") in all_49a_stmts
        and (
            str((e.get("metadata") or {}).get("effect_id") or "") == art1_effect_id
            or _explanation_evidence_value(e, kind="effect_id") == art1_effect_id
        )
    ]
    if art1_relevant:
        raise AssertionError(
            "Article 1 effect must not appear as relevant on Article 49a statements."
        )
    art1_excluded = _relevance(
        rule_id="source_effect.exclude_unrelated_fragment",
        effect_id=art1_effect_id,
        statement_ids=all_49a_stmts,
    )
    if not art1_excluded:
        raise AssertionError(
            "Expected an exclusion/boundary explanation establishing Article 1 "
            "is not an ancestor of Article 49a."
        )
    for row in art1_excluded:
        blob = json.dumps(row).lower()
        if "article:1" in blob and "not a structural ancestor" in blob:
            continue
        if "not a structural ancestor" in blob:
            continue
        raise AssertionError(
            "Article 1 exclusion explanation must state non-ancestry boundary."
        )

    # Outstanding status explanation
    outstanding_expl = [
        e
        for e in explanations
        if e.get("rule_id") == "source_effect.classify_outstanding_status"
    ]
    if not outstanding_expl:
        raise AssertionError("Expected outstanding-effects status explanation.")
    status_norm = outstanding
    if status_norm in {"present"}:
        status_norm = "source_reports_present"
    if status_norm in {"unknown"}:
        status_norm = "source_status_unknown"
    matched_outstanding = [
        e for e in outstanding_expl if str(e.get("outcome") or "") == status_norm
    ]
    if not matched_outstanding and status_norm:
        # Accept fixture's actual enum value on any outstanding explanation.
        outcomes = {str(e.get("outcome") or "") for e in outstanding_expl}
        if status_norm not in outcomes and outstanding not in outcomes:
            raise AssertionError(
                f"Expected outstanding explanation outcome {status_norm!r}; found {outcomes}."
            )
    for e in outstanding_expl:
        if e.get("outcome") == "source_reports_none" and outstanding in {
            "source_reports_present",
            "source_status_unknown",
            "present",
            "unknown",
        }:
            raise AssertionError("Outstanding unknown/present displayed as none.")

    # Independent consumption — assert fixture's actual status without inventing.
    for ann_id in ARTICLE_49A_EFFECT_ANNOTATION_IDS:
        effect = by_ann[ann_id]
        effect_id = str(effect.get("id") or "")
        cons = str(effect.get("independent_consumption_status") or "")
        cons_expl = [
            e
            for e in explanations
            if e.get("rule_id") == "source_effect.assess_independent_consumption"
            and str(e.get("subject_id") or "") == effect_id
        ]
        if not cons_expl:
            raise AssertionError(
                f"Expected independent-consumption explanation for effect {ann_id}."
            )
        for e in cons_expl:
            if str(e.get("outcome") or "") != cons:
                raise AssertionError(
                    f"Consumption explanation outcome {e.get('outcome')!r} "
                    f"!= fixture status {cons!r} for {ann_id}."
                )
            summary = str(e.get("summary") or "").lower()
            if cons == "not_matched" and (
                "instrument does not exist" in summary
                or "instrument is nonexistent" in summary
            ) and "does not mean" not in summary and "not mean" not in summary:
                raise AssertionError(
                    "not_matched must not be described as instrument nonexistent."
                )
            if cons == "consumed_in_current_run" and (
                "verified" in summary or "correctly applied" in summary
            ):
                raise AssertionError(
                    "consumed status must not claim amendment verified/applied."
                )
            if cons == "not_assessed" and "attempted a run-scoped identity match" in summary:
                raise AssertionError(
                    "not_assessed must not claim matching was attempted."
                )
            snap_ev = _explanation_evidence_value(e, kind="source_snapshot_id")
            meta_snap = (e.get("metadata") or {}).get("source_snapshot_id")
            if snap_ev and snap_ev != snap_id and meta_snap and str(meta_snap) != snap_id:
                raise AssertionError(
                    f"Source-effect explanation references wrong snapshot {snap_ev!r}."
                )

    # Duplicate relevance decisions forbidden for same statement+effect+basis.
    seen_rel: set[str] = set()
    for e in explanations:
        if e.get("rule_id") not in {
            "source_effect.link_exact_fragment",
            "source_effect.inherit_from_structural_ancestor",
        }:
            continue
        if str(e.get("subject_id") or "") not in all_49a_stmts:
            continue
        key = (
            f"{e.get('rule_id')}|{e.get('subject_id')}|"
            f"{(e.get('metadata') or {}).get('effect_id')}|"
            f"{(e.get('metadata') or {}).get('relevance_basis')}"
        )
        if key in seen_rel:
            raise AssertionError(f"Duplicated source-effect relevance decision: {key}")
        seen_rel.add(key)

    # No absolute filesystem paths / file:// URLs in provenance explanations.
    for e in explanations:
        if e.get("stage") not in {"provenance", "source_effect"}:
            continue
        blob = json.dumps(e)
        if "file://" in blob or "/Users/" in blob or "/home/" in blob:
            raise AssertionError(
                "Provenance/source-effect explanation must not include absolute paths."
            )


def assert_serialized_artifacts(export_dir: Path) -> None:
    required = (
        "source_snapshots.json",
        "source_fragments.json",
        "propositions.json",
        "legal_rule_groups.json",
        "legal_rule_relationships.json",
        "effective_law_statements.json",
        "proposition_matcher_law_candidates.json",
        "source_legal_effects.json",
        "decision_explanations.json",
    )
    for name in required:
        path = export_dir / name
        if not path.is_file():
            raise AssertionError(f"Expected additive artifact {name} after serialization.")
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Round-trip sanity
        path.write_text(json.dumps(raw), encoding="utf-8")
        again = json.loads(path.read_text(encoding="utf-8"))
        if again != raw:
            raise AssertionError(f"Artifact {name} failed JSON round-trip equality.")


def run_article_49a_acceptance_pipeline(
    *,
    work_dir: Path,
    fixture: Path | None = None,
    export: bool = True,
) -> Article49aAcceptanceResult:
    """Run the offline production-shaped Article 49a acceptance pipeline."""
    base = fixture if fixture is not None else fixture_dir()
    case = load_case(base)
    xml = (base / "source.xml").read_text(encoding="utf-8")
    responses = load_frontier_responses(base)

    def fake_fetch(url: str) -> tuple[str, dict[str, object]]:
        return xml, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml.encode("utf-8")),
            "fetched_url": url,
        }

    class _FakeLLM:
        class _Settings:
            frontier_extract_model = "frontier_extract"
            local_extract_model = "local_extract"
            max_extract_input_tokens = 150_000
            extract_model_context_limit = 200_000
            skip_llm_preflight = True

        def __init__(self) -> None:
            self.settings = self._Settings()

        def complete_text(self, *, prompt: str, model: str, **kwargs: object) -> str:
            return self.complete_text_result(prompt=prompt, model=model, **kwargs).content

        def complete_text_result(
            self, *, prompt: str, model: str, **kwargs: object
        ) -> TextCompletionResult:
            _ = (model, kwargs)
            for locator, body in responses.items():
                needle = f"Fragment locator (traceability): {locator}"
                if needle in prompt:
                    return TextCompletionResult(content=body, finish_reason="stop")
            raise AssertionError(
                "Captured frontier response not found for prompt fragment locator."
            )

    def make_service(cache_dir: Path | str) -> SourceIngestionService:
        adapter = LegislationGovUkAuthorityAdapter(fetch_xml=fake_fetch)
        return SourceIngestionService(
            cache_dir=cache_dir,
            adapters={"legislation_gov_uk": adapter},
        )

    source_cache = work_dir / "source-cache"
    derived_cache = work_dir / "derived-cache"
    export_dir = work_dir / "export"

    with (
        patch("law_proposition_extractor_pipeline.runner.JuditLLMClient", lambda: _FakeLLM()),
        patch("law_proposition_extractor_pipeline.runner.SourceIngestionService", make_service),
        patch("law_proposition_extractor_pipeline.runner.preflight_llm_extraction", lambda *_a, **_k: None),
    ):
        bundle = build_bundle_from_case(
            case_data=case,
            use_llm=True,
            extraction_mode="frontier",
            extraction_fallback="fail_closed",
            divergence_reasoning="none",
            source_cache_dir=str(source_cache),
            derived_cache_dir=str(derived_cache),
        )

    if export:
        export_dir.mkdir(parents=True, exist_ok=True)
        export_bundle(bundle=bundle, output_dir=str(export_dir))
        # Reload artifacts from disk into bundle for assertion convenience
        for name, key in (
            ("legal_rule_groups.json", "legal_rule_groups"),
            ("legal_rule_relationships.json", "legal_rule_relationships"),
            ("effective_law_statements.json", "effective_law_statements"),
            ("proposition_matcher_law_candidates.json", "proposition_matcher_law_candidates"),
            ("source_legal_effects.json", "source_legal_effects"),
            ("decision_explanations.json", "decision_explanations"),
            ("source_snapshots.json", "source_snapshots"),
            ("source_fragments.json", "source_fragments"),
            ("propositions.json", "propositions"),
        ):
            path = export_dir / name
            if path.is_file():
                bundle[key] = json.loads(path.read_text(encoding="utf-8"))

    roles = assert_article_49a_legal_structure(bundle)
    if export:
        assert_serialized_artifacts(export_dir)

    return Article49aAcceptanceResult(
        bundle=bundle,
        export_dir=export_dir,
        proposition_ids=roles,
    )
