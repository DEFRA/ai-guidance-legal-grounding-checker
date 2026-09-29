from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from law_discovery.models import CandidateSource, SourceBundle

PriorityPolicy = Literal["raw", "current_core"]

_JURISDICTION_URI_PATTERNS: dict[str, tuple[str, ...]] = {
    "northern ireland": ("/nisr/",),
}

_CURRENT_CORE_PRINCIPAL_TITLES: tuple[str, ...] = (
    "The Nitrate Pollution Prevention Regulations 2015",
    "The Water Resources (Control of Agricultural Pollution) (Wales) Regulations 2021",
    "The Water Resources (Control of Pollution) (Silage, Slurry and Agricultural Fuel Oil) (England) Regulations 2010",
    "The Reduction and Prevention of Agricultural Diffuse Pollution (England) Regulations 2018",
    "The Control of Pollution (Silage, Slurry and Agricultural Fuel Oil) (Scotland) Regulations 2003",
)

_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2, "unknown": 3}

_INTAKE_SECTIONS: tuple[str, ...] = (
    "principal_sources",
    "amending_sources",
    "revocation_sources",
    "contextual_sources",
    "rejected_sources",
    "relationships",
)

_OTHER_SOURCE_SECTIONS: tuple[str, ...] = (
    "commencement_sources",
    "correction_sources",
    "interpretive_sources",
    "guidance_sources",
    "form_sources",
)


@dataclass(frozen=True)
class JuditIntakeCounts:
    principal_sources: int
    amending_sources: int
    revocation_sources: int
    contextual_sources: int
    rejected_sources: int
    relationships: int

    def as_dict(self) -> dict[str, int]:
        return {
            "principal_sources": self.principal_sources,
            "amending_sources": self.amending_sources,
            "revocation_sources": self.revocation_sources,
            "contextual_sources": self.contextual_sources,
            "rejected_sources": self.rejected_sources,
            "relationships": self.relationships,
        }


@dataclass(frozen=True)
class JuditIntakeResult:
    bundle: SourceBundle
    before: JuditIntakeCounts
    after: JuditIntakeCounts
    excluded: JuditIntakeCounts


def _section_count(bundle: SourceBundle, section: str) -> int:
    return len(getattr(bundle, section))


def _counts_from_bundle(bundle: SourceBundle) -> JuditIntakeCounts:
    return JuditIntakeCounts(
        **{section: _section_count(bundle, section) for section in _INTAKE_SECTIONS}
    )


def _filter_sources(
    sources: list[CandidateSource],
    statuses: set[str],
) -> list[CandidateSource]:
    return [source for source in sources if source.review_status in statuses]


def _normalise_jurisdiction(value: str) -> str:
    return " ".join(value.casefold().split())


def _jurisdiction_uri_patterns(jurisdiction: str) -> tuple[str, ...]:
    return _JURISDICTION_URI_PATTERNS.get(_normalise_jurisdiction(jurisdiction), ())


def _is_excluded_by_jurisdiction(
    source: CandidateSource,
    exclude_jurisdictions: set[str],
) -> bool:
    if not exclude_jurisdictions:
        return False

    title = source.title.casefold()
    canonical_uri = (source.canonical_uri or "").casefold()

    for jurisdiction in exclude_jurisdictions:
        jurisdiction_key = _normalise_jurisdiction(jurisdiction)
        if jurisdiction_key in title:
            return True
        for pattern in _jurisdiction_uri_patterns(jurisdiction):
            if pattern in canonical_uri:
                return True

    return False


def _apply_jurisdiction_exclusions(
    sources: list[CandidateSource],
    exclude_jurisdictions: set[str],
) -> list[CandidateSource]:
    if not exclude_jurisdictions:
        return sources
    return [
        source
        for source in sources
        if not _is_excluded_by_jurisdiction(source, exclude_jurisdictions)
    ]


def _is_downranked_principal(source: CandidateSource) -> bool:
    if source.temporal_status in ("revoked", "historical"):
        return True
    title = source.title.casefold()
    return "revoked" in title or "repealed" in title


def _current_core_title_rank(source: CandidateSource) -> int | None:
    title = source.title.strip()
    for index, core_title in enumerate(_CURRENT_CORE_PRINCIPAL_TITLES):
        if title == core_title or title.startswith(f"{core_title} "):
            return index
    return None


def _temporal_rank(source: CandidateSource) -> int:
    if source.temporal_status in ("current", "current_or_part_current"):
        return 0
    if source.temporal_status == "prospective":
        return 1
    return 2


def _current_core_sort_key(source: CandidateSource) -> tuple[int, int, int, str]:
    core_rank = _current_core_title_rank(source)
    if core_rank is not None:
        return (0, core_rank, 0, source.title.casefold())
    if _is_downranked_principal(source):
        return (2, _temporal_rank(source), _CONFIDENCE_RANK[source.confidence], source.title.casefold())
    return (1, _temporal_rank(source), _CONFIDENCE_RANK[source.confidence], source.title.casefold())


def _sort_principal_sources(
    sources: list[CandidateSource],
    *,
    priority_policy: PriorityPolicy,
) -> list[CandidateSource]:
    if priority_policy == "raw":
        return sources
    return sorted(sources, key=_current_core_sort_key)


def _build_filter_policy(
    *,
    include_source_statuses: set[str],
    include_relationship_statuses: set[str],
    include_contextual_statuses: set[str],
    include_rejected_sources: bool,
    principal_only: bool,
    max_principal_sources: int | None,
    exclude_jurisdictions: set[str],
    priority_policy: PriorityPolicy,
) -> dict[str, object]:
    if principal_only:
        return {
            "principal_sources": sorted(include_source_statuses),
            "amending_sources": [],
            "revocation_sources": [],
            "relationships": [],
            "contextual_sources": [],
            "rejected_sources": [],
            "principal_only": True,
            "max_principal_sources": max_principal_sources,
            "exclude_jurisdictions": sorted(exclude_jurisdictions),
            "priority_policy": priority_policy,
        }
    return {
        "principal_sources": sorted(include_source_statuses),
        "amending_sources": sorted(include_source_statuses),
        "revocation_sources": sorted(include_source_statuses),
        "relationships": sorted(include_relationship_statuses),
        "contextual_sources": sorted(include_contextual_statuses),
        "rejected_sources": sorted(include_source_statuses) if include_rejected_sources else [],
        "principal_only": False,
        "max_principal_sources": max_principal_sources,
        "exclude_jurisdictions": sorted(exclude_jurisdictions),
        "priority_policy": priority_policy,
    }


def make_law_proposition_extractor_intake_bundle(
    bundle: SourceBundle,
    *,
    principal_only: bool = False,
    max_principal_sources: int | None = None,
    exclude_jurisdictions: set[str] | None = None,
    priority_policy: PriorityPolicy = "raw",
    include_relationship_statuses: set[str] | None = None,
    include_source_statuses: set[str] | None = None,
    include_contextual_statuses: set[str] | None = None,
    include_rejected_sources: bool = False,
) -> JuditIntakeResult:
    """Create a Law Proposition Extractor-safe intake bundle from a reviewed Law Discovery source bundle."""
    source_statuses = include_source_statuses or {"accepted"}
    relationship_statuses = include_relationship_statuses or {"accepted"}
    contextual_statuses = include_contextual_statuses or set()
    jurisdiction_exclusions = exclude_jurisdictions or set()

    before = _counts_from_bundle(bundle)

    principal_sources = _apply_jurisdiction_exclusions(
        _filter_sources(bundle.principal_sources, source_statuses),
        jurisdiction_exclusions,
    )
    principal_sources = _sort_principal_sources(
        principal_sources,
        priority_policy=priority_policy,
    )
    if max_principal_sources is not None:
        principal_sources = principal_sources[:max_principal_sources]

    included_principal_ids = {source.source_id for source in principal_sources}
    all_principal_ids = {source.source_id for source in bundle.principal_sources}

    if principal_only:
        amending_sources: list[CandidateSource] = []
        revocation_sources: list[CandidateSource] = []
        commencement_sources: list[CandidateSource] = []
        correction_sources: list[CandidateSource] = []
        interpretive_sources: list[CandidateSource] = []
        guidance_sources: list[CandidateSource] = []
        form_sources: list[CandidateSource] = []
        contextual_sources: list[CandidateSource] = []
        rejected_sources: list[CandidateSource] = []
        relationships: list[SourceRelationship] = []
    else:
        amending_sources = _apply_jurisdiction_exclusions(
            _filter_sources(bundle.amending_sources, source_statuses),
            jurisdiction_exclusions,
        )
        revocation_sources = _apply_jurisdiction_exclusions(
            _filter_sources(bundle.revocation_sources, source_statuses),
            jurisdiction_exclusions,
        )
        commencement_sources = _apply_jurisdiction_exclusions(
            _filter_sources(bundle.commencement_sources, source_statuses),
            jurisdiction_exclusions,
        )
        correction_sources = _apply_jurisdiction_exclusions(
            _filter_sources(bundle.correction_sources, source_statuses),
            jurisdiction_exclusions,
        )
        interpretive_sources = _apply_jurisdiction_exclusions(
            _filter_sources(bundle.interpretive_sources, source_statuses),
            jurisdiction_exclusions,
        )
        guidance_sources = _apply_jurisdiction_exclusions(
            _filter_sources(bundle.guidance_sources, source_statuses),
            jurisdiction_exclusions,
        )
        form_sources = _apply_jurisdiction_exclusions(
            _filter_sources(bundle.form_sources, source_statuses),
            jurisdiction_exclusions,
        )
        contextual_sources = _apply_jurisdiction_exclusions(
            _filter_sources(bundle.contextual_sources, contextual_statuses),
            jurisdiction_exclusions,
        )
        rejected_sources = (
            _apply_jurisdiction_exclusions(
                _filter_sources(bundle.rejected_sources, source_statuses),
                jurisdiction_exclusions,
            )
            if include_rejected_sources
            else []
        )

        included_source_ids = {
            source.source_id
            for sources in (
                principal_sources,
                amending_sources,
                revocation_sources,
                commencement_sources,
                correction_sources,
                interpretive_sources,
                guidance_sources,
                form_sources,
                contextual_sources,
                rejected_sources,
            )
            for source in sources
        }

        relationships = []
        for relationship in bundle.relationships:
            if relationship.review_status not in relationship_statuses:
                continue
            if (
                relationship.from_source_id in all_principal_ids
                and relationship.from_source_id not in included_principal_ids
            ) or (
                relationship.to_source_id in all_principal_ids
                and relationship.to_source_id not in included_principal_ids
            ):
                continue
            if (
                relationship.from_source_id not in included_source_ids
                or relationship.to_source_id not in included_source_ids
            ):
                continue
            relationships.append(relationship)

    intake_bundle = SourceBundle(
        bundle_id=str(uuid4()),
        category_id=bundle.category_id,
        created_at=datetime.now(tz=UTC),
        principal_sources=principal_sources,
        amending_sources=amending_sources,
        commencement_sources=commencement_sources,
        correction_sources=correction_sources,
        revocation_sources=revocation_sources,
        interpretive_sources=interpretive_sources,
        guidance_sources=guidance_sources,
        form_sources=form_sources,
        contextual_sources=contextual_sources,
        rejected_sources=rejected_sources,
        relationships=relationships,
        metadata={
            **bundle.metadata,
            "intake": {
                "kind": "judit_intake",
                "source_bundle_id": bundle.bundle_id,
                "filter_policy": _build_filter_policy(
                    include_source_statuses=source_statuses,
                    include_relationship_statuses=relationship_statuses,
                    include_contextual_statuses=contextual_statuses,
                    include_rejected_sources=include_rejected_sources,
                    principal_only=principal_only,
                    max_principal_sources=max_principal_sources,
                    exclude_jurisdictions=jurisdiction_exclusions,
                    priority_policy=priority_policy,
                ),
            },
        },
    )

    after = _counts_from_bundle(intake_bundle)
    excluded = JuditIntakeCounts(
        **{
            section: before.as_dict()[section] - after.as_dict()[section]
            for section in _INTAKE_SECTIONS
        }
    )
    intake_bundle.metadata["intake"]["excluded_counts"] = excluded.as_dict()

    return JuditIntakeResult(
        bundle=intake_bundle,
        before=before,
        after=after,
        excluded=excluded,
    )


def format_law_proposition_extractor_intake_summary(
    result: JuditIntakeResult,
    *,
    output_path: str | None = None,
    dry_run: bool = False,
) -> str:
    """Format a human-readable before/after summary for CLI output."""
    lines: list[str] = []
    if dry_run:
        lines.append(f"Would write Law Proposition Extractor intake bundle to {output_path}")
    elif output_path is not None:
        lines.append(f"Wrote Law Proposition Extractor intake bundle to {output_path}")

    labels = {
        "principal_sources": "Principal sources",
        "amending_sources": "Amending sources",
        "revocation_sources": "Revocation sources",
        "contextual_sources": "Contextual sources",
        "rejected_sources": "Rejected sources",
        "relationships": "Relationships",
    }
    before = result.before.as_dict()
    after = result.after.as_dict()
    for section in _INTAKE_SECTIONS:
        lines.append(f"{labels[section]}: {after[section]} / {before[section]}")
    return "\n".join(lines)
