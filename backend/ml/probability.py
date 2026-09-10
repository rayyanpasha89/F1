"""Outcome-free probability coherence for a race with a fixed podium count."""

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.special import expit, logit


@dataclass(frozen=True)
class ProbabilityProjection:
    adjusted: np.ndarray
    log_odds_offset: float
    raw_sum: float
    adjusted_sum: float
    expected_count: int


def project_expected_count(
    probabilities: Sequence[float] | np.ndarray, expected_count: int = 3
) -> ProbabilityProjection:
    """Shift every logit equally so the marginal probabilities sum to a known count."""

    raw = np.asarray(probabilities, dtype=float)
    if raw.ndim != 1 or raw.size < 2:
        raise ValueError("Probabilities must be a one-dimensional field with at least two entries.")
    if type(expected_count) is not int or not 0 < expected_count < raw.size:
        raise ValueError("Expected count must be a positive integer below the number of entries.")
    if not np.isfinite(raw).all() or ((raw < 0) | (raw > 1)).any():
        raise ValueError("Probabilities must be finite values between zero and one.")

    epsilon = np.finfo(float).eps
    logits = logit(np.clip(raw, epsilon, 1 - epsilon))
    lower, upper = -80.0, 80.0
    for _ in range(100):
        midpoint = (lower + upper) / 2
        if float(expit(logits + midpoint).sum()) > expected_count:
            upper = midpoint
        else:
            lower = midpoint
    offset = (lower + upper) / 2
    adjusted = np.asarray(expit(logits + offset), dtype=float)
    adjusted.setflags(write=False)
    return ProbabilityProjection(
        adjusted=adjusted,
        log_odds_offset=float(offset),
        raw_sum=float(raw.sum()),
        adjusted_sum=float(adjusted.sum()),
        expected_count=expected_count,
    )
