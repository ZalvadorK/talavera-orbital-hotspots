#!/usr/bin/env python3
"""Validation of RT-05 (ADR-0005, D2-S-07 §4.3) - pre-registered core. A single function for development and test.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
Modified 15-Nov ~04:40 Puebla by Claude Code (SI-generated): pendientes() also lists run tests without their threshold.
Modified 15-Nov ~14:00 Puebla by Claude Code (SI-generated): team decision lot 3 (P5 and clases_I05 run, P3 without
S_hat = 0, rule M1 'too_few_modis'): the core now READS umbrales.M1.min_modis_por_mes (etiqueta_estimacion, M1 in the
I-05 verdict), and verdict*.json carries both P3 coverages and the number of cell-months left out for S_hat = 0.
Modified 15-Nov ~14:30 Puebla by Claude Code (SI-generated): gate B-G1 option A - rule 3b of I-05 (country P2+P2b,
AOI >= 900 cells) now applies ALSO when clases_I05 runs; the class verdict is an extra condition, never an override.

Tests (config/validacion.yaml -> `pruebas`):
  P2 / P2b  U1 (+I2) flags of H_TA vs the target at 3 deg block, against the twin ceiling (target vs witness)
  P3        coverage of the IC80 at 1 deg cell (all evaluable cell-months, including S = 0 and S_hat = 0), point estimate
  P4        skill = 1 - MdALE_method / MdALE_M1 (M1 = global Terra+Aqua ratio, nucleo.baseline.global_count_ratio)
  J1        Jul-2002 splice: log(H_TA / H_T) country x month in 2003-2011, 95 % CI by bootstrap over years
  J2        Apr-2018 splice at block level (decides) and country level (check): log(NOAA-20 / S-NPP)
  T1 / T2   transfer MX <-> AR (all parameters / only the shape with the own level)
  P1        level consistency check (does not decide)
  E1b       P1-P3 also on the E1b scale (7g-bis), in the same run
  C_V       MODIS version check (Pettitt on log(S/(T+A)) 2016-2018)
  S8        (ADR-0012 option 2) seasonal Sen slope of the target VIIRS series against H_TA per 3 deg block;
            REPORTED, DOES NOT DECIDE (config `s8.decide: false`; it never enters the verdict)
  clases_I05  P2/P2b by expected MODIS count class (route I-05); `run` since the team decision of lot 3 (point 9).
            Rule M1 (`umbrales.M1.min_modis_por_mes`): a class entirely below it is 'too_few_modis', never 'reliable'.
            `--i05-exploratorio` (development only) computes it as exploratory when the config says not_run.
  P5        Terra-only era (ADR-0005 7a/7f; D2-S-07 §4.3): P2, P2b and P3 with H_T (clock 'T') instead of H_TA; SEPARATE
            verdict, and the era stays "indicative (Terra only)" even if it passes. `run` since lot 3 (point 17).
            Threshold: `umbrales.P5.criterio` (null -> 'pending_threshold'). `--p5-exploratorio` (development only):
            outside the verdict, when the config says not_run.
P3 ALWAYS reports both populations (with and without S_hat = 0) and the number left out; `p3.poblacion` says which
decides (incluye_s0 if the key is absent; the config sets excluye_s0 since lot 3, point 7).
Label of an estimated month/AOI (etiqueta_estimacion): 'too_few_modis' (rule M1) > Terra-only 'indicative' (even if P5
passes) > 'reliable' only if rule 3b of I-05 holds (country passed P2+P2b on the published scale, AOI >= one 3-degree
block) AND, with clases_I05 run, the count class is reliable (gate B-G1, option A) > 'indicative'.
Bootstrap by 3 deg block x year (and 6 deg x year as sensitivity); report by year and AR without 2020.
S8 and I-05 use their OWN random generators (seed, 8) and (seed, 5): they do not alter the core sequence, so the core
metrics are identical with or without them.

Modes (--modo):
  desarrollo (default)  development: factores(pais, '2012-02-01', '2015-12-31'), evaluates 2016-2018 against S-NPP.
                        NEVER touches 2019+.
  prueba                single test: W2 2019-01 -> 2021-12 against NOAA-20. Requires --prueba-unica, the `prereg-v1`
                        tag, hashes of src/nucleo/ and of the YAML equal to config/validacion.hashes.json, no pending
                        thresholds, real factors (src/nucleo/factores.py) and no previous test run.
  --registrar-hashes    writes config/validacion.hashes.json (freeze step; refused while thresholds are pending).
                        Pending = any `pendiente_lote3: true` OR any `run` test whose required threshold is null/absent
                        (UMBRALES_REQUERIDOS: e.g. P5 -> umbrales.P5.criterio, clases_I05 -> umbrales.M1.min_modis_por_mes).

Usage (with the shared memory lock; the script takes it by itself if not launched under `flock`):
  flock data/.pesado.lock .venv/bin/python src/nucleo/validacion_rt05.py --modo desarrollo --exp EXP-003
--exp is a folder INSIDE runs/ (name or path); it is validated before reading data or writing (outside runs/ -> REFUSED;
already existing -> REFUSED unless --sobrescribir in development; in test mode it is never overwritten).
Test mode (gate H4): the guard also compares the INPUTS (deteccion_*.parquet, disponibilidad_plataforma_dia.csv,
mascara_*.parquet) with `entradas_prueba` of config/validacion.hashes.json, and writes the marker
runs/.prueba_unica_iniciada.json (+ <EXP>/prueba_iniciada.json) BEFORE reading data: with the marker, another run is
REFUSED even if no verdict.json exists (only --re-corrida-documentada REASON).
The manifest adds "dirty" (git status --porcelain of the hashed files: config, src/nucleo/, tables) without changing
the other keys.
JSON keys and values of metricas.json / verdict*.json / manifiesto.json keep their Spanish names (schema read by the
app exporter and compared across runs); the report text (informe.md) and the messages are in English.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
from nucleo import validacion_marca as VM  # noqa: E402
from nucleo.baseline import global_count_ratio  # noqa: E402
from nucleo.provenance import git_dirty  # noqa: E402
from nucleo.runguard import acquire_heavy_lock, refuse_overwrite, resolve_under  # noqa: E402
from nucleo.trend import pettitt, seasonal_sen_slope  # noqa: E402

PROC = RAIZ / "data/processed"
CONFIG = RAIZ / "config/validacion.yaml"
HASHES = RAIZ / "config/validacion.hashes.json"
TAG = "prereg-v1"
FECHA_RESERVA = "2019-01-01"
MARCA_SI = "SI-generated (AI): Claude Code wrote the script that produced this file during the event; reviewed by the team."


# ============================================================================ utilities
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def hash_arbol_nucleo() -> tuple[str, dict]:
    """SHA-256 of the src/nucleo/ tree (sorted *.py files, relative path + content hash)."""
    archivos = sorted(p for p in (RAIZ / "src/nucleo").rglob("*.py") if "__pycache__" not in p.parts)
    det = {str(p.relative_to(RAIZ)): sha256(p) for p in archivos}
    h = hashlib.sha256("".join(f"{k}\0{v}\n" for k, v in det.items()).encode()).hexdigest()
    return h, det


def tablas_congeladas() -> dict:
    out = {}
    for patron in ("factores_*_2012-02-01_2018-12-31.parquet", "factores_*_2012-02-01_2018-12-31.json",
                   "factores_mexico.parquet", "factores_argentina.parquet", "intervalos_*.json"):
        for p in sorted(PROC.glob(patron)):
            out[str(p.relative_to(RAIZ))] = sha256(p)
    return out


# Gate H4 D-N5: INPUT files read by the test (besides the factor and interval tables of tablas_congeladas):
# detections per country, the R1 availability table and the static masks (origin of `en_mascara`).
PATRONES_ENTRADAS_PRUEBA = ("deteccion_*.parquet", "disponibilidad_plataforma_dia.csv", "mascara_*.parquet")


def entradas_prueba() -> dict:
    """SHA-256 of the test input files (path relative to the root -> hash). Stored by --registrar-hashes
    (key `entradas_prueba`) and compared by test mode: a detections parquet or a mask regenerated after the
    freeze REFUSES the test."""
    out = {}
    for patron in PATRONES_ENTRADAS_PRUEBA:
        for p in sorted(PROC.glob(patron)):
            out[str(p.relative_to(RAIZ))] = sha256(p)
    return out


# Gate H4 D-N3: "single test started" marker. It is written BEFORE reading any data (and therefore before reading
# anything >= 2019); if it exists, the guard refuses another run even without verdict.json (e.g. a crashed process).
def marca_prueba() -> Path:
    return RAIZ / "runs/.prueba_unica_iniciada.json"


NOMBRE_MARCA_EXP = "prueba_iniciada.json"


def marcas_prueba_existentes() -> list[Path]:
    return [p for p in [marca_prueba(), *sorted((RAIZ / "runs").glob(f"*/{NOMBRE_MARCA_EXP}"))] if p.exists()]


def marcar_inicio_prueba(d: Path, guarda: dict, exp: str) -> dict:
    """Writes the global marker (runs/.prueba_unica_iniciada.json) and a copy in the EXP folder, with commit, tag,
    time and command. First run: exclusive creation (O_EXCL). Documented re-run: appends the attempt to the history."""
    ahora = dt.datetime.now(dt.timezone.utc)
    intento = {"exp": str(d.relative_to(RAIZ)) if d.is_relative_to(RAIZ) else str(d), "exp_arg": exp,
               "commit": git("rev-parse", "HEAD") or None, "tag": guarda.get("tag"), "commit_tag": guarda.get("commit_tag"),
               "re_corrida": guarda.get("re_corrida"), "hora_utc": ahora.isoformat(timespec="seconds"),
               "hora_puebla": (ahora - dt.timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S") + " (UTC-6)",
               "pid": os.getpid(), "comando": " ".join([".venv/bin/python", *sys.argv])}
    g = marca_prueba()
    g.parent.mkdir(parents=True, exist_ok=True)
    if g.exists():
        if not guarda.get("re_corrida"):
            raise SystemExit(f"REFUSED: the test-started marker {g} already exists (use --re-corrida-documentada REASON)")
        previo = json.loads(g.read_text(encoding="utf-8"))
        historial = previo.get("intentos", [previo])
    else:
        historial = []
    marca = {"aviso": "PRE-REGISTERED SINGLE TEST STARTED: a second run is refused while this file exists "
                      "(only --re-corrida-documentada MOTIVO, reported as such).",
             "intentos": [*historial, intento], "marca_si": MARCA_SI}
    texto = json.dumps(marca, indent=2, ensure_ascii=False) + "\n"
    if historial:
        g.write_text(texto, encoding="utf-8")
    else:
        fd = os.open(g, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o664)    # two processes at once: only one creates it
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
    d.mkdir(parents=True, exist_ok=True)
    (d / NOMBRE_MARCA_EXP).write_text(json.dumps(intento | {"marca_si": MARCA_SI}, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    return intento


# Thresholds each test needs when `pruebas.<test>: run` (paths under `umbrales`, "/"-separated). A path that is ABSENT
# or holds null ANYWHERE inside it counts as PENDING: the freeze (--registrar-hashes) and the test-mode guard refuse.
# Besides this table, any `run` test whose own block `umbrales.<test>` exists and holds a null is pending too.
# clases_I05 (route I-05, lot 3 point 9) needs the M1 threshold ("too few MODIS", ADR-0004): `umbrales.M1.min_modis_por_mes`
# (set to 10 by the team in lot 3; a number for both eras, or {TA: n, T: n}).
UMBRALES_REQUERIDOS: dict[str, tuple[str, ...]] = {
    "P2": ("P2",), "P2b": ("P2b",), "P3": ("P3",), "P4": ("P4",), "J1": ("J1",), "J2": ("J2_bloque",),
    "T1": ("T",), "T2": ("T",),
    "P5": ("P5/criterio",),
    "clases_I05": ("M1/min_modis_por_mes", "P2", "P2b"),
}
_AUSENTE = object()


def _tiene_nulo(x) -> bool:
    if x is None:
        return True
    if isinstance(x, dict):
        return any(_tiene_nulo(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return any(_tiene_nulo(v) for v in x)
    return False


def _valor(U, ruta: str):
    x = U
    for k in ruta.split("/"):
        if not isinstance(x, dict) or k not in x:
            return _AUSENTE
        x = x[k]
    return x


def pendientes(cfg) -> list[str]:
    """Pending thresholds. (1) every `pendiente_lote3: true` (path of its block, e.g. "/umbrales"); (2) for every test
    with `pruebas.<test>: run`, each required threshold (UMBRALES_REQUERIDOS, plus the test's own `umbrales.<test>`
    block if present) that is absent or holds null: "/umbrales/<path> (pruebas.<test>: run)". Empty list = nothing
    pending. With the current config (P5 and clases_I05 not_run) the result is the same as before (["/umbrales"])."""
    out = []

    def rec(x, ruta):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "pendiente_lote3" and v is True:
                    out.append(ruta or "/")
                rec(v, f"{ruta}/{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                rec(v, f"{ruta}[{i}]")
    rec(cfg, "")
    U = (cfg or {}).get("umbrales") or {}
    for prueba, estado in ((cfg or {}).get("pruebas") or {}).items():
        if estado != "run":
            continue
        rutas = list(UMBRALES_REQUERIDOS.get(prueba, ()))
        if prueba in U and prueba not in rutas:
            rutas.append(prueba)         # own block (any null inside), unless a sub-path of it is already reported
        for ruta in rutas:
            v = _valor(U, ruta)
            if v is _AUSENTE or _tiene_nulo(v):
                if ruta == prueba and any(x.startswith(f"/umbrales/{prueba}/") for x in out):
                    continue
                item = f"/umbrales/{ruta} (pruebas.{prueba}: run)"
                if item not in out:
                    out.append(item)
    return out


def cargar_interfaz(modo: str):
    """The real module src/nucleo/factores.py (fixed contract). The development stub was removed at integration:
    without the real factores.py the script does not run in any mode. Returns (module, es_stub=False)."""
    try:
        from nucleo import factores as FZ  # type: ignore
        for f in ("factores", "pesos_modis", "intervalo", "disponibilidad"):
            if not hasattr(FZ, f):
                raise ImportError(f"factores.py does not expose {f}()")
        return FZ, False
    except ImportError as e:
        raise SystemExit(f"REFUSED: the validation requires the real src/nucleo/factores.py ({e}); mode {modo}")


# ============================================================================ anti-leak guard
def guarda_prueba(cfg, args) -> dict:
    motivos = []
    if not args.prueba_unica:
        motivos.append("missing --prueba-unica")
    if not git("tag", "-l", TAG):
        motivos.append(f"the git tag {TAG} does not exist")
    if pendientes(cfg):
        motivos.append(f"pending thresholds (pendiente_lote3 or a run test without its threshold): {pendientes(cfg)}")
    if not HASHES.exists():
        motivos.append("config/validacion.hashes.json does not exist")
    else:
        reg = json.loads(HASHES.read_text())
        en_tag = git("show", f"{TAG}:config/validacion.hashes.json")
        if not en_tag or json.loads(en_tag) != reg:
            motivos.append("config/validacion.hashes.json differs from the one registered in the tag")
        h, _ = hash_arbol_nucleo()
        if h != reg.get("arbol_src_nucleo"):
            motivos.append("the hash of the src/nucleo/ tree does not match")
        if sha256(CONFIG) != reg.get("config_yaml"):
            motivos.append("the hash of config/validacion.yaml does not match")
        for ruta, hh in reg.get("tablas", {}).items():
            p = RAIZ / ruta
            if not p.exists() or sha256(p) != hh:
                motivos.append(f"frozen table changed or missing: {ruta}")
        # D-N5: test inputs (detections, availability, masks) equal to the registered ones
        reg_ent = reg.get("entradas_prueba")
        if not reg_ent:
            motivos.append("config/validacion.hashes.json does not register the test inputs (entradas_prueba); "
                           "run --registrar-hashes again")
        else:
            act = entradas_prueba()
            for ruta, hh in reg_ent.items():
                if act.get(ruta) != hh:
                    motivos.append(f"test input changed or missing: {ruta}")
            for ruta in sorted(set(act) - set(reg_ent)):
                motivos.append(f"new test input, not registered: {ruta}")
    previas = [p for p in (RAIZ / "runs").glob("EXP-*/verdict.json")
               if json.loads(p.read_text()).get("modo") == "prueba"]
    if previas and not args.re_corrida_documentada:
        motivos.append(f"a test run already exists: {[str(p) for p in previas]} (use --re-corrida-documentada REASON)")
    marcas = marcas_prueba_existentes()       # D-N3: a started run counts (even if it crashed without verdict.json)
    if marcas and not args.re_corrida_documentada:
        motivos.append(f"a single test was already started (marker {[str(p) for p in marcas]}), even though no verdict.json "
                       "exists (use --re-corrida-documentada REASON)")
    if cfg["modos"]["prueba"]["evaluacion"] != ["2019-01-01", "2021-12-31"]:
        motivos.append("the test window is not W2 2019-01-01 → 2021-12-31")
    if motivos:
        raise SystemExit("REFUSED (anti-leak guard):\n  - " + "\n  - ".join(motivos))
    return {"tag": TAG, "commit_tag": git("rev-list", "-n", "1", TAG), "re_corrida": args.re_corrida_documentada}


def registrar_hashes(cfg) -> None:
    if pendientes(cfg):
        raise SystemExit(f"REFUSED: pending thresholds (pendiente_lote3 or a run test without its threshold): "
                         f"{pendientes(cfg)}; nothing is frozen.")
    FZ, stub = cargar_interfaz("prueba")
    h, det = hash_arbol_nucleo()
    par = RAIZ / "tests/paridad_marca.json"
    out = {"arbol_src_nucleo": h, "archivos_src_nucleo": det, "config_yaml": sha256(CONFIG), "tablas": tablas_congeladas(),
           "entradas_prueba": entradas_prueba(),                           # D-N5: compared by test mode
           "paridad_marca_json": sha256(par) if par.exists() else None,   # informative (ADR-0006 §5); the guard does not require it
           "fecha_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "commit_previo": git("rev-parse", "--short", "HEAD"),
           "marca_si": MARCA_SI}
    HASHES.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"hashes registered in {HASHES.relative_to(RAIZ)}; now commit + tag {TAG}")


# ============================================================================ reading (DuckDB, aggregates only)
class Lector:
    def __init__(self, fecha_maxima: str):
        self.fmax = fecha_maxima
        self.con = duckdb.connect()
        self.con.execute("SET memory_limit='600MB'; SET threads=2; SET preserve_insertion_order=false")

    def q(self, sql: str, desde: str, hasta: str) -> pd.DataFrame:
        assert hasta <= self.fmax, f"anti-leak: {hasta} > maximum date of the mode {self.fmax}"
        df = self.con.execute(sql.format(d0=desde, d1=hasta)).fetchdf()
        for c in ("acq_date_utc", "fecha"):
            if c in df and len(df):
                assert str(pd.Timestamp(df[c].max()).date()) <= self.fmax, "anti-leak: date read outside the mode"
        return df


def leer_modis_dia(L: Lector, pais: str, desde: str, hasta: str) -> pd.DataFrame:
    sql = f"""SELECT plataforma, acq_date_utc, CAST(anio AS INT) anio, CAST(mes AS INT) mes, turno, celda1, count(*) n
              FROM read_parquet('{PROC / f"deteccion_{pais}.parquet"}')
              WHERE procesamiento='estandar' AND NOT en_mascara AND plataforma IN ('Terra','Aqua')
                AND acq_date_utc BETWEEN DATE '{{d0}}' AND DATE '{{d1}}' GROUP BY ALL"""
    df = L.q(sql, desde, hasta)
    df["acq_date_utc"] = pd.to_datetime(df["acq_date_utc"])
    df["celda1"] = df["celda1"].astype("category")
    return df


def leer_viirs_mes(L: Lector, pais: str, desde: str, hasta: str) -> pd.DataFrame:
    sql = f"""SELECT plataforma, CAST(anio AS INT) anio, CAST(mes AS INT) mes, celda1, count(*) n, max(acq_date_utc) fecha
              FROM read_parquet('{PROC / f"deteccion_{pais}.parquet"}')
              WHERE procesamiento='estandar' AND NOT en_mascara AND plataforma IN ('S-NPP','NOAA-20')
                AND acq_date_utc BETWEEN DATE '{{d0}}' AND DATE '{{d1}}' GROUP BY plataforma, anio, mes, celda1"""
    return L.q(sql, desde, hasta).drop(columns="fecha")


def disponibilidad_ventana(L: Lector, desde: str, hasta: str, avisos: list | None = None) -> pd.DataFrame:
    """Frozen R1 rule (ADR-0003; N = 20, global MX+AR, standard, all types, no mask) for dates > 2018.
    The published table (disponibilidad_plataforma_dia.csv) only reaches 2018-12-31 because of the anti-leak rule."""
    partes = []
    for pais, col in (("mexico", "n_mx"), ("argentina", "n_ar")):
        sql = f"""SELECT acq_date_utc fecha, plataforma, count(*) {col}
                  FROM read_parquet('{PROC / f"deteccion_{pais}.parquet"}')
                  WHERE procesamiento='estandar' AND plataforma IN ('Terra','Aqua')
                    AND acq_date_utc BETWEEN DATE '{{d0}}' AND DATE '{{d1}}' GROUP BY ALL"""
        partes.append(L.q(sql, desde, hasta).set_index(["fecha", "plataforma"]))
    dias = pd.date_range(desde, hasta, freq="D")
    idx = pd.MultiIndex.from_product([dias, ["Terra", "Aqua"]], names=["fecha", "plataforma"])
    d = pd.concat(partes, axis=1).reindex(idx).fillna(0).astype(int).reset_index()
    tot = d.n_mx + d.n_ar
    otra = d.assign(t=tot).pivot(index="fecha", columns="plataforma", values="t")
    otra_n = np.where(d.plataforma == "Terra", otra.loc[d.fecha, "Aqua"].to_numpy(), otra.loc[d.fecha, "Terra"].to_numpy())
    d["sin_datos"] = (tot == 0) & (otra_n >= 20)
    d["fuente"] = np.where(d.sin_datos, "regla_datos", "")
    for plat, a0, a1 in (avisos or []):
        m = (d.plataforma == plat) & (d.fecha >= a0) & (d.fecha <= a1)
        d.loc[m, "sin_datos"] = True
        d.loc[m, "fuente"] = "aviso_oficial"
    return d[["fecha", "plataforma", "n_mx", "n_ar", "sin_datos", "fuente"]]


# ============================================================================ statistics
def kappa_conf(C: np.ndarray) -> float:
    """Cohen's kappa from a k x k confusion matrix (rows = A, columns = B)."""
    n = C.sum()
    if n <= 0:
        return float("nan")
    po = np.trace(C) / n
    pe = float((C.sum(1) / n) @ (C.sum(0) / n))
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


CATS = {"high": 0, "none": 1, "low": 2}


def onehot_conf(a: np.ndarray, b: np.ndarray, binaria: str | None = None) -> np.ndarray:
    """Per element, the 9 (3x3) or 4 (2x2) vector of its confusion cell."""
    ia = np.array([CATS[x] for x in a])
    ib = np.array([CATS[x] for x in b])
    if binaria:
        k = CATS[binaria]
        ia, ib, kk = (ia == k).astype(int), (ib == k).astype(int), 2
    else:
        kk = 3
    M = np.zeros((len(ia), kk * kk))
    M[np.arange(len(ia)), ia * kk + ib] = 1
    return M


class Boot:
    """Bootstrap over units (block x year): replicate weights per unit (multinomial)."""

    def __init__(self, unidades: np.ndarray, n_boot: int, rng: np.random.Generator):
        self.u, self.inv = np.unique(unidades, return_inverse=True)
        U = len(self.u)
        draws = rng.integers(0, U, size=(n_boot, U))
        self.W = np.zeros((n_boot, U))
        for b in range(n_boot):
            self.W[b] = np.bincount(draws[b], minlength=U)

    def sumas(self, X: np.ndarray) -> np.ndarray:
        """Weighted sum per replicate of the columns X (n x k) -> (B x k)."""
        X = np.asarray(X, float).reshape(len(self.inv), -1)
        G = np.zeros((len(self.u), X.shape[1]))
        np.add.at(G, self.inv, X)
        return self.W @ G

    def mediana(self, v: np.ndarray, trozo: int = 200) -> np.ndarray:
        v = np.asarray(v, float)
        orden = np.argsort(v, kind="stable")
        vs, inv = v[orden], self.inv[orden]
        out = []
        for i in range(0, len(self.W), trozo):
            We = self.W[i:i + trozo][:, inv]
            cum = np.cumsum(We, axis=1)
            tot = cum[:, -1]
            p1, p2 = np.floor((tot + 1) / 2), np.floor(tot / 2) + 1
            i1 = (cum < p1[:, None]).sum(1)
            i2 = (cum < p2[:, None]).sum(1)
            out.append((vs[np.minimum(i1, len(vs) - 1)] + vs[np.minimum(i2, len(vs) - 1)]) / 2)
        return np.concatenate(out)


def ic(x: np.ndarray, nivel: float = 0.95) -> list[float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return [float("nan"), float("nan")]
    a = (1 - nivel) / 2
    return [float(np.quantile(x, a)), float(np.quantile(x, 1 - a))]


M1_N_BOOT = 2000   # replicates of the M1 CI (the same as before K1-en: identical metrics)


def razon_global(num, den, semilla: int) -> dict:
    """Baseline M1: global ratio sum(num)/sum(den) with a 95 % bootstrap CI over paired units (nucleo.baseline)."""
    x = global_count_ratio(np.asarray(num, float), np.asarray(den, float), n_boot=M1_N_BOOT, seed=semilla)
    return {"razon": x["ratio"], "ic95": x["ci95"], "n": x["n"]}


def ale(s, p, c=1.0):
    return np.abs(np.log((np.asarray(s, float) + c) / (np.asarray(p, float) + c)))


def r(x, nd=4):
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        return [r(v, nd) for v in x]
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    return None if not math.isfinite(xf) else round(xf, nd)


# ============================================================================ per-country panels
def bloque_de(celda1: pd.Series, grados: int) -> pd.Series:
    ab = celda1.astype(str).str.split("_", expand=True).astype(int)
    return (ab[0] // grados).astype(str) + "_" + (ab[1] // grados).astype(str)


def meses_incompletos(disp: pd.DataFrame, desde: str, hasta: str) -> tuple[set, set]:
    """(months with a day without any MODIS -> incomplete for H_TA; months with a day without Terra -> excluded from H_T)."""
    d = disp[(disp.fecha >= desde) & (disp.fecha <= hasta)]
    p = d.pivot_table(index="fecha", columns="plataforma", values="sin_datos", aggfunc="max")
    for c in ("Terra", "Aqua"):
        if c not in p:
            p[c] = False
    p = p.fillna(False).astype(bool)
    ym = lambda idx: {(t.year, t.month) for t in idx}
    ninguno = ym(p.index[p.Terra & (p.Aqua | (p.index < pd.Timestamp("2002-07-04")))])
    sin_terra = ym(p.index[p.Terra])
    return ninguno, sin_terra


def pesos_reloj_T(det: pd.DataFrame, F: pd.DataFrame) -> np.ndarray:
    """H_T (Terra-only predictor, clock 'T') for J1/P5: w of 'T' per (mes, turno, celda1); cell without factor -> country k (s = 1)."""
    FT = F[F.reloj == "T"]
    w_c = FT.set_index(["mes", "turno", "celda1"])["w"]
    k_p = FT.drop_duplicates(["mes", "turno"]).set_index(["mes", "turno"])["k"]
    idx = pd.MultiIndex.from_arrays([det.mes.astype(int).to_numpy(), det.turno.to_numpy(), det.celda1.astype(str).to_numpy()])
    w = w_c.reindex(idx).to_numpy(dtype=float)
    k = k_p.reindex(pd.MultiIndex.from_arrays([det.mes.astype(int).to_numpy(), det.turno.to_numpy()])).to_numpy(dtype=float)
    return np.where(np.isfinite(w), w, k)


def predecir(FZ, det: pd.DataFrame, F: pd.DataFrame, disp: pd.DataFrame) -> pd.DataFrame:
    """S_hat_TA (pesos_modis contract) per celda1 x year x month; NaN if some day has no MODIS."""
    d = det.copy()
    d["celda1"] = d["celda1"].astype(str)
    w = np.asarray(FZ.pesos_modis(d[["plataforma", "acq_date_utc", "mes", "turno", "celda1"]], F, disp), float)
    d["h"] = w * d.n
    d["h_nan"] = ~np.isfinite(d["h"].to_numpy())
    g = d.groupby(["celda1", "anio", "mes"]).agg(H_TA=("h", "sum"), h_nan=("h_nan", "max"))
    g.loc[g.h_nan, "H_TA"] = np.nan
    return g[["H_TA"]].reset_index()


def panel_pais(FZ, pais: str, F: pd.DataFrame, mod: pd.DataFrame, vi: pd.DataFrame, disp: pd.DataFrame,
               desde: str, hasta: str, objetivo: str, testigo: str, cfg) -> pd.DataFrame:
    """Panel 1 deg cell x year x month on [desde, hasta]: T, A, H_TA, S (target), W (witness), SN (S-NPP), N20 (NOAA-20)."""
    m = mod[(mod.acq_date_utc >= desde) & (mod.acq_date_utc <= hasta)]
    pred = predecir(FZ, m, F, disp)
    cruda = m.assign(celda1=m.celda1.astype(str)).pivot_table(index=["celda1", "anio", "mes"], columns="plataforma",
                                                              values="n", aggfunc="sum", observed=True).fillna(0)
    for c in ("Terra", "Aqua"):
        if c not in cruda:
            cruda[c] = 0.0
    v = vi[(vi.anio * 100 + vi.mes >= int(desde[:4]) * 100 + int(desde[5:7])) &
           (vi.anio * 100 + vi.mes <= int(hasta[:4]) * 100 + int(hasta[5:7]))]
    vv = v.assign(celda1=v.celda1.astype(str)).pivot_table(index=["celda1", "anio", "mes"], columns="plataforma",
                                                           values="n", aggfunc="sum").fillna(0)
    for c in ("S-NPP", "NOAA-20"):
        if c not in vv:
            vv[c] = 0.0
    celdas = sorted(set(cruda.index.get_level_values(0)) | set(vv.index.get_level_values(0)))
    meses = [(t.year, t.month) for t in pd.period_range(desde[:7], hasta[:7], freq="M")]
    if cfg.get("excluir_enero_2012", True):
        meses = [ym for ym in meses if ym != (2012, 1)]
    idx = pd.MultiIndex.from_tuples([(c, y, mm) for c in celdas for (y, mm) in meses], names=["celda1", "anio", "mes"])
    P = pd.DataFrame(index=idx)
    P["T"] = cruda["Terra"].reindex(idx).fillna(0).to_numpy()
    P["A"] = cruda["Aqua"].reindex(idx).fillna(0).to_numpy()
    P["H_TA"] = pred.set_index(["celda1", "anio", "mes"])["H_TA"].reindex(idx).to_numpy()
    sinmod = ~np.isfinite(P["H_TA"].to_numpy()) & (P["T"] + P["A"] == 0).to_numpy()
    P.loc[sinmod, "H_TA"] = 0.0      # no MODIS detections -> 0 (not NaN), except an incomplete month (below)
    P["SN"] = vv["S-NPP"].reindex(idx).fillna(0).to_numpy()
    P["N20"] = vv["NOAA-20"].reindex(idx).fillna(0).to_numpy()
    P = P.reset_index()
    inc, _ = meses_incompletos(disp, desde, hasta)
    huecos = {tuple(int(x) for x in s.split("-")) for s in cfg.get("meses_excluidos_huecos_viirs", [])}
    P["excluido"] = [((y, mm) in inc) or ((y, mm) in huecos) for y, mm in zip(P.anio, P.mes)]
    col = {"S-NPP": "SN", "NOAA-20": "N20"}
    P["S"] = P[col[objetivo]]
    P["W"] = P[col[testigo]]
    ab = P.celda1.str.split("_", expand=True).astype(int)
    P["a"], P["o"] = ab[0], ab[1]
    P["bloque"] = (P.a // 3).astype(str) + "_" + (P.o // 3).astype(str)
    P["bloque6"] = (P.a // 6).astype(str) + "_" + (P.o // 6).astype(str)
    return P


def base_serie(vi: pd.DataFrame, desde: str, hasta: str, cambio: str, cfg, f_e1b: float = 1.0) -> pd.DataFrame:
    """VIIRS series of the base (E1c: S-NPP before `cambio`, NOAA-20 from `cambio`) per celda1 x year x month."""
    ym = vi.anio * 100 + vi.mes
    y0, y1, yc = int(desde[:4]) * 100 + int(desde[5:7]), int(hasta[:4]) * 100 + int(hasta[5:7]), int(cambio[:4]) * 100 + int(cambio[5:7])
    sel = (ym >= y0) & (ym <= y1) & (((vi.plataforma == "S-NPP") & (ym < yc)) | ((vi.plataforma == "NOAA-20") & (ym >= yc)))
    if cfg.get("excluir_enero_2012", True):
        sel &= ym != 201201
    b = vi[sel].copy()
    b["n"] = b.n * np.where(b.plataforma == "S-NPP", f_e1b, 1.0)
    b["celda1"] = b.celda1.astype(str)
    b = b.groupby(["celda1", "anio", "mes"], as_index=False).n.sum()
    return b, sorted({(y // 100, y % 100) for y in range(y0, y1 + 1) if 1 <= y % 100 <= 12
                      and not (cfg.get("excluir_enero_2012", True) and y == 201201)})


def umbrales_unidad(base: pd.DataFrame, unidades: list, clave, meses_base: list, inc: set) -> dict:
    """Type 6 thresholds per (unit, calendar month) with all base years (zeros included; incomplete months left out)."""
    piv = base.groupby([clave, "anio", "mes"]).n.sum()
    out = {}
    for u in unidades:
        for m in range(1, 13):
            vals = [float(piv.get((u, y, m), 0.0)) for (y, mm) in meses_base if mm == m and (y, mm) not in inc]
            out[(u, m)] = VM.umbrales(vals)
    return out


def marcar(valores, lo, hi, U: dict, unidades, meses):
    est, u1 = [], []
    for v, l, h, u, m in zip(valores, lo, hi, unidades, meses):
        th = U[(u, m)]
        if not VM.base_suficiente(th):
            est.append(VM.INSUFFICIENT)
            u1.append(None)
            continue
        e_v, e_l, e_h = VM.regla_u1(v, th), VM.regla_u1(l, th), VM.regla_u1(h, th)
        if e_l == e_h and e_l != VM.NONE:
            est.append(VM.UNUSUAL + "_" + e_l)
        elif e_l == VM.NONE and e_h == VM.NONE:
            est.append(VM.TYPICAL)
        else:
            est.append(VM.POSSIBLY)
        u1.append(e_v)
    return np.array(est, dtype=object), np.array(u1, dtype=object)


# ============================================================================ tests
VENTANA_INTERVALOS: tuple | None = None   # set by correr(): intervals of the SAME calibration as the mode


def intervalos(FZ, pais, s_hat: np.ndarray, tramo: str, nivel: str, forma: str):
    """Absolute interval [S_hat*lo, S_hat*hi] (multiplicative contract). S_hat <= 0 -> the contract returns (0, inf): [0, inf]."""
    import inspect
    kw = {"ventana": VENTANA_INTERVALOS} if VENTANA_INTERVALOS and "ventana" in inspect.signature(FZ.intervalo).parameters else {}
    s_hat = np.asarray(s_hat, float)
    lo = np.empty(len(s_hat))
    hi = np.empty(len(s_hat))
    cache = {}
    for i, s in enumerate(s_hat):
        if forma != "multiplicativo":
            raise ValueError(f"unknown interval form: {forma}")
        if not np.isfinite(s):
            lo[i] = hi[i] = np.nan
            continue
        if s not in cache:
            cache[s] = FZ.intervalo(pais, float(s), tramo, nivel, **kw)
        a, b = cache[s]
        if s <= 0:
            lo[i], hi[i] = 0.0, (math.inf if not math.isfinite(b) else 0.0)
        else:
            lo[i], hi[i] = s * a, s * b
    return lo, hi


def agregar_bloques(P: pd.DataFrame, cols: list, clave: str = "bloque") -> pd.DataFrame:
    return P.groupby([clave, "anio", "mes"], as_index=False)[cols].sum(min_count=1)


def prueba_P2(FZ, pais, B: pd.DataFrame, U: dict, cfg, rng, sufijo="", tramo: str = "TA") -> dict:
    """P2 / P2b at 3 deg block: kappa_cross (target vs H_TA), kappa_twins (target vs witness), same block-months.
    `tramo` = clock of the interval: "TA" (core, default) or "T" (P5: the H_TA column then carries H_T)."""
    forma = cfg["intervalo"]["forma"]
    lo, hi = intervalos(FZ, pais, B.H_TA.to_numpy(), tramo, cfg["intervalo"]["nivel_bloque"], forma)
    ones = B.S.to_numpy()
    e_S, u_S = marcar(ones, ones, ones, U, B.bloque, B.mes)
    e_W, u_W = marcar(B.W.to_numpy(), B.W.to_numpy(), B.W.to_numpy(), U, B.bloque, B.mes)
    e_H, u_H = marcar(B.H_TA.to_numpy(), B.H_TA.to_numpy(), B.H_TA.to_numpy(), U, B.bloque, B.mes)
    e_HI, _ = marcar(B.H_TA.to_numpy(), lo, hi, U, B.bloque, B.mes)
    e_M1, u_M1 = marcar(B.M1.to_numpy(), B.M1.to_numpy(), B.M1.to_numpy(), U, B.bloque, B.mes)
    e_M0, u_M0 = marcar(B.M0.to_numpy(), B.M0.to_numpy(), B.M0.to_numpy(), U, B.bloque, B.mes)
    ok = np.array([x is not None for x in u_S]) & ~B.excluido.to_numpy() & np.isfinite(B.H_TA.to_numpy())
    gem = ok & B.testigo_ok.to_numpy()
    unid = (B.bloque + "|" + B.anio.astype(str)).to_numpy()
    res = {"n_bloque_meses": int(ok.sum()), "n_pareado_gemelos": int(gem.sum()), "n_bloques": int(B.bloque[ok].nunique())}
    if ok.sum() == 0:
        return res
    bt = Boot(unid[ok], cfg["n_boot"], rng)
    btg = Boot(unid[gem], cfg["n_boot"], rng) if gem.sum() else None

    def kap(a, b, mask, boot, binaria=None):
        M = onehot_conf(a[mask], b[mask], binaria)
        k = int(round(math.sqrt(M.shape[1])))
        pt = kappa_conf(M.sum(0).reshape(k, k))
        bs = np.array([kappa_conf(x.reshape(k, k)) for x in boot.sumas(M)]) if boot is not None else np.array([])
        return pt, bs

    kc, kc_b = kap(u_S, u_H, ok, bt)
    res["kappa_cruzado"] = {"punto": r(kc), "ic95": r(ic(kc_b))}
    res["kappa_cruzado_M1"] = {"punto": r(kap(u_S, u_M1, ok, None)[0])}
    res["kappa_cruzado_M0"] = {"punto": r(kap(u_S, u_M0, ok, None)[0])}
    res["kappa_cruzado_solo_high"] = r(kap(u_S, u_H, ok, None, "high")[0])
    res["kappa_cruzado_solo_low"] = r(kap(u_S, u_H, ok, None, "low")[0])
    res["prevalencia"] = {"objetivo_high": r(np.mean(u_S[ok] == "high")), "objetivo_low": r(np.mean(u_S[ok] == "low")),
                          "H_TA_high": r(np.mean(u_H[ok] == "high")), "H_TA_low": r(np.mean(u_H[ok] == "low"))}
    res["acuerdo_bruto"] = r(np.mean(u_S[ok] == u_H[ok]))
    res["tabla_3x3_objetivo_x_HTA"] = onehot_conf(u_S[ok], u_H[ok]).sum(0).reshape(3, 3).astype(int).tolist()
    if gem.sum():
        kg, kg_b = kap(u_S, u_W, gem, btg)
        kcp, kcp_b = kap(u_S, u_H, gem, btg)
        # paired ratio with the same replicates
        Mw, Mh = onehot_conf(u_S[gem], u_W[gem]), onehot_conf(u_S[gem], u_H[gem])
        rw, rh = btg.sumas(Mw), btg.sumas(Mh)
        coc = np.array([kappa_conf(b.reshape(3, 3)) / kappa_conf(a.reshape(3, 3)) for a, b in zip(rw, rh)])
        res["kappa_gemelos"] = {"punto": r(kg), "ic95": r(ic(kg_b))}
        res["kappa_cruzado_pareado"] = {"punto": r(kcp), "ic95": r(ic(kcp_b))}
        res["cociente_pareado"] = {"punto": r(kcp / kg if kg else float("nan")), "ic95": r(ic(coc))}
    # P2b: three states with the IC80 of H_TA vs the target flag
    unus = np.array([str(x).startswith(VM.UNUSUAL) for x in e_HI])
    typ = e_HI == VM.TYPICAL
    pos = e_HI == VM.POSSIBLY
    dir_ok = np.array([str(e).endswith(str(s)) for e, s in zip(e_HI, u_S)])
    cov = (B.S.to_numpy() >= lo - 1e-9) & (B.S.to_numpy() <= hi + 1e-9)
    res["P2b"] = {"n": int(ok.sum()),
                  "pct_unusual": r(unus[ok].mean()), "pct_typical": r(typ[ok].mean()), "pct_indeterminado": r(pos[ok].mean()),
                  "precision_unusual": r(dir_ok[ok & unus].mean()) if (ok & unus).any() else None,
                  "precision_typical": r((u_S[ok & typ] == "none").mean()) if (ok & typ).any() else None,
                  "cobertura_ic80_bloque": r(cov[ok].mean()),
                  "cobertura_ic80_bloque_ic95": r(ic(bt.sumas(cov[ok].astype(float))[:, 0] / bt.sumas(np.ones(ok.sum()))[:, 0]))}
    # by year
    res["por_anio"] = {}
    for y in sorted(B.anio[ok].unique()):
        my = ok & (B.anio.to_numpy() == y)
        mg = gem & (B.anio.to_numpy() == y)
        res["por_anio"][int(y)] = {"n": int(my.sum()), "kappa_cruzado": r(kap(u_S, u_H, my, None)[0]),
                                   "kappa_gemelos": r(kap(u_S, u_W, mg, None)[0]) if mg.sum() else None}
    # sensitivity with 6 deg blocks x year (only the CI of kappa_cross)
    u6 = (B.bloque6 + "|" + B.anio.astype(str)).to_numpy()
    b6 = Boot(u6[ok], cfg["n_boot"], rng)
    res["kappa_cruzado_ic95_bloque6xanio"] = r(ic(kap(u_S, u_H, ok, b6)[1]))
    res["_mascaras"] = (ok, u_S, u_H)
    return res


def prueba_P3_P4(FZ, pais, C: pd.DataFrame, cfg, rng, tramo: str = "TA") -> dict:
    """P3 coverage of the IC80 at 1 deg cell (evaluable cells, including S = 0 and S_hat = 0) and P4 skill vs M1.
    Both P3 populations are ALWAYS reported (B-R10): with S_hat = 0 (`cobertura`, interval (0, inf) that always
    covers) and without S_hat = 0 (`cobertura_excluye_Shat_cero`); config `p3.poblacion` says which one the verdict uses."""
    ok = C.evaluable.to_numpy() & ~C.excluido.to_numpy() & np.isfinite(C.H_TA.to_numpy())
    D = C[ok]
    lo, hi = intervalos(FZ, pais, D.H_TA.to_numpy(), tramo, cfg["intervalo"]["nivel_celda"], cfg["intervalo"]["forma"])
    S = D.S.to_numpy()
    cov = ((S >= lo - 1e-9) & (S <= hi + 1e-9)).astype(float)
    covW = ((D.W.to_numpy() >= lo - 1e-9) & (D.W.to_numpy() <= hi + 1e-9)).astype(float)
    unid = (D.bloque + "|" + D.anio.astype(str)).to_numpy()
    bt = Boot(unid, cfg["n_boot"], rng)
    one = np.ones(len(D))
    den = bt.sumas(one)[:, 0]
    c = cfg["pseudoconteo_log"]
    e_m, e_1, e_1a, e_0 = ale(S, D.H_TA, c), ale(S, D.M1, c), ale(S, D.M1A, c), ale(S, D.M0, c)
    md_m, md_1 = bt.mediana(e_m), bt.mediana(e_1)
    clases = pd.cut(D.H_TA, [-np.inf, 5, 20, 100, np.inf], right=False, labels=["<5", "5-20", "20-100", ">=100"])
    res = {"n_celda_meses": int(len(D)), "n_celdas": int(D.celda1.nunique()), "n_S_cero": int((S == 0).sum()),
           "n_Shat_cero": int((D.H_TA.to_numpy() == 0).sum()),
           "P3": {"cobertura": r(cov.mean()), "ic95": r(ic(bt.sumas(cov)[:, 0] / den)),
                  "cobertura_vs_testigo": r(covW[D.testigo_ok.to_numpy()].mean()) if D.testigo_ok.any() else None,
                  "cobertura_sin_Shat_cero_reporte": r(cov[(D.H_TA.to_numpy() > 0)].mean()),
                  "ancho_mediano_factor": r(np.median((hi + 1) / (lo + 1))),
                  "por_clase_Shat": {str(k): {"n": int((clases == k).sum()), "cobertura": r(cov[(clases == k).to_numpy()].mean())}
                                     for k in clases.cat.categories if (clases == k).any()},
                  "por_anio": {int(y): r(cov[(D.anio == y).to_numpy()].mean()) for y in sorted(D.anio.unique())},
                  **p3_poblaciones(cov, D.H_TA.to_numpy() > 0, bt, cfg)},
           "P4": {"MdALE_metodo": r(np.median(e_m)), "MdALE_M1": r(np.median(e_1)), "MdALE_M1_Aqua": r(np.median(e_1a)),
                  "MdALE_M0": r(np.median(e_0)),
                  "skill": r(1 - np.median(e_m) / np.median(e_1)), "skill_ic95": r(ic(1 - md_m / md_1)),
                  "diferencia_MdALE": r(np.median(e_m) - np.median(e_1)), "diferencia_MdALE_ic95": r(ic(md_m - md_1)),
                  "por_anio": {int(y): r(1 - np.median(e_m[(D.anio == y).to_numpy()]) / np.median(e_1[(D.anio == y).to_numpy()]))
                               for y in sorted(D.anio.unique())}}}
    return res


P3_POBLACIONES = ("incluye_s0", "excluye_s0")   # "s0" = S_hat = 0 (zero MODIS prediction -> interval (0, inf))


def p3_poblacion(cfg) -> str:
    """P3 population used by the verdict (config `p3.poblacion`; default `incluye_s0`, the previous behaviour)."""
    pob = (cfg.get("p3") or {}).get("poblacion", "incluye_s0")
    if pob not in P3_POBLACIONES:
        raise SystemExit(f"REFUSED: p3.poblacion = {pob!r}; valid values: {list(P3_POBLACIONES)}")
    return pob


def p3_poblaciones(cov: np.ndarray, con_shat: np.ndarray, bt: "Boot", cfg) -> dict:
    """The two P3 coverage figures with their 95 % CI (same replicates `bt`; `Boot.sumas` consumes no random numbers, so
    it does not alter the core sequence). New keys; `cobertura` (with S_hat = 0) does not change."""
    w = con_shat.astype(float)
    num, den = bt.sumas(np.c_[cov, cov * w]), bt.sumas(np.c_[np.ones(len(cov)), w])
    with np.errstate(invalid="ignore", divide="ignore"):
        ic_ex = ic(num[:, 1] / den[:, 1])
    return {"poblaciones": {
        "incluye_s0": {"cobertura": r(cov.mean()), "ic95": r(ic(num[:, 0] / den[:, 0])), "n": int(len(cov))},
        "excluye_s0": {"cobertura": r(cov[con_shat].mean()) if con_shat.any() else None, "ic95": r(ic_ex),
                       "n": int(con_shat.sum())}},
        "n_excluidos_Shat_cero": int(len(cov) - con_shat.sum()),
        "cobertura_excluye_Shat_cero": r(cov[con_shat].mean()) if con_shat.any() else None,
        "poblacion_veredicto": p3_poblacion(cfg)}


def resumen_P3(p3: dict) -> dict | None:
    """Both P3 coverages for verdict*.json (lot 3 point 7: always reported, with the number of cell-months left out for
    S_hat = 0 and the population that decides). None if P3 has no population block."""
    pob = (p3 or {}).get("poblaciones")
    if not pob:
        return None
    n_ex = (p3.get("n_excluidos_Shat_cero") if p3.get("n_excluidos_Shat_cero") is not None
            else pob["incluye_s0"]["n"] - pob["excluye_s0"]["n"])
    return {"incluye_s0": pob["incluye_s0"], "excluye_s0": pob["excluye_s0"], "n_excluidos_Shat_cero": int(n_ex),
            "decide": p3.get("poblacion_veredicto")}


def prueba_P1(B_all: pd.DataFrame, cfg, rng) -> dict:
    ok = ~B_all.excluido.to_numpy() & np.isfinite(B_all.H_TA.to_numpy())
    D = B_all[ok]
    unid = (D.bloque + "|" + D.anio.astype(str)).to_numpy()
    bt = Boot(unid, cfg["n_boot"], rng)
    X = D[["S", "H_TA", "M1", "M0", "W"]].to_numpy()
    sb = bt.sumas(X)
    res = {"B_objetivo_sobre_HTA": r(D.S.sum() / D.H_TA.sum()), "ic90": r(ic(sb[:, 0] / sb[:, 1], 0.90)),
           "B_M1": r(D.S.sum() / D.M1.sum()), "B_M0": r(D.S.sum() / D.M0.sum()),
           "B_testigo_sobre_HTA": r(D.W[D.testigo_ok].sum() / D.H_TA[D.testigo_ok].sum()) if D.testigo_ok.any() else None,
           "por_anio": {int(y): r(D.S[D.anio == y].sum() / D.H_TA[D.anio == y].sum()) for y in sorted(D.anio.unique())}}
    return res


def prueba_J2(B: pd.DataFrame, mask_p2: np.ndarray, Pn: pd.DataFrame, cfg, rng) -> dict:
    """J2: log((NOAA-20+1)/(S-NPP+1)) at block x month (P2 population with both twins) and country x month (check)."""
    c = cfg["pseudoconteo_log"]
    m = mask_p2 & B.ambos_vi.to_numpy()
    out = {}
    if m.sum():
        D = B[m]
        x = np.log((D.N20.to_numpy() + c) / (D.SN.to_numpy() + c))
        bt = Boot((D.bloque + "|" + D.anio.astype(str)).to_numpy(), cfg["n_boot"], rng)
        mb = bt.sumas(np.c_[x, np.ones(len(x))])
        out["bloque"] = {"n": int(m.sum()), "media_log": r(x.mean()), "ic95": r(ic(mb[:, 0] / mb[:, 1])),
                         "MdALE_gemelos": r(np.median(np.abs(x)))}
    Pp = Pn[Pn.ambos_vi & ~Pn.excluido].groupby(["anio", "mes"])[["N20", "SN"]].sum()
    if len(Pp):
        xp = np.log(Pp.N20 / Pp.SN)
        out["pais_chequeo"] = {"n_meses": int(len(Pp)), "media_log": r(xp.mean()),
                               "por_anio": {int(y): r(v) for y, v in xp.groupby(level=0).mean().items()}}
    return out


def prueba_J1(FZ, pais: str, F: pd.DataFrame, mod_j1: pd.DataFrame, disp: pd.DataFrame, cfg, rng) -> dict:
    d0, d1 = cfg["j1"]["ventana"]
    det = mod_j1.copy()
    det["celda1"] = det.celda1.astype(str)
    w_ta = np.asarray(FZ.pesos_modis(det[["plataforma", "acq_date_utc", "mes", "turno", "celda1"]], F, disp), float)
    det["hta"] = w_ta * det.n
    tt = det[det.plataforma == "Terra"]
    det.loc[tt.index, "ht"] = pesos_reloj_T(tt, F) * tt.n
    det["hta_nan"] = ~np.isfinite(det["hta"].to_numpy())
    g = det.groupby(["anio", "mes"]).agg(hta=("hta", "sum"), ht=("ht", "sum"), hnan=("hta_nan", "max"))
    ninguno, sin_terra = meses_incompletos(disp, d0, d1)
    excl = set(ninguno) | (set(sin_terra) if cfg["j1"]["excluir_meses_con_hueco_terra"] else set())
    g = g[np.array([(y, m) not in excl for y, m in g.index]) & ~g["hnan"].to_numpy() & (g.ht > 0).to_numpy()]
    x = np.log(g.hta / g.ht)
    anios = g.index.get_level_values(0).to_numpy()
    bt = Boot(anios, cfg["n_boot"], rng)
    mb = bt.sumas(np.c_[x.to_numpy(), np.ones(len(x))])
    return {"n_meses": int(len(g)), "meses_excluidos": sorted(f"{y}-{m:02d}" for y, m in excl),
            "media_log": r(x.mean()), "ic95": r(ic(mb[:, 0] / mb[:, 1])),
            "por_anio": {int(y): r(v) for y, v in x.groupby(level=0).mean().items()},
            "control_crudo_media_log_TA_sobre_T": r(np.log(det.groupby(["anio", "mes"]).n.sum() /
                                                           det[det.plataforma == "Terra"].groupby(["anio", "mes"]).n.sum()).mean())}


def prueba_CV(L: Lector, pais: str, cfg) -> dict:
    d0, d1 = cfg["c_v"]["ventana"]
    sql = f"""SELECT CAST(anio AS INT) anio, CAST(mes AS INT) mes,
                     count(*) FILTER (plataforma='S-NPP') s, count(*) FILTER (plataforma IN ('Terra','Aqua')) ta
              FROM read_parquet('{PROC / f"deteccion_{pais}.parquet"}')
              WHERE procesamiento='estandar' AND NOT en_mascara AND plataforma IN ('S-NPP','Terra','Aqua')
                AND acq_date_utc BETWEEN DATE '{{d0}}' AND DATE '{{d1}}' GROUP BY ALL ORDER BY 1, 2"""
    m = L.q(sql, d0, d1)
    lr = np.log((m.s + 1) / (m.ta + 1)).to_numpy()
    des = lr - pd.Series(lr).groupby(m.mes.to_numpy()).transform("mean").to_numpy()
    p = pettitt(des)
    y, mm = (int(x) for x in cfg["c_v"]["mes_escalon"].split("-"))
    tras = ((m.anio > y) | ((m.anio == y) & (m.mes >= mm))).to_numpy()
    return {"n_meses": int(len(m)), "pettitt_punto": f"{int(m.anio[p['change_index']])}-{int(m.mes[p['change_index']]):02d}",
            "pettitt_p": r(p["p"]), "escalon_log_en_mes_escalon": r(des[tras].mean() - des[~tras].mean()),
            "razon_anual": {int(a): r(g.s.sum() / g.ta.sum()) for a, g in m.groupby("anio")}}


# ============================================================================ S8 (ADR-0012 option 2): reported, does not decide
def _pend_bloque(g: pd.DataFrame, col: str, c: float) -> tuple[float, int]:
    return seasonal_sen_slope(np.log(g[col].to_numpy(float) + c), g.anio.to_numpy(), g.mes.to_numpy())


def prueba_S8(B: pd.DataFrame, ok_p2: np.ndarray, mc: dict, cfg, rng) -> dict:
    """SEASONAL Sen slope (same month of different years; units: per year) of log(x + c) per 3 deg block, for the
    target VIIRS series (test: NOAA-20) and for H_TA, M1 and M0; difference target - H_TA per block and for the
    country aggregate, with a bootstrap CI over blocks (own generator). Ceiling: witness - target where the witness
    has enough pairs. REPORTED, DOES NOT DECIDE: it never enters the verdict."""
    sc = cfg.get("s8", {})
    c = float(sc.get("pseudoconteo", cfg["pseudoconteo_log"]))
    min_pares = int(sc.get("min_pares_por_bloque", 6))
    nivel = float(sc.get("nivel_ic", 0.95))
    base_ok = ~B.excluido.to_numpy().astype(bool) & np.isfinite(B.H_TA.to_numpy())
    m = (ok_p2 & base_ok) if sc.get("poblacion", "p2") == "p2" else base_ok
    D = B[m]
    cols = {"objetivo": "S", "H_TA": "H_TA", "M1": "M1", "M0": "M0"}
    filas = []
    for b, g in D.groupby("bloque", sort=True):
        f = {"bloque": b}
        for nom, col in cols.items():
            f[nom], f[f"pares_{nom}"] = _pend_bloque(g, col, c)
        gt = g[g.testigo_ok.astype(bool)]
        f["testigo"], f["pares_testigo"] = _pend_bloque(gt, "W", c) if len(gt) else (float("nan"), 0)
        f["objetivo_en_meses_testigo"] = _pend_bloque(gt, "S", c)[0] if len(gt) else float("nan")
        filas.append(f)
    T = pd.DataFrame(filas)
    out = {"decide": False, "estado": "reported, does not decide (ADR-0012 option 2)",
           "serie_viirs": mc["objetivo"], "metodo": "seasonal Sen slope of log(x + c) per year (Hirsch et al. 1982)",
           "pseudoconteo": c, "poblacion": sc.get("poblacion", "p2"), "min_pares_por_bloque": min_pares}
    if not len(T):
        return {**out, "n_bloques": 0}
    T = T[T.pares_objetivo >= min_pares].reset_index(drop=True)
    out["n_bloques"] = int(len(T))
    if not len(T):
        return out
    out["pendiente_mediana_bloques"] = {k: r(np.nanmedian(T[k])) for k in cols}
    idx = rng.integers(0, len(T), size=(cfg["n_boot"], len(T)))
    for ref in ("H_TA", "M1", "M0"):
        d = (T["objetivo"] - T[ref]).to_numpy(float)
        sg = np.sign(T["objetivo"].to_numpy(float)) * np.sign(T[ref].to_numpy(float))
        out[f"diferencia_objetivo_menos_{ref}"] = {
            "mediana_bloques": r(np.nanmedian(d)), f"ic{int(round(nivel * 100))}": r(ic(np.nanmedian(d[idx], axis=1), nivel)),
            "mediana_abs": r(np.nanmedian(np.abs(d))),
            "fraccion_mismo_signo": r(np.mean(sg[sg != 0] > 0)) if (sg != 0).any() else None}
    # country aggregate: sum of the included blocks over all their non-excluded months with finite H_TA
    G = B[base_ok & B.bloque.isin(set(T.bloque)).to_numpy()]
    piv = G.pivot_table(index=["anio", "mes"], columns="bloque", values=["S", "H_TA"], aggfunc="sum", fill_value=0.0)
    S_ = piv["S"].reindex(columns=T.bloque, fill_value=0.0).to_numpy(float)
    H_ = piv["H_TA"].reindex(columns=T.bloque, fill_value=0.0).to_numpy(float)
    an, me = piv.index.get_level_values(0).to_numpy(), piv.index.get_level_values(1).to_numpy()
    pend = lambda x: seasonal_sen_slope(np.log(x + c), an, me)[0]  # noqa: E731
    po, ph = pend(S_.sum(1)), pend(H_.sum(1))
    bs = np.array([pend(S_[:, i].sum(1)) - pend(H_[:, i].sum(1)) for i in idx])
    out["agregado_pais"] = {"pendiente_objetivo": r(po), "pendiente_H_TA": r(ph), "diferencia": r(po - ph),
                            f"ic{int(round(nivel * 100))}": r(ic(bs, nivel)), "n_meses": int(len(an))}
    tg = T[T.pares_testigo >= min_pares]
    if len(tg):
        dg = (tg.testigo - tg.objetivo_en_meses_testigo).to_numpy(float)
        out["techo_gemelos"] = {"n_bloques": int(len(tg)), "testigo": mc["testigo"],
                                "diferencia_testigo_menos_objetivo_mediana": r(np.nanmedian(dg)),
                                "mediana_abs": r(np.nanmedian(np.abs(dg)))}
    else:
        out["techo_gemelos"] = {"n_bloques": 0, "testigo": mc["testigo"],
                                "nota": f"the witness has < {min_pares} same-month pairs per block in this window"}
    out["por_bloque"] = {row.bloque: {k: r(getattr(row, k)) for k in cols} for row in T.itertuples(index=False)}
    return out


# ============================================================================ I-05: P2/P2b by MODIS count class
def etiquetas_clase(cortes: list) -> list[str]:
    c = [float(x) for x in cortes]
    fmt = lambda x: f"{x:g}"  # noqa: E731
    return [f"<{fmt(c[0])}"] + [f"{fmt(a)}-{fmt(b)}" for a, b in zip(c[:-1], c[1:])] + [f">={fmt(c[-1])}"]


def clase_de(x, cortes: list) -> np.ndarray:
    """Count class: [0, c1) -> 0, [c1, c2) -> 1, ..., [ck, inf) -> k (each cut belongs to the class above)."""
    return np.searchsorted(np.asarray(cortes, float), np.asarray(x, float), side="right")


def conteo_esperado(cal: pd.DataFrame, unidad: pd.Series, meses_cal: list, inc: set, conteo: str = "TA",
                    estadistico: str = "mediana_mensual") -> pd.Series:
    """Expected MODIS count per unit: statistic of the monthly counts (Terra+Aqua or Terra) in the calibration window
    of the mode, with zeros (months without detections) and without incomplete months. Index = unit."""
    plats = {"TA": ("Terra", "Aqua"), "T": ("Terra",)}[conteo]
    sel = cal.plataforma.isin(plats).to_numpy()
    d = cal[sel].assign(u=unidad[sel].to_numpy())
    piv = d.groupby(["u", "anio", "mes"]).n.sum()
    meses = [ym for ym in meses_cal if ym not in inc]
    unidades = sorted(set(d.u))
    idx = pd.MultiIndex.from_tuples([(u, y, m) for u in unidades for (y, m) in meses], names=["u", "anio", "mes"])
    x = piv.reindex(idx, fill_value=0).astype(float)
    if estadistico == "mediana_mensual":
        return x.groupby(level="u").median()
    if estadistico == "media_mensual":
        return x.groupby(level="u").mean()
    raise ValueError(f"unknown expected-count statistic: {estadistico}")


def _resumen_p2(u_S, u_H, u_W, e_HI, S, lo, hi, ok, gem, unid, n_boot, rng) -> dict:
    """kappa cross / twins / ratio and P2b on one population (same logic as prueba_P2; own generator)."""
    res = {"n": int(ok.sum()), "n_pareado_gemelos": int(gem.sum())}
    if ok.sum() == 0:
        return res

    def kap(a, b, mask, boot):
        M = onehot_conf(a[mask], b[mask])
        pt = kappa_conf(M.sum(0).reshape(3, 3))
        bs = np.array([kappa_conf(x.reshape(3, 3)) for x in boot.sumas(M)]) if boot is not None else np.array([])
        return pt, bs

    bt = Boot(unid[ok], n_boot, rng)
    kc, kc_b = kap(u_S, u_H, ok, bt)
    res["kappa_cruzado"] = {"punto": r(kc), "ic95": r(ic(kc_b))}
    if gem.sum():
        btg = Boot(unid[gem], n_boot, rng)
        kg, kg_b = kap(u_S, u_W, gem, btg)
        kcp = kap(u_S, u_H, gem, None)[0]
        rw, rh = btg.sumas(onehot_conf(u_S[gem], u_W[gem])), btg.sumas(onehot_conf(u_S[gem], u_H[gem]))
        coc = np.array([kappa_conf(b.reshape(3, 3)) / kappa_conf(a.reshape(3, 3)) for a, b in zip(rw, rh)])
        res["kappa_gemelos"] = {"punto": r(kg), "ic95": r(ic(kg_b))}
        res["kappa_cruzado_pareado"] = {"punto": r(kcp)}
        res["cociente_pareado"] = {"punto": r(kcp / kg if kg else float("nan")), "ic95": r(ic(coc))}
    unus = np.array([str(x).startswith(VM.UNUSUAL) for x in e_HI])
    typ, pos = e_HI == VM.TYPICAL, e_HI == VM.POSSIBLY
    dir_ok = np.array([str(e).endswith(str(s)) for e, s in zip(e_HI, u_S)])
    cov = (S >= lo - 1e-9) & (S <= hi + 1e-9)
    res["P2b"] = {"pct_unusual": r(unus[ok].mean()), "pct_typical": r(typ[ok].mean()), "pct_indeterminado": r(pos[ok].mean()),
                  "precision_unusual": r(dir_ok[ok & unus].mean()) if (ok & unus).any() else None,
                  "precision_typical": r((u_S[ok & typ] == "none").mean()) if (ok & typ).any() else None,
                  "cobertura_ic80": r(cov[ok].mean())}
    return res


def prueba_I05(FZ, pais: str, Q: pd.DataFrame, B: pd.DataFrame, U_bloque: dict, base: pd.DataFrame, meses_base: list,
               inc_base: set, cal: pd.DataFrame, meses_cal: list, inc_cal: set, cfg, rng, modo_i05: str) -> dict:
    """P2/P2b by expected MODIS count class (route I-05), pooling 1 deg cell-months and 3 deg block-months of each class
    and also per unit type. The bootstrap unit is 3 deg block x year (a cell inherits its block)."""
    ci = cfg.get("i05", {})
    cortes = ci.get("cortes_conteo_modis", [10, 30, 100])
    etq = etiquetas_clase(cortes)
    forma = cfg["intervalo"]["forma"]
    niveles = {"celda1": cfg["intervalo"]["nivel_celda"], "bloque3": cfg["intervalo"]["nivel_bloque"], **ci.get("nivel_intervalo", {})}
    calc = cal.assign(celda1=cal.celda1.astype(str))
    piezas = {}
    for tipo in ci.get("unidades", ["celda1", "bloque3"]):
        if tipo == "celda1":
            unidad_cal = calc.celda1
            X = Q[["celda1", "bloque", "anio", "mes", "S", "W", "H_TA", "excluido", "testigo_ok"]].rename(columns={"celda1": "u"})
            U = umbrales_unidad(base.rename(columns={"celda1": "u"}), sorted(X.u.unique()), "u", meses_base, inc_base)
        elif tipo == "bloque3":
            unidad_cal = bloque_de(calc.celda1, 3)
            X = B[["bloque", "anio", "mes", "S", "W", "H_TA", "excluido", "testigo_ok"]].assign(u=B.bloque)
            U = U_bloque
        else:
            raise ValueError(f"unknown I-05 unit: {tipo}")
        X = X.reset_index(drop=True)
        esp = conteo_esperado(calc, unidad_cal, meses_cal, inc_cal, ci.get("conteo", "TA"), ci.get("estadistico", "mediana_mensual"))
        X["esperado"] = X.u.map(esp).fillna(0.0).to_numpy(float)
        X["clase"] = clase_de(X.esperado.to_numpy(), cortes)
        lo, hi = intervalos(FZ, pais, X.H_TA.to_numpy(), "TA", niveles[tipo], forma)
        v = lambda col: X[col].to_numpy(float)  # noqa: E731
        _, u_S = marcar(v("S"), v("S"), v("S"), U, X.u, X.mes)
        _, u_W = marcar(v("W"), v("W"), v("W"), U, X.u, X.mes)
        _, u_H = marcar(v("H_TA"), v("H_TA"), v("H_TA"), U, X.u, X.mes)
        e_HI, _ = marcar(v("H_TA"), lo, hi, U, X.u, X.mes)
        ok = np.array([x is not None for x in u_S]) & ~X.excluido.to_numpy().astype(bool) & np.isfinite(v("H_TA"))
        gem = ok & X.testigo_ok.to_numpy().astype(bool)
        unid = (X.bloque.astype(str) + "|" + X.anio.astype(str)).to_numpy()
        piezas[tipo] = dict(u_S=u_S, u_H=u_H, u_W=u_W, e_HI=e_HI, S=v("S"), lo=lo, hi=hi, ok=ok, gem=gem, unid=unid,
                            clase=X.clase.to_numpy(),
                            n_unidades={etq[k]: int(X.u[X.clase == k].nunique()) for k in range(len(etq))})
    grupos = {"juntas": list(piezas)} if ci.get("juntar_unidades", True) else {}
    if ci.get("reportar_por_unidad", True):
        grupos.update({t: [t] for t in piezas})
    out = {"modo": modo_i05, "cortes_conteo_modis": cortes, "clases": etq, "conteo": ci.get("conteo", "TA"),
           "estadistico": ci.get("estadistico", "mediana_mensual"), "ventana_conteo_esperado": "calibration window of the mode",
           "unidades_por_clase": {t: p["n_unidades"] for t, p in piezas.items()}, "resultados": {}}
    claves = ("u_S", "u_H", "u_W", "e_HI", "S", "lo", "hi", "ok", "gem", "unid", "clase")
    for g, tipos in grupos.items():
        cat = {k: np.concatenate([piezas[t][k] for t in tipos]) for k in claves}
        out["resultados"][g] = {}
        for k, nombre in enumerate(etq):
            sel = cat["clase"] == k
            out["resultados"][g][nombre] = _resumen_p2(cat["u_S"], cat["u_H"], cat["u_W"], cat["e_HI"], cat["S"], cat["lo"],
                                                       cat["hi"], cat["ok"] & sel, cat["gem"] & sel, cat["unid"], cfg["n_boot"], rng)
    return out


# ============================================================================ P5: Terra-only era (ADR-0005 7a/7f)
P5_CRITERIOS = (None, "mismos_que_P2_P2b_P3")


def h_terra(mod: pd.DataFrame, F: pd.DataFrame, P: pd.DataFrame, desde: str, hasta: str) -> np.ndarray:
    """H_T per row of P (celda1 x year x month): sum of w_T * n over the Terra detections (clock 'T', the one of the
    Dec-2000 -> Jun-2002 era, simulated with Terra only as in J1); 0 if the cell-month has no Terra detections."""
    m = mod[(mod.acq_date_utc >= desde) & (mod.acq_date_utc <= hasta) & (mod.plataforma == "Terra")]
    idx = pd.MultiIndex.from_arrays([P.celda1.astype(str).to_numpy(), P.anio.astype(int).to_numpy(),
                                     P.mes.astype(int).to_numpy()])
    if not len(m):
        return np.zeros(len(P))
    h = pesos_reloj_T(m, F) * m.n.to_numpy(float)
    g = pd.Series(h).groupby([m.celda1.astype(str).to_numpy(), m.anio.astype(int).to_numpy(), m.mes.astype(int).to_numpy()]).sum()
    return g.reindex(idx).fillna(0.0).to_numpy(float)


def prueba_P5(FZ, pais: str, Q: pd.DataFrame, U: dict, F: pd.DataFrame, mod: pd.DataFrame, disp: pd.DataFrame,
              ev0: str, ev1: str, m1t: dict, cfg, rng, modo_p5: str) -> dict:
    """P5 (D2-S-07 §4.3): P2, P2b and P3 with the Terra-only predictor H_T instead of H_TA (intervals of clock 'T'),
    same population, same VIIRS base and same block thresholds. Besides the months excluded by the core, months with
    a day without Terra are left out (as in J1). References: M1 with Terra (global ratio S/T) and M0 = raw Terra.
    Own generator: it does not alter the core sequence. Its verdict (if P5 = run) is SEPARATE and the era stays
    "indicative (Terra only)" even if it passes (ADR-0005 7f)."""
    _, sin_terra = meses_incompletos(disp, ev0, ev1)
    QT = Q.copy()
    QT["H_TA"] = h_terra(mod, F, QT, ev0, ev1)     # the H_TA column carries H_T: prueba_P2 / prueba_P3_P4 are reused
    QT["excluido"] = QT.excluido.to_numpy().astype(bool) | np.array([(y, m) in sin_terra for y, m in zip(QT.anio, QT.mes)])
    QT["M1"] = m1t["razon"] * QT["T"]
    QT["M0"] = QT["T"].astype(float)
    B = agregar_bloques(QT, ["T", "A", "H_TA", "S", "W", "SN", "N20", "M1", "M1A", "M0"])
    B = B.merge(QT.groupby(["bloque", "anio", "mes"], as_index=False).agg(excluido=("excluido", "max"),
                testigo_ok=("testigo_ok", "max"), ambos_vi=("ambos_vi", "max"), bloque6=("bloque6", "first")),
                on=["bloque", "anio", "mes"])
    out = {"modo": modo_p5, "predictor": "H_T (clock T, Terra only; Terra detections weighted with the T factors)",
           "intervalos_reloj": "T", "etiqueta_era": "indicative (Terra only)",
           "meses_excluidos_sin_terra": sorted(f"{y}-{m:02d}" for y, m in sin_terra),
           "M1_Terra": {"razon": r(m1t["razon"]), "ic95": r(m1t["ic95"])}}
    p2 = prueba_P2(FZ, pais, B, U, cfg, rng, tramo="T")
    p2.pop("_mascaras")
    out["P2_P2b"] = p2
    p34 = prueba_P3_P4(FZ, pais, QT, cfg, rng, tramo="T")
    out["P3"] = p34["P3"]
    out["P4_vs_M1_Terra_reporte"] = p34["P4"]        # P4 is not part of P5; reported only
    out["n_celda_meses_P3"] = p34["n_celda_meses"]
    return out


def bool_P2(p2: dict, U: dict):
    kc = (p2.get("kappa_cruzado") or {}).get("punto")
    coc = (p2.get("cociente_pareado") or {}).get("punto")
    return None if kc is None or coc is None else bool(kc >= U["P2"]["kappa_min"] and coc >= U["P2"]["cociente_gemelos_min"])


def bool_P2b(b: dict, U: dict):
    if not b:
        return None
    return bool((b.get("precision_unusual") or 0) >= U["P2b"]["precision_unusual_min"]
                and (b.get("precision_typical") or 0) >= U["P2b"]["precision_typical_min"]
                and U["P2b"]["cobertura_ic80_bloque"][0] <= (b.get("cobertura_ic80_bloque") or -1) <= U["P2b"]["cobertura_ic80_bloque"][1]
                and (b.get("pct_indeterminado") if b.get("pct_indeterminado") is not None else 9) <= U["P2b"]["indeterminado_max"])


def cobertura_P3(p3: dict, cfg):
    """P3 coverage that decides, according to `p3.poblacion` (incluye_s0 -> `cobertura`, the previous behaviour)."""
    if not p3:
        return None
    return p3.get("cobertura") if p3_poblacion(cfg) == "incluye_s0" else p3.get("cobertura_excluye_Shat_cero")


def bool_P3(p3: dict, U: dict, cfg):
    cov = cobertura_P3(p3, cfg)
    return None if cov is None else bool(U["P3"]["cobertura"][0] <= cov <= U["P3"]["cobertura"][1])


def veredicto_P5(p5: dict, U: dict, cfg) -> dict:
    """SEPARATE verdict of P5. Threshold: `umbrales.P5.criterio`. ADR-0005 does not set the P5 threshold (7c is still
    pending; D2-S-07 §4.3 recommends "same thresholds"), so by default it is null -> 'pending_threshold'. With
    `mismos_que_P2_P2b_P3`, P5 passes if P2, P2b and P3 (with H_T) pass with the thresholds of P2, P2b and P3."""
    crit = (U.get("P5") or {}).get("criterio")
    if crit not in P5_CRITERIOS:
        raise SystemExit(f"REFUSED: umbrales.P5.criterio = {crit!r}; valid values: {list(P5_CRITERIOS)}")
    base = {"etiqueta_era": "indicative (Terra only)", "criterio": crit}
    if crit is None:
        return {**base, "estado": "pending_threshold", "P5": None}
    p2 = p5.get("P2_P2b") or {}
    b2, b2b, b3 = bool_P2(p2, U), bool_P2b(p2.get("P2b") or {}, U), bool_P3(p5.get("P3") or {}, U, cfg)
    return {**base, "estado": "computed", "P2_bloque3": b2, "P2b": b2b, "P3": b3,
            "P5": None if None in (b2, b2b, b3) else bool(b2 and b2b and b3)}


# ============================================================================ run
def correr(cfg, modo: str, exp: str, args) -> Path:
    t0 = time.time()
    mc = cfg["modos"][modo]
    rng = np.random.default_rng(cfg["semilla"])
    rng_s8 = np.random.default_rng([cfg["semilla"], 8])     # own generators: they do not touch the core sequence
    rng_i05 = np.random.default_rng([cfg["semilla"], 5])
    rng_p5 = np.random.default_rng([cfg["semilla"], 50])     # P5: own generator (does not touch the core)
    i05_expl = bool(getattr(args, "i05_exploratorio", False)) and modo == "desarrollo"
    if getattr(args, "i05_exploratorio", False) and modo != "desarrollo":
        raise SystemExit("REFUSED: --i05-exploratorio only in development mode")
    p5_expl = bool(getattr(args, "p5_exploratorio", False)) and modo == "desarrollo"
    if getattr(args, "p5_exploratorio", False) and modo != "desarrollo":
        raise SystemExit("REFUSED: --p5-exploratorio only in development mode")
    p5_run = cfg["pruebas"].get("P5") == "run"
    p3_poblacion(cfg)                                        # validates p3.poblacion before reading data
    if p5_run or p5_expl:
        veredicto_P5({}, cfg["umbrales"], cfg)               # validates umbrales.P5.criterio before reading data
    d_exp = validar_exp(exp, modo, bool(getattr(args, "sobrescribir", False)))   # D-N2 (also when called without main)
    FZ, es_stub = cargar_interfaz(modo)
    guarda = guarda_prueba(cfg, args) if modo == "prueba" else None
    if modo == "prueba":
        # D-N3: "test started" marker BEFORE reading any data (nothing from 2019+ has been read yet)
        guarda["marca_inicio"] = marcar_inicio_prueba(d_exp, guarda, exp)
    assert mc["fecha_maxima"] < FECHA_RESERVA or modo == "prueba", "anti-leak: development never goes beyond 2018"
    cal0, cal1 = mc["calibracion"]
    ev0, ev1 = mc["evaluacion"]
    ba0, ba1 = mc["base"]
    assert cal1 < FECHA_RESERVA and ba1 < FECHA_RESERVA
    global VENTANA_INTERVALOS
    VENTANA_INTERVALOS = (cal0, cal1)
    L = Lector(mc["fecha_maxima"])
    disp = FZ.disponibilidad("global").copy()
    disp["fecha"] = pd.to_datetime(disp["fecha"])
    disp["sin_datos"] = disp["sin_datos"].astype(str).str.lower().eq("true")
    if ev1 > str(disp.fecha.max().date()):
        assert modo == "prueba", "anti-leak"
        disp = pd.concat([disp, disponibilidad_ventana(L, str((disp.fecha.max() + pd.Timedelta(days=1)).date()), ev1,
                                                        cfg.get("avisos_oficiales_modis", []))])
    paises = cfg["paises"]
    datos, Fs, res = {}, {}, {"paises": {}}
    for pais in paises:
        Fs[pais] = FZ.factores(pais, cal0, cal1)
        mod = leer_modis_dia(L, pais, cal0, ev1)
        vi = leer_viirs_mes(L, pais, cal0, ev1)
        datos[pais] = (mod, vi)
    for pais in paises:
        mod, vi = datos[pais]
        F = Fs[pais]
        R_ = {}
        cal = mod[(mod.acq_date_utc >= cal0) & (mod.acq_date_utc <= cal1)]
        vcal = vi[(vi.anio * 100 + vi.mes <= int(cal1[:4]) * 100 + int(cal1[5:7])) & (vi.plataforma == "S-NPP")]
        if cfg.get("excluir_enero_2012", True):
            vcal = vcal[~((vcal.anio == 2012) & (vcal.mes == 1))]
            cal = cal[~((cal.anio == 2012) & (cal.mes == 1))]
        # M1 (global Terra+Aqua ratio) and M1 Aqua, with the bootstrap CI of nucleo.baseline
        sm = vcal.groupby(["anio", "mes"]).n.sum()
        ta = cal.groupby(["anio", "mes"]).n.sum().reindex(sm.index).fillna(0)
        aq = cal[cal.plataforma == "Aqua"].groupby(["anio", "mes"]).n.sum().reindex(sm.index).fillna(0)
        m1 = razon_global(sm.to_numpy(), ta.to_numpy(), cfg["semilla"])
        m1a = razon_global(sm.to_numpy(), aq.to_numpy(), cfg["semilla"])
        evaluables = set(cal.assign(celda1=cal.celda1.astype(str)).groupby("celda1").n.sum()
                         .loc[lambda s: s >= cfg["umbral_celda_evaluable"]].index)
        # E1b: f = sum N20 / sum S-NPP over the Apr-Dec 2018 bridge
        p0, p1 = cfg["puente_e1b"]
        pu = vi[(vi.anio * 100 + vi.mes >= int(p0[:4]) * 100 + int(p0[5:7])) & (vi.anio * 100 + vi.mes <= int(p1[:4]) * 100 + int(p1[5:7]))]
        f_e1b = float(pu[pu.plataforma == "NOAA-20"].n.sum() / pu[pu.plataforma == "S-NPP"].n.sum())
        P = panel_pais(FZ, pais, F, mod, vi, disp, ev0, ev1, mc["objetivo"], mc["testigo"], cfg)
        P["M1"] = m1["razon"] * (P["T"] + P["A"])
        P["M1A"] = m1a["razon"] * P["A"]
        P["M0"] = P["T"] + P["A"]
        P["evaluable"] = P.celda1.isin(evaluables)
        P["testigo_ok"] = P.W.notna() & ((P.anio * 100 + P.mes) >= int(cfg["cambio_gemelo"][:4]) * 100 + int(cfg["cambio_gemelo"][5:7]))
        P["ambos_vi"] = P.testigo_ok
        datos[pais] = (mod, vi, P, m1, f_e1b, evaluables)
        inc_base, _ = meses_incompletos(disp, ba0, ba1)
        meses_cal = [(t.year, t.month) for t in pd.period_range(cal0[:7], cal1[:7], freq="M")
                     if not (cfg.get("excluir_enero_2012", True) and (t.year, t.month) == (2012, 1))]
        inc_cal, _ = meses_incompletos(disp, cal0, cal1)
        for escala, f in (("E1c", 1.0), ("E1b", f_e1b)):
            if escala == "E1b" and cfg["pruebas"].get("E1b") != "run":
                continue
            Q = P.copy()
            for ccol, plat in (("SN", "S-NPP"), ("N20", "NOAA-20")):
                Q[ccol] = Q[ccol] * (f if plat == "S-NPP" else 1.0)
            col = {"S-NPP": "SN", "NOAA-20": "N20"}
            Q["S"], Q["W"] = Q[col[mc["objetivo"]]], Q[col[mc["testigo"]]]
            for ccol in ("H_TA", "M1", "M1A"):
                Q[ccol] = Q[ccol] * f
            base, meses_base = base_serie(vi, ba0, ba1, cfg["cambio_gemelo"], cfg, f)
            base["bloque"] = bloque_de(base.celda1, 3)
            B = agregar_bloques(Q, ["T", "A", "H_TA", "S", "W", "SN", "N20", "M1", "M1A", "M0"])
            B = B.merge(Q.groupby(["bloque", "anio", "mes"], as_index=False).agg(excluido=("excluido", "max"),
                        testigo_ok=("testigo_ok", "max"), ambos_vi=("ambos_vi", "max"), bloque6=("bloque6", "first")),
                        on=["bloque", "anio", "mes"])
            U = umbrales_unidad(base, sorted(B.bloque.unique()), "bloque", meses_base, inc_base)
            R_[escala] = {}
            if cfg["pruebas"].get("P2") == "run":
                p2 = prueba_P2(FZ, pais, B, U, cfg, rng)
                ok_mask = p2.pop("_mascaras")[0]
                R_[escala]["P2_P2b"] = p2
                if escala == "E1c" and cfg["pruebas"].get("J2") == "run":
                    R_[escala]["J2"] = prueba_J2(B, ok_mask, Q, cfg, rng)
            if escala == "E1c" and cfg["pruebas"].get("S8") == "run":     # ADR-0012 option 2: reported, does not decide
                ok_s8 = ok_mask if cfg["pruebas"].get("P2") == "run" else np.ones(len(B), bool)
                R_[escala]["S8"] = prueba_S8(B, ok_s8, mc, cfg, rng_s8)
            if escala == "E1c" and (cfg["pruebas"].get("clases_I05") == "run" or i05_expl):
                R_[escala]["clases_I05"] = prueba_I05(
                    FZ, pais, Q, B, U, base, meses_base, inc_base, cal, meses_cal, inc_cal, cfg, rng_i05,
                    "run" if cfg["pruebas"].get("clases_I05") == "run" else
                    "exploratory (dev only; clases_I05 is not_run in the config; outside the verdict)")
            if cfg["pruebas"].get("P3") == "run" or cfg["pruebas"].get("P4") == "run":
                R_[escala]["P3_P4"] = prueba_P3_P4(FZ, pais, Q, cfg, rng)
            if escala == "E1c" and (p5_run or p5_expl):         # P5 (Terra-only era): its own block and verdict
                m1t = razon_global(sm.to_numpy(), cal[cal.plataforma == "Terra"].groupby(["anio", "mes"]).n.sum()
                                   .reindex(sm.index).fillna(0).to_numpy(), cfg["semilla"])
                R_["P5"] = prueba_P5(FZ, pais, Q, U, F, mod, disp, ev0, ev1, m1t, cfg, rng_p5,
                                     "run" if p5_run else
                                     "exploratory (dev only; P5 is not_run in the config; outside the verdict)")
            if cfg["pruebas"].get("P1") == "run":
                R_[escala]["P1_chequeo"] = prueba_P1(B, cfg, rng)
            excl = cfg.get("sensibilidad_excluir_anio", {}).get(pais)
            if escala == "E1c" and excl and excl in set(Q.anio):
                Qs, Bs = Q[Q.anio != excl], B[B.anio != excl]
                p2s = prueba_P2(FZ, pais, Bs, U, cfg, rng)
                p2s.pop("_mascaras")
                R_[escala][f"sensibilidad_sin_{excl}"] = {"P2_P2b": {k: p2s.get(k) for k in ("kappa_cruzado", "kappa_gemelos", "cociente_pareado", "n_bloque_meses")},
                                                         "P3_P4": prueba_P3_P4(FZ, pais, Qs, cfg, rng)}
            if escala == "E1c" and modo == "prueba" and mc.get("sub_ventana_w1"):
                w0, w1 = mc["sub_ventana_w1"]
                ym = B.anio * 100 + B.mes
                Bw = B[(ym >= int(w0[:4]) * 100 + int(w0[5:7])) & (ym <= int(w1[:4]) * 100 + int(w1[5:7]))]
                p2w = prueba_P2(FZ, pais, Bw, U, cfg, rng)
                p2w.pop("_mascaras")
                R_[escala]["sub_ventana_W1"] = {k: p2w.get(k) for k in ("kappa_cruzado", "kappa_gemelos", "cociente_pareado", "n_bloque_meses")}
        R_["M1"] = {"razon": r(m1["razon"]), "ic95": r(m1["ic95"]), "razon_aqua": r(m1a["razon"])}
        R_["f_E1b"] = r(f_e1b)
        R_["celdas_evaluables"] = len(evaluables)
        R_["meses_excluidos"] = sorted({f"{y}-{m:02d}" for y, m in zip(P.anio[P.excluido], P.mes[P.excluido])})
        if cfg["pruebas"].get("J1") == "run":
            j0, j1 = cfg["j1"]["ventana"]
            mj = leer_modis_dia(L, pais, j0, j1)
            R_["J1"] = prueba_J1(FZ, pais, F, mj, disp, cfg, rng)
            del mj
        if cfg["pruebas"].get("C_V") == "run":
            R_["C_V"] = prueba_CV(L, pais, cfg)
        res["paises"][pais] = R_
    # ---------------------------------------------------------------- transfer T1 / T2
    if len(paises) == 2 and (cfg["pruebas"].get("T1") == "run" or cfg["pruebas"].get("T2") == "run"):
        res["transferencia"] = {}
        for A, Bp in ((paises[0], paises[1]), (paises[1], paises[0])):
            mod, vi, P, m1, f_e1b, evaluables = datos[Bp]
            PA = panel_pais(FZ, Bp, Fs[A], mod, vi, disp, ev0, ev1, mc["objetivo"], mc["testigo"], cfg)
            Pc = panel_pais(FZ, Bp, Fs[A], mod, vi, disp, cal0, cal1, "S-NPP", "NOAA-20", cfg)
            c_lvl = Pc.S[~Pc.excluido].sum() / Pc.H_TA[~Pc.excluido].sum()
            out = {}
            for nombre, mult in (("T1", 1.0), ("T2", c_lvl)):
                if cfg["pruebas"].get(nombre) != "run":
                    continue
                Q = P.copy()
                Q["H_TA"] = PA["H_TA"].to_numpy() * mult
                ok = ~Q.excluido & np.isfinite(Q.H_TA)
                Bsum = Q.S[ok].sum() / Q.H_TA[ok].sum()
                okc = ok & Q.evaluable
                c = cfg["pseudoconteo_log"]
                G = np.median(ale(Q.S[okc], Q.H_TA[okc], c)) / np.median(ale(P.S[okc], P.H_TA[okc], c))
                # delta kappa at 3 deg block with the base of country B
                base, meses_base = base_serie(vi, ba0, ba1, cfg["cambio_gemelo"], cfg)
                base["bloque"] = bloque_de(base.celda1, 3)
                inc_base, _ = meses_incompletos(disp, ba0, ba1)
                kk = {}
                for et, QQ in (("transfer", Q), ("local", P)):
                    BB = agregar_bloques(QQ, ["H_TA", "S", "W", "M1", "M0"])
                    BB = BB.merge(QQ.groupby(["bloque", "anio", "mes"], as_index=False).agg(
                        excluido=("excluido", "max"), testigo_ok=("testigo_ok", "max"), bloque6=("bloque6", "first")),
                        on=["bloque", "anio", "mes"])
                    U = umbrales_unidad(base, sorted(BB.bloque.unique()), "bloque", meses_base, inc_base)
                    _, u_S = marcar(BB.S, BB.S, BB.S, U, BB.bloque, BB.mes)
                    _, u_H = marcar(BB.H_TA, BB.H_TA, BB.H_TA, U, BB.bloque, BB.mes)
                    okb = np.array([x is not None for x in u_S]) & ~BB.excluido.to_numpy() & np.isfinite(BB.H_TA.to_numpy())
                    kk[et] = kappa_conf(onehot_conf(u_S[okb], u_H[okb]).sum(0).reshape(3, 3))
                out[nombre] = {"B": r(Bsum), "log_B": r(math.log(Bsum)), "G": r(G), "kappa_transfer": r(kk["transfer"]),
                               "kappa_local": r(kk["local"]), "delta_kappa": r(kk["transfer"] - kk["local"]),
                               "nivel_T2": r(mult) if nombre == "T2" else None}
            res["transferencia"][f"{A}->{Bp}"] = out
    # ---------------------------------------------------------------- verdict
    res["veredicto"] = veredicto(res, cfg, modo)
    res["modo"] = modo
    res["stub_factores"] = es_stub
    res["no_ejecutadas"] = sorted(k for k, v in cfg["pruebas"].items() if v != "run")
    expl = []
    if i05_expl and cfg["pruebas"].get("clases_I05") != "run":
        expl.append("clases_I05 (--i05-exploratorio): computed for information only; not part of the verdict")
    if p5_expl and not p5_run:
        expl.append("P5 (--p5-exploratorio): computed for information only; not part of the verdict")
    if expl:
        res["exploratorio_dev"] = expl
    if cfg["pruebas"].get("S8") == "run":
        res["solo_reporte"] = ["S8 (s8.decide = false): reported, never part of the verdict"]
    res["umbrales_pendientes_lote3"] = pendientes(cfg)
    # ---------------------------------------------------------------- output
    d = d_exp
    d.mkdir(parents=True, exist_ok=True)
    etiqueta = ("DEV RUN — calibration 2012-02→2015-12, evaluation 2016–2018 (already inspected in pilots); NOT the pre-registered test"
                if modo == "desarrollo" else "PRE-REGISTERED SINGLE TEST (W2 2019-01→2021-12)")
    if es_stub:
        etiqueta += " · STUB FACTORS (not the method)"
    res["etiqueta"] = etiqueta
    (d / "metricas.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (d / ("verdict.json" if modo == "prueba" else "verdict_dev.json")).write_text(
        json.dumps({"modo": modo, "etiqueta": etiqueta, "veredicto": res["veredicto"], "marca_si": MARCA_SI}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (d / "informe.md").write_text(informe(res, cfg, modo, exp), encoding="utf-8")
    entradas = {str(p.relative_to(RAIZ)): sha256(p) for p in [CONFIG, *(PROC / f"deteccion_{q}.parquet" for q in paises),
                                                            PROC / "disponibilidad_plataforma_dia.csv"] if p.exists()}
    h, det = hash_arbol_nucleo()
    tablas = tablas_congeladas()
    sucio, _ = git_dirty([RAIZ / x for x in (*entradas, *det, *tablas)])
    man = {"id": str(d.relative_to(RAIZ / "runs")), "comando": " ".join([".venv/bin/python", *sys.argv]),
           "commit": git("rev-parse", "--short", "HEAD"), "dirty": sucio,
           "semilla": cfg["semilla"], "n_boot": cfg["n_boot"], "fecha_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "modo": modo, "etiqueta": etiqueta, "guarda": guarda, "entradas_sha256": entradas, "arbol_src_nucleo": h,
           "archivos_src_nucleo": det, "tablas_factores": tablas, "stub_factores": es_stub,
           "duckdb": {"memory_limit": "600MB", "threads": 2}, "tiempo_s": round(time.time() - t0, 1),
           "pico_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024), "marca_si": MARCA_SI}
    (d / "manifiesto.json").write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return d


def ruta_exp(exp: str) -> Path:
    """Output folder of --exp: ALWAYS inside runs/ (name or path). Validated before anything is written."""
    q = Path(exp)
    if not q.is_absolute() and q.parts[:1] != ("runs",):
        q = Path("runs") / q          # plain name (EXP-005) or sub-path -> relative to runs/
    return resolve_under(q, RAIZ / "runs", "folder --exp")


def validar_exp(exp: str, modo: str, sobrescribir: bool = False) -> Path:
    """Gate H4 D-N2: the --exp folder is validated BEFORE reading data or writing. Outside runs/ -> REFUSED. If it
    already exists: in development it is REFUSED (non-empty folder) unless --sobrescribir; in test mode it is ALWAYS
    REFUSED (even if empty) and --sobrescribir is never accepted."""
    d = ruta_exp(exp)
    if modo == "prueba":
        if sobrescribir:
            raise SystemExit("REFUSED: test mode never overwrites (--sobrescribir does not apply)")
        if d.exists():
            raise SystemExit(f"REFUSED: the --exp folder {d.relative_to(RAIZ) if d.is_relative_to(RAIZ) else d} already exists; "
                             "the single test writes into a new EXP and never overwrites")
        return d
    refuse_overwrite([d], sobrescribir, "--exp <new EXP folder>")
    return d


# ============================================================================ rule M1 and labels (lot 3, points 9 and 17)
TOO_FEW = "too_few_modis"          # 'too few MODIS detections' (ADR-0004 M1); never 'reliable'
RELIABLE, INDICATIVE = "reliable", "indicative"


def min_modis_por_mes(U: dict, tramo: str = "TA") -> float | None:
    """M1 threshold for the era (`umbrales.M1.min_modis_por_mes`: one number for both eras, or {TA: n, T: n}).
    None if absent (the rule is then off; pendientes() refuses a frozen config with clases_I05 run and no threshold)."""
    v = ((U or {}).get("M1") or {}).get("min_modis_por_mes")
    if isinstance(v, dict):
        v = v.get(tramo)
    return None if v is None else float(v)


def demasiado_pocos(mediana_modis, minimo) -> bool | None:
    """Rule M1 on one unit: True if its median monthly MODIS count is < the threshold; None if either is unknown."""
    if minimo is None or mediana_modis is None or not np.isfinite(float(mediana_modis)):
        return None
    return bool(float(mediana_modis) < minimo)


def clase_M1(k: int, cortes: list, minimo) -> str | None:
    """Position of count class k ([c_{k-1}, c_k); class 0 starts at 0, the last is open) relative to the M1 threshold:
    'too_few' if the whole class is below it (upper edge <= threshold), 'straddles' if the threshold falls inside the
    class (some of its units are too few: the class cannot be 'reliable'), 'ok' if the whole class is at or above it."""
    if minimo is None:
        return None
    c = [0.0] + [float(x) for x in cortes] + [math.inf]
    lo, hi = c[k], c[k + 1]
    return "too_few" if hi <= minimo else ("straddles" if lo < minimo else "ok")


def etiqueta_estimacion(v_pais: dict | None, tramo: str, mediana_modis, U: dict, cortes: list | None = None,
                        n_celdas: int | None = None, min_celdas_bloque: int = 900) -> dict:
    """Label of an ESTIMATED (MODIS-era) month of a unit/AOI, the reference rule of the core (the exporter and the app
    must say the same). `v_pais` = veredicto()["por_pais"][country] (None before the single test). `mediana_modis` =
    median monthly MODIS count expected in the unit (T+A for tramo 'TA', Terra for 'T'). Precedence:
      1. rule M1: median < umbrales.M1.min_modis_por_mes -> 'too_few_modis' (never 'reliable');
      2. Terra-only era -> 'indicative' ALWAYS, even if P5 passed (ADR-0005 7f; lot 3 point 17);
      3. no verdict -> 'indicative' ('not_tested');
      4. rule 3b of I-05 (ALWAYS in force, ADR-0014 point 9 / #20, PREREG section 4): 'reliable' only if the country
         passed P2 and P2b on the published scale (7g-bis) and the AOI covers >= one 3-degree block (n_celdas of
         0.1 deg >= min_celdas_bloque); unknown n_celdas never yields 'reliable';
      5. I-05 run (v_pais has clases_I05): ADDITIONALLY the unit's count class (pooled group 'juntas') must have
         reliable = True (so it is entirely at/above M1); a class verdict never overrides rule 3b (gate B-G1, option A).
    'reliable' only if no reason is collected; otherwise 'indicative'. An unknown median (None) never yields 'reliable'."""
    motivos: list[str] = []
    minimo = min_modis_por_mes(U, tramo)
    pocos = demasiado_pocos(mediana_modis, minimo)
    if pocos is True:
        return {"etiqueta": TOO_FEW, "motivos": ["too_few_modis"], "min_modis_por_mes": minimo}
    if tramo == "T":
        p5 = (v_pais or {}).get("P5_era_terra_sola") or {}
        return {"etiqueta": INDICATIVE, "motivos": ["terra_only"] + (["P5_passed_still_indicative"] if p5.get("P5") is True else []),
                "min_modis_por_mes": minimo}
    if tramo != "TA":
        raise ValueError(f"unknown tramo: {tramo!r} (expected 'TA' or 'T')")
    if pocos is None:
        motivos.append("expected_modis_count_unknown")
    if not v_pais:
        return {"etiqueta": INDICATIVE, "motivos": motivos + ["not_tested"], "min_modis_por_mes": minimo}
    # rule 3b of I-05: always applied (with or without the count classes) - gate B-G1, option A (ADR-0014 point 9)
    esc = v_pais.get("escala_publicada_7gbis") or "E1c"
    E = v_pais.get(esc) or {}
    if not (E.get("P2_bloque3") is True and E.get("P2b_7cbis_reliable") is True):
        motivos.append("country_test_not_passed")
    if n_celdas is None or n_celdas < min_celdas_bloque:
        motivos.append("aoi_smaller_than_block")
    regla = "I-05 rule 3b"
    i05 = v_pais.get("clases_I05")
    if i05:
        grupo = i05.get("juntas") or next(iter(i05.values()), {})
        if cortes is None or mediana_modis is None:
            motivos.append("count_class_unknown")
        else:
            k = int(clase_de([mediana_modis], cortes)[0])
            nombre = etiquetas_clase(cortes)[k]
            x = grupo.get(nombre) or {}
            if x.get("etiqueta") != RELIABLE or x.get("reliable") is not True:
                motivos.append(f"count_class_{nombre}_not_reliable")
        regla = "I-05 rule 3b + count classes"
    return {"etiqueta": INDICATIVE if motivos else RELIABLE, "motivos": motivos, "regla": regla, "min_modis_por_mes": minimo}


def veredicto(res, cfg, modo) -> dict:
    U = cfg["umbrales"]
    i05_run = cfg["pruebas"].get("clases_I05") == "run"
    out = {"umbrales_fijados": not pendientes(cfg), "por_pais": {},
           "P3_poblacion": p3_poblacion(cfg),          # B-R10 / lot 3 point 7: excluye_s0 decides; both reported per country
           "M1": {"min_modis_por_mes": (U.get("M1") or {}).get("min_modis_por_mes"), "etiqueta": TOO_FEW,
                  "estadistico": "median of the monthly MODIS counts of the unit in the calibration window of the mode "
                                 "(T+A for the Terra+Aqua era, Terra for the Terra-only era); below the threshold -> never reliable"},
           "regla_etiqueta": ("I-05 rule 3b + count classes (reliable only for AOIs >= one 3-degree block of a country "
                              "that passed P2 and P2b on the published scale AND whose count class passed P2 and P2b and "
                              "is not below M1)"
                              if i05_run else "I-05 rule 3b (reliable only for AOIs >= one 3-degree block of a country that "
                                              "passed P2 and P2b; never below M1)"),
           "era_terra_sola": "indicative (Terra only), even if P5 passes"}
    for pais, R in res["paises"].items():
        v = {}
        for escala in ("E1c", "E1b"):
            if escala not in R:
                continue
            E = R[escala]
            p2 = E.get("P2_P2b", {})
            P2 = bool_P2(p2, U)
            P2b = bool_P2b(p2.get("P2b", {}), U)
            p34 = E.get("P3_P4", {})
            P3 = bool_P3(p34.get("P3") or {}, U, cfg)
            sk = (p34.get("P4") or {}).get("skill_ic95")
            P4 = None if not sk or sk[0] is None else bool(sk[0] > U["P4"]["skill_ic95_inferior_mayor_que"])
            v[escala] = {"P2_bloque3": P2, "P2b_7cbis_reliable": P2b, "P3": P3, "P4": P4,
                         "RT05_bloque3": None if None in (P2, P3, P4) else bool(P2 and P3 and P4),
                         "P3_coberturas": resumen_P3(p34.get("P3") or {})}
        j2 = (R.get("E1c", {}).get("J2") or {}).get("bloque", {}).get("media_log")
        v["J2_bloque"] = None if j2 is None else bool(abs(j2) <= U["J2_bloque"]["media_abs_max"])
        j1 = R.get("J1")
        if j1:
            lo, hi = j1["ic95"]
            v["J1"] = bool(abs(j1["media_log"]) <= U["J1"]["media_abs_max"] and lo is not None and -U["J1"]["ic95_dentro_de"] <= lo
                           and hi <= U["J1"]["ic95_dentro_de"] and all(abs(x) <= U["J1"]["anio_abs_max"] for x in j1["por_anio"].values() if x is not None))
        i05 = R.get("E1c", {}).get("clases_I05")
        if i05_run and i05 and i05.get("modo") == "run":
            v["clases_I05"] = {}
            cortes = i05.get("cortes_conteo_modis") or (cfg.get("i05") or {}).get("cortes_conteo_modis", [10, 30, 100])
            minimo = min_modis_por_mes(U, "TA")
            for grupo, por_clase in i05["resultados"].items():
                v["clases_I05"][grupo] = {}
                for k, (cl, x) in enumerate(por_clase.items()):
                    kc = (x.get("kappa_cruzado") or {}).get("punto")
                    coc = (x.get("cociente_pareado") or {}).get("punto")
                    p2c = None if kc is None or coc is None else bool(kc >= U["P2"]["kappa_min"] and coc >= U["P2"]["cociente_gemelos_min"])
                    b = x.get("P2b") or {}
                    p2bc = None if not b else bool(
                        (b.get("precision_unusual") or 0) >= U["P2b"]["precision_unusual_min"]
                        and (b.get("precision_typical") or 0) >= U["P2b"]["precision_typical_min"]
                        and U["P2b"]["cobertura_ic80_bloque"][0] <= (b.get("cobertura_ic80") if b.get("cobertura_ic80") is not None else -1) <= U["P2b"]["cobertura_ic80_bloque"][1]
                        and (b.get("pct_indeterminado") if b.get("pct_indeterminado") is not None else 9) <= U["P2b"]["indeterminado_max"])
                    pos = clase_M1(k, cortes, minimo)
                    rel = None if None in (p2c, p2bc) else bool(p2c and p2bc)
                    if pos in ("too_few", "straddles", None):
                        rel = False if rel is not None or pos == "too_few" else None   # rule M1: never reliable
                    etq = TOO_FEW if pos == "too_few" else (RELIABLE if rel is True else INDICATIVE)
                    v["clases_I05"][grupo][cl] = {"P2": p2c, "P2b": p2bc, "posicion_M1": pos, "reliable": rel, "etiqueta": etq}
        p5 = R.get("P5")
        if cfg["pruebas"].get("P5") == "run" and p5 and p5.get("modo") == "run":
            v["P5_era_terra_sola"] = {**veredicto_P5(p5, U, cfg),          # SEPARATE verdict (ADR-0005 7f)
                                      "P3_coberturas": resumen_P3(p5.get("P3") or {})}
        v["escala_publicada_7gbis"] = "E1c" if v.get("J2_bloque") in (True, None) else "E1b"
        v["etiqueta_terra_sola"] = "indicative (Terra only)" if v.get("J1") in (True, None) else "indicative (Terra only), not continuous with Jul 2002"
        out["por_pais"][pais] = v
    for k, T in (res.get("transferencia") or {}).items():
        out.setdefault("transferencia", {})[k] = {n: bool(abs(t["log_B"]) <= U["T"]["log_sesgo_abs_max"] and t["G"] <= U["T"]["G_max"]
                                                         and t["delta_kappa"] >= U["T"]["delta_kappa_min"]) for n, t in T.items()}
    pend = pendientes(cfg)
    if pend:
        motivo = "pendiente_lote3" if all("(pruebas." not in x for x in pend) else f"pending: {pend}"
        out["aviso"] = f"Thresholds NOT fixed ({motivo}): booleans computed with the recommended D2-S-07 values; not a verdict."
    return out


def signos_s8(s8: dict) -> list[str]:
    """Sign count of the per-block slope (from `por_bloque`, 4 decimals) to read the median over blocks:
    with an even n the median is the mean of the two central values; if both are 0 it is 0 even if few blocks are 0."""
    pb = s8.get("por_bloque") or {}
    if not pb:
        return []
    partes, cero = [], False
    for k in ("objetivo", "H_TA", "M1", "M0"):
        v = np.sort(np.array([b[k] for b in pb.values() if b.get(k) is not None], float))
        if not len(v):
            continue
        n = len(v)
        centro = (f"positions {n // 2} and {n // 2 + 1}: {v[n // 2 - 1]:g} and {v[n // 2]:g}" if n % 2 == 0
                  else f"position {n // 2 + 1}: {v[n // 2]:g}")
        cero |= bool(np.median(v) == 0)
        partes.append(f"{k} {int((v < 0).sum())} < 0 · {int((v == 0).sum())} = 0 · {int((v > 0).sum())} > 0 ({centro})")
    nota = (" A median over blocks = 0 means the central values fall in the few blocks with slope 0 "
            "(negatives and positives almost balanced), not that most blocks or block-months are at 0." if cero else "")
    return ["Signs of the per-block slope (from `por_bloque`, 4 decimals; n = blocks): " + "; ".join(partes) + "." + nota, ""]


def informe(res, cfg, modo, exp) -> str:
    L = [f"# {exp} · RT-05 validation — {res['etiqueta']}", "",
         "SI-generated (AI): report generated by `src/nucleo/validacion_rt05.py` (Claude Code, during the event; reviewed by the team).", "",
         f"- Mode: **{modo}** (desarrollo = development, prueba = single test). Factors: {'**STUB (not the method)**' if res['stub_factores'] else 'src/nucleo/factores.py'}.",
         f"- Thresholds pending from lot 3: {res['umbrales_pendientes_lote3'] or 'none'}.",
         f"- Rule M1: 'too_few_modis' (never reliable) when the median monthly MODIS count < "
         f"{(res['veredicto'].get('M1') or {}).get('min_modis_por_mes')}; label rule: {res['veredicto'].get('regla_etiqueta')}.",
         f"- Tests not run (\"not run\"): {', '.join(res['no_ejecutadas'])}.",
         "- Units: hotspot detections (not fires). UTC dates. Bootstrap by 3° block × year.",
         "- The JSON blocks below keep the Spanish key names of metricas.json (e.g. kappa_cruzado = cross kappa, "
         "kappa_gemelos = twins kappa, cociente_pareado = paired ratio, cobertura = coverage, por_anio = by year).", ""]
    for pais, R in res["paises"].items():
        L += [f"## {pais}", "", f"- M1 (global ratio S/(T+A)): {R['M1']['razon']} {R['M1']['ic95']}; f E1b = {R['f_E1b']}; "
              f"evaluable cells = {R['celdas_evaluables']}; excluded months = {R['meses_excluidos'] or 'none'}", ""]
        for escala in ("E1c", "E1b"):
            if escala not in R:
                continue
            E = R[escala]
            p2 = E.get("P2_P2b", {})
            p34 = E.get("P3_P4", {})
            pob = (p34.get("P3") or {}).get("poblaciones") or {}
            if pob:
                L += [f"P3 ({escala}), both populations (`p3.poblacion` = {(p34.get('P3') or {}).get('poblacion_veredicto')} decides): "
                      f"with Ŝ = 0 {pob['incluye_s0']['cobertura']} {pob['incluye_s0']['ic95']} (n = {pob['incluye_s0']['n']}); "
                      f"without Ŝ = 0 {pob['excluye_s0']['cobertura']} {pob['excluye_s0']['ic95']} (n = {pob['excluye_s0']['n']}); "
                      f"cell-months left out for Ŝ = 0: {pob['incluye_s0']['n'] - pob['excluye_s0']['n']}.", ""]
            L += [f"### {escala}", "", "```json", json.dumps({"P2_P2b": {k: v for k, v in p2.items() if k != "por_anio"},
                                                              "P2_por_anio": p2.get("por_anio"),
                                                              "P3": p34.get("P3"), "P4": p34.get("P4"), "P1_chequeo": E.get("P1_chequeo"),
                                                              "J2": E.get("J2"),
                                                              **{k: v for k, v in E.items() if k.startswith("sensibilidad") or k.startswith("sub_")}},
                                                             indent=1, ensure_ascii=False, default=str), "```", ""]
        L += ["### J1 and C-V", "", "```json", json.dumps({"J1": R.get("J1"), "C_V": R.get("C_V")}, indent=1, ensure_ascii=False), "```", ""]
        s8 = R.get("E1c", {}).get("S8")
        if s8:
            L += ["### S8 · trend (ADR-0012 option 2) — REPORTED, DOES NOT DECIDE", "",
                  f"Seasonal Sen slope of log(x + {s8.get('pseudoconteo')}) per year; VIIRS series = {s8.get('serie_viirs')}.", "",
                  *signos_s8(s8),
                  "```json", json.dumps({k: v for k, v in s8.items() if k != "por_bloque"}, indent=1, ensure_ascii=False), "```", ""]
        p5 = R.get("P5")
        if p5:
            L += [f"### P5 · Terra-only era (H_T) — {p5['modo']}", "",
                  "P2, P2b and P3 with the Terra-only predictor instead of H_TA; the era stays \"indicative (Terra only)\" even if it passes.", "",
                  "```json", json.dumps(p5, indent=1, ensure_ascii=False, default=str), "```", ""]
        i05 = R.get("E1c", {}).get("clases_I05")
        if i05:
            L += [f"### I-05 count classes — {i05['modo']}", "", "```json", json.dumps(i05, indent=1, ensure_ascii=False), "```", ""]
    L += ["## Transfer", "", "```json", json.dumps(res.get("transferencia"), indent=1, ensure_ascii=False), "```", "",
          "## Verdict (booleans with the YAML thresholds)", "", "```json", json.dumps(res["veredicto"], indent=1, ensure_ascii=False), "```", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modo", choices=["desarrollo", "prueba"], default="desarrollo")
    ap.add_argument("--exp", default=None, help="folder runs/EXP-NNN")
    ap.add_argument("--prueba-unica", action="store_true")
    ap.add_argument("--re-corrida-documentada", default=None)
    ap.add_argument("--registrar-hashes", action="store_true")
    ap.add_argument("--paises", default=None, help="subset (comma-separated), development only")
    ap.add_argument("--n-boot", type=int, default=None, help="development only")
    ap.add_argument("--config", default=None, help="alternative YAML, development ONLY (debugging code paths)")
    ap.add_argument("--i05-exploratorio", action="store_true",
                    help="development ONLY: computes P2/P2b by count class (I-05) as exploratory, outside the verdict")
    ap.add_argument("--p5-exploratorio", action="store_true",
                    help="development ONLY: computes P5 (Terra-only era, H_T) as exploratory, outside the verdict")
    ap.add_argument("--sobrescribir", action="store_true",
                    help="development ONLY: allows writing into an --exp folder that already exists (never in test mode)")
    args = ap.parse_args()
    if args.config and (args.modo != "desarrollo" or args.registrar_hashes):
        raise SystemExit("REFUSED: --config only in development mode")
    cfg = yaml.safe_load(Path(args.config or CONFIG).read_text(encoding="utf-8"))
    if args.config:
        assert cfg["modos"]["desarrollo"]["fecha_maxima"] < FECHA_RESERVA, "anti-leak"
        cfg["modos"]["desarrollo"]["fecha_maxima"] = min(cfg["modos"]["desarrollo"]["fecha_maxima"], "2018-12-31")
    if args.registrar_hashes:
        acquire_heavy_lock()
        registrar_hashes(cfg)
        return 0
    if args.modo == "desarrollo":
        if args.paises:
            cfg["paises"] = args.paises.split(",")
        if args.n_boot:
            cfg["n_boot"] = args.n_boot
    elif args.paises or args.n_boot or args.i05_exploratorio or args.p5_exploratorio:
        raise SystemExit("REFUSED: test mode does not change the configuration from the command line")
    exp = args.exp or ("EXP-DEV" if args.modo == "desarrollo" else None)
    if not exp:
        raise SystemExit("test mode: give --exp EXP-NNN")
    validar_exp(exp, args.modo, args.sobrescribir)   # REFUSED before reading data or writing: outside runs/ or already exists
    acquire_heavy_lock()
    d = correr(cfg, args.modo, exp, args)
    print(f"OK -> {d.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
