from pathlib import Path
from typing import Any

from .runner import run_case_file

DEFAULT_DEMO_CASE = Path("data/demo/example_case.json")
DEMO_CASES: dict[str, Path] = {
    "example": DEFAULT_DEMO_CASE,
    "realistic": Path("data/demo/realistic_case.json"),
    "single-jurisdiction": Path("data/demo/single_jurisdiction_case.json"),
    "single_jurisdiction": Path("data/demo/single_jurisdiction_case.json"),
    "single": Path("data/demo/single_jurisdiction_case.json"),
}


def resolve_demo_case(case_name: str | None = None) -> Path:
    if not case_name:
        return DEFAULT_DEMO_CASE

    key = case_name.strip().lower()
    if key not in DEMO_CASES:
        available = ", ".join(sorted(DEMO_CASES))
        raise ValueError(f"Unknown demo case {case_name!r}. Available cases: {available}.")
    return DEMO_CASES[key]


def build_demo_bundle(use_llm: bool = False, case_name: str | None = None) -> dict[str, Any]:
    case_path = resolve_demo_case(case_name=case_name)
    return run_case_file(case_path=str(case_path), use_llm=use_llm)
