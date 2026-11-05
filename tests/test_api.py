import main
from database import Database


def test_api_routes_and_dashboard(tmp_path, monkeypatch):
    test_database = Database(tmp_path / "api.db")
    monkeypatch.setattr(main, "database", test_database)

    dashboard = main.dashboard()
    assert str(dashboard.path).endswith("index.html")
    assert main.health_live() == {"status": "ok"}
    assert main.get_readings(limit=120, device_id=None) == []
    assert main.get_alerts(limit=50, device_id=None) == []

    paths = main.app.openapi()["paths"]
    assert "/api/status" in paths
    assert "/api/readings" in paths
    assert "/api/alerts" in paths
    assert "/health/live" in paths
    assert "/docs" not in paths  # Rota interna do FastAPI, servida separadamente.
