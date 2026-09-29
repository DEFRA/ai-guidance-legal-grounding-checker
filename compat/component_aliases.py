"""Legacy personal-codename → canonical component aliases.

DEPRECATED: remove in rename+1.
"""

from __future__ import annotations

import os
import sys
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

ALIAS_REMOVAL_RELEASE = "rename+1"

# Legacy handoff filenames still accepted by readers.
LEGACY_ARTIFACT_FILENAMES = {
    "beatrice_law_candidates.json": "proposition_matcher_law_candidates.json",
    "anna-report.json": "match_adjudicator_report.json",
}

# Frozen domain identifier prefixes — never rewritten by this rename.
FROZEN_ID_PREFIXES = (
    "susan-",
    "judit_extraction_meta:",
    "judit_extraction_reuse:",
    "prop:",
    "lawstmt:",
    "bcand:",
    "m-",
)


@dataclass(frozen=True)
class ComponentAlias:
    slug: str
    display_name: str
    source_kind: str
    legacy_codename: str
    deprecated_aliases: tuple[str, ...]
    python_import: str | None = None


COMPONENTS: tuple[ComponentAlias, ...] = (
    ComponentAlias("scope-planner", "Scope Planner", "manual", "Grace", ("grace", "Grace")),
    ComponentAlias(
        "guidance-discovery",
        "Guidance Discovery",
        "guidance",
        "Mary",
        ("mary", "Mary"),
    ),
    ComponentAlias(
        "law-discovery",
        "Law Discovery",
        "law",
        "Ada",
        ("ada", "Ada", "ada-source-discovery"),
        python_import="law_discovery",
    ),
    ComponentAlias(
        "guidance-relevance-filter",
        "Guidance Relevance Filter",
        "guidance",
        "Radia",
        ("radia", "Radia"),
        python_import="guidance_relevance_filter",
    ),
    ComponentAlias(
        "guidance-proposition-extractor",
        "Guidance Proposition Extractor",
        "guidance",
        "Susan",
        ("susan", "Susan"),
        python_import="guidance_proposition_extractor",
    ),
    ComponentAlias(
        "law-proposition-extractor",
        "Law Proposition Extractor",
        "law",
        "Judit",
        ("judit", "Judit"),
        python_import="law_proposition_extractor",
    ),
    ComponentAlias(
        "proposition-matcher",
        "Proposition Matcher",
        "pipeline",
        "Beatrice",
        ("beatrice", "Beatrice"),
        python_import="proposition_matcher",
    ),
    ComponentAlias(
        "match-adjudicator",
        "Match Adjudicator",
        "pipeline",
        "Anna",
        ("anna", "Anna"),
        python_import="match_adjudicator",
    ),
    ComponentAlias(
        "audit-assembler",
        "Audit Assembler",
        "pipeline",
        "Esther",
        ("esther", "Esther"),
        python_import="audit_assembler",
    ),
)

COMPONENT_BY_SLUG: dict[str, ComponentAlias] = {c.slug: c for c in COMPONENTS}
COMPONENT_BY_LEGACY: dict[str, ComponentAlias] = {}
for _c in COMPONENTS:
    COMPONENT_BY_LEGACY[_c.legacy_codename.lower()] = _c
    for _a in _c.deprecated_aliases:
        COMPONENT_BY_LEGACY[_a.lower()] = _c


def warn_legacy_name(legacy: str, *, replacement: str | None = None) -> None:
    """Emit a deprecation warning for a legacy personal codename."""
    key = legacy.lower()
    comp = COMPONENT_BY_LEGACY.get(key)
    repl = replacement or (comp.slug if comp else "the canonical component name")
    msg = (
        f"Legacy component name {legacy!r} is deprecated; use {repl!r} instead. "
        f"Aliases will be removed in release {ALIAS_REMOVAL_RELEASE}."
    )
    warnings.warn(msg, DeprecationWarning, stacklevel=3)
    print(f"DEPRECATED: {msg}", file=sys.stderr)


def deprecate(legacy: str) -> ComponentAlias:
    """Resolve a legacy name to its canonical component, warning once per call."""
    comp = COMPONENT_BY_LEGACY.get(legacy.lower())
    if comp is None:
        raise KeyError(f"Unknown legacy component name: {legacy!r}")
    warn_legacy_name(legacy, replacement=comp.slug)
    return comp


def resolve_producer_component(value: str | None) -> str | None:
    """Map a producer label (legacy or canonical) to the canonical slug."""
    if value is None:
        return None
    if value in COMPONENT_BY_SLUG:
        return value
    comp = COMPONENT_BY_LEGACY.get(value.lower())
    if comp is not None:
        return comp.slug
    return value


def resolve_artifact_filename(name: str) -> str:
    """Return the canonical artifact filename for a possibly-legacy name."""
    return LEGACY_ARTIFACT_FILENAMES.get(name, name)


def find_artifact(directory: Path, canonical_name: str) -> Path | None:
    """Locate an artifact preferring the canonical filename, then legacy aliases."""
    canonical = directory / canonical_name
    if canonical.is_file():
        return canonical
    for legacy, canon in LEGACY_ARTIFACT_FILENAMES.items():
        if canon == canonical_name:
            legacy_path = directory / legacy
            if legacy_path.is_file():
                return legacy_path
    return None


# Env var prefix pairs: (canonical_prefix, legacy_prefix)
_ENV_PREFIX_PAIRS: tuple[tuple[str, str], ...] = (
    ("LAW_DISCOVERY_", "ADA_"),
    ("LAW_PROPOSITION_EXTRACTOR_", "JUDIT_"),
    ("GUIDANCE_RELEVANCE_FILTER_", "RADIA_"),
)


def resolve_env(
    canonical_name: str,
    *,
    legacy_name: str | None = None,
    default: str | None = None,
    environ: dict[str, str] | None = None,
) -> str | None:
    """Resolve an env var preferring canonical, accepting legacy, failing on conflict.

    `canonical_name` / `legacy_name` are full variable names (e.g. LAW_DISCOVERY_LEX_BASE_URL
    / ADA_LEX_BASE_URL).
    """
    env = environ if environ is not None else os.environ
    canon_val = env.get(canonical_name)
    legacy_val = env.get(legacy_name) if legacy_name else None

    if canon_val is not None and legacy_val is not None and canon_val != legacy_val:
        raise RuntimeError(
            f"Conflicting environment values for {canonical_name}={canon_val!r} and "
            f"{legacy_name}={legacy_val!r}. Supply only one, or make them identical."
        )
    if canon_val is not None:
        return canon_val
    if legacy_val is not None:
        assert legacy_name is not None
        warn_legacy_name(legacy_name, replacement=canonical_name)
        return legacy_val
    return default


def resolve_env_prefix(
    suffix: str,
    *,
    canonical_prefix: str,
    legacy_prefix: str,
    default: str | None = None,
    environ: dict[str, str] | None = None,
) -> str | None:
    """Resolve PREFIX+suffix with conflict detection."""
    return resolve_env(
        f"{canonical_prefix}{suffix}",
        legacy_name=f"{legacy_prefix}{suffix}",
        default=default,
        environ=environ,
    )


@lru_cache(maxsize=1)
def legacy_codenames() -> tuple[str, ...]:
    return tuple(sorted({c.legacy_codename for c in COMPONENTS}))


def all_banned_tokens() -> Iterable[str]:
    """Tokens the repository ban-list searches for (legacy names + old slugs)."""
    tokens: set[str] = set()
    for c in COMPONENTS:
        tokens.add(c.legacy_codename)
        tokens.add(c.legacy_codename.lower())
        tokens.update(c.deprecated_aliases)
    return sorted(tokens)
