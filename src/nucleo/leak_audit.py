#!/usr/bin/env python3
"""Leakage audit between a training (calibration) set and a test set.

SI-generated (AI): Claude Code wrote this during the event (K1-en, ADR-0011); reviewed by the team.

What the project uses (ADR-0005 anti-leak rules):
  * ``Partition``            train / test (/ validation) POSITIONAL indices plus a description.
  * ``temporal_partition``   split rows by date windows: train = [train_from, train_to], test = [test_from, test_to].
  * ``audit_leak``           blocking findings when train and test share indices, identical content rows or groups;
                             a warning when train reaches into the test period. Same rules and verdict as the
                             pre-event development auditor used before K1-en: ``ok`` is False only on BLOCKING findings.
  * CLI                      audits the pre-registered design of config/validacion.yaml (calibration 2012-02 -> 2018-12
                             vs single test W2 2019-01 -> 2021-12, per country) on a MONTH table, plus the calibration
                             windows recorded in the frozen factor metadata. It reads no detection rows (no data >= 2019).

Usage:
  .venv/bin/python src/nucleo/leak_audit.py            # exit 0 = OK, 1 = blocking finding
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = ["Partition", "temporal_partition", "audit_leak", "audit_design"]

ROOT = Path(__file__).resolve().parents[2]
RESERVED_FROM = "2019-01-01"


@dataclass
class Partition:
    train: np.ndarray
    test: np.ndarray
    val: np.ndarray | None = None
    strategy: str = ""
    detail: str = ""

    def summary(self) -> dict:
        return {"strategy": self.strategy, "train": int(len(self.train)),
                "val": int(len(self.val)) if self.val is not None else 0, "test": int(len(self.test)),
                "detail": self.detail}


def temporal_partition(df: pd.DataFrame, time_col: str, train: tuple[str, str], test: tuple[str, str]) -> Partition:
    """Rows whose `time_col` falls in the closed windows `train` and `test` (ISO dates). Other rows are left out."""
    t = pd.to_datetime(df[time_col])
    idx = np.arange(len(df))
    m_tr = ((t >= pd.Timestamp(train[0])) & (t <= pd.Timestamp(train[1]))).to_numpy()
    m_te = ((t >= pd.Timestamp(test[0])) & (t <= pd.Timestamp(test[1]))).to_numpy()
    return Partition(idx[m_tr], idx[m_te], None, "temporal",
                     f"train {train[0]}..{train[1]}, test {test[0]}..{test[1]}")


def audit_leak(df: pd.DataFrame, p: Partition, group_col: str | None = None, time_col: str | None = None,
               content_cols: list[str] | None = None) -> dict:
    """Leakage findings between p.train and p.test. Returns {"ok", "findings", **p.summary()}.

    BLOCKING: shared positional indices; test rows identical (on `content_cols`, default all columns) to a train row;
              groups of `group_col` present on both sides.
    WARNING : the training period reaches the test period (`time_col`): acceptable only for interpolation tasks.
    """
    findings: list[str] = []
    tr, te = df.iloc[p.train], df.iloc[p.test]
    if len(np.intersect1d(p.train, p.test)):
        findings.append("BLOCKING: indices shared between train and test")
    cols = content_cols or list(df.columns)
    try:
        h_tr = pd.util.hash_pandas_object(tr[cols], index=False)
        h_te = pd.util.hash_pandas_object(te[cols], index=False)
        rep = int(h_te.isin(set(h_tr)).sum())
        if rep:
            findings.append(f"BLOCKING: {rep} test rows identical to train rows")
    except TypeError:
        pass
    if group_col:
        shared = set(tr[group_col]) & set(te[group_col])
        if shared:
            findings.append(f"BLOCKING: {len(shared)} groups of '{group_col}' appear in train and test")
    if time_col:
        numeric = pd.api.types.is_numeric_dtype(df[time_col])
        t_tr = tr[time_col] if numeric else pd.to_datetime(tr[time_col])
        t_te = te[time_col] if numeric else pd.to_datetime(te[time_col])
        if len(t_tr) and len(t_te) and t_tr.max() >= t_te.min():
            findings.append(f"WARNING: train reaches {t_tr.max()} and test starts {t_te.min()} (temporal overlap; "
                            "acceptable only for interpolation, not for forecasting)")
    return {"ok": not any(f.startswith("BLOCKING") for f in findings), "findings": findings, **p.summary()}


def _months(d0: str, d1: str) -> list[str]:
    return [str(x) for x in pd.period_range(d0[:7], d1[:7], freq="M")]


def audit_design(config_path: Path | None = None) -> dict:
    """Audit the pre-registered calibration/test design per country on a month table (reads no detections)."""
    import yaml

    cfg = yaml.safe_load(Path(config_path or ROOT / "config/validacion.yaml").read_text(encoding="utf-8"))
    mode = cfg["modos"]["prueba"]
    cal, ev = mode["calibracion"], mode["evaluacion"]
    out: dict = {"calibration": cal, "test": ev, "countries": {}, "factor_windows": {}}
    ok = True
    for country in cfg["paises"]:
        months = _months(cal[0], ev[1])
        if cfg.get("excluir_enero_2012", True):
            months = [m for m in months if m != "2012-01"]
        df = pd.DataFrame({"country": country, "month": pd.to_datetime([m + "-01" for m in months])})
        df["month_key"] = df["month"].dt.strftime("%Y-%m")
        p = temporal_partition(df, "month", (cal[0], cal[1]), (ev[0], ev[1]))
        rep = audit_leak(df, p, group_col="month_key", time_col="month", content_cols=["country", "month_key"])
        if pd.Timestamp(df.iloc[p.train]["month"].max()) >= pd.Timestamp(RESERVED_FROM):
            rep["findings"].append(f"BLOCKING: calibration reaches the reserved period (>= {RESERVED_FROM})")
            rep["ok"] = False
        out["countries"][country] = rep
        ok &= rep["ok"]
    # Frozen factor metadata: every calibration window must end before the reserved period.
    for meta in sorted((ROOT / "data/processed").glob("factores_*_*.json")):
        m = json.loads(meta.read_text())
        good = str(m.get("hasta", "9999")) < RESERVED_FROM
        out["factor_windows"][meta.name] = {"from": m.get("desde"), "to": m.get("hasta"), "ok": good}
        ok &= good
    out["ok"] = bool(ok)
    return out


def main() -> int:
    rep = audit_design(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(json.dumps(rep, indent=1, default=str))
    print("LEAK AUDIT:", "OK" if rep["ok"] else "BLOCKING FINDINGS")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
