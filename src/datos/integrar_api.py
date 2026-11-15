#!/usr/bin/env python3
"""Integrate the FIRMS Area-API cache (2026 tail) into data/interim/firms/firms_<country>.parquet.

- Reads data/raw/firms/api/<area>/<SOURCE>/*.csv (from descargar_firms_api.py).
- Clips the bounding box to the country polygon (Natural Earth 1:10m admin-0, data/raw/fronteras/;
  D1 check 2026-11-14: 100.000 % (MX) and 99.987 % (AR) of FIRMS 2025 country-summary points fall inside it).
- Same schema as tabla_intermedia.py; procesamiento from the SOURCE name (_SP → estandar, _NRT → NRT);
  NRT rows are kept only AFTER the last standard date of the same platform (logs/firms_data_availability.csv);
  ruta_acceso = 'api_area'. Previous api rows are replaced (idempotent); country-summary rows are untouched.
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import shapely

RAIZ = Path(__file__).resolve().parents[2]
NE = RAIZ / "data" / "raw" / "fronteras" / "ne_10m_admin_0_countries.zip"
ISO = {"mexico": "MEX", "argentina": "ARG"}
FUENTE = {"MODIS": ("modis", "MODIS"), "VIIRS_SNPP": ("viirs-snpp", "VIIRS"),
          "VIIRS_NOAA20": ("viirs-jpss1", "VIIRS"), "VIIRS_NOAA21": ("viirs-jpss2", "VIIRS")}
PLAT = {"viirs-snpp": "S-NPP", "viirs-jpss1": "NOAA-20", "viirs-jpss2": "NOAA-21"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", choices=sorted(ISO), required=True)
    a = ap.parse_args(argv)
    base = RAIZ / "data" / "raw" / "firms" / "api" / a.area
    destino = RAIZ / "data" / "interim" / "firms" / f"firms_{a.area}.parquet"
    staging = RAIZ / "data" / "interim" / "firms" / "staging_api"
    if not destino.exists():
        raise SystemExit(f"missing {destino}; run tabla_intermedia.py first")
    staging.mkdir(parents=True, exist_ok=True)
    ne = gpd.read_file(f"zip://{NE}", columns=["ADM0_A3"], where=f"ADM0_A3 = '{ISO[a.area]}'")
    poly = ne.geometry.union_all()
    del ne
    con = duckdb.connect()
    con.execute(f"SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false; "
                f"SET temp_directory='{staging}/tmp'")
    import csv as _csv
    disp = {r['data_id']: r['max_date'] for r in _csv.DictReader((RAIZ / 'logs' / 'firms_data_availability.csv').open())}
    selects = []
    for carpeta in sorted(p for p in base.iterdir() if p.is_dir()):
        src = carpeta.name                       # e.g. VIIRS_NOAA20_NRT
        clave, proc = src.rsplit("_", 1)
        fuente, familia = FUENTE[clave]
        viirs = familia == "VIIRS"
        b1, b2 = ("bright_ti4", "bright_ti5") if viirs else ("brightness", "bright_t31")
        st = staging / f"{a.area}_{src}.parquet"
        con.execute(f"""COPY (SELECT row_number() OVER () AS rid, * FROM read_csv('{carpeta}/*.csv', header=true,
                        all_varchar=true, filename=true, union_by_name=true)) TO '{st}' (FORMAT parquet)""")
        xy = con.execute(f"SELECT rid, CAST(longitude AS DOUBLE) x, CAST(latitude AS DOUBLE) y FROM '{st}'").fetchnumpy()
        dentro = shapely.contains_xy(poly, xy["x"], xy["y"])
        keep = staging / f"{a.area}_{src}_keep.parquet"
        con.execute("CREATE OR REPLACE TEMP TABLE k AS SELECT unnest($1::BIGINT[]) AS rid", [xy["rid"][dentro].tolist()])
        con.execute(f"COPY k TO '{keep}' (FORMAT parquet)")
        print(f"{src:18s} bbox rows={len(dentro):>8,}  inside {ISO[a.area]}={int(dentro.sum()):>8,}", flush=True)
        del xy, dentro
        plat = f"'{PLAT[fuente]}'" if viirs else "CASE WHEN upper(satellite) IN ('TERRA','T') THEN 'Terra' ELSE 'Aqua' END"
        tipo = "TRY_CAST(NULLIF(type, '') AS INTEGER)" if proc == "SP" else "CAST(NULL AS INTEGER)"
        selects.append(f"""
          SELECT '{fuente}' fuente, '{familia}' familia, {plat} plataforma, satellite satellite_raw,
            instrument instrument_raw, '{'estandar' if proc == 'SP' else 'NRT'}' procesamiento, version,
            CAST(latitude AS DOUBLE) latitude, CAST(longitude AS DOUBLE) longitude,
            strptime(acq_date || ' ' || lpad(acq_time, 4, '0'), '%Y-%m-%d %H%M') acq_datetime_utc,
            CAST(acq_date AS DATE) acq_date_utc, daynight, confidence confidence_raw,
            TRY_CAST(frp AS DOUBLE) frp, TRY_CAST(scan AS DOUBLE) scan, TRY_CAST(track AS DOUBLE) track,
            TRY_CAST({b1} AS DOUBLE) bright_1, TRY_CAST({b2} AS DOUBLE) bright_2, '{b1}' bright_1_nombre,
            '{b2}' bright_2_nombre, {tipo} AS type, ({tipo} IS NULL) flag_type_ausente,
            {'true' if proc == 'NRT' else 'false'} flag_nrt,
            (CAST(acq_date AS DATE) < DATE '2000-12-01') flag_pre_dic2000,
            regexp_extract(filename, '[^/]+$') archivo_origen, 'api_area' ruta_acceso
          FROM '{st}' WHERE rid IN (SELECT rid FROM '{keep}')"""
            + (f" AND CAST(acq_date AS DATE) > DATE '{disp[clave + '_SP']}'" if proc == 'NRT' and clave + '_SP' in disp else ''))
    if not selects:
        print("no API data"); return 1
    tmp = destino.with_suffix(".tmp.parquet")
    api_sql = " UNION ALL BY NAME ".join(selects)
    con.execute(f"""COPY (SELECT * FROM '{destino}' WHERE coalesce(ruta_acceso,'resumen_pais') <> 'api_area'
                          UNION ALL BY NAME {api_sql})
                    TO '{tmp}' (FORMAT parquet, COMPRESSION zstd)""")
    tmp.replace(destino)
    n, n_api, d1 = con.execute(f"SELECT count(*), count(*) FILTER (ruta_acceso='api_area'), max(acq_date_utc) FROM '{destino}'").fetchone()
    print(f"OK → {destino.relative_to(RAIZ)}  rows={n:,}  (api={n_api:,}; last day={d1})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
