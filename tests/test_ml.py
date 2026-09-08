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
