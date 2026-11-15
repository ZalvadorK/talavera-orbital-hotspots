"""Trend and change-point statistics used by the validation (C-V check and S8).

SI-generated (AI): Claude Code wrote this during the event (K1-en, ADR-0011); reviewed by the team.

  pettitt(x)                         Pettitt (1979) change point in the mean, approximate p-value.
                                     Bit-identical to the pre-event development implementation used before K1-en.
  sen_slope(y, t)                    Theil-Sen slope: median of pairwise slopes (y_j - y_i) / (t_j - t_i), t_i < t_j.
  seasonal_sen_slope(y, year, month) Seasonal Sen slope (Hirsch et al. 1982): median of the pairwise slopes computed
                                     only between the SAME calendar month of different years (units: per year).
                                     It removes the seasonal cycle without estimating it. NaN values are skipped.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = ["pettitt", "sen_slope", "seasonal_pairwise_slopes", "seasonal_sen_slope"]


def pettitt(x) -> dict:
    """Change point in the mean (Pettitt 1979). Non-finite values are dropped. Approximate p-value."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    r = stats.rankdata(x)
    u = 2 * np.cumsum(r) - np.arange(1, n + 1) * (n + 1)
    k = int(np.argmax(np.abs(u)))
    K = float(np.abs(u[k]))
    p = float(min(1.0, 2 * np.exp(-6 * K ** 2 / (n ** 3 + n ** 2))))
    return {"change_index": k, "K": K, "p": p, "mean_before": float(x[:k + 1].mean()),
            "mean_after": float(x[k + 1:].mean()) if k + 1 < n else float("nan")}


def sen_slope(y, t=None) -> float:
    """Theil-Sen slope; NaN pairs are skipped. NaN if there is no valid pair."""
    y = np.asarray(y, float)
    t = np.arange(len(y), dtype=float) if t is None else np.asarray(t, float)
    i, j = np.triu_indices(len(y), k=1)
    dt = t[j] - t[i]
    s = (y[j] - y[i]) / np.where(dt != 0, dt, np.nan)
    s = s[np.isfinite(s)]
    return float(np.median(s)) if len(s) else float("nan")


def seasonal_pairwise_slopes(y, year, month) -> np.ndarray:
    """All slopes (y_j - y_i) / (year_j - year_i) between the same calendar month of different years."""
    y, year, month = np.asarray(y, float), np.asarray(year, float), np.asarray(month)
    out = []
    for m in np.unique(month):
        sel = month == m
        yy, tt = y[sel], year[sel]
        if len(yy) < 2:
            continue
        i, j = np.triu_indices(len(yy), k=1)
        dt = tt[j] - tt[i]
        s = (yy[j] - yy[i]) / np.where(dt != 0, dt, np.nan)
        out.append(s[np.isfinite(s)])
    return np.concatenate(out) if out else np.zeros(0)


def seasonal_sen_slope(y, year, month) -> tuple[float, int]:
    """(seasonal Sen slope per year, number of valid same-month pairs). Slope is NaN without valid pairs."""
    s = seasonal_pairwise_slopes(y, year, month)
    return (float(np.median(s)) if len(s) else float("nan")), int(len(s))
