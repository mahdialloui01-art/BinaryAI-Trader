from app.research.engine import analyze_binary_options


def _trend_candles(direction=1, count=100):
    rows = []
    price = 100.0
    for i in range(count):
        previous = price
        price += direction * 0.08
        rows.append({
            "timestamp": f"2026-01-01T00:{i:02d}:00Z" if i < 60 else f"2026-01-01T01:{i-60:02d}:00Z",
            "open": previous,
            "high": max(previous, price) + 0.02,
            "low": min(previous, price) - 0.02,
            "close": price,
        })
    return rows


def test_engine_returns_explainable_research_decision():
    result = analyze_binary_options(_trend_candles(), "EURUSD", "1m", {
        "5m": _trend_candles(), "15m": _trend_candles()
    })
    assert result["decision"] in {"CALL", "PUT", "NO_TRADE"}
    assert result["execution_enabled"] is False
    assert result["score_is_probability"] is False
    assert result["candles_used"] == 100
    assert "rationale" in result and "blockers" in result
    assert "ema50" in result["indicators"]


def test_engine_fails_closed_with_insufficient_data():
    result = analyze_binary_options(_trend_candles(count=30), "EURUSD")
    assert result["decision"] == "NO_TRADE"
    assert result["status"] == "insufficient_data"
    assert result["execution_enabled"] is False
