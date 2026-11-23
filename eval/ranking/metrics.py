"""Ranking metrics for the evaluation. numpy and the standard library only.

nDCG gain: "linear" uses the grade itself (0, 1, 2) and is the headline; "exponential" uses 2**grade - 1 and is
reported as a sensitivity check. The proposal names neither, so the choice is stated wherever a number is shown.
"""
import math

import numpy as np


def dcg(grades, gain="linear"):
    weight = (lambda g: g) if gain == "linear" else (lambda g: 2 ** g - 1)
    return sum(weight(g) / math.log2(i + 2) for i, g in enumerate(grades))


def ndcg_at_k(ranked, labels, pool, k=5, gain="linear"):
    """nDCG@k of a ranked list of job ids. `labels` maps job id to grade; `pool` is every job whose grade can
    set the ideal ranking (the pooled top 7 of all systems). None when no pool job has a grade above 0.

    An unlabelled job in the top k is an error, never a silent 0: that would reward a system for being unrated."""
    top = ranked[:k]
    outside = [j for j in top if j not in pool]
    if outside:
        raise KeyError(f"jobs in the top {k} that are not in the pool: {outside}")
    unlabelled = [j for j in pool if j not in labels]
    if unlabelled:
        raise KeyError(f"unlabelled jobs in the pool: {unlabelled}")
    best = dcg(sorted((labels[j] for j in pool), reverse=True)[:k], gain)
    return None if best == 0 else dcg([labels[j] for j in top], gain) / best


def precision_at_k(ranked, labels, k=5):
    """Share of the k slots filled by a job graded 1 or 2. A list shorter than k counts its empty slots as misses."""
    return sum(labels[j] >= 1 for j in ranked[:k]) / k


def weighted_kappa(first, second, categories=(0, 1, 2), weights="quadratic"):
    """Weighted Cohen's kappa of two raters' grades for the same items. None when it is undefined
    (both raters used one single grade for everything)."""
    index = {c: i for i, c in enumerate(categories)}
    n = len(categories)
    observed = np.zeros((n, n))
    for a, b in zip(first, second):
        observed[index[a], index[b]] += 1
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / observed.sum()
    distance = np.abs(np.subtract.outer(np.arange(n), np.arange(n))) / (n - 1)
    penalty = distance ** 2 if weights == "quadratic" else distance
    if (penalty * expected).sum() == 0:
        return None
    return 1 - (penalty * observed).sum() / (penalty * expected).sum()


def paired_bootstrap(differences, clusters=None, resamples=10_000, seed=0, level=0.95):
    """Mean of paired differences with a percentile bootstrap interval, as (mean, low, high).

    With `clusters` (one label per difference, e.g. the CV), whole clusters are resampled instead of single
    queries, because the two preference settings of one CV share most of their results and are not independent."""
    differences = np.asarray(differences, dtype=float)
    rng = np.random.default_rng(seed)
    if clusters is None:
        draws = rng.integers(0, len(differences), size=(resamples, len(differences)))
        means = differences[draws].mean(axis=1)
    else:
        groups = [differences[[i for i, c in enumerate(clusters) if c == name]] for name in dict.fromkeys(clusters)]
        means = np.empty(resamples)
        for r in range(resamples):
            chosen = rng.integers(0, len(groups), size=len(groups))
            means[r] = np.concatenate([groups[g] for g in chosen]).mean()
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(means, [tail, 100 - tail])
    return float(differences.mean()), float(low), float(high)


def wilson_interval(successes, total, z=1.96):
    """95% Wilson score interval for a proportion, as (rate, low, high). A rate is a poor summary of 0 or 1 counts."""
    if total == 0:
        return None
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return p, centre - half, centre + half
