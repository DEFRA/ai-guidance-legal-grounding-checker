import json
from pathlib import Path
from typing import Any


def resolve_case_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path.cwd() / candidate


def load_case_file(path: str | Path) -> dict[str, Any]:
    resolved = resolve_case_path(path)
    if resolved.is_dir():
        resolved = resolved / "case.json"
    if not resolved.is_file():
        raise ValueError(f"Case file not found: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if "topic" not in payload:
        raise ValueError("Case file must contain a 'topic' object.")
    if "cluster" not in payload:
        raise ValueError("Case file must contain a 'cluster' object.")
    sources = payload.get("sources")
    candidates = payload.get("source_family_candidates")
    if isinstance(sources, list) and sources:
        return payload
    if (
        str(payload.get("case_analysis_mode") or "").strip() == "candidate_universe"
        and isinstance(candidates, list)
        and len(candidates) > 0
    ):
        return payload
    raise ValueError(
        "Case file must contain a non-empty 'sources' list, or case_analysis_mode=candidate_universe "
        "with a non-empty source_family_candidates list."
    )
