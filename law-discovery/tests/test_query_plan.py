from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from law_discovery.models import CategoryBrief, load_category_brief
from law_discovery.query_plan import build_query_plan, query_plan_to_jsonable


@dataclass
class FakeSuggestedTerm:
    term: str
    confidence: str


@dataclass
class FakeExpansion:
    suggested_terms: list[FakeSuggestedTerm]
    suggested_exclusions: list[str] | None = None


def _equine_category(examples_dir: Path) -> CategoryBrief:
    return load_category_brief(examples_dir / "equine-identification.category.json")


def test_equine_category_includes_label(examples_dir: Path) -> None:
    plan = build_query_plan(_equine_category(examples_dir))
    queries = [item.query for item in plan]
    assert "Equine identification and traceability" in queries


def test_equine_category_includes_horse_passport(examples_dir: Path) -> None:
    plan = build_query_plan(_equine_category(examples_dir))
    queries = [item.query for item in plan]
    assert "horse passport" in queries


def test_equine_category_includes_combined_query_with_description(examples_dir: Path) -> None:
    category = _equine_category(examples_dir)
    plan = build_query_plan(category)
    combined = next(item for item in plan if item.query_type == "combined")
    assert category.description in combined.query
    assert category.label in combined.query


def test_equine_category_includes_jurisdiction_expanded_queries(examples_dir: Path) -> None:
    category = _equine_category(examples_dir)
    plan = build_query_plan(category)
    queries = [item.query for item in plan]
    assert "Equine identification and traceability UK" in queries
    assert "Equine identification and traceability Great Britain" in queries
    assert "Equine identification and traceability England" in queries


def test_duplicate_synonyms_are_deduped_case_insensitively() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test label",
        description="Test description",
        synonyms=["Horse Passport", "horse passport", "HORSE"],
        jurisdiction_hints=[],
    )
    plan = build_query_plan(category)
    passport_queries = [item.query for item in plan if item.query.casefold() == "horse passport"]
    assert len(passport_queries) == 1


def test_exclusions_are_not_included_as_query_strings(examples_dir: Path) -> None:
    category = _equine_category(examples_dir)
    plan = build_query_plan(category)
    queries = {item.query.casefold() for item in plan}
    assert "horse racing betting" not in queries
    assert "tourism" not in queries


def test_ordering_is_stable(examples_dir: Path) -> None:
    category = _equine_category(examples_dir)
    first = build_query_plan(category)
    second = build_query_plan(category)
    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]


def test_high_confidence_expansion_term_is_added() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test label",
        description="Test description",
        synonyms=["equine"],
    )
    expansion = FakeExpansion(
        suggested_terms=[FakeSuggestedTerm(term="central equine database", confidence="high")]
    )
    plan = build_query_plan(category, expansion=expansion)
    queries = [item.query for item in plan]
    assert "central equine database" in queries
    expansion_item = next(item for item in plan if item.query == "central equine database")
    assert "AI expansion" in (expansion_item.rationale or "")


def test_expansion_exclusion_is_not_added_as_query() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Test label",
        description="Test description",
        synonyms=["equine"],
    )
    expansion = FakeExpansion(
        suggested_terms=[FakeSuggestedTerm(term="racecourse admission", confidence="high")],
        suggested_exclusions=["racecourse admission"],
    )
    plan = build_query_plan(category, expansion=expansion)
    queries = {item.query.casefold() for item in plan}
    assert "racecourse admission" not in queries


def test_query_plan_to_jsonable() -> None:
    category = CategoryBrief(
        category_id="test",
        label="Label",
        description="Description",
        synonyms=["term"],
    )
    plan = build_query_plan(category)
    payload = query_plan_to_jsonable(plan)
    assert isinstance(payload, list)
    assert payload[0]["query_type"] == "combined"
    assert payload[0]["source_system"] == "lex"
