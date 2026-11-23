"""Metrics checked against values worked out by hand. Run: python -m pytest eval/ranking -q"""
import math

import pytest

import metrics

LABELS = {"a": 2, "b": 0, "c": 1, "d": 1}


def test_ndcg_linear_gain_matches_hand_calculation():
    # ideal order a,c,d = 2 + 1/log2(3) + 1/2; the system shows a,b,c = 2 + 0 + 1/2
    ideal = 2 + 1 / math.log2(3) + 0.5
    assert metrics.ndcg_at_k(["a", "b", "c"], LABELS, LABELS, k=3) == pytest.approx(2.5 / ideal)


def test_ndcg_exponential_gain_matches_hand_calculation():
    ideal = 3 + 1 / math.log2(3) + 0.5
    assert metrics.ndcg_at_k(["a", "b", "c"], LABELS, LABELS, k=3, gain="exponential") == pytest.approx(3.5 / ideal)


def test_a_perfect_ranking_scores_1_and_a_short_list_is_not_padded():
    assert metrics.ndcg_at_k(["a", "c", "d"], LABELS, LABELS, k=3) == pytest.approx(1.0)
    only_a = metrics.ndcg_at_k(["a"], LABELS, LABELS, k=3)
    assert only_a == pytest.approx(2 / (2 + 1 / math.log2(3) + 0.5))


def test_ndcg_is_undefined_when_nothing_in_the_pool_fits():
    assert metrics.ndcg_at_k(["b"], {"b": 0, "z": 0}, {"b": 0, "z": 0}) is None


def test_an_unlabelled_or_out_of_pool_job_is_an_error_not_a_zero():
    with pytest.raises(KeyError, match="not in the pool"):
        metrics.ndcg_at_k(["a", "x"], LABELS, LABELS)
    with pytest.raises(KeyError, match="unlabelled"):
        metrics.ndcg_at_k(["a"], {"a": 2}, {"a": 2, "q": 0})


def test_precision_counts_grade_1_and_2_and_empty_slots_are_misses():
    assert metrics.precision_at_k(["a", "b", "c"], LABELS, k=5) == pytest.approx(2 / 5)
    assert metrics.precision_at_k([], LABELS, k=5) == 0


def test_weighted_kappa_matches_hand_calculation():
    first, second = [0, 1, 2, 2], [0, 1, 2, 1]
    assert metrics.weighted_kappa(first, second, weights="linear") == pytest.approx(1 - 0.5 / 1.75)
    assert metrics.weighted_kappa(first, second, weights="quadratic") == pytest.approx(0.8)


def test_kappa_is_1_for_identical_ratings_and_below_0_for_opposed_ones():
    assert metrics.weighted_kappa([0, 1, 2, 1], [0, 1, 2, 1]) == pytest.approx(1.0)
    assert metrics.weighted_kappa([0, 2, 0, 2], [2, 0, 2, 0]) == pytest.approx(-1.0)


def test_kappa_is_undefined_when_both_raters_use_one_grade():
    assert metrics.weighted_kappa([1, 1, 1], [1, 1, 1]) is None


def test_bootstrap_of_a_constant_difference_has_no_spread():
    assert metrics.paired_bootstrap([0.1] * 16) == pytest.approx((0.1, 0.1, 0.1))


def test_bootstrap_interval_contains_the_mean_and_is_repeatable():
    diffs = [0.3, -0.1, 0.2, 0.0, 0.1, -0.2, 0.4, 0.05]
    mean, low, high = metrics.paired_bootstrap(diffs)
    assert low < mean < high
    assert (mean, low, high) == metrics.paired_bootstrap(diffs)


def test_cluster_bootstrap_resamples_whole_cvs_and_is_wider_for_correlated_pairs():
    # Each CV's two settings carry the same difference, so there are really 4 independent values, not 8.
    diffs = [0.4, 0.4, -0.2, -0.2, 0.1, 0.1, 0.3, 0.3]
    clusters = ["a", "a", "b", "b", "c", "c", "d", "d"]
    _, low_q, high_q = metrics.paired_bootstrap(diffs)
    _, low_c, high_c = metrics.paired_bootstrap(diffs, clusters=clusters)
    assert high_c - low_c > high_q - low_q


def test_wilson_interval_stays_inside_0_and_1_at_zero_failures():
    rate, low, high = metrics.wilson_interval(0, 100)
    assert rate == 0 and low == pytest.approx(0, abs=1e-12) and 0 < high < 0.05
    assert metrics.wilson_interval(0, 0) is None
