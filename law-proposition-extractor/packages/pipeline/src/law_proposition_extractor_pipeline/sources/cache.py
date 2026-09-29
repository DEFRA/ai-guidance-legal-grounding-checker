import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from .adapters import SourcePayload


def build_cache_key(
    authority: str,
    version_id: str,
    content_hash: str,
    *,
    cache_identity_key: str,
) -> str:
    """Stable cache filename identity: never key only on *content_hash* — include source identity.

    ``cache_identity_key`` must distinguish legal sources (e.g. authority_source_id + jurisdiction
    + citation) so identical EU/UK text does not return the wrong cached *SourcePayload*.
    """
    ident = cache_identity_key.strip().lower()
    raw_key = "|".join(
        [
            authority.strip().lower(),
            ident,
            version_id.strip(),
            content_hash.strip().lower(),
        ]
    )
    return sha256(raw_key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CachedSource:
    cache_key: str
    authority: str
    version_id: str
    content_hash: str
    payload: SourcePayload
    cached_at: datetime


class SnapshotCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(
        self,
        *,
        authority: str,
        version_id: str,
        content_hash: str,
        cache_identity_key: str,
    ) -> CachedSource | None:
        cache_key = build_cache_key(
            authority=authority,
            version_id=version_id,
            content_hash=content_hash,
            cache_identity_key=cache_identity_key,
        )
        payload = self._read_cache_file(cache_key)
        if payload is None:
            return None
        return self._cached_source_from_payload(payload)

    def put(
        self,
        *,
        authority: str,
        version_id: str,
        content_hash: str,
        cache_identity_key: str,
        payload: SourcePayload,
    ) -> CachedSource:
        cache_key = build_cache_key(
            authority=authority,
            version_id=version_id,
            content_hash=content_hash,
            cache_identity_key=cache_identity_key,
        )
        cache_file = self.cache_dir / f"{cache_key}.json"
        serialized = {
            "cache_key": cache_key,
            "authority": authority,
            "version_id": version_id,
            "content_hash": content_hash,
            "cache_identity_key": cache_identity_key,
            "cached_at": datetime.now(UTC).isoformat(),
            "payload": {
                "title": payload.title,
                "jurisdiction": payload.jurisdiction,
                "citation": payload.citation,
                "kind": payload.kind,
                "authoritative_text": payload.authoritative_text,
                "authoritative_locator": payload.authoritative_locator,
                "provenance": payload.provenance,
                "as_of_date": _json_safe_value(payload.as_of_date),
                "retrieved_at": _json_safe_value(payload.retrieved_at),
                "source_url": payload.source_url,
                "review_status": payload.review_status,
                "metadata": _json_safe_value(payload.metadata),
                "manifestation_type": _json_safe_value(payload.manifestation_type),
                "manifestation_basis": _json_safe_value(payload.manifestation_basis),
                "requested_as_of_date": _json_safe_value(payload.requested_as_of_date),
                "resolved_as_of_date": _json_safe_value(payload.resolved_as_of_date),
                "source_revision_date": _json_safe_value(payload.source_revision_date),
                "requested_manifestation": _json_safe_value(payload.requested_manifestation),
                "resolved_manifestation": _json_safe_value(payload.resolved_manifestation),
                "manifestation_evidence": _json_safe_value(
                    payload.manifestation_evidence or []
                ),
            },
        }
        cache_file.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
        return self._cached_source_from_payload(serialized)

    def _read_cache_file(self, cache_key: str) -> dict[str, Any] | None:
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _cached_source_from_payload(self, payload: dict[str, Any]) -> CachedSource:
        source_payload = payload.get("payload", {})
        if not isinstance(source_payload, dict):
            source_payload = {}
        return CachedSource(
            cache_key=str(payload.get("cache_key", "")),
            authority=str(payload.get("authority", "")),
            version_id=str(payload.get("version_id", "")),
            content_hash=str(payload.get("content_hash", "")),
            payload=SourcePayload(
                title=str(source_payload.get("title", "")),
                jurisdiction=str(source_payload.get("jurisdiction", "")),
                citation=str(source_payload.get("citation", "")),
                kind=str(source_payload.get("kind", "")),
                authoritative_text=str(source_payload.get("authoritative_text", "")),
                authoritative_locator=str(
                    source_payload.get("authoritative_locator", "document:full")
                ),
                provenance=str(source_payload.get("provenance", "manual")),
                as_of_date=source_payload.get("as_of_date"),
                retrieved_at=source_payload.get("retrieved_at"),
                source_url=source_payload.get("source_url"),
                review_status=source_payload.get("review_status", "draft"),
                metadata=source_payload.get("metadata", {}),
                manifestation_type=source_payload.get("manifestation_type"),
                manifestation_basis=source_payload.get("manifestation_basis"),
                requested_as_of_date=source_payload.get("requested_as_of_date"),
                resolved_as_of_date=source_payload.get("resolved_as_of_date"),
                source_revision_date=source_payload.get("source_revision_date"),
                requested_manifestation=source_payload.get("requested_manifestation"),
                resolved_manifestation=source_payload.get("resolved_manifestation"),
                manifestation_evidence=source_payload.get("manifestation_evidence") or [],
            ),
            cached_at=datetime.fromisoformat(
                str(payload.get("cached_at", datetime.now(UTC).isoformat()))
            ),
        )


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    # StrEnum / Enum — persist the value string.
    value_attr = getattr(value, "value", None)
    if isinstance(value_attr, str) and value.__class__.__name__ != "str":
        try:
            from enum import Enum

            if isinstance(value, Enum):
                return value_attr
        except Exception:
            pass
    return value
