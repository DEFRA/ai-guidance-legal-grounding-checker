from law_proposition_extractor_pipeline.demo import build_demo_bundle


def test_demo_bundle_shape() -> None:
    bundle = build_demo_bundle(use_llm=False)

    assert bundle["topic"]["name"] == "Movement record keeping"
    assert len(bundle["sources"]) == 2
    assert len(bundle["source_fragments"]) == 2
    assert len(bundle["source_parse_traces"]) == 2
    assert len(bundle["proposition_extraction_traces"]) == len(bundle["propositions"])
    assert len(bundle["propositions"]) >= 2
    assert bundle["proposition_inventory"]["proposition_count"] == len(bundle["propositions"])
    assert len(bundle["divergence_assessments"]) == 1
    assert bundle["divergence_assessments"][0]["divergence_type"] in {
        "institutional",
        "structural",
        "none",
        "procedural",
        "textual",
    }


def test_realistic_demo_bundle_has_multiple_comparisons() -> None:
    bundle = build_demo_bundle(use_llm=False, case_name="realistic")
    divergence_types = {item["divergence_type"] for item in bundle["divergence_assessments"]}

    assert len(bundle["divergence_assessments"]) >= 2
    assert "institutional" in divergence_types
    assert any(item != "institutional" for item in divergence_types)


def test_single_jurisdiction_demo_bundle_inventory_mode() -> None:
    bundle = build_demo_bundle(use_llm=False, case_name="single")

    assert bundle["run"]["workflow_mode"] == "single_jurisdiction"
    assert len(bundle["sources"]) == 1
    assert len(bundle["propositions"]) >= 1
    assert bundle["proposition_inventory"]["proposition_count"] == len(bundle["propositions"])
    assert len(bundle["divergence_assessments"]) == 0
