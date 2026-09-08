"""Report the frozen selection on reserved test years. Never tunes or fits here."""

import hashlib
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import shap
from scipy.special import expit

from backend.database import ROOT
from backend.ml.evaluation import metrics
from backend.ml.features import split_masks


def main():
    artifact = joblib.load(ROOT / "models/podium_model.joblib")
    if "selection_frozen_at" not in artifact:
        raise ValueError("Freeze selection before final evaluation")
    frame = pd.read_csv(ROOT / "data/processed/features.csv")
    test = frame.loc[split_masks(frame)["test"]]
    model = artifact["model"]
    x = test[artifact["features"]]
    calibration = artifact["calibration"]
    probabilities = expit(
        calibration["slope"] * model.decision_function(x) + calibration["intercept"]
    )
    baseline = joblib.load(ROOT / "models/grid_baseline.joblib").predict_proba(
        test[["grid_position"]]
    )[:, 1]
    report = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "selection_frozen_at": artifact["selection_frozen_at"],
        "test_years": [2022, 2024],
        "selected_model": metrics(test, probabilities),
        "baseline": metrics(test, baseline),
        "per_season": {},
    }
    for year in sorted(test.year.unique()):
        mask = test.year == year
        report["per_season"][str(year)] = {
            "selected_model": metrics(test.loc[mask], probabilities[mask]),
            "baseline": metrics(test.loc[mask], baseline[mask]),
        }
    report["artifact_sha256"] = hashlib.sha256(
        (ROOT / "models/podium_model.joblib").read_bytes()
    ).hexdigest()
    (ROOT / "reports/final_test_metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    explanations = shap.TreeExplainer(model)
    values = explanations.shap_values(x) * calibration["slope"]
    base = (
        float(np.asarray(explanations.expected_value).reshape(-1)[0]) * calibration["slope"]
        + calibration["intercept"]
    )
    np.testing.assert_allclose(expit(base + values.sum(axis=1)), probabilities, atol=1e-7)
    pd.DataFrame(
        {
            "feature": artifact["features"],
            "mean_absolute_calibrated_log_odds_shap": np.abs(values).mean(axis=0),
        }
    ).sort_values("mean_absolute_calibrated_log_odds_shap", ascending=False).to_csv(
        ROOT / "reports/feature_importance.csv", index=False
    )
    (ROOT / "reports/calibration_metrics.json").write_text(
        json.dumps(
            {
                "test": report["selected_model"]["calibration_bins"],
                "ece": report["selected_model"]["ece_10_bins"],
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                name: {k: v for k, v in report[name].items() if k != "calibration_bins"}
                for name in ["selected_model", "baseline"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
