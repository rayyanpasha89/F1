from itertools import combinations
from pathlib import Path

import numpy as np
import pytest

from backend.database import make_engine
from backend.ml.outcomes import PodiumOutcomeService, fit_fixed_size_distribution
from backend.ml.predictor import PredictionUnavailable, Predictor


def test_symmetric_distribution_is_uniform_and_canonical():
    fitted = fit_fixed_size_distribution(
        driver_ids=[4, 2, 1, 3],
        marginals=[0.75, 0.75, 0.75, 0.75],
    )

    assert fitted.driver_ids == (1, 2, 3, 4)
    assert fitted.driver_sets == tuple(combinations((1, 2, 3, 4), 3))
    assert fitted.probabilities == pytest.approx((0.25, 0.25, 0.25, 0.25))
    assert fitted.reconstructed_marginals == pytest.approx((0.75,) * 4)
    assert fitted.entropy_bits == pytest.approx(2)


def test_distribution_reconstructs_marginals_and_is_permutation_invariant():
    driver_ids = [50, 10, 40, 20, 30]
    marginals = [0.2, 0.9, 0.4, 0.8, 0.7]

    fitted = fit_fixed_size_distribution(driver_ids, marginals)
    permuted = fit_fixed_size_distribution(
        list(reversed(driver_ids)),
        list(reversed(marginals)),
    )

    assert fitted.driver_sets == permuted.driver_sets
    assert fitted.probabilities == pytest.approx(permuted.probabilities, abs=1e-12)
    assert sum(fitted.probabilities) == pytest.approx(1, abs=1e-12)
    assert sum(fitted.reconstructed_marginals) == pytest.approx(3, abs=1e-12)
    expected = dict(zip(driver_ids, marginals, strict=True))
    assert dict(
        zip(fitted.driver_ids, fitted.reconstructed_marginals, strict=True)
    ) == pytest.approx(expected, abs=1e-9)
    assert fitted.maximum_marginal_error < 1e-9


@pytest.mark.parametrize(
    ("driver_ids", "marginals"),
    [
        ([1, 2, 3], [1, 1, 1]),
        ([1, 2, 3, 4], [0.75, 0.75, 0.75]),
        ([1, 1, 2, 3], [0.75, 0.75, 0.75, 0.75]),
        ([1, 2, 3, 4], [0, 0.9, 0.9, 1.2]),
        ([1, 2, 3, 4], [0.7, 0.7, 0.7, 0.7]),
        ([1, 2, 3, 4], [float("nan"), 1, 1, 1]),
    ],
)
def test_distribution_refuses_invalid_marginal_contracts(driver_ids, marginals):
    with pytest.raises(PredictionUnavailable, match="Podium outcome distribution"):
        fit_fixed_size_distribution(driver_ids, marginals)


def test_service_returns_strict_ranked_outcomes_pairs_and_diagnostics():
    prediction = {
        "race_id": 99,
        "year": 2024,
        "experiment_id": "EXP-TEST",
        "model_version": "EXP-TEST+podium-count-v1",
        "predictions": [
            {"driver_id": 10, "constructor_id": 1, "probability": 0.9},
            {"driver_id": 20, "constructor_id": 1, "probability": 0.8},
            {"driver_id": 30, "constructor_id": 2, "probability": 0.7},
            {"driver_id": 40, "constructor_id": 2, "probability": 0.4},
            {"driver_id": 50, "constructor_id": 3, "probability": 0.2},
        ],
    }

    class StubPredictor:
        def predict(self, race_id):
            assert race_id == 99
            return prediction

    result = PodiumOutcomeService(StubPredictor()).derive(99, limit=3)
    payload = result.model_dump(mode="json")

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
    assert payload["schema_version"] == "f1-podium-outcomes-v1"
    assert payload["outcome_type"] == "derived_unordered_podium_set_distribution"
    assert payload["diagnostics"]["method"] == "maximum_entropy_fixed_size"
    assert payload["diagnostics"]["driver_count"] == 5
    assert payload["diagnostics"]["podium_size"] == 3
    assert payload["diagnostics"]["combination_count"] == 10
    assert payload["diagnostics"]["returned_outcome_count"] == 3
    assert payload["diagnostics"]["probability_sum"] == pytest.approx(1)
    assert payload["diagnostics"]["reconstructed_marginal_sum"] == pytest.approx(3)
    assert payload["diagnostics"]["maximum_marginal_error"] < 1e-8
    assert 1 <= payload["diagnostics"]["effective_outcome_count"] <= 10
    assert len(payload["outcomes"]) == 3
    assert [row["rank"] for row in payload["outcomes"]] == [1, 2, 3]
    assert all(row["driver_ids"] == sorted(row["driver_ids"]) for row in payload["outcomes"])
    assert [row["probability"] for row in payload["outcomes"]] == sorted(
        (row["probability"] for row in payload["outcomes"]), reverse=True
    )
    assert payload["outcomes"][-1]["cumulative_probability"] == pytest.approx(
        payload["diagnostics"]["returned_probability_sum"]
    )
    assert [row["forecast_rank"] for row in payload["driver_marginals"]] == [1, 2, 3, 4, 5]
    assert all(row["absolute_error"] < 1e-8 for row in payload["driver_marginals"])
    assert len(payload["co_podium_pairs"]) == 10
    assert [row["rank"] for row in payload["co_podium_pairs"]] == list(range(1, 11))
    assert payload["evidence_boundary"] == {
        "derived_from": "released race-level marginal podium probabilities",
        "outcome_data_used": False,
        "separately_trained_joint_model": False,
        "joint_forecast_validated": False,
        "causal": False,
        "ordering": "unordered_podium_set",
        "statement": (
            "This maximum-entropy distribution is derived from released marginals; it is not "
            "a separately trained or validated finishing-order forecast."
        ),
    }


def test_all_supported_races_converge_and_reconstruct_released_marginals():
    if not Path("models/podium_model.joblib").exists() or not Path("database/f1.db").exists():
        pytest.skip("Trusted model bundle and ingested archive required")
    predictor = Predictor(make_engine())
    service = PodiumOutcomeService(predictor)
    supported_races = sorted(
        predictor.frame().loc[lambda frame: frame.year.between(2022, 2024), "race_id"].unique()
    )

    assert len(supported_races) == 68
    for race_id in supported_races:
        result = service.derive(int(race_id), limit=3)
        assert result.diagnostics.probability_sum == pytest.approx(1, abs=1e-12)
        assert result.diagnostics.reconstructed_marginal_sum == pytest.approx(3, abs=1e-10)
        assert result.diagnostics.maximum_marginal_error < 1e-8
        assert result.diagnostics.combination_count == len(
            list(combinations(range(result.diagnostics.driver_count), 3))
        )
        assert len(result.outcomes) == 3


def test_solver_failure_is_reported_without_internal_details(monkeypatch):
    class FailedResult:
        success = False
        x = np.zeros(3)

    monkeypatch.setattr("backend.ml.outcomes.least_squares", lambda *args, **kwargs: FailedResult())

    with pytest.raises(
        PredictionUnavailable,
        match="Podium outcome distribution could not be derived",
    ) as error:
        fit_fixed_size_distribution([1, 2, 3, 4], [0.75] * 4)

    assert "scipy" not in str(error.value).lower()
