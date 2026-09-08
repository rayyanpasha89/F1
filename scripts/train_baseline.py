"""First measured experiment. Final test remains unopened until model selection."""

import json
from datetime import datetime, timezone

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.database import ROOT, make_engine
from backend.ml.features import baseline_frame, source_frame, split_masks
from backend.ml.evaluation import metrics


def fit_baseline(frame):
    masks = split_masks(frame)
    train = frame.loc[masks["train"]]
    if train.duplicated(["race_id", "driver_id"]).any():
        raise ValueError("Training driver/race grain is not unique")
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=42, max_iter=2000))
    model.fit(train[["grid_position"]], train.podium)
    return model


def main():
    frame = baseline_frame(source_frame(make_engine()))
    model = fit_baseline(frame)
    valid = frame.loc[split_masks(frame)["validation"]]
    report = {
        "experiment_id": "EXP-001",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "model": "StandardScaler + LogisticRegression",
        "features": ["grid_position"],
        "training_years": [2010, 2018],
        "validation_years": [2019, 2021],
        "reserved_test_years": [2022, 2024],
        "test_status": "not evaluated at this milestone",
        "validation": metrics(valid, model.predict_proba(valid[["grid_position"]])[:, 1]),
        "standardized_grid_coefficient": float(model[-1].coef_[0, 0]),
    }
    (ROOT / "reports/baseline_metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    joblib.dump(model, ROOT / "models/grid_baseline.joblib")
    print(
        json.dumps(
            {k: v for k, v in report["validation"].items() if k != "calibration_bins"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
