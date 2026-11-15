#!/usr/bin/env bash
# SI-generated (AI): Claude Code — regenerates all project results (completed during the event; D-N8 rewrite, Sun 15 Nov 2026).
# Clean-clone reproduction (no `make` needed):
#   git clone <repo> repro && cd repro
#   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt     # versions pinned to the ones the results were produced with
#   bash scripts/reproducir.sh --solo-comprobar                             # cheap pre-flight (reads no data, writes nothing)
#   bash scripts/reproducir.sh                                              # OFFLINE by default (see below)
#
# Usage: bash scripts/reproducir.sh [--solo-comprobar] [-h|--help]
#   --solo-comprobar   pre-flight only: interpreter and modules, every script this file calls, frozen availability file,
#                      Natural Earth archive, download registries. It reads no data/processed, hashes no raw data, writes nothing.
#
# Data modes (REPRO_NET):
#   REPRO_NET=0 (default): OFFLINE. Nothing is downloaded, no MAP_KEY. Uses the cached raw FIRMS files in data/raw/firms/ and
#       verifies each one against the SHA-256 recorded at download time (scripts/verificar_cache_firms.py). If the Natural Earth
#       archive is not in data/raw/fronteras/ the script FAILS with a message instead of fetching it.
#   REPRO_NET=1: downloads again with the SAME frozen cut: country summaries 2000-2025 and the 2026 area-API
#       tail up to --hasta 2026-11-14, using the frozen availability file
#       docs/02-datos/firms_data_availability_2026-11-14.csv. Needs FIRMS_MAP_KEY in .env (~25 min of network); it also fetches
#       Natural Earth if missing (public domain, SHA-256 checked). Already-cached chunks are skipped, so this reproduces the same rows.
# Extending the data past 2026-11-14 is NOT a reproduction: run the downloaders by hand and say so.
#
# The experiment step never overwrites an existing run: the development experiments go to a NEW directory runs/repro-<UTC>/
# (the script stops if it already exists). Figures and data/processed are regenerated in place (they are derived files).
# Anti-leak: before runs/*/verdict.json exists, nothing that reads or compares Terra/Aqua/S-NPP >= 2019-01-01 as ratios runs here
# (qa_firms.py, FIG-01, FIG-03 are all gated on the verdict); after it, qa_firms.py regenerates docs/02-datos/qa-firms*.md in place.
# This file is part of the public product tree. The tool that builds that tree (scripts/publicar_producto.sh) lives only in the
# private development repository and is not shipped with it.
set -euo pipefail
cd "$(dirname "$0")/.."

SOLO_COMPROBAR=0
case "${1:-}" in
  "") ;;
  --solo-comprobar) SOLO_COMPROBAR=1 ;;
  -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Unknown argument: $1 (use --solo-comprobar or --help)" >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then echo "Too many arguments (use --solo-comprobar or --help)" >&2; exit 2; fi

PY="${REPRO_PY:-.venv/bin/python}"   # override with REPRO_PY=/path/to/python
REPRO_NET="${REPRO_NET:-0}"
CUT=2026-11-14
NE_ZIP=data/raw/fronteras/ne_10m_admin_0_countries.zip
NE_URL=https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip
NE_SHA=ce1ac7036499a0edd641fbc093cd209a98f96a49d2eca8480aaacad35138a7f6
AVAIL="docs/02-datos/firms_data_availability_${CUT}.csv"

case "$REPRO_NET" in
  0|1) ;;
  *) echo "REPRO_NET must be 0 (offline, default) or 1 (download); got '$REPRO_NET'" >&2; exit 2 ;;
esac

# Everything this file calls (the pre-flight and the run use the same list).
SCRIPTS="scripts/verificar_cache_firms.py src/datos/tabla_intermedia.py src/datos/integrar_api.py src/datos/tabla_analitica.py
src/datos/disponibilidad.py src/datos/qa_2026.py src/datos/qa_firms.py src/nucleo/factores.py src/nucleo/experimentos.py
src/nucleo/validacion_rt05.py src/nucleo/m1_clases.py src/figuras/_comun.py src/figuras/paleta.py src/figuras/fig02_relojes.py src/figuras/fig04_mascara.py
src/figuras/fig01_sensor_swap.py src/figuras/fig03_transferencia.py src/exportar_demo.py config/validacion.yaml"
if [ "$REPRO_NET" = "1" ]; then SCRIPTS="$SCRIPTS src/datos/descargar_firms.py src/datos/descargar_firms_api.py"; fi

# Cheap pre-flight: reads nothing under data/processed or app/data, hashes no raw FIRMS file, never touches the network, writes nothing.
comprobar() {
  local fallos=0 f
  echo "Pre-flight (REPRO_NET=$REPRO_NET, cut $CUT)"
  if [ -x "$PY" ] || command -v "$PY" >/dev/null 2>&1; then
    echo "  ok   interpreter: $("$PY" -c 'import sys; print(sys.version.split()[0])')"
    if "$PY" -c 'import duckdb, pandas, numpy, scipy, shapely, geopandas, yaml, matplotlib, pyarrow' 2>/dev/null; then
      echo "  ok   modules: duckdb pandas numpy scipy shapely geopandas yaml matplotlib pyarrow"
    else
      echo "  FAIL a required module is missing (pip install -r requirements.txt in the environment of $PY)"; fallos=$((fallos+1))
    fi
  else
    echo "  FAIL interpreter not found: $PY (create .venv or set REPRO_PY=/path/to/python)"; fallos=$((fallos+1))
  fi
  local falta=0
  for f in $SCRIPTS; do
    [ -f "$f" ] || { echo "  FAIL missing: $f"; fallos=$((fallos+1)); falta=1; }
  done
  if [ "$falta" -eq 0 ]; then echo "  ok   all $(echo $SCRIPTS | wc -w) scripts and the config called by this file exist"; fi
  # Published single-test run (public tree: the 5 files of runs/EXP-NNN). FIG-01, FIG-03 and the audit read verdict, metricas and manifiesto.
  if compgen -G "runs/*/verdict.json" >/dev/null; then
    local v d
    for v in runs/*/verdict.json; do
      d="$(dirname "$v")"
      if [ -f "$d/metricas.json" ] && [ -f "$d/manifiesto.json" ]; then echo "  ok   published single-test run: $d (verdict.json, metricas.json, manifiesto.json)"
      else echo "  FAIL $d has verdict.json but lacks metricas.json or manifiesto.json (FIG-01, FIG-03 and the audit read all three)"; fallos=$((fallos+1)); fi
    done
  else
    echo "  note no runs/*/verdict.json: the single test is not in this tree; FIG-01, FIG-03 and the verdict audit will be skipped"
  fi
  if [ -f "$AVAIL" ]; then echo "  ok   frozen availability file: $AVAIL"
  else echo "  FAIL missing frozen availability file: $AVAIL"; fallos=$((fallos+1)); fi
  if [ -f "$NE_ZIP" ]; then
    if echo "$NE_SHA  $NE_ZIP" | sha256sum -c - >/dev/null 2>&1; then echo "  ok   Natural Earth archive present, SHA-256 matches"
    else echo "  FAIL Natural Earth archive present but its SHA-256 differs: $NE_ZIP"; fallos=$((fallos+1)); fi
  elif [ "$REPRO_NET" = "1" ]; then
    echo "  note Natural Earth archive absent: REPRO_NET=1 will fetch it (public domain, SHA-256 checked)"
  else
    echo "  FAIL Natural Earth archive absent and REPRO_NET=0 (offline): place $NE_URL at $NE_ZIP (SHA-256 $NE_SHA)"; fallos=$((fallos+1))
  fi
  for f in data/raw/firms/descargas.csv data/raw/firms/descargas_api.csv; do
    if [ -f "$f" ]; then echo "  ok   download registry: $f ($(grep -c '' "$f") lines)"
    elif [ "$REPRO_NET" = "1" ]; then echo "  note download registry absent: REPRO_NET=1 will create it"
    else echo "  FAIL missing download registry: $f (scripts/verificar_cache_firms.py needs it; restore it or run with REPRO_NET=1)"; fallos=$((fallos+1)); fi
  done
  if [ "$REPRO_NET" = "1" ]; then
    if [ -n "${FIRMS_MAP_KEY:-}" ] || [ -f .env ]; then echo "  ok   FIRMS_MAP_KEY source present (environment or .env; contents not read here)"
    else echo "  FAIL REPRO_NET=1 needs FIRMS_MAP_KEY in the environment or in a local .env"; fallos=$((fallos+1)); fi
  fi
  if command -v flock >/dev/null 2>&1; then echo "  ok   flock available: heavy steps run under data/.pesado.lock"
  else echo "  note flock not found: heavy steps run WITHOUT the shared lock (one heavy job at a time; DuckDB uses ~600 MB)"; fi
  if [ "$fallos" -eq 0 ]; then echo "Pre-flight OK: nothing was read from data/processed, nothing was written."; return 0; fi
  echo "Pre-flight FAILED: $fallos problem(s)."; return 1
}

if [ "$SOLO_COMPROBAR" = "1" ]; then
  rc=0; comprobar || rc=$?
  exit "$rc"
fi

LOCK=""
if command -v flock >/dev/null 2>&1; then LOCK="flock data/.pesado.lock"; fi

echo "[1/4] Data (REPRO_NET=$REPRO_NET, cut $CUT)"
# Country borders (Natural Earth 1:10m, public domain) to clip the area API by country. Offline mode never downloads.
mkdir -p data/raw/fronteras logs
if [ ! -f "$NE_ZIP" ]; then
  if [ "$REPRO_NET" = "1" ]; then
    curl -fsSL --retry 3 -o "$NE_ZIP" "$NE_URL"
  else
    echo "ERROR: $NE_ZIP is missing and REPRO_NET=0 (offline): nothing is downloaded." >&2
    echo "       Put the Natural Earth 1:10m admin-0 countries archive there (SHA-256 $NE_SHA)," >&2
    echo "       or rerun with REPRO_NET=1 to fetch it from $NE_URL" >&2
    exit 2
  fi
fi
echo "$NE_SHA  $NE_ZIP" | sha256sum -c -
# Frozen data availability (the downloader reads logs/firms_data_availability.csv)
cp "$AVAIL" logs/firms_data_availability.csv
if [ "$REPRO_NET" = "1" ]; then
  for PAIS in Mexico Argentina; do
    $PY src/datos/descargar_firms.py --pais $PAIS --desde 2000 --hasta 2025            # annual country summaries, no MAP_KEY
  done
  for AREA in mexico argentina; do
    $PY src/datos/descargar_firms_api.py --area $AREA --desde 2026-01-01 --hasta $CUT  # needs FIRMS_MAP_KEY
  done
fi
$PY scripts/verificar_cache_firms.py                                                   # SHA-256 of every cached raw file
for PAIS in Mexico Argentina; do
  $PY src/datos/tabla_intermedia.py --pais $PAIS                                      # -> data/interim/firms/firms_<pais>.parquet
done
for AREA in mexico argentina; do
  $PY src/datos/integrar_api.py --area $AREA                                          # country clip + NRT only after the last standard day
done
# Analytical table (ADR-0002/0003/0004) + platform-day availability + 2026 QA. They read data/interim and write data/processed, so they
# take the shared heavy-job lock (other agents/jobs run in parallel on a ~1.5 GB-free machine; DuckDB uses 600 MB / 2 threads).
for PAIS in mexico argentina; do
  $LOCK $PY src/datos/tabla_analitica.py --pais $PAIS                                 # -> data/processed/deteccion_<pais>.parquet (+ static mask, manifest)
done
$LOCK $PY src/datos/disponibilidad.py                                                  # -> data/processed/disponibilidad_plataforma_dia.csv (Terra/Aqua, 2000-11 .. 2018-12 only)
$LOCK $PY src/datos/qa_2026.py                                                         # -> docs/02-datos/qa-firms-2026.md (descriptive, no ratios)
# qa_firms.py computes S-NPP/Aqua and VIIRS/MODIS ratios (by month, day/night, FRP, 1-degree cell) over 2013-2024, which INCLUDES the window
# reserved for the single validation run (2019-2021, ADR-0005). So it is a post-verdict step, like FIG-01/FIG-03: before runs/*/verdict.json
# exists it is skipped and docs/02-datos/qa-firms*.md are left untouched. After the verdict it reads data/interim (heavy-job lock) and
# regenerates those two derived reports IN PLACE (as the figures are): they are not written to the new runs/repro-<UTC>/ directory.
if compgen -G "runs/*/verdict.json" >/dev/null; then
  for PAIS in Mexico Argentina; do
    $LOCK $PY src/datos/qa_firms.py --pais $PAIS                                       # -> docs/02-datos/qa-firms.md | qa-firms-argentina.md (ratios 2013-2024)
  done
else
  echo "  qa_firms.py (sensor ratios 2013-2024, includes 2019-2021) skipped: no runs/*/verdict.json yet; qa-firms*.md untouched"
fi

echo "[2/4] Core (analysis)"
# Lane A: VIIRS-equivalent factors (k by clock/month/shift/country x s by 1-degree cell/shift) and LOYO intervals, calibrated 2012-02-01..2018-12-31 only.
# Reads data/processed/deteccion_<pais>.parquet -> heavy-job lock (shared machine, DuckDB 600 MB / 2 threads).
$LOCK $PY src/nucleo/factores.py --generar                                              # -> data/processed/factores_<pais>_*.parquet, intervalos_<pais>*.json
# Development experiments (calibration window only; exploratory, NOT the pre-registered test). Each goes to a NEW directory
# runs/repro-<UTC>/, so a committed run (runs/EXP-00N) is never overwritten; compare the new metricas.json with the committed one.
REPRO_RUNS="runs/repro-$(date -u +%Y%m%dT%H%M%SZ)"
if [ -e "$REPRO_RUNS" ]; then echo "ERROR: $REPRO_RUNS already exists; rerun in a second (nothing was overwritten)." >&2; exit 2; fi
$LOCK $PY src/nucleo/experimentos.py --salida "$REPRO_RUNS/EXP-001-002"                # EXP-001 (baseline M1) + EXP-002 (clock method) -> .../EXP-001, .../EXP-002
$LOCK $PY src/nucleo/validacion_rt05.py --modo desarrollo --exp "$REPRO_RUNS/EXP-DEV" --i05-exploratorio  # development run of the validation design
$LOCK $PY src/nucleo/m1_clases.py --salida "$REPRO_RUNS/m1_clases"                       # exploratory table for the M1 decision (writes only inside the new directory)
echo "Development experiments written to $REPRO_RUNS/ (committed runs untouched)"
# The single validation run (ADR-0005, window 2019-2021) is NOT part of this script: it runs once, from the frozen code, and writes
# runs/<EXP>/verdict.json. Until verdict.json exists, nothing of Terra/Aqua/S-NPP >= 2019-01-01 is exported or plotted.
# (src/nucleo/diag_beta.py is not run here: it writes to the committed runs/EXP-002/diagnostico_beta, a fixed path.)

echo "[3/4] Figures"
# FIG-02 and FIG-04 are computed from data/processed with --real (they read it, so: shared lock); the palette needs no data.
$PY src/figuras/paleta.py                                                              # -> figures/paleta.json
$LOCK $PY src/figuras/fig02_relojes.py --real                                          # -> figures/FIG-02_clock_factors.* (+ figdata/, manifest)
$LOCK $PY src/figuras/fig04_mascara.py --real                                          # -> figures/FIG-04_mask_before_after_popocatepetl.* (+ figdata/, manifest)
# FIG-01 and FIG-03 belong to the single validation run: they are drawn from runs/EXP-NNN/{verdict,metricas,manifiesto}.json (published with this
# tree; nothing is recomputed) and exist only with a verdict.json. Same command as their manifests record: `flock ... --real`.
if compgen -G "runs/*/verdict.json" >/dev/null; then
  $LOCK $PY src/figuras/fig01_sensor_swap.py --real                                    # -> figures/FIG-01_sensor_swap_vs_twin_swap.* (+ figdata/, manifest)
  $LOCK $PY src/figuras/fig03_transferencia.py --real                                  # -> figures/FIG-03_transfer_mx_ar.* (+ figdata/, manifest)
else
  echo "  FIG-01 and FIG-03 skipped: no runs/*/verdict.json yet (they exist only after the single validation run)"
fi

echo "[4/4] Demo export + audit"
# Static-site aggregates for the app (ADR-0004/0009): app/data/<pais>/{mensual,diario,puntos,...} + manifest.json. Not versioned (.gitignore: app/data/);
# in the development repository they go to the orphan gh-pages branch through scripts/publicar_producto.sh (private tool, not in this tree).
# Ends with the anti-leak audit (asserts) over the whole of app/data/.
# --pesos real needs step 2 (factores/intervalos). `--pesos synthetic` is for building the app only and NEVER goes to the public repo.
$LOCK $PY src/exportar_demo.py --pesos real --pais ambos
# Audit alone, as anyone with the public tree runs it: anti-leak walk over app/data, the published verdict (manifest.verdict recomputed from
# runs/EXP-NNN/verdict.json + metricas.json) and the frozen code (src/nucleo tree and config/validacion.yaml = config/validacion.hashes.json = the run's manifiesto).
$LOCK $PY src/exportar_demo.py --solo-auditar
echo "Reproduction finished. New experiment outputs: $REPRO_RUNS/ . Compare their metricas.json with the committed runs/EXP-00N and the figures' manifests."
