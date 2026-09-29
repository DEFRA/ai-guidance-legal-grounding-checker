"""Token-usage accounting for Guidance Proposition Extractor's sync and batch paths.

Mirrors Proposition Matcher's cost model so every pipeline stage reports cost the same way:
per-1M-token list rates, the Message Batches API's 50% discount, and the 10%
rate on cache-read input tokens. The rate table is duplicated rather than shared
because each stage is a standalone package; if a rate is corrected here it should
be corrected in Proposition Matcher's ``pipeline/batch_match.py`` and Match Adjudicator's ``cost.py`` too.
"""

from __future__ import annotations

# Per-1M-token list rates (input, output), full price. The Batch API bills 0.5x.
RATES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}
BATCH_DISCOUNT = 0.5


def new_usage() -> dict[str, int]:
    return {"input": 0, "output": 0, "cache_read": 0}


def add_usage(usage: dict, message) -> None:
    """Fold one Messages/batch response's token counts into ``usage`` in place.

    Call this for every *billed* response — including a succeeded message that
    later fails our parse — so the recorded cost matches what Anthropic charged.
    """
    u = message.usage
    usage["input"] += u.input_tokens
    usage["output"] += u.output_tokens
    usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0


def cost_usd(usage: dict, model: str, *, batch: bool) -> float:
    """USD cost for ``usage`` at ``model``'s rates; ``batch`` applies the 0.5x."""
    rin, rout = RATES.get(model, RATES["claude-sonnet-4-6"])
    billable_in = usage["input"] + usage["cache_read"] * 0.1
    cost = billable_in / 1e6 * rin + usage["output"] / 1e6 * rout
    return cost * (BATCH_DISCOUNT if batch else 1.0)
