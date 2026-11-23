from datetime import datetime, timedelta, timezone

from app.research.gold_analysis import analyze_gold


def _trend_bars(count, seconds, start, slope):
    rows = []
    for i in range(count):
        base = 2300 + i * slope
        stamp = start + timedelta(seconds=i * seconds)
        rows.append({
            "timestamp": stamp.isoformat().replace("+00:00", "Z"),
            "open": base - slope * 0.2,
            "high": base + 0.5,
            "low": base - 0.5,
            "close": base,
        })
    return rows


def test_gold_analysis_fails_closed_on_missing_history():
    result = analyze_gold({"1m": [], "5m": [], "15m": [], "1h": []})
    assert result["decision"] == "WAIT"
    assert result["execution_enabled"] is False
    assert result["status"] == "insufficient_data"


def test_gold_analysis_requires_fresh_quote():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    candles = {
        "1m": _trend_bars(240, 60, now - timedelta(minutes=241), 0.03),
        "5m": _trend_bars(120, 300, now - timedelta(minutes=605), 0.15),
        "15m": _trend_bars(100, 900, now - timedelta(minutes=1501), 0.45),
        "1h": _trend_bars(80, 3600, now - timedelta(hours=81), 1.8),
        "4h": _trend_bars(80, 14400, now - timedelta(hours=321), 7.2),
    }
    result = analyze_gold(candles, {"price": 2400, "age_seconds": 90, "symbol": "frxXAUUSD"}, now)
    assert result["decision"] == "WAIT"
    assert any("قديم" in reason for reason in result["reasons"])
    assert result["execution_enabled"] is False


def test_gold_analysis_does_not_call_score_win_probability():
    now = datetime.now(timezone.utc)
    result = analyze_gold({"1m": [], "5m": [], "15m": [], "1h": []}, now=now)
    assert "ليست احتمال ربح" in result["score_label"]



def test_gold_analysis_exposes_dominant_bias_and_watch_zone_not_win_probability():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    candles = {
        "1m": _trend_bars(240, 60, now - timedelta(minutes=241), 0.03),
        "5m": _trend_bars(120, 300, now - timedelta(minutes=605), 0.15),
        "15m": _trend_bars(100, 900, now - timedelta(minutes=1501), 0.45),
        "1h": _trend_bars(80, 3600, now - timedelta(hours=81), 1.8),
        "4h": _trend_bars(80, 14400, now - timedelta(hours=321), 7.2),
    }
    last_close = candles["5m"][-1]["close"]
    result = analyze_gold(
        candles,
        {"price": last_close, "age_seconds": 1, "symbol": "frxXAUUSD"},
        now,
    )
    assert result["dominant_direction"] == "bullish"
    assert result["dominant_direction_label"] == "صاعد"
    assert 0 <= result["direction_confidence_pct"] <= 100
    assert "ليست احتمال نجاح" in result["direction_confidence_label"]
    assert result["entry_zones"]
    zone = result["entry_zones"][0]
    assert zone["side"] == "CALL"
    assert zone["low"] <= zone["reference"] <= zone["high"]
    assert zone["status"] in ("watch", "wait_confirmation")
    assert result["execution_enabled"] is False
