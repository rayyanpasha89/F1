import numpy as np
import pandas as pd
from backend.ml.features import baseline_frame, split_masks
from backend.ml.evaluation import metrics
from scripts.train_baseline import fit_baseline


def fixture_frame():
    rows = []
    for year in range(2010, 2025):
        for driver in range(1, 7):
            rows.append(
                dict(
                    result_id=len(rows),
                    race_id=year,
                    driver_id=driver,
                    constructor_id=(driver + 1) // 2,
                    year=year,
                    round=1,
                    date=f"{year}-03-01",
                    circuit_id=1,
                    grid=driver,
                    position=driver,
                    position_order=driver,
                    points=7 - driver,
                    status_name="Finished",
                )
            )
    return pd.DataFrame(rows)


def test_baseline_never_reads_outcomes_as_features():
    source = fixture_frame()
    original = baseline_frame(source)
    changed = source.assign(position=1, points=100, position_order=1, status_name="Engine")
    assert original.grid_position.equals(baseline_frame(changed).grid_position)
    source.loc[0, "grid"] = 0
    assert baseline_frame(source).iloc[0].grid_position == 25


def test_temporal_separation_and_reproducible_baseline():
    frame = baseline_frame(fixture_frame())
    masks = split_masks(frame)
    assert frame.loc[masks["train"], "date"].max() < frame.loc[masks["validation"], "date"].min()
    assert frame.loc[masks["validation"], "date"].max() < frame.loc[masks["test"], "date"].min()
    a, b = fit_baseline(frame), fit_baseline(frame)
    p = a.predict_proba(frame[["grid_position"]])[:, 1]
    np.testing.assert_array_equal(p, b.predict_proba(frame[["grid_position"]])[:, 1])
    assert np.all((p >= 0) & (p <= 1))
    altered = frame.copy()
    altered.loc[~masks["train"], "podium"] = 0
    np.testing.assert_array_equal(a[-1].coef_, fit_baseline(altered)[-1].coef_)


def test_top_three_metric_definition():
    frame = baseline_frame(fixture_frame().query("year == 2024"))
    score = metrics(frame, [0.9, 0.8, 0.7, 0.3, 0.2, 0.1])
    assert score["top3_hit_rate"] == 1
    assert score["exact_podium_set_rate"] == 1
    assert sum(b["count"] for b in score["calibration_bins"]) == 6


def test_same_race_and_future_outcome_mutations_leave_past_features_unchanged():
    from backend.ml.features import build_features, FEATURE_SETS

    source = fixture_frame()
    a = build_features(source)
    source.loc[source.year >= 2022, ["position", "position_order", "points"]] = [20, 20, 0]
    source.loc[source.year >= 2022, "status_name"] = "Engine"
    b = build_features(source)
    cols = FEATURE_SETS["full"]
    pd.testing.assert_frame_equal(a.loc[a.year <= 2022, cols], b.loc[b.year <= 2022, cols])
    assert not a.loc[a.year == 2023, "driver_recent_podium"].equals(
        b.loc[b.year == 2023, "driver_recent_podium"]
    )


def test_teammate_and_same_day_outcomes_do_not_leak():
    from backend.ml.features import build_features, FEATURE_SETS

    source = fixture_frame()
    source.loc[source.year == 2021, "date"] = "2020-03-01"
    a = build_features(source)
    changed = source.copy()
    changed.loc[changed.year == 2020, "position"] = 20
    b = build_features(changed)
    pd.testing.assert_frame_equal(
        a.loc[a.date <= "2020-03-01", FEATURE_SETS["full"]],
        b.loc[b.date <= "2020-03-01", FEATURE_SETS["full"]],
    )


def test_features_ignore_input_order_and_handle_debutants():
    from backend.ml.features import build_features, FEATURE_SETS

    source = fixture_frame()
    a = build_features(source)
    b = build_features(source.sample(frac=1, random_state=2))
    pd.testing.assert_frame_equal(a, b)
    assert np.isfinite(a[FEATURE_SETS["full"]].to_numpy()).all()
    assert a.iloc[0].history_races == 0
    assert not set(FEATURE_SETS["full"]) & {
        "position",
        "points",
        "status_name",
        "position_order",
        "podium",
    }


def test_real_shap_explanations_reconstruct_model_probability():
    import pytest
    from pathlib import Path
    from scipy.special import expit
    from backend.database import make_engine
    from backend.ml.predictor import Predictor, PredictionUnavailable

    if not Path("models/podium_model.joblib").exists() or not Path("database/f1.db").exists():
        pytest.skip("Trained artifacts required")
    predictor = Predictor(make_engine())
    frame = predictor.frame()
    race_id = int(frame.loc[frame.year == 2024, "race_id"].iloc[-1])
    result = predictor.predict(race_id)
    assert len(result["predictions"]) == 20
    for row in result["predictions"]:
        assert 0 <= row["probability"] <= 1
        assert (
            abs(
                expit(
                    row["base_log_odds"] + sum(f["log_odds_contribution"] for f in row["factors"])
                )
                - row["probability"]
            )
            < 1e-7
        )
    with pytest.raises(PredictionUnavailable):
        predictor.predict(int(frame.loc[frame.year == 2018, "race_id"].iloc[0]))
