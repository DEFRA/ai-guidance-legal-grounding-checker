from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import cast

from rich.console import Console

from law_discovery.console import DiscoveryConsole, OutputMode
from law_discovery.lex_adapter import LexAdapter, LexAdapterError, LexSearchResult
from law_discovery.models import CandidateSource, CategoryBrief, SourceRegister
from law_discovery.related_source_service import RelatedSourceExpansionService, select_seed_sources


class FakeLexAdapter:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls = 0

    def require_base_url(self) -> None:
        return None

    def search(self, query: str, *, limit: int = 10) -> list[LexSearchResult]:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise LexAdapterError("simulated failure")
        return [
            LexSearchResult(
                raw={"title": f"{query} Amendment Regulations 2015"},
                title="Horse Passports Regulations 2009 Amendment Regulations 2015",
                uri=f"https://example.test/{self.calls}",
                citation=f"SI {self.calls}/1",
            )
        ]


def _category() -> CategoryBrief:
    return CategoryBrief(
        category_id="equine_identification",
        label="Equine identification",
        description="Test",
    )


def _register(*, accepted: list[CandidateSource] | None = None) -> SourceRegister:
    return SourceRegister(
        register_id="reg-1",
        category_id="equine_identification",
        created_at=datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
        accepted_sources=accepted or [],
        rejected_sources=[
            CandidateSource(source_id="rej", title="Rejected", review_status="rejected")
        ],
        parked_sources=[
            CandidateSource(
                source_id="park-low",
                title="Parked low",
                confidence="low",
                review_status="parked",
            ),
            CandidateSource(
                source_id="park-high",
                title="Parked high",
                confidence="high",
                review_status="parked",
            ),
        ],
    )


def _seed(
    *,
    source_id: str = "uksi/2009/1741",
    title: str = "Horse Passports Regulations 2009",
    review_status: str = "accepted",
    confidence: str = "high",
    relationship_to_category: str = "directly_regulates",
) -> CandidateSource:
    return CandidateSource(
        source_id=source_id,
        title=title,
        review_status=review_status,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        relationship_to_category=relationship_to_category,  # type: ignore[arg-type]
    )


def test_select_seed_sources_prefers_accepted() -> None:
    register = _register(accepted=[_seed()])
    seeds = select_seed_sources(register, seed_source_type="all-accepted")
    assert len(seeds) == 1
    assert seeds[0].source_id == "uksi/2009/1741"


def test_select_seed_sources_uses_high_confidence_parked_when_no_accepted() -> None:
    seeds = select_seed_sources(_register(), seed_source_type="all-accepted")
    assert len(seeds) == 1
    assert seeds[0].source_id == "park-high"


def test_principal_seed_filtering_excludes_amendment_sources() -> None:
    register = _register(
        accepted=[
            _seed(),
            _seed(
                source_id="uksi/2015/999",
                title="Horse Passports Regulations 2009 Amendment Regulations 2015",
                relationship_to_category="amends",
            ),
        ]
    )
    seeds = select_seed_sources(register, seed_source_type="principal")
    assert len(seeds) == 1
    assert seeds[0].source_id == "uksi/2009/1741"


def test_max_seed_sources_limits_expansion() -> None:
    register = _register(
        accepted=[
            _seed(source_id="seed-1", title="Alpha Regulations 2009"),
            _seed(source_id="seed-2", title="Beta Regulations 2010"),
            _seed(source_id="seed-3", title="Gamma Regulations 2011"),
        ]
    )
    seeds = select_seed_sources(register, seed_source_type="all-accepted", max_seed_sources=2)
    assert len(seeds) == 2
    assert seeds[0].source_id == "seed-1"
    assert seeds[1].source_id == "seed-2"


def test_no_network_expansion_returns_seeds_and_warning() -> None:
    service = RelatedSourceExpansionService()
    run = service.run_related_source_expansion(
        _category(),
        _register(accepted=[_seed()]),
        use_network=False,
    )
    assert len(run.seed_sources) == 1
    assert run.related_sources == []
    assert any("disabled" in warning.casefold() for warning in run.warnings)
    assert run.metadata["query_count"] > 0


def test_network_expansion_deduplicates_and_classifies() -> None:
    service = RelatedSourceExpansionService(
        lex_adapter=cast(LexAdapter, FakeLexAdapter()),
    )
    run = service.run_related_source_expansion(
        _category(),
        _register(accepted=[_seed()]),
        limit_per_query=3,
        seed_source_type="all-accepted",
    )
    assert len(run.related_sources) >= 1
    assert len({source.source_id for source in run.related_sources}) == len(run.related_sources)
    assert all(source.source_id != _seed().source_id for source in run.related_sources)
    assert any(rel.relationship_type == "amended_by" for rel in run.relationships)


def test_failed_query_does_not_abort_run() -> None:
    service = RelatedSourceExpansionService(
        lex_adapter=cast(LexAdapter, FakeLexAdapter(fail_first=True)),
    )
    run = service.run_related_source_expansion(
        _category(),
        _register(accepted=[_seed()]),
        limit_per_query=1,
        seed_source_type="all-accepted",
    )
    assert run.metadata.get("partial_results") is True
    assert any("failed" in warning.casefold() for warning in run.warnings)
    assert len(run.related_sources) >= 1


def test_relationship_fan_out_capped_per_candidate() -> None:
    class MultiSeedLexAdapter:
        def require_base_url(self) -> None:
            return None

        def search(self, query: str, *, limit: int = 10) -> list[LexSearchResult]:
            return [
                LexSearchResult(
                    raw={"title": "Shared Amendment Regulations 2015"},
                    title="Shared Amendment Regulations 2015",
                    uri="https://example.test/shared",
                    citation="SI 1/1",
                )
            ]

    register = _register(
        accepted=[
            _seed(source_id="seed-1", title="Alpha Regulations 2009"),
            _seed(source_id="seed-2", title="Beta Regulations 2010"),
            _seed(source_id="seed-3", title="Gamma Regulations 2011"),
            _seed(source_id="seed-4", title="Delta Regulations 2012"),
        ]
    )
    service = RelatedSourceExpansionService(
        lex_adapter=cast(LexAdapter, MultiSeedLexAdapter()),
    )
    run = service.run_related_source_expansion(
        _category(),
        register,
        limit_per_query=1,
        seed_source_type="all-accepted",
        expansion_profile="minimal",
        max_seed_sources=4,
    )
    shared_relationships = [
        rel for rel in run.relationships if rel.to_source_id.startswith("lex-")
    ]
    assert len(shared_relationships) <= 3


def test_progress_shows_nonzero_collected_count() -> None:
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.PLAIN)
    console.console = Console(file=stderr, no_color=True, highlight=False, width=200)

    service = RelatedSourceExpansionService(
        lex_adapter=cast(LexAdapter, FakeLexAdapter()),
    )
    run = service.run_related_source_expansion(
        _category(),
        _register(accepted=[_seed()]),
        limit_per_query=1,
        seed_source_type="all-accepted",
        expansion_profile="minimal",
        progress_callback=console.handle_progress,
    )

    output = stderr.getvalue()
    assert "collected" in output
    assert run.metadata.get("raw_candidate_count", 0) > 0


def test_summary_includes_relationship_type_counts() -> None:
    service = RelatedSourceExpansionService(
        lex_adapter=cast(LexAdapter, FakeLexAdapter()),
    )
    run = service.run_related_source_expansion(
        _category(),
        _register(accepted=[_seed()]),
        seed_source_type="all-accepted",
        expansion_profile="minimal",
    )
    stderr = StringIO()
    console = DiscoveryConsole(mode=OutputMode.PLAIN)
    console.console = Console(file=stderr, no_color=True, highlight=False, width=200)
    console.show_related_expansion_summary(run, Path("out.json"), use_ai_triage=False)

    output = stderr.getvalue()
    assert "raw candidates:" in output
    assert "relationship types:" in output
    assert "related source review:" in output
    assert run.metadata.get("related_source_review_counts") is not None


def test_query_provenance_does_not_override_jurisdiction_mismatch() -> None:
    wales_amendment = (
        "The Action Programme for Nitrate Vulnerable Zones "
        "(Amendment) (Wales) Regulations 2003"
    )

    class NvzLexAdapter:
        def require_base_url(self) -> None:
            return None

        def search(self, query: str, *, limit: int = 10) -> list[LexSearchResult]:
            return [
                LexSearchResult(
                    raw={"title": wales_amendment},
                    title=wales_amendment,
                    uri="https://example.test/wales-amendment",
                    citation="WSI 2003/1852",
                )
            ]

    register = _register(
        accepted=[
            _seed(
                source_id="seed-ew",
                title=(
                    "The Action Programme for Nitrate Vulnerable Zones "
                    "(England and Wales) Regulations 1998"
                ),
            ),
            _seed(
                source_id="seed-scot",
                title=(
                    "The Action Programme for Nitrate Vulnerable Zones "
                    "(Scotland) Regulations 1998"
                ),
            ),
        ]
    )
    service = RelatedSourceExpansionService(
        lex_adapter=cast(LexAdapter, NvzLexAdapter()),
    )
    run = service.run_related_source_expansion(
        _category(),
        register,
        limit_per_query=1,
        seed_source_type="all-accepted",
        expansion_profile="minimal",
    )

    amended_by = [rel for rel in run.relationships if rel.relationship_type == "amended_by"]
    assert any(rel.from_source_id == "seed-ew" for rel in amended_by)
    assert not any(rel.from_source_id == "seed-scot" for rel in amended_by)
