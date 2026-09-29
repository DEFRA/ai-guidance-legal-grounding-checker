#!/usr/bin/env python3
"""Generate or validate the root README component table from components.manifest.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import sys

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from load_manifest import load_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
BEGIN = "<!-- BEGIN COMPONENT TABLE -->"
END = "<!-- END COMPONENT TABLE -->"


def _load_manifest() -> dict:
    return load_manifest()


def render_table(manifest: dict) -> str:
    rows = [
        "| Canonical name | Slug | Legacy codename | Responsibility |",
        "| --- | --- | --- | --- |",
    ]
    for c in manifest["components"]:
        rows.append(
            f"| **{c['display_name']}** | `{c['slug']}` | {c['legacy_codename']} | "
            f"{c['responsibility']} |"
        )
    return "\n".join(rows) + "\n"


def render_directory_list(manifest: dict) -> str:
    lines = []
    for c in manifest["components"]:
        d = c.get("directory")
        if d:
            lines.append(f"- [`{d}/`]({d}/) — {c['responsibility']}")
        else:
            lines.append(
                f"- **{c['display_name']}** — {c['responsibility']} "
                f"(manual; see [RUNBOOK.md](RUNBOOK.md))"
            )
    return "\n".join(lines) + "\n"


def inject(readme: str, table: str) -> str:
    if BEGIN not in readme or END not in readme:
        raise SystemExit(f"README.md missing markers {BEGIN!r} / {END!r}")
    before, rest = readme.split(BEGIN, 1)
    _, after = rest.split(END, 1)
    return f"{before}{BEGIN}\n{table}{END}{after}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Exit 1 if README table is stale")
    parser.add_argument("--write", action="store_true", help="Rewrite README table region")
    args = parser.parse_args()
    manifest = _load_manifest()
    table = render_table(manifest)
    readme = README.read_text(encoding="utf-8")
    if BEGIN not in readme:
        # First-time: not an error for --write if we also rebuild whole README elsewhere.
        if args.check:
            print("README missing component table markers", file=sys.stderr)
            return 1
        print(table)
        return 0
    updated = inject(readme, table)
    if args.check:
        if updated != readme:
            print("README component table is out of date; run with --write", file=sys.stderr)
            return 1
        print("README component table OK")
        return 0
    if args.write:
        README.write_text(updated, encoding="utf-8")
        print(f"Updated {README}")
        return 0
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
