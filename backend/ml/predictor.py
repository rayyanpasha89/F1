"""Inference from a frozen model, with SHAP contributions in calibrated log-odds."""

from functools import lru_cache

import joblib
import numpy as np
import shap
from scipy.special import expit

from backend.database import ROOT
from backend.ml.features import build_features, source_frame


class PredictionUnavailable(Exception):
    pass


@lru_cache(maxsize=1)
def load_artifacts():
    path = ROOT / "models/podium_model.joblib"
    if not path.exists():
        raise PredictionUnavailable("Model unavailable. Run the documented training pipeline.")
    # Only locally produced/trusted artifacts: joblib must never deserialize user uploads.
    artifact = joblib.load(path)
    baseline = joblib.load(ROOT / "models/grid_baseline.joblib")
    return artifact, baseline, shap.TreeExplainer(artifact["model"])


class Predictor:
    def __init__(self, engine):
        self.engine = engine

    @lru_cache(maxsize=1)
    def frame(self):
        return build_features(source_frame(self.engine))

    def predict(self, race_id):
        artifact, baseline, explainer = load_artifacts()
        data = self.frame()
        race = data.loc[data.race_id == race_id]
        if race.empty:
            raise PredictionUnavailable("No supported prediction inputs for this race.")
        if not race.year.between(*artifact["inference_years"]).all():
            raise PredictionUnavailable(
                "The frozen model supports historical 2022–2024 races only; earlier races overlap training or model selection."
            )
        cols = artifact["features"]
        x = race[cols]
        slope, intercept = artifact["calibration"]["slope"], artifact["calibration"]["intercept"]
        p = expit(slope * artifact["model"].decision_function(x) + intercept)
        values = np.asarray(explainer.shap_values(x)) * slope
        base = float(np.asarray(explainer.expected_value).reshape(-1)[0]) * slope + intercept
        if not np.allclose(expit(base + values.sum(axis=1)), p, atol=1e-7):
            raise RuntimeError("SHAP additive reconstruction failed")
        bp = baseline.predict_proba(race[["grid_position"]])[:, 1]
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
                    "baseline_probability": float(bp[i]),
                    "base_log_odds": base,
                    "factors": sorted(
                        factors, key=lambda f: abs(f["log_odds_contribution"]), reverse=True
                    ),
                }
            )
        return {
            "race_id": race_id,
            "year": int(race.iloc[0].year),
            "experiment_id": artifact["experiment_id"],
            "predictions": sorted(predictions, key=lambda p: (-p["probability"], p["driver_id"])),
            "cutoff": "After starting grid, before race; retrospective snapshot",
            "notes": [
                "Independent podium probabilities need not sum to three.",
                "SHAP contributions explain the fitted model, not causal effects. Units are calibrated log-odds.",
                "Model fit 2010–2018; model selection 2019–2021. No 2022–2024 outcomes fit parameters.",
                "Earlier completed races may inform the next race in this sequential backtest.",
            ],
        }
