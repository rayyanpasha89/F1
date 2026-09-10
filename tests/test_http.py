import re

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.http import install_http_policy


def _client():
    app = FastAPI()
    install_http_policy(app)

    @app.get("/api/history")
    def history():
        return {"data": ["historical-row"] * 200}

    @app.post("/api/chat")
    def chat():
        return {"status": "ok"}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/missing")
    def missing():
        raise HTTPException(404, "missing")

    @app.get("/broken")
    def broken():
        raise RuntimeError("failure-SENTINEL SELECT /Users/private")

    return TestClient(app)


def test_security_headers_and_request_ids_are_server_generated():
    with _client() as client:
        first = client.get("/api/history", headers={"x-request-id": "attacker-controlled"})
        second = client.get("/missing")

    request_id = first.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    assert request_id != "attacker-controlled"
    assert second.headers["x-request-id"] != request_id
    assert first.headers["x-content-type-options"] == "nosniff"
    assert first.headers["x-frame-options"] == "DENY"
    assert first.headers["referrer-policy"] == "no-referrer"
    assert first.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    assert first.headers["permissions-policy"] == (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    csp = first.headers["content-security-policy"]
    for directive in (
        "default-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "connect-src 'self'",
        "base-uri 'self'",
    ):
        assert directive in csp


def test_gzip_and_cache_policy_follow_route_sensitivity():
    with _client() as client:
        history = client.get("/api/history", headers={"accept-encoding": "gzip"})
        chat = client.post("/api/chat")
        health = client.get("/api/health")
        missing = client.get("/missing")

    assert history.headers["content-encoding"] == "gzip"
    assert history.headers["cache-control"] == "public, max-age=300"
    assert "Accept-Encoding" in history.headers["vary"]
    assert chat.headers["cache-control"] == "no-store"
    assert health.headers["cache-control"] == "no-store"
    assert missing.headers["cache-control"] == "no-store"


def test_unhandled_errors_are_safe_correlated_and_receive_delivery_headers(caplog):
    with caplog.at_level("INFO", logger="uvicorn.error"), _client() as client:
        response = client.get("/broken")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    event = next(
        record.getMessage() for record in caplog.records if "request_failed" in record.getMessage()
    )
    assert f"request_id={response.headers['x-request-id']}" in event
    assert "error_type=RuntimeError" in event
    assert "SENTINEL" not in event and "SELECT" not in event and "/Users/" not in event
