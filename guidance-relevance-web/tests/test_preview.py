from conftest import _page, write_snapshot
from guidance_relevance_web.category import category_document, lexicon_document
from guidance_relevance_web.corpus import Corpus
from guidance_relevance_web.cost_estimate import estimate_usd
from guidance_relevance_web.preview import run_preview
from guidance_relevance_web.store import Store


def _slurry(description="slurry storage", terms=None):
    categories = category_document(
        name="slurry",
        description=description,
        exclusion_criteria="not sewage",
        keep_hints=[],
        drop_hints=[],
    )
    lexicons = lexicon_document("slurry", terms or ["slurry", "lagoon"])
    return categories, lexicons


def test_preview_attaches_lexicon_hits_per_url(settings, corpus_dir):
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
    )
    routed = next(n for n in result["sankey"]["nodes"] if n["id"] == "would_route")
    assert routed["term_hits"] == [
        {"term": "slurry", "n": 1},
        {"term": "lagoon", "n": 1},
    ]
    assert routed["urls"][0]["url"] == "https://www.gov.uk/guidance/storing-slurry"
    assert routed["urls"][0]["lexicon_hits"] == ["slurry", "lagoon"]
    miss = next(c for c in result["chips"] if c["stage"] == "lexicon_miss")
    assert "lexicon_hits" not in (miss["urls"][0] if miss["urls"] else {})
    assert "term_hits" not in miss


def test_preview_term_histogram_counts_every_routed_page(settings, tmp_path):
    root = tmp_path / "hits"
    write_snapshot(root, [
        _page(
            "https://www.gov.uk/guidance/a", "A", "only slurry here",
            organisations=["environment-agency"], primary="environment-agency",
        ),
        _page(
            "https://www.gov.uk/guidance/b", "B", "slurry and a lagoon",
            organisations=["environment-agency"], primary="environment-agency",
        ),
        _page(
            "https://www.gov.uk/guidance/c", "C", "nothing relevant",
            organisations=["environment-agency"], primary="environment-agency",
        ),
    ], "2026-09-08")
    corpus = Corpus(root)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
    )
    routed = next(n for n in result["sankey"]["nodes"] if n["id"] == "would_route")
    assert routed["n"] == 2
    assert routed["term_hits"] == [
        {"term": "slurry", "n": 2},
        {"term": "lagoon", "n": 1},
    ]
    by_url = {u["url"]: u["lexicon_hits"] for u in routed["urls"]}
    assert by_url["https://www.gov.uk/guidance/a"] == ["slurry"]
    assert by_url["https://www.gov.uk/guidance/b"] == ["slurry", "lagoon"]


def test_preview_keeps_rare_term_pages_outside_head_sample(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("guidance_relevance_web.preview.ROUTED_URL_CAP", 1)
    root = tmp_path / "rare"
    write_snapshot(root, [
        _page(
            "https://www.gov.uk/guidance/a", "A", "only slurry here",
            organisations=["environment-agency"], primary="environment-agency",
        ),
        _page(
            "https://www.gov.uk/guidance/b", "B", "a lagoon and nothing else",
            organisations=["environment-agency"], primary="environment-agency",
        ),
    ], "2026-09-08")
    corpus = Corpus(root)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
    )
    routed = next(n for n in result["sankey"]["nodes"] if n["id"] == "would_route")
    by_url = {u["url"]: u["lexicon_hits"] for u in routed["urls"]}
    assert by_url["https://www.gov.uk/guidance/a"] == ["slurry"]
    assert by_url["https://www.gov.uk/guidance/b"] == ["lagoon"]
    assert routed["term_hits"] == [
        {"term": "slurry", "n": 1},
        {"term": "lagoon", "n": 1},
    ]


def test_preview_wordsearch_counts(settings, corpus_dir):
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
    )
    assert result["counts"]["input_pages"] == 4
    assert result["counts"]["would_route"] == 1
    assert result["counts"]["empty_body"] == 1
    assert result["counts"]["missing_body"] == 1
    assert result["counts"]["lexicon_miss"] == 1
    assert result["cap"]["ok"] is True
    assert result["cached"] is False
    assert result["cost_estimate"]["would_route"] == 1
    assert result["cost_estimate"]["usd"] > 0
    assert "0.5×" in result["cost_estimate"]["html"]
    assert "Not a quote" in result["cost_estimate"]["html"]
    assert result["cost_estimate_sync"]["usd"] == estimate_usd(1, batch=False)["usd"]
    assert "1×" in result["cost_estimate_sync"]["html"]
    assert "0.5×" not in result["cost_estimate_sync"]["html"]
    assert [c["stage"] for c in result["chips"]] == ["lexicon_miss"]
    assert [n["id"] for n in result["sankey"]["nodes"]] == [
        "preview_in", "missing_body", "empty_body", "would_route",
    ]


def test_preview_caches_by_corpus_and_lexicon(settings, corpus_dir):
    store = Store(settings)
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    first = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons,
        settings=settings, store=store,
    )
    assert first["cached"] is False
    assert first["counts"]["would_route"] == 1

    second = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons,
        settings=settings, store=store,
    )
    assert second["cached"] is True
    assert second["counts"] == first["counts"]

    rewritten, _ = _slurry(description="totally different inclusion spec")
    third = run_preview(
        corpus=corpus, categories=rewritten, lexicons=lexicons,
        settings=settings, store=store,
    )
    assert third["cached"] is True

    _, other_lex = _slurry(terms=["slurry", "lagoon", "digestate"])
    fourth = run_preview(
        corpus=corpus, categories=categories, lexicons=other_lex,
        settings=settings, store=store,
    )
    assert fourth["cached"] is False


def test_preview_filters_by_organisation(settings, corpus_dir):
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
        organisations=["environment-agency"],
    )
    assert result["counts"]["corpus_pages"] == 4
    assert result["counts"]["organisation_miss"] == 3
    assert result["counts"]["input_pages"] == 1
    assert result["counts"]["would_route"] == 1
    assert result["counts"]["lexicon_miss"] == 0
    assert result["counts"]["empty_body"] == 0
    assert result["counts"]["missing_body"] == 0
    assert [n["id"] for n in result["sankey"]["nodes"]] == [
        "organisation_pass", "would_route",
    ]
    assert result["sankey"]["links"] == [
        {"source": "organisation_pass", "target": "would_route", "n": 1},
    ]
    assert [c["stage"] for c in result["chips"]] == ["organisation_miss"]
    assert result["caption"] == "4 on the index → 1 matching organisation → 1 would go to the model"


def test_preview_filters_by_document_type(settings, corpus_dir):
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    guides = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
        document_types=["guide"],
    )
    assert guides["counts"]["corpus_pages"] == 4
    assert guides["counts"]["document_type_miss"] == 1
    assert guides["counts"]["input_pages"] == 3
    assert guides["counts"]["would_route"] == 1
    assert guides["counts"]["empty_body"] == 0
    assert guides["counts"]["missing_body"] == 1
    assert [n["id"] for n in guides["sankey"]["nodes"]] == [
        "document_type_pass",
        "missing_body",
        "would_route",
    ]

    detailed = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
        document_types=["Detailed Guide"],
    )
    assert detailed["counts"]["input_pages"] == 1
    assert detailed["counts"]["empty_body"] == 1
    assert detailed["counts"]["would_route"] == 0


def test_preview_filters_org_and_type(settings, corpus_dir):
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
        organisations=["environment-agency"],
        document_types=["guide"],
    )
    assert result["counts"]["organisation_miss"] == 3
    assert result["counts"]["document_type_miss"] == 0
    assert result["counts"]["input_pages"] == 1
    assert result["counts"]["would_route"] == 1
    assert result["counts"]["document_type_filter"] is True
    assert [n["id"] for n in result["sankey"]["nodes"]] == [
        "organisation_pass", "document_type_pass", "would_route",
    ]
    assert "document_type_miss" not in [n["id"] for n in result["sankey"]["nodes"]]

    empty = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
        organisations=["environment-agency"],
        document_types=["detailed_guide"],
    )
    assert empty["counts"]["organisation_miss"] == 3
    assert empty["counts"]["document_type_miss"] == 1
    assert empty["counts"]["input_pages"] == 0
    assert empty["counts"]["would_route"] == 0
    assert [n["id"] for n in empty["sankey"]["nodes"]] == [
        "organisation_pass",
        "document_type_pass",
    ]
    assert empty["caption"] == "4 on the index → 1 matching organisation → 0 matching document type"


def test_preview_cache_misses_when_scope_changes(settings, corpus_dir):
    store = Store(settings)
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    first = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons,
        settings=settings, store=store,
        organisations=["environment-agency"],
    )
    assert first["cached"] is False
    same = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons,
        settings=settings, store=store,
        organisations=["environment-agency"],
    )
    assert same["cached"] is True
    other_org = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons,
        settings=settings, store=store,
        organisations=["department-for-environment-food-rural-affairs"],
    )
    assert other_org["cached"] is False
    assert other_org["counts"]["would_route"] == 0
    other_type = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons,
        settings=settings, store=store,
        organisations=["environment-agency"],
        document_types=["detailed_guide"],
    )
    assert other_type["cached"] is False
    assert other_type["counts"]["input_pages"] == 0


def test_preview_warns_on_unknown_organisation_slug(settings, corpus_dir):
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
        organisations=["defra"],
    )
    assert result["counts"]["would_route"] == 0
    assert result["counts"]["input_pages"] == 0
    assert result["counts"]["organisation_miss"] == 4
    assert "organisation 'defra' matched no pages on this index" in result["warnings"]


def test_preview_cap_ok_at_limit(settings, corpus_dir):
    settings.grf_max_routed = 1
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
    )
    assert result["counts"]["would_route"] == 1
    assert result["cap"] == {"max_routed": 1, "ok": True}
    assert not any("over the run cap" in w for w in result["warnings"])


def test_preview_cap_warns_when_over(settings, corpus_dir):
    settings.grf_max_routed = 0
    corpus = Corpus(corpus_dir)
    categories, lexicons = _slurry()
    result = run_preview(
        corpus=corpus, categories=categories, lexicons=lexicons, settings=settings,
    )
    assert result["counts"]["would_route"] == 1
    assert result["cap"] == {"max_routed": 0, "ok": False}
    assert (
        "1 page would go to the model — over the run cap of 0. "
        "Wordsearch is not truncated; Run filter is blocked."
    ) in result["warnings"]
