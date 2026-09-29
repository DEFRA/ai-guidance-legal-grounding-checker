#!/usr/bin/env python3
"""Fail if personal component codenames appear outside the allowlist (AC-8)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LEGACY_NAMES = (
    "Grace",
    "Mary",
    "Ada",
    "Radia",
    "Susan",
    "Judit",
    "Beatrice",
    "Anna",
    "Esther",
)
LEGACY_SLUGS = (
    "grace",
    "mary",
    "ada",
    "radia",
    "susan",
    "judit",
    "beatrice",
    "anna",
    "esther",
)

ALLOW_PATH_PREFIXES = (
    "NAMES.md",
    "docs/",
    "components.manifest.yaml",
    "compat/",
    "scripts/",
    ".github/",
)

ALLOW_PATH_SUBSTRINGS = (
    "/tests/fixtures/",
    "/data/demo/",
    "/runs/",
    "/output/",
    "/generated/",
    "/.pytest_cache/",
    "/.next/",
    "beatrice_law_candidates",
    "judit_extraction_meta",
    "judit_extraction_reuse",
    "package-lock.json",
    "uv.lock",
    "node_modules/",
    ".venv/",
    "__pycache__/",
    ".git/",
    "govuk-slurry-search-all",
    # Import shims keep legacy package directory names until rename+1
    "/src/radia/",
    "/src/susan/",
    "/src/ada/",
    "/src/beatrice/",
    "/src/anna/",
    "/src/esther/",
)

LINE_ALLOW_PATTERNS = (
    re.compile(r"\bsusan-[a-z0-9]+-\d+\b"),
    re.compile(r'extraction_method\s*=\s*["\']susan["\']'),
    re.compile(r'["\']susan-default["\']'),
    re.compile(r'["\']susan["\']'),
    re.compile(r"judit_extraction_meta:"),
    re.compile(r"judit_extraction_reuse:"),
    re.compile(r"\bprop:[a-f0-9]+\b"),
    re.compile(r"COMPAT_LEGACY_NAME"),
    re.compile(r"legacy_codename"),
    re.compile(r"deprecated_aliases"),
    re.compile(r"DEPRECATED:.*rename\+1"),
    re.compile(r"beatrice_law_candidates"),
    # UUID / hex false positives around short tokens
    re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.I,
    ),
)

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".pdf",
    ".pptx",
    ".html",
    ".woff",
    ".woff2",
    ".pyc",
    ".lock",
    ".db",
    ".sqlite",
}


def _is_allowed_path(rel: str) -> bool:
    if any(rel == p or rel.startswith(p) for p in ALLOW_PATH_PREFIXES):
        return True
    if any(s in rel for s in ALLOW_PATH_SUBSTRINGS):
        return True
    if "test_compat" in rel or "test_legacy_alias" in rel or rel.endswith("_compat_test.py"):
        return True
    return False


def _token_patterns() -> tuple[re.Pattern[str], re.Pattern[str]]:
    # Case-sensitive: avoids camelCase false positives (e.g. annA) and keeps Title Case distinct.
    title = "|".join(re.escape(n) for n in LEGACY_NAMES)
    lower = "|".join(re.escape(n) for n in LEGACY_SLUGS)
    return (
        re.compile(rf"\b({title})\b"),
        re.compile(rf"\b({lower})\b"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--external", type=Path, action="append", default=[])
    parser.add_argument("--strict-external", action="store_true")
    args = parser.parse_args()
    title_pat, lower_pat = _token_patterns()

    def scan(base: Path) -> list[str]:
        found: list[str] = []
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            try:
                rel = str(path.relative_to(base))
            except ValueError:
                rel = str(path)
            if base == args.root and _is_allowed_path(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            in_component_table = False
            for i, line in enumerate(text.splitlines(), 1):
                if "<!-- BEGIN COMPONENT TABLE -->" in line:
                    in_component_table = True
                    continue
                if "<!-- END COMPONENT TABLE -->" in line:
                    in_component_table = False
                    continue
                if in_component_table:
                    continue
                if (
                    "COMPAT_LEGACY_NAME" in line
                    or "DEPRECATED aliases" in line
                    or "compat.legacy_cli" in line
                    or 'f"susan-' in line
                    or "f'susan-" in line
                    or "`susan-…`" in line
                    or "`susan-`" in line
                ):
                    continue
                scrubbed = line
                for p in LINE_ALLOW_PATTERNS:
                    scrubbed = p.sub("", scrubbed)
                matches = title_pat.findall(scrubbed) + lower_pat.findall(scrubbed)
                if matches:
                    uniq = sorted(set(matches))
                    found.append(f"{rel}:{i}: {uniq} :: {line.strip()[:160]}")
        return found

    violations = scan(args.root)
    external_hits: list[str] = []
    for ext in args.external:
        if ext.exists():
            hits = scan(ext)
            external_hits.extend(f"EXTERNAL {ext}: {h}" for h in hits[:50])
            if len(hits) > 50:
                external_hits.append(f"EXTERNAL {ext}: … {len(hits) - 50} more")

    if external_hits:
        print("External inventory hits (attach to story):", file=sys.stderr)
        for h in external_hits[:100]:
            print(h, file=sys.stderr)

    if violations:
        print(f"Found {len(violations)} disallowed legacy component name use(s):", file=sys.stderr)
        for v in violations[:200]:
            print(v, file=sys.stderr)
        if len(violations) > 200:
            print(f"… {len(violations) - 200} more", file=sys.stderr)
        return 1

    if args.strict_external and external_hits:
        return 1
    print("Legacy component name check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
