import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.build_model_manifest import ModelEvidenceError, build_manifest
from scripts.evaluate_probability_projection import evaluate_projection


class _ScoreModel:
    def decision_function(self, frame):
        return frame["model_score"].to_numpy()


class _GridBaseline:
    def predict_proba(self, frame):
        probability = np.asarray([0.62, 0.52, 0.42, 0.12, 0.06] * (len(frame) // 5))
        return np.column_stack([1 - probability, probability])


def _evaluation_frame():
    logits = np.log(
        np.array([0.72, 0.62, 0.52, 0.08, 0.03]) / np.array([0.28, 0.38, 0.48, 0.92, 0.97])
    )
    rows = []
    for race_id, year in enumerate((2019, 2020, 2021, 2022, 2023, 2024), start=1):
        for index, score in enumerate(logits):
            rows.append(
                {
                    "race_id": race_id,
                    "driver_id": race_id * 10 + index,
                    "year": year,
                    "podium": int(index < 3),
                    "grid_position": index + 1,
                    "model_score": score,
                }
            )
    return pd.DataFrame(rows)


def test_projection_evaluation_is_deterministic_bounded_and_honest():
    artifact = {
        "model": _ScoreModel(),
        "features": ["model_score"],
        "experiment_id": "EXP-TEST",
        "training_years": [2010, 2018],
        "selection_years": [2019, 2021],
        "inference_years": [2022, 2024],
        "calibration": {"slope": 1.0, "intercept": 0.0, "method": "test sigmoid"},
    }

    first = evaluate_projection(
        _evaluation_frame(), artifact, _GridBaseline(), bootstrap_replicates=200, seed=42
    )
    second = evaluate_projection(
        _evaluation_frame(), artifact, _GridBaseline(), bootstrap_replicates=200, seed=42
    )

    assert first == second
    assert first["schema_version"] == "f1-probability-coherence-v1"
    assert first["evidence_boundary"]["unseen_holdout"] is False
    assert first["splits"]["validation"]["evidence_status"] == "reused_model_selection_period"
    assert first["splits"]["consumed_test"]["evidence_status"] == "consumed_post_test_iterative"
    assert first["ship_gates"] == {
        "validation_log_loss_improved": True,
        "validation_brier_improved": True,
        "all_race_sums_exact": True,
        "all_rankings_preserved": True,
    }
    for split in first["splits"].values():
        assert split["race_constraint"]["maximum_absolute_sum_error"] < 1e-10
        assert split["race_constraint"]["selected_rank_preserved"] is True
        assert split["race_constraint"]["baseline_rank_preserved"] is True
        assert (
            split["selected_model"]["projected"]["log_loss"]
            < split["selected_model"]["raw"]["log_loss"]
        )
        assert (
            split["selected_model"]["projected"]["brier_score"]
            < split["selected_model"]["raw"]["brier_score"]
        )

    bootstrap = first["paired_race_bootstrap"]
    assert bootstrap["unit"] == "whole_race"
    assert bootstrap["replicates"] == 200
    assert bootstrap["seed"] == 42
    assert bootstrap["comparison"] == "projected_selected_minus_projected_baseline"
    for interval in bootstrap["metrics"].values():
        assert set(interval) == {"estimate", "lower_95", "upper_95"}
        assert all(np.isfinite(value) for value in interval.values())
    serialized = json.dumps(first).lower()
    for forbidden in (
        "database_url",
        "password",
        "secret",
        "access_token",
        str(Path.cwd()).lower(),
    ):
        assert forbidden not in serialized


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def test_manifest_contains_only_required_hashes_and_allowlisted_metadata(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "models/podium_model.joblib").write_bytes(b"selected-model")
    (tmp_path / "models/grid_baseline.joblib").write_bytes(b"grid-baseline")
    selection = {
        "experiment_id": "EXP-007",
        "features": ["grid_position", "driver_recent_podium"],
        "training_years": [2010, 2018],
        "selection_years": [2019, 2021],
        "inference_years": [2022, 2024],
        "calibration": {"slope": 1.1, "intercept": 0.2, "method": "temporal sigmoid"},
        "selection_frozen_at": "2026-09-08T10:35:42+00:00",
        "ignored": {"password": "must-not-leak"},
    }
    _write_json(tmp_path / "reports/model_selection.json", selection)
    _write_json(tmp_path / "reports/final_test_metrics.json", {"test_years": [2022, 2024]})
    _write_json(tmp_path / "reports/data_audit.json", {"format_version": 1})
    _write_json(
        tmp_path / "reports/race_constraint_evaluation.json",
        {
            "schema_version": "f1-probability-coherence-v1",
            "ship_gates": {
                "validation_log_loss_improved": True,
                "validation_brier_improved": True,
                "all_race_sums_exact": True,
                "all_rankings_preserved": True,
            },
        },
    )

    manifest = build_manifest(tmp_path, generated_at="2026-09-10T00:00:00+00:00")

    assert manifest["schema_version"] == "f1-model-manifest-v1"
    assert manifest["model_version"] == "EXP-007+podium-count-v1"
    assert manifest["features"] == selection["features"]
    assert manifest["postprocessor"] == {
        "name": "race_logit_offset",
        "version": "v1",
        "expected_count": 3,
    }
    assert (
        manifest["artifacts"]["podium_model_sha256"]
        == hashlib.sha256(b"selected-model").hexdigest()
    )
    assert (
        manifest["artifacts"]["grid_baseline_sha256"]
        == hashlib.sha256(b"grid-baseline").hexdigest()
    )
    serialized = json.dumps(manifest)
    assert str(tmp_path) not in serialized
    assert "must-not-leak" not in serialized
    assert "password" not in serialized.lower()


def test_manifest_rejects_missing_evidence(tmp_path):
    with pytest.raises(ModelEvidenceError, match="Model evidence bundle is incomplete"):
        build_manifest(tmp_path, generated_at="2026-09-10T00:00:00+00:00")
