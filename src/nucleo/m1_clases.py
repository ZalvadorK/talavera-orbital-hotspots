#!/usr/bin/env python3
"""Exploratory table for the M1 decision (ADR-0004, lot 3 point 9): leave-one-year-out residuals by MODIS count class.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

DEVELOPMENT ONLY (calibration window 2012-02-01 -> 2018-12-31; asserts: nothing >= 2019 is read). EXPLORATORY: it
informs the decision, it does not take it (no threshold is chosen here) and it is not a claim.

For each country and MODIS clock (TA = Terra+Aqua, the Jul-2002 -> 2011 era; T = Terra only, the Dec-2000 -> Jun-2002
era):
  1. LOYO predictions of the method (nucleo.modelo.loyo_predicciones with the final n0s of the country): each year
     2012..2018 is predicted with the factors fitted on the other years.
  2. Units: 1-degree cells and 3-degree blocks (and both pooled, as route I-05 proposes), by month.
  3. Expected MODIS count of a unit = median of its monthly MODIS counts of the clock (zeros included) over the
     TRAINING years only (the held-out year is excluded, so the class carries no information of the predicted year).
  4. Residual r = log1p(S) - log1p(S_hat) for unit-months with S_hat > 0 (same definition as intervalos_<pais>.json);
     S = S-NPP detections. Unit-months with S_hat = 0 are reported as "loss" (share of S-NPP they contain).
  5. Per class: n, median bias, q10/q90, IC80 width factor exp(q90 - q10), median |r|.
Classes: the I-05 proposal (<10, 10-30, 30-100, >=100) and a finer grid to see where the width changes.

Usage (the script takes the shared memory lock data/.pesado.lock itself; it also works under `flock`):
  .venv/bin/python src/nucleo/m1_clases.py --help            # help only; runs nothing
  .venv/bin/python src/nucleo/m1_clases.py                   # writes to a NEW directory
        runs/EXP-005/m1_clases-rerun-<UTC>/{metricas.json, manifiesto.json, m1-clases-dev.md}
  .venv/bin/python src/nucleo/m1_clases.py --salida runs/X [--doc runs/X/m1.md]   # explicit (inside runs/, new or empty)
  .venv/bin/python src/nucleo/m1_clases.py --sobrescribir    # regenerates the versioned canonical outputs
        runs/EXP-005/m1_clases/{metricas.json, manifiesto.json} and docs/03-nucleo/m1-clases-dev.md
Paths are validated BEFORE any data is read or any file is written (outside runs/ or docs/03-nucleo/ -> refused).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregados as AG  # noqa: E402
import factores as FA  # noqa: E402
import modelo as MO  # noqa: E402
from provenance import write_manifest  # noqa: E402
from runguard import acquire_heavy_lock, fresh_dir, refuse_overwrite, resolve_under  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs/EXP-005/m1_clases"
DOC = ROOT / "docs/03-nucleo/m1-clases-dev.md"
SEED = 42                     # no randomness is used; kept for the manifest
CUTS_I05 = [10, 30, 100]
CUTS_FINE = [5, 10, 15, 20, 25, 30, 50, 100]
CLOCKS = {"TA": "Terra+Aqua (Jul 2002 - 2011 era)", "T": "Terra only (Dec 2000 - Jun 2002 era)"}
LEVELS = ("1deg", "3deg")
CMD = ".venv/bin/python src/nucleo/m1_clases.py"   # completed with the real arguments in main()
SI = "SI-generated (AI): Claude Code wrote the script that produced this file during the event; reviewed by the team."


def labels(cuts: list) -> list[str]:
    return [f"<{cuts[0]}"] + [f"{a}-{b}" for a, b in zip(cuts[:-1], cuts[1:])] + [f">={cuts[-1]}"]


def unit_of(celda1: pd.Series, level: str) -> pd.Series:
    if level == "1deg":
        return celda1.astype(str)
    ab = celda1.astype(str).str.split("_", expand=True).astype(int)
    return "b" + (ab[0] // 3).astype(str) + "_" + (ab[1] // 3).astype(str)


def residual_table(pred: pd.DataFrame, level: str, months: list[str]) -> pd.DataFrame:
    """Unit-month rows of the held-out years with S, P, the residual and the LOYO expected MODIS count."""
    d = pred.assign(u=unit_of(pred["celda1"], level).to_numpy())
    um = d.groupby(["u", "ym"])[["S", "P", "M"]].sum()
    units = sorted(um.index.get_level_values(0).unique())
    full = um.reindex(pd.MultiIndex.from_product([units, months], names=["u", "ym"]), fill_value=0.0).reset_index()
    full["anio"] = full["ym"].str[:4].astype(int)
    rows = []
    for y in sorted(full["anio"].unique()):
        exp_ = full[full["anio"] != y].groupby("u")["M"].median()          # expected count from TRAINING years only
        te = full[full["anio"] == y].copy()
        te["esperado"] = te["u"].map(exp_).fillna(0.0).to_numpy()
        rows.append(te)
    t = pd.concat(rows, ignore_index=True)
    t["nivel"] = level
    return t


def summarize(t: pd.DataFrame, cuts: list) -> list[dict]:
    lab = labels(cuts)
    cls = np.searchsorted(np.asarray(cuts, float), t["esperado"].to_numpy(float), side="right")
    out = []
    for k, name in enumerate(lab):
        g = t[cls == k]
        pos = g[g["P"] > 0]
        r = np.log1p(pos["S"].to_numpy(float)) - np.log1p(pos["P"].to_numpy(float))
        row = {"clase": name, "unidades": int(g["u"].nunique()), "unidad_meses": int(len(g)), "n_Shat_pos": int(len(r)),
               "S_en_Shat0_%": float(g.loc[g["P"] == 0, "S"].sum() / g["S"].sum() * 100) if g["S"].sum() > 0 else None}
        if len(r):
            q10, q50, q90 = np.quantile(r, [0.10, 0.50, 0.90])
            row.update({"sesgo_mediano": float(q50), "q10": float(q10), "q90": float(q90),
                        "ancho_IC80_x": float(math.exp(q90 - q10)), "MdALE": float(np.median(np.abs(r))),
                        "Shat_mediano": float(np.median(pos["P"]))})
        out.append(row)
    return out


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=None, help="output directory inside runs/ (metricas.json + manifiesto.json); "
                                                   "default: a new runs/EXP-005/m1_clases-rerun-<UTC>")
    ap.add_argument("--doc", default=None, help="markdown table (inside runs/ or docs/03-nucleo/); default: "
                                                "<salida>/m1-clases-dev.md")
    ap.add_argument("--sobrescribir", action="store_true",
                    help="allow writing over existing outputs; without --salida/--doc regenerates the versioned "
                         "canonical runs/EXP-005/m1_clases and docs/03-nucleo/m1-clases-dev.md")
    return ap.parse_args(argv)


def targets(args: argparse.Namespace) -> tuple[Path, Path]:
    """(output directory, markdown path), validated BEFORE any data is read or written."""
    runs = ROOT / "runs"
    if args.salida:
        out = resolve_under(args.salida, runs, "output (--salida)")
    elif args.sobrescribir:
        out = OUT
    else:
        out = fresh_dir(OUT.parent, OUT.name)
    if args.doc:
        try:
            doc = resolve_under(args.doc, runs, "path --doc")
        except SystemExit:
            doc = resolve_under(args.doc, DOC.parent, "path --doc (runs/ or docs/03-nucleo/)")
    elif args.sobrescribir and not args.salida:
        doc = DOC
    else:
        doc = out / DOC.name
    refuse_overwrite([out / "metricas.json", out / "manifiesto.json", doc], args.sobrescribir)
    return out, doc


def main(argv: list[str] | None = None) -> int:
    args = arguments(argv)
    out_dir, doc = targets(args)
    lock_mode = acquire_heavy_lock()
    cmd = " ".join([CMD, *(sys.argv[1:] if argv is None else argv)])
    print(f"[m1_clases] lock: {lock_mode}; output: {out_dir.relative_to(ROOT)} + {doc.relative_to(ROOT)}", flush=True)
    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    months = [str(p) for p in pd.period_range(FA.FINAL[0][:7], FA.FINAL[1][:7], freq="M")]
    res: dict = {"etiqueta": "EXPLORATORY · development window 2012-02..2018-12 · LOYO · not a claim · does not set M1",
                 "ventana": list(FA.FINAL), "cortes_I05": CUTS_I05, "cortes_finos": CUTS_FINE, "paises": {}, "marca_si": SI}
    inputs = []
    for pais in AG.PAISES:
        ag = AG.calcular(pais, *FA.FINAL)
        assert pd.Timestamp(ag["dmax"].max()) < pd.Timestamp("2019-01-01"), "LEAK: data >= 2019 in the M1 table"
        n0s = float(FA.calibrar(pais, *FA.FINAL)["meta"]["n0s"])
        inputs += [AG.ruta_cache(pais, *FA.FINAL), FA.ruta_factores(pais, *FA.FINAL).with_suffix(".json")]
        res["paises"][pais] = {"n0s": n0s, "relojes": {}}
        for clock in CLOCKS:
            v = MO.vista_reloj(ag, clock)
            pred = MO.loyo_predicciones(v, clock, [n0s])[n0s]
            tabs = {lv: residual_table(pred, lv, months) for lv in LEVELS}
            tabs["juntas"] = pd.concat([tabs["1deg"], tabs["3deg"]], ignore_index=True)
            res["paises"][pais]["relojes"][clock] = {
                lv: {"I05": summarize(t, CUTS_I05), "finas": summarize(t, CUTS_FINE)} for lv, t in tabs.items()}
    (out_dir / "metricas.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_manifest(out_dir, SEED, [*inputs, AG.DISP], {"ventana": FA.FINAL, "cortes_I05": CUTS_I05, "cortes_finos": CUTS_FINE,
                                                       "relojes": list(CLOCKS), "niveles": [*LEVELS, "juntas"]},
                   cmd, {"marca_si": SI, "exploratorio": True, "candado_memoria": lock_mode,
                         "anti_fuga": "only 2012-02-01..2018-12-31 (assert on the aggregates' max date)",
                         "segundos": round(time.time() - t0, 1)})
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(render(res, out_dir, cmd), encoding="utf-8")
    print(f"OK -> {out_dir.relative_to(ROOT)} and {doc.relative_to(ROOT)} ({time.time() - t0:.0f} s)")
    return 0


def _f(x, nd=2):
    if x is None:
        return "—"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def _md(rows: list[dict]) -> str:
    cols = ["clase", "unidades", "n_Shat_pos", "sesgo_mediano", "q10", "q90", "ancho_IC80_x", "MdALE", "S_en_Shat0_%"]
    head = ["class (expected MODIS count/month)", "units", "n (Ŝ>0)", "median bias", "q10", "q90",
            "IC80 width (×)", "MdALE", "% S-NPP with Ŝ=0"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        lines.append("| " + " | ".join(_f(r.get(c), 1 if c == "S_en_Shat0_%" else 2) for c in cols) + " |")
    return "\n".join(lines)


def render(res: dict, out_dir: Path = OUT, cmd: str = CMD + " --sobrescribir") -> str:
    L = ["# M1 · LOYO residuals by MODIS count class (development, exploratory)", "",
         "> SI-generated (AI): generated by `src/nucleo/m1_clases.py` (Claude Code, during the event; reviewed by the team).",
         "> **Exploratory, development window 2012-02 → 2018-12 (nothing ≥ 2019). Not a claim and it does NOT set M1:** "
         "it informs the decision of lot 3, point 9 (M1 + I-05), which is the team's.", "",
         "## What it is", "",
         "- **Leave-one-year-out** (LOYO) prediction of method B with clocks, with the final n0s of each country; "
         "S = S-NPP, Ŝ = prediction of the clock.",
         "- Clock **TA** (Terra+Aqua) = Jul-2002 → 2011 era; clock **T** (Terra only) = Dec-2000 → Jun-2002 era "
         "(in 2012–2018 it is simulated with the Terra detections only).",
         "- **Expected MODIS count** of a unit = median of its monthly counts of the clock (zeros included) over the "
         "training years (without the predicted year). I-05 classes: < 10, 10–30, 30–100, ≥ 100; plus a finer grid.",
         "- Residual r = log1p(S) − log1p(Ŝ) on unit-months with Ŝ > 0 (same definition as `intervalos_<pais>.json`). "
         "**IC80 width (×)** = exp(q90 − q10): multiplicative factor between the ends of the empirical 80 % interval "
         "on the log1p scale (1.0 = no uncertainty). **% S-NPP with Ŝ = 0** = share of the S-NPP detections that fall in "
         "unit-months where the method cannot estimate (MODIS saw 0).",
         "- Units: 1° cell, 3° block, and both pooled (route I-05 §2). An AOI of the app is a set of 0.1° cells; "
         "this table measures whether the uncertainty depends on the **count** rather than on the **size** (the premise of M1).", "",
         f"Command: `{cmd}` · numeric output: `{out_dir.relative_to(ROOT)}/metricas.json` (+ manifest).", ""]
    for pais, P in res["paises"].items():
        L += [f"## {pais} (n0s = {P['n0s']:g})", ""]
        for clock, C in P["relojes"].items():
            L += [f"### Clock {clock} · {CLOCKS[clock]}", ""]
            for lv, nombre in (("juntas", "1° cells + 3° blocks pooled"), ("1deg", "1° cell"), ("3deg", "3° block")):
                L += [f"**{nombre} — I-05 classes**", "", _md(C[lv]["I05"]), ""]
            L += ["**1° cells + 3° blocks pooled — fine grid**", "", _md(C["juntas"]["finas"]), ""]
    L += ["## Computed summary (IC80 width ×, cells + blocks pooled, I-05 classes)", "",
          "| country | clock | " + " | ".join(labels(CUTS_I05)) + " | 10–30: 1° cell vs 3° block |", "|" + "---|" * 7]
    for pais, P in res["paises"].items():
        for clock, C in P["relojes"].items():
            w = [_f(x.get("ancho_IC80_x"), 1) + f" (u={x['unidades']})" for x in C["juntas"]["I05"]]
            c1 = next(x for x in C["1deg"]["I05"] if x["clase"] == "10-30").get("ancho_IC80_x")
            c3 = next(x for x in C["3deg"]["I05"] if x["clase"] == "10-30").get("ancho_IC80_x")
            L.append(f"| {pais} | {clock} | " + " | ".join(w) + f" | {_f(c1, 1)} vs {_f(c3, 1)} |")
    L += ["", "u = units (cells or blocks) in the class. Classes with few units (u < 10) are unstable.", ""]
    L += ["## Reading (facts, no threshold chosen)", "",
          "- The pending decision is: (a) M1 by count class (with these tables) or (b) M2 by size, declared "
          "(ADR-0004, reconsider signal). The pilots bounded the cut between 11 and 26.5 MODIS detections/month.",
          "- Choosing needs an acceptable-width criterion (e.g. a maximum IC80 width) that is **not** set here.",
          "- Compare the same count range in the 1° cell and in the 3° block: if the width is similar, the uncertainty "
          "depends on the count (supports M1); if it differs a lot, it also depends on the size.",
          *monotonia(res),
          "- Development figures: they are not published or cited as a result.", ""]
    return "\n".join(L)


def monotonia(res: dict) -> list[str]:
    """Gate H4 D-N7: states, with the numbers, whether the IC80 width (cells + blocks, I-05 classes) decreases
    MONOTONICALLY with the count or not (it used to read "the width decreases with the count" without nuance).
    Facts only; it does not choose a threshold."""
    mono, no_mono = [], []
    for pais, P in res["paises"].items():
        for clock, C in P["relojes"].items():
            filas = [x for x in C["juntas"]["I05"] if x.get("ancho_IC80_x") is not None]
            sube = [f"{a['clase']} = {a['ancho_IC80_x']:.1f} → {b['clase']} = {b['ancho_IC80_x']:.1f} (u={b['unidades']})"
                    for a, b in zip(filas, filas[1:]) if b["ancho_IC80_x"] > a["ancho_IC80_x"]]
            (no_mono if sube else mono).append(f"{pais} {clock}" + (": " + "; ".join(sube) if sube else ""))
    return ["- **Does the width decrease with the count?** The big jump is between < 10 and 10–30, but the decrease is "
            "**not monotonic** in every row. It rises in " + ("; ".join(no_mono) if no_mono else "none") + ". Monotonic in: "
            + (", ".join(mono) if mono else "none") + ". The high classes have few units (u < 10: unstable), "
            "so the order between 30–100 and ≥ 100 is not resolved with these data."]

if __name__ == "__main__":
    sys.exit(main())
