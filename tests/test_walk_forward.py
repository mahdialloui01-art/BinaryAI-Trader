from datetime import datetime, timedelta, timezone

from app.research.walk_forward import walk_forward_binary_options


def candles(count, start, step, drift=0.01):
    rows = []
    price = 100.0
    for i in range(count):
        before = price
        price += drift
        stamp = start + timedelta(seconds=i * step)
        rows.append({
            "timestamp": stamp.isoformat().replace("+00:00", "Z"),
            "open": before,
            "high": price + 0.01,
            "low": before - 0.01,
            "close": price,
        })
    return rows


def test_walk_forward_uses_chronological_point_in_time_replay():
    start = datetime.now(timezone.utc) - timedelta(hours=36)
    base = candles(240, start, 60)
    higher = {
        "5m": candles(100, start - timedelta(minutes=500), 300),
        "15m": candles(100, start - timedelta(minutes=1500), 900),
    }
    result = walk_forward_binary_options(
        base, "frxEURUSD", "1m", higher, payout=0.8, expiry_bars=1
    )
    assert result["lookahead_bias"] is False
    assert result["execution_enabled"] is False
    assert result["candles_used"] == 240
    assert set(result["chronological_splits"]) == {"train", "validation", "test"}
    assert result["break_even_win_rate"] == 0.55556
    assert result["research_assessment"]["live_signal_allowed"] is False
    assert result["research_assessment"]["status"] in {"INSUFFICIENT_EVIDENCE", "RESEARCH_PROMISING_NOT_VALIDATED"}
    assert "test_wilson_95_lower_bound" in result["validation_vs_test"]
