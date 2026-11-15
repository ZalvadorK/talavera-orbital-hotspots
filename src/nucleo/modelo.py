#!/usr/bin/env python3
"""Method "B with clocks" (ADR-0003): stratified ratio shrunk per MODIS clock, with fallbacks R1 and G1.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Notation (per country):
  clock r in {TA, T, A}: MODIS predictor M_r = T+A, T or A.
  Calibration view of clock r: aggregate rows from the days on which that clock exists
      TA: Terra and Aqua available · T: Terra available · A: Aqua available   (availability table, global N=20)
  k_r(turno)        = sum S / sum M_r                                         (country x overpass level)
  k_r(mes, turno)   = (S_mt + n0k*k_r(turno)) / (M_mt + n0k),   n0k = 20      (shrinks month towards overpass)
  s_r(celda1,turno) = (S_c + n0s) / (sum k_r(mes,turno)*M_r + n0s)            (shrinks cell towards 1; n0s per country, LOYO)
  w_r(mes, turno, celda1) = k_r(mes, turno) * s_r(celda1, turno)             VIIRS-eq weight per MODIS detection
  (mes = month, turno = overpass D/N, celda1 = 1 deg cell)
R1 (per day): TA days -> w_TA to Terra and Aqua; Terra only -> w_T to Terra (Aqua does not exist); Aqua only -> w_A
to Aqua (detections of the platform flagged without data that day weigh 0); neither -> NaN (incomplete month).

I-03 intervals: leave-one-year-out residuals r = log1p(S) - log1p(S_hat), per clock x level x S_hat class
(quintiles of log1p(S_hat) at 1 deg and approximate AOI; a single class at country level). 80 % interval = [q10, q90].

The column names returned by metricas() and cobertura() are JSON keys of runs/EXP-001/EXP-002 metricas.json and stay
in Spanish (sesgo = bias, modelo = model, tercil bajo/medio/alto = low/medium/high tercile, cobertura = coverage).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

RELOJES = ("TA", "T", "A")
N0K = 20.0
N0S_GRID = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, math.inf)
TOL_N0 = 0.005          # relative tie: within 0.5 % of the minimum loss the largest (most shrunk) n0 is preferred
NIVELES = ("1deg", "pais", "aoi")
CLASES = {"1deg": 5, "pais": 1, "aoi": 5}
AOI_CELDAS05 = 3        # approximate AOI = tiles of 3x3 cells of 0.5 deg (1.5 deg)


# ------------------------------------------------------------------------------------------------ views
def vista_reloj(ag: pd.DataFrame, reloj: str) -> pd.DataFrame:
    """Calibration rows of the clock with its predictor M."""
    if reloj == "TA":
        m, M = ag["t_ok"] & ag["a_ok"], ag["T"] + ag["A"]
    elif reloj == "T":
        m, M = ag["t_ok"], ag["T"]
    elif reloj == "A":
        m, M = ag["a_ok"], ag["A"]
    else:
        raise ValueError(reloj)
    v = ag.loc[m, ["i05", "j05", "celda1", "anio", "mes", "ym", "turno", "S"]].copy()
    v["M"] = M[m].astype(float).values
    return v.reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ fit
@dataclass
class Ajuste:
    reloj: str
    n0s: float
    n0k: float
    kd: dict                      # turno -> k
    km: pd.DataFrame              # index (mes, turno): S, M, k
    sc: pd.DataFrame              # index (celda1, turno): S, M, Mhat, s
    extra: dict = field(default_factory=dict)

    def k(self, mes, turno) -> np.ndarray:
        idx = pd.MultiIndex.from_arrays([np.asarray(mes, int), np.asarray(turno)])
        kk = self.km["k"].reindex(idx).values
        falta = np.isnan(kk)
        if falta.any():
            kk[falta] = pd.Series(np.asarray(turno)[falta]).map(self.kd).values
        return kk

    def s(self, celda1, turno) -> np.ndarray:
        if math.isinf(self.n0s):
            return np.ones(len(celda1))
        idx = pd.MultiIndex.from_arrays([np.asarray(celda1), np.asarray(turno)])
        return np.nan_to_num(self.sc["s"].reindex(idx).values, nan=1.0)


def ajustar(v: pd.DataFrame, reloj: str, n0s: float, n0k: float = N0K) -> Ajuste:
    g = v.groupby("turno")[["S", "M"]].sum()
    kd = (g["S"] / g["M"].replace(0, np.nan)).to_dict()
    malla = pd.MultiIndex.from_product([range(1, 13), ["D", "N"]], names=["mes", "turno"])
    km = v.groupby(["mes", "turno"])[["S", "M"]].sum().reindex(malla, fill_value=0).astype(float)
    kdt = km.index.get_level_values("turno").map(kd).values.astype(float)
    km["k"] = (km["S"] + n0k * kdt) / (km["M"] + n0k)
    aj = Ajuste(reloj=reloj, n0s=n0s, n0k=n0k, kd=kd, km=km, sc=pd.DataFrame())
    mhat = aj.k(v["mes"].values, v["turno"].values) * v["M"].values
    sc = pd.DataFrame({"celda1": v["celda1"].values, "turno": v["turno"].values, "S": v["S"].values,
                       "M": v["M"].values, "Mhat": mhat}).groupby(["celda1", "turno"])[["S", "M", "Mhat"]].sum()
    sc["s"] = 1.0 if math.isinf(n0s) else (sc["S"] + n0s) / (sc["Mhat"] + n0s)
    aj.sc = sc
    return aj


def predecir(v: pd.DataFrame, aj: Ajuste) -> np.ndarray:
    return aj.k(v["mes"].values, v["turno"].values) * aj.s(v["celda1"].values, v["turno"].values) * v["M"].values


def predecir_r1(ag: pd.DataFrame, ajustes: dict[str, Ajuste]) -> np.ndarray:
    """VIIRS-eq prediction with the per-clock fallback (R1) on aggregate rows (with t_ok, a_ok, T, A)."""
    t, a = ag["t_ok"].values, ag["a_ok"].values
    mes, tu, c1 = ag["mes"].values, ag["turno"].values, ag["celda1"].values
    out = np.full(len(ag), np.nan)
    for r, sel, M in (("TA", t & a, ag["T"].values + ag["A"].values), ("T", t & ~a, ag["T"].values),
                      ("A", ~t & a, ag["A"].values)):
        if sel.any():
            aj = ajustes[r]
            out[sel] = aj.k(mes[sel], tu[sel]) * aj.s(c1[sel], tu[sel]) * M[sel]
    return out


# ------------------------------------------------------------------------------------------------ LOYO
def _agrega_nivel(df: pd.DataFrame, nivel: str) -> pd.DataFrame:
    if nivel == "1deg":
        keys = ["celda1", "ym"]
    elif nivel == "pais":
        keys = ["ym"]
    elif nivel == "aoi":
        df = df.assign(ti=df["i05"] // AOI_CELDAS05, tj=df["j05"] // AOI_CELDAS05)
        keys = ["ti", "tj", "ym"]
    else:
        raise ValueError(nivel)
    return df.groupby(keys)[["S", "P"]].sum().reset_index()


def loyo_predicciones(v: pd.DataFrame, reloj: str, n0s_lista) -> dict[float, pd.DataFrame]:
    """For each n0s: out-of-year predictions (each year predicted with the fit on the other years)."""
    out = {n: [] for n in n0s_lista}
    for y in sorted(v["anio"].unique()):
        tr, te = v[v["anio"] != y], v[v["anio"] == y]
        for n in n0s_lista:
            aj = ajustar(tr, reloj, n)
            out[n].append(te.assign(P=predecir(te, aj)))
    return {n: pd.concat(x, ignore_index=True) for n, x in out.items()}


def perdida(pred: pd.DataFrame) -> float:
    """n0 selection loss: MAE of log1p at 1 deg cell x month (units with S>0 or S_hat>0)."""
    g = _agrega_nivel(pred, "1deg")
    g = g[(g["S"] > 0) | (g["P"] > 0)]
    return float(np.abs(np.log1p(g["S"]) - np.log1p(g["P"])).mean())


def elegir_n0(v: pd.DataFrame, reloj: str = "TA", grid=N0S_GRID) -> tuple[float, pd.DataFrame]:
    preds = loyo_predicciones(v, reloj, grid)
    tabla = pd.DataFrame({"n0s": list(preds), "perdida_MAE_log1p_1deg": [perdida(p) for p in preds.values()]})
    mn = tabla["perdida_MAE_log1p_1deg"].min()
    ok = tabla[tabla["perdida_MAE_log1p_1deg"] <= mn * (1 + TOL_N0)]
    return float(ok["n0s"].max()), tabla


def residuos(pred: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    for nv in NIVELES:
        g = _agrega_nivel(pred, nv)
        g = g[g["P"] > 0]
        out[nv] = pd.DataFrame({"lp": np.log1p(g["P"].values),
                                "r": np.log1p(g["S"].values) - np.log1p(g["P"].values), "S": g["S"].values})
    return out


def tabla_intervalos(res: dict[str, pd.DataFrame]) -> dict:
    """Residual quantiles per level and S_hat class (log1p)."""
    out = {}
    for nv, rr in res.items():
        nc = CLASES[nv]
        cortes = np.unique(rr["lp"].quantile(np.linspace(0, 1, nc + 1)[1:-1]).values) if nc > 1 else np.array([])
        b = np.searchsorted(cortes, rr["lp"].values, side="right")
        clases = []
        for i in range(len(cortes) + 1):
            x = rr["r"].values[b == i]
            q = np.quantile(x, [0.05, 0.10, 0.50, 0.90, 0.95]) if len(x) else [np.nan] * 5
            clases.append({"n": int(len(x)), "q05": float(q[0]), "q10": float(q[1]), "q50": float(q[2]),
                           "q90": float(q[3]), "q95": float(q[4]),
                           "S_hat_min": float(np.expm1(rr["lp"].values[b == i].min())) if len(x) else None,
                           "S_hat_max": float(np.expm1(rr["lp"].values[b == i].max())) if len(x) else None})
        out[nv] = {"cortes_log1p_S_hat": [float(c) for c in cortes], "clases": clases}
    return out


def aplicar_intervalo(tab_nivel: dict, s_hat, q_lo: str = "q10", q_hi: str = "q90") -> tuple[np.ndarray, np.ndarray]:
    """ABSOLUTE interval [lo, hi] for S_hat (vectorised)."""
    s_hat = np.asarray(s_hat, float)
    lp = np.log1p(np.clip(s_hat, 0, None))
    b = np.searchsorted(np.asarray(tab_nivel["cortes_log1p_S_hat"]), lp, side="right")
    ql = np.array([c[q_lo] for c in tab_nivel["clases"]])[b]
    qh = np.array([c[q_hi] for c in tab_nivel["clases"]])[b]
    return np.clip(np.expm1(lp + ql), 0, None), np.expm1(lp + qh)


# ------------------------------------------------------------------------------------------------ metrics
def malla_chequeo(ag_all: pd.DataFrame, chk: pd.DataFrame, modelos: dict[str, np.ndarray]) -> pd.DataFrame:
    """0.5 deg cell x year-month (day+night) with zeros, for the country cells that appear in the aggregates."""
    d = chk[["i05", "j05", "celda1", "ym", "S"]].copy()
    for m, p in modelos.items():
        d[m] = p
    d = d.groupby(["i05", "j05", "celda1", "ym"], as_index=False).sum(min_count=1)
    celdas = ag_all[["i05", "j05", "celda1"]].drop_duplicates()
    yms = pd.DataFrame({"ym": sorted(chk["ym"].unique())})
    g = celdas.merge(yms, how="cross").merge(d, on=["i05", "j05", "celda1", "ym"], how="left")
    g["S"] = g["S"].fillna(0)
    for m in modelos:
        g[m] = g[m].fillna(0)
    return g


def metricas(cm: pd.DataFrame, modelos: list[str], semilla: int = 42, B: int = 1000) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    nac = cm.groupby("ym")[["S"] + modelos].sum()
    g1 = cm.groupby(["celda1", "ym"])[["S"] + modelos].sum().reset_index()
    g1["y"] = g1["ym"].str[:4]
    c1t = cm.groupby("celda1")[["S"] + modelos].sum()
    act = cm[cm["S"] > 0]
    ib_c = rng.integers(0, len(c1t), (B, len(c1t)))
    ib_m = rng.integers(0, len(nac), (B, len(nac)))
    filas = []
    ape_ref = None
    for mo in modelos:
        sp = [stats.spearmanr(g[mo], g["S"]).statistic for _, g in cm.groupby(["i05", "j05"])
              if g["S"].sum() >= 100 and g[mo].nunique() > 1]
        pk = [g.loc[g[mo].idxmax(), "ym"] == g.loc[g["S"].idxmax(), "ym"] for _, g in g1.groupby(["celda1", "y"])
              if g["S"].sum() >= 100]
        h1 = g1[g1["S"] >= 50]
        S_c, P_c = c1t["S"].values, c1t[mo].values
        sesgo_b = (P_c[ib_c].sum(1) / S_c[ib_c].sum(1) - 1) * 100
        ape = (np.abs(nac[mo] - nac["S"]) / nac["S"]).values
        mape_b = ape[ib_m].mean(1)
        terc = pd.qcut(g1.loc[g1[mo] > 0, mo], 3, labels=["bajo", "medio", "alto"])
        gt = g1.loc[g1[mo] > 0].assign(t=terc)
        st = gt.groupby("t", observed=True).apply(lambda x: x["S"].sum() / x[mo].sum() - 1, include_groups=False) * 100
        fila = {"modelo": mo,                                   # keys = JSON schema of metricas.json
                "sesgo total %": (P_c.sum() / S_c.sum() - 1) * 100,
                "IC95 sesgo % (boot celdas 1°)": f"{np.quantile(sesgo_b, .025):+.1f} – {np.quantile(sesgo_b, .975):+.1f}",
                "medAPE 1°×mes (S≥50)": float((np.abs(h1[mo] - h1["S"]) / h1["S"]).median()),
                "MAPE serie país": float(ape.mean()),
                "IC95 MAPE (boot meses)": f"{np.quantile(mape_b, .025):.3f} – {np.quantile(mape_b, .975):.3f}",
                "Spearman mediano 0.5°": float(np.nanmedian(sp)),
                "mes pico = S (1°×año)": float(np.mean(pk)),
                "MAE log1p 0.5°×mes (S>0)": float(np.abs(np.log1p(act[mo]) - np.log1p(act["S"])).mean()),
                "% S>0 con pred 0": float(((cm[mo] == 0) & (cm["S"] > 0)).sum() / (cm["S"] > 0).sum() * 100),
                "sesgo % por tercil de Ŝ 1°×mes (bajo/medio/alto)": " / ".join(f"{x:+.1f}" for x in st.values)}
        if ape_ref is None:
            ape_ref = ape
        else:
            d = (ape - ape_ref)[ib_m].mean(1)
            fila["ΔMAPE vs 1er modelo (IC95)"] = f"{(ape - ape_ref).mean():+.3f} ({np.quantile(d, .025):+.3f} – {np.quantile(d, .975):+.3f})"
        filas.append(fila)
    return pd.DataFrame(filas)


def cobertura(cm: pd.DataFrame, col: str, tab: dict, nivel: str) -> dict:
    """Coverage of the 80 % (and 90 %) interval in the check, counting units with S>0 (like SNDB Q3c) and with S_hat>0."""
    g = _agrega_nivel(cm.rename(columns={col: "P"})[["i05", "j05", "celda1", "ym", "S", "P"]], nivel)
    out = {"nivel": nivel, "unidades_chequeo": int(len(g))}
    for nom, ql, qh in (("80", "q10", "q90"), ("90", "q05", "q95")):
        lo, hi = aplicar_intervalo(tab[nivel], g["P"].values, ql, qh)
        dentro = (g["S"].values >= lo) & (g["S"].values <= hi)
        sp, pp = g["S"].values > 0, g["P"].values > 0
        out[f"cobertura_{nom}_S>0_%"] = float(dentro[sp].mean() * 100)
        out[f"cobertura_{nom}_Shat>0_%"] = float(dentro[pp].mean() * 100)
        sel = g["S"].values >= 20
        out[f"ancho_rel_{nom}_mediano_S>=20"] = float(np.median(((hi - lo) / np.clip(g["P"].values, 1e-9, None))[sel & pp]))
    return out


def fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        v = float(v)
        if not math.isfinite(v):
            return "∞" if v > 0 else "—"
        return f"{v:.3g}" if abs(v) < 1000 else f"{v:.0f}"
    return str(v)


def md(df: pd.DataFrame) -> str:
    if not len(df):
        return "_(no rows)_"
    cab = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    return "\n".join([cab, sep] + ["| " + " | ".join(fmt(x) for x in f) + " |" for f in df.itertuples(index=False)])
