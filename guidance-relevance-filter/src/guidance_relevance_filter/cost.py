"""Token-cost accounting for Guidance Relevance Filter's two LLM passes.

Pass 1 (Haiku) and pass 2 (Sonnet) bill at different rates. Batch mode is 0.5x;
sync mode and oversized-page rescue are full price. ``cost_usd`` prices one
token bucket; the CLI sums the buckets.

If a model isn't in ``RATES`` (e.g. an overridden ``--model``) the price is
``None`` rather than a guess: the tokens are still recorded, but an invented
dollar figure would be worse than an honest gap.
"""
from __future__ import annotations

# Per-1M-token rates (input, output), full price. The Batch API bills at 0.5x.
RATES = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}
BATCH_DISCOUNT = 0.5


def cost_usd(input_tokens: int, output_tokens: int, model: str, *, batch: bool) -> float | None:
    """Batch- or full-price USD for a token bucket, or ``None`` if ``model`` is unpriced."""
    rate = RATES.get(model)
    if rate is None:
        return None
    rin, rout = rate
    mult = BATCH_DISCOUNT if batch else 1.0
    return round((input_tokens / 1e6 * rin + output_tokens / 1e6 * rout) * mult, 4)
