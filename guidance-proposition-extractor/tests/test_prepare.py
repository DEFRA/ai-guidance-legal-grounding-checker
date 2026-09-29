import json
from pathlib import Path

from typer.testing import CliRunner

from guidance_proposition_extractor.cli import _relevance_filter_to_pages, app
from guidance_proposition_extractor.funnel import prepare_journal, run_journal


def test_relevance_filter_to_pages_keeps_on_topic_and_projects():
    rows = [
        {"url": "u1", "content_id": "c1", "meta_data": {"title": "T1", "labels": {"slurry": True}}},
        {"url": "u2", "content_id": "c2", "meta_data": {"title": "T2", "labels": {"slurry": False}}},
        {"url": "u3", "meta_data": {"labels": {"slurry": True}}},  # no title -> ""; no content_id -> ""
        {"url": "u4", "meta_data": {}},  # no labels -> dropped
        {"url": "u5", "meta_data": {"labels": {"slurry": 1}}},  # truthy != True -> dropped
    ]
    kept, dropped = _relevance_filter_to_pages(rows, "slurry")
    assert kept == [
        {"url": "u1", "title": "T1", "content_id": "c1"},
        {"url": "u3", "title": "", "content_id": ""},
    ]
    assert [d["url"] for d in dropped] == ["u2", "u4", "u5"]
    assert dropped[0]["label"] is False
    assert dropped[1]["label"] is None
    assert dropped[2]["label"] == 1


def test_relevance_filter_to_pages_respects_category():
    rows = [
        {"url": "u1", "content_id": "c1", "meta_data": {"title": "T1", "labels": {"slurry": True, "nitrate": False}}},
        {"url": "u2", "content_id": "c2", "meta_data": {"title": "T2", "labels": {"nitrate": True}}},
    ]
    kept, dropped = _relevance_filter_to_pages(rows, "nitrate")
    assert kept == [
        {"url": "u2", "title": "T2", "content_id": "c2"},
    ]
    assert dropped[0]["url"] == "u1"
    assert dropped[0]["label"] is False


def test_prepare_journal_keeps_upstream_funnel_stage():
    kept = [{"url": "u1", "title": "Keep", "content_id": "c1"}]
    dropped = [{
        "url": "u2",
        "title": "Drop",
        "content_id": "c2",
        "label": False,
        "stage": "pass2_drop",
        "reason": "incidental",
        "pass1_reason": "mentions slurry",
        "pass2_reason": "incidental mention",
        "exclusion_hit": "incidental",
    }]
    doc = prepare_journal(category="slurry", source_n=2, kept=kept, dropped=dropped)
    assert doc["counts"]["kept"] == 1
    assert doc["counts"]["dropped_not_on_topic"] == 1
    assert doc["counts"]["dropped_by_stage"] == {"pass2_drop": 1}
    assert doc["dropped_not_on_topic"][0]["pass1_reason"] == "mentions slurry"
    assert doc["kept"][0]["url"] == "u1"


def test_run_journal_lists_extracted_excluded_and_pending():
    pages = [{"url": "a", "title": "A"}, {"url": "b", "title": "B"}, {"url": "c", "title": "C"}]
    extracted = {
        "a": {"url": "a", "content_id": "ca", "meta_data": {"title": "A", "propositions": [{}, {}]}},
    }
    excluded = [{"url": "b", "title": "B", "category": "too_big", "reason": "truncated"}]
    doc = run_journal(pages=pages, extracted=extracted, excluded=excluded)
    assert doc["counts"] == {
        "input_pages": 3,
        "extracted": 1,
        "excluded": 1,
        "not_yet_processed": 1,
    }
    assert doc["extracted"][0]["n_propositions"] == 2
    assert doc["excluded"][0]["url"] == "b"
    assert doc["not_yet_processed"][0]["url"] == "c"


def test_prepare_cli_writes_funnel_next_to_pages(tmp_path: Path):
    source = tmp_path / "filter.json"
    source.write_text(json.dumps([
        {
            "url": "https://example.gov.uk/keep",
            "content_id": "c1",
            "meta_data": {
                "title": "Keep",
                "labels": {"slurry": True},
                "funnel": {"stage": "pass2_keep"},
            },
        },
        {
            "url": "https://example.gov.uk/drop",
            "content_id": "c2",
            "meta_data": {
                "title": "Drop",
                "labels": {"slurry": False},
                "reasons": {"slurry": "incidental"},
                "funnel": {
                    "stage": "pass2_drop",
                    "pass1_reason": "mentions slurry",
                    "pass2_reason": "incidental mention",
                    "exclusion_hit": "incidental",
                },
            },
        },
    ]))
    pages_out = tmp_path / "pages.json"
    result = CliRunner().invoke(app, ["prepare", str(source), str(pages_out), "--category", "slurry"])
    assert result.exit_code == 0, result.output
    funnel = json.loads((tmp_path / "funnel.json").read_text())
    assert funnel["counts"]["kept"] == 1
    assert funnel["counts"]["dropped_not_on_topic"] == 1
    assert funnel["dropped_not_on_topic"][0]["url"] == "https://example.gov.uk/drop"
    assert funnel["dropped_not_on_topic"][0]["stage"] == "pass2_drop"
    assert funnel["dropped_not_on_topic"][0]["pass1_reason"] == "mentions slurry"
    assert "1 dropped" in result.output

