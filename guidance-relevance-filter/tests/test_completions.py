"""Sync adapter: skip checkpointed replies; concurrency still returns every id."""

from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from anthropic import AuthenticationError, BadRequestError
from anthropic.types import Message, TextBlock

from guidance_relevance_filter.completions import (
    AnthropicSyncCompletions,
    CompletionRequest,
    anthropic_completions,
)


def _req(cid: str, content: str = "x") -> CompletionRequest:
    return CompletionRequest(
        custom_id=cid, model="m", max_tokens=8,
        messages=[{"role": "user", "content": content}],
    )


def _message(text: str, *, inp: int = 1, out: int = 1):
    return cast(Message, SimpleNamespace(
        content=[TextBlock(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=inp, output_tokens=out),
    ))


def _status_error(cls, message: str, status: int):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(
        message,
        response=httpx.Response(status, request=request),
        body={"type": "error", "error": {"message": message}},
    )


def test_factory_rejects_unknown_mode():
    try:
        anthropic_completions("deepseek")
    except ValueError as e:
        assert "batch" in str(e) and "sync" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_sync_skips_already_checkpointed_replies():
    created: list[str] = []

    def create(**kwargs):
        created.append(kwargs["messages"][0]["content"])
        return _message("new", inp=2, out=3)

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    sync = AnthropicSyncCompletions(client, concurrency=2)
    raw, usage, meta = sync.complete_many(
        [_req("0", "a"), _req("1", "b")],
        label="classify",
        already={"0": {"text": "old", "input": 7, "output": 4}},
    )
    assert raw == {"0": "old", "1": "new"}
    assert created == ["b"]
    assert usage == {"input": 9, "output": 7}
    assert meta["resumed"] is True
    assert meta["mode"] == "sync"
    assert meta["submitted"] == 2
    assert meta["collected"] == 2
    assert meta["id"] is None
    assert meta["concurrency"] == 2


def test_sync_concurrency_returns_every_custom_id():
    def create(**kwargs):
        return _message(kwargs["messages"][0]["content"].upper())

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    sync = AnthropicSyncCompletions(client, concurrency=3)
    reqs = [_req(str(i), f"p{i}") for i in range(6)]
    raw, _, meta = sync.complete_many(reqs, label="adjudicate")
    assert raw == {str(i): f"P{i}" for i in range(6)}
    assert meta["collected"] == 6
    assert meta["request_counts"]["errored"] == 0


def test_sync_fires_on_result_for_new_replies_only():
    seen: list[str] = []
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: _message("ok")),
    )
    AnthropicSyncCompletions(client, concurrency=1).complete_many(
        [_req("0"), _req("1")],
        label="t",
        already={"0": {"text": "cached", "input": 1, "output": 1}},
        on_result=lambda cid, text, usage: seen.append(cid),
    )
    assert seen == ["1"]


def test_sync_credit_error_is_fatal_not_a_page_miss():
    def create(**_kwargs):
        raise _status_error(
            BadRequestError,
            "Your credit balance is too low to access the Anthropic API. "
            "Please go to Plans & Billing to upgrade or purchase credits.",
            400,
        )

    sync = AnthropicSyncCompletions(
        SimpleNamespace(messages=SimpleNamespace(create=create)),
        concurrency=2,
    )
    with pytest.raises(BadRequestError, match="credit balance"):
        sync.complete_many([_req("0"), _req("1")], label="classify")


def test_sync_auth_error_is_fatal():
    def create(**_kwargs):
        raise _status_error(AuthenticationError, "invalid x-api-key", 401)

    sync = AnthropicSyncCompletions(
        SimpleNamespace(messages=SimpleNamespace(create=create)),
        concurrency=1,
    )
    with pytest.raises(AuthenticationError, match="x-api-key"):
        sync.complete_one(_req("0"))


def test_sync_prompt_too_long_is_a_recoverable_miss():
    def create(**_kwargs):
        raise _status_error(
            BadRequestError, "prompt is too long: 200000 tokens > 200000 maximum", 400,
        )

    sync = AnthropicSyncCompletions(
        SimpleNamespace(messages=SimpleNamespace(create=create)),
        concurrency=2,
    )
    raw, _, meta = sync.complete_many([_req("0"), _req("1")], label="classify")
    assert raw == {}
    assert meta["request_counts"]["errored"] == 2
    assert sync.complete_one(_req("rescue")) is None
