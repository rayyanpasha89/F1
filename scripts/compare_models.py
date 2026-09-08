"""Validation-only experiments. Freeze selection before opening final test."""

import json
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.database import ROOT, make_engine
from backend.ml.features import build_features, source_frame, split_masks, FEATURE_SETS
from backend.ml.evaluation import metrics


def main():
    frame = build_features(source_frame(make_engine()))
    frame.to_csv(ROOT / "data/processed/features.csv", index=False)
    records = []
    candidates = {}
    # Feature ablations isolate the input change with a fixed model family/window.
    specs = [
        ("EXP-002", "driver", "logistic", 2010),
        ("EXP-003", "team", "logistic", 2010),
        ("EXP-004", "full", "logistic", 2010),
        ("EXP-005", "career", "logistic", 2010),
        ("EXP-006", "full", "forest", 2010),
        ("EXP-007", "full", "boosting", 2010),
        ("EXP-008", "full", "logistic", 2014),
        ("EXP-009", "full", "boosting", 2014),
    ]
    for exp, features, kind, start in specs:
        model = {
            "logistic": lambda: make_pipeline(
                StandardScaler(), LogisticRegression(random_state=42, max_iter=2000)
            ),
            "forest": lambda: RandomForestClassifier(
                n_estimators=300, min_samples_leaf=15, max_depth=7, random_state=42, n_jobs=1
            ),
            "boosting": lambda: GradientBoostingClassifier(
                n_estimators=150,
                learning_rate=0.035,
                max_depth=2,
                min_samples_leaf=20,
                random_state=42,
            ),
        }[kind]()
        masks = split_masks(frame, start)
        train, valid = frame.loc[masks["train"]], frame.loc[masks["validation"]]
        cols = FEATURE_SETS[features]
        model.fit(train[cols], train.podium)
        score = metrics(valid, model.predict_proba(valid[cols])[:, 1])
        record = {
            "experiment_id": exp,
            "model": kind,
            "feature_set": features,
            "features": cols,
            "training_years": [start, 2018],
            "validation_years": [2019, 2021],
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "validation": score,
        }
        records.append(record)
        candidates[exp] = model
        print(
            exp,
            kind,
            features,
            round(score["log_loss"], 6),
            round(score["brier_score"], 6),
            flush=True,
        )
    # Include baseline as a genuine candidate; no requirement that a complex model must win.
    baseline = json.loads((ROOT / "reports/baseline_metrics.json").read_text())
    baseline.update({"feature_set": "grid"})
    records.insert(0, baseline)
    candidates["EXP-001"] = joblib.load(ROOT / "models/grid_baseline.joblib")
    winner = min(
        records, key=lambda r: (r["validation"]["log_loss"], r["validation"]["brier_score"])
    )
    artifact = {
        "model": candidates[winner["experiment_id"]],
        "features": winner["features"],
        "experiment_id": winner["experiment_id"],
        "training_years": winner["training_years"],
        "selection_years": [2019, 2021],
        "inference_years": [2022, 2024],
    }
    joblib.dump(artifact, ROOT / "models/podium_model.joblib")
    selection = {k: v for k, v in artifact.items() if k != "model"}
    selection.update(
        {
            "selection_rule": "Lowest validation log loss, Brier tie-breaker; test not evaluated",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    (ROOT / "reports/model_selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    (ROOT / "reports/validation_experiments.json").write_text(json.dumps(records, indent=2) + "\n")
    pd.DataFrame(
        [
            {
                "experiment_id": r["experiment_id"],
                "model": r["model"],
                "feature_set": r["feature_set"],
                "train_start": r["training_years"][0],
                **{k: v for k, v in r["validation"].items() if k != "calibration_bins"},
            }
            for r in records
        ]
    ).to_csv(ROOT / "reports/model_comparison.csv", index=False)
    print("Selected", winner["experiment_id"])


if __name__ == "__main__":
    main()
