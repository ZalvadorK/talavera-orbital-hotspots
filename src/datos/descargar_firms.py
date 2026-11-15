#!/usr/bin/env python3
"""Download FIRMS yearly country summaries (MODIS C6.1 + VIIRS 375 m) into a local cache.

Route (D2-E-01, provisional): FIRMS "yearly summary by country" CSVs, public, no MAP_KEY needed.
URL pattern verified on 2026-11-14 (HTTP 206 with a valid CSV header):
    https://firms.modaps.eosdis.nasa.gov/data/country/<sensor>/<year>/<sensor>_<year>_<Country>.csv
    sensors: modis (Terra+Aqua), viirs-snpp (S-NPP), viirs-jpss1 (NOAA-20), viirs-jpss2 (NOAA-21)

Behaviour
- Idempotent: an existing complete file is never downloaded again (size checked against server).
- Atomic: writes <file>.part and renames when complete.
- Provenance: appends one row per file to data/raw/firms/descargas.csv
  (source, year, url, http status, bytes, sha256, downloaded_utc).
- Missing years (HTTP 404) are logged, not errors. Raw files are never modified.
- Standard library only.

Usage:
    python src/datos/descargar_firms.py --pais Mexico --desde 2000 --hasta 2026
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
SENSORES = {  # sensor -> first year worth probing
    "modis": 2000,
    "viirs-snpp": 2012,
    "viirs-jpss1": 2018,
    "viirs-jpss2": 2023,
}
UA = "spaceapps2026-hotspots/0.1 (+python urllib)"
RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "data" / "raw" / "firms" / "country"
REGISTRO = RAIZ / "data" / "raw" / "firms" / "descargas.csv"


def url_de(sensor: str, anio: int, pais: str) -> str:
    return f"{BASE}/{sensor}/{anio}/{sensor}_{anio}_{pais}.csv"


def tamano_remoto(url: str) -> tuple[int, int | None]:
    """(http_status, total_bytes) using a 1-byte range request."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            cr = r.headers.get("Content-Range", "")
            total = int(cr.split("/")[-1]) if "/" in cr and cr.split("/")[-1].isdigit() else None
            return r.status, total
    except urllib.error.HTTPError as e:
        return e.code, None


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def descargar(sensor: str, anio: int, pais: str, reintentos: int = 4) -> dict:
    url = url_de(sensor, anio, pais)
    ruta = DESTINO / sensor / str(anio) / f"{sensor}_{anio}_{pais}.csv"
    estado, total = tamano_remoto(url)
    fila = {"fuente": sensor, "anio": anio, "url": url, "http": estado, "bytes": "", "sha256": "",
            "descargado_utc": "", "nota": ""}
    if estado == 404:
        fila["nota"] = "not on the server"
        return fila
    if estado not in (200, 206):
        fila["nota"] = f"HTTP {estado}"
        return fila
    if ruta.exists() and total is not None and ruta.stat().st_size == total:
        fila.update(bytes=total, nota="cached")
        return fila
    ruta.parent.mkdir(parents=True, exist_ok=True)
    parcial = ruta.with_suffix(".csv.part")
    for intento in range(1, reintentos + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as r, parcial.open("wb") as fh:
                while bloque := r.read(1 << 20):
                    fh.write(bloque)
            if total is not None and parcial.stat().st_size != total:
                raise OSError(f"size {parcial.stat().st_size} != {total}")
            parcial.replace(ruta)
            fila.update(http=200, bytes=ruta.stat().st_size, sha256=sha256(ruta),
                        descargado_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
            return fila
        except (OSError, urllib.error.URLError) as e:
            fila["nota"] = f"attempt {intento}: {e}"
            time.sleep(2 ** intento)
    return fila


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pais", default="Mexico")
    ap.add_argument("--desde", type=int, default=2000)
    ap.add_argument("--hasta", type=int, default=dt.date.today().year)
    ap.add_argument("--sensores", nargs="*", default=list(SENSORES))
    ap.add_argument("--hilos", type=int, default=4)
    a = ap.parse_args(argv)
    tareas = [(s, y) for s in a.sensores for y in range(max(a.desde, SENSORES[s]), a.hasta + 1)]
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not REGISTRO.exists()
    campos = ["fuente", "anio", "url", "http", "bytes", "sha256", "descargado_utc", "nota"]
    fallos = 0
    with REGISTRO.open("a", newline="", encoding="utf-8") as fh, cf.ThreadPoolExecutor(a.hilos) as ex:
        w = csv.DictWriter(fh, fieldnames=campos)
        if nuevo:
            w.writeheader()
        for fila in ex.map(lambda t: descargar(t[0], t[1], a.pais), tareas):
            w.writerow(fila)
            fh.flush()
            ok = fila["http"] in (200, 206) and fila["bytes"] != ""
            fallos += 0 if ok or fila["http"] == 404 else 1
            print(f"{fila['fuente']:12s} {fila['anio']}  http={fila['http']}  bytes={fila['bytes'] or '-':>10}  "
                  f"{fila['nota']}", flush=True)
    print(f"Done. Failures (non-404): {fallos}. Registry: {REGISTRO.relative_to(RAIZ)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
