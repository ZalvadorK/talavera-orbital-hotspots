"""Baseline M1: global count ratio between two sensors, with a bootstrap confidence interval.

SI-generated (AI): Claude Code wrote this during the event (K1-en, ADR-0011); reviewed by the team.

This is the baseline every harmonisation result is compared against (ADR-0003 "A", ADR-0005 7d "M1"):

    ratio = sum(numerator) / sum(denominator)

e.g. numerator = S-NPP detections, denominator = Terra+Aqua detections of the same paired units (1-degree cells,
months, ...). The 95 % interval is a percentile bootstrap over the paired units: each replicate resamples the units
with replacement and recomputes the ratio of sums; replicates whose resampled denominator sums to 0 are skipped.

Determinism contract (the validation and EXP-001 depend on it): with the same inputs, n_boot and seed the result is
bit-identical to the pre-event development implementation used before K1-en (same generator, numpy
``default_rng(seed)``, same draw order ``integers(0, n, n)`` per replicate, same ``np.quantile`` default method).
"""
from __future__ import annotations

import numpy as np

__all__ = ["global_count_ratio", "apply_ratio"]


def global_count_ratio(numerator, denominator, n_boot: int = 2000, seed: int = 42) -> dict:
    """Global ratio sum(numerator) / sum(denominator) with a 95 % percentile bootstrap over paired units.

    numerator, denominator : array-likes of the same length (one entry per paired unit).
    n_boot                 : bootstrap replicates (default 2000).
    seed                   : seed of ``numpy.random.default_rng``.
    Returns {"ratio": float, "ci95": [lo, hi], "n": number of paired units}.
    """
    a = np.asarray(numerator, float)
    b = np.asarray(denominator, float)
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("numerator and denominator must be 1-D arrays of the same length")
    if len(a) == 0:
        raise ValueError("no paired units")
    rng = np.random.default_rng(seed)
    ratio = a.sum() / b.sum()
    reps = []
    for _ in range(n_boot):
        i = rng.integers(0, len(a), len(a))
        if b[i].sum() > 0:
            reps.append(a[i].sum() / b[i].sum())
    if not reps:
        raise ValueError("every bootstrap replicate had a zero denominator")
    return {"ratio": float(ratio), "ci95": [float(np.quantile(reps, .025)), float(np.quantile(reps, .975))],
            "n": int(len(a))}


def apply_ratio(ratio: float, denominator) -> np.ndarray:
    """Baseline prediction for new units: ratio x denominator (e.g. k x (Terra + Aqua))."""
    return float(ratio) * np.asarray(denominator, float)
