from app.storage import CandleStore


def test_store_upserts_and_returns_chronological_rows(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    rows = [
        {"timestamp": "2026-11-21T12:01:00Z", "open": 2},
        {"timestamp": "2026-11-21T12:00:00Z", "open": 1},
        {"timestamp": "not-a-time", "open": 3},
    ]
    result = store.upsert("biquote", "EURUSD", "1m", rows)
    assert result == {"stored": 2, "skipped_invalid_timestamp": 1}
    store.upsert("biquote", "EURUSD", "1m", [dict(rows[0], open=2.5)])
    saved = store.get("biquote", "EURUSD", "1m")
    assert [row["open"] for row in saved] == [1, 2.5]
    assert store.count() == 2


def test_store_filters_since_and_provider(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    store.upsert("biquote", "EURUSD", "1m", [
        {"timestamp": "2026-11-21T12:00:00Z", "close": 1},
        {"timestamp": "2026-11-21T12:01:00Z", "close": 2},
    ])
    assert len(store.get("biquote", "EURUSD", "1m", since="2026-11-21T12:01:00Z")) == 1
    assert store.count("other") == 0
