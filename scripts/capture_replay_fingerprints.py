#!/usr/bin/env python3
"""Capture substantive fingerprints for AC-10 before/after rename comparison."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "baseline-replay" / "fingerprints.json"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    info: dict = {
        "path": str(path.relative_to(ROOT)),
        "sha256": _sha(raw),
        "bytes": len(raw.encode("utf-8")),
    }
    if path.suffix == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return info
        ids: list[str] = []

        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in {"id", "proposition_id", "guidance_proposition_id", "law_proposition_id"} and isinstance(
                        v, str
                    ):
                        ids.append(v)
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)
        info["id_count"] = len(ids)
        info["ids_sha256"] = _sha("\n".join(sorted(ids)))
        if isinstance(data, list):
            info["list_len"] = len(data)
        elif isinstance(data, dict) and "propositions" in data:
            info["proposition_count"] = len(data["propositions"])
    return info


def main() -> int:
    candidates = [
        ROOT / "audit-assembler" / "tests",
        ROOT / "audit-assembler" / "tests",
        ROOT / "proposition-matcher" / "tests",
        ROOT / "proposition-matcher" / "tests",
        ROOT / "susan" / "tests",
        ROOT / "guidance-proposition-extractor" / "tests",
        ROOT / "law-proposition-extractor" / "data" / "demo",
        ROOT / "law-proposition-extractor" / "data" / "demo",
        ROOT / "law-proposition-extractor" / "tests" / "fixtures" / "article_49a_legal_structure" / "serialized",
        ROOT / "law-proposition-extractor"
        / "tests"
        / "fixtures"
        / "article_49a_legal_structure"
        / "serialized",
    ]
    files: list[Path] = []
    for c in candidates:
        if c.is_dir():
            files.extend(sorted(c.rglob("*.json")))
        elif c.is_file():
            files.append(c)

    # Cap to keep the baseline manageable
    files = [f for f in files if f.stat().st_size < 5_000_000][:80]
    payload = {
        "schema_version": 1,
        "note": "Substantive fingerprint baseline for component rename AC-10",
        "files": [fingerprint_file(f) for f in files],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(payload['files'])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
