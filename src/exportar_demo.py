#!/usr/bin/env python3
"""Static-demo exporter (ADR-0004, ADR-0007, ADR-0009, ADR-0010): precomputed aggregates on 1-degree tiles for app/data/.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Input   : data/processed/deteccion_<country>.parquet          (analytic table; src/datos/tabla_analitica.py)
          data/processed/disponibilidad_plataforma_dia.csv  (rule R1; src/datos/disponibilidad.py)
          data/raw/fronteras/ne_10m_admin_0_countries.zip   (Natural Earth 1:10m, public domain)
          --pesos real: src/nucleo/factores.py (factores(), pesos_modis(), intervalo(), ruta_intervalos())
          runs/EXP-*/verdict.json   OPTIONAL: the single-test verdict (written by src/nucleo/validacion_rt05.py in test mode only)
          runs/EXP-*/metricas.json  OPTIONAL, next to verdict.json: the key figures of the single test (kappa, P3 coverage, P4 skill) that
                                    the Method notes quote; summarized in manifest.verdict.metricas (with its sha256)
          data/raw/firms/missing_data/MODIS_SP.csv  OPTIONAL: FIRMS missing-data table (availability metadata, not detections);
                                    crossed with the availability table into manifest.huecos_modis
          src/plantillas_publicas/LICENSE-DATA.md           (template copied next to the data)
Output  : app/data/manifest.json, app/data/LICENSE-DATA.md,
          app/data/<country>/{contorno.geojson, intervalos.json, disponibilidad.json, export_manifiesto.json,
          mensual/<tile>.csv, diario/<tile>.csv, puntos/<tile>.parquet}   (contract: app/data/CONTRATO-DATOS.md)

Weight modes
  --pesos synthetic  MODIS weight = 1 (NOT harmonized), manifest.synthetic = true, SYNTHETIC banner. Only to shape the app.
                     This export NEVER goes to the public repo (ADR-0009). It never opens the reserve (see below).
  --pesos real       MODIS weight = w of lane A's contract (VIIRS-equivalent per detection, R1); intervalos.json copied from A.

ANTI-LEAK (ADR-0005) has two states, decided only by the existence of the single-test verdict.json:
  - CLOSED (no verdict.json; the default): Terra, Aqua and S-NPP with date >= 2019-01-01 are reserved for the single test.
    They enter no row and no column with a value (t, a, s come out EMPTY if y >= 2019) and manifest.verdict is null.
    The final audit walks all of app/data/ and fails on any leak (`--solo-auditar` runs it alone).
  - OPEN (runs/EXP-NNN/verdict.json exists, mode "prueba", thresholds fixed): the exporter copies a summary of the verdict
    to manifest.verdict (per-country booleans and the "reliable" / "indicative" label, rule I-05 3b) and ONLY THEN exports
    the raw monthly counts t, a, s of Terra/Aqua/S-NPP for 2019 onward. Both countries must be exported in the same run.
    The series itself and the point tiles never change (they never hold Terra/Aqua/S-NPP outside their series era).
    The audit then requires the summary, the sha256 of the verdict file, the SUMMARY RECOMPUTED from that file (resumir_verdict)
    equal to manifest.verdict, and non-empty t, a, s.
  `--runs-dir` (tests only) points to another directory with runs/EXP-*/verdict.json; it forbids writing to app/data.
  A checkout WITHOUT the rest of runs/ (the public repository) audits too if it carries runs/EXP-NNN/verdict.json and metricas.json
  byte for byte: `--listar-runs-auditoria` prints those paths from manifest.verdict (the publication script copies exactly them).

Light mode `--refrescar-manifest`: updates only the manifest fields added after an earlier export (si_assisted, SI
declaration, license) and copies LICENSE-DATA.md, without recomputing any table. Valid only while verdict.json does not exist.

Memory: the machine has ~1.5 GB free. ALWAYS run with the shared lock; DuckDB uses 600 MB / 2 threads and an on-disk
database (data/interim/export_tmp/):
  flock data/.pesado.lock .venv/bin/python src/exportar_demo.py --pesos synthetic --pais mexico
  flock data/.pesado.lock .venv/bin/python src/exportar_demo.py --pesos real --pais ambos
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
PROC = RAIZ / "data" / "processed"
NE = RAIZ / "data" / "raw" / "fronteras" / "ne_10m_admin_0_countries.zip"
TMP = RAIZ / "data" / "interim" / "export_tmp"
SALIDA_DEFECTO = RAIZ / "app" / "data"
PAISES = ("mexico", "argentina")
ISO = {"mexico": "MEX", "argentina": "ARG"}
NOMBRE = {"mexico": "Mexico", "argentina": "Argentina"}
MARCA_SI = "SI-generated (AI): Claude Code wrote the script that produced this file during the event; reviewed by the team."
FECHA_RESERVA = "2019-01-01"          # ADR-0005
CORTE = "2026-11-14"                  # frozen cut-off of the download (ADR-0008)
TOPE_BYTES = 15 * 1024 * 1024         # ADR-0009: no file > 15 MiB
VENTANA_CAL = ("2012-02-01", "2018-12-31")
BANNER_SINT = ("SYNTHETIC: MODIS weights are set to 1 (not harmonized). Shapes only, for building the app. "
               "Do not show as results; never publish this export.")
RUNS = RAIZ / "runs"
PLANTILLA_LICENCIA = RAIZ / "src" / "plantillas_publicas" / "LICENSE-DATA.md"
SI_DECLARATION = ("This dataset was produced with SI (AI) assistance: the export script, the analysis core and the app that reads it "
                  "were written by Claude Code during the event and reviewed by the team. Source data: NASA FIRMS. "
                  "License of the derived data: CC BY 4.0 (see LICENSE-DATA.md). Not endorsed by NASA.")
LICENCIA_DATOS = {"id": "CC BY 4.0", "file": "LICENSE-DATA.md"}
# Label rule of the single test (ADR-0005 7e/7f, ADR-0006, route I-05 point 3b: the count-class test of I-05 is "not run").
BLOQUE_GRADOS = 3                                                      # scale of the test (config/validacion.yaml: bloque_grados)
CELDA_GRADOS = 0.1                                                     # grid of the app
MIN_CELDAS_BLOQUE = round((BLOQUE_GRADOS / CELDA_GRADOS) ** 2)         # 900 cells of 0.1 deg = the area of one 3-degree block
REGLA_ETIQUETA = ("A harmonized (estimated) month is labelled 'reliable' only if its country passed the pre-registered sensor-agreement tests "
                  "P2 and P2b on the published scale AND the area covers at least one 3-degree block AND the count class of the area passed P2 and P2b "
                  "AND the area is not below the minimum of expected MODIS detections (M1); otherwise it is 'indicative'. "
                  "Months estimated from Terra alone (Dec 2000 to Jun 2002) are always 'indicative'.")
REGLA_REF = ["ADR-0005 7e/7f", "ADR-0006", "I-05 3b + count classes", "M1"]

# Era (tramo) per MONTH (column `tramo` of the monthly tiles). The limits are those of ADR-0002; the start of the NRT is read from the data.
#   T: Terra sola dic-2000..jun-2002 | TA: Terra+Aqua jul-2002..dic-2011 | S: S-NPP ene-2012..mar-2018
#   N: NOAA-20 standard Apr-2018..Jul-2026 | NP: NOAA-20 NRT "provisional" from Aug-2026
LIMITES_TRAMO = [(200207, "T"), (201201, "TA"), (201804, "S")]   # y*100+m < limit -> era; then N until NRT_YM; then NP
# Era per DETECTION (column `tramo` of the point tiles): what the analytic table says
TRAMO_DET = {"terra_sola": "T", "terra_aqua": "TA", "snpp": "S", "noaa20": "N", "noaa20_nrt": "NP"}

# Predefined AOIs (ADR-0007, ADR-0010). bbox = [lon_west, lat_south, lon_east, lat_north] as declared;
# bbox_celdas = snapped to the 0.1° grid (cells whose center falls inside: center >= minimum and < maximum).
AOI_PREDEF = {
    "mexico": [
        {"id": "puebla_popocatepetl", "nombre": "Puebla / Popocatépetl", "bbox": [-99.1, 17.85, -96.7, 20.85],
         "nota": "Includes the Popocatépetl volcano (static-mask showcase, ADR-0007)."},
    ],
    "argentina": [
        {"id": "bahia_blanca", "nombre": "Bahía Blanca", "bbox": [-66.0, -40.0, -61.0, -35.0],
         "nota": "SW Buenos Aires province; port and industrial non-vegetation thermal sources (identity not verified, ADR-0007)."},
        {"id": "delta_parana", "nombre": "Paraná Delta", "bbox": [-60.8, -34.5, -58.3, -32.0],
         "nota": ("Reasonable box (not an official boundary): from the Diamante/Rosario reach (~32.0 S, 60.8 W) down to the Río de la "
                  "Plata mouth (~34.5 S) and east to the Uruguay river (~58.3 W). Island-burning area; includes the Rosario and "
                  "Zárate-Campana industrial belts.")},
    ],
}

METODO_ADR = ["ADR-0002", "ADR-0003", "ADR-0004", "ADR-0005", "ADR-0006", "ADR-0007", "ADR-0009", "ADR-0010"]

COLS_MENSUAL = "c,y,m,tramo,v,vm,t,a,s,n20,xm,inc,prov"
COLS_DIARIO = "c,d,v,vm,prov"
COLS_PUNTOS = ["lat", "lon", "fecha_utc", "hora_utc", "plataforma", "procesamiento", "peso", "en_mascara", "flag_multipaso",
               "frp", "confidence", "type", "tramo"]


# ------------------------------------------------------------------------------------------------ utilidades
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def commit() -> tuple[str, bool]:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.strip()
        sucio = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=RAIZ, capture_output=True,
                                    text=True, check=True).stdout.strip())
        return c, sucio
    except Exception:  # noqa: BLE001
        return "unknown", True


def ahora_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def sql_str(p: Path | str) -> str:
    s = str(p)
    assert "'" not in s, f"path with a quote: {s}"
    return s


def conectar(db: Path) -> duckdb.DuckDBPyConnection:
    TMP.mkdir(parents=True, exist_ok=True)
    for ext in ("", ".wal"):
        Path(str(db) + ext).unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    con.execute("SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{sql_str(TMP / 'spill')}'")
    return con


def num(expr: str) -> str:
    """Compact number for CSV: DOUBLE rounded to 3 decimals, no trailing '.0' (12.0 -> 12)."""
    return f"regexp_replace(CAST(round({expr}, 3) AS VARCHAR), '\\.0$', '')"


def tramo_mes_sql(nrt_ym: int, anio: str = "anio", mes: str = "mes") -> str:
    ym = f"({anio}*100+{mes})"
    ramas = " ".join(f"WHEN {ym} < {lim} THEN '{t}'" for lim, t in LIMITES_TRAMO)
    return f"CASE {ramas} WHEN {ym} < {nrt_ym} THEN 'N' ELSE 'NP' END"


def tramo_mes_py(y: int, m: int, nrt_ym: int) -> str:
    ym = y * 100 + m
    for lim, t in LIMITES_TRAMO:
        if ym < lim:
            return t
    return "N" if ym < nrt_ym else "NP"


def snap_bbox(bbox: list[float]) -> list[float]:
    """Snaps to the 0.1° grid: cells whose CENTER is in [min, max) per axis. Integer arithmetic (hundredths of a degree)."""
    def ceil_div(x: int, y: int) -> int:
        return -((-x) // y)

    def rango(lo: float, hi: float) -> tuple[int, int]:
        a_, b_ = int(round(lo * 100)), int(round(hi * 100))
        # centers = 10k + 5 (hundredths): smallest k with 10k+5 >= a_ ; largest k with 10k+5 < b_
        return ceil_div(a_ - 5, 10), ceil_div(b_ - 5, 10) - 1

    kx0, kx1 = rango(bbox[0], bbox[2])
    ky0, ky1 = rango(bbox[1], bbox[3])
    return [kx0 / 10, ky0 / 10, (kx1 + 1) / 10, (ky1 + 1) / 10]


# ------------------------------------------------------------------------------------------------ contorno (Natural Earth)
def _contorno_directo(pais: str, salida: Path) -> dict:
    """Simplified Natural Earth 1:10m polygon (tolerance 0.005° ≈ 550 m; islands < 0.002 deg² ≈ 25 km² are dropped)."""
    import geopandas as gpd
    import shapely
    from shapely.geometry import MultiPolygon, mapping

    TOL, MIN_AREA, PREC = 0.005, 0.002, 0.0001
    gdf = gpd.read_file(f"zip://{NE}", columns=["ADM0_A3"], where=f"ADM0_A3 = '{ISO[pais]}'")
    assert len(gdf) == 1, f"expected 1 polygon for {ISO[pais]}, found {len(gdf)}"
    geom = gdf.geometry.union_all()
    partes = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    grandes = [p for p in partes if p.area >= MIN_AREA]
    g = shapely.set_precision(MultiPolygon(grandes).simplify(TOL, preserve_topology=True), PREC)
    assert g.is_valid and not g.is_empty
    o, s, e, n = g.bounds
    bbox = [math.floor(o * 10) / 10, math.floor(s * 10) / 10, math.ceil(e * 10) / 10, math.ceil(n * 10) / 10]
    feat = {"type": "FeatureCollection",
            "properties": {"si": MARCA_SI, "source": "Natural Earth 1:10m Admin-0 Countries (public domain), ADM0_A3=" + ISO[pais],
                           "simplify_deg": TOL, "min_island_area_deg2": MIN_AREA, "coordinate_precision_deg": PREC,
                           "partes_originales": len(partes), "partes_conservadas": len(grandes)},
            "features": [{"type": "Feature", "properties": {"name": NOMBRE[pais], "iso_a3": ISO[pais]}, "geometry": mapping(g)}]}
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(feat, separators=(",", ":")))
    return {"bbox": bbox, "bytes": salida.stat().st_size, "partes_originales": len(partes), "partes_conservadas": len(grandes)}


def construir_contorno(pais: str, salida: Path) -> dict:
    """Runs _contorno_directo in a subprocess: geopandas/shapely add ~250 MB of RSS that need not be kept (machine with ~1.5 GB free)."""
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--_contorno", pais, str(salida)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------------------------------------------ disponibilidad
def construir_disponibilidad(pais: str, salida: Path, datos_hasta: str, nrt_ym: int) -> tuple[dict, set[tuple[int, int]]]:
    """disponibilidad.json and the set of incomplete months (R1: some day with NO MODIS platform with data).

    Days with only one platform without data do NOT make the month incomplete (R1: backed up by the other); they are listed apart.
    Lane A's table only covers 2000-11-01 -> 2018-12-31 (anti-leak); from 2019 the series is VIIRS only and there is no MODIS to flag.
    """
    import pandas as pd

    csv = PROC / "disponibilidad_plataforma_dia.csv"
    d = pd.read_csv(csv, dtype={"sin_datos": str, "fuente": str})
    d["fecha"] = pd.to_datetime(d["fecha"])
    d["sd"] = d["sin_datos"].str.lower().eq("true")
    assert d["fecha"].max() < pd.Timestamp(FECHA_RESERVA), "the availability table must not go past 2018-12-31"
    t = d[d.plataforma == "Terra"].set_index("fecha")["sd"]
    a = d[d.plataforma == "Aqua"].set_index("fecha")["sd"]
    dias = pd.DataFrame({"t_sd": t}).join(a.rename("a_sd"), how="left")
    dias["aqua_existe"] = dias["a_sd"].notna()
    dias["a_sd"] = dias["a_sd"].fillna(True).astype(bool)   # Aqua without a row (before 2002-07-04) = not available
    dias["t_sd"] = dias["t_sd"].astype(bool)
    dias["aqua_existe"] = dias["aqua_existe"].astype(bool)
    dias["sin_modis"] = dias["t_sd"] & dias["a_sd"]
    inc = dias[dias["sin_modis"]].copy()
    inc["y"], inc["m"] = inc.index.year, inc.index.month
    meses_inc = (inc.groupby(["y", "m"]).size().reset_index(name="dias_sin_modis"))

    fuente_dia = d.set_index(["fecha", "plataforma"])["fuente"].fillna("")

    def rangos(nombre: str, serie_bool: "pd.Series") -> list[list[str]]:
        """Ranges of consecutive days with the same source: [start, end, source]."""
        out: list[list[str]] = []
        for f in serie_bool[serie_bool].index:
            src = str(fuente_dia.get((f, nombre), ""))
            if out and (f - pd.Timestamp(out[-1][1])).days == 1 and out[-1][2] == src:
                out[-1][1] = f.strftime("%Y-%m-%d")
            else:
                out.append([f.strftime("%Y-%m-%d"), f.strftime("%Y-%m-%d"), src])
        return out

    plataformas = {}
    for nombre, col in (("Terra", "t_sd"), ("Aqua", "a_sd")):
        s_ = dias[col] if nombre == "Terra" else dias[col] & dias["aqua_existe"]
        plataformas[nombre] = {"dias_sin_datos": int(s_.sum()), "rangos": rangos(nombre, s_)}
    j = {
        "si": MARCA_SI,
        "pais": pais,
        "fuente": "data/processed/disponibilidad_plataforma_dia.csv",
        "sha256_fuente": sha256(csv),
        "regla": ("ADR-0003 R1, global rule Mexico+Argentina with N=20 plus official notices (Terra 2001-06-15..07-02 and 2016-02-18..28). "
                  "A month is INCOMPLETE if some day has NO MODIS platform with data; a day with a single platform "
                  "without data is backed up by the other (it does not make the month incomplete)."),
        "rango_tabla": [str(dias.index.min().date()), str(dias.index.max().date())],
        "cobertura_modis_en_serie": "2000-12 to 2011-12 (MODIS is in the series only until Dec 2011; from Jan 2012 the series is VIIRS)",
        "plataformas": plataformas,
        "meses_incompletos": [{"y": int(r.y), "m": int(r.m), "motivo": "outage", "dias_sin_modis": int(r.dias_sin_modis)}
                              for r in meses_inc.itertuples()],
        "meses_parciales": [{"y": 2012, "m": 1, "motivo": "partial month: S-NPP data start 2012-01-20"}],
        "mes_en_curso": {"y": int(datos_hasta[:4]), "m": int(datos_hasta[5:7]), "hasta": datos_hasta,
                         "nota": "month to date; the last NRT days are provisional"},
        "nrt_desde": {"y": nrt_ym // 100, "m": nrt_ym % 100},
        "nota_ausencia_de_fila": ("In mensual/*.csv a cell-month without a row means 0 detections, EXCEPT when the month is in "
                                  "meses_incompletos (then it is 'no data', never 0)."),
    }
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(j, ensure_ascii=False, indent=1))
    conj = {(int(r.y), int(r.m)) for r in meses_inc.itertuples()} | {(2012, 1)}
    return j, conj


# ------------------------------------------------------------------------------------------------ pesos (synthetic | real)
def calcular_pesos_real(con: duckdb.DuckDBPyConnection, pais: str, nucleo_path: Path | None) -> dict:
    """VIIRS-eq weight per MODIS detection of the series with lane A's contract. Processed year by year to bound memory."""
    import pandas as pd

    sys.path.insert(0, str(nucleo_path or (RAIZ / "src")))
    from nucleo import factores as FA  # noqa: PLC0415

    desde, hasta = VENTANA_CAL
    assert hasta < FECHA_RESERVA
    F = FA.factores(pais, desde, hasta)
    disp = FA.disponibilidad(pais)
    con.execute("CREATE OR REPLACE TABLE pesos (rid BIGINT, w DOUBLE)")
    anios = [r[0] for r in con.execute("SELECT DISTINCT anio FROM serie WHERE en_serie AND familia = 'MODIS' ORDER BY 1").fetchall()]
    n_modis = n_nan = 0
    for y in anios:
        df = con.execute("""SELECT rowid AS rid, plataforma, acq_date_utc, mes, turno, celda1 FROM serie
                            WHERE en_serie AND familia = 'MODIS' AND anio = ?""", [y]).df()
        w = FA.pesos_modis(df, F, disp)
        assert len(w) == len(df)
        out = pd.DataFrame({"rid": df["rid"].to_numpy(), "w": w})
        con.register("w_df", out)
        con.execute("INSERT INTO pesos SELECT rid, CASE WHEN isnan(w) THEN NULL ELSE w END FROM w_df")
        con.unregister("w_df")
        n_modis += len(df)
        n_nan += int(pd.isna(w).sum())
    neg = con.execute("SELECT count(*) FROM pesos WHERE w < 0 OR w = 'inf'::DOUBLE").fetchone()[0]
    assert neg == 0, "negative or infinite weights"
    ejemplo = {}
    for tr in ("T", "TA"):
        for nivel in ("1deg", "pais", "aoi"):
            ejemplo[f"{tr}/{nivel}"] = [round(v, 4) if math.isfinite(v) else None for v in FA.intervalo(pais, 1.0, tr, nivel)]
    return {"detecciones_modis": n_modis, "sin_peso_nan": n_nan, "intervalo_s1_ic80_multiplicativo": ejemplo,
            "factores_filas": int(len(F)), "ventana_calibracion": [desde, hasta]}


# ------------------------------------------------------------------------------------------------ table construction
def preparar(con: duckdb.DuckDBPyConnection, pais: str, pesos: str, meses_inc: set[tuple[int, int]], teselas: list[str] | None,
             nucleo_path: Path | None, reserva_abierta: bool = False) -> dict:
    f = PROC / f"deteccion_{pais}.parquet"
    assert f.exists(), f"missing {f}; run src/datos/tabla_analitica.py --pais {pais}"
    filtro_tesela = ""
    if teselas:
        assert all(re.fullmatch(r"-?\d+_-?\d+", t) for t in teselas), teselas
        filtro_tesela = " AND celda1 IN (" + ",".join(f"'{t}'" for t in teselas) + ")"
    t0 = time.perf_counter()
    # Base: the series (en_serie) + what the raw counts t, a, s need (standard Terra/Aqua/S-NPP dated < 2019; any date if the reserve
    # is open). NOAA-21 is always out; with the reserve closed, Terra/Aqua/S-NPP >= 2019-01-01 stay OUT of the table (ADR-0005).
    con.execute(f"""
      CREATE OR REPLACE TABLE serie AS
      SELECT familia, plataforma, procesamiento, latitude, longitude, acq_datetime_utc, acq_date_utc, turno, celda01, celda1,
             tramo, en_serie, en_mascara, flag_multipaso, frp, confidence_raw, "type",
             CAST(anio AS INTEGER) AS anio, CAST(mes AS INTEGER) AS mes
      FROM read_parquet('{sql_str(f)}')
      WHERE {sql_filtro_base(reserva_abierta)}{filtro_tesela}
      ORDER BY celda1, celda01, acq_datetime_utc, latitude, longitude, plataforma""")
    n_base = con.execute("SELECT count(*) FROM serie").fetchone()[0]
    # --- ANTI-LEAK ASSERTS on the base table (only with the reserve closed; a verdict allows the raw counts of 2019+) ---
    n_fuga = con.execute(f"""SELECT count(*) FROM serie WHERE plataforma IN ('Terra', 'Aqua', 'S-NPP')
                             AND acq_date_utc >= DATE '{FECHA_RESERVA}'""").fetchone()[0]
    if not reserva_abierta:
        assert n_fuga == 0, f"LEAK: {n_fuga} Terra/Aqua/S-NPP rows >= {FECHA_RESERVA} in the base table"
    assert con.execute("SELECT count(*) FROM serie WHERE plataforma = 'NOAA-21'").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM serie WHERE en_serie AND tramo = 'fuera'").fetchone()[0] == 0
    mx, = con.execute("SELECT max(acq_date_utc) FROM serie").fetchone()
    assert str(mx) <= CORTE, f"data after the cut-off {CORTE}: {mx}"
    # Start of the NRT read from the data (must be day 1 of a month so that the era is monthly)
    nrt_min, = con.execute("SELECT min(acq_date_utc) FROM serie WHERE tramo = 'noaa20_nrt'").fetchone()
    assert nrt_min is not None and nrt_min.day == 1, f"the NRT does not start on day 1: {nrt_min}"
    nrt_ym = nrt_min.year * 100 + nrt_min.month
    # Monthly era consistent with the per-detection era (only exception: 2002-07-01..03, Terra still alone)
    malos = con.execute(f"""SELECT tm, tramo, ym, n FROM (
        SELECT {tramo_mes_sql(nrt_ym)} AS tm, tramo, anio*100+mes AS ym, count(*) AS n FROM serie WHERE en_serie GROUP BY ALL)
        WHERE NOT ((tramo = 'terra_sola' AND tm = 'T') OR (tramo = 'terra_aqua' AND tm = 'TA') OR (tramo = 'snpp' AND tm = 'S')
                   OR (tramo = 'noaa20' AND tm = 'N') OR (tramo = 'noaa20_nrt' AND tm = 'NP')
                   OR (tramo = 'terra_sola' AND ym = 200207 AND tm = 'TA'))""").fetchall()
    assert not malos, f"monthly era inconsistent with the per-detection era: {malos[:5]}"
    t1 = time.perf_counter()

    info_pesos: dict = {"modo": pesos}
    if pesos == "real":
        info_pesos.update(calcular_pesos_real(con, pais, nucleo_path))
        con.execute("""CREATE OR REPLACE VIEW serie_p AS
            SELECT s.*, CASE WHEN s.familia = 'VIIRS' THEN 1.0 ELSE p.w END AS peso
            FROM serie s LEFT JOIN pesos p ON p.rid = s.rowid""")
    else:
        con.execute("CREATE OR REPLACE VIEW serie_p AS SELECT *, 1.0 AS peso FROM serie")
    t2 = time.perf_counter()

    import pandas as pd
    con.register("meses_inc_df", pd.DataFrame(sorted(meses_inc), columns=["y", "m"]))
    con.execute("CREATE OR REPLACE TABLE meses_inc AS SELECT y * 100 + m AS ym FROM meses_inc_df")
    con.unregister("meses_inc_df")
    cond_tas = sql_cond_tas(reserva_abierta)
    # --- mensual (wide): one row per 0.1° cell × month with any detection; no row = 0 (unless the month is incomplete) ---
    # v: value shown outside the mask (observed VIIRS or sum of the VIIRS-eq weights of MODIS); vm: includes what is masked;
    # t, a, s: raw counts outside the mask per platform (NULL if y >= 2019 while the reserve is closed, ADR-0005); n20: NOAA-20 outside the mask;
    # xm: raw count INSIDE the mask of the series platform (everything en_serie with en_mascara).
    con.execute(f"""
      CREATE OR REPLACE TABLE mensual AS
      SELECT celda1, celda01 AS c, anio AS y, mes AS m, {tramo_mes_sql(nrt_ym)} AS tramo,
        coalesce(sum(round(peso, 6)) FILTER (WHERE en_serie AND NOT en_mascara), 0) AS v,
        coalesce(sum(round(peso, 6)) FILTER (WHERE en_serie), 0) AS vm,
        CASE WHEN {cond_tas} THEN count(*) FILTER (WHERE plataforma = 'Terra' AND NOT en_mascara) END AS t,
        CASE WHEN {cond_tas} THEN count(*) FILTER (WHERE plataforma = 'Aqua'  AND NOT en_mascara) END AS a,
        CASE WHEN {cond_tas} THEN count(*) FILTER (WHERE plataforma = 'S-NPP' AND NOT en_mascara) END AS s,
        count(*) FILTER (WHERE plataforma = 'NOAA-20' AND NOT en_mascara) AS n20,
        count(*) FILTER (WHERE en_serie AND en_mascara) AS xm,
        CASE WHEN (anio * 100 + mes) IN (SELECT ym FROM meses_inc) THEN 1 ELSE 0 END AS inc,
        CASE WHEN {tramo_mes_sql(nrt_ym)} = 'NP' THEN 1 ELSE 0 END AS prov
      FROM serie_p GROUP BY celda1, celda01, anio, mes ORDER BY celda1, celda01, anio, mes""")
    # --- daily: VIIRS of the series only (S-NPP <= 2018-03, NOAA-20 afterwards, NRT included) ---
    con.execute("""
      CREATE OR REPLACE TABLE diario AS
      SELECT celda1, celda01 AS c, CAST(acq_date_utc AS VARCHAR) AS d,
             count(*) FILTER (WHERE NOT en_mascara) AS v, count(*) AS vm,
             CAST(bool_or(tramo = 'noaa20_nrt') AS INTEGER) AS prov
      FROM serie WHERE tramo IN ('snpp', 'noaa20', 'noaa20_nrt') GROUP BY celda1, celda01, acq_date_utc
      ORDER BY celda1, celda01, acq_date_utc""")
    t3 = time.perf_counter()
    n_modis_nan = con.execute("SELECT count(*) FROM serie_p WHERE en_serie AND familia = 'MODIS' AND peso IS NULL").fetchone()[0]
    stats = {
        "filas_base": n_base,
        "filas_serie": con.execute("SELECT count(*) FROM serie WHERE en_serie").fetchone()[0],
        "filas_serie_en_mascara": con.execute("SELECT count(*) FROM serie WHERE en_serie AND en_mascara").fetchone()[0],
        "filas_mensual": con.execute("SELECT count(*) FROM mensual").fetchone()[0],
        "filas_diario": con.execute("SELECT count(*) FROM diario").fetchone()[0],
        "detecciones_modis_sin_peso": n_modis_nan,
        "datos_hasta": str(mx),
        "reserva_abierta": reserva_abierta,
        "nrt_desde": str(nrt_min),
        "tiempos_s": {"tabla_base": round(t1 - t0, 1), "pesos": round(t2 - t1, 1), "agregados": round(t3 - t2, 1)},
    }
    return {"nrt_ym": nrt_ym, "pesos": info_pesos, "stats": stats}


# ------------------------------------------------------------------------------------------------ writing per tile
def escribir_teselas(con: duckdb.DuckDBPyConnection, pais_dir: Path, sintetico: bool, teselas: list[str] | None, cm: str) -> dict:
    for sub in ("mensual", "diario", "puntos"):
        shutil.rmtree(pais_dir / sub, ignore_errors=True)   # only what this script generated before (app/data or data/...)
        (pais_dir / sub).mkdir(parents=True, exist_ok=True)
    todas = [r[0] for r in con.execute("SELECT DISTINCT celda1 FROM mensual ORDER BY 1").fetchall()]
    if teselas:
        todas = [t for t in todas if t in set(teselas)]
    assert todas, "no tiles to export"
    kv = (f"{{si: '{MARCA_SI}', synthetic: '{str(sintetico).lower()}', commit: '{cm}', "
          f"nota: 'weight: VIIRS 1; MODIS w (VIIRS-equivalent) or 1 if synthetic'}}")
    tramo_det = ("CASE tramo " + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in TRAMO_DET.items()) + " END")
    con_diario: list[str] = []
    con_puntos: list[str] = []
    for i, t in enumerate(todas, 1):
        assert re.fullmatch(r"-?\d+_-?\d+", t), t
        con.execute(f"""COPY (SELECT c, y, m, tramo, {num('v')} AS v, {num('vm')} AS vm, t, a, s, n20, xm, inc, prov
                        FROM mensual WHERE celda1 = '{t}' ORDER BY c, y, m)
                        TO '{sql_str(pais_dir / 'mensual' / (t + '.csv'))}' (FORMAT CSV, HEADER)""")
        n_d = con.execute(f"SELECT count(*) FROM diario WHERE celda1 = '{t}'").fetchone()[0]
        if n_d:
            con.execute(f"""COPY (SELECT c, d, v, vm, prov FROM diario WHERE celda1 = '{t}' ORDER BY c, d)
                            TO '{sql_str(pais_dir / 'diario' / (t + '.csv'))}' (FORMAT CSV, HEADER)""")
            con_diario.append(t)
        n_p = con.execute(f"SELECT count(*) FROM serie WHERE celda1 = '{t}' AND en_serie").fetchone()[0]
        if n_p:
            con.execute(f"""COPY (SELECT latitude AS lat, longitude AS lon, CAST(acq_date_utc AS VARCHAR) AS fecha_utc,
                                   strftime(acq_datetime_utc, '%H:%M') AS hora_utc, plataforma, procesamiento,
                                   round(peso, 6) AS peso, en_mascara, flag_multipaso, frp, confidence_raw AS confidence,
                                   "type" AS "type", {tramo_det} AS tramo
                            FROM serie_p WHERE celda1 = '{t}' AND en_serie
                            ORDER BY latitude, longitude, acq_datetime_utc, plataforma, procesamiento, frp, confidence_raw, "type", en_mascara, flag_multipaso, peso)
                            TO '{sql_str(pais_dir / 'puntos' / (t + '.parquet'))}'
                            (FORMAT PARQUET, COMPRESSION SNAPPY, PARQUET_VERSION V1, ROW_GROUP_SIZE 65536, KV_METADATA {kv})""")
            con_puntos.append(t)
        if i % 50 == 0 or i == len(todas):
            print(f"  tiles {i}/{len(todas)} (peak RSS {rss_mb()} MB)", flush=True)
    return {"teselas": todas, "teselas_diario": con_diario, "teselas_puntos": con_puntos}


def verificar_teselas(con: duckdb.DuckDBPyConnection, pais_dir: Path, teselas_p: list[str], teselas_d: list[str]) -> dict:
    """Rereads what was written and checks, tile by tile: point CSV = displayed count (RT-11) and daily = monthly (VIIRS)."""
    tipos = ("{'c':'VARCHAR','y':'INTEGER','m':'INTEGER','tramo':'VARCHAR','v':'DOUBLE','vm':'DOUBLE','t':'BIGINT','a':'BIGINT',"
             "'s':'BIGINT','n20':'BIGINT','xm':'BIGINT','inc':'INTEGER','prov':'INTEGER'}")
    celda = ("printf('%.1f_%.1f', floor(round(lat*100000)/10000)/10.0, floor(round(lon*100000)/10000)/10.0)")
    maxdif_v = 0.0
    mal = 0
    for t in teselas_p:
        m = sql_str(pais_dir / "mensual" / f"{t}.csv")
        p = sql_str(pais_dir / "puntos" / f"{t}.parquet")
        r = con.execute(f"""
          WITH pp AS (SELECT {celda} AS c, CAST(substr(fecha_utc, 1, 4) AS INTEGER) AS y, CAST(substr(fecha_utc, 6, 2) AS INTEGER) AS m,
                             coalesce(sum(peso) FILTER (WHERE NOT en_mascara), 0) AS v, coalesce(sum(peso), 0) AS vm,
                             count(*) FILTER (WHERE en_mascara) AS xm
                      FROM read_parquet('{p}') GROUP BY ALL),
               mm AS (SELECT c, y, m, v, vm, xm FROM read_csv('{m}', header = true, columns = {tipos}))
          SELECT count(*), coalesce(max(greatest(abs(coalesce(pp.v,0)-coalesce(mm.v,0)), abs(coalesce(pp.vm,0)-coalesce(mm.vm,0)))), 0),
                 count(*) FILTER (WHERE coalesce(pp.xm,0) <> coalesce(mm.xm,0))
          FROM pp FULL JOIN mm USING (c, y, m)
          WHERE abs(coalesce(pp.v,0)-coalesce(mm.v,0)) > 0.01 OR abs(coalesce(pp.vm,0)-coalesce(mm.vm,0)) > 0.01
             OR coalesce(pp.xm,0) <> coalesce(mm.xm,0)""").fetchone()
        mal += r[0]
        maxdif_v = max(maxdif_v, r[1])
        assert r[0] == 0, f"tile {t}: points and monthly differ in {r[0]} cell-months (RT-11)"
    for t in teselas_d:
        m = sql_str(pais_dir / "mensual" / f"{t}.csv")
        d = sql_str(pais_dir / "diario" / f"{t}.csv")
        r = con.execute(f"""
          WITH dd AS (SELECT c, CAST(substr(d, 1, 4) AS INTEGER) AS y, CAST(substr(d, 6, 2) AS INTEGER) AS m, sum(v) AS v, sum(vm) AS vm
                      FROM read_csv('{d}', header = true, columns = {{'c':'VARCHAR','d':'VARCHAR','v':'BIGINT','vm':'BIGINT','prov':'INTEGER'}}) GROUP BY ALL),
               mm AS (SELECT c, y, m, v, vm FROM read_csv('{m}', header = true, columns = {tipos}) WHERE tramo IN ('S','N','NP'))
          SELECT count(*) FROM dd FULL JOIN mm USING (c, y, m)
          WHERE abs(coalesce(dd.v,0)-coalesce(mm.v,0)) > 0.01 OR abs(coalesce(dd.vm,0)-coalesce(mm.vm,0)) > 0.01""").fetchone()
        assert r[0] == 0, f"tile {t}: daily and monthly differ in {r[0]} cell-months"
    return {"teselas_puntos_verificadas": len(teselas_p), "teselas_diario_verificadas": len(teselas_d),
            "celda_mes_incoherentes": mal, "max_dif_v": round(maxdif_v, 6)}


def tamanos(pais_dir: Path) -> dict:
    out: dict = {"total_bytes": 0, "por_tipo": {}}
    for sub in ("mensual", "diario", "puntos"):
        fs = sorted((p for p in (pais_dir / sub).glob("*") if p.is_file()), key=lambda p: p.stat().st_size, reverse=True)
        tot = sum(p.stat().st_size for p in fs)
        out["por_tipo"][sub] = {"archivos": len(fs), "bytes": tot, "max_bytes": fs[0].stat().st_size if fs else 0,
                                "max_archivo": fs[0].name if fs else None,
                                "mediana_bytes": fs[len(fs) // 2].stat().st_size if fs else 0}
        out["total_bytes"] += tot
    for nombre in ("contorno.geojson", "intervalos.json", "disponibilidad.json"):
        if (pais_dir / nombre).exists():
            out["total_bytes"] += (pais_dir / nombre).stat().st_size
    return out


# ------------------------------------------------------------------------------------------------ anti-leak audit
def auditar(raiz: Path, runs_dir: Path = RUNS) -> dict:
    """Walks ALL of app/data/ and fails on Terra/Aqua/S-NPP >= 2019-01-01 (rows or columns with a value) while the reserve is closed,
    on files > 15 MiB, or on inconsistencies. With a verdict (open reserve) it validates the other state: summary, label rule,
    sha256 of runs/EXP-NNN/verdict.json (in `runs_dir`) and non-empty t, a, s. Both states require the SI declaration and the license."""
    t0 = time.perf_counter()
    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false")
    rep: dict = {"archivos": 0, "bytes": 0, "paises": {}}
    for p in raiz.rglob("*"):
        if p.is_file():
            rep["archivos"] += 1
            rep["bytes"] += p.stat().st_size
            assert p.stat().st_size <= TOPE_BYTES, f"{p} exceeds 15 MiB ({p.stat().st_size})"
    man = json.loads((raiz / "manifest.json").read_text())
    abierta = man.get("verdict") is not None
    rep["reserva"] = "open" if abierta else "closed"
    # SI declaration and license (B-P4): required in both states
    assert man.get("si_assisted") is True, "manifest.si_assisted must be true (declaration of SI use)"
    assert isinstance(man.get("si_declaration"), str) and "SI" in man["si_declaration"], "manifest.si_declaration is missing"
    lic = raiz / "LICENSE-DATA.md"
    assert lic.is_file(), f"missing {lic} (run the exporter, or --refrescar-manifest)"
    txt_lic = lic.read_text(encoding="utf-8")
    for need in ("CC BY 4.0", "not endorsed by NASA", "SI-generated"):
        assert need in txt_lic, f"LICENSE-DATA.md must contain '{need}'"
    if abierta:
        validar_verdict_manifest(man, runs_dir)
        rep["verdict"] = {"exp": man["verdict"]["exp"], "etiquetas": {p: r["etiqueta_pais"] for p, r in man["verdict"]["paises"].items()}}
    for pais in PAISES:
        d = raiz / pais
        if not (d / "mensual").exists():
            continue
        ra: dict = {}
        assert bool(man["paises"].get(pais, {}).get("reserva_abierta", False)) == abierta, \
            f"{pais}: reserve state differs from manifest.verdict (export both countries in the same run)"
        mensual = sql_str(d / "mensual" / "*.csv")
        tipos = ("{'c':'VARCHAR','y':'INTEGER','m':'INTEGER','tramo':'VARCHAR','v':'DOUBLE','vm':'DOUBLE','t':'BIGINT','a':'BIGINT',"
                 "'s':'BIGINT','n20':'BIGINT','xm':'BIGINT','inc':'INTEGER','prov':'INTEGER'}")
        for f in (d / "mensual").glob("*.csv"):
            with f.open() as fh:
                assert fh.readline().strip() == COLS_MENSUAL, f"unexpected header in {f}"
        q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
        base = f"read_csv('{mensual}', header = true, columns = {tipos}, filename = true)"
        ra["mensual_filas"] = q(f"SELECT count(*) FROM {base}")
        if not abierta:
            assert q(f"SELECT count(*) FROM {base} WHERE y >= 2019 AND (t IS NOT NULL OR a IS NOT NULL OR s IS NOT NULL)") == 0, \
                "LEAK: t/a/s with a value in y >= 2019 (monthly)"
        else:
            assert q(f"SELECT count(*) FROM {base} WHERE y >= 2019 AND (t IS NULL OR a IS NULL OR s IS NULL)") == 0, \
                "reserve open (verdict) but t/a/s are empty in y >= 2019 (monthly): export again"
        assert q(f"SELECT count(*) FROM {base} WHERE y >= 2019 AND tramo NOT IN ('N', 'NP')") == 0, "LEAK: MODIS/S-NPP era in y >= 2019"
        assert q(f"SELECT count(*) FROM {base} WHERE (y*100+m) < 200012 OR y > 2026") == 0, "months out of range (Nov 2000 is out)"
        assert q(f"SELECT count(*) FROM {base} WHERE regexp_extract(filename, '([^/]+)\\.csv$', 1) <> "
                 f"printf('%d_%d', CAST(floor(CAST(split_part(c, '_', 1) AS DOUBLE)) AS BIGINT), "
                 f"CAST(floor(CAST(split_part(c, '_', 2) AS DOUBLE)) AS BIGINT))") == 0, "cell outside its tile (monthly)"
        ra["mensual_max_y"] = q(f"SELECT max(y) FROM {base}")
        ra["mensual_filas_y_ge_2019"] = q(f"SELECT count(*) FROM {base} WHERE y >= 2019")
        if (d / "diario").exists() and any((d / "diario").glob("*.csv")):
            for f in (d / "diario").glob("*.csv"):
                with f.open() as fh:
                    assert fh.readline().strip() == COLS_DIARIO, f"unexpected header in {f}"
            diario = sql_str(d / "diario" / "*.csv")
            dbase = (f"read_csv('{diario}', header = true, columns = {{'c':'VARCHAR','d':'VARCHAR','v':'BIGINT','vm':'BIGINT',"
                     f"'prov':'INTEGER'}}, filename = true)")
            ra["diario_filas"] = q(f"SELECT count(*) FROM {dbase}")
            assert q(f"SELECT count(*) FROM {dbase} WHERE d < '2012-01-20' OR d > '{CORTE}'") == 0, "daily out of the VIIRS range"
            assert q(f"SELECT count(*) FROM {dbase} WHERE prov = 1 AND d < '{man['paises'][pais]['nrt_desde']}'") == 0
        if (d / "puntos").exists() and any((d / "puntos").glob("*.parquet")):
            pun = sql_str(d / "puntos" / "*.parquet")
            cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{pun}')").fetchall()]
            assert cols == COLS_PUNTOS, f"unexpected point columns: {cols}"
            ra["puntos_filas"] = q(f"SELECT count(*) FROM read_parquet('{pun}')")
            assert q(f"SELECT count(*) FROM read_parquet('{pun}') WHERE plataforma IN ('Terra', 'Aqua', 'S-NPP') "
                     f"AND fecha_utc >= '{FECHA_RESERVA}'") == 0, "LEAK: Terra/Aqua/S-NPP points >= 2019-01-01"
            assert q(f"SELECT count(*) FROM read_parquet('{pun}') WHERE plataforma = 'S-NPP' AND fecha_utc >= '2018-04-01'") == 0, \
                "LEAK: S-NPP outside its series era"
            assert q(f"SELECT count(*) FROM read_parquet('{pun}') WHERE plataforma = 'NOAA-21'") == 0, "NOAA-21 is not part of the series"
            assert q(f"SELECT count(*) FROM read_parquet('{pun}') WHERE plataforma IN ('Terra', 'Aqua') AND fecha_utc >= '2012-01-01'") == 0, \
                "MODIS outside its series era"
            assert q(f"SELECT count(*) FROM read_parquet('{pun}') WHERE fecha_utc > '{CORTE}'") == 0
            ra["puntos_max_fecha_modis_s_npp"] = str(q(
                f"SELECT max(fecha_utc) FROM read_parquet('{pun}') WHERE plataforma IN ('Terra', 'Aqua', 'S-NPP')"))
            ra["puntos_en_mascara"] = q(f"SELECT count(*) FROM read_parquet('{pun}') WHERE en_mascara")
        rep["paises"][pais] = ra
    for jf in raiz.rglob("*.json"):
        json.loads(jf.read_text())            # every JSON of the tree must parse
    for gj in raiz.rglob("*.geojson"):
        assert json.loads(gj.read_text())["type"] == "FeatureCollection"
    rep["segundos"] = round(time.perf_counter() - t0, 1)
    return rep


# ------------------------------------------------------------------------------------------------ verdict (ADR-0005) y licencia
def buscar_verdict(runs_dir: Path, exp: str | None = None) -> Path | None:
    """Path of the single-test `verdict.json`, or None if it does not exist.

    src/nucleo/validacion_rt05.py writes `verdict.json` ONLY in test mode (dev mode writes verdict_dev.json, which is never read
    here). With several candidates and no `exp`, it refuses instead of guessing."""
    if exp:
        assert re.fullmatch(r"EXP-\d{3,}", exp), f"--verdict-exp must look like EXP-NNN: {exp}"
        p = runs_dir / exp / "verdict.json"
        assert p.is_file(), f"{p} does not exist"
        return p
    cands = sorted(runs_dir.glob("EXP-*/verdict.json"))
    assert len(cands) <= 1, f"several verdict.json files ({[str(c) for c in cands]}); choose one with --verdict-exp EXP-NNN"
    return cands[0] if cands else None


def resumir_metricas(ruta_verdict: Path, escalas: dict[str, str]) -> dict | None:
    """Key figures of the single test for the Method notes, read from `metricas.json` next to `verdict.json` (None if it is absent).

    Per country, on the published scale (`escalas`): cross kappa and twin kappa with their 95 % intervals and the paired ratio (P2),
    the baseline kappa (M1), the P2b shares, the P3 coverage of the deciding population and of both populations, and the P4 skill.
    Nothing is computed here: every number is copied from the file, whose sha256 is recorded, so the audit can recompute this summary."""
    mp = ruta_verdict.parent / "metricas.json"
    if not mp.is_file():
        return None
    mj = json.loads(mp.read_text(encoding="utf-8"))
    out: dict = {}
    for p, esc in escalas.items():
        E = (mj.get("paises") or {}).get(p, {}).get(esc)
        assert isinstance(E, dict) and "P2_P2b" in E and "P3_P4" in E, f"{mp}: no results for {p} on scale {esc}"
        P2 = E["P2_P2b"]
        P34 = E["P3_P4"]
        P3, P4 = P34["P3"], P34["P4"]
        pob = P3.get("poblaciones") or {}
        out[p] = {
            "escala": esc,
            "n_bloque_meses": P2["n_bloque_meses"], "n_bloques": P2["n_bloques"],
            "kappa_cruzado": P2["kappa_cruzado"], "kappa_gemelos": P2["kappa_gemelos"], "cociente_pareado": P2["cociente_pareado"],
            "kappa_cruzado_M1": (P2.get("kappa_cruzado_M1") or {}).get("punto"),
            "P2b": {k: P2["P2b"].get(k) for k in ("pct_indeterminado", "precision_unusual", "precision_typical", "cobertura_ic80_bloque")},
            "P3": {"poblacion_veredicto": P3.get("poblacion_veredicto"),
                   "cobertura": P3.get("cobertura_excluye_Shat_cero") if P3.get("poblacion_veredicto") == "excluye_s0" else P3.get("cobertura"),
                   "incluye_s0": pob.get("incluye_s0"), "excluye_s0": pob.get("excluye_s0"),
                   "n_excluidos_Shat_cero": P3.get("n_excluidos_Shat_cero")},
            "P4": {"skill": P4["skill"], "skill_ic95": P4["skill_ic95"]},
        }
    return {"fuente": f"runs/{ruta_verdict.parent.name}/metricas.json", "sha256": sha256(mp), "paises": out}


def resumir_verdict(vj: dict, ruta: Path, paises: list[str]) -> dict:
    """Summary of verdict.json for manifest.verdict: per-country booleans and the 'reliable' / 'indicative' label.

    Label rule (ADR-0005 7e/7f, ADR-0006, route I-05 point 3b): a country is 'reliable' only if P2 and P2b are both true on the
    published scale (E1c, or E1b if J2 failed: 7g-bis); anything else, including a test that was not computed, is 'indicative'.
    The app adds the size of the area (>= one 3-degree block) and the Terra-only era (always 'indicative').

    Fields copied as they are, with no influence on the labels: `veredicto.P3_poblacion` (population of the P3 coverage used by the
    verdict: incluye_s0 | excluye_s0) and, per country, `P5_era_terra_sola` (the SEPARATE Terra-only-era verdict; None when P5 was
    not run, as in the pre-registered single test while its threshold is null)."""
    assert vj.get("modo") == "prueba", f"{ruta}: mode {vj.get('modo')!r}; only the single test (mode 'prueba') opens the reserve"
    ver = vj.get("veredicto")
    assert isinstance(ver, dict) and isinstance(ver.get("por_pais"), dict), f"{ruta}: no veredicto.por_pais"
    assert ver.get("umbrales_fijados") is True, f"{ruta}: thresholds were not fixed (umbrales_fijados != true); not a valid verdict"
    por_pais: dict = {}
    for p in paises:
        R = ver["por_pais"].get(p)
        assert isinstance(R, dict), f"{ruta}: the verdict has no result for {p}"
        esc = R.get("escala_publicada_7gbis") or "E1c"
        E = R.get(esc) or {}
        p2, p2b = E.get("P2_bloque3"), E.get("P2b_7cbis_reliable")
        terra = R.get("etiqueta_terra_sola")
        if not (isinstance(terra, str) and terra.startswith("indicative")):
            terra = "indicative (Terra only)"        # the Terra-only era is never better than 'indicative'
        por_pais[p] = {"escala_publicada": esc, "P2": p2, "P2b": p2b, "P3": E.get("P3"), "P4": E.get("P4"),
                       "RT05_bloque3": E.get("RT05_bloque3"), "J1": R.get("J1"), "J2_bloque": R.get("J2_bloque"),
                       "etiqueta_pais": "reliable" if (p2 is True and p2b is True) else "indicative",
                       "etiqueta_terra_sola": terra, "clases_I05": R.get("clases_I05"),
                       "P5_era_terra_sola": R.get("P5_era_terra_sola")}
    return {"exp": ruta.parent.name, "fuente": f"runs/{ruta.parent.name}/verdict.json", "sha256": sha256(ruta), "modo": "prueba",
            "etiqueta": vj.get("etiqueta"), "umbrales_fijados": True, "regla_etiqueta": REGLA_ETIQUETA, "regla_ref": REGLA_REF,
            "min_celdas_aoi": MIN_CELDAS_BLOQUE, "P3_poblacion": ver.get("P3_poblacion"), "M1": ver.get("M1"), "paises": por_pais,
            "transferencia": ver.get("transferencia"),
            "metricas": resumir_metricas(ruta, {p: r["escala_publicada"] for p, r in por_pais.items()}), "si": MARCA_SI}


def sql_filtro_base(reserva_abierta: bool) -> str:
    """WHERE of the base table (the series + what the raw counts t, a, s need).

    Closed reserve: Terra/Aqua/S-NPP rows >= 2019-01-01 (and `reservado_prueba`) are excluded (ADR-0005). Open reserve (a verdict
    exists): standard Terra/Aqua/S-NPP rows of any date are kept; they only feed t, a, s (they are never in the series)."""
    if reserva_abierta:
        return ("NOT flag_pre_dic2000 AND plataforma <> 'NOAA-21' "
                "AND (en_serie OR (plataforma IN ('Terra', 'Aqua', 'S-NPP') AND procesamiento = 'estandar'))")
    return ("NOT flag_pre_dic2000 AND NOT reservado_prueba AND plataforma <> 'NOAA-21' "
            "AND (en_serie OR (plataforma IN ('Terra', 'Aqua', 'S-NPP') AND procesamiento = 'estandar' "
            f"AND acq_date_utc < DATE '{FECHA_RESERVA}'))")


def sql_cond_tas(reserva_abierta: bool) -> str:
    """Condition under which the monthly t, a, s are filled: always with an open reserve; only before 2019 otherwise."""
    return "TRUE" if reserva_abierta else f"anio < {FECHA_RESERVA[:4]}"


def copiar_licencia(raiz: Path) -> Path:
    """Copy the data-license template next to the data (app/data/LICENSE-DATA.md)."""
    assert PLANTILLA_LICENCIA.is_file(), f"missing template {PLANTILLA_LICENCIA}"
    destino = raiz / "LICENSE-DATA.md"
    shutil.copyfile(PLANTILLA_LICENCIA, destino)
    return destino


def campos_si(man: dict) -> None:
    """Declaration of SI use and license in the manifest (B-P4)."""
    man["si_assisted"] = True
    man["si_declaration"] = SI_DECLARATION
    man["licencia"] = dict(LICENCIA_DATOS)


def _canon(x) -> str:
    """Canonical JSON (sorted keys, NaN allowed) to compare two summaries without NaN != NaN and without key-order noise."""
    return json.dumps(x, sort_keys=True, ensure_ascii=False, allow_nan=True, separators=(",", ":"))


def _diferencias(a, b, ruta: str = "") -> list[str]:
    """Dotted paths where two JSON-like values differ (dicts are walked; lists and scalars are compared whole), for error messages."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{ruta}{k} ({'missing in manifest' if k not in a else 'not in the recomputed summary'})")
            else:
                out += _diferencias(a[k], b[k], f"{ruta}{k}.")
        return out
    return [] if _canon(a) == _canon(b) else [ruta.rstrip(".") or "(root)"]


def validar_verdict_manifest(man: dict, runs_dir: Path) -> None:
    """Checks the summary of an OPEN reserve: schema, label rule, the sha256 of the verdict file in runs/ AND the summary RECOMPUTED
    from that file with resumir_verdict, which must equal manifest.verdict (a matching sha256 alone only proves which file was
    cited, not that the summary says what the file says; arbitrary file content cannot pass because resumir_verdict rejects it)."""
    v = man["verdict"]
    assert isinstance(v, dict), "manifest.verdict must be null or an object"
    assert not man.get("synthetic"), "a SYNTHETIC export can never carry a verdict"
    for k in ("exp", "sha256", "modo", "umbrales_fijados", "regla_etiqueta", "min_celdas_aoi", "paises"):
        assert k in v, f"manifest.verdict lacks '{k}'"
    assert v["modo"] == "prueba" and v["umbrales_fijados"] is True, "manifest.verdict is not a fixed-threshold single test"
    assert isinstance(v["min_celdas_aoi"], int) and v["min_celdas_aoi"] >= 1
    f = runs_dir / v["exp"] / "verdict.json"
    assert f.is_file(), (f"manifest.verdict cites {f}, which does not exist. The audit of an open reserve recomputes the summary from "
                         f"runs/EXP-NNN/verdict.json and metricas.json, so a checkout without runs/ must carry both files byte for byte "
                         f"(`python src/exportar_demo.py --listar-runs-auditoria` lists them)")
    if v.get("metricas") is not None:
        mp = f.parent / "metricas.json"
        assert mp.is_file(), (f"manifest.verdict.metricas cites {mp}, which does not exist (the audit recomputes the key figures from it; "
                              f"`python src/exportar_demo.py --listar-runs-auditoria` lists the files a checkout must carry)")
    assert sha256(f) == v["sha256"], f"{f} changed after the export (sha256 differs): export again"
    for p, e in man["paises"].items():
        if not e.get("disponible"):
            continue
        R = v["paises"].get(p)
        assert isinstance(R, dict), f"manifest.verdict has no result for {p}"
        assert R.get("etiqueta_pais") in ("reliable", "indicative"), f"{p}: etiqueta_pais must be reliable | indicative"
        assert str(R.get("etiqueta_terra_sola", "")).startswith("indicative"), f"{p}: the Terra-only era is always 'indicative'"
        debe = "reliable" if (R.get("P2") is True and R.get("P2b") is True) else "indicative"
        assert R["etiqueta_pais"] == debe, f"{p}: label {R['etiqueta_pais']} does not follow the rule (P2 and P2b -> reliable)"
    # Recompute: the same function the exporter used, over the file the manifest cites (both countries, as in the export).
    try:
        vj = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(vj, dict), "the top level is not a JSON object"
        recalculado = resumir_verdict(vj, f, list(PAISES))
    except Exception as ex:  # noqa: BLE001  not JSON, or content that is not a valid single-test verdict (mode, thresholds, results)
        raise AssertionError(f"manifest.verdict cites {f}, which is not a valid single-test verdict ({type(ex).__name__}: {ex})") from ex
    if _canon(recalculado) != _canon(v):
        dif = _diferencias(v, recalculado)
        raise AssertionError(f"manifest.verdict does not match the summary recomputed from {f} ({len(dif)} difference(s): "
                             f"{'; '.join(dif[:6])}): export again")


def archivos_run_de_auditoria(man: dict) -> list[str]:
    """Files under runs/ (relative to the repository root) that the audit of an OPEN reserve reads, taken from manifest.verdict:
    the verdict itself and the key-figures file next to it (empty list while the reserve is closed). A checkout without the rest of
    runs/ (the public repository) must carry exactly these, unchanged byte for byte: the audit compares their sha256 and recomputes
    the summary from them. The other files of the run (informe.md, manifiesto.json) are for human readers."""
    v = man.get("verdict")
    if not isinstance(v, dict):
        return []
    out = []
    for ruta in (v.get("fuente"), (v.get("metricas") or {}).get("fuente")):
        if ruta:
            assert re.fullmatch(r"runs/EXP-\d{3,}/(verdict|metricas)\.json", ruta), f"unexpected path in manifest.verdict: {ruta}"
            out.append(ruta)
    return out


def verificar_congelado(dir_run: Path, raiz_repo: Path = RAIZ) -> dict | None:
    """Frozen-code check of a published single test; it needs no data, so it runs in the public checkout too.

    Compares, for the run in `dir_run` (runs/EXP-NNN): the SHA-256 of the src/nucleo/ tree (sorted *.py, relative path + content hash, the
    same rule as src/nucleo/validacion_rt05.py) and of config/validacion.yaml with (1) the hashes registered in config/validacion.hashes.json
    and (2) the ones the run recorded in its own manifiesto.json, and that the run started from the tagged state (tag prereg-v1, clean tree).
    It proves the code in this checkout is the code the single test ran, not that the test can be re-run (that needs raw data and the
    guard refuses a second run). Returns None if the hashes file or the run manifest is absent (nothing to compare)."""
    hj, mf = raiz_repo / "config" / "validacion.hashes.json", dir_run / "manifiesto.json"
    if not (hj.is_file() and mf.is_file()):
        return None
    reg, man = json.loads(hj.read_text(encoding="utf-8")), json.loads(mf.read_text(encoding="utf-8"))
    det = {p.relative_to(raiz_repo).as_posix(): sha256(p)
           for p in sorted((raiz_repo / "src" / "nucleo").rglob("*.py")) if "__pycache__" not in p.parts}
    arbol = hashlib.sha256("".join(f"{k}\0{v}\n" for k, v in det.items()).encode()).hexdigest()
    cfg = sha256(raiz_repo / "config" / "validacion.yaml")
    assert arbol == reg.get("arbol_src_nucleo"), "the src/nucleo/ tree differs from the hash frozen in config/validacion.hashes.json"
    assert arbol == man.get("arbol_src_nucleo"), f"the src/nucleo/ tree differs from the one {dir_run.name} ran with (manifiesto.json)"
    assert cfg == reg.get("config_yaml"), "config/validacion.yaml differs from the hash frozen in config/validacion.hashes.json"
    assert cfg == (man.get("entradas_sha256") or {}).get("config/validacion.yaml"), f"config/validacion.yaml differs from the one {dir_run.name} ran with"
    guarda = man.get("guarda") or {}
    assert guarda.get("tag") == "prereg-v1" and man.get("dirty") is False, f"{dir_run.name} did not start from the tagged, clean state"
    return {"arbol_src_nucleo": arbol, "archivos_src_nucleo": len(det), "config_yaml": cfg, "tag": guarda["tag"],
            "commit_tag": guarda.get("commit_tag"), "commit_de_la_corrida": man.get("commit"), "arbol_limpio": True}


def auditar_sin_app_data(raiz: Path, runs_dir: Path) -> dict:
    """`--solo-auditar` in a checkout that has NO exported app/data (the public main branch: app/data is built by scripts/reproducir.sh and
    published on the gh-pages branch). Skips what needs those tiles (the anti-leak walk, manifest <-> verdict) and says so; checks what the
    checkout does carry: the published verdict (mode, fixed thresholds, results, key figures recomputed into a summary) and the frozen code."""
    rep: dict = {"parcial": True, "sin_manifest": str(raiz / "manifest.json"),
                 "saltado": ["anti-leak walk over app/data tiles (needs the exported app/data: run scripts/reproducir.sh)",
                             "manifest.verdict <-> verdict.json comparison (needs app/data/manifest.json)"]}
    vp = buscar_verdict(runs_dir)
    if vp is None:
        rep["veredicto_publicado"] = None
        rep["nota"] = "no runs/EXP-*/verdict.json in this checkout: nothing else to verify"
        return rep
    resumen = resumir_verdict(json.loads(vp.read_text(encoding="utf-8")), vp, list(PAISES))
    rep["veredicto_publicado"] = {
        "exp": resumen["exp"], "sha256_verdict": resumen["sha256"], "sha256_metricas": (resumen.get("metricas") or {}).get("sha256"),
        "etiquetas": {p: r["etiqueta_pais"] for p, r in resumen["paises"].items()},
        "escala_publicada": {p: r["escala_publicada"] for p, r in resumen["paises"].items()}}
    if runs_dir.resolve() == RUNS.resolve():
        rep["congelado"] = verificar_congelado(vp.parent)
    return rep


def resumen_huecos_modis(disp_csv: Path | None = None, firms_csv: Path | None = None) -> dict | None:
    """Cross of two lists of MODIS platform-days without data, for the Method notes (manifest.huecos_modis); None if a file is missing.

    - our availability table (`disponibilidad_plataforma_dia.csv`, 2000-11-01 to 2018-12-31): the days marked `sin_datos`, split by the
      source of the flag (`regla_datos` = our data rule, no official notice behind it; `aviso_oficial` = official outage notice);
    - the FIRMS missing-data table of the MODIS standard product (`MODIS_SP.csv`: availability metadata, not detections).
    Reported: how many of the data-rule days FIRMS also lists, which ones it does not, and the days FIRMS lists inside the range of our
    table that our table does not flag (all of them Terra, Mar-Apr 2002 at the time of writing). Days >= 2019 never enter (anti-leak)."""
    import pandas as pd

    disp_csv = disp_csv or (PROC / "disponibilidad_plataforma_dia.csv")
    firms_csv = firms_csv or (RAIZ / "data" / "raw" / "firms" / "missing_data" / "MODIS_SP.csv")
    if not (disp_csv.is_file() and firms_csv.is_file()):
        return None
    d = pd.read_csv(disp_csv, dtype={"sin_datos": str, "fuente": str})
    d["sd"] = d["sin_datos"].str.lower().eq("true")
    assert d["fecha"].max() < FECHA_RESERVA, "the availability table must not go past 2018-12-31"
    sd = d[d["sd"]]
    f = pd.read_csv(firms_csv)
    f["plat"] = f["satelite_texto"].str.extract(r"^(Terra|Aqua)")[0]
    assert f["plat"].notna().all(), "FIRMS missing-data row with an unknown MODIS platform"
    f = f[f["fecha"] < FECHA_RESERVA]
    en_firms = set(zip(f["plat"], f["fecha"]))
    regla = sd[sd["fuente"] == "regla_datos"]
    en = [(r.plataforma, r.fecha) for r in regla.itertuples() if (r.plataforma, r.fecha) in en_firms]
    fuera = [[r.plataforma, r.fecha] for r in regla.itertuples() if (r.plataforma, r.fecha) not in en_firms]
    marcados = set(zip(sd["plataforma"], sd["fecha"]))
    sin_marca = sorted(x for x in en_firms if x not in marcados and d["fecha"].min() <= x[1] <= d["fecha"].max())

    def rangos(fechas: list[str]) -> list[list[str]]:
        out: list[list[str]] = []
        for x in fechas:
            if out and (pd.Timestamp(x) - pd.Timestamp(out[-1][1])).days == 1:
                out[-1][1] = x
            else:
                out.append([x, x])
        return out

    firms_sin_marca = {plat: rangos([x[1] for x in sin_marca if x[0] == plat]) for plat in ("Terra", "Aqua")}
    return {
        "fuente_tabla": "data/processed/disponibilidad_plataforma_dia.csv", "fuente_firms": "data/raw/firms/missing_data/MODIS_SP.csv",
        "consulta_firms_utc": str(f["consulta_utc"].iloc[0]), "sha256_respuesta_firms": str(f["sha256_respuesta"].iloc[0]),
        "regla_datos": {"dias": int(len(regla)), "terra": int((regla["plataforma"] == "Terra").sum()), "aqua": int((regla["plataforma"] == "Aqua").sum()),
                        "en_firms_missing_data": len(en), "no_en_firms_missing_data": len(fuera), "no_en_firms": fuera},
        "firms_sin_marcar_en_tabla": {"dias": len(sin_marca), "terra": firms_sin_marca["Terra"], "aqua": firms_sin_marca["Aqua"]},
        "nota": ("Days listed by FIRMS as missing inside the date range of our availability table that the table does not flag. Before "
                 "Jul 2002 only official notices are flagged (the data rule needs a second MODIS platform)."),
    }


def refrescar_manifest(raiz: Path, runs_dir: Path) -> dict:
    """Light mode: adds to an already exported manifest the fields created after that export (SI declaration, license) and copies
    LICENSE-DATA.md. No table is recomputed. Only while the reserve is closed: opening it needs a full export."""
    assert buscar_verdict(runs_dir) is None, "verdict.json exists: export both countries again (--pesos real --pais ambos) to open the reserve"
    mp = raiz / "manifest.json"
    assert mp.is_file(), f"missing {mp}"
    man = json.loads(mp.read_text())
    assert man.get("verdict") is None, "the manifest already carries a verdict: do a full export"
    campos_si(man)
    man["manifest_refrescado_utc"] = ahora_utc()
    tmp = mp.with_name(mp.name + ".tmp")
    tmp.write_text(json.dumps(man, ensure_ascii=False, indent=1))
    tmp.replace(mp)
    copiar_licencia(raiz)
    return man


# ------------------------------------------------------------------------------------------------ manifest
def actualizar_manifest(raiz: Path, entradas: dict[str, dict], exp: list[str], cm: str, sucio: bool,
                        verdict: dict | None = None) -> dict:
    mp = raiz / "manifest.json"
    man = json.loads(mp.read_text()) if mp.exists() else {"paises": {}}
    man.update({"version": None, "generado_utc": ahora_utc(), "commit": cm, "commit_con_cambios_sin_commit": sucio,
                "contrato": 1, "si": MARCA_SI,
                "metodo": {"adr": METODO_ADR, "exp": sorted(set(man.get("metodo", {}).get("exp", []) + exp
                                                                   + ([verdict["exp"]] if verdict else [])))},
                "verdict": verdict})
    campos_si(man)
    huecos = resumen_huecos_modis()
    if huecos is not None:
        man["huecos_modis"] = huecos
    for p, e in entradas.items():
        man["paises"][p] = e
    disp = [v for v in man["paises"].values() if v.get("disponible")]
    assert disp, "no country exported"
    for p, v in man["paises"].items():
        if v.get("disponible"):
            assert bool(v.get("reserva_abierta", False)) == (verdict is not None), \
                f"{p}: reserve state differs from the verdict (with a verdict.json, export both countries in the same run)"
    man["synthetic"] = any(v.get("synthetic") for v in disp)
    man["datos_hasta"] = min(v["datos_hasta"] for v in disp)
    man["version"] = f"{man['generado_utc'][:10]}.{cm}" + ("-synthetic" if man["synthetic"] else "")
    if man["synthetic"]:
        man["banner"] = BANNER_SINT
        (raiz / "SYNTHETIC.txt").write_text(BANNER_SINT + "\n" + MARCA_SI + "\n")
    else:
        man.pop("banner", None)
        (raiz / "SYNTHETIC.txt").unlink(missing_ok=True)
    mp.write_text(json.dumps(man, ensure_ascii=False, indent=1))
    return man


def aoi_con_celdas(pais: str) -> list[dict]:
    out = []
    for a in AOI_PREDEF[pais]:
        b = snap_bbox(a["bbox"])
        out.append({**a, "bbox_celdas": b, "n_celdas": round((b[2] - b[0]) * 10) * round((b[3] - b[1]) * 10)})
    return out


# ------------------------------------------------------------------------------------------------ principal
def exportar_pais(pais: str, a: argparse.Namespace, raiz_salida: Path, cm: str, sucio: bool, verdict: dict | None = None) -> dict:
    t_ini = time.perf_counter()
    sintetico = a.pesos == "synthetic"
    reserva_abierta = verdict is not None and not sintetico      # a SYNTHETIC export never opens the reserve
    pais_dir = raiz_salida / pais
    pais_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{pais}] pesos={a.pesos}  output={pais_dir}", flush=True)
    teselas = [t.strip() for t in a.teselas.split(",")] if a.teselas else None

    cont = construir_contorno(pais, pais_dir / "contorno.geojson")
    print(f"[{pais}] contorno.geojson {cont['bytes']/1024:.0f} KiB ({cont['partes_conservadas']}/{cont['partes_originales']} parts) "
          f"bbox={cont['bbox']}", flush=True)

    con = conectar(TMP / f"export_{pais}.duckdb")
    # nrt_ym depends on the data: disponibilidad.json needs meses_inc already, and nrt_ym is only used for its header.
    nrt_min, = con.execute(f"""SELECT min(acq_date_utc) FROM read_parquet('{sql_str(PROC / f'deteccion_{pais}.parquet')}')
                               WHERE tramo = 'noaa20_nrt'""").fetchone()
    nrt_ym_pre = nrt_min.year * 100 + nrt_min.month
    datos_hasta_pre = str(con.execute(f"""SELECT max(acq_date_utc) FROM read_parquet('{sql_str(PROC / f'deteccion_{pais}.parquet')}')
                                          WHERE en_serie""").fetchone()[0])
    disp_json, meses_inc = construir_disponibilidad(pais, pais_dir / "disponibilidad.json", datos_hasta_pre, nrt_ym_pre)
    print(f"[{pais}] disponibilidad.json: {len(disp_json['meses_incompletos'])} incomplete months (R1) + Jan-2012 partial", flush=True)

    prep = preparar(con, pais, a.pesos, meses_inc, teselas, Path(a.nucleo_path) if a.nucleo_path else None, reserva_abierta)
    assert prep["nrt_ym"] == nrt_ym_pre
    st = prep["stats"]
    print(f"[{pais}] series={st['filas_serie']:,} rows (in mask {st['filas_serie_en_mascara']:,}); monthly={st['filas_mensual']:,}; "
          f"daily={st['filas_diario']:,}; times={st['tiempos_s']}  peak RSS {rss_mb()} MB", flush=True)

    t0 = time.perf_counter()
    tes = escribir_teselas(con, pais_dir, sintetico, teselas, cm)
    t_escr = time.perf_counter() - t0
    ver = verificar_teselas(con, pais_dir, tes["teselas_puntos"], tes["teselas_diario"])
    print(f"[{pais}] reread verification: {ver}", flush=True)

    # intervalos.json
    if sintetico:
        iv = {"synthetic": True, "placeholder": True, "pais": pais, "si": MARCA_SI,
              "nota": ("SYNTHETIC placeholder: lane A's intervalos_<pais>.json is used with --pesos real. These numbers are NOT "
                       "intervals; the app must render them as 'SYNTHETIC' and not as results."),
              "ic80_multiplicativo_placeholder": {"T": {"1deg": [0.5, 2.0], "pais": [0.8, 1.25], "aoi": [0.6, 1.7]},
                                                  "TA": {"1deg": [0.6, 1.7], "pais": [0.85, 1.2], "aoi": [0.7, 1.5]}}}
        (pais_dir / "intervalos.json").write_text(json.dumps(iv, ensure_ascii=False, indent=1))
        iv_origen = None
    else:
        sys.path.insert(0, str(Path(a.nucleo_path) if a.nucleo_path else (RAIZ / "src")))
        from nucleo import factores as FA  # noqa: PLC0415
        iv_origen = FA.ruta_intervalos(pais)
        assert iv_origen.exists(), f"missing {iv_origen}"
        shutil.copyfile(iv_origen, pais_dir / "intervalos.json")

    tam = tamanos(pais_dir)
    for sub, v in tam["por_tipo"].items():
        assert v["max_bytes"] <= TOPE_BYTES, f"{sub}: file {v['max_archivo']} of {v['max_bytes']} B exceeds 15 MiB"

    entradas = {f"data/processed/deteccion_{pais}.parquet": sha256(PROC / f"deteccion_{pais}.parquet"),
                "data/processed/disponibilidad_plataforma_dia.csv": sha256(PROC / "disponibilidad_plataforma_dia.csv"),
                "data/raw/fronteras/ne_10m_admin_0_countries.zip": sha256(NE)}
    if iv_origen:
        entradas[str(iv_origen.relative_to(RAIZ))] = sha256(iv_origen)
        fpar = PROC / f"factores_{pais}_{VENTANA_CAL[0]}_{VENTANA_CAL[1]}.parquet"
        if fpar.exists():
            entradas[str(fpar.relative_to(RAIZ))] = sha256(fpar)
    segundos = round(time.perf_counter() - t_ini, 1)
    exp_man = {"id": f"export_demo_{pais}", "comando": a.comando, "commit": cm, "commit_con_cambios_sin_commit": sucio,
               "exportador_sha256": sha256(Path(__file__).resolve()),
               "semilla": None, "nota_semilla": "deterministic (no randomness)", "si": MARCA_SI, "fecha_utc": ahora_utc(),
               "reserva_abierta": reserva_abierta, "verdict": ({"exp": verdict["exp"], "sha256": verdict["sha256"]} if reserva_abierta else None),
               "pesos": prep["pesos"], "synthetic": sintetico, "entradas_sha256": entradas, "estadisticas": st,
               "verificacion_relectura": ver, "tamanos": tam, "segundos_total": segundos, "segundos_escritura": round(t_escr, 1),
               "rss_pico_mb": rss_mb(), "contorno": cont, "disponibilidad": {"meses_incompletos": len(disp_json["meses_incompletos"])},
               "duckdb": duckdb.__version__, "memory_limit": "600MB", "threads": 2}
    (pais_dir / "export_manifiesto.json").write_text(json.dumps(exp_man, ensure_ascii=False, indent=1, default=str))

    aoi = aoi_con_celdas(pais)
    entrada = {"nombre": NOMBRE[pais], "disponible": True, "synthetic": sintetico, "pesos": a.pesos, "reserva_abierta": reserva_abierta,
               "bbox": cont["bbox"],
               "teselas": tes["teselas"], "teselas_diario": tes["teselas_diario"], "teselas_puntos": tes["teselas_puntos"],
               "aoi_predef": aoi, "datos_hasta": st["datos_hasta"], "nrt_desde": st["nrt_desde"],
               "inicio_serie": "2000-12-01", "generado_utc": exp_man["fecha_utc"],
               "export": {"bytes_total": tam["total_bytes"], "filas_mensual": st["filas_mensual"], "filas_diario": st["filas_diario"],
                          "filas_puntos": st["filas_serie"]}}
    con.close()
    if not a.conservar_tmp:
        for ext in ("", ".wal"):
            Path(str(TMP / f"export_{pais}.duckdb") + ext).unlink(missing_ok=True)
        shutil.rmtree(TMP / "spill", ignore_errors=True)
    return {"entrada": entrada, "exp": exp_man}


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--_contorno":          # uso interno: subproceso de construir_contorno
        print(json.dumps(_contorno_directo(argv[1], Path(argv[2]))))
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pesos", choices=("synthetic", "real"), default=None, help="required unless --solo-auditar, --refrescar-manifest or --listar-runs-auditoria")
    ap.add_argument("--pais", choices=(*PAISES, "ambos"), default="mexico")
    ap.add_argument("--salida", default=str(SALIDA_DEFECTO), help="default app/data; in tests, a subdirectory of data/ or runs/")
    ap.add_argument("--teselas", default=None, help="list 'lat_lon,lat_lon' (tests only); default all")
    ap.add_argument("--exp", default="", help="method EXP ids, comma-separated (recorded in manifest.metodo.exp)")
    ap.add_argument("--nucleo-path", dest="nucleo_path", default=None, help="directory with the 'nucleo' package (default src/)")
    ap.add_argument("--conservar-tmp", action="store_true")
    ap.add_argument("--solo-auditar", action="store_true", help="only walks the output and runs the anti-leak audit")
    ap.add_argument("--verdict-exp", dest="verdict_exp", default=None,
                    help="EXP-NNN whose runs/EXP-NNN/verdict.json opens the reserve (needed only if there are several)")
    ap.add_argument("--runs-dir", dest="runs_dir", default=str(RUNS),
                    help="TESTS ONLY: directory with EXP-*/verdict.json; a non-default one forbids writing to app/data")
    ap.add_argument("--listar-runs-auditoria", dest="listar_runs", action="store_true",
                    help="prints, one per line, the files under runs/ that the audit of the open reserve reads (nothing while it is closed)")
    ap.add_argument("--refrescar-manifest", action="store_true",
                    help="light mode: adds SI declaration + license to an exported manifest (no table is recomputed; no verdict.json)")
    a = ap.parse_args(argv)
    if not a.solo_auditar and not a.refrescar_manifest and not a.listar_runs and not a.pesos:
        ap.error("--pesos is required (synthetic | real)")
    a.comando = "python src/exportar_demo.py " + " ".join(argv)
    raiz_salida = Path(a.salida).resolve()
    permitidos = [RAIZ / "app" / "data", RAIZ / "data", RAIZ / "runs"]
    assert any(raiz_salida == p or p in raiz_salida.parents for p in permitidos), f"--salida must be in app/data, data/ or runs/: {raiz_salida}"
    runs_dir = Path(a.runs_dir).resolve()
    if runs_dir != RUNS.resolve():                 # fictitious verdicts (tests) can never reach the real app/data
        assert any(runs_dir == p or p in runs_dir.parents for p in (RAIZ / "runs", RAIZ / "data")), f"--runs-dir must be in runs/ or data/: {runs_dir}"
        assert not (raiz_salida == SALIDA_DEFECTO.resolve() or SALIDA_DEFECTO.resolve() in raiz_salida.parents), \
            "a non-default --runs-dir (tests) cannot be combined with an app/data output"
    if a.listar_runs:
        for ruta in archivos_run_de_auditoria(json.loads((raiz_salida / "manifest.json").read_text())):
            print(ruta)
        return 0
    if a.solo_auditar:
        if not (raiz_salida / "manifest.json").is_file():          # public main branch: no exported app/data
            rep = auditar_sin_app_data(raiz_salida, runs_dir)
            print(f"AUDIT PARTIAL: {raiz_salida.relative_to(RAIZ) if RAIZ in raiz_salida.parents else raiz_salida}/manifest.json does not exist "
                  f"(this checkout carries no exported app/data); skipped: {'; '.join(rep['saltado'])}", flush=True)
            print("AUDIT PARTIAL OK (published verdict and frozen code only):", json.dumps(rep, ensure_ascii=False, indent=1))
            return 0
        rep = auditar(raiz_salida, runs_dir)
        if rep.get("verdict") and runs_dir.resolve() == RUNS.resolve():     # frozen code of the published single test (no data needed)
            rep["congelado"] = verificar_congelado(RUNS / rep["verdict"]["exp"])
        print("AUDIT OK:", json.dumps(rep, ensure_ascii=False, indent=1))
        return 0
    if a.refrescar_manifest:
        refrescar_manifest(raiz_salida, runs_dir)
        rep = auditar(raiz_salida, runs_dir)
        print("MANIFEST REFRESHED + AUDIT OK:", json.dumps(rep, ensure_ascii=False, indent=1))
        return 0
    # The reserve opens only with the single-test verdict.json; a SYNTHETIC export never reads it.
    vpath = None if a.pesos == "synthetic" else buscar_verdict(runs_dir, a.verdict_exp)
    if vpath is not None:
        assert a.pais == "ambos", "verdict.json exists: export both countries in the same run (--pais ambos)"
        assert not a.teselas, "verdict.json exists: a partial export (--teselas) cannot open the reserve"
        verdict = resumir_verdict(json.loads(vpath.read_text()), vpath, list(PAISES))
        print(f"[verdict] {verdict['fuente']} (sha256 {verdict['sha256'][:12]}): reserve OPEN; labels "
              f"{ {p: r['etiqueta_pais'] for p, r in verdict['paises'].items()} }", flush=True)
    else:
        verdict = None
    cm, sucio = commit()
    paises = list(PAISES) if a.pais == "ambos" else [a.pais]
    exp = [e.strip() for e in a.exp.split(",") if e.strip()]
    raiz_salida.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    entradas: dict[str, dict] = {}
    mp = raiz_salida / "manifest.json"
    previo = json.loads(mp.read_text())["paises"] if mp.exists() else {}
    for p in PAISES:
        if p in paises:
            entradas[p] = exportar_pais(p, a, raiz_salida, cm, sucio, verdict)["entrada"]
        elif not previo.get(p, {}).get("disponible"):
            # Country not exported yet: the app still needs its outline, box and AOIs (disponible=false -> "outside processed coverage")
            c = construir_contorno(p, raiz_salida / p / "contorno.geojson")
            entradas[p] = {"nombre": NOMBRE[p], "disponible": False, "synthetic": None, "bbox": c["bbox"], "teselas": [],
                           "aoi_predef": aoi_con_celdas(p), "nota": "not exported yet (no data files for this country)"}
    man = actualizar_manifest(raiz_salida, entradas, exp, cm, sucio, verdict)
    copiar_licencia(raiz_salida)
    rep = auditar(raiz_salida, runs_dir)
    print("ANTI-LEAK AUDIT OK:", json.dumps(rep, ensure_ascii=False), flush=True)
    print(f"TOTAL {time.perf_counter() - t0:.1f} s · peak RSS {rss_mb()} MB · manifest.synthetic={man['synthetic']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
