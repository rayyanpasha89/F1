"""Fit sigmoid calibration on temporal out-of-fold TRAINING margins only."""

import json
from datetime import datetime, timezone

import joblib
import pandas as pd
import numpy as np
from scipy.special import expit
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.database import ROOT
from backend.ml.features import split_masks, FEATURE_SETS
from backend.ml.evaluation import metrics


def main():
    frame = pd.read_csv(ROOT / "data/processed/features.csv")
    artifact = joblib.load(ROOT / "models/podium_model.joblib")
    if artifact["experiment_id"] != "EXP-007":
        raise ValueError("Calibration protocol is specified for the selected boosting model")
    model, cols = artifact["model"], artifact["features"]
    valid = frame.loc[split_masks(frame)["validation"]]
    margins, labels = [], []
    for fit_end, eval_start, eval_end in [(2014, 2015, 2016), (2016, 2017, 2018)]:
        fit = frame.loc[frame.year.between(2010, fit_end)]
        held = frame.loc[frame.year.between(eval_start, eval_end)]
        fold = clone(model).fit(fit[cols], fit.podium)
        margins.extend(fold.decision_function(held[cols]))
        labels.extend(held.podium)
    sigmoid = LogisticRegression(C=1e6, random_state=42).fit(
        np.array(margins).reshape(-1, 1), labels
    )
    slope, intercept = float(sigmoid.coef_[0, 0]), float(sigmoid.intercept_[0])
    raw = metrics(valid, model.predict_proba(valid[cols])[:, 1])
    calibrated = metrics(valid, expit(slope * model.decision_function(valid[cols]) + intercept))
    use = calibrated["log_loss"] < raw["log_loss"]
    artifact["calibration"] = {
        "slope": slope if use else 1.0,
        "intercept": intercept if use else 0.0,
        "method": "temporal training OOF sigmoid"
        if use
        else "uncalibrated; sigmoid did not improve validation log loss",
    }
    artifact["selection_frozen_at"] = datetime.now(timezone.utc).isoformat()
    joblib.dump(artifact, ROOT / "models/podium_model.joblib")
    report = {
        "executed_at": artifact["selection_frozen_at"],
        "training_oof_years": [[2015, 2016], [2017, 2018]],
        "validation_years": [2019, 2021],
        "slope": slope,
        "intercept": intercept,
        "raw": raw,
        "sigmoid": calibrated,
        "selected_sigmoid": use,
        "test_status": "not evaluated",
    }
    (ROOT / "reports/calibration_selection.json").write_text(json.dumps(report, indent=2) + "\n")
    selection = {k: v for k, v in artifact.items() if k != "model"}
    (ROOT / "reports/model_selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    # Clean logistic ablations for individual hypothesis evidence.
    ablations = []
    sets = {
        "H3_recent": ["grid_position", "driver_recent_podium"],
        "H3_career": ["grid_position", "driver_career_podium"],
        "H4_without_circuit": FEATURE_SETS["team"],
        "H4_with_circuit": FEATURE_SETS["team"] + ["driver_circuit_podium"],
    }
    train = frame.loc[split_masks(frame)["train"]]
    for name, features in sets.items():
        fitted = make_pipeline(
            StandardScaler(), LogisticRegression(random_state=42, max_iter=2000)
        ).fit(train[features], train.podium)
        ablations.append(
            {
                "experiment_id": name,
                "features": features,
                "validation": metrics(valid, fitted.predict_proba(valid[features])[:, 1]),
            }
        )
    (ROOT / "reports/hypothesis_ablations.json").write_text(json.dumps(ablations, indent=2) + "\n")
    print(
        json.dumps(
            {
                "raw_log_loss": raw["log_loss"],
                "sigmoid_log_loss": calibrated["log_loss"],
                "selected_sigmoid": use,
                "ablations": {a["experiment_id"]: a["validation"]["log_loss"] for a in ablations},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
