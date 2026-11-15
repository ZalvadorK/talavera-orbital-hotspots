#!/usr/bin/env python3
"""Build the intermediate FIRMS table (D1: raw columns + normalized names + flags; no rows deleted).

Input : data/raw/firms/country/<sensor>/<year>/<sensor>_<year>_<Country>.csv  (descargar_firms.py)
Output: data/interim/firms/firms_<country>.parquet   (schema: SOLICITUD_RETO_HOTSPOTS.md §6)

Every CSV column is read as text first (acq_time keeps its leading zeros), then typed.
Flags only mark rows (decision D2-S-04 is Salvador's); nothing is filtered out.
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
PLATAFORMA_POR_SENSOR = {"viirs-snpp": "S-NPP", "viirs-jpss1": "NOAA-20", "viirs-jpss2": "NOAA-21"}


def sql_sensor(sensor: str, patron: str) -> str:
    viirs = sensor.startswith("viirs")
    b1, b2 = ("bright_ti4", "bright_ti5") if viirs else ("brightness", "bright_t31")
    if viirs:
        plataforma = f"'{PLATAFORMA_POR_SENSOR[sensor]}'"
    else:
        plataforma = "CASE WHEN upper(satellite) IN ('TERRA','T') THEN 'Terra' ELSE 'Aqua' END"
    return f"""
    SELECT
      '{sensor}'                                   AS fuente,
      '{'VIIRS' if viirs else 'MODIS'}'            AS familia,
      {plataforma}                                 AS plataforma,
      satellite                                    AS satellite_raw,
      instrument                                   AS instrument_raw,
      CASE WHEN upper(version) LIKE '%NRT%' THEN 'NRT' ELSE 'estandar' END AS procesamiento,
      version,
      CAST(latitude AS DOUBLE)                     AS latitude,
      CAST(longitude AS DOUBLE)                    AS longitude,
      strptime(acq_date || ' ' || lpad(acq_time, 4, '0'), '%Y-%m-%d %H%M') AS acq_datetime_utc,
      CAST(acq_date AS DATE)                       AS acq_date_utc,
      daynight,
      confidence                                   AS confidence_raw,
      TRY_CAST(frp AS DOUBLE)                      AS frp,
      TRY_CAST(scan AS DOUBLE)                     AS scan,
      TRY_CAST(track AS DOUBLE)                    AS track,
      TRY_CAST({b1} AS DOUBLE)                     AS bright_1,
      TRY_CAST({b2} AS DOUBLE)                     AS bright_2,
      '{b1}'                                       AS bright_1_nombre,
      '{b2}'                                       AS bright_2_nombre,
      TRY_CAST(NULLIF(type, '') AS INTEGER)        AS type,
      (type IS NULL OR type = '')                  AS flag_type_ausente,
      (upper(version) LIKE '%NRT%')                AS flag_nrt,
      (CAST(acq_date AS DATE) < DATE '2000-12-01') AS flag_pre_dic2000,
      regexp_extract(filename, '[^/]+$')           AS archivo_origen,
      'resumen_pais'                               AS ruta_acceso
    FROM read_csv('{patron}', header=true, all_varchar=true, filename=true, union_by_name=true)
    """


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pais", default="Mexico")
    a = ap.parse_args(argv)
    base = RAIZ / "data" / "raw" / "firms" / "country"
    salida = RAIZ / "data" / "interim" / "firms" / f"firms_{a.pais.lower()}.parquet"
    salida.parent.mkdir(parents=True, exist_ok=True)
    partes = []
    for sensor in ["modis", "viirs-snpp", "viirs-jpss1", "viirs-jpss2"]:
        archivos = sorted(base.glob(f"{sensor}/*/{sensor}_*_{a.pais}.csv"))
        if archivos:
            partes.append(sql_sensor(sensor, str(base / sensor / "*" / f"{sensor}_*_{a.pais}.csv")))
            print(f"{sensor}: {len(archivos)} files")
    if not partes:
        print("no raw files; run src/datos/descargar_firms.py first")
        return 1
    t0 = time.time()
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"COPY ({' UNION ALL '.join(partes)} ORDER BY acq_datetime_utc) TO '{salida}' "
                "(FORMAT parquet, COMPRESSION zstd)")
    n, = con.execute(f"SELECT count(*) FROM '{salida}'").fetchone()
    print(f"OK → {salida.relative_to(RAIZ)}  rows={n:,}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
