"""Load components.manifest.yaml without requiring PyYAML."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "components.manifest.yaml"


def load_manifest(path: Path = MANIFEST) -> dict:
    """Parse the subset of YAML used by components.manifest.yaml."""
    lines = path.read_text(encoding="utf-8").splitlines()
    components: list[dict] = []
    current: dict | None = None
    in_components = False
    alias_removal_release = "rename+1"
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("alias_removal_release:"):
            alias_removal_release = line.split(":", 1)[1].strip().strip('"').strip("'")
            i += 1
            continue
        if line.startswith("components:"):
            in_components = True
            i += 1
            continue
        if not in_components:
            i += 1
            continue
        m = re.match(r"^  - id:\s*(.+)$", line)
        if m:
            if current:
                components.append(current)
            current = {"id": m.group(1).strip()}
            i += 1
            continue
        if current is None:
            i += 1
            continue
        m = re.match(r"^    ([a-z_]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "" or val == "|":
            # skip block scalars / empty complex fields for table rendering
            i += 1
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            current[key] = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()] if inner else []
        elif val in {"null", "~"}:
            current[key] = None
        else:
            current[key] = val.strip('"').strip("'")
        i += 1
    if current:
        components.append(current)
    return {"alias_removal_release": alias_removal_release, "components": components}
