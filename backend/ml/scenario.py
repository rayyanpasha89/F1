"""Strict public contract for frozen-model grid sensitivity analysis."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class GridScenarioRequest(_Contract):
    driver_a_id: int = Field(gt=0, strict=True)
    driver_b_id: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def distinct_drivers(self):
        if self.driver_a_id == self.driver_b_id:
            raise ValueError("Choose two different drivers.")
        return self


class GridChange(_Contract):
    driver_id: int = Field(gt=0)
    recorded_grid_position: int = Field(ge=0, le=40)
    scenario_grid_position: int = Field(ge=0, le=40)
    original_grid_input: int = Field(gt=0, le=40)
    scenario_grid_input: int = Field(gt=0, le=40)


class ScenarioModification(_Contract):
    kind: Literal["swap_recorded_grid_positions"]
    drivers: tuple[GridChange, GridChange]

    @model_validator(mode="after")
    def valid_swap(self):
        first, second = self.drivers
        if first.driver_id == second.driver_id:
            raise ValueError("scenario drivers must be distinct")
        if (
            first.recorded_grid_position != second.scenario_grid_position
            or second.recorded_grid_position != first.scenario_grid_position
            or first.original_grid_input != second.scenario_grid_input
            or second.original_grid_input != first.scenario_grid_input
        ):
            raise ValueError("scenario positions and model inputs must be exchanged")
        return self


class GridContribution(_Contract):
    original: float
    scenario: float
    delta: float

    @model_validator(mode="after")
    def consistent_delta(self):
        if not math.isclose(self.scenario - self.original, self.delta, abs_tol=1e-12):
            raise ValueError("grid contribution delta is inconsistent")
        return self


class ScenarioPrediction(_Contract):
    driver_id: int = Field(gt=0)
    constructor_id: int = Field(gt=0)
    recorded_grid_position: int = Field(ge=0, le=40)
    scenario_grid_position: int = Field(ge=0, le=40)
    original_grid_input: int = Field(gt=0, le=40)
    scenario_grid_input: int = Field(gt=0, le=40)
    original_rank: int = Field(gt=0, le=40)
    scenario_rank: int = Field(gt=0, le=40)
    original_probability: float = Field(gt=0, lt=1)
    scenario_probability: float = Field(gt=0, lt=1)
    probability_delta: float = Field(gt=-1, lt=1)
    starting_grid_contribution: GridContribution

    @model_validator(mode="after")
    def consistent_probability_delta(self):
        if not math.isclose(
            self.scenario_probability - self.original_probability,
            self.probability_delta,
            abs_tol=1e-12,
        ):
            raise ValueError("probability delta is inconsistent")
        return self


class ScenarioPostprocessor(_Contract):
    method: Literal["race_logit_offset"]
    expected_podiums: Literal[3]
    original_sum: float = Field(gt=0, le=40)
    scenario_sum: float = Field(gt=0, le=40)

    @model_validator(mode="after")
    def coherent_sums(self):
        if not math.isclose(self.original_sum, 3, abs_tol=1e-9) or not math.isclose(
            self.scenario_sum, 3, abs_tol=1e-9
        ):
            raise ValueError("scenario probabilities must sum to three")
        return self


class ScenarioEvidenceBoundary(_Contract):
    input_scope: Literal["recorded pre-race features with two grid positions swapped"]
    outcome_data_used: Literal[False]
    causal: Literal[False]
    validated_forecast: Literal[False]
    statement: Literal[
        "This counterfactual shows frozen-model sensitivity; it is not a causal estimate, an unseen evaluation, or a live-race recommendation."
    ]


class GridScenario(_Contract):
    schema_version: Literal["f1-grid-scenario-v1"]
    scenario_type: Literal["counterfactual_grid_swap"]
    race_id: int = Field(gt=0)
    year: int = Field(ge=2022, le=2024)
    experiment_id: str = Field(min_length=1, max_length=30)
    model_version: str = Field(min_length=1, max_length=100)
    modification: ScenarioModification
    postprocessing: ScenarioPostprocessor
    predictions: tuple[ScenarioPrediction, ...] = Field(min_length=2, max_length=40)
    evidence_boundary: ScenarioEvidenceBoundary
    notes: tuple[str, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def coherent_comparison(self):
        rows = self.predictions
        driver_ids = [row.driver_id for row in rows]
        if len(set(driver_ids)) != len(rows):
            raise ValueError("scenario drivers must be unique")
        expected_ranks = set(range(1, len(rows) + 1))
        if {row.original_rank for row in rows} != expected_ranks or {
            row.scenario_rank for row in rows
        } != expected_ranks:
            raise ValueError("scenario ranks must be complete")
        if [row.scenario_rank for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError("scenario rows must be sorted by scenario rank")
        if not math.isclose(
            sum(row.original_probability for row in rows),
            self.postprocessing.original_sum,
            abs_tol=1e-9,
        ) or not math.isclose(
            sum(row.scenario_probability for row in rows),
            self.postprocessing.scenario_sum,
            abs_tol=1e-9,
        ):
            raise ValueError("scenario row sums disagree with postprocessing")
        if not math.isclose(sum(row.probability_delta for row in rows), 0, abs_tol=1e-9):
            raise ValueError("scenario deltas must net to zero")
        changes_by_id = {change.driver_id: change for change in self.modification.drivers}
        changed_ids = set(changes_by_id)
        if not changed_ids.issubset(driver_ids):
            raise ValueError("modified drivers must be in the prediction set")
        for row in rows:
            should_change = row.driver_id in changed_ids
            input_changed = row.original_grid_input != row.scenario_grid_input
            if should_change is not input_changed:
                raise ValueError("scenario grid changes disagree with modification")
            if should_change:
                change = changes_by_id[row.driver_id]
                if (
                    row.recorded_grid_position != change.recorded_grid_position
                    or row.scenario_grid_position != change.scenario_grid_position
                    or row.original_grid_input != change.original_grid_input
                    or row.scenario_grid_input != change.scenario_grid_input
                ):
                    raise ValueError("scenario rows disagree with modification")
            elif row.recorded_grid_position != row.scenario_grid_position:
                raise ValueError("an unselected recorded grid position changed")
        return self


def _factor(row, feature):
    try:
        return next(item for item in row["factors"] if item["feature"] == feature)
    except (KeyError, StopIteration) as error:
        raise ValueError("prediction is missing the grid explanation") from error


class GridScenarioService:
    def __init__(self, predictor):
        self.predictor = predictor

    def swap(self, race_id: int, request: GridScenarioRequest) -> GridScenario:
        comparison = self.predictor.predict_grid_swap(
            race_id, request.driver_a_id, request.driver_b_id
        )
        original = comparison["original"]
        scenario = comparison["scenario"]
        recorded_grid = comparison["recorded_grid"]
        if (
            original["race_id"] != scenario["race_id"]
            or original["model_version"] != scenario["model_version"]
            or original["experiment_id"] != scenario["experiment_id"]
        ):
            raise ValueError("scenario and original model identity disagree")

        original_rows = {row["driver_id"]: row for row in original["predictions"]}
        original_ranks = {
            row["driver_id"]: rank for rank, row in enumerate(original["predictions"], start=1)
        }
        scenario_ranks = {
            row["driver_id"]: rank for rank, row in enumerate(scenario["predictions"], start=1)
        }

        predictions = []
        for scenario_row in scenario["predictions"]:
            driver_id = scenario_row["driver_id"]
            original_row = original_rows[driver_id]
            original_grid = _factor(original_row, "grid_position")
            scenario_grid = _factor(scenario_row, "grid_position")
            if driver_id == request.driver_a_id:
                scenario_grid_position = recorded_grid[request.driver_b_id]
            elif driver_id == request.driver_b_id:
                scenario_grid_position = recorded_grid[request.driver_a_id]
            else:
                scenario_grid_position = recorded_grid[driver_id]
            predictions.append(
                ScenarioPrediction(
                    driver_id=driver_id,
                    constructor_id=scenario_row["constructor_id"],
                    recorded_grid_position=recorded_grid[driver_id],
                    scenario_grid_position=scenario_grid_position,
                    original_grid_input=int(original_grid["value"]),
                    scenario_grid_input=int(scenario_grid["value"]),
                    original_rank=original_ranks[driver_id],
                    scenario_rank=scenario_ranks[driver_id],
                    original_probability=original_row["probability"],
                    scenario_probability=scenario_row["probability"],
                    probability_delta=(scenario_row["probability"] - original_row["probability"]),
                    starting_grid_contribution=GridContribution(
                        original=original_grid["log_odds_contribution"],
                        scenario=scenario_grid["log_odds_contribution"],
                        delta=(
                            scenario_grid["log_odds_contribution"]
                            - original_grid["log_odds_contribution"]
                        ),
                    ),
                )
            )

        changes = tuple(
            GridChange(
                driver_id=driver_id,
                recorded_grid_position=next(
                    row.recorded_grid_position for row in predictions if row.driver_id == driver_id
                ),
                scenario_grid_position=next(
                    row.scenario_grid_position for row in predictions if row.driver_id == driver_id
                ),
                original_grid_input=next(
                    row.original_grid_input for row in predictions if row.driver_id == driver_id
                ),
                scenario_grid_input=next(
                    row.scenario_grid_input for row in predictions if row.driver_id == driver_id
                ),
            )
            for driver_id in (request.driver_a_id, request.driver_b_id)
        )
        original_sum = sum(row.original_probability for row in predictions)
        scenario_sum = sum(row.scenario_probability for row in predictions)
        return GridScenario(
            schema_version="f1-grid-scenario-v1",
            scenario_type="counterfactual_grid_swap",
            race_id=race_id,
            year=original["year"],
            experiment_id=original["experiment_id"],
            model_version=original["model_version"],
            modification=ScenarioModification(
                kind="swap_recorded_grid_positions",
                drivers=changes,
            ),
            postprocessing=ScenarioPostprocessor(
                method="race_logit_offset",
                expected_podiums=3,
                original_sum=original_sum,
                scenario_sum=scenario_sum,
            ),
            predictions=tuple(predictions),
            evidence_boundary=ScenarioEvidenceBoundary(
                input_scope="recorded pre-race features with two grid positions swapped",
                outcome_data_used=False,
                causal=False,
                validated_forecast=False,
                statement=(
                    "This counterfactual shows frozen-model sensitivity; it is not a causal "
                    "estimate, an unseen evaluation, or a live-race recommendation."
                ),
            ),
            notes=(
                "Only the two selected model grid inputs changed; all other pre-race inputs stayed fixed.",
                "The shared race projection keeps all scenario probabilities equal to three podium places.",
                "Probability and SHAP changes describe the fitted model, not what would happen on track.",
            ),
        )
