"""Verify the cached raw FIRMS files against the SHA-256 recorded at download time (offline, no MAP_KEY).

SI-generated (AI): Claude Code — written during the event (adversarial review, Sat 14 Nov 2026).

Reads the two download registries written by src/datos/descargar_firms.py (country annual summaries)
and src/datos/descargar_firms_api.py (area API, 2026 tail). For every file, the LAST registry row with
HTTP 200 and a SHA-256 is the reference. Exit code 1 if any file is missing or its hash differs.

Usage: .venv/bin/python scripts/verificar_cache_firms.py
"""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "firms"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def expected() -> dict[Path, str]:
    ref: dict[Path, str] = {}
    country = RAW / "descargas.csv"
    if country.exists():
        for r in csv.DictReader(country.open(encoding="utf-8")):
            if r.get("http") == "200" and r.get("sha256"):
                name = r["url"].rsplit("/", 1)[-1]
                ref[RAW / "country" / r["fuente"] / r["anio"] / name] = r["sha256"]
    api = RAW / "descargas_api.csv"
    if api.exists():
        for r in csv.DictReader(api.open(encoding="utf-8")):
            if r.get("http") == "200" and r.get("sha256"):
                ref[RAW / "api" / r["area"] / r["fuente"] / f"{r['fecha']}_{r['dias']}d.csv"] = r["sha256"]
    return ref


def main() -> int:
    ref = expected()
    if not ref:
        print("No download registry found: nothing to verify (run with network first).")
        return 1
    bad = []
    for path, digest in sorted(ref.items()):
        if not path.exists():
            bad.append(f"missing  {path.relative_to(ROOT)}")
        elif sha256(path) != digest:
            bad.append(f"changed  {path.relative_to(ROOT)}")
    print(f"Cached raw files checked: {len(ref)}; problems: {len(bad)}")
    for line in bad[:50]:
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
