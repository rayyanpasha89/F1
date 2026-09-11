import json

import pandas as pd
import pytest

from scripts.evaluate_podium_outcomes import evaluate_podium_outcomes


class StubPredictor:
    def __init__(self):
        self.calls = []

    def frame(self):
        return pd.DataFrame(
            [
                {"race_id": 10, "year": 2022},
                {"race_id": 10, "year": 2022},
                {"race_id": 20, "year": 2024},
                {"race_id": 20, "year": 2024},
            ]
        )

    def predict(self, race_id):
        self.calls.append(race_id)
        return {
            "race_id": race_id,
            "year": 2022 if race_id == 10 else 2024,
            "experiment_id": "EXP-007",
            "model_version": "EXP-007+podium-count-v1",
            "predictions": [
                {"driver_id": 1, "probability": 0.9},
                {"driver_id": 2, "probability": 0.8},
                {"driver_id": 3, "probability": 0.7},
                {"driver_id": 4, "probability": 0.6},
            ],
        }


def test_evaluator_writes_only_aggregate_reproducible_evidence(tmp_path):
    output = tmp_path / "podium-outcomes.json"
    predictor = StubPredictor()

    report = evaluate_podium_outcomes(predictor, output)

    assert predictor.calls == [10, 20]
    assert report["schema_version"] == "f1-podium-outcome-evaluation-v1"
    assert report["status"] == "passed"
    assert report["model_version"] == "EXP-007+podium-count-v1"
    assert report["support"] == {"years": [2022, 2024], "race_count": 2, "driver_rows": 8}
    assert report["distribution"]["method"] == "maximum_entropy_fixed_size"
    assert report["distribution"]["podium_size"] == 3
    assert report["distribution"]["complete_outcome_count"] == 8
    assert report["distribution"]["combination_count_range"] == [4, 4]
    assert report["integrity"]["maximum_distribution_sum_error"] < 1e-12
    assert report["integrity"]["maximum_reconstructed_sum_error"] < 1e-9
    assert report["integrity"]["maximum_marginal_error"] < 1e-8
    assert report["evidence_boundary"]["outcome_data_used"] is False
    assert report["evidence_boundary"]["joint_forecast_validated"] is False
    assert json.loads(output.read_text()) == report
    serialized = output.read_text()
    for forbidden in ("driver_id", 'probability"', "database_url", "/Users/"):
        assert forbidden not in serialized


def test_evaluator_refuses_to_overwrite_before_prediction(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("keep")
    predictor = StubPredictor()

    with pytest.raises(FileExistsError):
        evaluate_podium_outcomes(predictor, output)

    assert predictor.calls == []
    assert output.read_text() == "keep"
