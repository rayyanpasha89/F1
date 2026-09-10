from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.database import make_engine


@pytest.fixture
def client():
    if not Path("database/f1.db").exists():
        pytest.skip("Source integration test requires ingestion")
    with TestClient(create_app()) as c:
        yield c


def test_season_standings_and_race_flow(client):
    assert client.get("/api/health").status_code == 200
    seasons = client.get("/api/seasons").json()["data"]
    assert seasons[0]["year"] == 2024
    races = client.get("/api/races?year=2024").json()["data"]
    assert len(races) == 24
    for kind in ["drivers", "constructors"]:
        standings = client.get(f"/api/standings/{kind}/2024").json()["data"]
        assert standings[0]["position"] == 1
        assert standings[0]["round"] == 24
    race_id = races[-1]["race_id"]
    for kind in ["results", "qualifying", "pit-stops", "grid"]:
        response = client.get(f"/api/races/{race_id}/{kind}")
        assert response.status_code == 200
        assert len(response.json()["data"]) > 0
    grid = client.get(f"/api/races/{race_id}/grid").json()["data"]
    assert all("points" not in row and "position_order" not in row for row in grid)


def test_readiness_verifies_database_and_model_bundle(client):
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "archive_through": 2024,
        "model_version": "EXP-007+podium-count-v1",
        "checks": {"database": "ok", "model_bundle": "verified"},
    }


def test_readiness_failure_is_safe(client, monkeypatch):
    from backend.ml.evidence import ModelBundleError

    monkeypatch.setattr(
        "backend.main.verify_model_bundle",
        lambda: (_ for _ in ()).throw(ModelBundleError("secret /tmp/model.joblib")),
    )

    response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "detail": "Model bundle unavailable."}
    assert "secret" not in response.text and "/tmp" not in response.text


def test_profiles_and_empty_coverage(client):
    drivers = client.get("/api/profiles/drivers?year=2024").json()["data"]
    profile = client.get(f"/api/profiles/drivers/{drivers[0]['driver_id']}?year=2024").json()
    assert profile["results"] and all(r["year"] == 2024 for r in profile["results"])
    assert profile["career"]["races"] >= len(profile["results"])
    assert client.get("/api/standings/constructors/1950").json() == {"data": []}
    race_id = client.get("/api/races?year=1950").json()["data"][0]["race_id"]
    assert client.get(f"/api/races/{race_id}/pit-stops").json() == {"data": []}


def test_comparison_uses_only_earlier_form_and_valid_entrants(client):
    result = client.get("/api/races/1128/comparison?driver_a=844&driver_b=830")
    assert result.status_code == 200
    data = result.json()
    assert len(data["drivers"]) == 2
    for driver in data["drivers"]:
        assert driver["recent_starts"] == 5
        assert all(r["date"] < data["race"]["date"] for r in driver["recent_races"])
        assert all(r["race_id"] != 1128 for r in driver["recent_races"])
        assert driver["recent_race_points"] == sum(r["points"] for r in driver["recent_races"])
    assert client.get("/api/races/1128/comparison?driver_a=844&driver_b=844").status_code == 422
    assert client.get("/api/races/1128/comparison?driver_a=844&driver_b=999999").status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "/api/races/-1",
        "/api/races?year=2026",
        "/api/profiles/drivers/-1",
        "/api/standings/drivers/2026",
    ],
)
def test_not_found(client, url):
    assert client.get(url).status_code == 404


def test_bad_input_and_safe_database_error(client):
    assert client.get("/api/races?year=abc").status_code == 422
    assert client.get("/api/standings/drop/2024").status_code == 422
    with TestClient(create_app(make_engine("sqlite:///:memory:"))) as empty:
        response = empty.get("/api/health")
        assert response.status_code == 503
        assert "SELECT" not in response.text


def test_real_prediction_endpoint_and_training_era_refusal(client):
    if not Path("models/podium_model.joblib").exists():
        pytest.skip("Trained artifact required")
    race_id = client.get("/api/races?year=2024").json()["data"][-1]["race_id"]
    response = client.get(f"/api/predictions/{race_id}")
    assert response.status_code == 200
    assert len(response.json()["predictions"]) == 20
    earlier = client.get("/api/races?year=2018").json()["data"][0]["race_id"]
    assert client.get(f"/api/predictions/{earlier}").status_code == 422
    assert client.get("/api/predictions/-1").status_code == 404


def test_real_forecast_review_endpoint_and_safe_refusals(client):
    if not Path("models/podium_model.joblib").exists():
        pytest.skip("Trained artifact required")
    races = client.get("/api/races?year=2024").json()["data"]
    monaco = next(race for race in races if "Monaco" in race["name"])

    response = client.get(f"/api/predictions/{monaco['race_id']}/review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_type"] == "post_race_review"
    assert payload["race"]["race_id"] == monaco["race_id"]
    assert len(payload["predicted_podium"]) == 3
    assert len(payload["recorded_podium"]) == 3
    assert payload["top_three_hits"] == 3
    earlier = client.get("/api/races?year=2018").json()["data"][0]["race_id"]
    assert client.get(f"/api/predictions/{earlier}/review").status_code == 422
    assert client.get("/api/predictions/-1/review").status_code == 404


def test_chat_unsupported_path_without_live_llm(client):
    response = client.post("/api/chat", json={"question": "Who performs best in wet races?"})
    assert response.status_code == 200
    assert response.json()["intent"] == "unsupported"
    assert "sql" not in response.json()
    assert client.post("/api/chat", json={"question": "x"}).status_code == 422


def test_configured_chat_access_code_is_enforced(client, monkeypatch):
    monkeypatch.setenv("CHAT_ACCESS_CODE", "unit-test-access")
    assert client.get("/api/chat/config").json()["requires_access_code"] is True
    assert client.post("/api/chat", json={"question": "Is weather available?"}).status_code == 401
    assert (
        client.post(
            "/api/chat",
            headers={"x-chat-access-code": "unit-test-access"},
            json={"question": "Is weather available?"},
        ).status_code
        == 200
    )


def test_chat_logs_safe_execution_evidence_without_request_secrets(client, monkeypatch, caplog):
    access_secret = "access-code-SENTINEL"
    question_secret = "question-SENTINEL"
    monkeypatch.setenv("CHAT_ACCESS_CODE", access_secret)

    with caplog.at_level("INFO", logger="backend.main"):
        response = client.post(
            "/api/chat",
            headers={"x-chat-access-code": access_secret},
            json={"question": f"Is wet weather available? {question_secret}"},
        )

    assert response.status_code == 200
    messages = [
        record.getMessage() for record in caplog.records if "chat_complete" in record.getMessage()
    ]
    assert len(messages) == 1
    event = messages[0]
    assert "route=unsupported" in event
    assert "status=unsupported" in event
    assert "provider_calls=0" in event
    assert "repairs=0" in event
    assert "tables=-" in event
    assert "elapsed_ms=" in event
    assert access_secret not in event
    assert question_secret not in event
    assert "SELECT" not in event and "postgresql://" not in event
