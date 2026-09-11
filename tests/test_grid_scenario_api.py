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


def _monaco_and_drivers(client):
    races = client.get("/api/races?year=2024").json()["data"]
    race_id = next(race["race_id"] for race in races if "Monaco" in race["name"])
    drivers = client.get(f"/api/races/{race_id}/grid").json()["data"]
    return race_id, drivers[0]["driver_id"], drivers[1]["driver_id"]


def test_grid_scenario_endpoint_is_allowlisted_coherent_and_not_cached(client):
    race_id, driver_a, driver_b = _monaco_and_drivers(client)

    response = client.post(
        f"/api/predictions/{race_id}/scenario",
        json={"driver_a_id": driver_a, "driver_b_id": driver_b},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]
    payload = response.json()
    assert payload["race_id"] == race_id
    assert payload["model_version"] == "EXP-007+podium-count-v1"
    assert payload["postprocessing"] == {
        "method": "race_logit_offset",
        "expected_podiums": 3,
        "original_sum": pytest.approx(3),
        "scenario_sum": pytest.approx(3),
    }
    assert len(payload["predictions"]) == len(
        client.get(f"/api/races/{race_id}/grid").json()["data"]
    )
    serialized = response.text.lower()
    for forbidden in ("database_url", "api_key", "password", "joblib", "/users/"):
        assert forbidden not in serialized


def test_grid_scenario_endpoint_rejects_invalid_or_unknown_drivers(client):
    race_id, driver_a, _ = _monaco_and_drivers(client)

    assert (
        client.post(
            f"/api/predictions/{race_id}/scenario",
            json={"driver_a_id": driver_a, "driver_b_id": driver_a},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/predictions/{race_id}/scenario",
            json={"driver_a_id": driver_a, "driver_b_id": 999999},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/predictions/{race_id}/scenario",
            json={"driver_a_id": driver_a, "driver_b_id": 830, "grid_position": 1},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/predictions/-1/scenario",
            json={"driver_a_id": 1, "driver_b_id": 2},
        ).status_code
        == 404
    )


def test_grid_scenario_log_is_bounded_and_correlatable(client, caplog):
    race_id, driver_a, driver_b = _monaco_and_drivers(client)

    with caplog.at_level("INFO", logger="uvicorn.error"):
        response = client.post(
            f"/api/predictions/{race_id}/scenario",
            json={"driver_a_id": driver_a, "driver_b_id": driver_b},
        )

    event = next(
        record.getMessage()
        for record in caplog.records
        if "scenario_complete" in record.getMessage()
    )
    assert f"request_id={response.headers['x-request-id']}" in event
    assert f"race_id={race_id}" in event
    assert "model_version=EXP-007+podium-count-v1" in event
    assert "scenario=grid_swap" in event
    assert "driver_count=20" in event
    assert "probability_sum=3.000000000000" in event
    assert "elapsed_ms=" in event
    for forbidden in (str(driver_a), str(driver_b), "SELECT", "/Users/", "question="):
        assert forbidden not in event
