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
