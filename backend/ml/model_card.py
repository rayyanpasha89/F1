"""Bounded public model accountability data assembled from verified evidence."""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.database import ROOT
from backend.ml.evidence import (
    EvidenceHashes,
    ModelBundleError,
    Postprocessor,
    Sha256,
    SourceCoverage,
    TemporalSplit,
    verify_model_bundle,
)


class ModelCardError(ValueError):
    pass


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ModelIdentity(_Contract):
    name: Literal["F1 Race Strategist podium probability model"]
    model_version: str = Field(min_length=1, max_length=100)
    experiment_id: str = Field(min_length=1, max_length=30)
    prediction_type: Literal["retrospective post-grid pre-race podium probability"]


class PublicArtifactHashes(_Contract):
    selected_model: Sha256
    grid_baseline: Sha256


class Lineage(_Contract):
    manifest_generated_at: datetime
    selection_frozen_at: datetime
    artifacts: PublicArtifactHashes
    evidence: EvidenceHashes


class ProbabilityScores(_Contract):
    log_loss: float = Field(ge=0, le=10)
    brier_score: float = Field(ge=0, le=1)
    roc_auc: float = Field(ge=0, le=1)
    top3_hit_rate: float = Field(ge=0, le=1)
    exact_podium_set_rate: float = Field(ge=0, le=1)
    ece_10_bins: float = Field(ge=0, le=1)


class ScoreChange(_Contract):
    log_loss: float = Field(ge=-10, le=10)
    brier_score: float = Field(ge=-1, le=1)
    top3_hit_rate: float = Field(ge=-1, le=1)


class ModelComparison(_Contract):
    raw: ProbabilityScores
    projected: ProbabilityScores
    projected_minus_raw: ScoreChange


class RaceConstraint(_Contract):
    expected_podiums: Literal[3]
    selected_average_raw_sum: float = Field(ge=0, le=40)
    selected_average_projected_sum: float = Field(ge=0, le=40)
    baseline_average_raw_sum: float = Field(ge=0, le=40)
    baseline_average_projected_sum: float = Field(ge=0, le=40)
    maximum_absolute_sum_error: float = Field(ge=0, le=1e-10)
    selected_rank_preserved: Literal[True]
    baseline_rank_preserved: Literal[True]


EvidenceStatus = Literal["reused_model_selection_period", "consumed_post_test_iterative"]


class SplitEvidence(_Contract):
    years: tuple[int, int]
    evidence_status: EvidenceStatus
    rows: int = Field(gt=0)
    races: int = Field(gt=0)
    selected_model: ModelComparison
    baseline: ModelComparison
    race_constraint: RaceConstraint


class MetricSplits(_Contract):
    validation: SplitEvidence
    consumed_test: SplitEvidence


class SeasonEvidence(_Contract):
    evidence_status: EvidenceStatus
    rows: int = Field(gt=0)
    races: int = Field(gt=0)
    selected_model: ProbabilityScores
    baseline: ProbabilityScores


class BootstrapInterval(_Contract):
    estimate: float = Field(ge=-10, le=10)
    lower_95: float = Field(ge=-10, le=10)
    upper_95: float = Field(ge=-10, le=10)

    @model_validator(mode="after")
    def ordered(self):
        if self.lower_95 > self.upper_95:
            raise ValueError("invalid interval")
        return self


class BootstrapMetrics(_Contract):
    log_loss: BootstrapInterval
    brier_score: BootstrapInterval
    top3_hit_rate: BootstrapInterval


class PairedRaceBootstrap(_Contract):
    split: Literal["consumed_test"]
    unit: Literal["whole_race"]
    replicates: Literal[5000]
    seed: Literal[42]
    comparison: Literal["projected_selected_minus_projected_baseline"]
    metrics: BootstrapMetrics
    limitation: str = Field(min_length=1, max_length=500)


class CalibrationSummary(_Contract):
    method: str = Field(min_length=1, max_length=100)
    slope: float
    intercept: float
    validation_raw_ece: float = Field(ge=0, le=1)
    validation_projected_ece: float = Field(ge=0, le=1)
    consumed_test_raw_ece: float = Field(ge=0, le=1)
    consumed_test_projected_ece: float = Field(ge=0, le=1)


class ExplanationSummary(_Contract):
    method: Literal["Tree SHAP"]
    units: Literal["calibrated log-odds"]
    probability_reconstruction: Literal["exact after adding the race-level offset to the base"]
    causal: Literal[False]


class EvidenceBoundary(_Contract):
    status: Literal["post_test_iterative_evidence"]
    unseen_holdout: Literal[False]
    statement: str = Field(min_length=1, max_length=500)


class ModelCard(_Contract):
    schema_version: Literal["f1-public-model-card-v1"]
    identity: ModelIdentity
    lineage: Lineage
    source_coverage: SourceCoverage
    intended_use: tuple[str, ...] = Field(min_length=1, max_length=8)
    excluded_uses: tuple[str, ...] = Field(min_length=1, max_length=8)
    features: tuple[str, ...] = Field(min_length=1, max_length=32)
    temporal_split: TemporalSplit
    postprocessor: Postprocessor
    metrics: MetricSplits
    per_season: dict[str, SeasonEvidence]
    paired_race_bootstrap: PairedRaceBootstrap
    calibration: CalibrationSummary
    explanations: ExplanationSummary
    evidence_boundary: EvidenceBoundary
    limitations: tuple[str, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid_seasons(self):
        if set(self.per_season) != {"2019", "2020", "2021", "2022", "2023", "2024"}:
            raise ValueError("invalid public season set")
        return self


def _scores(value: dict) -> ProbabilityScores:
    return ProbabilityScores(
        log_loss=value["log_loss"],
        brier_score=value["brier_score"],
        roc_auc=value["roc_auc"],
        top3_hit_rate=value["top3_hit_rate"],
        exact_podium_set_rate=value["exact_podium_set_rate"],
        ece_10_bins=value["ece_10_bins"],
    )


def _comparison(value: dict) -> ModelComparison:
    return ModelComparison(
        raw=_scores(value["raw"]),
        projected=_scores(value["projected"]),
        projected_minus_raw=ScoreChange(**value["projected_minus_raw"]),
    )


def _split(value: dict) -> SplitEvidence:
    return SplitEvidence(
        years=value["years"],
        evidence_status=value["evidence_status"],
        rows=value["rows"],
        races=value["races"],
        selected_model=_comparison(value["selected_model"]),
        baseline=_comparison(value["baseline"]),
        race_constraint=RaceConstraint(**value["race_constraint"]),
    )


class ModelCardService:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)

    def get(self) -> ModelCard:
        try:
            manifest = verify_model_bundle(self.root)
            report = json.loads((self.root / "reports/race_constraint_evaluation.json").read_text())
            if (
                not isinstance(report, dict)
                or report.get("schema_version") != "f1-probability-coherence-v1"
                or report.get("model_version") != manifest.model_version
                or report.get("evidence_boundary", {}).get("unseen_holdout") is not False
                or not all(report.get("ship_gates", {}).values())
            ):
                raise ValueError("evidence disagreement")
            metrics = MetricSplits(
                validation=_split(report["splits"]["validation"]),
                consumed_test=_split(report["splits"]["consumed_test"]),
            )
            per_season = {
                year: SeasonEvidence(
                    evidence_status=value["evidence_status"],
                    rows=value["rows"],
                    races=value["races"],
                    selected_model=_scores(value["selected_model"]["projected"]),
                    baseline=_scores(value["baseline"]["projected"]),
                )
                for year, value in report["per_season"].items()
            }
            validation = metrics.validation.selected_model
            consumed = metrics.consumed_test.selected_model
            return ModelCard(
                schema_version="f1-public-model-card-v1",
                identity=ModelIdentity(
                    name="F1 Race Strategist podium probability model",
                    model_version=manifest.model_version,
                    experiment_id=manifest.experiment_id,
                    prediction_type="retrospective post-grid pre-race podium probability",
                ),
                lineage=Lineage(
                    manifest_generated_at=manifest.generated_at,
                    selection_frozen_at=manifest.selection_frozen_at,
                    artifacts=PublicArtifactHashes(
                        selected_model=manifest.artifacts.podium_model_sha256,
                        grid_baseline=manifest.artifacts.grid_baseline_sha256,
                    ),
                    evidence=manifest.evidence_sha256,
                ),
                source_coverage=manifest.source_coverage,
                intended_use=(
                    "Explore historical 2022-2024 podium probabilities after the recorded starting grid.",
                    "Compare a frozen selected model with a grid-only baseline.",
                    "Teach temporal evaluation, calibration, explanations, and post-race error analysis.",
                ),
                excluded_uses=(
                    "Live race operations or safety decisions.",
                    "Betting, financial decisions, or claims about future seasons.",
                    "Causal conclusions about drivers, teams, or race strategy.",
                ),
                features=manifest.features,
                temporal_split=manifest.temporal_split,
                postprocessor=manifest.postprocessor,
                metrics=metrics,
                per_season=per_season,
                paired_race_bootstrap=PairedRaceBootstrap(**report["paired_race_bootstrap"]),
                calibration=CalibrationSummary(
                    method=manifest.calibration.method,
                    slope=manifest.calibration.slope,
                    intercept=manifest.calibration.intercept,
                    validation_raw_ece=validation.raw.ece_10_bins,
                    validation_projected_ece=validation.projected.ece_10_bins,
                    consumed_test_raw_ece=consumed.raw.ece_10_bins,
                    consumed_test_projected_ece=consumed.projected.ece_10_bins,
                ),
                explanations=ExplanationSummary(
                    method="Tree SHAP",
                    units="calibrated log-odds",
                    probability_reconstruction="exact after adding the race-level offset to the base",
                    causal=False,
                ),
                evidence_boundary=EvidenceBoundary(**report["evidence_boundary"]),
                limitations=(
                    "The archive is a historical snapshot through 2024 and may contain later corrections.",
                    "Predictions are retrospective and require the recorded starting grid.",
                    "Weather, live telemetry, tyre compounds, and in-race events are outside the model.",
                    "The 2022-2024 outcomes were already consumed before the postprocessor assessment.",
                    "Bootstrap intervals describe sampled-race variation and do not remove selection bias.",
                    "SHAP explains fitted associations and does not establish causation.",
                ),
            )
        except ModelCardError:
            raise
        except (
            ModelBundleError,
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ModelCardError("Model accountability evidence is invalid.") from error
