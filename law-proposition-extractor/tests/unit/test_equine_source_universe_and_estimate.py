"""Staged equine source universe, profiles, and corpus run estimates."""

from __future__ import annotations

from pathlib import Path

from law_proposition_extractor_pipeline.corpus_run_estimate import estimate_corpus_run_from_case
from law_proposition_extractor_pipeline.equine_source_universe import (
    load_equine_source_universe,
    materialize_case_for_profile,
    materialize_case_from_universe_path,
    profile_member_ids,
    universe_instrument_count,
)
from law_proposition_extractor_pipeline.runner import build_bundle_from_case

REPO_ROOT = Path(__file__).resolve().parents[2]


def _mini_case_with_sources(*sources: dict[str, object]) -> dict[str, object]:
    return {
        "topic": {
            "name": "Equine scope",
            "description": "test",
            "subject_tags": ["equine"],
        },
        "cluster": {
            "name": "Test cluster",
            "description": "test",
        },
        "sources": list(sources),
    }


def test_universe_has_21_instruments() -> None:
    u = load_equine_source_universe(REPO_ROOT / "examples" / "equine_source_universe.json")
    assert universe_instrument_count(u) == 21


def test_passport_profile_excludes_tarpr_and_official_controls() -> None:
    u = load_equine_source_universe(REPO_ROOT / "examples" / "equine_source_universe.json")
    mids = profile_member_ids(u, "equine_passport_identification_v0_1")
    assert "uksi/2011/1197" not in mids
    assert "uksi/2020/1481" not in mids
    assert "uksi/2020/1631" not in mids
    assert "uksi/2018/761" in mids


def test_movement_profile_excludes_pure_passport_baselines() -> None:
    u = load_equine_source_universe(REPO_ROOT / "examples" / "equine_source_universe.json")
    mids = profile_member_ids(u, "equine_movement_import_trade_v0_1")
    assert "eur/2015/262" not in mids
    assert "uksi/2018/761" not in mids
    assert "uksi/2011/1197" in mids


def test_candidate_universe_case_builds_without_ingested_sources() -> None:
    case = materialize_case_from_universe_path(
        REPO_ROOT / "examples" / "equine_source_universe.json",
        "equine_full_candidate_universe",
    )
    assert case.get("sources") == []
    assert len(case.get("source_family_candidates") or []) == 21
    bundle = build_bundle_from_case(
        case,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    assert len(bundle.get("sources") or bundle.get("source_records") or []) == 0


def test_estimate_offline_sizing_has_no_live_llm_path() -> None:
    case = materialize_case_from_universe_path(
        REPO_ROOT / "examples" / "equine_source_universe.json",
        "equine_passport_identification_v0_1",
    )
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier", offline_chars_per_instrument=2000)
    assert est["source_count"] == 11
    assert est["estimated_llm_invocations"] >= 1
    assert est["mode"] == "offline_synthetic"
    assert est["largest_fragment_source_id"] is not None
    assert est["largest_fragment_title"] is not None
    assert est["largest_fragment_locator"] is not None
    assert est["largest_fragment_chars"] > 0
    assert est["largest_fragment_estimated_input_tokens"] > 0
    assert est["estimated_input_tokens_total"] > 0
    assert est["average_estimated_input_tokens_per_call"] > 0
    assert isinstance(est["top_large_fragments"], list)
    assert isinstance(est["top_contributing_sources"], list)


def test_estimate_top_large_fragments_sorted_descending() -> None:
    case = _mini_case_with_sources(
        {
            "id": "src-small",
            "authority": "case_file",
            "title": "Small source",
            "jurisdiction": "UK",
            "citation": "SMALL",
            "kind": "instrument",
            "text": "a" * 1_200,
            "metadata": {"disable_fragment_expansion": True},
        },
        {
            "id": "src-large",
            "authority": "case_file",
            "title": "Large source",
            "jurisdiction": "UK",
            "citation": "LARGE",
            "kind": "instrument",
            "text": "b" * 6_000,
            "metadata": {"disable_fragment_expansion": True},
        },
    )
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier")
    top = est["top_large_fragments"]
    assert len(top) == 2
    assert top[0]["source_id"] == "src-large"
    assert top[0]["estimated_input_tokens"] >= top[1]["estimated_input_tokens"]


def test_estimate_caution_recommendation_when_calls_are_huge() -> None:
    case = materialize_case_from_universe_path(
        REPO_ROOT / "examples" / "equine_source_universe.json",
        "equine_passport_identification_v0_1",
    )
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier", offline_chars_per_instrument=450_000)
    assert "Run with caution: at least one extraction call is very large." in est["recommendations"]


def test_estimate_makes_no_llm_calls(monkeypatch) -> None:
    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("LLM call was attempted in estimate mode")

    monkeypatch.setattr("law_proposition_extractor_pipeline.extract.JuditLLMClient.complete_text", _raise_if_called)
    case = materialize_case_from_universe_path(
        REPO_ROOT / "examples" / "equine_source_universe.json",
        "equine_passport_identification_v0_1",
    )
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier", offline_chars_per_instrument=2_000)
    assert est["estimated_llm_invocations"] >= 1


def test_readiness_counts_universe_vs_profile_sources() -> None:
    u = load_equine_source_universe(REPO_ROOT / "examples" / "equine_source_universe.json")
    passport = materialize_case_for_profile(u, "equine_passport_identification_v0_1")
    assert universe_instrument_count(u) == 21
    assert len(passport["sources"]) == 11


def test_coverage_source_roles_from_universe_metadata() -> None:
    from law_proposition_extractor_pipeline.equine_corpus_workflow import build_source_coverage_rows

    case = materialize_case_from_universe_path(
        REPO_ROOT / "examples" / "equine_source_universe.json",
        "equine_passport_identification_v0_1",
    )
    bundle = build_bundle_from_case(
        case,
        use_llm=False,
        extraction_mode="heuristic",
        extraction_fallback="mark_needs_review",
        divergence_reasoning="none",
    )
    rows = build_source_coverage_rows(bundle)
    by_id = {r["source_id"]: r for r in rows}
    assert by_id["equine-uni-uksi-2018-761"]["source_role"] == "required_core"


def test_estimate_legislation_structural_locators_for_large_schedule() -> None:
    schedule_blob = " ".join(["Substituted text for Schedule 1 paragraph 3."] * 600)
    xml_payload = f"""
    <Legislation DocumentURI="http://www.legislation.gov.uk/ssi/2019/71">
      <Title>The Animal Health (EU Exit) (Scotland) (Amendment) Regulations 2019</Title>
      <Body id="body">
        <P1 id="regulation-1">
          <Pnumber>1.</Pnumber>
          <Text>Citation and commencement.</Text>
        </P1>
        <P1 id="schedule-1">
          <Title>Schedule 1</Title>
          <Text>Amendments.</Text>
        </P1>
        <P2 id="schedule-1-paragraph-3">
          <Pnumber>3.</Pnumber>
          <Text>{schedule_blob}</Text>
        </P2>
      </Body>
    </Legislation>
    """

    def fake_fetch(_source_url: str) -> tuple[str, dict[str, object]]:
        return xml_payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(xml_payload),
        }

    case = _mini_case_with_sources(
        {
            "id": "equine-uni-ssi-2019-71",
            "authority": "legislation_gov_uk",
            "authority_source_id": "ssi/2019/71",
            "version_id": "2023-05-18",
            "title": "The Animal Health (EU Exit) (Scotland) (Amendment) Regulations 2019",
            "jurisdiction": "Scotland",
            "citation": "SSI 2019/71",
            "kind": "ssi",
        }
    )
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier", fetch_xml=fake_fetch)
    locators = [row["locator"] for row in est["top_large_fragments"]]
    assert any(locator.startswith("schedule:1:paragraph:3") for locator in locators)
    assert any(locator.startswith("regulation:1") for locator in locators)
    assert "xml:regulation-1" not in locators
    assert est["largest_fragment_chars"] < len(schedule_blob) + 500


def test_estimate_very_large_cost_class_emits_staged_recommendation() -> None:
    many_sources = [
        {
            "id": f"src-{i:03d}",
            "authority": "case_file",
            "title": f"Source {i}",
            "jurisdiction": "UK",
            "citation": f"CITE-{i}",
            "kind": "instrument",
            "text": "Operators must maintain records.",
            "metadata": {"disable_fragment_expansion": True},
        }
        for i in range(60)
    ]
    case = _mini_case_with_sources(*many_sources)
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier")
    assert est["cost_class"] == "very_large"
    assert est["jobs_over_context_budget"] == 0
    assert "Split this profile or run staged subsets before frontier extraction." in est["recommendations"]


def test_estimate_high_invocation_count_emits_strong_staging_recommendation() -> None:
    many_sources = [
        {
            "id": f"src-hi-{i:03d}",
            "authority": "case_file",
            "title": f"High Invocation Source {i}",
            "jurisdiction": "UK",
            "citation": f"HI-{i}",
            "kind": "instrument",
            "text": "Operators must maintain records.",
            "metadata": {"disable_fragment_expansion": True},
        }
        for i in range(170)
    ]
    case = _mini_case_with_sources(*many_sources)
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier")
    assert est["estimated_llm_invocations"] > 150
    assert "Staged run strongly recommended: estimated model invocation count is very high." in est[
        "recommendations"
    ]
    assert "Run with caution: this profile may make many model calls." in est["recommendations"]


def test_estimate_top_contributing_sources_sorted_by_total_tokens() -> None:
    case = _mini_case_with_sources(
        {
            "id": "src-small-tokens",
            "authority": "case_file",
            "title": "Small",
            "jurisdiction": "UK",
            "citation": "S",
            "kind": "instrument",
            "text": "x " * 200,
            "metadata": {"disable_fragment_expansion": True},
        },
        {
            "id": "src-large-tokens",
            "authority": "case_file",
            "title": "Large",
            "jurisdiction": "UK",
            "citation": "L",
            "kind": "instrument",
            "text": "y " * 6000,
            "metadata": {"disable_fragment_expansion": True},
        },
    )
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier")
    top_sources = est["top_contributing_sources"]
    assert len(top_sources) == 2
    assert top_sources[0]["source_id"] == "src-large-tokens"
    assert top_sources[0]["estimated_input_tokens_total"] >= top_sources[1]["estimated_input_tokens_total"]
    assert est["estimated_input_tokens_total"] >= top_sources[0]["estimated_input_tokens_total"]


def test_staged_passport_profiles_estimate_smaller_than_umbrella_profile() -> None:
    universe = load_equine_source_universe(REPO_ROOT / "examples" / "equine_source_universe.json")
    umbrella_case = materialize_case_for_profile(universe, "equine_passport_identification_v0_1")
    umbrella_est = estimate_corpus_run_from_case(
        umbrella_case,
        extraction_mode="frontier",
        offline_chars_per_instrument=2_000,
    )
    umbrella_calls = int(umbrella_est["estimated_llm_invocations"])

    staged_profiles = [
        "equine_passport_eu_2015_262_v0_1",
        "equine_passport_england_ukwide_v0_1",
        "equine_passport_devolved_v0_1",
    ]
    for profile_id in staged_profiles:
        case = materialize_case_for_profile(universe, profile_id)
        est = estimate_corpus_run_from_case(
            case,
            extraction_mode="frontier",
            offline_chars_per_instrument=2_000,
        )
        assert int(est["estimated_llm_invocations"]) < umbrella_calls


def test_passport_only_staged_profiles_exclude_movement_import_trade_families() -> None:
    universe = load_equine_source_universe(REPO_ROOT / "examples" / "equine_source_universe.json")
    by_id = {str(row["id"]): row for row in universe["instruments"]}
    banned_families = {"movement_import_trade", "animal_products_trade", "official_controls"}
    staged_profiles = [
        "equine_passport_eu_2015_262_v0_1",
        "equine_passport_england_ukwide_v0_1",
        "equine_passport_devolved_v0_1",
    ]
    for profile_id in staged_profiles:
        for instrument_id in profile_member_ids(universe, profile_id):
            family = str(by_id[instrument_id].get("source_family") or "")
            assert family not in banned_families


def test_fetch_estimate_stays_llm_free_for_staged_passport_profile(monkeypatch) -> None:
    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("LLM call was attempted in estimate mode")

    def fake_fetch(_source_url: str) -> tuple[str, dict[str, object]]:
        payload = """
        <Legislation DocumentURI="http://www.legislation.gov.uk/eur/2015/262">
          <Title>Commission Implementing Regulation (EU) 2015/262</Title>
          <Body id="body">
            <P1 id="article-1">
              <Pnumber>Article 1</Pnumber>
              <Text>Passport and identification requirements for equidae.</Text>
            </P1>
          </Body>
        </Legislation>
        """
        return payload, {
            "status": 200,
            "content_type": "application/xml",
            "response_bytes": len(payload),
        }

    monkeypatch.setattr("law_proposition_extractor_pipeline.extract.JuditLLMClient.complete_text", _raise_if_called)
    case = materialize_case_from_universe_path(
        REPO_ROOT / "examples" / "equine_source_universe.json",
        "equine_passport_eu_2015_262_v0_1",
    )
    est = estimate_corpus_run_from_case(case, extraction_mode="frontier", fetch_xml=fake_fetch)
    assert est["estimated_llm_invocations"] >= 1
