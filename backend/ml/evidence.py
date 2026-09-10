"""Strict, non-secret validation for the model and its committed evidence bundle."""

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.database import ROOT


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ModelBundleError(ValueError):
    pass


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Calibration(_StrictModel):
    slope: float
    intercept: float
    method: str = Field(min_length=1, max_length=100)

    @field_validator("slope", "intercept")
    @classmethod
    def finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value


class Postprocessor(_StrictModel):
    name: Literal["race_logit_offset"]
    version: Literal["v1"]
    expected_count: Literal[3]


class ArtifactHashes(_StrictModel):
    podium_model_sha256: Sha256
    grid_baseline_sha256: Sha256


class EvidenceHashes(_StrictModel):
    model_selection: Sha256
    final_test_metrics: Sha256
    data_audit: Sha256
    race_constraint_evaluation: Sha256


class TemporalSplit(_StrictModel):
    training_years: tuple[int, int]
    selection_years: tuple[int, int]
    inference_years: tuple[int, int]

    @model_validator(mode="after")
    def ordered(self):
        ranges = (self.training_years, self.selection_years, self.inference_years)
        if any(start > end for start, end in ranges):
            raise ValueError("invalid year range")
        if not self.training_years[1] < self.selection_years[0]:
            raise ValueError("training and selection overlap")
        if not self.selection_years[1] < self.inference_years[0]:
            raise ValueError("selection and inference overlap")
        return self


class SourceCoverage(_StrictModel):
    archive_years: tuple[int, int]
    races: int = Field(gt=0)
    audited_tables: int = Field(gt=0)


class ModelManifest(_StrictModel):
    schema_version: Literal["f1-model-manifest-v1"]
    generated_at: datetime
    model_version: str = Field(pattern=r"^EXP-[0-9]{3}\+podium-count-v1$")
    experiment_id: str = Field(pattern=r"^EXP-[0-9]{3}$")
    features: tuple[str, ...] = Field(min_length=1, max_length=32)
    temporal_split: TemporalSplit
    selection_frozen_at: datetime
    calibration: Calibration
    postprocessor: Postprocessor
    artifacts: ArtifactHashes
    evidence_sha256: EvidenceHashes
    source_coverage: SourceCoverage
    evidence_status: Literal["post_test_iterative_evidence"]

    @field_validator("features")
    @classmethod
    def valid_features(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not name or len(name) > 100 for name in value):
            raise ValueError("invalid features")
        return value

    @model_validator(mode="after")
    def matching_version(self):
        if self.model_version != f"{self.experiment_id}+podium-count-v1":
            raise ValueError("model version mismatch")
        return self


ARTIFACT_TARGETS = {
    "podium_model_sha256": "models/podium_model.joblib",
    "grid_baseline_sha256": "models/grid_baseline.joblib",
}
EVIDENCE_TARGETS = {
    "model_selection": "reports/model_selection.json",
    "final_test_metrics": "reports/final_test_metrics.json",
    "data_audit": "reports/data_audit.json",
    "race_constraint_evaluation": "reports/race_constraint_evaluation.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise ModelBundleError("Model evidence verification failed.") from error
    return digest.hexdigest()


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ModelBundleError("Model evidence verification failed.") from error
    if not isinstance(value, dict):
        raise ModelBundleError("Model evidence verification failed.")
    return value


def _timestamp(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ModelBundleError("Model evidence verification failed.") from error


def load_manifest(path: Path = ROOT / "models/manifest.json") -> ModelManifest:
    try:
        return ModelManifest.model_validate_json(path.read_text())
    except Exception as error:
        raise ModelBundleError("Model manifest is invalid.") from error


def verify_model_bundle(root: Path = ROOT) -> ModelManifest:
    """Verify hashes and allowlisted report agreement without deserializing a model."""

    root = Path(root)
    manifest = load_manifest(root / "models/manifest.json")
    for field, relative in ARTIFACT_TARGETS.items():
        if _sha256(root / relative) != getattr(manifest.artifacts, field):
            raise ModelBundleError("Model evidence verification failed.")
    for field, relative in EVIDENCE_TARGETS.items():
        if _sha256(root / relative) != getattr(manifest.evidence_sha256, field):
            raise ModelBundleError("Model evidence verification failed.")

    selection = _json(root / EVIDENCE_TARGETS["model_selection"])
    final_test = _json(root / EVIDENCE_TARGETS["final_test_metrics"])
    audit = _json(root / EVIDENCE_TARGETS["data_audit"])
    projection = _json(root / EVIDENCE_TARGETS["race_constraint_evaluation"])
    expected_selection = {
        "experiment_id": manifest.experiment_id,
        "features": list(manifest.features),
        "training_years": list(manifest.temporal_split.training_years),
        "selection_years": list(manifest.temporal_split.selection_years),
        "inference_years": list(manifest.temporal_split.inference_years),
        "calibration": manifest.calibration.model_dump(),
    }
    if any(selection.get(key) != value for key, value in expected_selection.items()):
        raise ModelBundleError("Model evidence verification failed.")
    if _timestamp(selection.get("selection_frozen_at")) != manifest.selection_frozen_at:
        raise ModelBundleError("Model evidence verification failed.")
    if (
        final_test.get("artifact_sha256") != manifest.artifacts.podium_model_sha256
        or final_test.get("test_years") != list(manifest.temporal_split.inference_years)
        or _timestamp(final_test.get("selection_frozen_at")) != manifest.selection_frozen_at
    ):
        raise ModelBundleError("Model evidence verification failed.")
    races = audit.get("tables", {}).get("races", {})
    if (
        races.get("year_range") != list(manifest.source_coverage.archive_years)
        or races.get("rows") != manifest.source_coverage.races
        or len(audit.get("tables", {})) != manifest.source_coverage.audited_tables
    ):
        raise ModelBundleError("Model evidence verification failed.")
    gates = projection.get("ship_gates")
    if (
        projection.get("schema_version") != "f1-probability-coherence-v1"
        or projection.get("model_version") != manifest.model_version
        or projection.get("evidence_boundary", {}).get("unseen_holdout") is not False
        or not isinstance(gates, dict)
        or set(gates)
        != {
            "validation_log_loss_improved",
            "validation_brier_improved",
            "all_race_sums_exact",
            "all_rankings_preserved",
        }
        or not all(value is True for value in gates.values())
    ):
        raise ModelBundleError("Model evidence verification failed.")
    return manifest
