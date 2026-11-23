from fastapi.testclient import TestClient
from app.main import app


def test_forex_gold_routes_are_separate_from_binary_options():
    paths = set(app.openapi()["paths"])
    assert "/forex/gold/quote" in paths
    assert "/forex/gold/candles" in paths
    assert "/binary-options/{symbol}/contracts" in paths


def test_gold_candles_reject_unknown_interval():
    response = TestClient(app).get("/forex/gold/candles?interval=2m")
    assert response.status_code == 422
