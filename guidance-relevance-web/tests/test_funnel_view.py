from guidance_relevance_web.funnel_view import build_funnel_view, view_from_journal


def test_preview_passes_term_hits_onto_would_route_node():
    stages = [
        {"stage": "empty_body", "n": 1, "urls": [{"url": "https://www.gov.uk/e", "title": "E"}]},
        {
            "stage": "would_route",
            "n": 2,
            "urls": [{
                "url": "https://www.gov.uk/s",
                "title": "S",
                "lexicon_hits": ["slurry", "lagoon"],
            }],
            "term_hits": [{"term": "slurry", "n": 2}, {"term": "lagoon", "n": 1}],
        },
    ]
    view = build_funnel_view(stages, {"would_route": 2, "empty_body": 1})
    routed = next(n for n in view["sankey"]["nodes"] if n["id"] == "would_route")
    assert routed["term_hits"] == [{"term": "slurry", "n": 2}, {"term": "lagoon", "n": 1}]
    assert routed["urls"][0]["lexicon_hits"] == ["slurry", "lagoon"]
    preview_in = next(n for n in view["sankey"]["nodes"] if n["id"] == "preview_in")
    assert "term_hits" not in preview_in


def test_preview_omits_lexicon_miss_and_zeros():
    stages = [
        {"stage": "missing_body", "n": 0, "urls": []},
        {"stage": "empty_body", "n": 1, "urls": [{"url": "https://www.gov.uk/e", "title": "E"}]},
        {
            "stage": "lexicon_miss",
            "n": 22544,
            "urls": [{"url": "https://www.gov.uk/x", "title": "X"}],
        },
        {"stage": "would_route", "n": 544, "urls": [{"url": "https://www.gov.uk/s", "title": "S"}]},
    ]
    view = build_funnel_view(stages, {"would_route": 544, "lexicon_miss": 22544, "empty_body": 1})
    assert [s["stage"] for s in view["stages"]] == ["empty_body", "lexicon_miss", "would_route"]
    assert [c["stage"] for c in view["chips"]] == ["lexicon_miss"]
    assert view["chips"][0]["hidden"] is True
    ids = [n["id"] for n in view["sankey"]["nodes"]]
    assert "lexicon_miss" not in ids
    assert "missing_body" not in ids
    assert ids == ["preview_in", "empty_body", "would_route"]
    assert view["sankey"]["links"] == [
        {"source": "preview_in", "target": "empty_body", "n": 1},
        {"source": "preview_in", "target": "would_route", "n": 544},
    ]
    assert view["caption"] == "544 would go to the model"


def test_preview_scope_filters_are_sequential_columns():
    stages = [
        {
            "stage": "organisation_miss",
            "n": 3,
            "urls": [{"url": "https://www.gov.uk/fish", "title": "F"}],
        },
        {
            "stage": "document_type_miss",
            "n": 1,
            "urls": [{"url": "https://www.gov.uk/empty", "title": "E"}],
        },
        {"stage": "lexicon_miss", "n": 10, "urls": []},
        {"stage": "would_route", "n": 2, "urls": [{"url": "https://www.gov.uk/s", "title": "S"}]},
    ]
    view = build_funnel_view(stages, {
        "corpus_pages": 16,
        "input_pages": 12,
        "organisation_miss": 3,
        "document_type_miss": 1,
        "lexicon_miss": 10,
        "would_route": 2,
    })
    ids = [n["id"] for n in view["sankey"]["nodes"]]
    assert ids == [
        "organisation_pass",
        "document_type_pass",
        "would_route",
    ]
    assert view["sankey"]["links"] == [
        {"source": "organisation_pass", "target": "document_type_pass", "n": 12},
        {"source": "document_type_pass", "target": "would_route", "n": 2},
    ]
    assert [c["stage"] for c in view["chips"]] == ["organisation_miss", "document_type_miss", "lexicon_miss"]
    assert view["chips"][0]["hidden"] is False
    assert view["caption"] == (
        "16 on the index → 13 matching organisation → 12 matching document type → 2 would go to the model"
    )


def test_finished_run_sankey_is_the_llm_flow():
    doc = {
        "counts": {
            "input_pages": 23454,
            "missing_body": 0,
            "empty_body": 366,
            "lexicon_miss": 22544,
            "cosine_miss": 0,
            "lexicon_hit": 544,
            "pass1_false": 366,
            "pass1_true": 178,
            "pass2_dropped": 45,
            "pass2_kept": 133,
            "pass2_unadjudicated": 0,
        },
        "missing_body": [],
        "empty_body": [{"url": "https://www.gov.uk/empty", "title": "Empty"}],
        "lexicon_miss": [{"url": "https://www.gov.uk/miss", "title": "Miss"}],
        "cosine_miss": [],
        "pass1_false": [
            {
                "url": "https://www.gov.uk/no",
                "title": "No",
                "pass1_reason": "not slurry",
                "lexicon_hits": ["Animal by-products"],
            },
        ],
        "pass2_drop": [
            {
                "url": "https://www.gov.uk/drop",
                "title": "Drop",
                "pass2_reason": "incidental",
                "lexicon_hits": ["Slurry", "Animal by-products"],
            },
        ],
        "pass2_keep": [{
            "url": "https://www.gov.uk/keep",
            "title": "Keep",
            "lexicon_hits": ["Slurry"],
        }],
        "pass2_unadjudicated": [],
    }
    view = view_from_journal(doc)
    chips = {c["stage"]: c for c in view["chips"]}
    assert set(chips) == {"empty_body", "lexicon_miss"}
    assert chips["lexicon_miss"]["hidden"] is True
    assert chips["empty_body"]["hidden"] is False
    ids = [n["id"] for n in view["sankey"]["nodes"]]
    assert ids == ["lexicon_hit", "pass1_false", "pass1_true", "pass2_drop", "pass2_keep"]
    assert view["caption"] == "544 keyword hits → 178 first-pass yes → 133 kept"
    by_id = {n["id"]: n for n in view["sankey"]["nodes"]}
    assert by_id["lexicon_hit"]["label"] == "Input Shortlist"
    assert by_id["pass1_true"]["label"] == "Filtered by LLM Inclusion Rules"
    assert by_id["pass1_false"]["label"] == "Dropped"
    assert by_id["pass2_keep"]["label"] == "Filtered by LLM Exclusion Rules"
    assert by_id["pass2_drop"]["label"] == "Dropped"
    assert by_id["pass2_keep"]["urls"][0]["url"] == "https://www.gov.uk/keep"
    assert by_id["pass2_keep"]["urls"][0]["lexicon_hits"] == ["Slurry"]
    assert by_id["pass1_false"]["term_hits"] == [{"term": "Animal by-products", "n": 1}]
    assert by_id["pass2_drop"]["term_hits"] == [
        {"term": "Slurry", "n": 1},
        {"term": "Animal by-products", "n": 1},
    ]
    assert by_id["lexicon_hit"]["term_hits"] == [
        {"term": "Animal by-products", "n": 2},
        {"term": "Slurry", "n": 2},
    ]
    assert "cheap" not in by_id["pass1_false"]["meaning"].lower()
    assert by_id["pass1_false"]["meaning"].startswith("A first read")
    assert by_id["pass1_true"]["meaning"].startswith("A first read thought")
    assert by_id["pass2_keep"]["meaning"].startswith("Both reads agreed")
    assert chips["lexicon_miss"]["meaning"].startswith("None of your topic words")


def test_finished_run_prepends_scope_survivor_chain():
    doc = {
        "counts": {
            "input_pages": 12,
            "lexicon_hit": 2,
            "pass1_false": 1,
            "pass1_true": 1,
            "pass2_dropped": 0,
            "pass2_kept": 1,
            "pass2_unadjudicated": 0,
        },
        "missing_body": [],
        "empty_body": [],
        "lexicon_miss": [{"url": "https://www.gov.uk/miss", "title": "Miss"}],
        "cosine_miss": [],
        "pass1_false": [{"url": "https://www.gov.uk/no", "title": "No"}],
        "pass2_drop": [],
        "pass2_keep": [{"url": "https://www.gov.uk/keep", "title": "Keep"}],
        "pass2_unadjudicated": [],
    }
    view = view_from_journal(doc, scope={
        "organisations": ["environment-agency"],
        "document_types": ["guidance"],
        "counts": {
            "corpus_pages": 16,
            "input_pages": 12,
            "organisation_miss": 3,
            "document_type_miss": 1,
            "organisation_filter": True,
            "document_type_filter": True,
        },
        "stages": [
            {
                "stage": "organisation_miss",
                "n": 3,
                "urls": [{"url": "https://www.gov.uk/fish", "title": "F"}],
            },
            {
                "stage": "organisation_pass",
                "n": 13,
                "urls": [{"url": "https://www.gov.uk/keep", "title": "Keep"}],
            },
            {
                "stage": "document_type_miss",
                "n": 1,
                "urls": [{"url": "https://www.gov.uk/html", "title": "H"}],
            },
            {
                "stage": "document_type_pass",
                "n": 12,
                "urls": [{"url": "https://www.gov.uk/keep", "title": "Keep"}],
            },
        ],
    })
    ids = [n["id"] for n in view["sankey"]["nodes"]]
    assert ids == [
        "organisation_pass",
        "document_type_pass",
        "lexicon_hit",
        "pass1_false",
        "pass1_true",
        "pass2_keep",
    ]
    assert {"source": "organisation_pass", "target": "document_type_pass", "n": 12} in view["sankey"]["links"]
    assert {"source": "document_type_pass", "target": "lexicon_hit", "n": 2} in view["sankey"]["links"]
    chips = {c["stage"]: c for c in view["chips"]}
    assert chips["organisation_miss"]["n"] == 3
    assert chips["organisation_miss"]["hidden"] is False
    assert chips["document_type_miss"]["n"] == 1
    assert view["caption"].startswith("16 on the index → 13 matching organisation → 12 matching document type")


def test_zero_drop_type_gate_still_gets_a_column():
    stages = [
        {"stage": "organisation_miss", "n": 3, "urls": []},
        {"stage": "organisation_pass", "n": 1, "urls": [{"url": "https://www.gov.uk/s", "title": "S"}]},
        {"stage": "document_type_miss", "n": 0, "urls": []},
        {"stage": "document_type_pass", "n": 1, "urls": [{"url": "https://www.gov.uk/s", "title": "S"}]},
        {"stage": "would_route", "n": 1, "urls": [{"url": "https://www.gov.uk/s", "title": "S"}]},
    ]
    view = build_funnel_view(stages, {
        "corpus_pages": 4,
        "input_pages": 1,
        "organisation_filter": True,
        "document_type_filter": True,
        "organisation_miss": 3,
        "document_type_miss": 0,
        "would_route": 1,
    })
    assert [n["id"] for n in view["sankey"]["nodes"]] == [
        "organisation_pass", "document_type_pass", "would_route",
    ]
    assert [c["stage"] for c in view["chips"]] == ["organisation_miss"]
    assert view["caption"] == (
        "4 on the index → 1 matching organisation → 1 matching document type → 1 would go to the model"
    )
