"""Run provenance: write ``manifiesto.json`` (seed, command, git state, package versions, input SHA-256).

SI-generated (AI): Claude Code wrote this during the event (K1-en, ADR-0011); reviewed by the team.

The JSON keys are kept identical to the manifests already in runs/ (Spanish keys: creado_utc, comando, semilla, ...)
so that earlier and later runs can be compared field by field. One key is ADDED (gate 15-Nov, D1): "dirty" (bool or
null) = `git status --porcelain` is non-empty for the hashed input files plus the code under src/nucleo/ (the files
that determine the result); "dirty_detalle" lists those porcelain lines. Files ignored by git (data/processed) never
show up as dirty: their identity is the SHA-256 in "datos". "git.cambios_sin_commit" (whole repository) is unchanged.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

__all__ = ["write_manifest", "sha256_file", "package_versions", "git_dirty"]

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "polars", "duckdb", "pyarrow", "xarray",
            "matplotlib", "earthaccess", "asf_search", "astropy", "astroquery", "spiceypy", "skyfield", "lightgbm", "xgboost"]


def sha256_file(path: str | Path, block: int = 1 << 20) -> str:
    """SHA-256 of a file (same as `sha256sum`)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(block), b""):
            h.update(b)
    return h.hexdigest()


def _git() -> dict:
    try:
        h = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        s = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return {"commit": h.stdout.strip() or None, "cambios_sin_commit": bool(s.stdout.strip())}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None}


def git_dirty(paths: list[str | Path], include_code: bool = True) -> tuple[bool | None, list[str]]:
    """(dirty, porcelain lines) of `git status --porcelain` restricted to `paths` that lie inside the repository
    (plus src/nucleo/ when include_code). dirty is None if git is unavailable. Untracked, non-ignored files count."""
    rel = []
    for p in paths:
        try:
            rel.append(str(Path(p).resolve().relative_to(ROOT)))
        except ValueError:
            continue
    if include_code:
        rel.append("src/nucleo")
    if not rel:
        return False, []
    try:
        s = subprocess.run(["git", "status", "--porcelain", "--", *sorted(set(rel))], cwd=ROOT, capture_output=True,
                           text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None, []
    if s.returncode != 0:
        return None, []
    lines = [x for x in s.stdout.splitlines() if x.strip()]
    return bool(lines), lines


def package_versions() -> dict:
    out = {}
    for p in PACKAGES:
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pass
    return out


def write_manifest(directory: str | Path, seed: int | None, data: list[str | Path] | None = None,
                   config: dict | None = None, command: str | None = None, extra: dict | None = None,
                   fingerprints: bool = True, **legacy) -> Path:
    """Write <directory>/manifiesto.json and return its path. Files in `data` that do not exist are skipped.

    `legacy` accepts the keyword names of the earlier call sites (comando=, extra= is shared, huellas=)."""
    unknown = set(legacy) - {"comando", "huellas"}
    if unknown:
        raise TypeError(f"unexpected keyword arguments: {sorted(unknown)}")
    command = legacy.get("comando", command)
    fingerprints = legacy.get("huellas", fingerprints)
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    files = [Path(p) for p in (data or []) if Path(p).exists()]
    info = {
        "creado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "comando": command or " ".join(sys.argv),
        "semilla": seed,
        "python": sys.version.split()[0],
        "plataforma": platform.platform(),
        "git": _git(),
        **dict(zip(("dirty", "dirty_detalle"), git_dirty([p for p in files if p.is_file()]))),
        "paquetes": package_versions(),
        "datos": [{"ruta": str(p), "mb": round(p.stat().st_size / 1e6, 3),
                   **({"sha256": sha256_file(p)} if fingerprints and p.stat().st_size / 1e6 < 5000 else {})}
                  for p in files if p.is_file()],
        "config": config or {},
        **(extra or {}),
    }
    path = d / "manifiesto.json"
    path.write_text(json.dumps(info, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
