from fastapi.testclient import TestClient

from app.main import app
from app.feeds.normalization import candle_timestamp


def test_health_is_research_only():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["execution_enabled"] is False
    assert body["free_first"] is True


def test_example_signal_is_no_trade():
    client = TestClient(app)
    response = client.get("/signals/example")
    assert response.status_code == 200
    assert response.json()["decision"] == "NO_TRADE"


def test_history_stats_uses_configured_sqlite_path(tmp_path, monkeypatch):
    monkeypatch.setenv("BINARYAI_DB_PATH", str(tmp_path / "api.db"))
    client = TestClient(app)
    response = client.get("/history/stats")
    assert response.status_code == 200
    assert response.json()["stored_candles"] == 0


def test_biquote_open_time_is_used_for_candle_freshness():
    stamp = candle_timestamp({"openTime": "2026-11-21T20:00:00Z", "open": 1.0})
    assert stamp is not None
    assert stamp.isoformat() == "2026-11-21T20:00:00+00:00"


def test_otc_stream_route_is_registered():
    paths = set(app.openapi()["paths"])
    assert "/quotex/stream" in paths
    assert "/quotex/symbols" in paths


def test_deriv_public_routes_are_registered():
    paths = set(app.openapi()["paths"])
    assert "/deriv/stream" in paths
    assert "/deriv/{symbol}/contracts" in paths
    assert "/symbols" in paths



def test_professional_analysis_and_walk_forward_routes_are_registered():
    paths = set(app.openapi()["paths"])
    assert "/analysis/{symbol}" in paths
    assert "/research/walk-forward/{symbol}" in paths


def test_market_candles_include_per_candle_pressure_without_trade_execution(monkeypatch):
    class FakeMarket:
        async def reference_candles(self, symbol, interval, limit):
            return [{
                "provider": "deriv", "symbol": symbol, "interval": interval,
                "timestamp": "2026-11-23T12:00:00Z",
                "open": 100.0, "high": 110.0, "low": 99.0, "close": 109.0,
            }]

    monkeypatch.setattr("app.main.data_service", lambda: FakeMarket())
    response = TestClient(app).get("/market/R_100/candles?interval=1m&limit=10")
    assert response.status_code == 200
    body = response.json()
    candle = body["candles"][0]
    assert candle["buyer_strength"] > candle["seller_strength"]
    assert candle["dominant_side"] == "BUYERS"
    assert candle["is_aggressor_delta"] is False
    assert body["pressure_is_probability"] is False
