from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client():
    if not Path("database/f1.db").exists() or not Path("models/podium_model.joblib").exists():
        pytest.skip("Trusted model bundle and ingested archive required")
    with TestClient(create_app()) as test_client:
        yield test_client


def _monaco(client):
    return next(
        race["race_id"]
        for race in client.get("/api/races?year=2024").json()["data"]
        if "Monaco" in race["name"]
    )


def test_podium_outcome_endpoint_is_allowlisted_coherent_and_cacheable(client):
    race_id = _monaco(client)
    forecast = client.get(f"/api/predictions/{race_id}").json()

    response = client.get(f"/api/predictions/{race_id}/podium-outcomes?limit=7")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["x-request-id"]
    payload = response.json()
    assert set(payload) == {
        "schema_version",
        "outcome_type",
        "race_id",
        "year",
        "experiment_id",
        "model_version",
        "diagnostics",
        "outcomes",
        "driver_marginals",
        "co_podium_pairs",
        "evidence_boundary",
        "notes",
    }
    assert payload["race_id"] == race_id
    assert payload["year"] == 2024
    assert payload["model_version"] == forecast["model_version"]
    assert payload["diagnostics"]["combination_count"] == 1140
    assert payload["diagnostics"]["returned_outcome_count"] == 7
    assert payload["diagnostics"]["probability_sum"] == pytest.approx(1, abs=1e-12)
    assert payload["diagnostics"]["reconstructed_marginal_sum"] == pytest.approx(3, abs=1e-10)
    assert payload["diagnostics"]["maximum_marginal_error"] < 1e-8
    assert len(payload["outcomes"]) == 7
    assert len(payload["driver_marginals"]) == 20
    released = {row["driver_id"]: row["probability"] for row in forecast["predictions"]}
    for row in payload["driver_marginals"]:
        assert row["released_probability"] == pytest.approx(released[row["driver_id"]])
        assert row["reconstructed_probability"] == pytest.approx(
            released[row["driver_id"]], abs=1e-8
        )
    serialized = response.text.lower()
    for forbidden in ("database_url", "api_key", "password", "joblib", "/users/"):
        assert forbidden not in serialized


def test_podium_outcome_endpoint_validates_limit_and_supported_race(client):
    race_id = _monaco(client)
    assert client.get(f"/api/predictions/{race_id}/podium-outcomes?limit=3").status_code == 200
    assert client.get(f"/api/predictions/{race_id}/podium-outcomes?limit=25").status_code == 200
    assert client.get(f"/api/predictions/{race_id}/podium-outcomes?limit=2").status_code == 422
    assert client.get(f"/api/predictions/{race_id}/podium-outcomes?limit=26").status_code == 422
    assert client.get(f"/api/predictions/{race_id}/podium-outcomes?limit=x").status_code == 422
    earlier = client.get("/api/races?year=2018").json()["data"][0]["race_id"]
    assert client.get(f"/api/predictions/{earlier}/podium-outcomes").status_code == 422
    assert client.get("/api/predictions/-1/podium-outcomes").status_code == 404


def test_podium_outcome_log_is_bounded_and_correlatable(client, caplog):
    race_id = _monaco(client)

    with caplog.at_level("INFO", logger="uvicorn.error"):
        response = client.get(f"/api/predictions/{race_id}/podium-outcomes?limit=6")

    event = next(
        record.getMessage()
        for record in caplog.records
        if "podium_outcomes_complete" in record.getMessage()
    )
    assert f"request_id={response.headers['x-request-id']}" in event
    assert f"race_id={race_id}" in event
    assert "model_version=EXP-007+podium-count-v1" in event
    assert "method=maximum_entropy_fixed_size" in event
    assert "driver_count=20" in event
    assert "combination_count=1140" in event
    assert "returned_count=6" in event
    assert "probability_sum=1.000000000000" in event
    assert "maximum_marginal_error=" in event
    assert "elapsed_ms=" in event
    for forbidden in ("driver_id=", "SELECT", "/Users/", "question=", "http"):
        assert forbidden not in event
