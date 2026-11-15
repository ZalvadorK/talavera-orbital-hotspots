#!/usr/bin/env python3
"""Per-country calibration aggregates (ADR-0003 "B with clocks", ADR-0004 S1/T1/F1/C1).

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

What it does: counts S-NPP (S), Terra (T) and Aqua (A) detections from the country's analytic table
(data/processed/deteccion_<pais>.parquet) by

    0.5 deg cell (i05, j05 = floor(lat/0.5), floor(lon/0.5))  ->  celda1 (1 deg floor, "lat_lon")
  x year-month (UTC date) x overpass (D/N)
  x day availability (t_ok, a_ok) from data/processed/disponibilidad_plataforma_dia.csv (rule R1)

Filters (ADR-0002/0003): en_calibracion, NOT en_mascara, procesamiento='estandar', platforms Terra/Aqua/S-NPP,
date in [desde, hasta]. The 0.5 deg cell is finer than the calibration cell (1 deg): it is kept for the internal-check
metrics (Spearman at 0.5 deg, approximate 1.5 deg AOIs) and aggregated to 1 deg without loss.

ANTI-LEAK (ADR-0005): `hasta` < 2019-01-01 by assert, plus another assert on the maximum date read.
Memory: DuckDB with memory_limit 600MB, threads 2; only the aggregate (~10^5 rows) is pulled into pandas.

Usage (with the memory lock):
  flock data/.pesado.lock .venv/bin/python src/nucleo/agregados.py --pais mexico
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
PROC = RAIZ / "data/processed"
DISP = PROC / "disponibilidad_plataforma_dia.csv"
PAISES = ("mexico", "argentina")
FECHA_RESERVA = "2019-01-01"
CAL_DESDE, CAL_HASTA = "2012-02-01", "2018-12-31"


def ruta_deteccion(pais: str) -> Path:
    assert pais in PAISES, pais
    return PROC / f"deteccion_{pais}.parquet"


def ruta_cache(pais: str, desde: str, hasta: str) -> Path:
    return PROC / f"factores_agregados_{pais}_{desde}_{hasta}.parquet"


def conectar() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false")
    tmp = RAIZ / "data/.duckdb_tmp_nucleo"
    tmp.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{tmp}'")
    return con


def disponibilidad_global() -> pd.DataFrame:
    """Availability table (global MX+AR, ADR-0003 rule N=20 + official notices)."""
    d = pd.read_csv(DISP, dtype={"plataforma": str, "fuente": str})
    d["fecha"] = pd.to_datetime(d["fecha"]).dt.date
    d["sin_datos"] = d["sin_datos"].astype(str).str.lower().eq("true")
    return d


def calcular(pais: str, desde: str = CAL_DESDE, hasta: str = CAL_HASTA, cache: bool = True) -> pd.DataFrame:
    assert pais in PAISES, pais
    assert hasta < FECHA_RESERVA, f"LEAK: hasta={hasta} >= {FECHA_RESERVA} (ADR-0005)"
    assert desde >= CAL_DESDE, f"desde={desde} is before the calibration start {CAL_DESDE}"
    rc = ruta_cache(pais, desde, hasta)
    if cache and rc.exists():
        ag = pd.read_parquet(rc)
        _verificar(ag, hasta)
        return ag
    con = conectar()
    disp = disponibilidad_global()
    con.register("disp_df", disp)
    con.execute("""CREATE TEMP TABLE dd AS
        SELECT fecha,
               bool_or(plataforma='Terra' AND NOT sin_datos) AS t_ok,
               bool_or(plataforma='Aqua'  AND NOT sin_datos) AS a_ok
        FROM disp_df GROUP BY fecha""")
    q = f"""
        WITH b AS (
          SELECT plataforma p, acq_date_utc d, turno, celda1,
                 CAST(floor(latitude/0.5) AS INT) i05, CAST(floor(longitude/0.5) AS INT) j05
          FROM read_parquet('{ruta_deteccion(pais)}')
          WHERE en_calibracion AND NOT en_mascara AND procesamiento='estandar'
            AND NOT reservado_prueba
            AND plataforma IN ('Terra','Aqua','S-NPP')
            AND acq_date_utc BETWEEN DATE '{desde}' AND DATE '{hasta}')
        SELECT b.i05, b.j05, b.celda1, CAST(year(b.d) AS INT) anio, CAST(month(b.d) AS INT) mes, b.turno,
               coalesce(dd.t_ok, false) t_ok, coalesce(dd.a_ok, false) a_ok,
               count(*) FILTER (WHERE p='S-NPP') S, count(*) FILTER (WHERE p='Terra') T,
               count(*) FILTER (WHERE p='Aqua') A, max(b.d) dmax, count(DISTINCT b.d) FILTER (WHERE dd.fecha IS NULL) dias_sin_disp
        FROM b LEFT JOIN dd ON dd.fecha = b.d
        GROUP BY ALL"""
    ag = con.execute(q).df()
    con.close()
    assert int(ag["dias_sin_disp"].sum()) == 0, "some calibration dates have no row in the availability table"
    ag["dmax"] = pd.to_datetime(ag["dmax"])
    _verificar(ag, hasta)
    ag = ag.drop(columns=["dias_sin_disp"])
    for c in ("S", "T", "A"):
        ag[c] = ag[c].astype("int64")
    ag["ym"] = ag["anio"].astype(str) + "-" + ag["mes"].astype(str).str.zfill(2)
    ag = ag.sort_values(["anio", "mes", "i05", "j05", "turno"]).reset_index(drop=True)
    if cache:
        ag.to_parquet(rc, index=False)
    return ag


def _verificar(ag: pd.DataFrame, hasta: str) -> None:
    mx = pd.Timestamp(ag["dmax"].max()).date()
    assert mx <= dt.date.fromisoformat(hasta), f"date {mx} > hasta {hasta}"
    assert mx < dt.date(2019, 1, 1), f"LEAK: date {mx} >= 2019-01-01 in calibration aggregates"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pais", choices=PAISES, required=True)
    ap.add_argument("--desde", default=CAL_DESDE)
    ap.add_argument("--hasta", default=CAL_HASTA)
    a = ap.parse_args()
    ag = calcular(a.pais, a.desde, a.hasta, cache=True)
    print(a.pais, len(ag), "rows;", ag[["S", "T", "A"]].sum().to_dict(),
          "cell-days by clock:", ag.groupby(["t_ok", "a_ok"])[["S", "T", "A"]].sum().to_dict())


if __name__ == "__main__":
    main()
