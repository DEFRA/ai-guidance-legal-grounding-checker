"""Join a URL CSV against output.json / funnel.json."""

import csv
import json

from typer.testing import CliRunner

from guidance_relevance_filter.annotate import (
    FUNNEL_REASON_COL,
    FUNNEL_STAGE_COL,
    NOT_IN_CORPUS,
    NOT_IN_CORPUS_REASON,
    STAGE_GUIDE,
    STAGE_KEYS,
    AnnotateError,
    annotate_row,
    drop_reason,
    explain_csv,
    format_histogram,
    govuk_path,
    index_funnel_json,
    index_output_json,
    load_run,
    resolve_url_column,
)
from guidance_relevance_filter.cli import app

runner = CliRunner()

KEEP_URL = "https://www.gov.uk/guidance/slurry-storage"
DROP_URL = "https://www.gov.uk/guidance/aquarium-fish"
MISS_URL = "https://www.gov.uk/guidance/hedgerows"
ABSENT_URL = "https://www.gov.uk/guidance/never-seen"


def _page(url: str, stage: str, **funnel) -> dict:
    reasons = {"slurry": funnel.pop("reason", "")}
    return {
        "url": url,
        "meta_data": {
            "title": url.rsplit("/", 1)[-1],
            "labels": {"slurry": stage in {"pass2_keep", "pass2_unadjudicated"}},
            "reasons": reasons,
            "funnel": {"stage": stage, **funnel},
        },
    }


def _output_pages() -> list[dict]:
    return [
        _page(
            KEEP_URL,
            "pass2_keep",
            pass2_reason="dedicated slurry store page",
            pass1_reason="mentions slurry",
            exclusion_hit="none",
        ),
        _page(
            DROP_URL,
            "pass2_drop",
            pass2_reason="ornamental aquarium fish",
            pass1_reason="mentions fish slurry",
            exclusion_hit="wrong_domain",
        ),
        _page(
            MISS_URL,
            "lexicon_miss",
            reason="excluded by wordsearch_binary (no cats selected; LLM not called)",
        ),
    ]


def _funnel_doc() -> dict:
    return {
        "category": "slurry",
        "counts": {},
        "lexicon_miss": [{"url": MISS_URL, "stage": "lexicon_miss"}],
        "pass2_drop": [
            {
                "url": DROP_URL,
                "stage": "pass2_drop",
                "pass2_reason": "ornamental aquarium fish",
                "exclusion_hit": "wrong_domain",
            }
        ],
        "pass2_keep": [
            {
                "url": KEEP_URL,
                "stage": "pass2_keep",
                "pass2_reason": "dedicated slurry store page",
            }
        ],
        "missing_body": [],
        "empty_body": [],
        "pass1_false": [],
        "pass2_unadjudicated": [],
    }


def test_govuk_path_public_url():
    assert govuk_path(KEEP_URL) == "/guidance/slurry-storage"
    assert govuk_path(KEEP_URL + "/") == "/guidance/slurry-storage"


def test_govuk_path_content_api():
    api = "https://www.gov.uk/api/content/guidance/slurry-storage"
    assert govuk_path(api) == "/guidance/slurry-storage"


def test_govuk_path_webarchive_embedded():
    archived = (
        "https://webarchive.nationalarchives.gov.uk/ukgwa/20250602185011/"
        "https:/www.gov.uk/countryside-stewardship-grants/basic-overwinter-stubble-ab2"
    )
    assert govuk_path(archived) == "/countryside-stewardship-grants/basic-overwinter-stubble-ab2"


def test_govuk_path_empty():
    assert govuk_path("") is None
    assert govuk_path("   ") is None


def test_drop_reason_pass2_drop():
    assert drop_reason({
        "stage": "pass2_drop",
        "exclusion_hit": "wrong_domain",
        "pass2_reason": "ornamental aquarium fish",
    }) == "[wrong_domain] ornamental aquarium fish"


def test_drop_reason_pass1_false():
    assert drop_reason({
        "stage": "pass1_false",
        "pass1_reason": "incidental mention",
    }) == "incidental mention"


def test_drop_reason_lexicon_miss_falls_back_to_stage():
    assert drop_reason({"stage": "lexicon_miss"}) == "lexicon_miss"


def test_drop_reason_cosine_miss_falls_back_to_stage():
    assert drop_reason({"stage": "cosine_miss"}) == "cosine_miss"


def test_join_output_json_stages():
    index = index_output_json(_output_pages())
    assert annotate_row(index, KEEP_URL) == ("pass2_keep", "dedicated slurry store page")
    assert annotate_row(index, DROP_URL) == (
        "pass2_drop",
        "[wrong_domain] ornamental aquarium fish",
    )
    assert annotate_row(index, MISS_URL) == (
        "lexicon_miss",
        "excluded by wordsearch_binary (no cats selected; LLM not called)",
    )
    assert annotate_row(index, ABSENT_URL) == (NOT_IN_CORPUS, NOT_IN_CORPUS_REASON)


def test_join_matches_content_api_url():
    index = index_output_json(_output_pages())
    api = "https://www.gov.uk/api/content/guidance/slurry-storage"
    assert annotate_row(index, api)[0] == "pass2_keep"


def test_index_funnel_json():
    index = index_funnel_json(_funnel_doc())
    assert annotate_row(index, KEEP_URL)[0] == "pass2_keep"
    assert annotate_row(index, DROP_URL)[0] == "pass2_drop"
    assert annotate_row(index, MISS_URL) == ("lexicon_miss", "lexicon_miss")
    assert annotate_row(index, ABSENT_URL)[0] == NOT_IN_CORPUS


def test_old_funnel_json_without_cosine_miss_still_indexes():
    doc = _funnel_doc()
    assert "cosine_miss" not in doc
    index = index_funnel_json(doc)
    assert annotate_row(index, KEEP_URL)[0] == "pass2_keep"
    assert annotate_row(index, MISS_URL)[0] == "lexicon_miss"


def test_join_cosine_miss_from_output_json():
    cosine_url = "https://www.gov.uk/guidance/passport-office"
    pages = [_page(
        cosine_url,
        "cosine_miss",
        reason="excluded by cosine_body (score 0.05 < 0.2; LLM not called)",
    )]
    index = index_output_json(pages)
    assert annotate_row(index, cosine_url) == (
        "cosine_miss",
        "excluded by cosine_body (score 0.05 < 0.2; LLM not called)",
    )


def test_load_run_prefers_output_json(tmp_path):
    (tmp_path / "output.json").write_text(json.dumps(_output_pages()))
    (tmp_path / "funnel.json").write_text(json.dumps(_funnel_doc()))
    index = load_run(tmp_path)
    assert annotate_row(index, MISS_URL)[1].startswith("excluded by wordsearch")


def test_load_run_falls_back_to_funnel_json(tmp_path):
    (tmp_path / "funnel.json").write_text(json.dumps(_funnel_doc()))
    index = load_run(tmp_path)
    assert annotate_row(index, KEEP_URL)[0] == "pass2_keep"


def test_load_run_file_paths(tmp_path):
    out = tmp_path / "output.json"
    funnel = tmp_path / "funnel.json"
    out.write_text(json.dumps(_output_pages()))
    funnel.write_text(json.dumps(_funnel_doc()))
    assert annotate_row(load_run(out), DROP_URL)[0] == "pass2_drop"
    assert annotate_row(load_run(funnel), DROP_URL)[0] == "pass2_drop"


def test_resolve_url_column_fallback():
    assert resolve_url_column(["title", "Original URL"], None) == "Original URL"
    assert resolve_url_column(["clened-urls", "title"], None) == "clened-urls"
    assert resolve_url_column(["url", "Original URL"], None) == "url"


def test_resolve_url_column_explicit_missing():
    try:
        resolve_url_column(["title"], "url")
    except AnnotateError as e:
        assert "url" in str(e)
        assert "title" in str(e)
    else:
        raise AssertionError("expected AnnotateError")


def test_explain_csv_preserves_rows_and_appends_columns(tmp_path):
    csv_path = tmp_path / "gold.csv"
    csv_path.write_text(
        "title,url\n"
        f"keep,{KEEP_URL}\n"
        f"keep-dup,{KEEP_URL}\n"
        f"absent,{ABSENT_URL}\n"
    )
    run = tmp_path / "run"
    run.mkdir()
    (run / "output.json").write_text(json.dumps(_output_pages()))

    dest, counts = explain_csv(csv_path, run)
    assert dest == tmp_path / "gold-funnel.csv"
    assert counts["pass2_keep"] == 2
    assert counts[NOT_IN_CORPUS] == 1

    with dest.open() as fh:
        rows = list(csv.DictReader(fh))
    assert [r["title"] for r in rows] == ["keep", "keep-dup", "absent"]
    assert rows[0][FUNNEL_STAGE_COL] == "pass2_keep"
    assert rows[2][FUNNEL_STAGE_COL] == NOT_IN_CORPUS
    assert rows[2][FUNNEL_REASON_COL] == NOT_IN_CORPUS_REASON


def test_cli_explain_writes_columns(tmp_path):
    csv_path = tmp_path / "urls.csv"
    csv_path.write_text(f"url\n{DROP_URL}\n{KEEP_URL}\n")
    run = tmp_path / "output.json"
    run.write_text(json.dumps(_output_pages()))
    out = tmp_path / "annotated.csv"

    result = runner.invoke(app, ["explain", str(csv_path), str(run), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "Wrote" in result.output
    assert "pass2_drop=1" in result.output
    assert "pass2_keep=1" in result.output

    rows = list(csv.DictReader(out.open()))
    assert rows[0][FUNNEL_STAGE_COL] == "pass2_drop"
    assert "[wrong_domain]" in rows[0][FUNNEL_REASON_COL]


def test_cli_explain_url_column_override(tmp_path):
    csv_path = tmp_path / "board.csv"
    csv_path.write_text(f"clened-urls,note\n{MISS_URL},board\n")
    run = tmp_path / "funnel.json"
    run.write_text(json.dumps(_funnel_doc()))

    result = runner.invoke(app, [
        "explain", str(csv_path), str(run), "--url-column", "clened-urls",
    ])
    assert result.exit_code == 0, result.output
    dest = tmp_path / "board-funnel.csv"
    rows = list(csv.DictReader(dest.open()))
    assert rows[0][FUNNEL_STAGE_COL] == "lexicon_miss"


def test_cli_explain_missing_column(tmp_path):
    csv_path = tmp_path / "urls.csv"
    csv_path.write_text("title\nhello\n")
    run = tmp_path / "output.json"
    run.write_text(json.dumps(_output_pages()))

    result = runner.invoke(app, [
        "explain", str(csv_path), str(run), "--url-column", "url",
    ])
    assert result.exit_code == 1
    assert "Column 'url' not in CSV" in result.output


def test_cli_serve_without_streamlit(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _block_streamlit(name, *args, **kwargs):
        if name == "streamlit" or name.startswith("streamlit."):
            raise ImportError("no streamlit")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_streamlit)
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 1
    assert "uv sync --group web" in result.output


def test_stage_guide_covers_every_stage_in_funnel_order():
    stages = [stage for stage, _label, _meaning in STAGE_GUIDE]
    assert stages[0] == NOT_IN_CORPUS
    assert set(stages) == {NOT_IN_CORPUS, *STAGE_KEYS}
    assert stages.index("lexicon_miss") < stages.index("cosine_miss") < stages.index("pass1_false")
    assert stages.index("pass1_false") < stages.index("pass2_drop")
    assert stages[-1] == "pass2_keep"


def test_format_histogram_order():
    from collections import Counter

    text = format_histogram(Counter({"pass2_keep": 2, NOT_IN_CORPUS: 1, "lexicon_miss": 3}))
    assert text == f"{NOT_IN_CORPUS}=1 lexicon_miss=3 pass2_keep=2"
