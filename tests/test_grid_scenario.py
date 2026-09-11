from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from backend.database import make_engine
from backend.ml.predictor import PredictionUnavailable, Predictor
from backend.ml.scenario import GridScenarioRequest, GridScenarioService
from backend.ml.features import build_features


def _real_service():
    if not Path("models/podium_model.joblib").exists() or not Path("database/f1.db").exists():
        pytest.skip("Trusted model bundle and ingested archive required")
    predictor = Predictor(make_engine())
    race = predictor.frame().loc[lambda frame: frame.year == 2024].iloc[-1]
    race_id = int(race.race_id)
    starters = predictor.frame().loc[lambda frame: frame.race_id == race_id]
    first, second = starters.iloc[0], starters.iloc[1]
    return (
        predictor,
        GridScenarioService(predictor),
        race_id,
        int(first.driver_id),
        int(second.driver_id),
    )


def test_grid_scenario_request_is_strict_and_requires_distinct_drivers():
    assert GridScenarioRequest(driver_a_id=1, driver_b_id=2).model_dump() == {
        "driver_a_id": 1,
        "driver_b_id": 2,
    }
    with pytest.raises(ValidationError):
        GridScenarioRequest(driver_a_id=1, driver_b_id=1)
    with pytest.raises(ValidationError):
        GridScenarioRequest(driver_a_id=1, driver_b_id=2, feature_value=99)
    with pytest.raises(ValidationError):
        GridScenarioRequest(driver_a_id=0, driver_b_id=2)
    with pytest.raises(ValidationError):
        GridScenarioRequest(driver_a_id="1", driver_b_id=2)


def test_predictor_grid_swap_changes_only_copied_grid_inputs_and_is_symmetric():
    predictor, _, race_id, driver_a, driver_b = _real_service()

    forward = predictor.predict_grid_swap(race_id, driver_a, driver_b)
    reverse = predictor.predict_grid_swap(race_id, driver_b, driver_a)
    after = predictor.predict(race_id)

    original = {row["driver_id"]: row for row in forward["original"]["predictions"]}
    scenario = {row["driver_id"]: row for row in forward["scenario"]["predictions"]}
    reverse_scenario = {row["driver_id"]: row for row in reverse["scenario"]["predictions"]}
    after_rows = {row["driver_id"]: row for row in after["predictions"]}

    assert set(original) == set(scenario) == set(reverse_scenario) == set(after_rows)
    assert sum(row["probability"] for row in scenario.values()) == pytest.approx(3)
    assert forward["scenario"]["postprocessing"]["selected"]["adjusted_sum"] == pytest.approx(3)
    assert original[driver_a]["factors"] != scenario[driver_a]["factors"]
    assert original[driver_b]["factors"] != scenario[driver_b]["factors"]

    for driver_id in original:
        original_values = {
            factor["feature"]: factor["value"] for factor in original[driver_id]["factors"]
        }
        scenario_values = {
            factor["feature"]: factor["value"] for factor in scenario[driver_id]["factors"]
        }
        changed = {
            feature
            for feature in original_values
            if original_values[feature] != scenario_values[feature]
        }
        assert changed == ({"grid_position"} if driver_id in {driver_a, driver_b} else set())
        assert scenario[driver_id]["probability"] == pytest.approx(
            reverse_scenario[driver_id]["probability"]
        )
        assert original[driver_id]["probability"] == pytest.approx(
            after_rows[driver_id]["probability"]
        )

    original_a_grid = next(
        factor["value"]
        for factor in original[driver_a]["factors"]
        if factor["feature"] == "grid_position"
    )
    original_b_grid = next(
        factor["value"]
        for factor in original[driver_b]["factors"]
        if factor["feature"] == "grid_position"
    )
    scenario_a_grid = next(
        factor["value"]
        for factor in scenario[driver_a]["factors"]
        if factor["feature"] == "grid_position"
    )
    scenario_b_grid = next(
        factor["value"]
        for factor in scenario[driver_b]["factors"]
        if factor["feature"] == "grid_position"
    )
    assert (scenario_a_grid, scenario_b_grid) == (original_b_grid, original_a_grid)


def test_grid_scenario_service_returns_bounded_coherent_comparison():
    _, service, race_id, driver_a, driver_b = _real_service()

    result = service.swap(
        race_id,
        GridScenarioRequest(driver_a_id=driver_a, driver_b_id=driver_b),
    )
    payload = result.model_dump(mode="json")

    assert set(payload) == {
        "schema_version",
        "scenario_type",
        "race_id",
        "year",
        "experiment_id",
        "model_version",
        "modification",
        "postprocessing",
        "predictions",
        "evidence_boundary",
        "notes",
    }
    assert payload["schema_version"] == "f1-grid-scenario-v1"
    assert payload["scenario_type"] == "counterfactual_grid_swap"
    assert payload["model_version"] == "EXP-007+podium-count-v1"
    assert payload["evidence_boundary"] == {
        "input_scope": "recorded pre-race features with two grid positions swapped",
        "outcome_data_used": False,
        "causal": False,
        "validated_forecast": False,
        "statement": (
            "This counterfactual shows frozen-model sensitivity; it is not a causal estimate, "
            "an unseen evaluation, or a live-race recommendation."
        ),
    }
    rows = payload["predictions"]
    assert 2 <= len(rows) <= 40
    assert [row["scenario_rank"] for row in rows] == list(range(1, len(rows) + 1))
    assert set(row["original_rank"] for row in rows) == set(range(1, len(rows) + 1))
    assert sum(row["original_probability"] for row in rows) == pytest.approx(3)
    assert sum(row["scenario_probability"] for row in rows) == pytest.approx(3)
    assert sum(row["probability_delta"] for row in rows) == pytest.approx(0, abs=1e-10)
    assert all(0 < row["original_probability"] < 1 for row in rows)
    assert all(0 < row["scenario_probability"] < 1 for row in rows)
    assert {change["driver_id"] for change in payload["modification"]["drivers"]} == {
        driver_a,
        driver_b,
    }
    assert all(
        set(change)
        == {
            "driver_id",
            "recorded_grid_position",
            "scenario_grid_position",
            "original_grid_input",
            "scenario_grid_input",
        }
        for change in payload["modification"]["drivers"]
    )


def test_grid_scenario_rejects_nonstarters_and_direct_same_driver_calls():
    predictor, service, race_id, driver_a, _ = _real_service()

    with pytest.raises(PredictionUnavailable, match="Both drivers must be starters"):
        service.swap(
            race_id,
            GridScenarioRequest(driver_a_id=driver_a, driver_b_id=999999),
        )
    with pytest.raises(PredictionUnavailable, match="Choose two different drivers"):
        predictor.predict_grid_swap(race_id, driver_a, driver_a)


def test_pit_lane_grid_zero_is_distinct_from_its_model_proxy():
    predictor, service, _, _, _ = _real_service()
    frame = predictor.frame()
    pit_lane = frame.loc[frame.year.between(2022, 2024) & frame.grid.eq(0)].iloc[0]
    race = frame.loc[frame.race_id == pit_lane.race_id]
    other = race.loc[race.grid.gt(0) & race.grid_position.ne(25)].iloc[0]

    result = service.swap(
        int(pit_lane.race_id),
        GridScenarioRequest(
            driver_a_id=int(pit_lane.driver_id),
            driver_b_id=int(other.driver_id),
        ),
    )
    rows = {row.driver_id: row for row in result.predictions}
    pit_row = rows[int(pit_lane.driver_id)]
    other_row = rows[int(other.driver_id)]

    assert pit_row.recorded_grid_position == 0
    assert pit_row.original_grid_input == 25
    assert pit_row.scenario_grid_position == int(other.grid)
    assert pit_row.scenario_grid_input == int(other.grid_position)
    assert other_row.scenario_grid_position == 0
    assert other_row.scenario_grid_input == 25


def test_same_race_and_future_outcomes_cannot_change_grid_scenario(monkeypatch):
    rows = []
    for year in range(2010, 2025):
        for driver_id in range(1, 7):
            rows.append(
                {
                    "result_id": len(rows),
                    "race_id": year,
                    "driver_id": driver_id,
                    "constructor_id": (driver_id + 1) // 2,
                    "year": year,
                    "round": 1,
                    "date": f"{year}-03-01",
                    "circuit_id": 1,
                    "grid": driver_id,
                    "position": driver_id,
                    "position_order": driver_id,
                    "points": 7 - driver_id,
                    "status_name": "Finished",
                }
            )
    source = pd.DataFrame(rows)
    original_features = build_features(source)
    changed_source = source.copy()
    changed_source.loc[
        changed_source.year >= 2022,
        ["position", "position_order", "points", "status_name"],
    ] = [20, 20, 0, "Engine"]
    changed_features = build_features(changed_source)

    original = Predictor(make_engine("sqlite:///:memory:"))
    changed = Predictor(make_engine("sqlite:///:memory:"))
    monkeypatch.setattr(original, "frame", lambda: original_features)
    monkeypatch.setattr(changed, "frame", lambda: changed_features)

    first = original.predict_grid_swap(2022, 1, 2)["scenario"]
    second = changed.predict_grid_swap(2022, 1, 2)["scenario"]

    assert first == second
