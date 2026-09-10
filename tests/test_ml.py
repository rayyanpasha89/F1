import numpy as np
import pandas as pd
import joblib
import json
import hashlib
import pytest
from backend.ml.features import baseline_frame, split_masks
from backend.ml.evaluation import metrics
from backend.ml.evidence import ModelBundleError, verify_model_bundle
from backend.ml.predictor import PredictionUnavailable, load_verified_artifacts
from scripts.build_model_manifest import build_manifest
from scripts.train_baseline import fit_baseline


class BundleScoreModel:
    def decision_function(self, frame):
        return np.zeros(len(frame))


class BundleBaseline:
    def predict_proba(self, frame):
        probability = np.full(len(frame), 0.15)
        return np.column_stack([1 - probability, probability])


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def _model_bundle(tmp_path, selected_model=None, artifact_changes=None):
    (tmp_path / "models").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    selection = {
        "experiment_id": "EXP-007",
        "features": ["grid_position"],
        "training_years": [2010, 2018],
        "selection_years": [2019, 2021],
        "inference_years": [2022, 2024],
        "calibration": {"slope": 1.1, "intercept": 0.2, "method": "temporal sigmoid"},
        "selection_frozen_at": "2026-09-08T10:35:42+00:00",
    }
    artifact = {
        "model": selected_model or BundleScoreModel(),
        **selection,
    }
    if artifact_changes:
        artifact.update(artifact_changes)
    joblib.dump(artifact, tmp_path / "models/podium_model.joblib")
    joblib.dump(BundleBaseline(), tmp_path / "models/grid_baseline.joblib")
    model_hash = hashlib.sha256((tmp_path / "models/podium_model.joblib").read_bytes()).hexdigest()
    _write_json(tmp_path / "reports/model_selection.json", selection)
    _write_json(
        tmp_path / "reports/final_test_metrics.json",
        {
            "selection_frozen_at": selection["selection_frozen_at"],
            "test_years": selection["inference_years"],
            "artifact_sha256": model_hash,
        },
    )
    _write_json(
        tmp_path / "reports/data_audit.json",
        {
            "format_version": 1,
            "tables": {"races": {"rows": 1125, "year_range": [1950, 2024]}},
        },
    )
    _write_json(
        tmp_path / "reports/race_constraint_evaluation.json",
        {
            "schema_version": "f1-probability-coherence-v1",
            "model_version": "EXP-007+podium-count-v1",
            "evidence_boundary": {"unseen_holdout": False},
            "ship_gates": {
                "validation_log_loss_improved": True,
                "validation_brier_improved": True,
                "all_race_sums_exact": True,
                "all_rankings_preserved": True,
            },
        },
    )
    manifest = build_manifest(tmp_path, generated_at="2026-09-10T00:00:00+00:00")
    _write_json(tmp_path / "models/manifest.json", manifest)
    return tmp_path


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
    assert result["model_version"] == "EXP-007+podium-count-v1"
    assert result["postprocessing"]["method"] == "race_logit_offset"
    assert result["postprocessing"]["expected_podiums"] == 3
    assert sum(row["probability"] for row in result["predictions"]) == pytest.approx(3)
    assert sum(row["baseline_probability"] for row in result["predictions"]) == pytest.approx(3)
    assert result["postprocessing"]["selected"]["adjusted_sum"] == pytest.approx(3)
    assert result["postprocessing"]["baseline"]["adjusted_sum"] == pytest.approx(3)
    for row in result["predictions"]:
        assert 0 <= row["probability"] <= 1
        assert 0 <= row["raw_probability"] <= 1
        assert 0 <= row["raw_baseline_probability"] <= 1
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


def test_bundle_hashes_are_checked_before_deserialization(tmp_path, monkeypatch):
    root = _model_bundle(tmp_path)
    (root / "models/podium_model.joblib").write_bytes(b"tampered")
    loads = []

    def forbidden_load(path):
        loads.append(path)
        raise AssertionError("deserialization ran before hash verification")

    monkeypatch.setattr("backend.ml.predictor.joblib.load", forbidden_load)

    with pytest.raises(PredictionUnavailable, match="Model verification failed") as error:
        load_verified_artifacts(root)
    assert loads == []
    assert str(root) not in str(error.value)


def test_bundle_rejects_evidence_mismatch_and_invalid_model_interface(tmp_path):
    root = _model_bundle(tmp_path)
    projection = root / "reports/race_constraint_evaluation.json"
    projection.write_text(projection.read_text().replace("EXP-007", "EXP-999"))
    _write_json(
        root / "models/manifest.json",
        build_manifest(root, generated_at="2026-09-10T00:00:00+00:00"),
    )
    with pytest.raises(ModelBundleError, match="Model evidence verification failed"):
        verify_model_bundle(root)

    other = tmp_path / "invalid"
    root = _model_bundle(other, selected_model=object())
    with pytest.raises(PredictionUnavailable, match="Model artifact interface is invalid"):
        load_verified_artifacts(root)


@pytest.mark.parametrize(
    "changes",
    [
        {"features": ["unexpected_feature"]},
        {"calibration": {"slope": float("nan"), "intercept": 0.2, "method": "bad"}},
        {"inference_years": [2020, 2024]},
    ],
)
def test_loaded_bundle_rejects_manifest_metadata_disagreement(tmp_path, changes):
    root = _model_bundle(tmp_path, artifact_changes=changes)
    with pytest.raises(PredictionUnavailable, match="Model artifact metadata is invalid"):
        load_verified_artifacts(root)
