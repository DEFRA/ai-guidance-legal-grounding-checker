"""Shared Anthropic batch mechanics for Guidance Relevance Filter's two passes.

Both the pass-1 classifier and the pass-2 adjudicator submit a batch of requests,
poll it to completion, and collect the first text block of every succeeded reply.
That submit/poll/collect loop lives here so neither pass owns a private copy.
"""
from __future__ import annotations

import sys
import time
from collections.abc import Callable

import anthropic
from anthropic import Anthropic
from anthropic.types import Message, TextBlock
from anthropic.types.messages import MessageBatch
from anthropic.types.messages.batch_create_params import Request

from .checkpoint import ResumeIncompatible

POLL_SECONDS = 10
MAX_SERVER_RETRIES = 8

# Sleep/wake and wifi blips: keep retrying. 429/5xx: bounded backoff, then raise.
_DISCONNECT = (anthropic.APIConnectionError, anthropic.APITimeoutError)
_SERVER = (
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.OverloadedError,
)


def log(msg: str) -> None:
    """Progress to stderr, flushed so a long run isn't a silent wait."""
    print(msg, file=sys.stderr, flush=True)


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def text_of(message: Message) -> str:
    """First text block of a model reply, or '' (skips thinking / tool blocks)."""
    for block in message.content:
        if isinstance(block, TextBlock):
            return block.text
    return ""


def request_counts(batch: MessageBatch) -> dict[str, int] | None:
    """Anthropic's per-batch status breakdown, or None if the object has none."""
    c = getattr(batch, "request_counts", None)
    if c is None:
        return None
    return {
        "succeeded": int(c.succeeded),
        "processing": int(c.processing),
        "errored": int(c.errored),
        "canceled": int(getattr(c, "canceled", 0) or 0),
        "expired": int(getattr(c, "expired", 0) or 0),
    }


def _retry[T](op: Callable[[], T], *, what: str) -> T:
    """Retry ``op`` on disconnect forever, on 429/5xx a handful of times."""
    disconnect_attempt = 0
    server_attempt = 0
    while True:
        try:
            return op()
        except _DISCONNECT as e:
            disconnect_attempt += 1
            delay = min(60, POLL_SECONDS * min(disconnect_attempt, 6))
            log(
                f"  {what}: {type(e).__name__}: {e}; "
                f"retry {disconnect_attempt} in {delay}s (keeps retrying — sleep/wake is ok)"
            )
            time.sleep(delay)
        except _SERVER as e:
            server_attempt += 1
            delay = min(60, 2**server_attempt)
            log(
                f"  {what}: {type(e).__name__}: {e}; "
                f"retry {server_attempt}/{MAX_SERVER_RETRIES} in {delay}s"
            )
            if server_attempt > MAX_SERVER_RETRIES:
                raise
            time.sleep(delay)


def _log_progress(batch: MessageBatch, label: str, *, started: float, done: bool = False) -> None:
    """Print one batch-poll line: done/total plus the Anthropic status breakdown."""
    c = request_counts(batch)
    if c is None:
        log(
            f"  {label} {batch.id}: in progress  "
            f"elapsed {_fmt_elapsed(time.monotonic() - started)}"
        )
        return
    total = c["succeeded"] + c["processing"] + c["errored"] + c["canceled"] + c["expired"]
    extras = ""
    if c["canceled"]:
        extras += f", {c['canceled']} canceled"
    if c["expired"]:
        extras += f", {c['expired']} expired"
    state = "finished" if done else "polling"
    log(
        f"  {label} {batch.id}: {c['succeeded']}/{total} done ({state}; "
        f"{c['processing']} processing, {c['errored']} errored{extras})  "
        f"elapsed {_fmt_elapsed(time.monotonic() - started)}"
    )


def _assert_resume_size(batch: MessageBatch, n: int, label: str) -> None:
    c = request_counts(batch)
    if c is None:
        return
    total = c["succeeded"] + c["processing"] + c["errored"] + c["canceled"] + c["expired"]
    if total != n:
        raise ResumeIncompatible(
            f"{label} batch {batch.id} has {total} requests but this run has {n}. "
            "Refusing to pair custom_ids. Use --fresh."
        )


def submit_and_collect(
    client: Anthropic,
    requests: list[Request],
    *,
    label: str,
    resume_id: str | None = None,
    on_submitted: Callable[[str], None] | None = None,
) -> tuple[dict[str, str], dict[str, int], dict]:
    """Create (or reattach to) a batch, poll to completion, return texts/usage/meta.

    ``usage`` totals the ``input``/``output`` tokens over the succeeded rows so the
    caller can price the pass. Rows that errored or were cancelled are simply absent
    from the result (and unbilled); the caller decides how to handle a missing
    custom_id (pass 1 rescues, pass 2 keeps).

    ``batch_meta`` is the durable identity of the run: Anthropic batch id, how many
    requests were submitted vs collected, wall time, and the final request_counts.

    ``resume_id`` skips ``create`` and polls an existing batch — the checkpoint's
    reason to exist. ``on_submitted`` fires with the batch id *before* polling so a
    crash mid-wait still has something to reattach to.
    """
    n = len(requests)
    started = time.monotonic()
    if resume_id:
        log(f"  {label}: reattaching to {resume_id} ({n} requests) — not submitting a new batch")
        batch = _retry(
            lambda: client.messages.batches.retrieve(resume_id),
            what=f"{label} retrieve {resume_id}",
        )
        _assert_resume_size(batch, n, label)
    else:
        log(
            f"  {label}: uploading {n} requests to the Anthropic batch API "
            "(this can take a while)…"
        )
        batch = client.messages.batches.create(requests=requests)
        log(
            f"  {label} submitted {batch.id} ({n} requests) in "
            f"{_fmt_elapsed(time.monotonic() - started)}; "
            f"polling every {POLL_SECONDS}s until Anthropic finishes the batch"
        )
    if on_submitted is not None:
        on_submitted(batch.id)

    while batch.processing_status == "in_progress":
        _log_progress(batch, label, started=started)
        time.sleep(POLL_SECONDS)
        poll_id = batch.id
        batch = _retry(
            lambda bid=poll_id: client.messages.batches.retrieve(bid),
            what=f"{label} poll {poll_id}",
        )
    if request_counts(batch) is not None:
        _log_progress(batch, label, started=started, done=True)

    log(f"  {label}: collecting results for {batch.id}…")
    collect_id = batch.id
    rows = _retry(
        lambda: list(client.messages.batches.results(collect_id)),
        what=f"{label} collect {collect_id}",
    )
    raw: dict[str, str] = {}
    usage = {"input": 0, "output": 0}
    for r in rows:
        if r.result.type == "succeeded":
            raw[r.custom_id] = text_of(r.result.message)
            u = r.result.message.usage
            usage["input"] += u.input_tokens
            usage["output"] += u.output_tokens
    log(f"  {label}: collected {len(raw)}/{n} succeeded replies")
    meta = {
        "id": batch.id,
        "submitted": n,
        "collected": len(raw),
        "elapsed_seconds": int(time.monotonic() - started),
        "request_counts": request_counts(batch),
        "resumed": bool(resume_id),
    }
    return raw, usage, meta
