from pathlib import Path

import pytest
from law_proposition_extractor_pipeline.source_bundle_intake import (
    FullLawDiscoveryBundleRejectedError,
    IntakeBundleSelection,
    ada_entry_to_case_source,
    detect_input_kind,
    format_intake_summary_lines,
    intake_plan_to_dict,
    is_full_ada_bundle,
    is_law_proposition_extractor_intake_bundle,
    load_source_bundle,
    materialize_case_from_intake_bundle,
    plan_intake_bundle_dry_run,
    resolve_case_output_paths,
    resolve_selected_sections,
    select_case_sources,
    write_materialized_case,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _ada_entry(source_id: str, uri: str, *, review_status: str = "accepted") -> dict:
    return {
        "source_id": source_id,
        "title": f"Instrument {source_id}",
        "citation": None,
        "source_type": "uksi",
        "canonical_uri": uri,
        "source_system": "lex",
        "jurisdiction_extent": ["England"],
        "relationship_to_category": "directly_regulates",
        "review_status": review_status,
    }


def _intake_bundle(
    *,
    principals: list[dict] | None = None,
    amending: list[dict] | None = None,
    revocations: list[dict] | None = None,
    contextual: list[dict] | None = None,
    rejected: list[dict] | None = None,
    with_intake_metadata: bool = True,
) -> dict:
    bundle: dict = {
        "bundle_id": "bundle-test",
        "category_id": "test_category",
        "created_at": "2026-06-01T00:00:00Z",
        "principal_sources": principals or [],
        "amending_sources": amending or [],
        "revocation_sources": revocations or [],
        "contextual_sources": contextual or [],
        "rejected_sources": rejected or [],
        "relationships": [],
    }
    if with_intake_metadata:
        bundle["metadata"] = {
            "source_register_id": "law-discovery-register-test",
            "intake": {
                "kind": "judit_intake",
                "filter_policy": {
                    "principal_sources": ["accepted"],
                    "amending_sources": ["accepted"],
                    "contextual_sources": [],
                    "principal_only": False,
                },
                "excluded_counts": {
                    "contextual_sources": len(contextual or []),
                    "rejected_sources": len(rejected or []),
                },
            },
        }
    return bundle


def test_is_law_proposition_extractor_intake_bundle_and_filter_policy_logging() -> None:
    bundle = _intake_bundle(
        principals=[_ada_entry("lex-a", "http://www.legislation.gov.uk/id/uksi/2020/1")]
    )
    assert is_law_proposition_extractor_intake_bundle(bundle) is True
    assert is_full_ada_bundle(bundle) is False

    plan = plan_intake_bundle_dry_run(bundle, IntakeBundleSelection())
    assert plan.intake_kind == "judit_intake"
    assert plan.filter_policy is not None
    assert any("judit_intake" in line for line in plan.log_lines)
    assert any("filter policy" in line.lower() for line in plan.log_lines)


def test_default_selection_is_principal_only() -> None:
    bundle = _intake_bundle(
        principals=[
            _ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1"),
            _ada_entry("lex-p2", "http://www.legislation.gov.uk/id/uksi/2020/2"),
        ],
        amending=[_ada_entry("lex-a1", "http://www.legislation.gov.uk/id/uksi/2020/3")],
        revocations=[_ada_entry("lex-r1", "http://www.legislation.gov.uk/id/uksi/2020/4")],
    )
    selection = IntakeBundleSelection()
    assert resolve_selected_sections(selection) == ["principal_sources"]

    sources, by_role = select_case_sources(bundle, selection)
    assert len(sources) == 2
    assert by_role == {"principal": 2}
    assert all(src["metadata"]["ada_source_bundle"]["bundle_role"] == "principal" for src in sources)


def test_include_amendments_and_revocations_flags() -> None:
    bundle = _intake_bundle(
        principals=[_ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1")],
        amending=[_ada_entry("lex-a1", "http://www.legislation.gov.uk/id/uksi/2020/2")],
        revocations=[_ada_entry("lex-r1", "http://www.legislation.gov.uk/id/uksi/2020/3")],
    )
    selection = IntakeBundleSelection(
        principal_only=False,
        include_amendments=True,
        include_revocations=True,
    )
    assert resolve_selected_sections(selection) == [
        "principal_sources",
        "amending_sources",
        "revocation_sources",
    ]
    sources, by_role = select_case_sources(bundle, selection)
    assert len(sources) == 3
    assert by_role == {"principal": 1, "amending": 1, "revocation": 1}


def test_max_sources_caps_selection() -> None:
    bundle = _intake_bundle(
        principals=[
            _ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1"),
            _ada_entry("lex-p2", "http://www.legislation.gov.uk/id/uksi/2020/2"),
            _ada_entry("lex-p3", "http://www.legislation.gov.uk/id/uksi/2020/3"),
        ],
    )
    sources, _ = select_case_sources(bundle, IntakeBundleSelection(max_sources=2))
    assert len(sources) == 2


def test_full_ada_bundle_refused_without_allow_flag() -> None:
    bundle = _intake_bundle(
        principals=[_ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1")],
        contextual=[_ada_entry("lex-c1", "http://www.legislation.gov.uk/id/uksi/1999/9")],
        with_intake_metadata=False,
    )
    assert is_full_ada_bundle(bundle) is True
    assert detect_input_kind(bundle) == "full_ada"

    with pytest.raises(FullLawDiscoveryBundleRejectedError, match="Full reviewed Law Discovery bundle"):
        select_case_sources(bundle, IntakeBundleSelection())


def test_full_ada_bundle_allowed_but_not_processed_wholesale() -> None:
    bundle = _intake_bundle(
        principals=[
            _ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1"),
            _ada_entry("lex-p2", "http://www.legislation.gov.uk/id/uksi/2020/2"),
        ],
        amending=[_ada_entry("lex-a1", "http://www.legislation.gov.uk/id/uksi/2020/3")],
        contextual=[_ada_entry("lex-c1", "http://www.legislation.gov.uk/id/uksi/1999/9")] * 5,
        rejected=[_ada_entry("lex-x1", "http://www.legislation.gov.uk/id/uksi/1998/8")],
        with_intake_metadata=False,
    )
    selection = IntakeBundleSelection(allow_full_law_discovery_bundle=True)
    plan = plan_intake_bundle_dry_run(bundle, selection)
    payload = intake_plan_to_dict(plan)

    assert payload["section_counts"]["contextual_sources"] == 5
    assert payload["section_counts"]["rejected_sources"] == 1
    assert payload["selected_source_count"] == 2
    assert payload["selected_by_role"] == {"principal": 2}
    assert payload["section_counts"]["amending_sources"] == 1


def test_judit_intake_with_populated_contextual_is_refused() -> None:
    bundle = _intake_bundle(
        principals=[_ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1")],
        contextual=[_ada_entry("lex-c1", "http://www.legislation.gov.uk/id/uksi/1999/9")],
        with_intake_metadata=True,
    )
    with pytest.raises(FullLawDiscoveryBundleRejectedError):
        select_case_sources(bundle, IntakeBundleSelection())


def test_dry_run_reports_counts_and_estimated_batches() -> None:
    bundle = _intake_bundle(
        principals=[
            _ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1"),
            _ada_entry("lex-p2", "http://www.legislation.gov.uk/id/uksi/2020/2"),
        ],
        amending=[_ada_entry("lex-a1", "http://www.legislation.gov.uk/id/uksi/2020/3")],
    )
    plan = plan_intake_bundle_dry_run(bundle, IntakeBundleSelection(), avg_fragments_per_source=4)
    assert plan.selected_source_count == 2
    assert plan.estimated_extraction_batches_lower_bound == 8
    assert plan.section_counts["amending_sources"] == 1


def test_ada_entry_maps_to_legislation_case_source() -> None:
    entry = _ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/15")
    bundle = _intake_bundle()
    case_source = ada_entry_to_case_source(entry, bundle_role="principal", bundle=bundle)
    assert case_source["authority"] == "legislation_gov_uk"
    assert case_source["authority_source_id"] == "uksi/2020/15"
    assert case_source["provenance"] == "law_discovery.law_proposition_extractor_intake"
    assert case_source["metadata"]["ada_source_bundle"]["bundle_role"] == "principal"


def test_materialize_case_from_intake_bundle_shape() -> None:
    bundle = _intake_bundle(
        principals=[_ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1")],
    )
    case = materialize_case_from_intake_bundle(bundle, IntakeBundleSelection())
    assert case["topic"]["name"] == "test category"
    assert case["cluster"]["name"] == "test_category"
    assert len(case["sources"]) == 1
    assert case["ada_intake_ref"]["intake_kind"] == "judit_intake"


def test_load_default_intake_bundle_fixture_file() -> None:
    path = _REPO_ROOT / "source-bundle-law-proposition-extractor-intake-principal-only.json"
    if not path.is_file():
        pytest.skip("repo intake fixture missing")
    bundle = load_source_bundle(path)
    plan = plan_intake_bundle_dry_run(bundle, IntakeBundleSelection())
    assert plan.intake_kind == "judit_intake"
    assert plan.selected_source_count == 10
    assert plan.section_counts["contextual_sources"] == 0


def test_reviewed_bundle_dry_run_refused_by_default() -> None:
    path = _REPO_ROOT / "source-bundle-reviewed.json"
    if not path.is_file():
        pytest.skip("repo reviewed fixture missing")
    bundle = load_source_bundle(path)
    assert is_full_ada_bundle(bundle) is True
    with pytest.raises(FullLawDiscoveryBundleRejectedError):
        plan_intake_bundle_dry_run(bundle, IntakeBundleSelection())


def test_reviewed_bundle_with_allow_flag_selects_principals_only() -> None:
    path = _REPO_ROOT / "source-bundle-reviewed.json"
    if not path.is_file():
        pytest.skip("repo reviewed fixture missing")
    bundle = load_source_bundle(path)
    plan = plan_intake_bundle_dry_run(
        bundle,
        IntakeBundleSelection(allow_full_law_discovery_bundle=True),
    )
    assert plan.selected_source_count == 24
    assert plan.section_counts["contextual_sources"] == 93
    assert plan.section_counts["rejected_sources"] == 16
    assert plan.selected_by_role == {"principal": 24}


def test_format_intake_summary_lines_includes_filter_policy_keys() -> None:
    bundle = _intake_bundle(
        principals=[_ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1")],
    )
    bundle["metadata"]["intake"]["filter_policy"] = {
        "principal_only": True,
        "max_principal_sources": 5,
        "priority_policy": "current_core",
        "exclude_jurisdictions": ["Northern Ireland"],
    }
    plan = plan_intake_bundle_dry_run(bundle, IntakeBundleSelection())
    lines = format_intake_summary_lines(bundle, plan, selection=IntakeBundleSelection())
    assert "category_id: test_category" in lines
    assert "intake.kind: judit_intake" in lines
    assert "principal_only: True" in lines
    assert "max_principal_sources: 5" in lines
    assert "priority_policy: current_core" in lines
    assert "exclude_jurisdictions: ['Northern Ireland']" in lines


def test_write_materialized_case_to_directory(tmp_path: Path) -> None:
    bundle = _intake_bundle(
        principals=[_ada_entry("lex-p1", "http://www.legislation.gov.uk/id/uksi/2020/1")],
    )
    case = materialize_case_from_intake_bundle(bundle, IntakeBundleSelection())
    out_dir = tmp_path / "runs" / "test-case"
    case_json = write_materialized_case(case, out_dir)
    assert case_json == out_dir / "case.json"
    assert case_json.is_file()
    case_dir, resolved = resolve_case_output_paths(out_dir)
    assert case_dir == out_dir
    assert resolved == case_json


def test_full_intake_bundle_default_not_wholesale() -> None:
    path = _REPO_ROOT / "source-bundle-law-proposition-extractor-intake.json"
    if not path.is_file():
        pytest.skip("repo intake fixture missing")
    bundle = load_source_bundle(path)
    plan = plan_intake_bundle_dry_run(bundle, IntakeBundleSelection())
    assert plan.selected_source_count == 24
    assert plan.section_counts["amending_sources"] == 25
    assert plan.section_counts["contextual_sources"] == 0

    with_amendments = plan_intake_bundle_dry_run(
        bundle,
        IntakeBundleSelection(include_amendments=True),
    )
    assert with_amendments.selected_source_count == 49
