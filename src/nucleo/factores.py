#!/usr/bin/env python3
"""INTERFACE CONTRACT of the core (lane A): VIIRS-eq factors per MODIS clock, per-detection weights, intervals.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

API (fixed; used by the validation lane B and by src/exportar_demo.py):
  factores(pais, desde, hasta) -> DataFrame[reloj, mes, turno, celda1, k, s, w, n_cal]
  pesos_modis(det, F, disp)    -> np.ndarray of VIIRS-eq weights per MODIS detection (R1; NaN = day without MODIS)
  intervalo(pais, s_hat, tramo, nivel) -> multiplicative (lo, hi) of the 80 % interval
  disponibilidad(pais_o_global) -> DataFrame of data/processed/disponibilidad_plataforma_dia.csv

Definitions (ADR-0003 "B with clocks" + R1 + G1; ADR-0004 S1): see src/nucleo/modelo.py and docs/03-nucleo/metodo.md.
  reloj = clock (TA, T, A), mes = month, turno = overpass (D/N), celda1 = 1 deg cell.
  n_cal = MODIS detections of the clock in the calibration window inside the (celda1, turno) stratum that sets s.
  A celda1 that is not in F (no MODIS or S-NPP detections in the calibration) gets s = 1 (country factor).

ANTI-LEAK (ADR-0005): factores() requires hasta < 2019-01-01 (assert). Terra/Aqua/S-NPP rows >= 2019 are not read here.

The descriptive texts written into data/processed/factores_*.json and intervalos_*.json (keys and values) are kept
as they are, so that a regenerated file is identical to the one the validation and the app were built with.

Generate everything (with the memory lock):
  flock data/.pesado.lock .venv/bin/python src/nucleo/factores.py --generar
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import agregados as AG
    from . import modelo as MO
except ImportError:  # run as a script or with src/nucleo on sys.path
    import agregados as AG  # type: ignore
    import modelo as MO  # type: ignore

RAIZ = Path(__file__).resolve().parents[2]
PROC = RAIZ / "data/processed"
PAISES = AG.PAISES
FECHA_RESERVA = "2019-01-01"
FINAL = ("2012-02-01", "2018-12-31")
DESARROLLO = ("2012-02-01", "2015-12-31")
COLUMNAS = ["reloj", "mes", "turno", "celda1", "k", "s", "w", "n_cal"]
MARCA_SI = "SI-generated (AI): Claude Code wrote the code that produced this file during the event; reviewed by the team."


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ruta_factores(pais: str, desde: str, hasta: str) -> Path:
    return PROC / f"factores_{pais}_{desde}_{hasta}.parquet"


def ruta_intervalos(pais: str, desde: str = FINAL[0], hasta: str = FINAL[1]) -> Path:
    if (desde, hasta) == FINAL:
        return PROC / f"intervalos_{pais}.json"
    return PROC / f"intervalos_{pais}_{desde}_{hasta}.json"


# ------------------------------------------------------------------------------------------------ calibration
def calibrar(pais: str, desde: str, hasta: str, forzar: bool = False, n0s: float | None = None) -> dict:
    """Calibrates one country on [desde, hasta]: n0s by LOYO (G1), k and s per clock, LOYO intervals. Writes the cache."""
    assert pais in PAISES, pais
    assert hasta < FECHA_RESERVA, f"LEAK: hasta={hasta} >= {FECHA_RESERVA} (ADR-0005)"
    rf = ruta_factores(pais, desde, hasta)
    rj = rf.with_suffix(".json")
    ri = ruta_intervalos(pais, desde, hasta)
    if not forzar and rf.exists() and rj.exists() and ri.exists() and n0s is None:
        return {"F": pd.read_parquet(rf), "meta": json.loads(rj.read_text()), "intervalos": json.loads(ri.read_text())}
    ag = AG.calcular(pais, desde, hasta, cache=True)
    assert pd.Timestamp(ag["dmax"].max()) < pd.Timestamp(FECHA_RESERVA), "LEAK in aggregates"
    vistas = {r: MO.vista_reloj(ag, r) for r in MO.RELOJES}
    if n0s is None:
        n0s, curva = MO.elegir_n0(vistas["TA"], "TA")
        curvas = {"TA": curva}
        for r in ("T", "A"):   # informative: does not change n0 (ADR-0003: one n0 per country)
            curvas[r] = MO.elegir_n0(vistas[r], r)[1]
    else:
        curvas = {}
    ajustes = {r: MO.ajustar(vistas[r], r, n0s) for r in MO.RELOJES}
    filas = []
    for r, aj in ajustes.items():
        km = aj.km.reset_index()[["mes", "turno", "k"]]
        sc = aj.sc.reset_index()
        sc["s"] = 1.0 if math.isinf(n0s) else sc["s"]
        f = km.merge(sc[["celda1", "turno", "s", "M"]], on="turno", how="inner")
        f["reloj"] = r
        f["w"] = f["k"] * f["s"]
        f["n_cal"] = f["M"].round().astype("int64")
        filas.append(f[COLUMNAS])
    F = pd.concat(filas, ignore_index=True)
    F["mes"] = F["mes"].astype("int64")
    # I-03 intervals: LOYO residuals with the chosen n0, per clock x level x S_hat class
    # (the texts below are the content of data/processed/intervalos_*.json and factores_*.json: kept unchanged)
    tab = {}
    for r in MO.RELOJES:
        pred = MO.loyo_predicciones(vistas[r], r, [n0s])[n0s]
        tab[r] = MO.tabla_intervalos(MO.residuos(pred))
    tab_alias = dict(tab)
    intervalos = {"pais": pais, "ventana_calibracion": [desde, hasta], "n0s": n0s, "nivel_nominal": 0.80,
                  "residuo": "log1p(S) - log1p(S_hat), S = S-NPP, S_hat = predicción LOYO del reloj",
                  "niveles": {"1deg": "celda 1° × mes (día+noche)", "pais": "país × mes",
                              "aoi": f"AOI aproximada = tesela {MO.AOI_CELDAS05 * 0.5}° × mes"},
                  "clases": "cuantiles de log1p(S_hat) (quintiles en 1deg y aoi; una clase en pais)",
                  "relojes": tab_alias, "marca_si": MARCA_SI,
                  "uso": "intervalo absoluto = [expm1(log1p(S_hat)+q10), expm1(log1p(S_hat)+q90)]"}
    meta = {"pais": pais, "desde": desde, "hasta": hasta, "n0k": MO.N0K, "n0s": n0s,
            "criterio_n0": "min MAE log1p a celda 1°×mes, LOYO dentro de la ventana; empate ±0.5 % → n0 mayor",
            "curvas_loyo": {r: c.replace({math.inf: "inf"}).to_dict(orient="records") for r, c in curvas.items()},
            "k_turno": {r: aj.kd for r, aj in ajustes.items()},
            "S_cal": {r: int(vistas[r]["S"].sum()) for r in MO.RELOJES},
            "M_cal": {r: int(vistas[r]["M"].sum()) for r in MO.RELOJES},
            "entradas": {str(AG.ruta_deteccion(pais).relative_to(RAIZ)): _sha(AG.ruta_deteccion(pais)),
                         str(AG.DISP.relative_to(RAIZ)): _sha(AG.DISP)},
            "fecha_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "marca_si": MARCA_SI}
    F.to_parquet(rf, index=False)
    rj.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str))
    ri.write_text(json.dumps(intervalos, indent=2, ensure_ascii=False, default=str))
    if (desde, hasta) == FINAL:
        F.to_parquet(PROC / f"factores_{pais}.parquet", index=False)
    return {"F": F, "meta": meta, "intervalos": intervalos, "ajustes": ajustes, "agregados": ag}


# ------------------------------------------------------------------------------------------------ CONTRACT
def factores(pais: str, desde: str, hasta: str) -> pd.DataFrame:
    """k, s and w = k*s per (reloj, mes, turno, celda1). Cached in data/processed/factores_<pais>_<desde>_<hasta>.parquet."""
    assert hasta < FECHA_RESERVA, f"LEAK: hasta={hasta} >= {FECHA_RESERVA} (ADR-0005)"
    return calibrar(pais, desde, hasta)["F"][COLUMNAS].copy()


def disponibilidad(pais_o_global: str = "global") -> pd.DataFrame:
    """Table disponibilidad_plataforma_dia (global MX+AR rule, N=20 + notices). With a country it adds that country's n column."""
    d = AG.disponibilidad_global()
    if pais_o_global in ("mexico", "argentina"):
        d = d.assign(n=d["n_mx"] if pais_o_global == "mexico" else d["n_ar"])
    elif pais_o_global != "global":
        raise ValueError(pais_o_global)
    return d


def relojes_dia(fechas, disp: pd.DataFrame, fuera_cobertura: str = "error") -> pd.DataFrame:
    """Per date: t_ok, a_ok and clock ('TA'|'T'|'A'|None). A platform without a row in the table is not available.

    fuera_cobertura: what to do with dates outside the table range ('error' | 'disponible'). 'disponible' assumes the
    platforms in orbit are available (Terra from 2000-02-24, Aqua from 2002-07-04); use it only with the extended
    table or declaring it."""
    d = disp.copy()
    d["fecha"] = pd.to_datetime(d["fecha"]).dt.date
    sd = d["sin_datos"].astype(str).str.lower().eq("true")
    t_ok = d[(d["plataforma"] == "Terra") & ~sd].groupby("fecha").size().gt(0)
    a_ok = d[(d["plataforma"] == "Aqua") & ~sd].groupby("fecha").size().gt(0)
    f = pd.Series(pd.to_datetime(pd.Series(fechas)).dt.date.unique())
    out = pd.DataFrame({"fecha": f})
    out["t_ok"] = out["fecha"].map(t_ok).fillna(False).astype(bool)
    out["a_ok"] = out["fecha"].map(a_ok).fillna(False).astype(bool)
    fmin, fmax = d["fecha"].min(), d["fecha"].max()
    fuera = (out["fecha"] < fmin) | (out["fecha"] > fmax)
    if fuera.any():
        if fuera_cobertura == "error":
            raise ValueError(f"{int(fuera.sum())} dates outside the availability table [{fmin}, {fmax}] "
                             f"(e.g. {out.loc[fuera, 'fecha'].iloc[0]}); extend the table or use fuera_cobertura='disponible'")
        out.loc[fuera, "t_ok"] = out.loc[fuera, "fecha"] >= dt.date(2000, 2, 24)
        out.loc[fuera, "a_ok"] = out.loc[fuera, "fecha"] >= dt.date(2002, 7, 4)
    out["reloj"] = np.select([out.t_ok & out.a_ok, out.t_ok, out.a_ok], ["TA", "T", "A"], default=None)
    return out


def pesos_modis(det: pd.DataFrame, F: pd.DataFrame, disp: pd.DataFrame, fuera_cobertura: str = "error") -> np.ndarray:
    """VIIRS-eq weight of each MODIS detection (R1).

    Day with Terra and Aqua -> w('TA'); day with only one -> w('T') or w('A') for that platform and 0 for the platform
    flagged without data (if it had rows); day with neither -> NaN (the month is flagged incomplete). Cell without a
    factor -> s=1.
    """
    req = {"plataforma", "acq_date_utc", "mes", "turno", "celda1"}
    falta = req - set(det.columns)
    if falta:
        raise ValueError(f"missing columns in det: {sorted(falta)}")
    if len(det) == 0:
        return np.zeros(0)
    plat = det["plataforma"].astype(str).values
    if not np.isin(plat, ["Terra", "Aqua"]).all():
        raise ValueError("pesos_modis only accepts Terra/Aqua detections")
    fechas = pd.to_datetime(det["acq_date_utc"]).dt.date.values
    rd = relojes_dia(fechas, disp, fuera_cobertura).set_index("fecha")
    t_ok = rd["t_ok"].reindex(fechas).values.astype(bool)
    a_ok = rd["a_ok"].reindex(fechas).values.astype(bool)
    reloj = np.select([t_ok & a_ok, t_ok, a_ok], ["TA", "T", "A"], default="")
    k = (F.groupby(["reloj", "mes", "turno"])["k"].first())
    s = F.set_index(["reloj", "celda1", "turno"])["s"]
    s = s[~s.index.duplicated()]
    mes = det["mes"].astype(int).values
    tu = det["turno"].astype(str).values
    c1 = det["celda1"].astype(str).values
    kk = k.reindex(pd.MultiIndex.from_arrays([reloj, mes, tu])).values.astype(float)
    ss = np.nan_to_num(s.reindex(pd.MultiIndex.from_arrays([reloj, c1, tu])).values.astype(float), nan=1.0)
    w = kk * ss
    plat_ok = np.where(plat == "Terra", t_ok, a_ok)
    w = np.where(reloj == "", np.nan, np.where(plat_ok, w, 0.0))
    return w


def _tabla(pais: str, ventana: tuple[str, str] = FINAL) -> dict:
    return json.loads(ruta_intervalos(pais, *ventana).read_text())


def intervalo(pais: str, s_hat: float, tramo: str, nivel: str, *, nominal: str = "80",
              ventana: tuple[str, str] = FINAL) -> tuple[float, float]:
    """MULTIPLICATIVE (lo, hi) of the 80 % interval for a VIIRS-eq S_hat: the absolute interval is (S_hat*lo, S_hat*hi).

    tramo (era) 'TA' (Terra+Aqua) or 'T' (Terra only); 'A' is also accepted. nivel (level) '1deg' | 'pais' | 'aoi'.
    S_hat <= 0 -> (0, inf): the method cannot bound months without MODIS detections (loss where MODIS saw 0).
    ventana: the final calibration by default; DESARROLLO = intervals from LOYO residuals of 2012-02 -> 2015-12.
    """
    if tramo not in ("TA", "T", "A") or nivel not in MO.NIVELES:
        raise ValueError((tramo, nivel))
    s_hat = float(s_hat)
    if not s_hat > 0:
        return 0.0, math.inf
    tab = _tabla(pais, ventana)["relojes"][tramo][nivel]
    ql, qh = {"80": ("q10", "q90"), "90": ("q05", "q95")}[nominal]
    lo, hi = MO.aplicar_intervalo(tab, [s_hat], ql, qh)
    return float(lo[0] / s_hat), float(hi[0] / s_hat)


# ------------------------------------------------------------------------------------------------ CLI
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generar", action="store_true", help="FINAL and DESARROLLO (development) factors and intervals for both countries")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    if a.generar:
        for pais in PAISES:
            for desde, hasta in (FINAL, DESARROLLO):
                r = calibrar(pais, desde, hasta, forzar=a.forzar)
                print(pais, desde, hasta, "n0s =", r["meta"]["n0s"], "rows F =", len(r["F"]))


if __name__ == "__main__":
    main()
