import pytest

from evals.suites.calibration import quadratic_weighted_kappa, spearman


def test_spearman_handles_ties_and_order() -> None:
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 2, 3], [5, 5, 6, 7]) == pytest.approx(1.0)


def test_qwk_perfect_and_opposite() -> None:
    assert quadratic_weighted_kappa([1, 2, 3], [1, 2, 3], 0, 4) == pytest.approx(1.0)
    assert quadratic_weighted_kappa([0, 4], [4, 0], 0, 4) < 0
