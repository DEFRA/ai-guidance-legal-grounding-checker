#!/usr/bin/env python3
"""Rewrite legacy personal codenames to canonical names across the tree.

Skips allowlisted paths and protects frozen ID patterns on a line-by-line basis.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIR_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "compat",  # keep legacy tokens in compat layer
}
SKIP_FILES = {
    "NAMES.md",
    "components.manifest.yaml",
    "check_legacy_component_names.py",
    "bulk_rewrite_names.py",
    "rename_components.py",
    "load_manifest.py",
    "migration-component-rename.md",
    "alias-removal-follow-up.md",
    "external-name-inventory.md",
}
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".pdf",
    ".woff",
    ".woff2",
    ".pyc",
    ".lock",
}

# Longest-first replacements (path/import/package identity).
REPLACEMENTS: list[tuple[str, str]] = [
    # Judit workspace packages
    ("judit_pipeline", "law_proposition_extractor_pipeline"),
    ("judit_domain", "law_proposition_extractor_domain"),
    ("judit_exporters", "law_proposition_extractor_exporters"),
    ("judit_storage", "law_proposition_extractor_storage"),
    ("judit_llm", "law_proposition_extractor_llm"),
    ("judit_api", "law_proposition_extractor_api"),
    ("judit-pipeline", "law-proposition-extractor-pipeline"),
    ("judit-domain", "law-proposition-extractor-domain"),
    ("judit-exporters", "law-proposition-extractor-exporters"),
    ("judit-storage", "law-proposition-extractor-storage"),
    ("judit-llm", "law-proposition-extractor-llm"),
    ("judit-api", "law-proposition-extractor-api"),
    ("judit-workspace", "law-proposition-extractor-workspace"),
    ("judit-demo", "law-proposition-extractor-demo"),
    ("judit-run-case", "law-proposition-extractor-run-case"),
    ("judit-export-case", "law-proposition-extractor-export-case"),
    ("@judit/web", "@law-proposition-extractor/web"),
    ("judit-root", "law-proposition-extractor-root"),
    ("ada-source-discovery", "law-discovery"),
    ("ada-viewer", "law-discovery-viewer"),
    ("ada-discovery-fast", "law-discovery-fast"),
    # Directory / path segments (with slash)
    ("guidance-discovery/", "guidance-discovery/"),  # noop placeholder
    ("mary/", "guidance-discovery/"),
    ("radia/", "guidance-relevance-filter/"),
    ("susan/", "guidance-proposition-extractor/"),
    ("beatrice/", "proposition-matcher/"),
    ("anna/", "match-adjudicator/"),
    ("esther/", "audit-assembler/"),
    ("judit/", "law-proposition-extractor/"),
    # backtick path forms without trailing slash handled via word rules below
    # Python package imports for small components
    ("guidance_relevance_filter", "guidance_relevance_filter"),
    ("from radia", "from guidance_relevance_filter"),
    ("import radia", "import guidance_relevance_filter"),
    ("from susan", "from guidance_proposition_extractor"),
    ("import susan", "import guidance_proposition_extractor"),
    ("from beatrice", "from proposition_matcher"),
    ("import beatrice", "import proposition_matcher"),
    ("from anna", "from match_adjudicator"),
    ("import anna", "import match_adjudicator"),
    ("from esther", "from audit_assembler"),
    ("import esther", "import audit_assembler"),
    ("from ada", "from law_discovery"),
    ("import ada", "import law_discovery"),
    # Artifact / module names that are identity (not frozen IDs)
    ("beatrice_law_candidates", "proposition_matcher_law_candidates"),
    ("beatrice-law-candidates", "proposition-matcher-law-candidates"),
    ("judit_intake_bundle", "law_proposition_extractor_intake_bundle"),
    ("make_judit_intake", "make_law_proposition_extractor_intake"),
    ("format_judit_intake", "format_law_proposition_extractor_intake"),
    ("export-bundle-for-judit", "export-bundle-for-law-proposition-extractor"),
    ("export-for-judit", "export-for-law-proposition-extractor"),
    ("--beatrice-run", "--proposition-matcher-run"),
    ("beatrice-run", "proposition-matcher-run"),
    ("anna-report.json", "match_adjudicator_report.json"),
    ("guidance_from_susan", "guidance_from_guidance_proposition_extractor"),
    ("inferBeatriceCandidateProxy", "inferPropositionMatcherCandidateProxy"),
    ("BeatriceProxyBreakdown", "PropositionMatcherProxyBreakdown"),
    ("BeatriceCandidate", "PropositionMatcherCandidate"),
    ("isBeatriceCandidate", "isPropositionMatcherCandidate"),
    ("beatriceCandidate", "propositionMatcherCandidate"),
    ("beatriceIds", "propositionMatcherIds"),
    ("beatriceOnly", "propositionMatcherOnly"),
    ("beatrice_proxy", "proposition_matcher_proxy"),
    ("beatriceStatementIds", "propositionMatcherStatementIds"),
    ("setBeatrice", "setPropositionMatcher"),
    ("BEATRICE_", "PROPOSITION_MATCHER_"),
    # Env prefixes
    ("ADA_LEX_", "LAW_DISCOVERY_LEX_"),
    ("ADA_AI_", "LAW_DISCOVERY_AI_"),
    ("ADA_LITELLM_", "LAW_DISCOVERY_LITELLM_"),
    ("JUDIT_LLM_", "LAW_PROPOSITION_EXTRACTOR_LLM_"),
    ("JUDIT_MODEL_", "LAW_PROPOSITION_EXTRACTOR_MODEL_"),
    ("JUDIT_DATABASE_", "LAW_PROPOSITION_EXTRACTOR_DATABASE_"),
    ("NEXT_PUBLIC_JUDIT_", "NEXT_PUBLIC_LAW_PROPOSITION_EXTRACTOR_"),
    ("RADIA_ADJUDICATOR_MODEL", "GUIDANCE_RELEVANCE_FILTER_ADJUDICATOR_MODEL"),
]

# Word-boundary display / token replacements (applied after string replacements).
WORD_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bGrace\b"), "Scope Planner"),
    (re.compile(r"\bMary\b"), "Guidance Discovery"),
    (re.compile(r"\bRadia\b"), "Guidance Relevance Filter"),
    (re.compile(r"\bSusan\b"), "Guidance Proposition Extractor"),
    (re.compile(r"\bJudit\b"), "Law Proposition Extractor"),
    (re.compile(r"\bBeatrice\b"), "Proposition Matcher"),
    (re.compile(r"\bAnna\b"), "Match Adjudicator"),
    (re.compile(r"\bEsther\b"), "Audit Assembler"),
    # Ada last among capitals — word boundary avoids cascade
    (re.compile(r"\bAda\b"), "Law Discovery"),
]

# Lowercase standalone path/cli tokens in common contexts
LOWER_WORD = [
    (re.compile(r"(?<![A-Za-z0-9_-])mary(?![A-Za-z0-9_-])"), "guidance-discovery"),
    (re.compile(r"(?<![A-Za-z0-9_-])radia(?![A-Za-z0-9_-])"), "guidance-relevance-filter"),
    (re.compile(r"(?<![A-Za-z0-9_-])susan(?![A-Za-z0-9_-])"), "guidance-proposition-extractor"),
    (re.compile(r"(?<![A-Za-z0-9_-])beatrice(?![A-Za-z0-9_-])"), "proposition-matcher"),
    (re.compile(r"(?<![A-Za-z0-9_-])anna(?![A-Za-z0-9_-])"), "match-adjudicator"),
    (re.compile(r"(?<![A-Za-z0-9_-])esther(?![A-Za-z0-9_-])"), "audit-assembler"),
    (re.compile(r"(?<![A-Za-z0-9_-])judit(?![A-Za-z0-9_-])"), "law-proposition-extractor"),
    (re.compile(r"(?<![A-Za-z0-9_-])ada(?![A-Za-z0-9_-])"), "law-discovery"),
    (re.compile(r"(?<![A-Za-z0-9_-])grace(?![A-Za-z0-9_-])"), "scope-planner"),
]

PROTECT = [
    re.compile(r"susan-[a-z0-9]+-\d+"),
    re.compile(r'extraction_method\s*=\s*["\']susan["\']'),
    re.compile(r'["\']susan["\']'),  # frozen extraction_method / candidate literals
    re.compile(r"judit_extraction_meta:"),
    re.compile(r"judit_extraction_reuse:"),
    re.compile(r'["\']susan-default["\']'),
]


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIR_PARTS:
        return True
    if path.name in SKIP_FILES:
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    if "tests/fixtures" in str(path) or "/runs/" in str(path) or "/data/demo/" in str(path):
        # Keep historic fixture bytes; still update *.py / *.md outside fixtures
        if path.suffix in {".json", ".jsonl", ".csv"}:
            return True
    return False


def _protect(line: str) -> tuple[str, list[str]]:
    slots: list[str] = []
    out = line
    for pat in PROTECT:
        def repl(m, _slots=slots):
            _slots.append(m.group(0))
            return f"__PROTECT_{len(_slots) - 1}__"

        out = pat.sub(repl, out)
    return out, slots


def _unprotect(line: str, slots: list[str]) -> str:
    for i, val in enumerate(slots):
        line = line.replace(f"__PROTECT_{i}__", val)
    return line


def rewrite_text(text: str) -> str:
    out_lines = []
    for line in text.splitlines(keepends=True):
        body, ending = line, ""
        if line.endswith("\r\n"):
            body, ending = line[:-2], "\r\n"
        elif line.endswith("\n"):
            body, ending = line[:-1], "\n"
        protected, slots = _protect(body)
        for old, new in REPLACEMENTS:
            if old != new:
                protected = protected.replace(old, new)
        for pat, new in WORD_REPLACEMENTS:
            protected = pat.sub(new, protected)
        for pat, new in LOWER_WORD:
            protected = pat.sub(new, protected)
        out_lines.append(_unprotect(protected, slots) + ending)
    return "".join(out_lines)


def main() -> int:
    changed = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or _should_skip(path):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        updated = rewrite_text(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(path.relative_to(ROOT))
    print(f"rewrote {changed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
