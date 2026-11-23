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
    assert "/binary-options/{symbol}/contracts" in paths


def test_gold_candles_reject_unknown_interval():
    response = TestClient(app).get("/forex/gold/candles?interval=2m")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_resolve_gold_symbol_prefers_deriv_xauusd():
    class FakeFeed:
        async def symbols(self):
            return [
                {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
                {"symbol": "frxXAUUSD", "display_name": "Gold/USD"},
            ]

    item = await resolve_gold_symbol(FakeFeed())
    assert item["symbol"] == "frxXAUUSD"


@pytest.mark.asyncio
async def test_resolve_gold_symbol_fails_closed_when_deriv_has_no_gold():
    class FakeFeed:
        async def symbols(self):
            return [{"symbol": "frxEURUSD", "display_name": "EUR/USD"}]

    with pytest.raises(HTTPException) as error:
        await resolve_gold_symbol(FakeFeed())
    assert error.value.status_code == 503
