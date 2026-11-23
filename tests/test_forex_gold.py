import asyncio
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.forex_gold import resolve_gold_symbol
from app.main import app


def test_forex_gold_routes_are_separate_from_binary_options():
    paths = set(app.openapi()["paths"])
    assert "/forex/gold/symbol" in paths
    assert "/forex/gold/quote" in paths
    assert "/forex/gold/candles" in paths
    assert "/forex/gold/stream" in paths
    assert "/forex/gold/analyze" in paths
    assert "/binary-options/{symbol}/contracts" in paths


def test_gold_candles_reject_unknown_interval():
    response = TestClient(app).get("/forex/gold/candles?interval=2m")
    assert response.status_code == 422


def test_resolve_gold_symbol_uses_configured_deriv_underlying_without_catalogue():
    class FakeFeed:
        async def symbols(self):
            raise AssertionError("Gold analysis must not call active_symbols")

    item = asyncio.run(resolve_gold_symbol(FakeFeed()))
    assert item["symbol"] == "frxXAUUSD"
    assert item["symbol_source"] == "configured_deriv_underlying"


def test_resolve_gold_symbol_is_stable_when_catalogue_is_rate_limited():
    class RateLimitedFeed:
        async def symbols(self):
            raise RuntimeError("HTTP 429")

    item = asyncio.run(resolve_gold_symbol(RateLimitedFeed()))
    assert item["symbol"] == "frxXAUUSD"



def test_gold_analysis_uses_one_snapshot_and_short_cache(monkeypatch):
    import app.forex_gold as gold_module

    calls = {"count": 0}

    async def fake_snapshot(self, symbol):
        calls["count"] += 1
        assert symbol == "frxXAUUSD"
        return (
            {"symbol": symbol, "price": 3600.0, "timestamp": "2026-11-23T05:00:00Z"},
            {"1m": [], "5m": [], "15m": [], "1h": [], "4h": []},
        )

    monkeypatch.setattr("app.forex_gold.DerivFeed.gold_analysis_snapshot", fake_snapshot)
    monkeypatch.setattr("app.forex_gold.analyze_gold", lambda candles, quote: {
        "status": "ready", "decision": "WAIT", "score": 12, "execution_enabled": False
    })
    gold_module._GOLD_ANALYSIS_CACHE.update({"created": 0.0, "result": None})

    client = TestClient(app)
    first = client.get("/forex/gold/analyze")
    second = client.get("/forex/gold/analyze")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1
    assert second.json()["cache_age_seconds"] >= 0
