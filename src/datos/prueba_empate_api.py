#!/usr/bin/env python3
"""D2-E-01 tie test (descriptive, D1): does the FIRMS Area API, clipped to the country polygon, return the same
detections as the FIRMS yearly country summary for the same month and sensor?

Criterion fixed BEFORE running (Salvador, Sat 14 Nov ~21:40 Puebla time): |relative difference| <= 2 % in the
December-2025 monthly total, per sensor platform (Terra, Aqua, NOAA-20) and per country. If it fails, the 2026
tail carries the label "assignment by polygon" and the gap goes to Limitations.

- Downloads Dec-2025 MODIS_SP and VIIRS_NOAA20_SP by bounding box into a SEPARATE cache
  (data/raw/firms/api_empate/...) so that integrar_api.py never ingests these rows (no duplicates).
- Clips with Natural Earth 1:10m (same polygon as integrar_api.py).
- Compares against data/interim/firms/firms_<country>.parquet rows with ruta_acceso='resumen_pais'.
Output: docs/02-datos/prueba-empate-api-dic2025.md (+ manifiesto.json in runs/E01-empate/).
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import shapely

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "datos"))
import descargar_firms_api as dfa  # noqa: E402

CACHE = RAIZ / "data" / "raw" / "firms" / "api_empate"
dfa.CACHE = CACHE
dfa.REGISTRO = RAIZ / "data" / "raw" / "firms" / "descargas_api_empate.csv"
NE = RAIZ / "data" / "raw" / "fronteras" / "ne_10m_admin_0_countries.zip"
ISO = {"mexico": "MEX", "argentina": "ARG"}
INI, FIN = "2025-12-01", "2025-12-31"
UMBRAL = 0.02
OUT = RAIZ / "docs" / "02-datos" / "prueba-empate-api-dic2025.md"
MAN = RAIZ / "runs" / "E01-empate" / "manifiesto.json"


def main() -> int:
    for area in ISO:
        rc = dfa.main(["--area", area, "--desde", INI, "--hasta", FIN, "--fuentes", "MODIS_SP", "VIIRS_NOAA20_SP"])
        if rc:
            print(f"{area}: some downloads failed; check {dfa.REGISTRO}")
    con = duckdb.connect()
    con.execute("SET memory_limit='500MB'; SET threads=2")
    filas = []
    for area, iso in ISO.items():
        poly = gpd.read_file(f"zip://{NE}", columns=["ADM0_A3"], where=f"ADM0_A3 = '{iso}'").geometry.union_all()
        for src in ["MODIS_SP", "VIIRS_NOAA20_SP"]:
            d = con.execute(f"""SELECT CAST(longitude AS DOUBLE) x, CAST(latitude AS DOUBLE) y, satellite,
                  CAST(acq_date AS DATE) d FROM read_csv('{CACHE}/{area}/{src}/*.csv', header=true, all_varchar=true)
                  WHERE CAST(acq_date AS DATE) BETWEEN DATE '{INI}' AND DATE '{FIN}'""").df()
            d["dentro"] = shapely.contains_xy(poly, d["x"].values, d["y"].values)
            if src == "MODIS_SP":
                d["plataforma"] = d["satellite"].str.upper().map(lambda s: "Terra" if s in ("TERRA", "T") else "Aqua")
            else:
                d["plataforma"] = "NOAA-20"
            for plat, g in d.groupby("plataforma"):
                api_caja, api_pais = len(g), int(g["dentro"].sum())
                res, = con.execute(f"""SELECT count(*) FROM 'data/interim/firms/firms_{area}.parquet'
                    WHERE ruta_acceso='resumen_pais' AND plataforma='{plat}'
                      AND acq_date_utc BETWEEN DATE '{INI}' AND DATE '{FIN}'""").fetchone()
                dif = (api_pais - res) / res if res else float("nan")
                filas.append({"país": area, "fuente API": src, "plataforma": plat, "API en caja": api_caja,
                              "API dentro del polígono": api_pais, "resumen por país": res,
                              "diferencia relativa": f"{100*dif:+.2f} %", "cumple ≤ 2 %": abs(dif) <= UMBRAL})
    ok = all(f["cumple ≤ 2 %"] for f in filas)
    s = [f"# API vs country-summary tie test (D2-E-01) — December 2025\n",
         f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')} by `src/datos/prueba_empate_api.py`. "
         "Descriptive (D1), not a claim. **Criterion fixed before running:** |relative difference| ≤ 2 % in the monthly "
         "total per platform and country. API = `/api/area/` by bounding box, clipped with Natural Earth 1:10m (same as "
         "`integrar_api.py`); summary = `ruta_acceso='resumen_pais'` in the intermediate table. Separate cache "
         "(`data/raw/firms/api_empate/`), never integrated.\n",
         "| country | API source | platform | API in bbox | API inside polygon | country summary | difference | passes |",
         "|---|---|---|---|---|---|---|---|"]
    for f in filas:
        s.append(f"| {f['país']} | {f['fuente API']} | {f['plataforma']} | {f['API en caja']} | {f['API dentro del polígono']} | "
                 f"{f['resumen por país']} | {f['diferencia relativa']} | {'yes' if f['cumple ≤ 2 %'] else '**no**'} |")
    s.append(f"\n**Overall result:** {'PASSES in every row' if ok else 'FAILS in at least one row → the 2026 tail carries the label \"assignment by polygon\" and the gap goes to Limitations'}.\n")
    OUT.write_text("\n".join(s) + "\n", encoding="utf-8")
    MAN.parent.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    MAN.write_text(json.dumps({"id": "E01-empate", "script": "src/datos/prueba_empate_api.py",
                               "comando": f"{sys.executable} src/datos/prueba_empate_api.py", "commit": commit,
                               "criterio": "abs(rel diff) <= 0.02 per platform and country, Dec-2025",
                               "ventana": [INI, FIN], "resultado_global_cumple": ok, "filas": filas,
                               "generado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
                              indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("\n".join(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
