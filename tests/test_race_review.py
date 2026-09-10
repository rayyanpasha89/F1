from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from backend.database import make_engine
from backend.ml.features import build_features
from backend.ml.predictor import PredictionUnavailable, Predictor
from backend.ml.probability import project_expected_count
from backend.ml.review import RaceReviewService
from backend.services.analytics import Analytics


class StaticPredictor:
    def __init__(self, probabilities, calls=None):
        self.probabilities = probabilities
        self.calls = calls

    def predict(self, race_id):
        if self.calls is not None:
            self.calls.append("predict")
        return {
            "race_id": race_id,
            "year": 2024,
            "model_version": "EXP-007+podium-count-v1",
            "postprocessing": {"method": "race_logit_offset", "expected_podiums": 3},
            "predictions": [
                {
                    "driver_id": driver_id,
                    "constructor_id": driver_id,
                    "probability": probability,
                    "factors": [{"feature": "grid_position", "log_odds_contribution": -driver_id}],
                }
                for driver_id, probability in enumerate(self.probabilities, start=1)
            ],
        }


class StaticAnalytics:
    def __init__(self, positions=(1, 2, 4, 3, 5), calls=None):
        self.positions = positions
        self.calls = calls

    def race(self, race_id):
        if self.calls is not None:
            self.calls.append("race")
        return {
            "race_id": race_id,
            "year": 2024,
            "round": 8,
            "name": "Synthetic Grand Prix",
            "date": "2024-05-26",
            "circuit_name": "Synthetic Circuit",
            "country": "Testland",
        }

    def race_table(self, race_id, kind):
        assert kind == "results"
        if self.calls is not None:
            self.calls.append("results")
        return [
            {
                "driver_id": driver_id,
                "constructor_id": driver_id,
                "driver_name": f"Driver {driver_id}",
                "constructor_name": f"Team {driver_id}",
                "grid": driver_id,
                "position": position,
                "position_text": str(position),
                "position_order": position,
            }
            for driver_id, position in enumerate(self.positions, start=1)
        ]


def test_review_metrics_ordering_and_allowlisted_contract():
    calls = []
    review = RaceReviewService(
        StaticPredictor([0.9, 0.8, 0.7, 0.4, 0.2], calls), StaticAnalytics(calls=calls)
    ).review(100)

    assert calls == ["predict", "race", "results"]
    assert review.review_type == "post_race_review"
    assert review.top_three_hits == 2
    assert review.exact_podium_set is False
    expected = np.mean((np.array([0.9, 0.8, 0.7, 0.4, 0.2]) - [1, 1, 0, 1, 0]) ** 2)
    assert review.brier_score == pytest.approx(expected)
    assert review.mean_absolute_error == pytest.approx(
        np.mean(np.abs(np.array([0.9, 0.8, 0.7, 0.4, 0.2]) - [1, 1, 0, 1, 0]))
    )
    assert [row.driver_id for row in review.predicted_podium] == [1, 2, 3]
    assert [row.driver_id for row in review.recorded_podium] == [1, 2, 4]
    assert review.surprises.largest_overprediction.driver_id == 3
    assert review.surprises.largest_underprediction.driver_id == 4
    payload = review.model_dump(mode="json")
    assert set(payload) == {
        "review_type",
        "race",
        "model_version",
        "postprocessor",
        "predicted_podium",
        "recorded_podium",
        "top_three_hits",
        "exact_podium_set",
        "brier_score",
        "mean_absolute_error",
        "surprises",
        "drivers",
        "notes",
    }
    serialized = str(payload).lower()
    assert "points" not in serialized and "status_name" not in serialized
    assert "/users/" not in serialized and "secret" not in serialized


def test_review_has_stable_tie_breaking_and_rejects_incomplete_results():
    tied = RaceReviewService(StaticPredictor([0.7, 0.7, 0.7, 0.7, 0.2]), StaticAnalytics()).review(
        100
    )
    assert [row.driver_id for row in tied.predicted_podium] == [1, 2, 3]

    with pytest.raises(PredictionUnavailable, match="Recorded podium is unavailable"):
        RaceReviewService(
            StaticPredictor([0.9, 0.8, 0.7, 0.4, 0.2]),
            StaticAnalytics(positions=(1, 2, 4, 5, 6)),
        ).review(100)


def _source_frame():
    rows = []
    for year in range(2010, 2025):
        for driver in range(1, 7):
            rows.append(
                {
                    "result_id": len(rows) + 1,
                    "race_id": year,
                    "driver_id": driver,
                    "constructor_id": (driver + 1) // 2,
                    "year": year,
                    "round": 1,
                    "date": f"{year}-03-01",
                    "circuit_id": 1,
                    "grid": driver,
                    "position": driver,
                    "position_order": driver,
                    "position_text": str(driver),
                    "points": max(0, 7 - driver),
                    "status_name": "Finished",
                }
            )
    return pd.DataFrame(rows)


class FramePredictor:
    def __init__(self, source):
        self.source = source

    def predict(self, race_id):
        race = build_features(self.source).loc[lambda frame: frame.race_id == race_id]
        if race.empty or not race.year.between(2022, 2024).all():
            raise PredictionUnavailable("Unsupported model year.")
        margin = (
            1.8 - 0.55 * race.grid_position.to_numpy() + 0.35 * race.driver_recent_podium.to_numpy()
        )
        raw = expit(margin)
        adjusted = project_expected_count(raw).adjusted
        predictions = []
        for index, (_, row) in enumerate(race.iterrows()):
            predictions.append(
                {
                    "driver_id": int(row.driver_id),
                    "constructor_id": int(row.constructor_id),
                    "probability": float(adjusted[index]),
                    "factors": [
                        {"feature": "grid_position", "value": float(row.grid_position)},
                        {
                            "feature": "driver_recent_podium",
                            "value": float(row.driver_recent_podium),
                        },
                    ],
                }
            )
        return {
            "race_id": race_id,
            "year": int(race.iloc[0].year),
            "model_version": "EXP-TEST+podium-count-v1",
            "postprocessing": {"method": "race_logit_offset", "expected_podiums": 3},
            "predictions": sorted(
                predictions, key=lambda row: (-row["probability"], row["driver_id"])
            ),
        }


class FrameAnalytics:
    def __init__(self, source):
        self.source = source

    def race(self, race_id):
        row = self.source.loc[self.source.race_id == race_id].iloc[0]
        return {
            "race_id": race_id,
            "year": int(row.year),
            "round": int(row["round"]),
            "name": f"Race {race_id}",
            "date": row.date,
            "circuit_name": "Circuit 1",
            "country": "Testland",
        }

    def race_table(self, race_id, kind):
        assert kind == "results"
        race = self.source.loc[self.source.race_id == race_id]
        return [
            {
                "driver_id": int(row.driver_id),
                "constructor_id": int(row.constructor_id),
                "driver_name": f"Driver {int(row.driver_id)}",
                "constructor_name": f"Team {int(row.constructor_id)}",
                "grid": int(row.grid),
                "position": int(row.position),
                "position_text": str(int(row.position)),
                "position_order": int(row.position_order),
            }
            for _, row in race.iterrows()
        ]


def _forecast_signature(review):
    return [(row.driver_id, row.probability, row.predicted_rank) for row in review.drivers]


def test_same_race_outcomes_cannot_change_forecast_probabilities_or_factors():
    source = _source_frame()
    original_predictor = FramePredictor(source)
    original = RaceReviewService(original_predictor, FrameAnalytics(source)).review(2023)
    original_factors = original_predictor.predict(2023)["predictions"]

    changed = source.copy()
    mask = changed.race_id == 2023
    changed.loc[mask, "position"] = [4, 3, 2, 1, 5, 6]
    changed.loc[mask, "position_order"] = [4, 3, 2, 1, 5, 6]
    changed.loc[mask, "points"] = [0, 8, 18, 25, 0, 0]
    changed.loc[mask, "status_name"] = "Engine"
    changed_predictor = FramePredictor(changed)
    mutated = RaceReviewService(changed_predictor, FrameAnalytics(changed)).review(2023)

    assert _forecast_signature(mutated) == _forecast_signature(original)
    assert changed_predictor.predict(2023)["predictions"] == original_factors
    assert mutated.recorded_podium != original.recorded_podium


def test_future_outcomes_cannot_change_an_earlier_review():
    source = _source_frame()
    original = RaceReviewService(FramePredictor(source), FrameAnalytics(source)).review(2023)
    changed = source.copy()
    mask = changed.race_id == 2024
    changed.loc[mask, "position"] = [6, 5, 4, 3, 2, 1]
    changed.loc[mask, "position_order"] = [6, 5, 4, 3, 2, 1]
    changed.loc[mask, "points"] = 100
    changed.loc[mask, "status_name"] = "Engine"

    after = RaceReviewService(FramePredictor(changed), FrameAnalytics(changed)).review(2023)

    assert after == original


def test_real_monaco_2024_review_has_three_hits_and_recomputable_brier():
    if not Path("database/f1.db").exists() or not Path("models/podium_model.joblib").exists():
        pytest.skip("Trusted model and archive are required")
    analytics = Analytics(make_engine())
    race_id = next(row["race_id"] for row in analytics.races(2024) if "Monaco" in row["name"])
    review = RaceReviewService(Predictor(analytics.engine), analytics).review(race_id)

    assert review.top_three_hits == 3
    assert review.exact_podium_set is True
    recomputed = np.mean(
        [(row.probability - int(row.recorded_podium)) ** 2 for row in review.drivers]
    )
    assert review.brier_score == pytest.approx(recomputed)
