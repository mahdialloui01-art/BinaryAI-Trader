from app.candle_pressure import candle_pressure, candle_pressure_series


def test_bullish_closed_candle_scores_buyers_higher():
    result = candle_pressure({"open": 100, "high": 110, "low": 99, "close": 109})
    assert result["buyer_strength"] > result["seller_strength"]
    assert result["dominant_side"] == "BUYERS"
    assert result["is_aggressor_delta"] is False


def test_bearish_closed_candle_scores_sellers_higher():
    result = candle_pressure({"open": 109, "high": 110, "low": 99, "close": 100})
    assert result["seller_strength"] > result["buyer_strength"]
    assert result["dominant_side"] == "SELLERS"


def test_live_candle_adds_tick_direction_proxy():
    result = candle_pressure({
        "open": 100, "high": 104, "low": 99, "close": 101,
        "upTicks": 16, "downTicks": 2, "tickCount": 20,
    }, live=True)
    assert result["tick_direction_proxy_percent"] > 0
    assert result["live"] is True
    assert result["is_aggressor_delta"] is False


def test_flat_candle_returns_unavailable_instead_of_fake_score():
    result = candle_pressure({"open": 100, "high": 100, "low": 100, "close": 100})
    assert result["status"] == "UNAVAILABLE_INVALID_OR_FLAT_CANDLE"
    assert result["buyer_strength"] is None


def test_series_returns_a_result_for_each_candle():
    rows = candle_pressure_series([
        {"timestamp": "a", "open": 1, "high": 3, "low": 1, "close": 2},
        {"timestamp": "b", "open": 2, "high": 4, "low": 1, "close": 3.8},
    ])
    assert [row["timestamp"] for row in rows] == ["a", "b"]
    assert len(rows) == 2
