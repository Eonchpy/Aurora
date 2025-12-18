from fastapi.testclient import TestClient

import aurora_api.main as main


def test_health_ok(monkeypatch):
    monkeypatch.setattr(main, "check_database", lambda: True)
    client = TestClient(main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in {"ok", "degraded"}
    assert data["database"] == "ok"
