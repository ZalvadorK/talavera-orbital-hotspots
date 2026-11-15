#!/usr/bin/env python3
"""Download the 2026 tail (and optional extra sources) from the FIRMS Area API into a raw cache.

API (verified 2026-11-14 at https://firms.modaps.eosdis.nasa.gov/api/area/):
    /api/area/csv/[MAP_KEY]/[SOURCE]/[west,south,east,north]/[DAY_RANGE 1..5]/[DATE]
    → returns DATE .. DATE+DAY_RANGE-1.  Limit: 5000 transactions / 10 min per MAP_KEY.
Source date ranges come from /api/data_availability/ (logs/firms_data_availability.csv).

- MAP_KEY is read from the FIRMS_MAP_KEY environment variable or from .env; it is NEVER printed or logged.
- Bounding boxes include neighbouring countries: raw files keep everything; clipping to a border is an
  analysis decision (D2-S-03/D2-S-05), done later without deleting raw rows.
- Idempotent cache: data/raw/firms/api/<area>/<SOURCE>/<DATE>_<N>d.csv ; log: data/raw/firms/descargas_api.csv
- Standard library only.

Usage:
    python src/datos/descargar_firms_api.py --actualizar-disponibilidad
    python src/datos/descargar_firms_api.py --area mexico --desde 2026-01-01 --hasta 2026-11-14
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw" / "firms" / "api"
REGISTRO = RAIZ / "data" / "raw" / "firms" / "descargas_api.csv"
DISPONIBLE = RAIZ / "logs" / "firms_data_availability.csv"
BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
# Generous bounding boxes (west, south, east, north); clipping happens later.
AREAS = {"mexico": (-118.7, 14.3, -86.4, 32.8), "argentina": (-73.8, -55.3, -53.4, -21.6)}
FUENTES_DEF = ["MODIS_SP", "MODIS_NRT", "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_SP",
               "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT"]
RITMO_DIAS_POR_MIN = 300  # stays well under 5000 transactions / 10 min (a 5-day request counts ~5)


def leer_clave() -> str:
    k = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not k and (RAIZ / ".env").exists():
        m = re.search(r"^\s*FIRMS_MAP_KEY\s*=\s*(\S*)\s*$", (RAIZ / ".env").read_text(encoding="utf-8"), re.M)
        k = m.group(1).strip("'\"") if m else ""
    if not k:
        raise SystemExit("FIRMS_MAP_KEY is missing (set it in .env or in the environment). Request one at https://firms.modaps.eosdis.nasa.gov/api/map_key/")
    return k


def disponibilidad() -> dict[str, tuple[dt.date, dt.date]]:
    if not DISPONIBLE.exists():
        raise SystemExit(f"Missing {DISPONIBLE.relative_to(RAIZ)}: query /api/data_availability/ first")
    out = {}
    for r in csv.DictReader(DISPONIBLE.open(encoding="utf-8")):
        out[r["data_id"]] = (dt.date.fromisoformat(r["min_date"]), dt.date.fromisoformat(r["max_date"]))
    return out


def bajar(url: str, clave: str, reintentos: int = 4) -> tuple[int, bytes, str]:
    for intento in range(1, reintentos + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "spaceapps2026-hotspots/0.1"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, r.read(), ""
        except urllib.error.HTTPError as e:
            cuerpo = e.read()[:200].decode("utf-8", "replace").replace(clave, "<MAP_KEY>")
            if e.code in (429, 500, 502, 503, 504) and intento < reintentos:
                time.sleep(10 * intento)
                continue
            return e.code, b"", cuerpo
        except Exception as e:  # noqa: BLE001
            nota = f"{type(e).__name__}: {str(e).replace(clave, '<MAP_KEY>')[:160]}"
            if intento < reintentos:
                time.sleep(5 * intento)
                continue
            return 0, b"", nota
    return 0, b"", "no response"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=sorted(AREAS))
    ap.add_argument("--actualizar-disponibilidad", action="store_true",
                    help="download /api/data_availability/ to logs/firms_data_availability.csv (key masked) and exit")
    ap.add_argument("--desde", default="2026-01-01")
    ap.add_argument("--hasta", default=dt.date.today().isoformat())
    ap.add_argument("--fuentes", nargs="*", default=FUENTES_DEF)
    a = ap.parse_args(argv)
    clave = leer_clave()
    if a.actualizar_disponibilidad:
        estado, datos, nota = bajar(f"https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{clave}/all", clave)
        if estado != 200:
            raise SystemExit(f"data_availability: HTTP {estado} {nota}")
        DISPONIBLE.parent.mkdir(parents=True, exist_ok=True)
        DISPONIBLE.write_text(datos.decode("utf-8", "replace").replace(clave, "<MAP_KEY>"), encoding="utf-8")
        print(DISPONIBLE.read_text(encoding="utf-8"))
        return 0
    if not a.area:
        ap.error("--area is required")
    disp = disponibilidad()
    desde, hasta = dt.date.fromisoformat(a.desde), dt.date.fromisoformat(a.hasta)
    caja = ",".join(f"{v:g}" for v in AREAS[a.area])
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not REGISTRO.exists()
    campos = ["area", "fuente", "fecha", "dias", "url", "http", "filas", "bytes", "sha256", "descargado_utc", "nota"]
    dias_en_ventana, t_ventana = 0, time.time()
    fallos = 0
    with REGISTRO.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        if nuevo:
            w.writeheader()
        for fuente in a.fuentes:
            if fuente not in disp:
                print(f"{fuente}: not listed in data_availability; skipped")
                continue
            ini, fin = max(desde, disp[fuente][0]), min(hasta, disp[fuente][1])
            d = ini
            while d <= fin:
                n = min(5, (fin - d).days + 1)
                ruta = CACHE / a.area / fuente / f"{d.isoformat()}_{n}d.csv"
                url_pub = f"{BASE}/<MAP_KEY>/{fuente}/{caja}/{n}/{d.isoformat()}"
                fila = {"area": a.area, "fuente": fuente, "fecha": d.isoformat(), "dias": n, "url": url_pub,
                        "http": "", "filas": "", "bytes": "", "sha256": "", "descargado_utc": "", "nota": ""}
                if ruta.exists() and ruta.stat().st_size > 0:
                    d += dt.timedelta(days=n)
                    continue
                if dias_en_ventana + n > RITMO_DIAS_POR_MIN:
                    espera = 60 - (time.time() - t_ventana)
                    if espera > 0:
                        time.sleep(espera)
                    dias_en_ventana, t_ventana = 0, time.time()
                estado, datos, nota = bajar(url_pub.replace("<MAP_KEY>", clave), clave)
                dias_en_ventana += n
                fila.update(http=estado, nota=nota)
                texto = datos.decode("utf-8", "replace")
                if estado == 200 and texto.startswith("latitude"):
                    ruta.parent.mkdir(parents=True, exist_ok=True)
                    ruta.write_bytes(datos)
                    fila.update(filas=max(0, texto.count("\n") - 1), bytes=len(datos),
                                sha256=hashlib.sha256(datos).hexdigest(),
                                descargado_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
                else:
                    fallos += 1
                    fila["nota"] = (nota or texto[:160].replace(clave, "<MAP_KEY>")).replace("\n", " ")
                w.writerow(fila)
                fh.flush()
                print(f"{a.area:9s} {fuente:17s} {d} +{n}d  http={estado}  filas={fila['filas']}  {fila['nota'][:80]}", flush=True)
                d += dt.timedelta(days=n)
    print(f"Done. Failures: {fallos}. Registry: {REGISTRO.relative_to(RAIZ)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
