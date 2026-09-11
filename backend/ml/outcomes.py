"""Derived maximum-entropy distribution over unordered podium sets."""

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.optimize import least_squares
from scipy.special import logit

from backend.ml.predictor import PredictionUnavailable


MAXIMUM_MARGINAL_ERROR = 1e-8


@dataclass(frozen=True)
class FixedSizeDistribution:
    """Complete fixed-size distribution in canonical driver-ID order."""

    driver_ids: tuple[int, ...]
    driver_sets: tuple[tuple[int, int, int], ...]
    probabilities: tuple[float, ...]
    reconstructed_marginals: tuple[float, ...]
    maximum_marginal_error: float
    entropy_bits: float


def _invalid_distribution() -> PredictionUnavailable:
    return PredictionUnavailable(
        "Podium outcome distribution requires distinct drivers and finite marginal "
        "probabilities in (0, 1) that sum to three."
    )


def fit_fixed_size_distribution(driver_ids, marginals) -> FixedSizeDistribution:
    """Fit the maximum-entropy distribution matching three-place marginals."""

    ids_input = tuple(driver_ids)
    marginal_input = tuple(marginals)
    if len(ids_input) != len(marginal_input) or not 4 <= len(ids_input) <= 40:
        raise _invalid_distribution()
    if any(
        isinstance(value, bool) or not isinstance(value, (int, np.integer)) for value in ids_input
    ):
        raise _invalid_distribution()
    ids = tuple(int(value) for value in ids_input)
    if any(value <= 0 for value in ids) or len(set(ids)) != len(ids):
        raise _invalid_distribution()
    try:
        marginal_values = np.asarray(marginal_input, dtype=float)
    except (TypeError, ValueError, OverflowError) as error:
        raise _invalid_distribution() from error
    if (
        marginal_values.shape != (len(ids),)
        or not np.isfinite(marginal_values).all()
        or not ((marginal_values > 0) & (marginal_values < 1)).all()
        or not math.isclose(float(marginal_values.sum()), 3, abs_tol=1e-9)
    ):
        raise _invalid_distribution()

    canonical_order = np.argsort(np.asarray(ids), kind="stable")
    canonical_ids = tuple(ids[index] for index in canonical_order)
    target = marginal_values[canonical_order]
    combination_indexes = np.asarray(
        list(combinations(range(len(canonical_ids)), 3)), dtype=np.int64
    )
    incidence = np.zeros((len(combination_indexes), len(canonical_ids)), dtype=float)
    incidence[np.arange(len(combination_indexes))[:, None], combination_indexes] = 1

    def evaluate(free_parameters):
        parameters = np.concatenate((np.asarray(free_parameters, dtype=float), [0.0]))
        scores = incidence @ parameters
        weights = np.exp(scores - scores.max())
        probabilities = weights / weights.sum()
        reconstructed = incidence.T @ probabilities
        return probabilities, reconstructed

    def residual(free_parameters):
        return evaluate(free_parameters)[1][:-1] - target[:-1]

    def jacobian(free_parameters):
        probabilities, reconstructed = evaluate(free_parameters)
        second_moment = incidence.T @ (probabilities[:, None] * incidence)
        covariance = second_moment - np.outer(reconstructed, reconstructed)
        return covariance[:-1, :-1]

    initial = logit(target[:-1]) - logit(target[-1])
    try:
        solution = least_squares(
            residual,
            initial,
            jac=jacobian,
            method="trf",
            ftol=1e-13,
            xtol=1e-13,
            gtol=1e-13,
            max_nfev=200,
        )
        probabilities, reconstructed = evaluate(solution.x)
    except (FloatingPointError, OverflowError, ValueError, np.linalg.LinAlgError) as error:
        raise PredictionUnavailable("Podium outcome distribution could not be derived.") from error

    maximum_error = float(np.max(np.abs(reconstructed - target)))
    if (
        not solution.success
        or not np.isfinite(solution.x).all()
        or not np.isfinite(probabilities).all()
        or not np.isfinite(reconstructed).all()
        or not math.isclose(float(probabilities.sum()), 1, abs_tol=1e-12)
        or maximum_error > MAXIMUM_MARGINAL_ERROR
    ):
        raise PredictionUnavailable("Podium outcome distribution could not be derived.")

    driver_sets = tuple(
        tuple(canonical_ids[index] for index in indexes) for indexes in combination_indexes
    )
    entropy_bits = float(-np.sum(probabilities * np.log2(probabilities)))
    return FixedSizeDistribution(
        driver_ids=canonical_ids,
        driver_sets=driver_sets,
        probabilities=tuple(float(value) for value in probabilities),
        reconstructed_marginals=tuple(float(value) for value in reconstructed),
        maximum_marginal_error=maximum_error,
        entropy_bits=entropy_bits,
    )


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class OutcomeDiagnostics(_Contract):
    method: Literal["maximum_entropy_fixed_size"]
    driver_count: int = Field(ge=4, le=40)
    podium_size: Literal[3]
    combination_count: int = Field(gt=0, le=9880)
    probability_sum: float = Field(gt=0, le=1)
    reconstructed_marginal_sum: float = Field(gt=0, le=40)
    maximum_marginal_error: float = Field(ge=0, le=MAXIMUM_MARGINAL_ERROR)
    entropy_bits: float = Field(ge=0, le=14)
    effective_outcome_count: float = Field(ge=1, le=9880)
    returned_outcome_count: int = Field(ge=3, le=25)
    returned_probability_sum: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def coherent_diagnostics(self):
        if self.combination_count != math.comb(self.driver_count, self.podium_size):
            raise ValueError("combination count is inconsistent")
        if not math.isclose(self.probability_sum, 1, abs_tol=1e-12):
            raise ValueError("outcome probabilities must sum to one")
        if not math.isclose(self.reconstructed_marginal_sum, 3, abs_tol=1e-9):
            raise ValueError("reconstructed marginals must sum to three")
        if self.entropy_bits > math.log2(self.combination_count) + 1e-10:
            raise ValueError("entropy exceeds the complete outcome space")
        if not math.isclose(
            self.effective_outcome_count, 2**self.entropy_bits, rel_tol=1e-10, abs_tol=1e-10
        ):
            raise ValueError("effective outcome count is inconsistent")
        if self.returned_outcome_count > self.combination_count:
            raise ValueError("returned count exceeds the outcome space")
        return self


class PodiumSetOutcome(_Contract):
    rank: int = Field(gt=0, le=25)
    driver_ids: tuple[int, int, int]
    probability: float = Field(gt=0, lt=1)
    cumulative_probability: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def canonical_set(self):
        if any(driver_id <= 0 for driver_id in self.driver_ids):
            raise ValueError("outcome driver IDs must be positive")
        if tuple(sorted(self.driver_ids)) != self.driver_ids:
            raise ValueError("outcome driver IDs must be canonical")
        return self


class DriverMarginal(_Contract):
    driver_id: int = Field(gt=0)
    forecast_rank: int = Field(gt=0, le=40)
    released_probability: float = Field(gt=0, lt=1)
    reconstructed_probability: float = Field(gt=0, lt=1)
    absolute_error: float = Field(ge=0, le=MAXIMUM_MARGINAL_ERROR)

    @model_validator(mode="after")
    def coherent_error(self):
        if not math.isclose(
            abs(self.reconstructed_probability - self.released_probability),
            self.absolute_error,
            abs_tol=1e-15,
        ):
            raise ValueError("marginal reconstruction error is inconsistent")
        return self


class CoPodiumPair(_Contract):
    rank: int = Field(gt=0, le=10)
    driver_ids: tuple[int, int]
    probability: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def canonical_pair(self):
        if any(driver_id <= 0 for driver_id in self.driver_ids):
            raise ValueError("pair driver IDs must be positive")
        if tuple(sorted(self.driver_ids)) != self.driver_ids:
            raise ValueError("pair driver IDs must be canonical")
        return self


class PodiumOutcomeEvidenceBoundary(_Contract):
    derived_from: Literal["released race-level marginal podium probabilities"]
    outcome_data_used: Literal[False]
    separately_trained_joint_model: Literal[False]
    joint_forecast_validated: Literal[False]
    causal: Literal[False]
    ordering: Literal["unordered_podium_set"]
    statement: Literal[
        "This maximum-entropy distribution is derived from released marginals; it is not a separately trained or validated finishing-order forecast."
    ]


class PodiumOutcomes(_Contract):
    schema_version: Literal["f1-podium-outcomes-v1"]
    outcome_type: Literal["derived_unordered_podium_set_distribution"]
    race_id: int = Field(gt=0)
    year: int = Field(ge=2022, le=2024)
    experiment_id: str = Field(min_length=1, max_length=30)
    model_version: str = Field(min_length=1, max_length=100)
    diagnostics: OutcomeDiagnostics
    outcomes: tuple[PodiumSetOutcome, ...] = Field(min_length=3, max_length=25)
    driver_marginals: tuple[DriverMarginal, ...] = Field(min_length=4, max_length=40)
    co_podium_pairs: tuple[CoPodiumPair, ...] = Field(min_length=1, max_length=10)
    evidence_boundary: PodiumOutcomeEvidenceBoundary
    notes: tuple[str, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def coherent_distribution(self):
        diagnostics = self.diagnostics
        if len(self.driver_marginals) != diagnostics.driver_count:
            raise ValueError("driver count is inconsistent")
        if len(self.outcomes) != diagnostics.returned_outcome_count:
            raise ValueError("returned outcome count is inconsistent")

        driver_ids = [row.driver_id for row in self.driver_marginals]
        if len(set(driver_ids)) != len(driver_ids):
            raise ValueError("marginal drivers must be unique")
        if [row.forecast_rank for row in self.driver_marginals] != list(
            range(1, diagnostics.driver_count + 1)
        ):
            raise ValueError("marginals must follow forecast rank")
        if not math.isclose(
            sum(row.released_probability for row in self.driver_marginals), 3, abs_tol=1e-9
        ) or not math.isclose(
            sum(row.reconstructed_probability for row in self.driver_marginals),
            diagnostics.reconstructed_marginal_sum,
            abs_tol=1e-9,
        ):
            raise ValueError("marginal sums are inconsistent")
        if not math.isclose(
            max(row.absolute_error for row in self.driver_marginals),
            diagnostics.maximum_marginal_error,
            abs_tol=1e-15,
        ):
            raise ValueError("maximum marginal error is inconsistent")

        expected_ranks = list(range(1, len(self.outcomes) + 1))
        if [row.rank for row in self.outcomes] != expected_ranks:
            raise ValueError("outcome ranks must be complete")
        probabilities = [row.probability for row in self.outcomes]
        if probabilities != sorted(probabilities, reverse=True):
            raise ValueError("outcomes must be probability ordered")
        if len({row.driver_ids for row in self.outcomes}) != len(self.outcomes):
            raise ValueError("outcome sets must be unique")
        cumulative = 0.0
        known_drivers = set(driver_ids)
        for row in self.outcomes:
            if not set(row.driver_ids).issubset(known_drivers):
                raise ValueError("outcome contains an unknown driver")
            cumulative += row.probability
            if not math.isclose(row.cumulative_probability, cumulative, abs_tol=1e-12):
                raise ValueError("outcome cumulative probability is inconsistent")
        if not math.isclose(cumulative, diagnostics.returned_probability_sum, abs_tol=1e-12):
            raise ValueError("returned probability sum is inconsistent")

        expected_pair_count = min(10, math.comb(diagnostics.driver_count, 2))
        if len(self.co_podium_pairs) != expected_pair_count:
            raise ValueError("co-podium pair count is inconsistent")
        if [row.rank for row in self.co_podium_pairs] != list(range(1, expected_pair_count + 1)):
            raise ValueError("pair ranks must be complete")
        pair_probabilities = [row.probability for row in self.co_podium_pairs]
        if pair_probabilities != sorted(pair_probabilities, reverse=True):
            raise ValueError("pairs must be probability ordered")
        if len({row.driver_ids for row in self.co_podium_pairs}) != expected_pair_count:
            raise ValueError("pairs must be unique")
        if any(not set(row.driver_ids).issubset(known_drivers) for row in self.co_podium_pairs):
            raise ValueError("pair contains an unknown driver")
        return self


class PodiumOutcomeService:
    def __init__(self, predictor):
        self.predictor = predictor

    def derive(self, race_id: int, limit: int = 12) -> PodiumOutcomes:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 3 <= limit <= 25:
            raise PredictionUnavailable("Podium outcome limit must be between 3 and 25.")
        prediction = self.predictor.predict(race_id)
        rows = prediction["predictions"]
        driver_ids = [int(row["driver_id"]) for row in rows]
        released = [float(row["probability"]) for row in rows]
        fitted = fit_fixed_size_distribution(driver_ids, released)

        complete_outcomes = sorted(
            zip(fitted.driver_sets, fitted.probabilities, strict=True),
            key=lambda item: (-item[1], item[0]),
        )
        selected_outcomes = complete_outcomes[:limit]
        outcome_rows = []
        cumulative_probability = 0.0
        for rank, (driver_set, probability) in enumerate(selected_outcomes, start=1):
            cumulative_probability += probability
            outcome_rows.append(
                PodiumSetOutcome(
                    rank=rank,
                    driver_ids=driver_set,
                    probability=probability,
                    cumulative_probability=cumulative_probability,
                )
            )

        reconstructed_by_id = dict(
            zip(fitted.driver_ids, fitted.reconstructed_marginals, strict=True)
        )
        marginal_rows = tuple(
            DriverMarginal(
                driver_id=driver_id,
                forecast_rank=rank,
                released_probability=probability,
                reconstructed_probability=reconstructed_by_id[driver_id],
                absolute_error=abs(reconstructed_by_id[driver_id] - probability),
            )
            for rank, (driver_id, probability) in enumerate(
                zip(driver_ids, released, strict=True), start=1
            )
        )

        pair_probabilities = {pair: 0.0 for pair in combinations(fitted.driver_ids, 2)}
        for driver_set, probability in zip(fitted.driver_sets, fitted.probabilities, strict=True):
            for pair in combinations(driver_set, 2):
                pair_probabilities[pair] += probability
        selected_pairs = sorted(pair_probabilities.items(), key=lambda item: (-item[1], item[0]))[
            :10
        ]
        pair_rows = tuple(
            CoPodiumPair(rank=rank, driver_ids=pair, probability=probability)
            for rank, (pair, probability) in enumerate(selected_pairs, start=1)
        )

        probability_sum = math.fsum(fitted.probabilities)
        if math.isclose(probability_sum, 1, abs_tol=1e-12):
            probability_sum = 1.0
        reconstructed_sum = math.fsum(fitted.reconstructed_marginals)
        returned_sum = math.fsum(probability for _, probability in selected_outcomes)
        return PodiumOutcomes(
            schema_version="f1-podium-outcomes-v1",
            outcome_type="derived_unordered_podium_set_distribution",
            race_id=race_id,
            year=prediction["year"],
            experiment_id=prediction["experiment_id"],
            model_version=prediction["model_version"],
            diagnostics=OutcomeDiagnostics(
                method="maximum_entropy_fixed_size",
                driver_count=len(driver_ids),
                podium_size=3,
                combination_count=len(fitted.driver_sets),
                probability_sum=probability_sum,
                reconstructed_marginal_sum=reconstructed_sum,
                maximum_marginal_error=fitted.maximum_marginal_error,
                entropy_bits=fitted.entropy_bits,
                effective_outcome_count=2**fitted.entropy_bits,
                returned_outcome_count=len(selected_outcomes),
                returned_probability_sum=returned_sum,
            ),
            outcomes=tuple(outcome_rows),
            driver_marginals=marginal_rows,
            co_podium_pairs=pair_rows,
            evidence_boundary=PodiumOutcomeEvidenceBoundary(
                derived_from="released race-level marginal podium probabilities",
                outcome_data_used=False,
                separately_trained_joint_model=False,
                joint_forecast_validated=False,
                causal=False,
                ordering="unordered_podium_set",
                statement=(
                    "This maximum-entropy distribution is derived from released marginals; "
                    "it is not a separately trained or validated finishing-order forecast."
                ),
            ),
            notes=(
                "Every outcome contains three distinct drivers and the complete distribution sums to one.",
                "Driver marginals reconstruct the released race forecast within the reported numerical error.",
                "Podium sets are unordered; the result does not assign first, second, or third place.",
            ),
        )
