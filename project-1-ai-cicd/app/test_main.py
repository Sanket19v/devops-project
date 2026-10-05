from main import app


def test_health():
    r = app.test_client().get("/health")
    assert r.status_code == 200 and r.json["status"] == "ok"


def test_error_returns_500():
    assert app.test_client().get("/error").status_code == 500


def test_metrics_exposed():
    app.test_client().get("/")
    assert b"app_requests_total" in app.test_client().get("/metrics").data
