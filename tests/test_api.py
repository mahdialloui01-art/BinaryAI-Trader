from fastapi.testclient import TestClient

from app.main import app


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
