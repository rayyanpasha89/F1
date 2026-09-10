"""Inference from a frozen model, with SHAP contributions in calibrated log-odds."""

from functools import lru_cache

import joblib
import numpy as np
import shap
from scipy.special import expit

from backend.database import ROOT
from backend.ml.features import build_features, source_frame
from backend.ml.probability import project_expected_count


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
