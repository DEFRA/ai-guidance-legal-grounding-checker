from __future__ import annotations

from pathlib import Path

from law_discovery.models import load_category_brief
from law_discovery.query_plan import build_query_plan


def _equine_passports_category(examples_dir: Path):
    return load_category_brief(examples_dir / "categories" / "equine_passports.category.json")


def _standalone_queries(examples_dir: Path) -> set[str]:
    plan = build_query_plan(_equine_passports_category(examples_dir))
    return {item.query.casefold() for item in plan if item.query_type == "synonym"}


def test_weak_terms_are_not_emitted_as_standalone_queries(examples_dir: Path) -> None:
    queries = _standalone_queries(examples_dir)
    weak_terms = {
        "passport",
        "passports",
        "identification document",
        "identification documents",
        "register",
        "database",
        "keeper",
        "owner",
        "movement",
        "transfer",
        "import",
        "food chain",
        "veterinary medicine",
        "slaughter",
    }
    assert weak_terms.isdisjoint(queries)


def test_broad_species_terms_are_not_emitted_as_standalone_queries(examples_dir: Path) -> None:
    queries = _standalone_queries(examples_dir)
    broad_species = {
        "horse",
        "horses",
        "pony",
        "ponies",
        "donkey",
        "donkeys",
        "mule",
        "mules",
        "zebra",
        "zebras",
        "equine",
        "equines",
        "equid",
        "equids",
        "equidae",
    }
    assert broad_species.isdisjoint(queries)


def test_core_compound_queries_are_preserved(examples_dir: Path) -> None:
    queries = _standalone_queries(examples_dir)
    preserved = {
        "equine passport",
        "equine passports",
        "horse passport",
        "horse passports",
        "equine identification",
        "horse identification",
        "identification of equidae",
        "identification of equines",
        "unique equine lifetime number",
        "ueln",
        "passport issuing organisation",
        "passport issuing organisations",
        "central equine database",
        "central equine databases",
        "equine register",
        "equine registers",
    }
    assert preserved.issubset(queries)


def test_label_and_combined_queries_are_preserved(examples_dir: Path) -> None:
    category = _equine_passports_category(examples_dir)
    plan = build_query_plan(category)
    queries = {item.query for item in plan}
    assert category.label in queries
    combined = next(item for item in plan if item.query_type == "combined")
    assert category.description in combined.query
