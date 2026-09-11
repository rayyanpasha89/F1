"""Inference from a frozen model, with SHAP contributions in calibrated log-odds."""

from functools import lru_cache

import joblib
import numpy as np
import shap
from scipy.special import expit

from backend.database import ROOT
from backend.ml.evidence import ModelBundleError, ModelManifest, verify_model_bundle
from backend.ml.features import build_features, source_frame
from backend.ml.probability import project_expected_count


class PredictionUnavailable(Exception):
    pass


def _validate_loaded_artifacts(artifact, baseline, manifest: ModelManifest) -> None:
    try:
        calibration = artifact["calibration"]
        valid = (
            artifact["experiment_id"] == manifest.experiment_id
            and list(artifact["features"]) == list(manifest.features)
            and list(artifact["training_years"]) == list(manifest.temporal_split.training_years)
            and list(artifact["selection_years"]) == list(manifest.temporal_split.selection_years)
            and list(artifact["inference_years"]) == list(manifest.temporal_split.inference_years)
            and artifact["selection_frozen_at"] == manifest.selection_frozen_at.isoformat()
            and calibration["method"] == manifest.calibration.method
            and float(calibration["slope"]) == manifest.calibration.slope
            and float(calibration["intercept"]) == manifest.calibration.intercept
            and np.isfinite([calibration["slope"], calibration["intercept"]]).all()
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise PredictionUnavailable("Model artifact metadata is invalid.")
    if not callable(getattr(artifact.get("model"), "decision_function", None)) or not callable(
        getattr(baseline, "predict_proba", None)
    ):
        raise PredictionUnavailable("Model artifact interface is invalid.")


def load_verified_artifacts(root=ROOT):
    """Verify every byte and contract before deserializing trusted local artifacts."""

    try:
        manifest = verify_model_bundle(root)
    except ModelBundleError as error:
        raise PredictionUnavailable("Model verification failed.") from error
    try:
        artifact = joblib.load(root / "models/podium_model.joblib")
        baseline = joblib.load(root / "models/grid_baseline.joblib")
    except Exception as error:
        raise PredictionUnavailable("Model artifact could not be loaded.") from error
    _validate_loaded_artifacts(artifact, baseline, manifest)
    return artifact, baseline, manifest


@lru_cache(maxsize=1)
def load_artifacts():
    artifact, baseline, _ = load_verified_artifacts(ROOT)
    try:
        explainer = shap.TreeExplainer(artifact["model"])
    except Exception as error:
        raise PredictionUnavailable("Model explanation artifact is invalid.") from error
    return artifact, baseline, explainer


class Predictor:
    def __init__(self, engine):
        self.engine = engine

    @lru_cache(maxsize=1)
    def frame(self):
        return build_features(source_frame(self.engine))

    def _race_frame(self, race_id, artifact):
        data = self.frame()
        race = data.loc[data.race_id == race_id].copy()
        if race.empty:
            raise PredictionUnavailable("No supported prediction inputs for this race.")
        if not race.year.between(*artifact["inference_years"]).all():
            raise PredictionUnavailable(
                "The frozen model supports historical 2022–2024 races only; earlier races overlap training or model selection."
            )
        return race

    @staticmethod
    def _predict_race(race_id, race, artifact, baseline, explainer):
        cols = artifact["features"]
        x = race[cols]
        slope, intercept = artifact["calibration"]["slope"], artifact["calibration"]["intercept"]
        raw_p = expit(slope * artifact["model"].decision_function(x) + intercept)
        selected_projection = project_expected_count(raw_p)
        p = selected_projection.adjusted
        values = np.asarray(explainer.shap_values(x)) * slope
        raw_base = float(np.asarray(explainer.expected_value).reshape(-1)[0]) * slope + intercept
        base = raw_base + selected_projection.log_odds_offset
        if not np.allclose(expit(base + values.sum(axis=1)), p, atol=1e-7):
            raise RuntimeError("SHAP additive reconstruction failed")
        raw_bp = baseline.predict_proba(race[["grid_position"]])[:, 1]
        baseline_projection = project_expected_count(raw_bp)
        bp = baseline_projection.adjusted
        predictions = []
        for i, (_, row) in enumerate(race.iterrows()):
            factors = [
                {
                    "feature": col,
                    "value": float(row[col]),
                    "log_odds_contribution": float(values[i, j]),
                }
                for j, col in enumerate(cols)
            ]
            predictions.append(
                {
                    "driver_id": int(row.driver_id),
                    "constructor_id": int(row.constructor_id),
                    "probability": float(p[i]),
                    "raw_probability": float(raw_p[i]),
                    "baseline_probability": float(bp[i]),
                    "raw_baseline_probability": float(raw_bp[i]),
                    "base_log_odds": base,
                    "raw_base_log_odds": raw_base,
                    "factors": sorted(
                        factors, key=lambda f: abs(f["log_odds_contribution"]), reverse=True
                    ),
                }
            )
        return {
            "race_id": race_id,
            "year": int(race.iloc[0].year),
            "experiment_id": artifact["experiment_id"],
            "model_version": f"{artifact['experiment_id']}+podium-count-v1",
            "postprocessing": {
                "method": "race_logit_offset",
                "expected_podiums": 3,
                "selected": {
                    "raw_sum": selected_projection.raw_sum,
                    "adjusted_sum": selected_projection.adjusted_sum,
                    "log_odds_offset": selected_projection.log_odds_offset,
                },
                "baseline": {
                    "raw_sum": baseline_projection.raw_sum,
                    "adjusted_sum": baseline_projection.adjusted_sum,
                    "log_odds_offset": baseline_projection.log_odds_offset,
                },
            },
            "predictions": sorted(predictions, key=lambda p: (-p["probability"], p["driver_id"])),
            "cutoff": "After starting grid, before race; retrospective snapshot",
            "notes": [
                "Race-level logit projection makes the marginal podium probabilities sum to the three available positions while preserving rank.",
                "SHAP contributions explain the fitted model, not causal effects. Units are calibrated log-odds.",
                "Model fit 2010–2018; model selection 2019–2021. No 2022–2024 outcomes fit parameters.",
                "Earlier completed races may inform the next race in this sequential backtest.",
            ],
        }

    def predict(self, race_id):
        artifact, baseline, explainer = load_artifacts()
        race = self._race_frame(race_id, artifact)
        return self._predict_race(race_id, race, artifact, baseline, explainer)

    def predict_grid_swap(self, race_id, driver_a_id, driver_b_id):
        """Compare the released forecast with two copied grid inputs exchanged."""

        if driver_a_id == driver_b_id:
            raise PredictionUnavailable("Choose two different drivers.")
        artifact, baseline, explainer = load_artifacts()
        original_frame = self._race_frame(race_id, artifact)
        driver_ids = set(original_frame.driver_id.astype(int))
        if driver_a_id not in driver_ids or driver_b_id not in driver_ids:
            raise PredictionUnavailable("Both drivers must be starters in this race.")

        scenario_frame = original_frame.copy()
        a_mask = scenario_frame.driver_id == driver_a_id
        b_mask = scenario_frame.driver_id == driver_b_id
        a_grid = float(scenario_frame.loc[a_mask, "grid_position"].iloc[0])
        b_grid = float(scenario_frame.loc[b_mask, "grid_position"].iloc[0])
        if a_grid == b_grid:
            raise PredictionUnavailable("Choose drivers with different model grid inputs.")
        scenario_frame.loc[a_mask, "grid_position"] = b_grid
        scenario_frame.loc[b_mask, "grid_position"] = a_grid

        return {
            "original": self._predict_race(race_id, original_frame, artifact, baseline, explainer),
            "scenario": self._predict_race(race_id, scenario_frame, artifact, baseline, explainer),
            "recorded_grid": {
                int(row.driver_id): int(row.grid) for row in original_frame.itertuples()
            },
        }
