#!/usr/bin/env python3
"""Genera tests/paridad_marca.json: casos para la paridad Python ↔ JS de la marca U1 + I2 (ADR-0006 6c-q).

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Casos (v2, integración con src/nucleo/factores.py real; solo datos ≤ 2018-12-31):
  A) REAL observado (3 AOI × 12 meses × 2012–2018): serie VIIRS mostrada (S-NPP estándar 2012-02 → 2018-03, NOAA-20
     estándar 2018-04 → 2018-12), fuera de máscara, AOI = celdas 0.1° cuyo centro cae en la caja. Base = mismo mes
     calendario en los DEMÁS años 2012–2018 (ene-2012 fuera; N = 6, o 5 en enero). Sin intervalo (lo = hi = null).
     El subconjunto 2018 es el caso "3 AOI × 12 meses" de ADR-0006 §5.
  B) REAL armonizado (3 AOI × 12 meses × {2011 Terra+Aqua, 2001 Terra sola}): Ŝ = Σ pesos_modis (factores finales
     2012-02 → 2018-12) de las detecciones MODIS estándar fuera de máscara en la AOI; IC80 = Ŝ·intervalo(pais, Ŝ, tramo,
     'aoi') de intervalos_<pais>.json; base = mismo mes 2012–2018 VIIRS (N = 7, o 6 en enero). Mes con algún día sin
     ninguna plataforma MODIS (relojes_dia) → valor null (incomplete). Ŝ = 0 → hi = Infinity.
  C) SYNTHETIC — bordes: empates, igualdad con el umbral, ceros (p10 = 0), mediana = 5 exacta, N = 13 (interpolación),
     N = 1, base vacía, valor NaN (incomplete), intervalo infinito, y casos de "temporada inusual" y año de fuego.
  D) SYNTHETIC — EMPATES EXACTOS con el umbral interpolado (v3, bloqueante B1 del gate O-2): N = 13 y N = 14, p10 y
     p90, con el valor o un extremo del IC80 IGUAL al cuantil tipo 6 exacto (enteros, rejilla de 0.25 y el double más
     cercano a un umbral no representable). Igual al umbral → no se marca (ADR-0006 paso 2). La referencia Python
     decide con Fraction (src/nucleo/validacion_marca.py), igual que app/js/marca.js.
Anti-fuga: solo lee fechas ≤ 2018-12-31 (assert); MODIS solo ≤ 2011; nada reservado (≥ 2019) se toca.

Uso: flock data/.pesado.lock .venv/bin/python tests/paridad_marca_generar.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
from nucleo import factores as FZ  # noqa: E402
from nucleo import validacion_marca as VM  # noqa: E402

SALIDA = RAIZ / "tests/paridad_marca.json"
AOIS = {  # (pais, lat_min, lat_max, lon_min, lon_max) — cajas de demo (ADR-0010) y la del sondeo S-08
    "puebla_popocatepetl_MX": ("mexico", 17.85, 20.85, -99.1, -96.7),
    "bahia_blanca_AR": ("argentina", -40.0, -37.0, -64.5, -61.0),
    "delta_parana_AR": ("argentina", -34.5, -32.5, -60.8, -58.3),
}
ANIOS_VIIRS = list(range(2012, 2019))
ANIOS_MODIS = {2011: "TA", 2001: "T"}   # año armonizado → tramo del intervalo (era del mes, ADR-0006 I2)
FMAX = "2018-12-31"
BASE_NOMBRE = "2012–2018 VIIRS"


def _caja(la0, la1, lo0, lo1) -> str:
    return (f"floor(latitude * 10) / 10 + 0.05 BETWEEN {la0} AND {la1} "
            f"AND floor(longitude * 10) / 10 + 0.05 BETWEEN {lo0} AND {lo1}")


def serie_aoi(con, pais, la0, la1, lo0, lo1) -> dict:
    pq = RAIZ / f"data/processed/deteccion_{pais}.parquet"
    q = con.execute(f"""
        SELECT CAST(anio AS INT) y, CAST(mes AS INT) m, count(*) n, max(acq_date_utc) dmax
        FROM read_parquet('{pq}')
        WHERE procesamiento = 'estandar' AND NOT en_mascara AND tramo IN ('snpp', 'noaa20')
          AND acq_date_utc BETWEEN DATE '2012-02-01' AND DATE '{FMAX}'
          AND {_caja(la0, la1, lo0, lo1)}
        GROUP BY ALL""").fetchall()
    assert all(str(r[3]) <= FMAX for r in q), "anti-fuga"
    d = {(y, m): float(n) for y, m, n, _ in q}
    return {(y, m): d.get((y, m), 0.0) for y in ANIOS_VIIRS for m in range(1, 13) if (y, m) != (2012, 1)}


def modis_aoi(con, pais, anio, F, disp, la0, la1, lo0, lo1) -> dict:
    """Ŝ VIIRS-eq por mes de `anio` (≤ 2011) en la AOI con el contrato pesos_modis; NaN si el mes está incompleto."""
    assert anio <= 2011, "anti-fuga: el armonizado de paridad es solo de la era MODIS"
    pq = RAIZ / f"data/processed/deteccion_{pais}.parquet"
    det = con.execute(f"""
        SELECT plataforma, acq_date_utc, CAST(mes AS INT) mes, turno, celda1, count(*) n
        FROM read_parquet('{pq}')
        WHERE procesamiento = 'estandar' AND NOT en_mascara AND plataforma IN ('Terra', 'Aqua')
          AND acq_date_utc BETWEEN DATE '{anio}-01-01' AND DATE '{anio}-12-31'
          AND {_caja(la0, la1, lo0, lo1)}
        GROUP BY ALL""").fetchdf()
    assert len(det) == 0 or str(pd.Timestamp(det.acq_date_utc.max()).date()) <= f"{anio}-12-31", "anti-fuga"
    w = np.asarray(FZ.pesos_modis(det[["plataforma", "acq_date_utc", "mes", "turno", "celda1"]], F, disp), float)
    det["h"] = w * det["n"].to_numpy()
    dias = pd.date_range(f"{anio}-01-01", f"{anio}-12-31", freq="D")
    rd = FZ.relojes_dia(dias, disp)
    sin_reloj = {pd.Timestamp(f).month for f, t, a in zip(rd.fecha, rd.t_ok, rd.a_ok) if not (t or a)}  # día sin ninguna → incompleto
    out = {}
    for m in range(1, 13):
        g = det[det.mes == m]
        h = float(g.h.sum()) if len(g) else 0.0
        out[m] = None if (m in sin_reloj or (len(g) and not np.isfinite(g.h).all())) else h
    return out


def caso(cid, valor, base, lo=None, hi=None, etiqueta="REAL", **extra) -> dict:
    m = VM.marca(valor if valor is not None else float("nan"), base, lo, hi)
    num = lambda x: None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x
    return {"id": cid, "etiqueta": etiqueta, **extra, "valor": num(valor), "lo": num(lo) if lo is not None else None,
            "hi": ("Infinity" if (hi is not None and hi == math.inf) else num(hi)) if hi is not None else None,
            "base": base,
            "esperado": {"p10": num(m["p10"]), "mediana": num(m["mediana"]), "p90": num(m["p90"]), "n": m["n"],
                         "estado": m["estado"], "direccion": m["direccion"], "u1": m["u1"],
                         "razon_mediana": num(m["razon_mediana"]),
                         "texto_razon": VM.texto_razon(valor, m["mediana"], BASE_NOMBRE) if valor is not None else None}}


def main() -> None:
    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false")
    disp = FZ.disponibilidad("global")
    Fp = {p: FZ.factores(p, *FZ.FINAL) for p in {v[0] for v in AOIS.values()}}
    casos = []
    for aoi, (pais, la0, la1, lo0, lo1) in AOIS.items():
        s = serie_aoi(con, pais, la0, la1, lo0, lo1)
        for anio in ANIOS_VIIRS:          # A) observado, base sin el año evaluado
            for mes in range(1, 13):
                if (anio, mes) not in s:
                    continue
                base = [s[(y, mes)] for y in ANIOS_VIIRS if y != anio and (y, mes) in s]
                casos.append(caso(f"{aoi}-{anio}-{mes:02d}-obs", s[(anio, mes)], base, aoi=aoi, pais=pais, anio=anio, mes=mes,
                                  tipo="observed_viirs"))
        for anio, tramo in ANIOS_MODIS.items():   # B) armonizado con IC80 real
            h = modis_aoi(con, pais, anio, Fp[pais], disp, la0, la1, lo0, lo1)
            for mes in range(1, 13):
                base = [s[(y, mes)] for y in ANIOS_VIIRS if (y, mes) in s]
                v = h[mes]
                if v is None:
                    lo = hi = None
                else:
                    ml, mh = FZ.intervalo(pais, v, tramo, "aoi")
                    lo, hi = v * ml, (math.inf if not math.isfinite(mh) else v * mh)
                casos.append(caso(f"{aoi}-{anio}-{mes:02d}-harm{tramo}", v, base, lo, hi,
                                  etiqueta=f"REAL harmonized estimate ({'Terra+Aqua' if tramo == 'TA' else 'Terra only'}; "
                                           f"final factors 2012-02..2018-12; IC80 from intervalos_{pais}.json, nivel aoi)",
                                  aoi=aoi, pais=pais, anio=anio, mes=mes, tipo=f"harmonized_{tramo}"))
    con.close()
    S = "SYNTHETIC"
    b7 = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    b13 = [float(x) for x in [3, 8, 8, 12, 15, 15, 15, 21, 30, 44, 51, 60, 75]]
    bordes = [
        ("igual_p90", 70.0, b7, None, None), ("sobre_p90", 70.5, b7, None, None), ("igual_p10", 10.0, b7, None, None),
        ("bajo_p10", 9.99, b7, None, None), ("p10_cero_sin_marca_baja", 0.0, [0, 0, 10, 20, 30, 40, 50], None, None),
        ("mediana_4_insuficiente", 100.0, [0, 1, 2, 4, 6, 8, 9], None, None),
        ("mediana_5_exacta", 100.0, [0, 1, 2, 5, 6, 8, 9], None, None),
        ("n13_interp_alto", 72.0, b13, None, None), ("n13_interp_igual_exacto", VM.cuantil_t6(b13, 0.9), b13[::-1], None, None),
        ("n13_interp_bajo", 4.9, b13, None, None), ("n1", 6.0, [5.0], None, None), ("base_vacia", 3.0, [], None, None),
        ("empates", 20.0, [20, 20, 20, 20, 20, 20], None, None), ("empates_sobre", 20.000001, [20, 20, 20, 20, 20, 20], None, None),
        ("valor_nan_incompleto", None, b7, None, None),
        ("i2_ambos_altos", 100.0, b7, 80.0, 150.0), ("i2_uno_alto", 100.0, b7, 50.0, 150.0), ("i2_ambos_bajos", 5.0, b7, 2.0, 8.0),
        ("i2_cruza_ambos", 40.0, b7, 5.0, 90.0), ("i2_hi_infinito_shat0", 0.0, b7, 0.0, math.inf),
        ("i2_typical", 40.0, b7, 20.0, 60.0), ("n13_razon_tie_2_25", 4.5 * 15.0 / 2.0, b13, None, None),
    ]
    for cid, v, base, lo, hi in bordes:
        casos.append(caso(f"borde-{cid}", v, [float(x) for x in base], lo, hi, etiqueta=S))
    # D) empates exactos con el umbral interpolado (N = 13: h10 = 1.4, h90 = 12.6; N = 14: h10 = 1.5, h90 = 13.5)
    e13 = [1, 6, 8, 10, 12, 15, 15, 20, 25, 30, 40, 60, 70]                 # p10 = 3, p90 = 66, mediana 15
    e14 = [2, 6, 8, 10, 12, 15, 15, 20, 25, 30, 40, 50, 60, 80]             # p10 = 4, p90 = 70, mediana 17.5
    q13 = [1.25, 3.75, 8.5, 10, 12.25, 15, 15.5, 20, 25.75, 30, 40.5, 60.25, 70.75]   # rejilla 0.25: p10 = 2.25 (exacto); p90 = 1331/20 (no representable)
    d13 = [5.1, 7.3, 8.9, 10.2, 12.7, 15.3, 15.9, 20.1, 25.6, 30.3, 40.8, 60.7, 70.9]  # doubles: umbral no representable
    empates = [
        ("n13_p10_igual", 3.0, e13, None, None), ("n13_p10_menos1", 2.0, e13, None, None), ("n13_p10_mas1", 4.0, e13, None, None),
        ("n13_p90_igual", 66.0, e13, None, None), ("n13_p90_mas1", 67.0, e13, None, None), ("n13_p90_menos1", 65.0, e13, None, None),
        ("n13_i2_lo_igual_p10", 10.0, e13, 3.0, 20.0), ("n13_i2_hi_igual_p90", 40.0, e13, 20.0, 66.0),
        ("n13_i2_hi_igual_p10", 2.5, e13, 2.0, 3.0), ("n13_i2_lo_igual_p90", 70.0, e13, 66.0, 80.0),
        ("n14_p10_igual", 4.0, e14, None, None), ("n14_p10_menos1", 3.0, e14, None, None),
        ("n14_p90_igual", 70.0, e14, None, None), ("n14_p90_mas1", 71.0, e14, None, None),
        ("n14_i2_lo_igual_p10", 10.0, e14, 4.0, 20.0), ("n14_i2_hi_igual_p90", 40.0, e14, 20.0, 70.0),
        ("n13_rejilla_p10_igual", VM.cuantil_t6(q13, 0.1), q13, None, None),
        ("n13_rejilla_p90_igual", VM.cuantil_t6(q13, 0.9), q13, None, None),
        ("n13_doubles_p10_cercano", VM.cuantil_t6(d13, 0.1), d13, None, None),
        ("n13_doubles_p90_cercano", VM.cuantil_t6(d13, 0.9), d13, None, None),
        ("n13_desordenada_p10_igual", 3.0, e13[::-1], None, None),
    ]
    for cid, v, base, lo, hi in empates:
        casos.append(caso(f"empate-{cid}", v, [float(x) for x in base], lo, hi, etiqueta=S, tipo="exact_tie"))
    temporada = []
    for cid, acc, base in [("sobre", 151.0, [100, 120, 130, 140, 150, 90, 110]), ("igual", 150.0, [100, 120, 130, 140, 150, 90, 110]),
                           ("n13", 70.0, b13), ("vacia", 10.0, []), ("n13_igual_p90_exacto", 66.0, e13),
                           ("n14_igual_p90_exacto", 70.0, e14)]:
        t = VM.temporada_inusual(acc, [float(x) for x in base])
        temporada.append({"id": f"temporada-{cid}", "etiqueta": S, "acumulado": acc, "base": [float(x) for x in base],
                          "esperado": {"inusual": t["inusual"], "estado": t["estado"], "p90": None if not math.isfinite(t["p90"]) else t["p90"]}})
    anio_fuego = [{"id": "anio_fuego-ar", "etiqueta": S, "medianas": [9, 8, 5, 3, 2, 1, 2, 6, 9, 12, 14, 10], "esperado": VM.inicio_anio_fuego([9, 8, 5, 3, 2, 1, 2, 6, 9, 12, 14, 10])},
                  {"id": "anio_fuego-empate", "etiqueta": S, "medianas": [1, 1, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5], "esperado": VM.inicio_anio_fuego([1, 1, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5])}]
    out = {
        "descripcion": "Parity cases Python <-> JS for the 'unusual' flag U1 + I2 (ADR-0006 rule 6c-q). Python reference: src/nucleo/validacion_marca.py.",
        "marca_si": "SI-generated (AI): Claude Code generated this file during the event; reviewed by the team.",
        "generado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True).stdout.strip(),
        "comando": "flock data/.pesado.lock .venv/bin/python tests/paridad_marca_generar.py",
        "regla": {
            "cuantil": "type 6: x sorted ascending, N=len; h=(N+1)*p; if h<=1 -> x[0]; if h>=N -> x[N-1]; else j=floor(h), g=h-j, q = x[j-1] + g*(x[j]-x[j-1]) (0-indexed array, exactly this expression)",
            "p_alto": 0.9, "p_bajo": 0.1, "mediana": "type 6 with p=0.5",
            "insuficiente": "N==0 or mediana < 5 -> estado 'insufficient' (no flag)",
            "u1": "high if v > p90 (strict); else low if p10 > 0 and v < p10 (strict); else none",
            "i2": "evaluate u1 at lo and hi; both high -> unusual/high; both low -> unusual/low; both none -> typical; else possibly_unusual (direccion = the flagged side, or 'both')",
            "observado": "lo = hi = null -> use the value itself",
            "incompleto": "valor null/NaN -> estado 'incomplete'",
            "razon_mediana": "v / mediana (null if mediana <= 0)",
            "texto_razon": "toFixed(1) of razon + '× the <base> median' (Python uses ROUND_HALF_UP on the exact binary value = JS toFixed)",
            "hi_infinity": "the string 'Infinity' means +Infinity (S_hat = 0 interval)",
            "temporada": "inusual = acumulado > p90 type 6 of base cumulatives at same day (strict); base empty -> insufficient",
            "anio_fuego": "month after the first minimum of the 12 monthly medians (1..12)",
        },
        "version": 3,
        "exactitud": "every decision uses the EXACT rational type-6 threshold (Python fractions.Fraction with p = 1/10, 1/2, 9/10; JS BigInt); "
                     "reported p10/mediana/p90 are the nearest doubles and are never used to decide. Cases with tipo 'exact_tie' have the value or an "
                     "interval end equal to the exact threshold (N = 13 and N = 14).",
        "nota_datos": "REAL observed cases use NASA FIRMS VIIRS standard detections (S-NPP to 2018-03, NOAA-20 from 2018-04), outside the static mask, "
                      "2012-02 to 2018-12 only; base = same calendar month in the other 2012-2018 years. REAL harmonized cases are MODIS (Terra/Aqua, "
                      "standard, outside mask) detections of 2011 (Terra+Aqua) and 2001 (Terra only) weighted with the final factors (calibrated "
                      "2012-02..2018-12) via pesos_modis, with the 80% interval of intervalos_<pais>.json at level 'aoi'; base = same month 2012-2018 VIIRS. "
                      "Cases labelled SYNTHETIC are invented inputs for edge cases; they are not observations.",
        "aois": {k: {"pais": v[0], "lat": [v[1], v[2]], "lon": [v[3], v[4]], "regla": "0.1-degree cells whose centre (floor(x*10)/10+0.05) is inside the box"}
                 for k, v in AOIS.items()},
        "casos": casos, "temporada": temporada, "anio_fuego": anio_fuego,
    }
    SALIDA.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    n_real = sum(c["etiqueta"].startswith("REAL") for c in casos)
    n_h = sum(c.get("tipo", "").startswith("harmonized") for c in casos)
    print(f"OK -> {SALIDA.relative_to(RAIZ)}: {len(casos)} casos ({n_real} reales, {n_h} de ellos armonizados con IC80 real), "
          f"{len(temporada)} temporada, {len(anio_fuego)} año de fuego")


if __name__ == "__main__":
    main()
