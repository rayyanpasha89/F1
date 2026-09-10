"""Build a bounded hash manifest for the trusted model and evidence bundle."""

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from backend.database import ROOT


class ModelEvidenceError(ValueError):
    pass


REQUIRED_FILES = {
    "podium_model": "models/podium_model.joblib",
    "grid_baseline": "models/grid_baseline.joblib",
    "model_selection": "reports/model_selection.json",
    "final_test_metrics": "reports/final_test_metrics.json",
    "data_audit": "reports/data_audit.json",
    "race_constraint_evaluation": "reports/race_constraint_evaluation.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ModelEvidenceError("Model evidence bundle is invalid.") from error
    if not isinstance(value, dict):
        raise ModelEvidenceError("Model evidence bundle is invalid.")
    return value


def _years(selection: dict, name: str) -> list[int]:
    value = selection.get(name)
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(item) is not int for item in value)
        or value[0] > value[1]
    ):
        raise ModelEvidenceError("Model selection metadata is invalid.")
    return value


def build_manifest(root: Path, generated_at: str | None = None) -> dict:
    """Hash fixed bundle locations and copy only allowlisted selection metadata."""

    root = Path(root)
    paths = {name: root / relative for name, relative in REQUIRED_FILES.items()}
    if not all(path.is_file() for path in paths.values()):
        raise ModelEvidenceError("Model evidence bundle is incomplete.")
    selection = _json(paths["model_selection"])
    final_test = _json(paths["final_test_metrics"])
    audit = _json(paths["data_audit"])
    projection = _json(paths["race_constraint_evaluation"])
    features = selection.get("features")
    experiment_id = selection.get("experiment_id")
    calibration = selection.get("calibration")
    if (
        not isinstance(experiment_id, str)
        or not experiment_id
        or not isinstance(features, list)
        or not features
        or any(not isinstance(feature, str) or not feature for feature in features)
        or not isinstance(calibration, dict)
    ):
        raise ModelEvidenceError("Model selection metadata is invalid.")
    try:
        slope = float(calibration["slope"])
        intercept = float(calibration["intercept"])
        method = calibration["method"]
    except (KeyError, TypeError, ValueError) as error:
        raise ModelEvidenceError("Model calibration metadata is invalid.") from error
    if not math.isfinite(slope) or not math.isfinite(intercept) or not isinstance(method, str):
        raise ModelEvidenceError("Model calibration metadata is invalid.")
    gates = projection.get("ship_gates")
    if projection.get("schema_version") != "f1-probability-coherence-v1" or not isinstance(
        gates, dict
    ):
        raise ModelEvidenceError("Probability-coherence evidence is invalid.")
    required_gates = {
        "validation_log_loss_improved",
        "validation_brier_improved",
        "all_race_sums_exact",
        "all_rankings_preserved",
    }
    if set(gates) != required_gates or not all(gates.values()):
        raise ModelEvidenceError("Probability-coherence ship gates failed.")
    model_hash = _sha256(paths["podium_model"])
    recorded_model_hash = final_test.get("artifact_sha256")
    if recorded_model_hash is not None and recorded_model_hash != model_hash:
        raise ModelEvidenceError("Final evaluation does not match the selected artifact.")
    races = audit.get("tables", {}).get("races", {})
    source_coverage = {
        "archive_years": races.get("year_range"),
        "races": races.get("rows"),
        "audited_tables": len(audit.get("tables", {})),
    }
    return {
        "schema_version": "f1-model-manifest-v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "model_version": f"{experiment_id}+podium-count-v1",
        "experiment_id": experiment_id,
        "features": list(features),
        "temporal_split": {
            "training_years": _years(selection, "training_years"),
            "selection_years": _years(selection, "selection_years"),
            "inference_years": _years(selection, "inference_years"),
        },
        "selection_frozen_at": selection.get("selection_frozen_at"),
        "calibration": {"slope": slope, "intercept": intercept, "method": method},
        "postprocessor": {"name": "race_logit_offset", "version": "v1", "expected_count": 3},
        "artifacts": {
            "podium_model_sha256": model_hash,
            "grid_baseline_sha256": _sha256(paths["grid_baseline"]),
        },
        "evidence_sha256": {
            "model_selection": _sha256(paths["model_selection"]),
            "final_test_metrics": _sha256(paths["final_test_metrics"]),
            "data_audit": _sha256(paths["data_audit"]),
            "race_constraint_evaluation": _sha256(paths["race_constraint_evaluation"]),
        },
        "source_coverage": source_coverage,
        "evidence_status": "post_test_iterative_evidence",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "models/manifest.json")
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    manifest = build_manifest(ROOT, generated_at=args.generated_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output.relative_to(ROOT)),
                "model_version": manifest["model_version"],
                "schema_version": manifest["schema_version"],
            }
        )
    )


if __name__ == "__main__":
    main()
