#!/usr/bin/env python3
"""Descriptive QA of the 2026 tail (H2): counts per country × platform × processing × month. No ratios between sensors.

Input : data/processed/deteccion_<pais>.parquet  (tabla_analitica.py)  and  docs/02-datos/firms_data_availability_2026-11-14.csv
Output: docs/02-datos/qa-firms-2026.md
Descriptive (D1), NOT a claim. It computes no ratios between platforms and does not compare Terra/Aqua/S-NPP with VIIRS: rows of
those platforms dated >= 2019-01-01 are reserved for the single test (ADR-0005); here they are only counted.

Uso: flock data/.pesado.lock .venv/bin/python src/datos/qa_2026.py
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
PAISES = {"mexico": "Mexico", "argentina": "Argentina"}
PLATAFORMAS = ["Terra", "Aqua", "S-NPP", "NOAA-20", "NOAA-21"]
PROCESOS = ["estandar", "NRT"]
DISP = RAIZ / "docs" / "02-datos" / "firms_data_availability_2026-11-14.csv"
SALIDA = RAIZ / "docs" / "02-datos" / "qa-firms-2026.md"
CORTE = "2026-11-14"


def tabla(cab: list[str], filas: list[list]) -> str:
    out = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    out += ["| " + " | ".join(str(c) for c in f) + " |" for f in filas]
    return "\n".join(out)


def n(x) -> str:
    return "—" if x is None else f"{x:,}".replace(",", " ")


def main() -> int:
    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false")
    s = [
        "# Descriptive QA of the 2026 tail (FIRMS Area API, 2026-01-01 → 2026-11-14)\n",
        "> SI-generated (AI): Claude Code wrote the script that produced this file during the event; reviewed by the team.\n",
        f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')} by `src/datos/qa_2026.py` from "
        "`data/processed/deteccion_<pais>.parquet`. **Descriptive, not a claim.** Counts of detections (`hotspot detections, not fires`), "
        "UTC date, all confidence levels and all `type` values, **no** mask except the explicit column. "
        "**No ratios between sensors are computed**: rows of Terra, Aqua and S-NPP dated ≥ 2019-01-01 are reserved "
        "for the single test (ADR-0005; column `reservado_prueba`) and are only counted here.\n",
        "## How to read it\n",
        "- **standard** (`estandar` in the tables) = science-quality processing (`_SP`, with `type`); **NRT** = near real time (provisional; no `type`; the version ends in `NRT`).",
        "- NRT only enters after the last standard date of the same platform (ADR-0002 S4.2; `integrar_api.py`), so there are no SP/NRT duplicates.",
        "- Rows clipped to each country's polygon (Natural Earth 1:10m, see `fuentes.md`); the Dec-2025 tie test passes 6 of 6 (EVD-048).",
        "- **Incomplete months:** 2026-11 only reaches the 14th; S-NPP NRT ends on 2026-11-02; standard VIIRS ends on 2026-07-31 and standard MODIS on 2026-08-31 "
        "(the rest of the cut-off month is NRT). NOAA-21 is QA only (ADR-0002); it is not part of the series.",
        "- A month with few rows is not 'little fire' if the platform had no data or changed processing (T-16).\n",
        "### Source coverage (frozen copy of `/api/data_availability/`, 2026-11-14)\n",
    ]
    with DISP.open() as f:
        cob = [[r["data_id"], r["min_date"], r["max_date"]] for r in csv.DictReader(f)
               if r["data_id"].startswith(("MODIS_", "VIIRS_"))]
    s.append(tabla(["source", "first day", "last day"], cob))
    s.append("")
    meses = [f"2026-{m:02d}" for m in range(1, 12)]
    for pais, nombre in PAISES.items():
        pq = RAIZ / "data" / "processed" / f"deteccion_{pais}.parquet"
        if not pq.exists():
            raise SystemExit(f"missing {pq}; run tabla_analitica.py first")
        r = con.execute(f"""
          SELECT plataforma, procesamiento, mes, count(*) AS filas, count(DISTINCT acq_date_utc) AS dias,
                 min(acq_date_utc) AS d0, max(acq_date_utc) AS d1,
                 count(*) FILTER (en_mascara) AS en_mascara, count(*) FILTER (type IS NOT NULL AND type <> 0) AS type_ne0,
                 bool_or(reservado_prueba) AS reservado
          FROM '{pq}' WHERE acq_date_utc >= DATE '2026-01-01' GROUP BY ALL ORDER BY ALL""").fetchall()
        filas = {(a, b, m): (nf, nd) for a, b, m, nf, nd, *_ in r}
        tot: dict[tuple, list] = {}
        for a, b, m, nf, nd, d0, d1, em, tn, res in r:
            t = tot.setdefault((a, b), [0, None, None, 0, 0, res])
            t[0] += nf
            t[1] = d0 if t[1] is None or d0 < t[1] else t[1]
            t[2] = d1 if t[2] is None or d1 > t[2] else t[2]
            t[3] += em
            t[4] += tn
        s.append(f"## {nombre}\n")
        s.append("### Rows per platform × processing × month\n")
        cab = ["platform", "processing"] + [m[5:] for m in meses] + ["total 2026"]
        cuerpo = []
        for pl in PLATAFORMAS:
            for pr in PROCESOS:
                if (pl, pr) not in tot:
                    continue
                cuerpo.append([pl, pr] + [n(filas.get((pl, pr, i + 1), (None, None))[0]) if (pl, pr, i + 1) in filas else "·"
                                          for i in range(11)] + [f"**{n(tot[(pl, pr)][0])}**"])
        s.append(tabla(cab, cuerpo))
        s.append("\n`·` = no rows that month. Columns = month of 2026 (01 = January).\n")
        s.append("### UTC days with at least one detection\n")
        cuerpo = []
        for pl in PLATAFORMAS:
            for pr in PROCESOS:
                if (pl, pr) not in tot:
                    continue
                cuerpo.append([pl, pr] + [str(filas[(pl, pr, i + 1)][1]) if (pl, pr, i + 1) in filas else "·" for i in range(11)])
        s.append(tabla(["platform", "processing"] + [m[5:] for m in meses], cuerpo))
        s.append("\nA full calendar month has 28–31 days; fewer days with data than the month has means a source cut-off or a gap, not absence of fire (T-16).\n")
        s.append("### Summary per platform × processing\n")
        cuerpo = []
        for pl in PLATAFORMAS:
            for pr in PROCESOS:
                if (pl, pr) not in tot:
                    continue
                t = tot[(pl, pr)]
                cuerpo.append([pl, pr, n(t[0]), t[1], t[2], n(t[3]), n(t[4]) if pr == "estandar" else "— (NRT has no `type`)",
                               "yes" if t[5] else "no"])
        s.append(tabla(["platform", "processing", "rows", "first day", "last day", "rows in static mask",
                        "rows with `type`≠0", "reservado_prueba"], cuerpo))
        s.append("")
    # Days with no row inside each source's coverage (descriptive; a day empty in both countries suggests a platform gap)
    cobertura = {r[0]: (r[1], r[2]) for r in cob}
    clave = {"Terra": "MODIS", "Aqua": "MODIS", "S-NPP": "VIIRS_SNPP", "NOAA-20": "VIIRS_NOAA20", "NOAA-21": "VIIRS_NOAA21"}
    s.append("## UTC days with no row inside the source coverage\n")
    s.append("For each platform and processing: days between the first and the last day of the source (coverage table, bounded to 2026) "
             "on which the country has no row. A day empty **in both countries** suggests a platform gap, not absence of fire "
             "(rule R1 of ADR-0003; T-16); a day empty in only one country may simply be low activity (austral winter with Terra, e.g.).\n")
    vacios: dict[tuple, dict] = {}
    for pais in PAISES:
        pq = RAIZ / "data" / "processed" / f"deteccion_{pais}.parquet"
        for pl in PLATAFORMAS:
            sp0, sp1 = cobertura[clave[pl] + "_SP"]
            nr0, nr1 = cobertura[clave[pl] + "_NRT"]
            tramos = {"estandar": ("2026-01-01", sp1), "NRT": (max(nr0, (dt.date.fromisoformat(sp1) + dt.timedelta(days=1)).isoformat()), nr1)}
            for pr, (a, b) in tramos.items():
                dias = con.execute(f"""
                  SELECT CAST(d AS DATE) FROM range(DATE '{a}', DATE '{b}' + INTERVAL 1 DAY, INTERVAL 1 DAY) t(d)
                  WHERE CAST(d AS DATE) NOT IN (SELECT DISTINCT acq_date_utc FROM '{pq}'
                                                WHERE plataforma = '{pl}' AND procesamiento = '{pr}' AND acq_date_utc >= DATE '2026-01-01')
                  ORDER BY 1""").fetchall()
                vacios[(pl, pr, pais)] = {"rango": (a, b), "dias": [str(x[0]) for x in dias]}
    cuerpo = []
    for pl in PLATAFORMAS:
        for pr in PROCESOS:
            mx_, ar_ = vacios[(pl, pr, "mexico")], vacios[(pl, pr, "argentina")]
            ambos = sorted(set(mx_["dias"]) & set(ar_["dias"]))
            cuerpo.append([pl, pr, f"{mx_['rango'][0]} → {mx_['rango'][1]}", len(mx_["dias"]), len(ar_["dias"]), len(ambos),
                           ", ".join(ambos) if ambos else "—"])
    s.append(tabla(["platform", "processing", "source range", "empty days MX", "empty days AR", "empty in both",
                    "dates empty in both (UTC)"], cuerpo))
    s.append("")
    s.append("## Notes\n")
    s.append("- `rows in static mask` applies the ADR-0003 mask (S-NPP `type≠0`, 2012-01-20 → 2018-12-31, 0.01° cells + 3×3 neighbors, same country) "
             "equally to all platforms and to NRT; it is descriptive and does not measure which share is vegetation fire.")
    s.append("- Rows with `reservado_prueba = yes` (Terra, Aqua and S-NPP from 2019-01-01) enter no comparison until `verdict.json` exists.")
    s.append("- Regenerate: `flock data/.pesado.lock .venv/bin/python src/datos/qa_2026.py`.")
    SALIDA.write_text("\n".join(s) + "\n")
    print(f"OK → {SALIDA.relative_to(RAIZ)}")
    # control: totals per platform/processing = direct count from the parquet
    for pais in PAISES:
        pq = RAIZ / "data" / "processed" / f"deteccion_{pais}.parquet"
        print(pais, con.execute(f"SELECT plataforma, procesamiento, count(*) FROM '{pq}' WHERE acq_date_utc >= DATE '2026-01-01' "
                                "GROUP BY ALL ORDER BY ALL").fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
