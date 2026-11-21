from app.feeds.normalization import align_candles, classify_market, parse_timestamp


def test_market_classification_is_conservative():
    assert classify_market("EURUSD_otc") == "otc"
    assert classify_market("EURUSD", "real") == "unknown"


def test_parse_timestamp_supports_iso_and_milliseconds():
    assert parse_timestamp("2026-11-21T12:00:00Z").isoformat() == "2026-11-21T12:00:00+00:00"
    assert parse_timestamp(1795262400000) is not None


def test_alignment_matches_only_same_open_time():
    left = [{"timestamp": "2026-11-21T12:00:00Z", "open": 1, "high": 2, "low": 0.5, "close": 1.5}]
    right = [{"time": "2026-11-21T12:00:00+00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5},
             {"time": "2026-11-21T12:01:00Z", "open": 1, "high": 2, "low": 0.5, "close": 1.5}]
    result = align_candles(left, right, tolerance=0)
    assert result["matched_candles"] == 1
    assert result["right_unmatched"] == 1
    assert result["comparisons"][0]["within_tolerance"] is True
