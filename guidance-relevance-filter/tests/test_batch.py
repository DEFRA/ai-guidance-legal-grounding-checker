"""Batch-poll progress, disconnect retries, and reattach-to-existing-batch."""

from types import SimpleNamespace
from typing import cast

import anthropic
import pytest
from anthropic.types import Message, TextBlock
from httpx import Request

from guidance_relevance_filter._batch import _fmt_elapsed, _log_progress, submit_and_collect
from guidance_relevance_filter.checkpoint import ResumeIncompatible

REQ = {"custom_id": "0", "params": {"model": "m", "max_tokens": 1, "messages": []}}


def _counts(succeeded=0, processing=0, errored=0):
    return SimpleNamespace(
        succeeded=succeeded, processing=processing, errored=errored, canceled=0, expired=0,
    )


def _reply(text="ok"):
    return cast(Message, SimpleNamespace(
        content=[TextBlock(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=3, output_tokens=2),
    ))


def _row(custom_id="0", text="ok"):
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="succeeded", message=_reply(text)),
    )


def test_fmt_elapsed():
    assert _fmt_elapsed(9) == "9s"
    assert _fmt_elapsed(75) == "1m15s"
    assert _fmt_elapsed(3725) == "1h02m"


def test_progress_line_shows_done_over_total(capsys, monkeypatch):
    monkeypatch.setattr("guidance_relevance_filter._batch.time.monotonic", lambda: 90)
    batch = SimpleNamespace(
        id="msgbatch_test",
        request_counts=_counts(succeeded=12, processing=525),
    )
    _log_progress(batch, "classify", started=0)
    err = capsys.readouterr().err
    assert "classify msgbatch_test: 12/537 done" in err
    assert "525 processing" in err
    assert "elapsed 1m30s" in err


def test_reattach_skips_create_and_collects(monkeypatch):
    monkeypatch.setattr("guidance_relevance_filter._batch.time.sleep", lambda _s: None)
    created = []
    ended = SimpleNamespace(
        id="msgbatch_old", processing_status="ended",
        request_counts=_counts(succeeded=1),
    )
    client = SimpleNamespace(messages=SimpleNamespace(batches=SimpleNamespace(
        create=lambda requests: created.append(requests) or ended,
        retrieve=lambda _id: ended,
        results=lambda _id: iter([_row()]),
    )))
    raw, usage, meta = submit_and_collect(
        client, [REQ], label="classify", resume_id="msgbatch_old",
    )
    assert created == []
    assert raw == {"0": "ok"}
    assert usage == {"input": 3, "output": 2}
    assert meta["id"] == "msgbatch_old"
    assert meta["resumed"] is True
    assert meta["submitted"] == 1


def test_poll_retries_a_connection_error_then_continues(monkeypatch, capsys):
    monkeypatch.setattr("guidance_relevance_filter._batch.time.sleep", lambda _s: None)
    req = Request("GET", "https://api.anthropic.com")
    calls = {"n": 0}
    in_progress = SimpleNamespace(
        id="b", processing_status="in_progress", request_counts=_counts(processing=1),
    )
    ended = SimpleNamespace(
        id="b", processing_status="ended", request_counts=_counts(succeeded=1),
    )

    def retrieve(_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise anthropic.APIConnectionError(message="wifi down", request=req)
        return ended

    client = SimpleNamespace(messages=SimpleNamespace(batches=SimpleNamespace(
        create=lambda requests: in_progress,
        retrieve=retrieve,
        results=lambda _id: iter([_row()]),
    )))
    raw, _, meta = submit_and_collect(client, [REQ], label="classify")
    assert raw["0"] == "ok"
    assert meta["resumed"] is False
    assert "wifi down" in capsys.readouterr().err
    assert calls["n"] == 2


def test_resume_refuses_when_batch_size_does_not_match(monkeypatch):
    monkeypatch.setattr("guidance_relevance_filter._batch.time.sleep", lambda _s: None)
    ended = SimpleNamespace(
        id="b", processing_status="ended",
        request_counts=_counts(succeeded=99),
    )
    client = SimpleNamespace(messages=SimpleNamespace(batches=SimpleNamespace(
        create=lambda requests: ended,
        retrieve=lambda _id: ended,
        results=lambda _id: iter([]),
    )))
    with pytest.raises(ResumeIncompatible, match="99 requests"):
        submit_and_collect(client, [REQ], label="classify", resume_id="b")
