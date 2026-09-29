from .adapters import (
    AdapterFetchResult,
    AuthorityAdapter,
    CaseFileAuthorityAdapter,
    LegislationGovUkAuthorityAdapter,
    SourceFetchRequest,
    SourcePayload,
)
from .cache import CachedSource, SnapshotCache, build_cache_key
from .categorisation import (
    LINK_TO_RELATIONSHIP,
    RELATIONSHIPS,
    SOURCE_ROLES,
    TARGET_LINK_TYPES,
    build_source_target_link,
    classify_source_categorisation,
)
from .registry import SourceRegistryError, SourceRegistryService
from .search import (
    LegislationGovUkSourceSearchProvider,
    SourceSearchCandidate,
    SourceSearchError,
    SourceSearchProvider,
    SourceSearchService,
    registry_entries_as_search_candidates,
)
from .service import (
    IngestionResult,
    SourceIngestionService,
    content_hash,
    slugify,
    snapshot_cache_identity_key,
)
from .source_family_discovery import (
    candidates_for_included_ids,
    default_discover,
    discover_related_for_registry_entry,
)

__all__ = [
    "LINK_TO_RELATIONSHIP",
    "RELATIONSHIPS",
    "SOURCE_ROLES",
    "TARGET_LINK_TYPES",
    "AdapterFetchResult",
    "AuthorityAdapter",
    "CachedSource",
    "CaseFileAuthorityAdapter",
    "IngestionResult",
    "LegislationGovUkAuthorityAdapter",
    "LegislationGovUkSourceSearchProvider",
    "SnapshotCache",
    "SourceFetchRequest",
    "SourceIngestionService",
    "SourcePayload",
    "SourceRegistryError",
    "SourceRegistryService",
    "SourceSearchCandidate",
    "SourceSearchError",
    "SourceSearchProvider",
    "SourceSearchService",
    "build_cache_key",
    "build_source_target_link",
    "candidates_for_included_ids",
    "classify_source_categorisation",
    "content_hash",
    "default_discover",
    "discover_related_for_registry_entry",
    "registry_entries_as_search_candidates",
    "slugify",
    "snapshot_cache_identity_key",
]
