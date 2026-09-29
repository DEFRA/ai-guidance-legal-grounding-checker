from guidance_relevance_web.cost_estimate import estimate_usd


def test_slurry_calibration_typical_matches_recorded_run():
    est = estimate_usd(544)
    assert est["usd"] == 3.35
    assert est["low_usd"] == 1.66
    assert est["high_usd"] == 6.22
    assert est["pass2_pages_typical"] == 178
    assert est["label"] == "$3.35"
    assert est["range_label"] == "$1.66–$6.22"
    assert est["summary"] == "$3.35 ($1.66–$6.22)"
    assert "cost-badge" in est["html"]
    assert "0.5×" in est["html"]
    assert "slurry" in est["html"]
    assert "Anthropic batch API" in est["html"]
    assert est["source"] == "slurry-title-gate"


def test_sync_estimate_is_double_the_batch_rate():
    batch = estimate_usd(544, batch=True)
    sync = estimate_usd(544, batch=False)
    assert sync["usd"] == round(batch["usd"] * 2, 2)
    assert "1×" in sync["html"]
    assert "0.5×" not in sync["html"]
    assert "on-demand" in sync["html"]


def test_zero_routed_is_free():
    est = estimate_usd(0)
    assert est["usd"] == 0.0
    assert est["summary"] == "$0.00 — nothing would go to the model."
    assert est["badges"] == []
