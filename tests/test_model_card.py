import json
import math
from pathlib import Path

import pytest

from backend.ml.evidence import load_manifest
from backend.ml.model_card import ModelCardError, ModelCardService


ROOT = Path(__file__).resolve().parents[1]


def _trusted_manifest(monkeypatch, root=ROOT):
    manifest = load_manifest(ROOT / "models/manifest.json")
    monkeypatch.setattr("backend.ml.model_card.verify_model_bundle", lambda candidate: manifest)
    return manifest


def test_model_card_is_allowlisted_finite_and_matches_manifest(monkeypatch):
    manifest = _trusted_manifest(monkeypatch)

    card = ModelCardService(ROOT).get()
    payload = card.model_dump(mode="json")

    assert set(payload) == {
        "schema_version",
        "identity",
        "lineage",
        "source_coverage",
        "intended_use",
        "excluded_uses",
        "features",
        "temporal_split",
        "postprocessor",
        "metrics",
        "per_season",
        "paired_race_bootstrap",
        "calibration",
        "explanations",
        "evidence_boundary",
        "limitations",
    }
    assert payload["schema_version"] == "f1-public-model-card-v1"
    assert payload["identity"]["model_version"] == manifest.model_version
    assert payload["identity"]["experiment_id"] == manifest.experiment_id
    assert payload["features"] == list(manifest.features)
    assert payload["lineage"]["artifacts"]["selected_model"] == (
        manifest.artifacts.podium_model_sha256
    )
    assert payload["lineage"]["artifacts"]["grid_baseline"] == (
        manifest.artifacts.grid_baseline_sha256
    )
    split = payload["temporal_split"]
    assert split["training_years"][1] < split["selection_years"][0]
    assert split["selection_years"][1] < split["inference_years"][0]
    assert payload["metrics"]["consumed_test"]["evidence_status"] == (
        "consumed_post_test_iterative"
    )
    assert payload["evidence_boundary"]["unseen_holdout"] is False
    assert any("grid inputs are exchanged" in item for item in payload["intended_use"])
    assert any("Grid-swap scenarios" in item for item in payload["limitations"])
    assert set(payload["per_season"]) == {"2019", "2020", "2021", "2022", "2023", "2024"}

    def assert_finite(value):
        if isinstance(value, dict):
            for nested in value.values():
                assert_finite(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_finite(nested)
        elif isinstance(value, float):
            assert math.isfinite(value)

    assert_finite(payload)
    serialized = json.dumps(payload).lower()
    for forbidden in (
        str(ROOT).lower(),
        "/users/",
        "database_url",
        "api_key",
        "password",
        "secret",
        "joblib",
        "gradientboostingclassifier(",
    ):
        assert forbidden not in serialized


def test_model_card_rejects_invalid_or_disagreeing_report(tmp_path, monkeypatch):
    manifest = _trusted_manifest(monkeypatch)
    (tmp_path / "reports").mkdir()
    report = json.loads((ROOT / "reports/race_constraint_evaluation.json").read_text())
    report["model_version"] = "EXP-999+podium-count-v1"
    (tmp_path / "reports/race_constraint_evaluation.json").write_text(json.dumps(report))

    with pytest.raises(ModelCardError, match="Model accountability evidence is invalid"):
        ModelCardService(tmp_path).get()

    report["model_version"] = manifest.model_version
    report["splits"]["validation"]["selected_model"]["projected"]["log_loss"] = float("nan")
    (tmp_path / "reports/race_constraint_evaluation.json").write_text(json.dumps(report))
    with pytest.raises(ModelCardError, match="Model accountability evidence is invalid"):
        ModelCardService(tmp_path).get()
