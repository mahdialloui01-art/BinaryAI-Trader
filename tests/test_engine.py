from datetime import datetime, timedelta, timezone

from app.research.engine import analyze_binary_options


def _trend_candles(direction=1, count=160, start=None, step=60):
    rows = []
    price = 100.0
    start = start or datetime.now(timezone.utc) - timedelta(seconds=count * step)
    for i in range(count):
        previous = price
        price += direction * 0.08
        stamp = start + timedelta(seconds=i * step)
        rows.append({
            "timestamp": stamp.isoformat().replace("+00:00", "Z"),
            "open": previous,
            "high": max(previous, price) + 0.02,
            "low": min(previous, price) - 0.02,
            "close": price,
        })
    return rows


def test_engine_returns_full_explainable_research_report():
    now = datetime.now(timezone.utc)
    result = analyze_binary_options(
        _trend_candles(count=160, start=now - timedelta(seconds=160 * 60)),
        "EURUSD", "1m",
        {
            "5m": _trend_candles(count=80, start=now - timedelta(seconds=80 * 300), step=300),
            "15m": _trend_candles(count=80, start=now - timedelta(seconds=80 * 900), step=900),
        },
    )
    assert result["decision"] in {"CALL", "PUT", "NO_TRADE"}
    assert result["execution_enabled"] is False
    assert result["score_is_probability"] is False
    assert result["candles_used"] == 160
    assert "rationale" in result and "blockers" in result
    assert {"trend_structure", "market_structure", "momentum", "liquidity_sweep",
            "multi_timeframe"}.issubset(result["modules"])
    assert "ema100" in result["indicators"]
    assert result["engine_version"] == "2.3.0"
    assert result["confidence"] is None
    assert result["confidence_status"] == "NOT_CALIBRATED"
    assert result["confluence_score"] == result["score"]
    assert "STRATEGY_NOT_VALIDATED_FOR_LIVE_SIGNALS" in result["blockers"]
    assert result["decision"] == "NO_TRADE"
    assert result["market_regime"]["trend_state"] in {"DIRECTIONAL", "MIXED", "CHOPPY"}
    assert result["market_regime"]["volatility_state"] in {"EXPANSION", "COMPRESSION", "NORMAL", "UNAVAILABLE"}
    forecasts = result["horizon_forecasts"]
    assert set(forecasts) == {"1m", "2m", "5m"}
    for key, minutes in (("1m", 1), ("2m", 2), ("5m", 5)):
        assert forecasts[key]["horizon_minutes"] == minutes
        assert forecasts[key]["decision"] in {"CALL", "PUT", "NO_TRADE"}
        assert forecasts[key]["score"] <= 100
        assert len(forecasts[key]["evidence"]) == 5


def test_engine_fails_closed_with_insufficient_data():
    result = analyze_binary_options(_trend_candles(count=80), "EURUSD")
    assert result["decision"] == "NO_TRADE"
    assert result["status"] == "insufficient_data"
    assert result["execution_enabled"] is False


def test_engine_blocks_stale_closed_candles():
    old = datetime.now(timezone.utc) - timedelta(days=2)
    result = analyze_binary_options(
        _trend_candles(count=160, start=old),
        "EURUSD", "1m",
        {
            "5m": _trend_candles(count=80, start=old, step=300),
            "15m": _trend_candles(count=80, start=old, step=900),
        },
    )
    assert result["decision"] == "NO_TRADE"
    assert "STALE_CLOSED_CANDLES" in result["blockers"]



def test_research_mode_can_replay_candidates_without_enabling_live_signals():
    now = datetime.now(timezone.utc)
    rows = _trend_candles(count=160, start=now - timedelta(seconds=160 * 60))
    result = analyze_binary_options(rows, "EURUSD", "1m", research_mode=True)
    assert "STRATEGY_NOT_VALIDATED_FOR_LIVE_SIGNALS" not in result["blockers"]
    assert result["execution_enabled"] is False
    assert result["confidence"] is None



def test_engine_sorts_newest_first_candle_batches_chronologically():
    now = datetime.now(timezone.utc)
    rows = _trend_candles(count=160, start=now - timedelta(seconds=160 * 60))
    ordered = analyze_binary_options(rows, "EURUSD", "1m", research_mode=True)
    reversed_result = analyze_binary_options(list(reversed(rows)), "EURUSD", "1m", research_mode=True)
    assert reversed_result["latest_closed_candle"] == ordered["latest_closed_candle"]
    assert reversed_result["indicators"] == ordered["indicators"]
    assert reversed_result["research_candidate"] == ordered["research_candidate"]


def test_engine_rejects_future_dated_candles():
    now = datetime.now(timezone.utc)
    rows = _trend_candles(count=160, start=now + timedelta(minutes=5))
    result = analyze_binary_options(rows, "EURUSD", "1m", as_of=now, research_mode=True)
    assert result["quality"]["future_timestamp_detected"] is True
    assert result["quality"]["stale"] is True
    assert result["decision"] == "NO_TRADE"
    assert "STALE_CLOSED_CANDLES" in result["blockers"]
