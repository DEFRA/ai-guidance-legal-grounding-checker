"""Deprecated personal-codename CLI entry points.

DEPRECATED: remove in rename+1.

These modules are registered as console_scripts from each package's pyproject
and forward to the canonical CLI after emitting a deprecation warning.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing compat from package entry points when installed editable from a
# component directory by adding the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from compat.component_aliases import deprecate  # noqa: E402


def _forward(legacy: str, import_path: str, attr: str = "app") -> None:
    deprecate(legacy)
    module_name, _, _ = import_path.partition(":")
    # import_path like "guidance_relevance_filter.cli:app"
    mod_path, _, attr_name = import_path.partition(":")
    attr_name = attr_name or attr
    import importlib

    mod = importlib.import_module(mod_path)
    target = getattr(mod, attr_name)
    if callable(target) and attr_name == "main":
        target()
    elif callable(target):
        # Typer/Click app
        target()
    else:
        raise RuntimeError(f"Cannot invoke {import_path}")


def mary() -> None:
    deprecate("mary")
    print(
        "Guidance Discovery has no console script; run ./run.sh in guidance-discovery/",
        file=sys.stderr,
    )
    raise SystemExit(2)


def radia() -> None:
    _forward("radia", "guidance_relevance_filter.cli:app")


def susan() -> None:
    _forward("susan", "guidance_proposition_extractor.cli:app")


def ada() -> None:
    _forward("ada", "law_discovery.cli:main")


def ada_viewer() -> None:
    _forward("ada", "law_discovery.viewer:cli_main")


def beatrice() -> None:
    _forward("beatrice", "proposition_matcher.cli:main")


def anna() -> None:
    _forward("anna", "match_adjudicator.cli:app")


def esther() -> None:
    _forward("esther", "audit_assembler.cli:app")


def judit_demo() -> None:
    _forward("judit", "law_proposition_extractor_pipeline.cli:demo_command")


def judit_run_case() -> None:
    _forward("judit", "law_proposition_extractor_pipeline.cli:run_case_command")


def judit_export_case() -> None:
    _forward("judit", "law_proposition_extractor_pipeline.cli:export_case_command")
