"""The `guidance-relevance-filter run` CLI runs both passes and writes its files, fully offline.

`classify` and `adjudicate` (the only API-calling parts) are stubbed, so this
covers argument parsing and file output without a network call or an API key.
"""

import json

from typer.testing import CliRunner

from guidance_relevance_filter.cli import app
from guidance_relevance_filter.narrowing import DEFAULT_EMBED_MODEL, EmbedCache

runner = CliRunner()


def test_run_writes_output_audit_and_a_model_card(tmp_path, monkeypatch, build_page):
    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"

    def fake_classify(items, categories, lexicons, **_):
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: True}, "scores": {cat: 0.3},
            "reasons": {cat: f"mentions {cat}"},
            "funnel": {
                "stage": "pass1_true",
                "pass1_label": True,
                "pass1_score": 0.3,
                "pass1_reason": f"mentions {cat}",
            },
            "selection_meta_body": {
                "strategy": "wordsearch_binary",
                "hits_per_cat": {cat: [cat]},
            },
        }}
        return [labelled], {"n_routed": 1, "n_skipped": 0, "n_empty_body": 0,
                            "n_pages": 1, "n_rescued": 0, "n_batch_missing": 0,
                            "n_pass1_false": 0, "n_pass1_true": 1,
                            "batch": {"id": "msgbatch_p1", "submitted": 1, "collected": 1,
                                      "elapsed_seconds": 12, "request_counts": {
                                          "succeeded": 1, "processing": 0, "errored": 0,
                                          "canceled": 0, "expired": 0}},
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 100, "output": 50},
                                      "rescue": {"input": 0, "output": 0}}}

    def fake_adjudicate(items, results, categories, **_):
        cat = categories[0]["name"]
        md = results[0]["meta_data"]
        md["labels"][cat] = False  # pass 2 drops it
        md["reasons"][cat] = "incidental mention"
        md["funnel"] = {
            **md.get("funnel", {}),
            "stage": "pass2_drop",
            "pass2_keep": False,
            "pass2_reason": "incidental mention",
            "exclusion_hit": "incidental",
        }
        audit = [{"url": results[0]["url"], "stage": "pass2_drop",
                  "pass2_keep": False, "exclusion_hit": "incidental"}]
        return results, {"n_positives": 1, "n_kept": 0, "n_dropped": 1,
                         "n_unadjudicated": 0, "model": "claude-sonnet-4-6",
                         "batch": {"id": "msgbatch_p2", "submitted": 1, "collected": 1,
                                   "elapsed_seconds": 8, "request_counts": {
                                       "succeeded": 1, "processing": 0, "errored": 0,
                                       "canceled": 0, "expired": 0}},
                         "usage": {"model": "claude-sonnet-4-6",
                                   "batch": {"input": 200, "output": 80}}}, audit

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr("guidance_relevance_filter.cli.adjudicate", fake_adjudicate)

    result = runner.invoke(app, ["run", str(input_path), str(output_dir)])

    assert result.exit_code == 0, result.output
    written = json.loads((output_dir / "output.json").read_text())
    cat = written[0]["meta_data"]["labels"]
    label_key = next(iter(cat))
    assert cat[label_key] is False  # final, post-pass-2
    assert json.loads((output_dir / "adjudication.json").read_text())[0]["pass2_keep"] is False
    assert (output_dir / "MODEL.md").exists()

    metrics = json.loads((output_dir / "metrics.json").read_text())
    assert metrics["tokens"] == {"input": 300, "output": 130}  # 100+200 in, 50+80 out
    assert metrics["pass1"]["cost_usd"] is not None and metrics["pass2"]["cost_usd"] is not None
    assert metrics["cost_usd"] == round(
        metrics["pass1"]["cost_usd"] + metrics["pass2"]["cost_usd"], 4
    )
    funnel = metrics["funnel"]
    assert funnel["input_pages"]["n"] == 1
    assert funnel["lexicon_hit"]["n"] == 1
    assert "pass-1 classify batch" in funnel["lexicon_hit"]["meaning"]
    assert funnel["pass1_true"]["n"] == 1
    assert funnel["pass1_false"]["n"] == 0
    assert funnel["pass2_dropped"]["n"] == 1
    assert funnel["pass2_dropped_by_exclusion_hit"]["incidental"] == 1
    assert funnel["final_true"]["n"] == 0
    journal = json.loads((output_dir / "funnel.json").read_text())
    assert journal["counts"]["pass2_dropped"] == 1
    assert journal["counts"]["missing_body"] == 0
    assert journal["pass2_drop"][0]["exclusion_hit"] == "incidental"
    assert journal["pass2_drop"][0]["pass1_reason"] == f"mentions {label_key}"
    assert metrics["funnel"]["missing_body"]["n"] == 0
    assert metrics["pass1"]["batch_meta"]["id"] == "msgbatch_p1"
    assert metrics["pass1"]["batch_meta"]["submitted"] == 1
    assert metrics["pass2"]["batch_meta"]["id"] == "msgbatch_p2"
    assert metrics["resumed"] is False
    assert metrics["llm_mode"] == "batch"
    assert isinstance(metrics["elapsed_seconds"], int)
    assert metrics["elapsed_seconds"] >= 0
    assert metrics["finished_at"]
    assert not (output_dir / "checkpoint.json").exists()
    card = (output_dir / "MODEL.md").read_text()
    assert "## Funnel" in card
    assert "Lexicon-hit:** 1" in card
    assert "Pass 1" in card and "false" in card
    assert "incidental 1" in card
    assert "funnel.json" in card
    assert "msgbatch_p1" in card
    assert "msgbatch_p2" in card
    assert "Total:" in card
    assert "Elapsed (this process):" in card
    assert "elapsed=" in result.output


def test_run_accepts_custom_category_and_lexicon_paths(tmp_path, monkeypatch, build_page):
    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    categories_path = tmp_path / "categories.json"
    lexicon_path = tmp_path / "lexicon.json"
    categories_path.write_text(json.dumps([{"name": "demo", "description": "demo topic"}]))
    lexicon_path.write_text(json.dumps({"demo": ["Demo"]}))

    seen: dict = {}

    def fake_classify(items, categories, lexicons, **_):
        seen["categories"] = categories
        seen["lexicons"] = lexicons
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: False}, "scores": {cat: 0.0}, "reasons": {cat: "no"}}}
        return [labelled], {"n_routed": 0, "n_skipped": 1, "n_rescued": 0,
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 0, "output": 0},
                                      "rescue": {"input": 0, "output": 0}}}

    def fake_adjudicate(items, results, categories, **_):
        return results, {"n_positives": 0, "n_kept": 0, "n_dropped": 0,
                         "n_unadjudicated": 0, "model": "claude-sonnet-4-6",
                         "usage": {"model": "claude-sonnet-4-6",
                                   "batch": {"input": 0, "output": 0}}}, []

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr("guidance_relevance_filter.cli.adjudicate", fake_adjudicate)

    result = runner.invoke(app, [
        "run", str(input_path), str(output_dir),
        "--categories", str(categories_path),
        "--lexicon", str(lexicon_path),
    ])

    assert result.exit_code == 0, result.output
    assert seen["categories"][0]["name"] == "demo"
    assert seen["lexicons"] == {"demo": ["Demo"]}
    model_card = (output_dir / "MODEL.md").read_text()
    assert "demo" in model_card
    assert "categories.json" in model_card


def _fp(input_path, categories, lexicons):
    from guidance_relevance_filter.adjudicate import DEFAULT_ADJUDICATOR_MODEL
    from guidance_relevance_filter.checkpoint import fingerprint_for
    from guidance_relevance_filter.classify import DEFAULT_MODEL

    return fingerprint_for(
        input_path=input_path,
        n_pages=1,
        category=categories[0]["name"],
        model=DEFAULT_MODEL,
        adjudicator_model=DEFAULT_ADJUDICATOR_MODEL,
        max_words=60000,
        shard_name=None,
        categories=categories,
        lexicons=lexicons,
    )


def test_run_reattaches_when_a_checkpoint_is_present(tmp_path, monkeypatch, build_page):
    from guidance_relevance_filter.checkpoint import Checkpoint
    from guidance_relevance_filter.cli import load_category_data

    input_path = tmp_path / "pages.json"
    page = build_page()
    input_path.write_text(json.dumps([page]))
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    categories, lexicons = load_category_data()
    cp = Checkpoint(output_dir / "checkpoint.json")
    cp.init(_fp(input_path, categories, lexicons), "2026-01-01T00:00:00")
    cp.record_pass1_routing([page["url"]])
    cp.record_pass1_batch("msgbatch_resume_p1")

    seen: dict = {}

    def fake_classify(items, categories, lexicons, checkpoint=None, **_):
        seen["pass1"] = None if checkpoint is None else checkpoint.pass1_batch_id
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: True}, "scores": {cat: 0.3}, "reasons": {cat: "x"}}}
        return [labelled], {"n_routed": 1, "n_skipped": 0, "n_empty_body": 0,
                            "n_pages": 1, "n_rescued": 0, "n_batch_missing": 0,
                            "batch": {"id": "msgbatch_resume_p1", "submitted": 1,
                                      "collected": 1, "elapsed_seconds": 1,
                                      "request_counts": None},
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 1, "output": 1},
                                      "rescue": {"input": 0, "output": 0}}}

    def fake_adjudicate(items, results, categories, **_):
        return results, {"n_positives": 1, "n_kept": 1, "n_dropped": 0,
                         "n_unadjudicated": 0, "model": "claude-sonnet-4-6",
                         "usage": {"model": "claude-sonnet-4-6",
                                   "batch": {"input": 1, "output": 1}}}, []

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr("guidance_relevance_filter.cli.adjudicate", fake_adjudicate)

    result = runner.invoke(app, ["run", str(input_path), str(output_dir)])
    assert result.exit_code == 0, result.output
    assert seen["pass1"] == "msgbatch_resume_p1"
    metrics = json.loads((output_dir / "metrics.json").read_text())
    assert metrics["resumed"] is True
    assert metrics["started_at"] == "2026-01-01T00:00:00"
    assert "resumed from checkpoint" in (output_dir / "MODEL.md").read_text()
    assert not (output_dir / "checkpoint.json").exists()


def test_run_refuses_a_mismatched_checkpoint(tmp_path, monkeypatch, build_page):
    from guidance_relevance_filter.checkpoint import Checkpoint
    from guidance_relevance_filter.cli import load_category_data

    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    categories, lexicons = load_category_data()
    fp = _fp(input_path, categories, lexicons)
    fp["n_pages"] = 999
    cp = Checkpoint(output_dir / "checkpoint.json")
    cp.init(fp, "2026-01-01T00:00:00")

    monkeypatch.setattr(
        "guidance_relevance_filter.cli.classify",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not classify")),
    )
    result = runner.invoke(app, ["run", str(input_path), str(output_dir)])
    assert result.exit_code == 1
    err = (result.output or "") + (getattr(result, "stderr", None) or "")
    assert "does not match this invocation" in err
    assert (output_dir / "checkpoint.json").exists()


def test_fresh_abandons_a_mismatched_checkpoint(tmp_path, monkeypatch, build_page):
    from guidance_relevance_filter.checkpoint import Checkpoint
    from guidance_relevance_filter.cli import load_category_data

    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    categories, lexicons = load_category_data()
    fp = _fp(input_path, categories, lexicons)
    fp["n_pages"] = 999
    Checkpoint(output_dir / "checkpoint.json").init(fp, "2026-01-01T00:00:00")

    def fake_classify(items, categories, lexicons, **_):
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: False}, "scores": {cat: 0.0}, "reasons": {cat: "no"}}}
        return [labelled], {"n_routed": 0, "n_skipped": 1, "n_rescued": 0,
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 0, "output": 0},
                                      "rescue": {"input": 0, "output": 0}}}

    def fake_adjudicate(items, results, categories, **_):
        return results, {"n_positives": 0, "n_kept": 0, "n_dropped": 0,
                         "n_unadjudicated": 0, "model": "claude-sonnet-4-6",
                         "usage": {"model": "claude-sonnet-4-6",
                                   "batch": {"input": 0, "output": 0}}}, []

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr("guidance_relevance_filter.cli.adjudicate", fake_adjudicate)

    result = runner.invoke(app, ["run", str(input_path), str(output_dir), "--fresh"])
    assert result.exit_code == 0, result.output
    assert json.loads((output_dir / "metrics.json").read_text())["resumed"] is False
    assert not (output_dir / "checkpoint.json").exists()


def test_score_only_skips_adjudicate_and_anthropic(tmp_path, monkeypatch, build_page):
    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    seen: dict = {}

    def fake_classify(items, categories, lexicons, score_only=False, **_):
        seen["score_only"] = score_only
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: False}, "scores": {cat: 0.4},
            "reasons": {cat: "score-only: routed; LLM not called"},
            "funnel": {"stage": "pass1_true"},
            "selection_meta_body": {"strategy": "cosine_body", "scores": {cat: 0.4}},
        }}
        return [labelled], {"n_routed": 1, "n_skipped": 0, "n_empty_body": 0,
                            "n_pages": 1, "n_rescued": 0, "n_batch_missing": 0,
                            "n_pass1_false": 0, "n_pass1_true": 0,
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 0, "output": 0},
                                      "rescue": {"input": 0, "output": 0}}}

    def fake_adjudicate(*_a, **_k):
        raise AssertionError("score-only must not adjudicate")

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr("guidance_relevance_filter.cli.adjudicate", fake_adjudicate)
    monkeypatch.setattr(
        "guidance_relevance_filter.cli.load_or_build_embed_cache",
        lambda *_a, **_k: EmbedCache("sha", DEFAULT_EMBED_MODEL),
    )

    result = runner.invoke(app, [
        "run", str(input_path), str(output_dir), "--score-only", "--router", "cosine",
    ])
    assert result.exit_code == 0, result.output
    assert seen["score_only"] is True
    written = json.loads((output_dir / "output.json").read_text())
    cat = next(iter(written[0]["meta_data"]["labels"]))
    assert written[0]["meta_data"]["labels"][cat] is False
    metrics = json.loads((output_dir / "metrics.json").read_text())
    assert metrics["score_only"] is True
    assert metrics["router"] == "cosine"
    assert "Score-only" in (output_dir / "MODEL.md").read_text()


def test_wordsearch_custom_categories_require_lexicon(tmp_path, build_page):
    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    categories_path = tmp_path / "categories.json"
    categories_path.write_text(json.dumps([{"name": "demo", "description": "demo topic"}]))

    result = runner.invoke(app, [
        "run", str(input_path), str(output_dir),
        "--categories", str(categories_path),
    ])
    assert result.exit_code != 0
    err = (result.output or "") + (getattr(result, "stderr", None) or "")
    assert "--lexicon" in err


def test_wordsearch_builds_sqlite_and_passes_stem_index(tmp_path, monkeypatch, build_page):
    from guidance_relevance_filter.narrowing import StemIndex, sha256_file

    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    seen: dict = {}

    def fake_classify(items, categories, lexicons, **kwargs):
        seen["stem_index_db"] = kwargs.get("stem_index_db")
        seen["n_items"] = len(items)
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: False}, "scores": {cat: 0.0},
            "reasons": {cat: "score-only"},
            "funnel": {"stage": "pass1_true"},
        }}
        return [labelled], {"n_routed": 1, "n_skipped": 0, "n_empty_body": 0,
                            "n_pages": 1, "n_rescued": 0, "n_batch_missing": 0,
                            "n_pass1_false": 0, "n_pass1_true": 0,
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 0, "output": 0},
                                      "rescue": {"input": 0, "output": 0}}}

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr(
        "guidance_relevance_filter.cli.adjudicate",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("score-only")),
    )

    result = runner.invoke(app, [
        "run", str(input_path), str(output_dir), "--score-only",
    ])
    assert result.exit_code == 0, result.output
    sqlite_path = (
        input_path.parent / "stem_index" / f"{sha256_file(input_path)}.sqlite"
    )
    assert sqlite_path.is_file()
    assert isinstance(seen["stem_index_db"], StemIndex)
    assert seen["stem_index_db"].path == sqlite_path
    assert seen["n_items"] == 1


def test_wordsearch_stem_index_flag_matches_slice_by_url(tmp_path, monkeypatch, build_page):
    from guidance_relevance_filter.narrowing import load_or_build_stem_index, sha256_file

    full = tmp_path / "with_body.json"
    hit = build_page()
    miss = {
        "url": "https://example.gov.uk/passports",
        "content_id": "xyz",
        "meta_data": {"title": "Passports", "body_text": "passport applications"},
    }
    full.write_text(json.dumps([hit, miss]))
    sha = sha256_file(full)
    sqlite = tmp_path / "stem_index" / f"{sha}.sqlite"
    built = load_or_build_stem_index(full, corpus_sha256=sha, path=sqlite)
    built.close()
    slice_path = tmp_path / "slice.json"
    slice_path.write_text(json.dumps([hit]))
    output_dir = tmp_path / "run"
    seen: dict = {}

    def fake_classify(items, categories, lexicons, **kwargs):
        seen["urls"] = [i["url"] for i in items]
        seen["stem_index_db"] = kwargs.get("stem_index_db")
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: False}, "scores": {cat: 0.0},
            "reasons": {cat: "score-only"},
            "funnel": {"stage": "pass1_true"},
        }}
        return [labelled], {"n_routed": 1, "n_skipped": 0, "n_empty_body": 0,
                            "n_pages": 1, "n_rescued": 0, "n_batch_missing": 0,
                            "n_pass1_false": 0, "n_pass1_true": 0,
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 0, "output": 0},
                                      "rescue": {"input": 0, "output": 0}}}

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr(
        "guidance_relevance_filter.cli.adjudicate",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("score-only")),
    )

    result = runner.invoke(app, [
        "run", str(slice_path), str(output_dir),
        "--score-only", "--stem-index", str(sqlite),
    ])
    assert result.exit_code == 0, result.output
    assert seen["urls"] == [hit["url"]]
    assert seen["stem_index_db"].path == sqlite


def test_cosine_allows_categories_without_lexicon(tmp_path, monkeypatch, build_page):
    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    categories_path = tmp_path / "categories.json"
    categories_path.write_text(json.dumps([{"name": "demo", "description": "demo topic"}]))
    seen: dict = {}

    def fake_classify(items, categories, lexicons, **kwargs):
        seen["lexicons"] = lexicons
        seen["router"] = kwargs.get("router")
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: False}, "scores": {cat: 0.0}, "reasons": {cat: "no"},
            "funnel": {"stage": "cosine_miss"},
        }}
        return [labelled], {"n_routed": 0, "n_skipped": 1, "n_rescued": 0,
                            "n_pages": 1, "n_empty_body": 0, "n_pass1_false": 0,
                            "n_pass1_true": 0,
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 0, "output": 0},
                                      "rescue": {"input": 0, "output": 0}}}

    def fake_adjudicate(items, results, categories, **_):
        return results, {"n_positives": 0, "n_kept": 0, "n_dropped": 0,
                         "n_unadjudicated": 0, "model": "claude-sonnet-4-6",
                         "usage": {"model": "claude-sonnet-4-6",
                                   "batch": {"input": 0, "output": 0}}}, []

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr("guidance_relevance_filter.cli.adjudicate", fake_adjudicate)
    monkeypatch.setattr(
        "guidance_relevance_filter.cli.load_or_build_embed_cache",
        lambda *_a, **_k: EmbedCache("sha", DEFAULT_EMBED_MODEL),
    )

    result = runner.invoke(app, [
        "run", str(input_path), str(output_dir),
        "--router", "cosine",
        "--categories", str(categories_path),
        "--score-only",
    ])
    assert result.exit_code == 0, result.output
    assert seen["lexicons"] == {}
    assert seen["router"] == "cosine"


def test_cosine_run_passes_embed_cache(tmp_path, monkeypatch, build_page):
    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    cache = EmbedCache("sha", DEFAULT_EMBED_MODEL)
    seen: dict = {}

    def fake_load(*_items, **kwargs):
        seen["path"] = kwargs["path"]
        seen["embed_model"] = kwargs["embed_model"]
        return cache

    def fake_classify(items, categories, lexicons, **kwargs):
        seen["embed_cache"] = kwargs.get("embed_cache")
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: False}, "scores": {cat: 0.0}, "reasons": {cat: "no"},
            "funnel": {"stage": "cosine_miss"},
        }}
        return [labelled], {"n_routed": 0, "n_skipped": 1, "n_rescued": 0,
                            "n_pages": 1, "n_empty_body": 0, "n_pass1_false": 0,
                            "n_pass1_true": 0,
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 0, "output": 0},
                                      "rescue": {"input": 0, "output": 0}}}

    monkeypatch.setattr("guidance_relevance_filter.cli.load_or_build_embed_cache", fake_load)
    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr(
        "guidance_relevance_filter.cli.adjudicate",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("unused")),
    )

    result = runner.invoke(app, [
        "run", str(input_path), str(output_dir),
        "--router", "cosine", "--score-only",
    ])
    assert result.exit_code == 0, result.output
    assert seen["embed_cache"] is cache
    assert seen["embed_model"] == DEFAULT_EMBED_MODEL
    assert seen["path"].parent.name == "embed_index"
    assert seen["path"].suffix == ".pkl"


def test_max_routed_writes_funnel_and_exits_without_adjudicate(tmp_path, monkeypatch, build_page):
    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    seen: dict = {}

    def fake_classify(items, categories, lexicons, **kwargs):
        seen["max_routed"] = kwargs.get("max_routed")
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: False}, "scores": {cat: 0.0},
            "reasons": {cat: "max-routed: 1 pages routed, cap 0; LLM not called"},
            "funnel": {"stage": "pass1_true", "pass1_reason": "max-routed"},
        }}
        return [labelled], {
            "n_routed": 1, "n_skipped": 0, "n_empty_body": 0, "n_pages": 1,
            "n_rescued": 0, "n_batch_missing": 0, "n_pass1_false": 0, "n_pass1_true": 0,
            "capped": True, "max_routed": 0,
            "model": "claude-haiku-4-5-20251001",
            "usage": {"model": "claude-haiku-4-5-20251001",
                      "batch": {"input": 0, "output": 0},
                      "rescue": {"input": 0, "output": 0}},
        }

    def fake_adjudicate(*_a, **_k):
        raise AssertionError("capped run must not adjudicate")

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr("guidance_relevance_filter.cli.adjudicate", fake_adjudicate)

    result = runner.invoke(app, [
        "run", str(input_path), str(output_dir), "--max-routed", "0",
    ])
    assert result.exit_code == 1, result.output
    assert seen["max_routed"] == 0
    assert (output_dir / "funnel.json").exists()
    assert (output_dir / "metrics.json").exists()
    metrics = json.loads((output_dir / "metrics.json").read_text())
    assert metrics["capped"] is True
    assert metrics["max_routed"] == 0
    assert not (output_dir / "checkpoint.json").exists()
    assert "Capped" in (output_dir / "MODEL.md").read_text()


def test_run_sync_prices_full_rate(tmp_path, monkeypatch, build_page):
    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"

    def fake_classify(items, categories, lexicons, **_):
        cat = categories[0]["name"]
        labelled = {**items[0], "meta_data": {
            "labels": {cat: True}, "scores": {cat: 0.3},
            "reasons": {cat: f"mentions {cat}"},
            "funnel": {"stage": "pass1_true", "pass1_label": True},
        }}
        return [labelled], {"n_routed": 1, "n_skipped": 0, "n_empty_body": 0,
                            "n_pages": 1, "n_rescued": 0, "n_batch_missing": 0,
                            "n_pass1_false": 0, "n_pass1_true": 1,
                            "batch": {"id": None, "submitted": 1, "collected": 1,
                                      "elapsed_seconds": 2, "mode": "sync",
                                      "concurrency": 10, "request_counts": {
                                          "succeeded": 1, "processing": 0, "errored": 0,
                                          "canceled": 0, "expired": 0}},
                            "model": "claude-haiku-4-5-20251001",
                            "usage": {"model": "claude-haiku-4-5-20251001",
                                      "batch": {"input": 100, "output": 50},
                                      "rescue": {"input": 0, "output": 0}}}

    def fake_adjudicate(items, results, categories, **_):
        return results, {"n_positives": 1, "n_kept": 1, "n_dropped": 0,
                         "n_unadjudicated": 0, "model": "claude-sonnet-4-6",
                         "batch": {"id": None, "submitted": 1, "collected": 1,
                                   "elapsed_seconds": 1, "mode": "sync"},
                         "usage": {"model": "claude-sonnet-4-6",
                                   "batch": {"input": 200, "output": 80}}}, []

    monkeypatch.setattr("guidance_relevance_filter.cli.classify", fake_classify)
    monkeypatch.setattr("guidance_relevance_filter.cli.adjudicate", fake_adjudicate)

    result = runner.invoke(app, ["run", str(input_path), str(output_dir), "--sync"])
    assert result.exit_code == 0, result.output
    metrics = json.loads((output_dir / "metrics.json").read_text())
    assert metrics["llm_mode"] == "sync"
    from guidance_relevance_filter.cost import cost_usd
    expected = round(
        (cost_usd(100, 50, "claude-haiku-4-5-20251001", batch=False) or 0)
        + (cost_usd(200, 80, "claude-sonnet-4-6", batch=False) or 0),
        4,
    )
    assert metrics["cost_usd"] == expected
    card = (output_dir / "MODEL.md").read_text()
    assert "on-demand" in card
    assert "Messages API (sync)" in card
    assert "LLM mode:** `sync`" in card


def test_run_refuses_sync_against_a_batch_checkpoint(tmp_path, monkeypatch, build_page):
    from guidance_relevance_filter.checkpoint import Checkpoint
    from guidance_relevance_filter.cli import load_category_data

    input_path = tmp_path / "pages.json"
    input_path.write_text(json.dumps([build_page()]))
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    categories, lexicons = load_category_data()
    Checkpoint(output_dir / "checkpoint.json").init(
        _fp(input_path, categories, lexicons), "2026-01-01T00:00:00",
    )
    monkeypatch.setattr(
        "guidance_relevance_filter.cli.classify",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not classify")),
    )
    result = runner.invoke(app, ["run", str(input_path), str(output_dir), "--sync"])
    assert result.exit_code == 1
    err = (result.output or "") + (getattr(result, "stderr", None) or "")
    assert "llm_mode" in err
    assert (output_dir / "checkpoint.json").exists()


