"""Evaluate the outcome-free podium-count projection on documented time splits."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit

from backend.database import ROOT
from backend.ml.evaluation import metrics
from backend.ml.features import split_masks
from backend.ml.probability import project_expected_count


REPORT_SCHEMA = "f1-probability-coherence-v1"
METRIC_FIELDS = (
    "rows",
    "races",
    "positive_rate",
    "roc_auc",
    "log_loss",
    "brier_score",
    "top3_hit_rate",
    "exact_podium_set_rate",
    "ece_10_bins",
)


def _compact_metrics(frame: pd.DataFrame, probabilities: np.ndarray) -> dict:
    result = metrics(frame, probabilities)
    return {field: result[field] for field in METRIC_FIELDS}


def _rank_order(frame: pd.DataFrame, probabilities: np.ndarray, positions: np.ndarray) -> list[int]:
    drivers = frame.iloc[positions].driver_id.to_numpy()
    local = probabilities[positions]
    return positions[np.lexsort((drivers, -local))].tolist()


def _project_races(frame: pd.DataFrame, probabilities: np.ndarray) -> tuple[np.ndarray, dict]:
    probabilities = np.asarray(probabilities, dtype=float)
    if len(frame) != len(probabilities):
        raise ValueError("Prediction count does not match evaluation rows.")
    adjusted = np.empty_like(probabilities)
    raw_sums = []
    adjusted_sums = []
    rank_preserved = True
    for positions in frame.groupby("race_id", sort=True).indices.values():
        positions = np.asarray(positions, dtype=int)
        projection = project_expected_count(probabilities[positions], expected_count=3)
        adjusted[positions] = projection.adjusted
        raw_sums.append(projection.raw_sum)
        adjusted_sums.append(projection.adjusted_sum)
        rank_preserved &= _rank_order(frame, probabilities, positions) == _rank_order(
            frame, adjusted, positions
        )
    return adjusted, {
        "average_raw_sum": float(np.mean(raw_sums)),
        "average_projected_sum": float(np.mean(adjusted_sums)),
        "maximum_absolute_sum_error": float(np.max(np.abs(np.asarray(adjusted_sums) - 3))),
        "rank_preserved": bool(rank_preserved),
    }


def _model_probabilities(frame: pd.DataFrame, artifact: dict) -> np.ndarray:
    required = {"model", "features", "calibration"}
    if not required.issubset(artifact):
        raise ValueError("Selected artifact is missing evaluation metadata.")
    calibration = artifact["calibration"]
    return np.asarray(
        expit(
            float(calibration["slope"])
            * artifact["model"].decision_function(frame[artifact["features"]])
            + float(calibration["intercept"])
        ),
        dtype=float,
    )


def _comparison(frame: pd.DataFrame, raw: np.ndarray, projected: np.ndarray) -> dict:
    raw_metrics = _compact_metrics(frame, raw)
    projected_metrics = _compact_metrics(frame, projected)
    return {
        "raw": raw_metrics,
        "projected": projected_metrics,
        "projected_minus_raw": {
            "log_loss": projected_metrics["log_loss"] - raw_metrics["log_loss"],
            "brier_score": projected_metrics["brier_score"] - raw_metrics["brier_score"],
            "top3_hit_rate": projected_metrics["top3_hit_rate"] - raw_metrics["top3_hit_rate"],
        },
    }


def _race_statistics(
    frame: pd.DataFrame, selected: np.ndarray, baseline: np.ndarray
) -> list[dict[str, float]]:
    labels = frame.podium.to_numpy(dtype=float)
    selected = np.clip(selected, np.finfo(float).eps, 1 - np.finfo(float).eps)
    baseline = np.clip(baseline, np.finfo(float).eps, 1 - np.finfo(float).eps)
    rows = []
    for positions in frame.groupby("race_id", sort=True).indices.values():
        positions = np.asarray(positions, dtype=int)
        y = labels[positions]
        selected_local = selected[positions]
        baseline_local = baseline[positions]
        selected_top = np.lexsort((frame.iloc[positions].driver_id.to_numpy(), -selected_local))[:3]
        baseline_top = np.lexsort((frame.iloc[positions].driver_id.to_numpy(), -baseline_local))[:3]
        rows.append(
            {
                "count": float(len(positions)),
                "selected_log_loss_sum": float(
                    -(y * np.log(selected_local) + (1 - y) * np.log(1 - selected_local)).sum()
                ),
                "baseline_log_loss_sum": float(
                    -(y * np.log(baseline_local) + (1 - y) * np.log(1 - baseline_local)).sum()
                ),
                "selected_brier_sum": float(np.square(selected_local - y).sum()),
                "baseline_brier_sum": float(np.square(baseline_local - y).sum()),
                "selected_hits": float(y[selected_top].sum()),
                "baseline_hits": float(y[baseline_top].sum()),
            }
        )
    return rows


def _paired_race_bootstrap(
    frame: pd.DataFrame,
    selected: np.ndarray,
    baseline: np.ndarray,
    replicates: int,
    seed: int,
) -> dict:
    if type(replicates) is not int or replicates < 1:
        raise ValueError("Bootstrap replicates must be a positive integer.")
    statistics = _race_statistics(frame, selected, baseline)
    if len(statistics) < 2:
        raise ValueError("At least two races are required for a race bootstrap.")
    matrix = {key: np.asarray([row[key] for row in statistics]) for key in statistics[0]}
    rng = np.random.default_rng(seed)
    samples = {"log_loss": [], "brier_score": [], "top3_hit_rate": []}
    for _ in range(replicates):
        drawn = rng.integers(0, len(statistics), size=len(statistics))
        row_count = matrix["count"][drawn].sum()
        samples["log_loss"].append(
            float(
                (
                    matrix["selected_log_loss_sum"][drawn].sum()
                    - matrix["baseline_log_loss_sum"][drawn].sum()
                )
                / row_count
            )
        )
        samples["brier_score"].append(
            float(
                (
                    matrix["selected_brier_sum"][drawn].sum()
                    - matrix["baseline_brier_sum"][drawn].sum()
                )
                / row_count
            )
        )
        samples["top3_hit_rate"].append(
            float(
                (matrix["selected_hits"][drawn].sum() - matrix["baseline_hits"][drawn].sum())
                / (3 * len(statistics))
            )
        )
    total_rows = matrix["count"].sum()
    estimates = {
        "log_loss": float(
            (matrix["selected_log_loss_sum"].sum() - matrix["baseline_log_loss_sum"].sum())
            / total_rows
        ),
        "brier_score": float(
            (matrix["selected_brier_sum"].sum() - matrix["baseline_brier_sum"].sum()) / total_rows
        ),
        "top3_hit_rate": float(
            (matrix["selected_hits"].sum() - matrix["baseline_hits"].sum()) / (3 * len(statistics))
        ),
    }
    intervals = {}
    for name, values in samples.items():
        lower, upper = np.quantile(np.asarray(values), [0.025, 0.975])
        intervals[name] = {
            "estimate": estimates[name],
            "lower_95": float(lower),
            "upper_95": float(upper),
        }
    return {
        "split": "consumed_test",
        "unit": "whole_race",
        "replicates": replicates,
        "seed": seed,
        "comparison": "projected_selected_minus_projected_baseline",
        "metrics": intervals,
        "limitation": "Intervals quantify sampled-race variation only; they do not remove model-selection bias or create an unseen holdout.",
    }


def _evaluate_split(
    frame: pd.DataFrame,
    artifact: dict,
    baseline,
    evidence_status: str,
) -> tuple[dict, np.ndarray, np.ndarray]:
    subset = frame.reset_index(drop=True)
    if subset.empty or not (subset.groupby("race_id").podium.sum() == 3).all():
        raise ValueError("Every evaluated race must contain exactly three recorded podium labels.")
    selected_raw = _model_probabilities(subset, artifact)
    baseline_raw = np.asarray(baseline.predict_proba(subset[["grid_position"]])[:, 1], dtype=float)
    selected_projected, selected_constraint = _project_races(subset, selected_raw)
    baseline_projected, baseline_constraint = _project_races(subset, baseline_raw)
    maximum_error = max(
        selected_constraint["maximum_absolute_sum_error"],
        baseline_constraint["maximum_absolute_sum_error"],
    )
    report = {
        "years": [int(subset.year.min()), int(subset.year.max())],
        "evidence_status": evidence_status,
        "rows": int(len(subset)),
        "races": int(subset.race_id.nunique()),
        "selected_model": _comparison(subset, selected_raw, selected_projected),
        "baseline": _comparison(subset, baseline_raw, baseline_projected),
        "race_constraint": {
            "expected_podiums": 3,
            "selected_average_raw_sum": selected_constraint["average_raw_sum"],
            "selected_average_projected_sum": selected_constraint["average_projected_sum"],
            "baseline_average_raw_sum": baseline_constraint["average_raw_sum"],
            "baseline_average_projected_sum": baseline_constraint["average_projected_sum"],
            "maximum_absolute_sum_error": maximum_error,
            "selected_rank_preserved": selected_constraint["rank_preserved"],
            "baseline_rank_preserved": baseline_constraint["rank_preserved"],
        },
    }
    return report, selected_projected, baseline_projected


def evaluate_projection(
    frame: pd.DataFrame,
    artifact: dict,
    baseline,
    bootstrap_replicates: int = 5000,
    seed: int = 42,
) -> dict:
    """Return deterministic structural and post-test evidence for the race projection."""

    masks = split_masks(frame)
    validation_frame = frame.loc[masks["validation"]].copy()
    test_frame = frame.loc[masks["test"]].copy()
    validation, _, _ = _evaluate_split(
        validation_frame, artifact, baseline, "reused_model_selection_period"
    )
    consumed_test, selected_test, baseline_test = _evaluate_split(
        test_frame, artifact, baseline, "consumed_post_test_iterative"
    )
    per_season = {}
    for year in sorted(set(validation_frame.year) | set(test_frame.year)):
        season = frame.loc[frame.year == year].copy()
        status = "reused_model_selection_period" if year <= 2021 else "consumed_post_test_iterative"
        season_report, _, _ = _evaluate_split(season, artifact, baseline, status)
        per_season[str(int(year))] = {
            "evidence_status": status,
            "rows": season_report["rows"],
            "races": season_report["races"],
            "selected_model": season_report["selected_model"],
            "baseline": season_report["baseline"],
        }
    report = {
        "schema_version": REPORT_SCHEMA,
        "model_version": f"{artifact['experiment_id']}+podium-count-v1",
        "postprocessor": {
            "name": "race_logit_offset",
            "version": "v1",
            "expected_count": 3,
            "uses_outcomes": False,
        },
        "evidence_boundary": {
            "status": "post_test_iterative_evidence",
            "unseen_holdout": False,
            "statement": "The 2022-2024 outcomes were already consumed before this structural postprocessor was assessed; results are not fresh holdout evidence.",
        },
        "splits": {"validation": validation, "consumed_test": consumed_test},
        "per_season": per_season,
        "paired_race_bootstrap": _paired_race_bootstrap(
            test_frame.reset_index(drop=True),
            selected_test,
            baseline_test,
            bootstrap_replicates,
            seed,
        ),
    }
    report["ship_gates"] = {
        "validation_log_loss_improved": validation["selected_model"]["projected"]["log_loss"]
        < validation["selected_model"]["raw"]["log_loss"],
        "validation_brier_improved": validation["selected_model"]["projected"]["brier_score"]
        < validation["selected_model"]["raw"]["brier_score"],
        "all_race_sums_exact": all(
            split["race_constraint"]["maximum_absolute_sum_error"] < 1e-10
            for split in report["splits"].values()
        ),
        "all_rankings_preserved": all(
            split["race_constraint"]["selected_rank_preserved"]
            and split["race_constraint"]["baseline_rank_preserved"]
            for split in report["splits"].values()
        ),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "reports/race_constraint_evaluation.json"
    )
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    artifact = joblib.load(ROOT / "models/podium_model.joblib")
    baseline = joblib.load(ROOT / "models/grid_baseline.joblib")
    frame = pd.read_csv(ROOT / "data/processed/features.csv")
    report = evaluate_projection(frame, artifact, baseline, args.bootstrap_replicates, args.seed)
    report["generated_at"] = args.generated_at or datetime.now(timezone.utc).isoformat()
    if not all(report["ship_gates"].values()):
        raise SystemExit("Probability-coherence ship gates failed.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output.relative_to(ROOT)), **report["ship_gates"]}))


if __name__ == "__main__":
    main()
