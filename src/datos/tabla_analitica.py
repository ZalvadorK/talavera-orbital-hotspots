#!/usr/bin/env python3
"""Analytical table of detections (H2, ADR-0002/0003/0004): the intermediate table + derived columns. NO row is deleted.

SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.

Input : data/interim/firms/firms_<pais>.parquet          (tabla_intermedia.py + integrar_api.py)
Output: data/processed/deteccion_<pais>.parquet          (all the original columns + the ones below)
        data/processed/mascara_estatica_<pais>.parquet   (0.01° cells of the mask; input of the ADR-0007 "visible mask")
        data/processed/deteccion_<pais>.manifiesto.json  (command, commit, hashes, UTC date, checks)

Added columns (the original ones, including flag_nrt, flag_type_ausente and flag_pre_dic2000, are kept):
  anio, mes        from acq_date_utc (UTC date, ADR-0004 F1)
  turno            'D' | 'N' (= daynight; fails on any other value)
  celda01          "lat_lon" of the south-west corner of the 0.1° cell, 1 decimal:  printf('%.1f_%.1f', floor(lat*10)/10, floor(lon*10)/10)
  celda1           "lat_lon" of the south-west corner of the 1° cell, integers:     printf('%d_%d', floor(lat), floor(lon))   (e.g. '19_-99')
  tramo            'terra_sola'  Terra standard 2000-12-01 → 2002-07-03
                   'terra_aqua'  Terra/Aqua standard 2002-07-04 → 2011-12-31
                   'snpp'        S-NPP standard 2012-01-20 → 2018-03-31
                   'noaa20'      NOAA-20 standard from 2018-04-01
                   'noaa20_nrt'  NOAA-20 NRT (provisional)
                   'fuera'       everything else (Terra/Aqua/S-NPP from 2012 or 2018-04, Nov 2000, NOAA-21, …)
  en_serie         tramo <> 'fuera' and not flag_pre_dic2000 (what the harmonized series shows)
  en_calibracion   standard and (Terra/Aqua/S-NPP 2012-02-01 → 2018-12-31, or NOAA-20 2018-04-01 → 2018-12-31 for the bridge)
  reservado_prueba Terra/Aqua/S-NPP with date >= 2019-01-01 (ADR-0005: single test; not compared, not plotted, not exported)
  en_mascara       0.01° cell (floor(lat*100), floor(lon*100)) inside the static mask of ADR-0003: cells where standard S-NPP
                   had type<>0 in 2012-01-20 → 2018-12-31 OF THE SAME COUNTRY, plus their 8 neighbors (3x3). Same for all
                   sensors and for NRT (which carries no type).
  flag_multipaso   the 0.01° cell × UTC day × platform has >= 2 distinct acq_datetime_utc values (ADR-0004 C1: counted raw)

Usage (with the shared memory lock):
  flock data/.pesado.lock .venv/bin/python src/datos/tabla_analitica.py --pais mexico
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import resource
import subprocess
import sys
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
PAISES = ("mexico", "argentina")
MARCA_SI = "SI-generated (AI): Claude Code wrote the script that produced this file during the event; reviewed by the team."

# --- Frozen parameters (ADR-0002, ADR-0003 at 21:30; ADR-0004) ----------------------------------------------------
VENTANA_MASCARA = ("2012-01-20", "2018-12-31")      # ADR-0003: same as the calibration; standard S-NPP type<>0
CALIB_MODIS_SNPP = ("2012-02-01", "2018-12-31")     # standard Terra/Aqua/S-NPP
CALIB_NOAA20_PUENTE = ("2018-04-01", "2018-12-31")  # standard NOAA-20, only for the bridge
FECHA_RESERVA = "2019-01-01"                        # ADR-0005: from here on Terra/Aqua/S-NPP belong to the single test
ULTIMO_DIA_CALIBRACION = "2018-12-31"
# Popocatépetl check (ADR-0007; Mexico only)
POPO = (19.023, -98.622)
POPO_RADIO_KM = 5.0
POPO_VENTANA = ("2016-01-01", "2018-12-31")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def conectar(tmp: Path) -> duckdb.DuckDBPyConnection:
    tmp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false; "
                f"SET temp_directory='{tmp}'")
    return con


def construir_mascara(con, interim: Path, salida_mascara: Path) -> dict:
    """Static mask: standard S-NPP type<>0 inside the window, same country, + 3x3 neighbors (0.01° cells)."""
    ini, fin = VENTANA_MASCARA
    assert fin <= ULTIMO_DIA_CALIBRACION, "LEAK: the mask cannot use dates after 2018-12-31"
    con.execute(f"""
      CREATE OR REPLACE TEMP TABLE nucleo AS
      SELECT CAST(floor(latitude*100) AS BIGINT) AS la, CAST(floor(longitude*100) AS BIGINT) AS lo, count(*) AS n_snpp_type_ne0
      FROM read_parquet('{interim}')
      WHERE plataforma = 'S-NPP' AND procesamiento = 'estandar' AND type IS NOT NULL AND type <> 0
        AND acq_date_utc BETWEEN DATE '{ini}' AND DATE '{fin}'
      GROUP BY 1, 2""")
    con.execute("""
      CREATE OR REPLACE TEMP TABLE mascara AS
      SELECT n.la + dx AS la, n.lo + dy AS lo,
             bool_or(dx = 0 AND dy = 0) AS nucleo, sum(CASE WHEN dx = 0 AND dy = 0 THEN n.n_snpp_type_ne0 ELSE 0 END) AS n_snpp_type_ne0
      FROM nucleo n, range(-1, 2) a(dx), range(-1, 2) b(dy)
      GROUP BY 1, 2""")
    n_nucleo, n_total, = con.execute("SELECT count(*) FILTER (nucleo), count(*) FROM mascara").fetchone()
    # anti-leak: whatever fed the mask ends on 2018-12-31
    mx, = con.execute(f"""SELECT max(acq_date_utc) FROM read_parquet('{interim}')
                          WHERE plataforma='S-NPP' AND procesamiento='estandar' AND type IS NOT NULL AND type <> 0
                            AND acq_date_utc BETWEEN DATE '{ini}' AND DATE '{fin}'""").fetchone()
    assert mx is not None and mx <= dt.date.fromisoformat(ULTIMO_DIA_CALIBRACION), "LEAK in the mask"
    con.execute(f"""COPY (SELECT la AS lat100, lo AS lon100, la / 100.0 AS lat_sw, lo / 100.0 AS lon_sw, nucleo,
                                 CAST(n_snpp_type_ne0 AS BIGINT) AS n_snpp_type_ne0
                          FROM mascara ORDER BY la, lo) TO '{salida_mascara}'
                          (FORMAT parquet, COMPRESSION zstd, KV_METADATA {{si_generated: '{MARCA_SI}'}})""")
    return {"ventana": [ini, fin], "celdas_nucleo": n_nucleo, "celdas_con_vecinas_3x3": n_total, "ultima_fecha_usada": str(mx)}


SQL_TRAMO = """CASE
  WHEN plataforma = 'Terra' AND procesamiento = 'estandar' AND acq_date_utc BETWEEN DATE '2000-12-01' AND DATE '2002-07-03' THEN 'terra_sola'
  WHEN plataforma IN ('Terra', 'Aqua') AND procesamiento = 'estandar' AND acq_date_utc BETWEEN DATE '2002-07-04' AND DATE '2011-12-31' THEN 'terra_aqua'
  WHEN plataforma = 'S-NPP' AND procesamiento = 'estandar' AND acq_date_utc BETWEEN DATE '2012-01-20' AND DATE '2018-03-31' THEN 'snpp'
  WHEN plataforma = 'NOAA-20' AND procesamiento = 'estandar' AND acq_date_utc >= DATE '2018-04-01' THEN 'noaa20'
  WHEN plataforma = 'NOAA-20' AND procesamiento = 'NRT' THEN 'noaa20_nrt'
  ELSE 'fuera' END"""


def construir_tabla(con, interim: Path, destino: Path) -> None:
    c0, c1 = CALIB_MODIS_SNPP
    p0, p1 = CALIB_NOAA20_PUENTE
    tmp = destino.with_suffix(".tmp.parquet")
    # b is scanned twice (multi-pass and main table) instead of being materialized: it fits in 600 MB.
    sql = f"""
    COPY (
      WITH mp AS (
        SELECT plataforma AS mp_pl, acq_date_utc AS mp_d, CAST(floor(latitude*100) AS BIGINT) AS mp_la,
               CAST(floor(longitude*100) AS BIGINT) AS mp_lo
        FROM read_parquet('{interim}')
        GROUP BY ALL
        HAVING min(acq_datetime_utc) <> max(acq_datetime_utc)
      ),
      b AS (
        SELECT *, CAST(floor(latitude*100) AS BIGINT) AS _la, CAST(floor(longitude*100) AS BIGINT) AS _lo,
               {SQL_TRAMO} AS _tramo
        FROM read_parquet('{interim}')
      )
      SELECT b.* EXCLUDE (_la, _lo, _tramo),
        CAST(year(b.acq_date_utc) AS SMALLINT)  AS anio,
        CAST(month(b.acq_date_utc) AS TINYINT)  AS mes,
        b.daynight                               AS turno,
        printf('%.1f_%.1f', CAST(floor(b.latitude*10) AS BIGINT) / 10.0, CAST(floor(b.longitude*10) AS BIGINT) / 10.0) AS celda01,
        printf('%d_%d', CAST(floor(b.latitude) AS BIGINT), CAST(floor(b.longitude) AS BIGINT)) AS celda1,
        b._tramo AS tramo,
        (b._tramo <> 'fuera' AND NOT b.flag_pre_dic2000) AS en_serie,
        (b.procesamiento = 'estandar' AND (
            (b.plataforma IN ('Terra', 'Aqua', 'S-NPP') AND b.acq_date_utc BETWEEN DATE '{c0}' AND DATE '{c1}')
         OR (b.plataforma = 'NOAA-20' AND b.acq_date_utc BETWEEN DATE '{p0}' AND DATE '{p1}'))) AS en_calibracion,
        (b.plataforma IN ('Terra', 'Aqua', 'S-NPP') AND b.acq_date_utc >= DATE '{FECHA_RESERVA}') AS reservado_prueba,
        (m.la IS NOT NULL) AS en_mascara,
        (mp.mp_la IS NOT NULL) AS flag_multipaso
      FROM b
      LEFT JOIN mascara m ON m.la = b._la AND m.lo = b._lo
      LEFT JOIN mp ON mp.mp_pl = b.plataforma AND mp.mp_d = b.acq_date_utc AND mp.mp_la = b._la AND mp.mp_lo = b._lo
    ) TO '{tmp}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 122880,
                                   KV_METADATA {{si_generated: '{MARCA_SI}', source: 'NASA FIRMS (MODIS, VIIRS); see docs/02-datos/fuentes.md'}})"""
    con.execute(sql)
    tmp.replace(destino)


def verificar(con, pais: str, interim: Path, destino: Path) -> dict:
    """Checks with asserts (anti-leak and counts); returns the numbers for the manifest."""
    v: dict = {}
    # 1) counts per platform/processing/route identical to the intermediate table
    q = ("SELECT plataforma, procesamiento, coalesce(ruta_acceso, 'resumen_pais'), count(*) FROM read_parquet('{f}') "
         "GROUP BY ALL ORDER BY ALL")
    a = con.execute(q.format(f=interim)).fetchall()
    b = con.execute(q.format(f=destino)).fetchall()
    assert a == b, f"counts differ between the intermediate and analytical tables:\n{a}\n{b}"
    v["filas_intermedia"] = sum(r[3] for r in a)
    v["filas_analitica"] = sum(r[3] for r in b)
    assert v["filas_intermedia"] == v["filas_analitica"]
    v["conteos_por_plataforma_procesamiento_ruta"] = [list(map(str, r)) for r in b]
    # 2) Nov 2000 outside the series
    n, n_serie, n_tramo = con.execute(f"""SELECT count(*), count(*) FILTER (en_serie), count(*) FILTER (tramo <> 'fuera')
                                          FROM read_parquet('{destino}') WHERE flag_pre_dic2000""").fetchone()
    assert n > 0 and n_serie == 0 and n_tramo == 0, "Nov 2000 must stay outside the series"
    v["nov2000"] = {"filas": n, "en_serie": n_serie}
    # 3) allowed values and anti-leak
    assert con.execute(f"SELECT count(*) FROM read_parquet('{destino}') WHERE turno NOT IN ('D', 'N') OR turno IS NULL").fetchone()[0] == 0
    mx_cal, = con.execute(f"SELECT max(acq_date_utc) FROM read_parquet('{destino}') WHERE en_calibracion").fetchone()
    assert mx_cal <= dt.date.fromisoformat(ULTIMO_DIA_CALIBRACION), "LEAK: calibration with dates >= 2019"
    assert con.execute(f"SELECT count(*) FROM read_parquet('{destino}') WHERE en_calibracion AND reservado_prueba").fetchone()[0] == 0
    assert con.execute(f"""SELECT count(*) FROM read_parquet('{destino}')
                           WHERE reservado_prueba AND (en_serie OR en_calibracion)""").fetchone()[0] == 0, \
        "LEAK: reserved rows inside the series or the calibration"
    assert con.execute(f"""SELECT count(*) FROM read_parquet('{destino}')
                           WHERE plataforma IN ('Terra','Aqua','S-NPP') AND acq_date_utc >= DATE '{FECHA_RESERVA}' AND NOT reservado_prueba""").fetchone()[0] == 0
    v["max_fecha_en_calibracion"] = str(mx_cal)
    v["tramos"] = [[r[0], r[1], r[2], str(r[3]), str(r[4]), r[5]] for r in con.execute(f"""
        SELECT tramo, plataforma, procesamiento, min(acq_date_utc), max(acq_date_utc), count(*)
        FROM read_parquet('{destino}') GROUP BY ALL ORDER BY ALL""").fetchall()]
    v["banderas"] = dict(zip(["en_serie", "en_calibracion", "reservado_prueba", "en_mascara", "flag_multipaso", "flag_nrt"],
        con.execute(f"""SELECT count(*) FILTER (en_serie), count(*) FILTER (en_calibracion), count(*) FILTER (reservado_prueba),
                               count(*) FILTER (en_mascara), count(*) FILTER (flag_multipaso), count(*) FILTER (flag_nrt)
                        FROM read_parquet('{destino}')""").fetchone()))
    # 3b) content checksum independent of row order (the parquet bytes may vary between runs with 2 threads)
    cs, = con.execute(f"""SELECT sum(CAST(hash(plataforma, procesamiento, acq_datetime_utc, latitude, longitude, type, frp, tramo, en_serie,
                                  en_calibracion, reservado_prueba, en_mascara, flag_multipaso, celda01, celda1, anio, mes, turno) AS HUGEINT))
                           FROM read_parquet('{destino}')""").fetchone()
    v["checksum_contenido"] = str(cs)
    # 4) Popocatépetl (Mexico only): type=1 within <= 5 km of the crater, 2016-2018, per platform. Per-sensor query, NO ratios.
    if pais == "mexico":
        la0, lo0 = POPO
        kx = 111.195 * math.cos(math.radians(la0))
        # only platforms and dates inside the calibration window (2016-2018): no leak
        assert POPO_VENTANA[1] <= ULTIMO_DIA_CALIBRACION
        filas = con.execute(f"""
          SELECT plataforma, count(*) AS n_type1_5km, count(*) FILTER (en_mascara) AS n_en_mascara
          FROM read_parquet('{destino}')
          WHERE type = 1 AND procesamiento = 'estandar'
            AND acq_date_utc BETWEEN DATE '{POPO_VENTANA[0]}' AND DATE '{POPO_VENTANA[1]}'
            AND plataforma IN ('S-NPP', 'NOAA-20', 'Aqua')
            AND sqrt(power((latitude - {la0}) * 111.195, 2) + power((longitude - ({lo0})) * {kx}, 2)) <= {POPO_RADIO_KM}
          GROUP BY plataforma ORDER BY plataforma""").fetchall()
        v["popocatepetl_type1_5km_2016_2018"] = [{"plataforma": r[0], "n_type1": r[1], "n_en_mascara": r[2],
                                                   "captura_pct": round(100.0 * r[2] / r[1], 2) if r[1] else None} for r in filas]
    return v


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pais", choices=PAISES, required=True)
    a = ap.parse_args(argv)
    pais = a.pais
    interim = RAIZ / "data" / "interim" / "firms" / f"firms_{pais}.parquet"
    out_dir = RAIZ / "data" / "processed"
    destino = out_dir / f"deteccion_{pais}.parquet"
    f_mascara = out_dir / f"mascara_estatica_{pais}.parquet"
    manif = out_dir / f"deteccion_{pais}.manifiesto.json"
    if not interim.exists():
        raise SystemExit(f"missing {interim}; run tabla_intermedia.py and integrar_api.py first")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpdir = RAIZ / "data" / "interim" / "tmp_tabla_analitica"
    t0 = time.time()
    con = conectar(tmpdir)
    masc = construir_mascara(con, interim, f_mascara)
    t1 = time.time()
    print(f"[{pais}] mask: {masc['celdas_nucleo']:,} core cells → {masc['celdas_con_vecinas_3x3']:,} with 3x3 neighbors "
          f"(window {masc['ventana'][0]} → {masc['ventana'][1]}; last date used {masc['ultima_fecha_usada']})  {t1 - t0:.1f} s")
    construir_tabla(con, interim, destino)
    t2 = time.time()
    print(f"[{pais}] analytical table written  {t2 - t1:.1f} s")
    ver = verificar(con, pais, interim, destino)
    t3 = time.time()
    con.close()
    # remove our own temp dir (inside data/)
    for p in tmpdir.glob("*"):
        p.unlink(missing_ok=True)
    try:
        tmpdir.rmdir()
    except OSError:
        pass
    pico_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    manifiesto = {
        "id": f"tabla_analitica_{pais}",
        "comando": "flock data/.pesado.lock .venv/bin/python src/datos/tabla_analitica.py " + " ".join(argv),
        "commit": commit(),
        "semilla": None,
        "nota_semilla": "deterministic (no randomness)",
        "marca_si": MARCA_SI,
        "fecha_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "entradas": {str(interim.relative_to(RAIZ)): {"sha256": sha256(interim), "bytes": interim.stat().st_size}},
        "salidas": {str(destino.relative_to(RAIZ)): {"sha256": sha256(destino), "bytes": destino.stat().st_size},
                    str(f_mascara.relative_to(RAIZ)): {"sha256": sha256(f_mascara), "bytes": f_mascara.stat().st_size}},
        "parametros": {"ventana_mascara": list(VENTANA_MASCARA), "calibracion_modis_snpp": list(CALIB_MODIS_SNPP),
                       "calibracion_noaa20_puente": list(CALIB_NOAA20_PUENTE), "fecha_reserva_prueba": FECHA_RESERVA,
                       "duckdb": duckdb.__version__, "memory_limit": "600MB", "threads": 2},
        "mascara": masc,
        "verificacion": ver,
        "tiempos_s": {"mascara": round(t1 - t0, 1), "tabla": round(t2 - t1, 1), "verificacion": round(t3 - t2, 1),
                      "total": round(t3 - t0, 1)},
        "pico_rss_mb": round(pico_mb),
    }
    manif.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False) + "\n")
    print(f"[{pais}] OK → {destino.relative_to(RAIZ)}  rows={ver['filas_analitica']:,}  "
          f"{destino.stat().st_size / 1e6:.0f} MB  total {t3 - t0:.1f} s  peak RSS {pico_mb:.0f} MB")
    print(f"[{pais}] flags: {ver['banderas']}")
    print(f"[{pais}] Nov 2000: {ver['nov2000']}")
    if "popocatepetl_type1_5km_2016_2018" in ver:
        print(f"[{pais}] Popocatépetl type=1 ≤ {POPO_RADIO_KM:g} km, 2016-2018 (per platform, no ratios): "
              f"{ver['popocatepetl_type1_5km_2016_2018']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
