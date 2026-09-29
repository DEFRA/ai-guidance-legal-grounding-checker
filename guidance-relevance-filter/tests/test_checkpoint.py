"""Checkpoint fingerprint and URL-order guards — the reason resume is safe."""

import pytest

from guidance_relevance_filter.checkpoint import Checkpoint, ResumeIncompatible, fingerprint_for


def test_fingerprint_changes_when_the_input_file_changes(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text("[]")
    b.write_text("[1]")
    kwargs = dict(
        n_pages=0, category="fish", model="m", adjudicator_model="n",
        max_words=1, shard_name=None, categories=[{"name": "fish"}],
        lexicons={"fish": ["x"]},
    )
    assert fingerprint_for(input_path=a, **kwargs) != fingerprint_for(input_path=b, **kwargs)


def test_fingerprint_changes_when_the_router_or_threshold_changes(tmp_path):
    a = tmp_path / "a.json"
    a.write_text("[]")
    kwargs = dict(
        n_pages=0, category="fish", model="m", adjudicator_model="n",
        max_words=1, shard_name=None, categories=[{"name": "fish"}],
        lexicons={"fish": ["x"]},
    )
    base = fingerprint_for(input_path=a, **kwargs)
    assert fingerprint_for(input_path=a, **kwargs, router="cosine") != base
    assert fingerprint_for(input_path=a, **kwargs, cosine_threshold=0.3) != base
    assert fingerprint_for(input_path=a, **kwargs, embed_model="other-model") != base
    assert fingerprint_for(input_path=a, **kwargs, llm_mode="sync") != base
    assert fingerprint_for(input_path=a, **kwargs)["llm_mode"] == "batch"


def test_fingerprint_treats_missing_llm_mode_as_batch(tmp_path):
    cp = Checkpoint(tmp_path / "checkpoint.json")
    fp = {"k": 1}
    cp.init(fp, "2026-01-01T00:00:00")
    cp.assert_fingerprint({"k": 1, "llm_mode": "batch"})
    with pytest.raises(ResumeIncompatible, match="llm_mode"):
        cp.assert_fingerprint({"k": 1, "llm_mode": "sync"})


def test_record_reply_round_trips(tmp_path):
    cp = Checkpoint(tmp_path / "checkpoint.json")
    cp.init({"k": 1}, "2026-01-01T00:00:00")
    cp.record_pass1_reply("0", '{"x": true}', {"input": 3, "output": 2})
    assert cp.pass1_replies == {"0": {"text": '{"x": true}', "input": 3, "output": 2}}
    reloaded = Checkpoint(tmp_path / "checkpoint.json")
    assert reloaded.pass1_replies["0"]["text"] == '{"x": true}'


def test_record_urls_refuses_a_changed_list(tmp_path):
    cp = Checkpoint(tmp_path / "checkpoint.json")
    cp.init({"k": 1}, "2026-01-01T00:00:00")
    cp.record_pass1_routing(["https://a"])
    with pytest.raises(ResumeIncompatible, match="routed_urls changed"):
        cp.record_pass1_routing(["https://b"])
    cp.record_pass1_routing(["https://a"])  # identical is fine
