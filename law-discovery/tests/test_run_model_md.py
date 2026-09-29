"""MODEL.md metadata generation for Law Discovery run outputs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from law_discovery.models import (
    CandidateSource,
    CategoryBrief,
    DiscoveryQuery,
    DiscoveryRun,
    RelatedSourceExpansionRun,
    SourceBundle,
    SourceRegister,
    save_discovery_run,
    save_related_source_expansion_run,
    save_source_bundle,
)
from law_discovery.run_model_md import (
    MODEL_MD_FILENAME,
    build_discovery_model_metadata,
    build_related_expansion_model_metadata,
    render_model_md,
)


def _sample_category() -> CategoryBrief:
    return CategoryBrief(
        category_id="equine_passports",
        label="Equine passports",
        description="Horse identification and passport rules for UK equine keepers.",
        jurisdiction_hints=["England", "Wales"],
        metadata={"discovery_profile": "standard", "notes": "Pilot category run."},
    )


def _discovery_run(
    *,
    metadata: dict | None = None,
    warnings: list[str] | None = None,
) -> DiscoveryRun:
    category = _sample_category()
    return DiscoveryRun(
        run_id="law-discovery-run-test",
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        category=category,
        query_plan=[
            DiscoveryQuery(query="equine passport", query_type="label", source_system="lex"),
            DiscoveryQuery(query="horse passport", query_type="synonym", source_system="lex"),
        ],
        candidate_sources=[
            CandidateSource(source_id="lex-1", title="Equine regs", confidence="high"),
            CandidateSource(source_id="lex-2", title="Other", confidence="low"),
        ],
        warnings=warnings or [],
        metadata=metadata
        or {
            "use_network": True,
            "use_ai_triage": True,
            "ai_triage_model": "frontier_discovery",
            "ai_triage_successful_batch_count": 2,
            "ai_triage_failed_batch_count": 0,
            "candidate_count": 2,
            "successful_query_count": 2,
            "failed_query_count": 0,
        },
    )


def test_discovery_model_md_sections(tmp_path: Path) -> None:
    output = tmp_path / "runs" / "equine_passports" / "discovery-run.json"
    run = _discovery_run()
    meta = build_discovery_model_metadata(run, output_path=output)
    md = render_model_md(meta)

    assert "# Model & run metadata" in md
    assert "> **Run status:** completed" in md
    assert "## Run identity" in md
    assert "discovery" in md
    assert "## Models used" in md
    assert "frontier_discovery" in md
    assert "## Results summary" in md
    assert "Queries Generated" in md
    assert "High Confidence Candidates" in md
    assert "## Settings & notes" in md
    assert "AI triage:** enabled" in md
    assert "Pilot category run." in md


def test_related_expansion_with_ai_triage_and_warnings() -> None:
    run = RelatedSourceExpansionRun(
        run_id="law-discovery-related-test",
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        category_id="equine_passports",
        seed_sources=[CandidateSource(source_id="seed-1", title="Seed act")],
        related_sources=[CandidateSource(source_id="rel-1", title="Amendment")],
        relationships=[],
        warnings=["Lex query timeout on one seed"],
        metadata={
            "use_ai_triage": True,
            "expansion_profile": "standard",
            "query_count": 5,
            "seed_source_count": 1,
            "related_source_count": 1,
            "relationship_count": 0,
            "related_source_review_counts": {"accepted": 1, "rejected": 0},
            "relationship_review_counts": {"accepted": 0, "rejected": 0},
            "llm_usage": {
                "models": [
                    {
                        "role": "relationship triage",
                        "alias": "frontier_related",
                        "provider_model": "anthropic/claude-sonnet-4",
                        "live_calls": 3,
                        "cached_calls": 0,
                        "failed_calls": 0,
                    }
                ],
            },
        },
    )
    md = render_model_md(
        build_related_expansion_model_metadata(
            run,
            category_label="Equine passports",
            category_description="Horse identification rules",
        )
    )

    assert "> **Run status:** completed with warnings — 1 warnings." in md
    assert "related-source-expansion" in md
    assert "relationship triage" in md
    assert "anthropic/claude-sonnet-4" in md
    assert "Related Sources" in md


def test_cached_calls_and_cost_estimate() -> None:
    run = _discovery_run(
        metadata={
            "use_network": True,
            "use_ai_triage": True,
            "candidate_count": 1,
            "llm_usage": {
                "models": [
                    {
                        "roles": ["candidate triage"],
                        "alias": "frontier_discovery",
                        "provider_model": "openai/gpt-4.1",
                        "live_calls": 1,
                        "cached_calls": 2,
                        "failed_calls": 0,
                    }
                ],
                "estimated_input_tokens_total": 9000,
                "estimated_input_tokens_live_only": 3000,
                "estimated_input_tokens_cached_only": 6000,
                "pricing_tier": "frontier",
            },
        }
    )
    md = render_model_md(build_discovery_model_metadata(run))

    assert "| 1 | 2 | 0 |" in md
    assert "Estimated input tokens (cached calls only)" in md
    assert "## Indicative cost estimate" in md
    assert "Lower-bound indicative USD (live input tokens only)" in md
    assert "not a total run cost" in md


def test_missing_cost_tokens_omits_cost_table_rows() -> None:
    run = _discovery_run(metadata={"use_network": False, "candidate_count": 0})
    md = render_model_md(build_discovery_model_metadata(run))

    assert "## Indicative cost estimate" in md
    assert "No token usage recorded" in md
    assert "Lower-bound indicative USD" not in md


def test_ai_triage_failure_status() -> None:
    run = _discovery_run(
        metadata={
            "ai_triage_failed": True,
            "ai_triage_model": "frontier_discovery",
            "candidate_count": 0,
        },
        warnings=["AI triage failed for all batches"],
    )
    md = render_model_md(build_discovery_model_metadata(run))
    assert "> **Run status:** completed with warnings" in md


def test_render_omits_absolute_paths(tmp_path: Path) -> None:
    abs_out = tmp_path / "nested" / "discovery-run.json"
    abs_out.parent.mkdir(parents=True)
    run = _discovery_run()
    md = render_model_md(build_discovery_model_metadata(run, output_path=abs_out))

    assert str(abs_out) not in md
    assert str(tmp_path) not in md


def test_save_discovery_run_writes_model_md(tmp_path: Path) -> None:
    output = tmp_path / "discovery-run.json"
    save_discovery_run(_discovery_run(), output)

    model_md = output.parent / MODEL_MD_FILENAME
    assert model_md.is_file()
    text = model_md.read_text(encoding="utf-8")
    assert "discovery-run.json" in text
    assert "/Users/" not in text


def test_save_source_bundle_writes_model_md(tmp_path: Path) -> None:
    bundle = SourceBundle(
        bundle_id="bundle-1",
        category_id="equine_passports",
        created_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        principal_sources=[CandidateSource(source_id="p1", title="Principal")],
        relationships=[],
    )
    output = tmp_path / "source-bundle.json"
    save_source_bundle(bundle, output)

    assert (output.parent / MODEL_MD_FILENAME).is_file()


def test_output_tokens_only_when_present() -> None:
    run = _discovery_run(
        metadata={
            "llm_usage": {
                "estimated_input_tokens_total": 1000,
                "estimated_input_tokens_live_only": 1000,
                "estimated_output_tokens": 250,
            }
        }
    )
    md = render_model_md(build_discovery_model_metadata(run))
    assert "Estimated output tokens" in md


def test_save_related_run_writes_model_md(tmp_path: Path) -> None:
    run = RelatedSourceExpansionRun(
        run_id="rel-1",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        category_id="equine_passports",
        metadata={"use_ai_triage": False, "related_source_count": 0},
    )
    output = tmp_path / "related-sources-run.json"
    save_related_source_expansion_run(run, output)
    assert (output.parent / MODEL_MD_FILENAME).is_file()


def test_source_register_metadata(tmp_path: Path) -> None:
    register = SourceRegister(
        register_id="reg-1",
        category_id="equine_passports",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        accepted_sources=[CandidateSource(source_id="a1", title="Accepted")],
        rejected_sources=[],
        parked_sources=[],
    )
    from law_discovery.models import save_source_register

    output = tmp_path / "source-register.json"
    save_source_register(register, output)
    text = (output.parent / MODEL_MD_FILENAME).read_text(encoding="utf-8")
    assert "source-register" in text
    assert "Accepted Sources" in text
