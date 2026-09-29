"""Ballpark USD for a GRF run from ``would_route``.

Preview never calls Anthropic, so this is slurry-title-gate (2026-09-04)
observed $/page, not a quote. Pass-2 volume is unknown until Haiku finishes;
the range varies a body-length factor and the pass-1-true rate.
"""

from __future__ import annotations

from html import escape
from typing import Any

# content-audit-data-assets/.../slurry-title-gate/metrics.json
_SLURRY_PASS1_USD = 1.8472
_SLURRY_PASS1_ROUTED = 544
_SLURRY_PASS2_USD = 1.5036
_SLURRY_PASS2_POSITIVES = 178

PASS1_USD_PER_ROUTED = _SLURRY_PASS1_USD / _SLURRY_PASS1_ROUTED
PASS2_USD_PER_POSITIVE = _SLURRY_PASS2_USD / _SLURRY_PASS2_POSITIVES
PASS1_TRUE_RATE = _SLURRY_PASS2_POSITIVES / _SLURRY_PASS1_ROUTED

LENGTH_LOW = 0.6
LENGTH_HIGH = 1.5
TRUE_RATE_LOW = 0.20
TRUE_RATE_HIGH = 0.50

SOURCE = "slurry-title-gate"

RANGE_TIP = "Not a quote — longer pages or more pass-1 trues cost more."
SLURRY_TIP = "Per-page $ from the slurry-title-gate run (2026-09-04)."
BATCH_TIP = "Anthropic batch API — tokens billed at 0.5× on-demand."
SYNC_TIP = "Anthropic Messages API — billed at on-demand (1×) rates."

BADGES = (
    {"label": "slurry", "tip": SLURRY_TIP},
    {"label": "0.5×", "tip": BATCH_TIP},
)
SYNC_BADGES = (
    {"label": "slurry", "tip": SLURRY_TIP},
    {"label": "1×", "tip": SYNC_TIP},
)


def badge_html(label: str, tip: str) -> str:
    return (
        f'<abbr class="cost-badge" tabindex="0" data-tip="{escape(tip, quote=True)}"'
        f' aria-label="{escape(tip, quote=True)}">{escape(label)}</abbr>'
    )


BATCH_BADGE_HTML = badge_html("0.5×", BATCH_TIP)
SYNC_BADGE_HTML = badge_html("1×", SYNC_TIP)


def llm_batch(mode: str) -> bool:
    return mode != "sync"


def llm_badge_html(batch: bool) -> str:
    return BATCH_BADGE_HTML if batch else SYNC_BADGE_HTML


def _money(value: float, places: int) -> float:
    return round(value, places)


def _label(value: float, places: int) -> str:
    return f"${_money(value, places):.{places}f}"


def _estimate_html(
    label: str, range_label: str | None, badges: tuple[dict[str, str], ...] | list[dict[str, str]],
) -> str:
    bits = [f'<span class="cost-point">{escape(label)}</span>']
    if range_label:
        bits.append(
            f'<abbr class="cost-range" tabindex="0" data-tip="{escape(RANGE_TIP, quote=True)}"'
            f' aria-label="{escape(RANGE_TIP, quote=True)}">({escape(range_label)})</abbr>'
        )
    bits.extend(badge_html(b["label"], b["tip"]) for b in badges)
    return f'<span class="cost-line">{"".join(bits)}</span>'


def estimate_usd(would_route: int, *, batch: bool = True) -> dict[str, Any]:
    n = max(0, int(would_route))
    if n == 0:
        zero = _label(0.0, 2)
        summary = f"{zero} — nothing would go to the model."
        return {
            "usd": 0.0,
            "low_usd": 0.0,
            "high_usd": 0.0,
            "label": zero,
            "range_label": f"{zero}–{zero}",
            "would_route": 0,
            "pass2_pages_typical": 0,
            "source": SOURCE,
            "summary": summary,
            "html": _estimate_html(summary, None, ()),
            "badges": [],
        }

    typical_p2 = n * PASS1_TRUE_RATE
    typical = n * PASS1_USD_PER_ROUTED + typical_p2 * PASS2_USD_PER_POSITIVE
    low = (
        n * LENGTH_LOW * PASS1_USD_PER_ROUTED
        + n * TRUE_RATE_LOW * LENGTH_LOW * PASS2_USD_PER_POSITIVE
    )
    high = (
        n * LENGTH_HIGH * PASS1_USD_PER_ROUTED
        + n * TRUE_RATE_HIGH * LENGTH_HIGH * PASS2_USD_PER_POSITIVE
    )
    if not batch:
        typical *= 2
        low *= 2
        high *= 2
    places = 2 if typical >= 0.10 else 4
    label = _label(typical, places)
    range_label = f"{_label(low, places)}–{_label(high, places)}"
    summary = f"{label} ({range_label})"
    badge_set = BADGES if batch else SYNC_BADGES
    return {
        "usd": _money(typical, places),
        "low_usd": _money(low, places),
        "high_usd": _money(high, places),
        "label": label,
        "range_label": range_label,
        "would_route": n,
        "pass2_pages_typical": round(typical_p2),
        "source": SOURCE,
        "summary": summary,
        "html": _estimate_html(label, range_label, badge_set),
        "badges": [dict(b) for b in badge_set],
    }
