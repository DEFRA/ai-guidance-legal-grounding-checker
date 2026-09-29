import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


def _stable_hash(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    return value


@dataclass(frozen=True)
class CachedDerivedArtifact:
    cache_key: str
    stage_name: str
    payload: dict[str, Any]
    cached_at: datetime
    storage_uri: str


class DerivedArtifactCache:
    def __init__(self, cache_dir: Path | None = None) -> None:
        default_cache_dir = Path(tempfile.gettempdir()) / "law-proposition-extractor" / "derived-artifacts"
        self.cache_dir = cache_dir or default_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, *, stage_name: str, cache_key: str) -> CachedDerivedArtifact | None:
        cache_file = self._cache_file(stage_name=stage_name, cache_key=cache_key)
        if not cache_file.exists():
            return None
        try:
            stored = json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(stored, dict):
            return None
        if str(stored.get("stage_name", "")) != stage_name:
            return None

        payload = stored.get("payload")
        if not isinstance(payload, dict):
            return None

        cached_at_raw = str(stored.get("cached_at", datetime.now(UTC).isoformat()))
        try:
            cached_at = datetime.fromisoformat(cached_at_raw)
        except ValueError:
            cached_at = datetime.now(UTC)

        return CachedDerivedArtifact(
            cache_key=str(stored.get("cache_key", cache_key)),
            stage_name=stage_name,
            payload=payload,
            cached_at=cached_at,
            storage_uri=str(cache_file),
        )

    def put(
        self, *, stage_name: str, cache_key: str, payload: dict[str, Any]
    ) -> CachedDerivedArtifact:
        cache_file = self._cache_file(stage_name=stage_name, cache_key=cache_key)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cached_at = datetime.now(UTC)
        serialized = {
            "cache_key": cache_key,
            "stage_name": stage_name,
            "cached_at": cached_at.isoformat(),
            "payload": _json_safe_value(payload),
        }
        serialized_payload = serialized["payload"]
        if not isinstance(serialized_payload, dict):
            raise ValueError("derived cache payload must serialize to a JSON object.")
        cache_file.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
        return CachedDerivedArtifact(
            cache_key=cache_key,
            stage_name=stage_name,
            payload=serialized_payload,
            cached_at=cached_at,
            storage_uri=str(cache_file),
        )

    def _cache_file(self, *, stage_name: str, cache_key: str) -> Path:
        return self.cache_dir / stage_name / f"{cache_key}.json"


PROPOSITION_EXTRACTION_CACHE_STAGES: tuple[str, ...] = (
    "proposition_extraction",
    "proposition_extraction_chunk",
    "proposition_extraction_content_hash",
)


def clear_proposition_extraction_derived_cache(cache_dir: Path) -> list[str]:
    """Remove proposition extraction derived-cache stage trees (aggregate, chunk, content-hash)."""
    removed: list[str] = []
    for stage_name in PROPOSITION_EXTRACTION_CACHE_STAGES:
        stage_dir = cache_dir / stage_name
        if not stage_dir.exists():
            continue
        for path in sorted(stage_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
                removed.append(str(path))
        if stage_dir.exists():
            for child in sorted(stage_dir.iterdir(), reverse=True):
                if child.is_dir():
                    child.rmdir()
            try:
                stage_dir.rmdir()
            except OSError:
                pass
        if not stage_dir.exists():
            removed.append(str(stage_dir.resolve()) + "/")
    return removed


def build_proposition_extraction_chunk_cache_key(
    *,
    authority: str | None,
    authority_source_id: str | None,
    source_fragment_locator: str | None,
    chunk_index: int,
    chunk_body_fingerprint: str,
    model_alias: str,
    extraction_mode: str,
    prompt_version: str,
    focus_scopes: tuple[str, ...],
    max_propositions: int,
    pipeline_version: str,
    strategy_version: str,
) -> str:
    """Stable key for one LLM extraction chunk (ASID + content; not Law Discovery snapshot/fragment ids)."""
    key_payload = {
        "stage_name": "proposition_extraction_chunk",
        "authority": (authority or "").strip() or "none",
        "authority_source_id": (authority_source_id or "").strip() or "none",
        "source_fragment_locator": source_fragment_locator or "none",
        "chunk_index": chunk_index,
        "chunk_body_fingerprint": chunk_body_fingerprint,
        "model_alias": model_alias or "none",
        "extraction_mode": extraction_mode,
        "prompt_version": prompt_version,
        "focus_scopes": list(focus_scopes),
        "max_propositions": max_propositions,
        "pipeline_version": pipeline_version,
        "strategy_version": strategy_version,
    }
    return _stable_hash(key_payload)


def build_proposition_extraction_content_hash_cache_key(
    *,
    content_hash: str,
    model_alias: str | None,
    extraction_mode: str,
    prompt_version: str,
    focus_scopes: tuple[str, ...] | list[str],
    max_propositions: int,
    pipeline_version: str,
    strategy_version: str,
) -> str:
    """Durable key for reusing a full extraction job by identical fragment/snapshot body hash."""
    scopes = tuple(sorted(str(s).strip() for s in focus_scopes if str(s).strip()))
    key_payload = {
        "stage_name": "proposition_extraction_content_hash",
        "content_hash": (content_hash or "").strip() or "none",
        "model_alias": model_alias or "none",
        "extraction_mode": extraction_mode,
        "prompt_version": prompt_version,
        "focus_scopes": list(scopes),
        "max_propositions": max_propositions,
        "pipeline_version": pipeline_version,
        "strategy_version": strategy_version,
    }
    return _stable_hash(key_payload)


def build_derived_artifact_cache_key(
    *,
    stage_name: str,
    source_snapshot_ids: list[str],
    source_fragment_ids: list[str] | None,
    model_alias: str | None,
    prompt_name: str,
    prompt_version: str,
    pipeline_version: str,
    strategy_version: str,
    parameters: dict[str, Any] | None = None,
) -> str:
    key_payload = {
        "stage_name": stage_name,
        "source_snapshot_ids": sorted(source_snapshot_ids),
        "source_fragment_ids": sorted(source_fragment_ids or []),
        "model_alias": model_alias or "none",
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "pipeline_version": pipeline_version,
        "strategy_version": strategy_version,
        "parameters": _json_safe_value(parameters or {}),
    }
    return _stable_hash(key_payload)


def build_derived_artifact_cache_hook(
    *,
    stage_name: str,
    source_snapshot_ids: list[str],
    source_fragment_ids: list[str] | None,
    model_alias: str | None,
    prompt_name: str,
    prompt_version: str,
    pipeline_version: str,
    strategy_version: str,
    parameters: dict[str, Any] | None = None,
    cache_status: str,
    cache_dir: str | None = None,
    cache_storage_uri: str | None = None,
    cached_at: str | None = None,
) -> dict[str, Any]:
    cache_key = build_derived_artifact_cache_key(
        stage_name=stage_name,
        source_snapshot_ids=source_snapshot_ids,
        source_fragment_ids=source_fragment_ids,
        model_alias=model_alias,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        pipeline_version=pipeline_version,
        strategy_version=strategy_version,
        parameters=parameters,
    )
    hook = {
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "pipeline_version": pipeline_version,
        "strategy_version": strategy_version,
        "model_alias": model_alias,
        "source_snapshot_ids": sorted(source_snapshot_ids),
        "source_fragment_ids": sorted(source_fragment_ids or []),
        "derived_artifact_cache_key": cache_key,
        "cache_status": cache_status,
    }
    if cache_dir:
        hook["cache_dir"] = cache_dir
    if cache_storage_uri:
        hook["cache_storage_uri"] = cache_storage_uri
    if cached_at:
        hook["cached_at"] = cached_at
    return hook
