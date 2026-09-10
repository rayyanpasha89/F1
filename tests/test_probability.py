import numpy as np
import pytest

from backend.ml.probability import project_expected_count


def test_projection_is_deterministic_bounded_and_preserves_order():
    raw = np.array([0.82, 0.55, 0.28, 0.11, 0.03])

    first = project_expected_count(raw, expected_count=3)
    second = project_expected_count(raw.tolist(), expected_count=3)

    np.testing.assert_array_equal(first.adjusted, second.adjusted)
    assert np.isfinite(first.adjusted).all()
    assert ((first.adjusted > 0) & (first.adjusted < 1)).all()
    assert abs(first.adjusted.sum() - 3) < 1e-10
    assert first.raw_sum == pytest.approx(raw.sum())
    assert first.adjusted_sum == pytest.approx(3, abs=1e-10)
    assert first.expected_count == 3
    assert not first.adjusted.flags.writeable
    assert np.array_equal(
        np.argsort(-raw, kind="stable"), np.argsort(-first.adjusted, kind="stable")
    )


def test_projection_treats_equal_probabilities_symmetrically():
    result = project_expected_count([0.2] * 6, expected_count=3)

    np.testing.assert_allclose(result.adjusted, [0.5] * 6, atol=1e-12)
    assert result.log_odds_offset > 0


def test_projection_is_effectively_a_no_op_when_sum_is_already_correct():
    raw = np.array([0.8, 0.7, 0.6, 0.5, 0.3, 0.1])

    result = project_expected_count(raw, expected_count=3)

    np.testing.assert_allclose(result.adjusted, raw, atol=1e-12)
    assert result.log_odds_offset == pytest.approx(0, abs=1e-12)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([0.2, 0.3], 3),
        ([0.2, 0.3, 0.4], 0),
        ([0.2, 0.3, 0.4], 3),
        ([0.2, 0.3, 0.4], True),
        ([0.2, 0.3, 0.4, 0.5], 3.0),
        ([0.2, float("nan"), 0.4, 0.5], 3),
        ([-0.1, 0.3, 0.4, 0.5], 3),
        ([0.1, 0.3, 1.1, 0.5], 3),
    ],
)
def test_projection_rejects_invalid_inputs(values, expected):
    with pytest.raises(ValueError):
        project_expected_count(values, expected_count=expected)
