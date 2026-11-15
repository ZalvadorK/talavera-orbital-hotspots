#!/usr/bin/env python3
"""Platform-day availability table for MODIS (H2, ADR-0003 gap rule R1, ADR-0004).

Output : data/processed/disponibilidad_plataforma_dia.csv  (+ .manifiesto.json)
Columns: fecha, plataforma ('Terra'|'Aqua'), n_mx, n_ar, sin_datos (bool), fuente ('aviso_oficial'|'regla_datos'|'' = empty field)
Range  : 2000-11-01 → 2018-12-31 ONLY (anti-leak, ADR-0005: 2019+ is computed by the frozen script in the single run).
         Terra from 2000-11-01; Aqua from 2002-07-04 (first day with standard Aqua data: the platform did not exist before,
         so there are no Aqua rows in the Terra-only stretch).

Rules (ADR-0003, frozen at 21:30; N = 20):
  n_mx, n_ar = STANDARD detections of the platform on that UTC day in each country (all confidence levels and all `type` values; no mask).
  sin_datos  = True if
    (1) the day is inside an official notice: Terra 2001-06-15 → 2001-07-02 and Terra 2016-02-18 → 2016-02-28   [fuente='aviso_oficial']
    (2) GLOBAL data rule (Mexico + Argentina summed) from 2002-07-04: the platform has n_mx + n_ar = 0 and the other MODIS
        platform has n_mx + n_ar >= 20                                                                  [fuente='regla_datos']
  Before 2002-07-04 (Terra alone) only official notices count. If a notice and the rule coincide, fuente='aviso_oficial'.
  A `sin_datos` day is NOT "zero fire": the month that contains it is flagged incomplete (R1).

Usage (with the shared memory lock):
  flock data/.pesado.lock .venv/bin/python src/datos/disponibilidad.py
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
DESDE = "2000-11-01"
HASTA = "2018-12-31"          # anti-leak: never beyond
INICIO_AQUA = "2002-07-04"
N_REGLA = 20
AVISOS = [("Terra", "2001-06-15", "2001-07-02"), ("Terra", "2016-02-18", "2016-02-28")]
SALIDA = RAIZ / "data" / "processed" / "disponibilidad_plataforma_dia.csv"


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


def main() -> int:
    assert HASTA <= "2018-12-31", "LEAK: availability only up to 2018-12-31"
    t0 = time.time()
    mx = RAIZ / "data" / "interim" / "firms" / "firms_mexico.parquet"
    ar = RAIZ / "data" / "interim" / "firms" / "firms_argentina.parquet"
    for p in (mx, ar):
        if not p.exists():
            raise SystemExit(f"missing {p}")
    tmp = RAIZ / "data" / "interim" / "tmp_disponibilidad"
    tmp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false; SET temp_directory='{tmp}'")
    avisos = ", ".join(f"('{p}', DATE '{a}', DATE '{b}')" for p, a, b in AVISOS)
    cnt = ("SELECT acq_date_utc AS f, plataforma AS p, count(*) AS n FROM read_parquet('{f}') "
           f"WHERE procesamiento = 'estandar' AND plataforma IN ('Terra', 'Aqua') "
           f"AND acq_date_utc BETWEEN DATE '{DESDE}' AND DATE '{HASTA}' GROUP BY ALL")
    con.execute(f"""
      CREATE OR REPLACE TEMP TABLE base AS
      WITH cal AS (SELECT CAST(d AS DATE) AS fecha FROM range(DATE '{DESDE}', DATE '{HASTA}' + INTERVAL 1 DAY, INTERVAL 1 DAY) t(d)),
           plat AS (SELECT * FROM (VALUES ('Terra', DATE '{DESDE}'), ('Aqua', DATE '{INICIO_AQUA}')) v(plataforma, inicio)),
           mx AS ({cnt.format(f=mx)}), ar AS ({cnt.format(f=ar)})
      SELECT cal.fecha, plat.plataforma, coalesce(mx.n, 0) AS n_mx, coalesce(ar.n, 0) AS n_ar
      FROM cal CROSS JOIN plat
      LEFT JOIN mx ON mx.f = cal.fecha AND mx.p = plat.plataforma
      LEFT JOIN ar ON ar.f = cal.fecha AND ar.p = plat.plataforma
      WHERE cal.fecha >= plat.inicio""")
    con.execute(f"""
      COPY (
        WITH av(plataforma, d0, d1) AS (VALUES {avisos}),
        x AS (
          SELECT b.fecha, b.plataforma, b.n_mx, b.n_ar,
                 EXISTS (SELECT 1 FROM av WHERE av.plataforma = b.plataforma AND b.fecha BETWEEN av.d0 AND av.d1) AS aviso,
                 coalesce(o.n_mx + o.n_ar, 0) AS n_otra
          FROM base b LEFT JOIN base o ON o.fecha = b.fecha AND o.plataforma <> b.plataforma
        )
        SELECT fecha, plataforma, n_mx, n_ar,
               (aviso OR regla) AS sin_datos,
               CASE WHEN aviso THEN 'aviso_oficial' WHEN regla THEN 'regla_datos' END AS fuente
        FROM (SELECT *, (fecha >= DATE '{INICIO_AQUA}' AND n_mx + n_ar = 0 AND n_otra >= {N_REGLA}) AS regla FROM x)
        ORDER BY fecha, plataforma
      ) TO '{SALIDA}' (FORMAT csv, HEADER)""")
    n, f0, f1, n_sd = con.execute(
        f"SELECT count(*), min(fecha), max(fecha), count(*) FILTER (sin_datos) FROM read_csv('{SALIDA}', header=true)").fetchone()
    assert f1 <= dt.date.fromisoformat(HASTA), "LEAK: dates after 2018-12-31 in the availability table"
    dias = con.execute(f"""SELECT fecha, plataforma, n_mx, n_ar, fuente FROM read_csv('{SALIDA}', header=true)
                           WHERE sin_datos ORDER BY fecha, plataforma""").fetchall()
    con.close()
    for p in tmp.glob("*"):
        p.unlink(missing_ok=True)
    try:
        tmp.rmdir()
    except OSError:
        pass
    manifiesto = {
        "id": "disponibilidad_plataforma_dia",
        "comando": "flock data/.pesado.lock .venv/bin/python src/datos/disponibilidad.py",
        "commit": commit(), "semilla": None, "nota_semilla": "deterministic (no randomness)",
        "marca_si": "SI-generated (AI): Claude Code wrote the script that produced this file during the event; reviewed by the team.",
        "fecha_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "entradas": {str(p.relative_to(RAIZ)): {"sha256": sha256(p), "bytes": p.stat().st_size} for p in (mx, ar)},
        "salidas": {str(SALIDA.relative_to(RAIZ)): {"sha256": sha256(SALIDA), "bytes": SALIDA.stat().st_size}},
        "parametros": {"desde": DESDE, "hasta": HASTA, "inicio_aqua": INICIO_AQUA, "N": N_REGLA, "avisos_oficiales": AVISOS,
                       "regla": "global MX+AR; platform = 0 and the other MODIS >= N; only from 2002-07-04"},
        "resultado": {"filas": n, "primer_dia": str(f0), "ultimo_dia": str(f1), "dias_sin_datos": n_sd,
                      "sin_datos": [{"fecha": str(d[0]), "plataforma": d[1], "n_mx": d[2], "n_ar": d[3], "fuente": d[4]} for d in dias]},
        "tiempo_s": round(time.time() - t0, 1),
    }
    SALIDA.with_suffix(".manifiesto.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False) + "\n")
    print(f"OK → {SALIDA.relative_to(RAIZ)}  rows={n:,}  {f0} → {f1}  sin_datos={n_sd}  ({time.time() - t0:.1f} s)")
    for d in dias:
        print(f"  {d[0]}  {d[1]:5s}  n_mx={d[2]:>6}  n_ar={d[3]:>6}  {d[4]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
