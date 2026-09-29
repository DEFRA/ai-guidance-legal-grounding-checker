import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from law_proposition_extractor_domain import (
    ReviewDecision,
    ReviewStatus,
    SourceFetchAttempt,
    SourceFragment,
    SourceParseTrace,
    SourceRecord,
    SourceSnapshot,
)
from law_proposition_extractor_llm.settings import LLMSettings

from law_proposition_extractor_pipeline.fragment_types import fragment_type_from_locator
from law_proposition_extractor_pipeline.source_fragmentation import (
    expand_monolithic_source_fragment,
    max_fragment_body_chars_for_llm_budget,
    reviews_for_expanded_fragments,
)

from .adapters import (
    AuthorityAdapter,
    CaseFileAuthorityAdapter,
    LegislationGovUkAuthorityAdapter,
    SourceFetchRequest,
    SourcePayload,
)
from .cache import SnapshotCache, build_cache_key
from .legislation_effects import (
    finalize_source_legal_effects,
    parsed_effects_from_metadata,
    source_effect_id,
)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def content_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def snapshot_cache_identity_key(request: SourceFetchRequest) -> str:
    """Segments snapshot file cache — includes legal source identity, not text hash alone."""
    raw = request.raw_source
    jur = str(raw.get("jurisdiction", "") or "")
    cit = str(raw.get("citation", "") or "")
    asi = request.authority_source_id.strip()
    return "|".join([asi.lower(), jur.strip().lower(), cit.strip().lower()])


@dataclass(frozen=True)
class IngestionResult:
    sources: list[SourceRecord]
    snapshots: list[SourceSnapshot]
    fragments: list[SourceFragment]
    parse_traces: list[SourceParseTrace]
    reviews: list[ReviewDecision]
    traces: list[dict[str, Any]]
    attempts: list[SourceFetchAttempt]
    source_legal_effects: list[dict[str, Any]]


class SourceIngestionService:
    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        adapters: dict[str, AuthorityAdapter] | None = None,
    ) -> None:
        default_cache_dir = Path(tempfile.gettempdir()) / "law-proposition-extractor" / "source-snapshots"
        self.cache = SnapshotCache(cache_dir=cache_dir or default_cache_dir)
        adapter_registry = adapters or {}
        if "case_file" not in adapter_registry:
            adapter_registry = {**adapter_registry, "case_file": CaseFileAuthorityAdapter()}
        if "legislation_gov_uk" not in adapter_registry:
            adapter_registry = {
                **adapter_registry,
                "legislation_gov_uk": LegislationGovUkAuthorityAdapter(),
            }
        self.adapters = adapter_registry

    def ingest_sources(self, raw_sources: list[dict[str, Any]]) -> IngestionResult:
        sources: list[SourceRecord] = []
        snapshots: list[SourceSnapshot] = []
        fragments: list[SourceFragment] = []
        parse_traces: list[SourceParseTrace] = []
        reviews: list[ReviewDecision] = []
        traces: list[dict[str, Any]] = []
        attempts: list[SourceFetchAttempt] = []
        source_legal_effects: list[dict[str, Any]] = []

        for index, raw in enumerate(raw_sources, start=1):
            request = self._build_fetch_request(raw=raw, index=index)
            payload, trace, source_attempts = self._resolve_payload(request)
            source, snapshot, fragment, parse_trace, review = self._normalize(
                index=index,
                request=request,
                payload=payload,
                raw=raw,
                trace=trace,
            )
            disable_exp = False
            if isinstance(fragment.metadata, dict):
                disable_exp = bool(fragment.metadata.get("disable_fragment_expansion"))
            if isinstance(raw.get("metadata"), dict):
                disable_exp = disable_exp or bool(raw["metadata"].get("disable_fragment_expansion"))

            if disable_exp:
                expanded_frags = [fragment]
            else:
                llm_settings = LLMSettings()
                max_body = max_fragment_body_chars_for_llm_budget(
                    max_extract_input_tokens=llm_settings.max_extract_input_tokens
                )
                overlap = min(8192, max(512, llm_settings.max_extract_input_tokens // 40))
                expanded_frags = expand_monolithic_source_fragment(
                    fragment,
                    max_body_chars=max_body,
                    overlap_chars=overlap,
                    slugify=slugify,
                )

            effects_inventory = self._finalize_legal_effects(
                source=source,
                snapshot=snapshot,
                fragments=expanded_frags,
            )
            if effects_inventory is not None:
                source_legal_effects.append(effects_inventory)
                snap_meta = dict(snapshot.metadata) if isinstance(snapshot.metadata, dict) else {}
                snap_meta["source_legal_effects"] = effects_inventory
                snap_meta.pop("source_legal_effects_draft", None)
                snapshot = snapshot.model_copy(update={"metadata": snap_meta})

            trace_fragment_ids = [f.id for f in expanded_frags]
            trace.update(
                {
                    "source_record_id": source.id,
                    "source_snapshot_id": snapshot.id,
                    "source_fragment_id": trace_fragment_ids[0],
                    "source_fragment_ids": trace_fragment_ids,
                    "provenance": source.provenance,
                    "retrieved_at": source.retrieved_at.isoformat().replace("+00:00", "Z")
                    if source.retrieved_at
                    else None,
                }
            )
            source_attempts = [
                attempt.model_copy(
                    update={
                        "source_record_id": source.id,
                        "id": f"fetch-attempt-{slugify(source.id)}-{attempt.attempt_number:03d}",
                    }
                )
                for attempt in source_attempts
            ]

            sources.append(source)
            snapshots.append(snapshot)
            fragments.extend(expanded_frags)
            if len(expanded_frags) > 1:
                parse_trace = parse_trace.model_copy(
                    update={
                        "output_fragment_ids": trace_fragment_ids,
                        "fragment_count": len(expanded_frags),
                        "metrics": {
                            **parse_trace.metrics,
                            "fragment_count": len(expanded_frags),
                            "fragmentation_expanded": True,
                        },
                    }
                )
                reviews.extend(reviews_for_expanded_fragments(review, expanded_frags, slugify=slugify))
            else:
                reviews.append(review)
            parse_traces.append(parse_trace)
            traces.append(trace)
            attempts.extend(source_attempts)

        return IngestionResult(
            sources=sources,
            snapshots=snapshots,
            fragments=fragments,
            parse_traces=parse_traces,
            reviews=reviews,
            traces=traces,
            attempts=attempts,
            source_legal_effects=source_legal_effects,
        )

    def _finalize_legal_effects(
        self,
        *,
        source: SourceRecord,
        snapshot: SourceSnapshot,
        fragments: list[SourceFragment],
    ) -> dict[str, Any] | None:
        meta = snapshot.metadata if isinstance(snapshot.metadata, dict) else {}
        parsed = parsed_effects_from_metadata(meta)
        if parsed is None:
            return None
        # Re-bind placeholder ids from law_discoverypter draft onto real record/snapshot ids.
        rebound_effects = []
        rebound_locators: dict[str, list[str]] = {}
        old_to_new: dict[str, str] = {}
        for effect in parsed.effects:
            annotation_key = effect.annotation_id or effect.id
            new_id = source_effect_id(
                source_snapshot_id=snapshot.id,
                annotation_id=annotation_key,
                effect_description=effect.effect_description or "",
            )
            old_to_new[effect.id] = new_id
            rebound_effects.append(
                effect.model_copy(
                    update={
                        "id": new_id,
                        "source_record_id": source.id,
                        "source_snapshot_id": snapshot.id,
                    }
                )
            )
        for old_id, locators in parsed.effect_locators.items():
            new_id = old_to_new.get(old_id, old_id)
            rebound_locators[new_id] = list(locators)
        parsed.effects = rebound_effects
        parsed.effect_locators = rebound_locators
        return finalize_source_legal_effects(parsed, fragments)

    def _build_fetch_request(self, *, raw: dict[str, Any], index: int) -> SourceFetchRequest:
        authority = str(raw.get("authority", "case_file"))
        authority_source_id = str(
            raw.get("authority_source_id") or raw.get("id") or f"source-{index:03d}"
        )
        version_id = str(raw.get("version_id") or "v1")

        expected_content_hash = raw.get("content_hash")
        if not expected_content_hash and isinstance(raw.get("text"), str):
            expected_content_hash = content_hash(raw["text"])

        return SourceFetchRequest(
            authority=authority,
            authority_source_id=authority_source_id,
            version_id=version_id,
            expected_content_hash=str(expected_content_hash) if expected_content_hash else None,
            raw_source=raw,
        )

    def _resolve_payload(
        self, request: SourceFetchRequest
    ) -> tuple[SourcePayload, dict[str, Any], list[SourceFetchAttempt]]:
        adapter = self.adapters.get(request.authority)
        if adapter is None:
            known = ", ".join(sorted(self.adapters))
            raise ValueError(
                f"Unsupported source authority {request.authority!r}. Known adapters: {known}."
            )

        trace: dict[str, Any] = {
            "authority": request.authority,
            "authority_source_id": request.authority_source_id,
            "version_id": request.version_id,
            "adapter": adapter.__class__.__name__,
            "requested_content_hash": request.expected_content_hash,
            "cache_dir": str(self.cache.cache_dir),
        }
        attempts: list[SourceFetchAttempt] = []
        max_attempts = int(request.raw_source.get("max_fetch_attempts", 1))
        max_attempts = min(max(max_attempts, 1), 3)
        source_url = str(request.raw_source.get("source_url", "")).strip() or None
        method_hint = (
            "file_input"
            if request.authority == "case_file"
            else "live_fetch" if request.authority == "legislation_gov_uk" else "synthetic"
        )
        for attempt_number in range(1, max_attempts + 1):
            started_at = datetime.now(UTC)
            try:
                cached = None
                if request.expected_content_hash:
                    cached = self.cache.get(
                        authority=request.authority,
                        version_id=request.version_id,
                        content_hash=request.expected_content_hash,
                        cache_identity_key=snapshot_cache_identity_key(request),
                    )

                if cached is not None:
                    raw_artifact_uri = str(
                        (self.cache.cache_dir / f"{cached.cache_key}.json").resolve().as_uri()
                    )
                    finished_at = datetime.now(UTC)
                    attempts.append(
                        SourceFetchAttempt(
                            id=(
                                "fetch-attempt-"
                                + slugify(request.authority_source_id)
                                + f"-{attempt_number:03d}"
                            ),
                            source_record_id=request.authority_source_id,
                            attempt_number=attempt_number,
                            started_at=started_at,
                            finished_at=finished_at,
                            status="cache_hit",
                            url=source_url,
                            authority=request.authority,
                            content_hash=cached.content_hash,
                            cache_key=cached.cache_key,
                            raw_artifact_uri=raw_artifact_uri,
                            method="cache",
                            metadata={"version_id": request.version_id},
                        )
                    )
                    trace["decision"] = "cache_hit"
                    trace["fetch_status"] = "cache_hit"
                    trace["cache_key"] = cached.cache_key
                    trace["content_hash"] = cached.content_hash
                    trace["raw_artifact_uri"] = raw_artifact_uri
                    trace["attempt_count"] = len(attempts)
                    return cached.payload, trace, attempts

                adapter_result = adapter.fetch(request)
                payload = adapter_result.payload
                resolved_hash = content_hash(payload.authoritative_text)
                cached_source = self.cache.put(
                    authority=request.authority,
                    version_id=request.version_id,
                    content_hash=resolved_hash,
                    cache_identity_key=snapshot_cache_identity_key(request),
                    payload=payload,
                )
                raw_artifact_uri = str(
                    (self.cache.cache_dir / f"{cached_source.cache_key}.json").resolve().as_uri()
                )
                adapter_trace = (
                    adapter_result.trace_metadata
                    if isinstance(adapter_result.trace_metadata, dict)
                    else {}
                )
                finished_at = datetime.now(UTC)
                attempts.append(
                    SourceFetchAttempt(
                        id=(
                            "fetch-attempt-"
                            + slugify(request.authority_source_id)
                            + f"-{attempt_number:03d}"
                        ),
                        source_record_id=request.authority_source_id,
                        attempt_number=attempt_number,
                        started_at=started_at,
                        finished_at=finished_at,
                        status="success",
                        url=source_url,
                        authority=request.authority,
                        http_status=(
                            int(adapter_trace["http_status"])
                            if adapter_trace.get("http_status") is not None
                            else None
                        ),
                        response_content_type=(
                            str(adapter_trace.get("content_type"))
                            if adapter_trace.get("content_type")
                            else None
                        ),
                        response_content_length=(
                            int(adapter_trace["response_bytes"])
                            if adapter_trace.get("response_bytes") is not None
                            else None
                        ),
                        content_hash=resolved_hash,
                        cache_key=cached_source.cache_key,
                        raw_artifact_uri=raw_artifact_uri,
                        method=method_hint,
                        metadata={
                            "version_id": request.version_id,
                            "parser": adapter_trace.get("parser"),
                        },
                    )
                )
                trace["decision"] = "fetched_then_cached"
                trace["fetch_status"] = "fetched_then_cached"
                trace["cache_key"] = cached_source.cache_key
                trace["content_hash"] = resolved_hash
                trace["raw_artifact_uri"] = raw_artifact_uri
                trace["adapter_trace"] = adapter_trace
                trace["attempt_count"] = len(attempts)
                return payload, trace, attempts
            except Exception as exc:
                finished_at = datetime.now(UTC)
                retryable = attempt_number < max_attempts
                attempts.append(
                    SourceFetchAttempt(
                        id=(
                            "fetch-attempt-"
                            + slugify(request.authority_source_id)
                            + f"-{attempt_number:03d}"
                        ),
                        source_record_id=request.authority_source_id,
                        attempt_number=attempt_number,
                        started_at=started_at,
                        finished_at=finished_at,
                        status="retryable_error" if retryable else "fatal_error",
                        url=source_url,
                        authority=request.authority,
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                        method=method_hint,
                        metadata={"version_id": request.version_id},
                    )
                )
                trace["attempt_count"] = len(attempts)
                if retryable:
                    continue
                trace["fetch_status"] = "fatal_error"
                trace["error_type"] = exc.__class__.__name__
                trace["error_message"] = str(exc)
                raise

        raise ValueError("Fetch attempts exhausted without payload resolution.")

    def _normalize(
        self,
        *,
        index: int,
        request: SourceFetchRequest,
        payload: SourcePayload,
        raw: dict[str, Any],
        trace: dict[str, Any],
    ) -> tuple[SourceRecord, SourceSnapshot, SourceFragment, SourceParseTrace, ReviewDecision]:
        source_id = str(raw.get("id") or f"src-{slugify(payload.jurisdiction)}-{index:03d}")
        source_hash = content_hash(payload.authoritative_text)
        snapshot_id = str(
            raw.get("snapshot_id") or f"snap-{slugify(source_id)}-{request.version_id}"
        )
        fragment_id = str(raw.get("fragment_id") or f"frag-{slugify(source_id)}-001")

        retrieved_at = payload.retrieved_at or datetime.now(UTC)
        raw_review_status = raw.get("review_status")
        review_status = (
            ReviewStatus(raw_review_status)
            if raw_review_status is not None
            else (payload.review_status or ReviewStatus.PROPOSED)
        )
        metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
        adapter_trace = trace.get("adapter_trace")
        adapter_trace = adapter_trace if isinstance(adapter_trace, dict) else {}
        parser_name = str(adapter_trace.get("parser", "")) or None
        parser_version = "v1" if parser_name else None
        parsed_at = datetime.now(UTC)
        raw_artifact_uri = str(trace.get("raw_artifact_uri", "")) or None
        source_url = payload.source_url

        source = SourceRecord(
            id=source_id,
            title=payload.title,
            jurisdiction=payload.jurisdiction,
            citation=payload.citation,
            kind=payload.kind,
            authoritative_text=payload.authoritative_text,
            authoritative_locator=payload.authoritative_locator,
            status=str(raw.get("status", "working")),
            review_status=review_status,
            provenance=payload.provenance,
            as_of_date=payload.as_of_date,
            retrieved_at=retrieved_at,
            content_hash=source_hash,
            version_id=request.version_id,
            current_snapshot_id=snapshot_id,
            source_url=source_url,
            metadata={
                **metadata,
                "authority": request.authority,
                "authority_source_id": request.authority_source_id,
                "raw_artifact_uri": raw_artifact_uri,
                "parser_name": parser_name,
                "parser_version": parser_version,
                "parsed_at": parsed_at.isoformat().replace("+00:00", "Z"),
            },
        )
        snapshot = SourceSnapshot(
            id=snapshot_id,
            source_record_id=source_id,
            version_id=request.version_id,
            authoritative_text=payload.authoritative_text,
            authoritative_locator=payload.authoritative_locator,
            provenance=payload.provenance,
            as_of_date=payload.as_of_date,
            retrieved_at=retrieved_at,
            content_hash=source_hash,
            raw_artifact_uri=raw_artifact_uri,
            parser_name=parser_name,
            parser_version=parser_version,
            parsed_at=parsed_at,
            authority=request.authority,
            manifestation_type=payload.manifestation_type,
            manifestation_basis=payload.manifestation_basis,
            requested_as_of_date=payload.requested_as_of_date,
            resolved_as_of_date=payload.resolved_as_of_date,
            source_revision_date=payload.source_revision_date,
            requested_manifestation=payload.requested_manifestation,
            resolved_manifestation=payload.resolved_manifestation,
            manifestation_evidence=list(payload.manifestation_evidence or []),
            metadata={
                **metadata,
                "authority": request.authority,
                "authority_source_id": request.authority_source_id,
                "raw_artifact_uri": raw_artifact_uri,
                "parser_name": parser_name,
                "parser_version": parser_version,
                "parsed_at": parsed_at.isoformat().replace("+00:00", "Z"),
            },
        )
        fragment = SourceFragment(
            id=fragment_id,
            fragment_id=fragment_id,
            source_record_id=source_id,
            source_snapshot_id=snapshot_id,
            fragment_type=(
                str(raw.get("fragment_type", "")).strip()
                or fragment_type_from_locator(
                    str(raw.get("fragment_locator", payload.authoritative_locator))
                )
            ),
            locator=str(raw.get("fragment_locator", payload.authoritative_locator)),
            fragment_text=payload.authoritative_text,
            fragment_hash=source_hash,
            text_hash=source_hash,
            char_start=raw.get("char_start"),
            char_end=raw.get("char_end"),
            parent_fragment_id=raw.get("parent_fragment_id"),
            order_index=raw.get("order_index"),
            review_status=review_status,
            metadata=metadata,
        )
        parse_trace = SourceParseTrace(
            id=str(raw.get("parse_trace_id") or f"parse-trace-{slugify(snapshot_id)}"),
            source_record_id=source_id,
            source_snapshot_id=snapshot_id,
            parser_name=parser_name or "unknown_parser",
            parser_version=parser_version or "unknown",
            started_at=parsed_at,
            finished_at=parsed_at,
            status="success",
            input_content_hash=source_hash,
            output_fragment_ids=[fragment.id],
            fragment_count=1,
            warning_count=0,
            error_count=0,
            warnings=[],
            errors=[],
            metrics={
                "fragment_count": 1,
                "input_char_count": len(payload.authoritative_text),
            },
        )
        review = ReviewDecision(
            id=str(raw.get("review_decision_id") or f"review-{slugify(fragment_id)}"),
            target_type="source_fragment",
            target_id=fragment_id,
            previous_status=None,
            new_status=review_status,
            reviewer=str(raw.get("reviewed_by", "system:intake")),
            note=str(raw.get("review_rationale", "Initial intake registration.")),
            metadata={
                "source_record_id": source_id,
                "source_snapshot_id": snapshot_id,
                "cache_key": build_cache_key(
                    authority=request.authority,
                    version_id=request.version_id,
                    content_hash=source_hash,
                    cache_identity_key=snapshot_cache_identity_key(request),
                ),
                "authority": request.authority,
                "authority_source_id": request.authority_source_id,
            },
        )
        return source, snapshot, fragment, parse_trace, review
