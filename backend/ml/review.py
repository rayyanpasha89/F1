"""Post-race evaluation that keeps recorded outcomes outside forecast generation."""

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.ml.predictor import PredictionUnavailable


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RaceIdentity(_Contract):
    race_id: int = Field(gt=0)
    year: int = Field(ge=1950, le=2100)
    round: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    circuit_name: str = Field(min_length=1, max_length=200)
    country: str = Field(min_length=1, max_length=100)


class ReviewPostprocessor(_Contract):
    method: Literal["race_logit_offset"]
    expected_podiums: Literal[3]


class PodiumDriver(_Contract):
    rank: int = Field(ge=1, le=3)
    driver_id: int = Field(gt=0)
    driver_name: str = Field(min_length=1, max_length=200)
    constructor_name: str = Field(min_length=1, max_length=200)
    probability: float = Field(gt=0, lt=1)


class ReviewDriver(_Contract):
    predicted_rank: int = Field(gt=0, le=40)
    driver_id: int = Field(gt=0)
    driver_name: str = Field(min_length=1, max_length=200)
    constructor_name: str = Field(min_length=1, max_length=200)
    grid: int = Field(ge=0, le=99)
    probability: float = Field(gt=0, lt=1)
    recorded_finish: str = Field(min_length=1, max_length=20)
    recorded_podium: bool
    absolute_error: float = Field(ge=0, le=1)


class SurpriseDriver(_Contract):
    driver_id: int = Field(gt=0)
    driver_name: str = Field(min_length=1, max_length=200)
    probability: float = Field(gt=0, lt=1)
    recorded_podium: bool
    error: float = Field(ge=0, le=1)


class Surprises(_Contract):
    largest_overprediction: SurpriseDriver
    largest_underprediction: SurpriseDriver


class RaceReview(_Contract):
    review_type: Literal["post_race_review"]
    race: RaceIdentity
    model_version: str = Field(min_length=1, max_length=100)
    postprocessor: ReviewPostprocessor
    predicted_podium: tuple[PodiumDriver, PodiumDriver, PodiumDriver]
    recorded_podium: tuple[PodiumDriver, PodiumDriver, PodiumDriver]
    top_three_hits: int = Field(ge=0, le=3)
    exact_podium_set: bool
    brier_score: float = Field(ge=0, le=1)
    mean_absolute_error: float = Field(ge=0, le=1)
    surprises: Surprises
    drivers: tuple[ReviewDriver, ...] = Field(min_length=2, max_length=40)
    notes: tuple[str, ...] = Field(min_length=1, max_length=8)

    @field_validator("drivers")
    @classmethod
    def unique_drivers(cls, value: tuple[ReviewDriver, ...]) -> tuple[ReviewDriver, ...]:
        identifiers = [row.driver_id for row in value]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("duplicate driver")
        return value


class RaceReviewService:
    def __init__(self, predictor, analytics):
        self.predictor = predictor
        self.analytics = analytics

    def review(self, race_id: int) -> RaceReview:
        # Generate the forecast before reading any same-race result label.
        forecast = self.predictor.predict(race_id)
        race = self.analytics.race(race_id)
        results = self.analytics.race_table(race_id, "results")
        predictions = forecast.get("predictions")
        if not isinstance(predictions, list) or not 2 <= len(predictions) <= 40:
            raise PredictionUnavailable("Forecast review is unavailable for this race.")
        try:
            predictions = sorted(
                predictions, key=lambda row: (-float(row["probability"]), int(row["driver_id"]))
            )
            probability_sum = sum(float(row["probability"]) for row in predictions)
        except (KeyError, TypeError, ValueError) as error:
            raise PredictionUnavailable("Forecast review is unavailable for this race.") from error
        if not math.isclose(probability_sum, 3, abs_tol=1e-10) or any(
            not 0 < float(row["probability"]) < 1 for row in predictions
        ):
            raise PredictionUnavailable("Forecast review is unavailable for this race.")
        result_map = {int(row["driver_id"]): row for row in results}
        if len(result_map) != len(results) or set(result_map) != {
            int(row["driver_id"]) for row in predictions
        }:
            raise PredictionUnavailable("Recorded result set does not match the forecast entrants.")
        recorded = []
        for position in (1, 2, 3):
            matches = [row for row in results if row.get("position") == position]
            if len(matches) != 1:
                raise PredictionUnavailable("Recorded podium is unavailable for this race.")
            recorded.append(matches[0])

        driver_rows = []
        labels = []
        probabilities = []
        for predicted_rank, prediction in enumerate(predictions, start=1):
            driver_id = int(prediction["driver_id"])
            probability = float(prediction["probability"])
            result = result_map[driver_id]
            label = bool(result.get("position") in (1, 2, 3))
            labels.append(int(label))
            probabilities.append(probability)
            driver_rows.append(
                ReviewDriver(
                    predicted_rank=predicted_rank,
                    driver_id=driver_id,
                    driver_name=result["driver_name"],
                    constructor_name=result["constructor_name"],
                    grid=int(result["grid"]),
                    probability=probability,
                    recorded_finish=str(result.get("position_text") or result["position_order"]),
                    recorded_podium=label,
                    absolute_error=abs(probability - int(label)),
                )
            )
        labels_array = np.asarray(labels, dtype=float)
        probabilities_array = np.asarray(probabilities, dtype=float)
        predicted_ids = {row.driver_id for row in driver_rows[:3]}
        recorded_ids = {int(row["driver_id"]) for row in recorded}
        hits = len(predicted_ids & recorded_ids)

        over = min(
            driver_rows,
            key=lambda row: (-(row.probability - int(row.recorded_podium)), row.driver_id),
        )
        under = min(
            driver_rows,
            key=lambda row: (-(int(row.recorded_podium) - row.probability), row.driver_id),
        )

        def podium_driver(result, rank):
            row = next(item for item in driver_rows if item.driver_id == int(result["driver_id"]))
            return PodiumDriver(
                rank=rank,
                driver_id=row.driver_id,
                driver_name=row.driver_name,
                constructor_name=row.constructor_name,
                probability=row.probability,
            )

        return RaceReview(
            review_type="post_race_review",
            race=RaceIdentity(
                race_id=int(race["race_id"]),
                year=int(race["year"]),
                round=int(race["round"]),
                name=race["name"],
                date=str(race["date"]),
                circuit_name=race["circuit_name"],
                country=race["country"],
            ),
            model_version=forecast["model_version"],
            postprocessor=ReviewPostprocessor(
                method=forecast["postprocessing"]["method"],
                expected_podiums=forecast["postprocessing"]["expected_podiums"],
            ),
            predicted_podium=tuple(
                podium_driver(result_map[row.driver_id], rank)
                for rank, row in enumerate(driver_rows[:3], start=1)
            ),
            recorded_podium=tuple(
                podium_driver(result, rank) for rank, result in enumerate(recorded, start=1)
            ),
            top_three_hits=hits,
            exact_podium_set=predicted_ids == recorded_ids,
            brier_score=float(np.mean(np.square(probabilities_array - labels_array))),
            mean_absolute_error=float(np.mean(np.abs(probabilities_array - labels_array))),
            surprises=Surprises(
                largest_overprediction=SurpriseDriver(
                    driver_id=over.driver_id,
                    driver_name=over.driver_name,
                    probability=over.probability,
                    recorded_podium=over.recorded_podium,
                    error=over.probability - int(over.recorded_podium),
                ),
                largest_underprediction=SurpriseDriver(
                    driver_id=under.driver_id,
                    driver_name=under.driver_name,
                    probability=under.probability,
                    recorded_podium=under.recorded_podium,
                    error=int(under.recorded_podium) - under.probability,
                ),
            ),
            drivers=tuple(driver_rows),
            notes=(
                "Forecast probabilities and explanations are produced before recorded results are read.",
                "Recorded finishes are evaluation labels only and are never model inputs for this race.",
                "Brier score and mean absolute error cover every recorded entrant; lower is better.",
            ),
        )
