import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .service import SourceIngestionService


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return "-".join(segment for segment in slug.split("-") if segment) or "item"


class SourceRegistryError(ValueError):
    """Raised when source registry operations fail."""


class SourceRegistryService:
    def __init__(
        self,
        *,
        registry_path: str | Path | None = None,
        source_cache_dir: str | Path | None = None,
    ) -> None:
        default_registry_path = Path(tempfile.gettempdir()) / "law-proposition-extractor" / "source-registry.json"
        self.registry_path = Path(registry_path) if registry_path else default_registry_path
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.source_cache_dir = Path(source_cache_dir) if source_cache_dir else None

    def list_entries(self) -> list[dict[str, Any]]:
        state = self._load_state()
        entries = state.get("sources", [])
        if not isinstance(entries, list):
            return []
        return [item for item in entries if isinstance(item, dict)]

    def inspect_entry(self, registry_id: str) -> dict[str, Any]:
        entry = self._entry_by_id(registry_id)
        return entry

    def register_reference(
        self,
        *,
        reference: dict[str, Any],
        refresh: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(reference, dict):
            raise SourceRegistryError("Source reference payload must be an object.")

        authority = str(reference.get("authority", "case_file"))
        authority_source_id = str(
            reference.get("authority_source_id") or reference.get("id") or ""
        ).strip()
        if not authority_source_id:
            raise SourceRegistryError(
                "Source reference requires authority_source_id or id for stable lookup."
            )

        state = self._load_state()
        entries = state.setdefault("sources", [])
        if not isinstance(entries, list):
            raise SourceRegistryError("Invalid registry state: sources must be a list.")

        registry_id = str(reference.get("registry_id") or "").strip()
        if not registry_id:
            registry_id = f"reg-{_slugify(f'{authority}-{authority_source_id}')}"

        if any(str(item.get("registry_id", "")) == registry_id for item in entries):
            raise SourceRegistryError(f"Registry source {registry_id!r} already exists.")

        normalized_reference = self._normalize_reference(
            reference=reference, registry_id=registry_id
        )
        now = _utc_now_iso()
        entry: dict[str, Any] = {
            "registry_id": registry_id,
            "created_at": now,
            "updated_at": now,
            "reference": normalized_reference,
            "current_state": None,
            "refresh_history": [],
        }
        entries.append(entry)
        self._save_state(state)

        if refresh:
            return self.refresh_reference(registry_id=registry_id)
        return entry

    def refresh_reference(self, *, registry_id: str) -> dict[str, Any]:
        state = self._load_state()
        entries = state.get("sources", [])
        if not isinstance(entries, list):
            raise SourceRegistryError("Invalid registry state: sources must be a list.")

        entry_index = next(
            (
                idx
                for idx, item in enumerate(entries)
                if str(item.get("registry_id", "")) == registry_id
            ),
            None,
        )
        if entry_index is None:
            raise SourceRegistryError(f"Registry source {registry_id!r} was not found.")

        entry = entries[entry_index]
        reference = entry.get("reference")
        if not isinstance(reference, dict):
            raise SourceRegistryError(f"Registry source {registry_id!r} has an invalid reference.")

        ingestion = SourceIngestionService(cache_dir=self.source_cache_dir)
        result = ingestion.ingest_sources([reference])
        source = result.sources[0]
        snapshot = result.snapshots[0]
        fragment = result.fragments[0]
        review = result.reviews[0]
        trace = result.traces[0]
        refreshed_at = _utc_now_iso()

        current_state = {
            "refreshed_at": refreshed_at,
            "source_record": source.model_dump(mode="json"),
            "source_snapshot": snapshot.model_dump(mode="json"),
            "source_fragment": fragment.model_dump(mode="json"),
            "review_decision": review.model_dump(mode="json"),
            "fetch_trace": trace,
        }
        history = entry.get("refresh_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "refreshed_at": refreshed_at,
                "source_record_id": source.id,
                "source_snapshot_id": snapshot.id,
                "source_fragment_id": fragment.id,
                "decision": trace.get("decision"),
                "cache_key": trace.get("cache_key"),
                "content_hash": trace.get("content_hash"),
            }
        )

        entry["current_state"] = current_state
        entry["refresh_history"] = history
        entry["updated_at"] = refreshed_at
        entries[entry_index] = entry
        self._save_state(state)
        return entry

    def build_case_sources(self, *, registry_ids: list[str]) -> list[dict[str, Any]]:
        if not registry_ids:
            raise SourceRegistryError("At least one registry source is required.")

        sources: list[dict[str, Any]] = []
        for registry_id in registry_ids:
            entry = self._entry_by_id(registry_id)
            current_state = entry.get("current_state")
            if not isinstance(current_state, dict):
                raise SourceRegistryError(
                    f"Registry source {registry_id!r} has no current state. Refresh it first."
                )
            source_record = current_state.get("source_record")
            if not isinstance(source_record, dict):
                raise SourceRegistryError(
                    f"Registry source {registry_id!r} has invalid current source_record."
                )
            reference = entry.get("reference")
            metadata = source_record.get("metadata")
            merged_metadata = (
                {
                    **metadata,
                    "registry_id": registry_id,
                    "authority": reference.get("authority")
                    if isinstance(reference, dict)
                    else None,
                    "authority_source_id": reference.get("authority_source_id")
                    if isinstance(reference, dict)
                    else None,
                }
                if isinstance(metadata, dict)
                else {
                    "registry_id": registry_id,
                    "authority": reference.get("authority")
                    if isinstance(reference, dict)
                    else None,
                    "authority_source_id": reference.get("authority_source_id")
                    if isinstance(reference, dict)
                    else None,
                }
            )
            sources.append(
                {
                    "id": source_record.get("id"),
                    "authority": "case_file",
                    "authority_source_id": source_record.get("id"),
                    "title": source_record.get("title"),
                    "jurisdiction": source_record.get("jurisdiction"),
                    "citation": source_record.get("citation"),
                    "kind": source_record.get("kind"),
                    "text": source_record.get("authoritative_text", ""),
                    "authoritative_locator": source_record.get(
                        "authoritative_locator", "document:full"
                    ),
                    "status": source_record.get("status", "working"),
                    "review_status": source_record.get("review_status", "proposed"),
                    "provenance": source_record.get("provenance", "registry.current_state"),
                    "as_of_date": source_record.get("as_of_date"),
                    "retrieved_at": source_record.get("retrieved_at"),
                    "version_id": source_record.get("version_id") or "v1",
                    "source_url": source_record.get("source_url"),
                    "metadata": merged_metadata,
                }
            )
        return sources

    def _entry_by_id(self, registry_id: str) -> dict[str, Any]:
        entry = next(
            (
                item
                for item in self.list_entries()
                if str(item.get("registry_id", "")) == registry_id
            ),
            None,
        )
        if entry is None:
            raise SourceRegistryError(f"Registry source {registry_id!r} was not found.")
        return entry

    def _normalize_reference(
        self, *, reference: dict[str, Any], registry_id: str
    ) -> dict[str, Any]:
        normalized = dict(reference)
        normalized["registry_id"] = registry_id
        normalized["authority"] = str(reference.get("authority", "case_file"))
        normalized["authority_source_id"] = str(
            reference.get("authority_source_id") or reference.get("id") or registry_id
        )
        normalized["id"] = str(reference.get("id") or f"src-{_slugify(registry_id)}")
        if "version_id" not in normalized or not str(normalized.get("version_id", "")).strip():
            normalized["version_id"] = "v1"
        return normalized

    def _load_state(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": "0.1", "sources": []}
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SourceRegistryError(
                f"Could not read source registry {self.registry_path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            return {"version": "0.1", "sources": []}
        payload.setdefault("version", "0.1")
        payload.setdefault("sources", [])
        return payload

    def _save_state(self, payload: dict[str, Any]) -> None:
        self.registry_path.write_text(_json_dump(payload), encoding="utf-8")
