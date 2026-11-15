#!/usr/bin/env python3
"""EXP-001 (baseline M1, global ratio) and EXP-002 (method "B with clocks", R1, G1, I-03 intervals).

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Everything stays inside the calibration window 2012-02-01 -> 2018-12-31 (ADR-0005: 2019+ held out; asserts).
EXPLORATORY internal check (not the single test of D2-S-07): calibrate 2012-02 -> 2015-12, evaluate 2016-01 -> 2018-12.
Check unit: 0.5 deg cell x year-month (day+night) with zeros; same metrics as the SNDB probe (Q3).

Usage (the script takes the memory lock data/.pesado.lock by itself; it also works under `flock`):
  .venv/bin/python src/nucleo/experimentos.py --help                       # help only; runs nothing
  .venv/bin/python src/nucleo/experimentos.py                              # writes into a NEW directory:
        runs/EXP-001-002-rerun-<UTC>/{EXP-001,EXP-002}/   (never overwrites versioned runs)
  .venv/bin/python src/nucleo/experimentos.py --salida runs/MY-DIR         # explicit base (inside runs/; it must not
        exist or must be empty) -> runs/MY-DIR/EXP-001 and runs/MY-DIR/EXP-002. An existing non-empty base (e.g. a
        versioned runs/EXP-*) is REFUSED unless --sobrescribir is given (gate H4 D-N1).
  .venv/bin/python src/nucleo/experimentos.py --sobrescribir               # regenerates the canonical runs/EXP-001
        and runs/EXP-002 (versioned): only on purpose
Outputs per experiment: EXP-001/{informe.md, metricas.json, manifiesto.json}
         EXP-002/{informe.md, metricas.json, manifiesto.json, serie_pais_chequeo_<pais>.csv, k_reloj_mes_turno_<pais>.csv}
The path is validated BEFORE reading data or writing anything (outside runs/ -> REFUSED, nothing written).
The JSON keys of metricas.json/manifiesto.json and the model/column names that are JSON keys stay in Spanish
(schema of the committed runs); the report text (informe.md) is in English.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
RAIZ = Path(__file__).resolve().parents[2]
import agregados as AG  # noqa: E402
import factores as FA  # noqa: E402
import modelo as MO  # noqa: E402
from baseline import global_count_ratio  # noqa: E402
from provenance import write_manifest as manifiesto  # noqa: E402
from runguard import acquire_heavy_lock, fresh_dir, refuse_overwrite, resolve_under  # noqa: E402

SEMILLA = 42
B = 1000
FIN_CAL_CHK = "2015-12"
NOMBRE = {"mexico": "Mexico", "argentina": "Argentina"}
CMD = ".venv/bin/python src/nucleo/experimentos.py"   # completed with the actual arguments in main()


def commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "desconocido"


def rk(num, den) -> dict:
    x = global_count_ratio(np.asarray(num, float), np.asarray(den, float), n_boot=B, seed=SEMILLA)
    return {"razon": x["ratio"], "ic95": x["ci95"], "n": x["n"]}


def ic(r: dict) -> str:
    return f"{r['razon']:.2f} ({r['ic95'][0]:.2f}–{r['ic95'][1]:.2f})"


def particion(ag: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cal = ag[ag["ym"] <= FIN_CAL_CHK].reset_index(drop=True)
    chk = ag[ag["ym"] > FIN_CAL_CHK].reset_index(drop=True)
    assert cal["ym"].max() < chk["ym"].min(), "temporal split with overlap"
    assert chk["anio"].max() <= 2018 and cal["anio"].max() <= 2015
    return cal, chk


# ================================================================================================ EXP-001
def exp001(paises: dict[str, pd.DataFrame], out: list[str], met: dict) -> None:
    out.append("# EXP-001 · Baseline M1: global ratio per country and era (`nucleo.baseline.global_count_ratio`)\n")
    out.append("EXPLORATORY, inside the calibration window (2012-02-01 → 2018-12-31). ADR-0002/0003 configuration: outside "
               "the static mask, standard processing, all confidence levels, raw detections, UTC date. "
               "Each ratio is computed on the days its clock exists (availability table, global N = 20). "
               "95 % CI: bootstrap over paired 1° cells (B = 1000, seed 42).\n")
    for pais, ag in paises.items():
        res = {}
        out.append(f"\n## {NOMBRE[pais]}\n")
        filas = []
        for r, etiqueta in (("TA", "S/(T+A) · Terra+Aqua era (M1)"), ("T", "S/T · Terra-only era"),
                            ("A", "S/A · pilot reference")):
            v = MO.vista_reloj(ag, r)
            fila = {"ratio": etiqueta}
            # tn is part of the JSON keys (TA_día, TA_noche, ...): kept in Spanish, the report column is translated
            for tn, sub in (("global", v), ("día", v[v.turno == "D"]), ("noche", v[v.turno == "N"])):
                g = sub.groupby("celda1")[["S", "M"]].sum()
                x = rk(g["S"], g["M"])
                fila[{"día": "day", "noche": "night"}.get(tn, tn)] = ic(x)    # report column (English)
                res[f"{r}_{tn}"] = x                                           # JSON key (schema of runs/EXP-001)
            an = v.groupby("anio")[["S", "M"]].sum()
            an = an[an.index >= 2013]   # 2012 is incomplete (from Feb) and is left out of the CV
            rr = an["S"] / an["M"]
            fila["CV across years 2013-18 %"] = f"{rr.std(ddof=1) / rr.mean() * 100:.1f}"
            res[f"{r}_anual"] = rr.round(4).to_dict()
            filas.append(fila)
        out.append(MO.md(pd.DataFrame(filas)) + "\n")
        # internal check
        cal, chk = particion(ag)
        k = {r: MO.vista_reloj(cal, r)[["S", "M"]].sum() for r in MO.RELOJES}
        k = {r: float(x["S"] / x["M"]) for r, x in k.items()}
        modelos = {"M1 S/(T+A)": k["TA"] * (chk["T"] + chk["A"]).values,
                   "M1T S/T": k["T"] * chk["T"].values,
                   "M1A S/A": k["A"] * chk["A"].values}
        cm = MO.malla_chequeo(ag, chk, modelos)
        tm = MO.metricas(cm, list(modelos), SEMILLA, B)
        out.append(f"### Exploratory internal check (calibrates 2012-02 → 2015-12; evaluates 2016-01 → 2018-12; "
                   f"{cm[['i05', 'j05']].drop_duplicates().shape[0]} cells of 0.5°)\n")
        out.append(f"Factors from 2012-02 → 2015-12: S/(T+A) = {k['TA']:.3f} · S/T = {k['T']:.3f} · S/A = {k['A']:.3f}.\n")
        out.append(MO.md(tm) + "\n")
        res["k_chequeo"] = k
        res["chequeo"] = tm.to_dict(orient="records")
        met[pais] = res


# ================================================================================================ EXP-002
def exp002(paises: dict[str, pd.DataFrame], out: list[str], met: dict, series: dict) -> None:
    out.append("# EXP-002 · Method B with clocks (ADR-0003): k(clock, month, overpass) × s(clock, 1° cell, overpass), R1, G1\n")
    out.append("EXPLORATORY, inside the calibration window. k(month, overpass) shrunk towards k(overpass) with n0k = 20; "
               "s shrunk towards 1 with n0s chosen per country by LOYO (loss MAE log1p at 1° × month; tie ±0.5 % → larger n0). "
               "R1: Terra+Aqua days → TA clock, Aqua only → A, Terra only → T. Check models: `M1` = global S/(T+A) "
               "(ΔMAPE reference); `B-R1 (G1)` = main method; `B-R1 G2` = without the cell multiplier "
               "(planned fallback); `B2s sin R1` = TA clock on every day, without R1 (like SNDB); `BT` = Terra-only clock "
               "(proxy of the Dec-2000 → Jun-2002 era).\n")
    for pais, ag in paises.items():
        res = {}
        out.append(f"\n## {NOMBRE[pais]}\n")
        cal, chk = particion(ag)
        # development factors (2012-02 -> 2015-12) from the contract cache + consistency check
        dev = FA.calibrar(pais, *FA.DESARROLLO)
        n0_dev = float(dev["meta"]["n0s"])
        ag_dev = AG.calcular(pais, *FA.DESARROLLO)
        aj = {r: MO.ajustar(MO.vista_reloj(ag_dev, r), r, n0_dev) for r in MO.RELOJES}
        ajG2 = {r: MO.ajustar(MO.vista_reloj(ag_dev, r), r, math.inf) for r in MO.RELOJES}
        Fd = dev["F"]
        chkF = Fd[(Fd.reloj == "TA") & (Fd.mes == 1) & (Fd.turno == "D")].iloc[0]
        assert abs(chkF["w"] - aj["TA"].k([1], ["D"])[0] * aj["TA"].s([chkF["celda1"]], ["D"])[0]) < 1e-9
        # applying pesos_modis (contract) at aggregate level is equivalent to predecir_r1 (same k*s per stratum)
        t_only = chk["t_ok"] & ~chk["a_ok"]
        modelos = {
            "M1 S/(T+A)": float(MO.vista_reloj(cal, "TA")[["S", "M"]].sum().pipe(lambda x: x["S"] / x["M"]))
            * (chk["T"] + chk["A"]).values,
            "B-R1 (G1)": MO.predecir_r1(chk, aj),
            "B-R1 G2": MO.predecir_r1(chk, ajG2),
            "B2s sin R1": MO.predecir(chk.assign(M=(chk["T"] + chk["A"]).astype(float)), aj["TA"]),
            "BT": np.where(chk["t_ok"], MO.predecir(chk.assign(M=chk["T"].astype(float)), aj["T"]), 0.0),
        }
        assert not np.isnan(modelos["B-R1 (G1)"]).any(), "days without MODIS in the check"
        dias_reloj = chk.assign(r=np.select([chk.t_ok & chk.a_ok, t_only, ~chk.t_ok & chk.a_ok], ["TA", "T", "A"], "—"))
        cm = MO.malla_chequeo(ag, chk, modelos)
        tm = MO.metricas(cm, list(modelos), SEMILLA, B)
        out.append(f"n0s chosen by LOYO inside 2012-02 → 2015-12: **{fmt_n0(n0_dev)}**. "
                   f"S-NPP detections of the check on days with clock A (Terra gap): "
                   f"{int(dias_reloj.loc[dias_reloj.r == 'A', 'S'].sum())} of {int(chk['S'].sum())}.\n")
        out.append("### Exploratory internal check (calibrates 2012-02 → 2015-12; evaluates 2016-01 → 2018-12)\n")
        out.append(MO.md(tm) + "\n")
        res["chequeo"] = tm.to_dict(orient="records")
        res["n0s_desarrollo"] = n0_dev
        # interval coverage (LOYO residuals 2012-02 -> 2015-12) in 2016-2018
        cob = []
        tabs = dev["intervalos"]["relojes"]
        for col, r in (("B-R1 (G1)", "TA"), ("BT", "T")):
            for nv in MO.NIVELES:
                c = MO.cobertura(cm, col, tabs[r], nv)
                cob.append({"estimador": col, "tramo": r, **c})
        cob = pd.DataFrame(cob)
        out.append("### Coverage of the I-03 intervals (LOYO residuals from 2012-02 → 2015-12) in 2016-2018\n")
        out.append("Nominal 80 % and 90 %. `S>0` counts units with S-NPP > 0 (like SNDB Q3c); `Ŝ>0`, units with "
                   "prediction > 0. Country: 36 months (binomial 95 % CI ≈ ±13 pp). AOI = 1.5° tiles. "
                   "Column names are the JSON keys (estimador = estimator, tramo = era).\n")
        out.append(MO.md(cob) + "\n")
        res["cobertura"] = cob.to_dict(orient="records")
        # J1 proxy (Jul-2002 step): BT / B2s
        nac = cm.groupby("ym")[["S", "B-R1 (G1)", "BT"]].sum()
        q = (nac["BT"] / nac["B-R1 (G1)"])
        res["J1_proxy"] = {"suma_BT_sobre_B": float(nac["BT"].sum() / nac["B-R1 (G1)"].sum()),
                           "p05": float(q.quantile(.05)), "p95": float(q.quantile(.95))}
        out.append(f"J1 proxy (BT/B at country × month, 2016-2018): Σ = {res['J1_proxy']['suma_BT_sobre_B']:.3f}; "
                   f"p5–p95 month by month = {res['J1_proxy']['p05']:.2f}–{res['J1_proxy']['p95']:.2f}.\n")
        # loss where MODIS saw 0
        perd = {}
        for nv in ("1deg", "aoi"):
            g = MO._agrega_nivel(cm.rename(columns={"B-R1 (G1)": "P"})[["i05", "j05", "celda1", "ym", "S", "P"]], nv)
            perd[nv] = float(g.loc[g["P"] == 0, "S"].sum() / g["S"].sum() * 100)
        g05 = cm[cm["B-R1 (G1)"] == 0]["S"].sum() / cm["S"].sum() * 100
        res["perdida_S_en_unidades_con_pred_0_%"] = {"0.5deg": float(g05), **perd}
        out.append(f"Loss (S-NPP in unit × month cells with Ŝ = 0): 0.5° {g05:.1f} % · 1° {perd['1deg']:.1f} % · "
                   f"AOI 1.5° {perd['aoi']:.1f} %.\n")
        series[pais] = cm.groupby("ym")[["S"] + list(modelos)].sum().reset_index()

        # ------------------------------------------------------------ FINAL calibration
        fin = FA.calibrar(pais, *FA.FINAL)
        mt = fin["meta"]
        res["final"] = {"n0s": mt["n0s"], "k_turno": mt["k_turno"], "S_cal": mt["S_cal"], "M_cal": mt["M_cal"],
                        "curvas_loyo": mt["curvas_loyo"]}
        out.append(f"### Final calibration 2012-02-01 → 2018-12-31 (the one used by the product and by the single test)\n")
        out.append(f"n0s chosen by LOYO (7 years): **{fmt_n0(mt['n0s'])}**; n0k = {mt['n0k']:.0f}.\n")
        cur = pd.DataFrame({r: {fmt_n0(c['n0s'] if c['n0s'] != 'inf' else math.inf): c["perdida_MAE_log1p_1deg"]
                                for c in mt["curvas_loyo"][r]} for r in MO.RELOJES})
        cur.index.name = "n0s"
        out.append("LOYO curve (MAE log1p at 1° × month; the choice uses TA; T and A are informative):\n")
        out.append(MO.md(cur.reset_index()) + "\n")
        kt = pd.DataFrame(mt["k_turno"]).T.reset_index().rename(columns={"index": "clock"})
        out.append("Country k(clock, overpass) (VIIRS-eq per MODIS detection):\n")
        out.append(MO.md(kt) + "\n")
        F = fin["F"]
        km = F.groupby(["reloj", "mes", "turno"])["k"].first().unstack(["reloj", "turno"])
        km.to_csv(RUN2 / f"k_reloj_mes_turno_{pais}.csv")
        sw = F[F.reloj == "TA"].drop_duplicates(["celda1", "turno"])
        sw = sw[sw.n_cal >= 100]
        out.append(f"s(TA, 1° cell, overpass) in cells with ≥ 100 MODIS detections: n = {len(sw)}, "
                   f"p10–p50–p90 = {sw.s.quantile(.1):.2f}–{sw.s.median():.2f}–{sw.s.quantile(.9):.2f}.\n")
        anchos = []
        for r in ("TA", "T"):
            for nv in MO.NIVELES:
                for s_hat in (20, 100, 1000):
                    lo, hi = FA.intervalo(pais, s_hat, r, nv)
                    anchos.append({"tramo": r, "nivel": nv, "Ŝ": s_hat, "lo×": lo, "hi×": hi})
        out.append("Final 80 % interval (multiplicative) for example Ŝ (tramo = era, nivel = level):\n")
        out.append(MO.md(pd.DataFrame(anchos)) + "\n")
        res["intervalos_ejemplo"] = anchos
        met[pais] = res


def fmt_n0(x) -> str:
    return "∞ (G2)" if (isinstance(x, float) and math.isinf(x)) or x == "inf" else f"{float(x):g}"


RUNS = RAIZ / "runs"
RUN1, RUN2 = RUNS / "EXP-001", RUNS / "EXP-002"   # canonical (versioned); main() reassigns them from --salida


ADENDA_BETA = """

## Addendum · beta < 1 signal of ADR-0003 (blocking item of the verifier, Sun 15-Nov ~00:20 Puebla)

**Status: factores_<pais>.parquet and intervalos_<pais>.json NOT FROZEN until the D2 on beta < 1.**

The column "sesgo % por tercil de Ŝ" (bias % by tercile of Ŝ) above uses terciles **specific to each model**, so it
does not compare models with each other. With **common** terciles (MODIS T+A activity at 1° × month ≡ Ŝ_M1) the
pattern is NOT the same in M1 and in B (correcting what the draft said): Mexico M1 +24.9 / +0.3 / +3.1 % (underestimates
the high tercile), G1 n0s=10 +30.0 / +0.5 / −4.2 % (overestimates it), G2 +33.8 / +5.8 / −1.0 %. Argentina M1
+14.5 / −15.7 / −2.9 %, G1 n0s=300 +20.9 / −5.2 / −1.4 %.
Convention: S/Ŝ − 1 (positive = the model underestimates). log-log beta at 1° × month: MX 0.98 (M1) / 0.93 (G1) /
0.95 (G2); AR 0.97 / 0.97 / 0.96. At country × month: G1 1.02 (MX) and 1.00 (AR). Bias of the MX total by n0s (with
R1): 10 → +2.7 %, 20 → +2.5 %, 100 → +1.9 %, 300 → +1.4 %, 1000 → +0.6 %, ∞ → −0.7 %.

Details, the exploratory variant "B + activity term" and interval coverage by tercile:
`runs/EXP-002/diagnostico_beta/diagnostico_beta.md` (`src/nucleo/diag_beta.py`). Options for the D2: `docs/03-nucleo/metodo.md` §8.
"""


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=None,
                    help="base directory inside runs/ (creates <salida>/EXP-001 and <salida>/EXP-002); by default "
                         "a new runs/EXP-001-002-rerun-<UTC>")
    ap.add_argument("--sobrescribir", action="store_true",
                    help="allows writing over existing outputs; without --salida it regenerates the canonical runs/EXP-001 and "
                         "runs/EXP-002 (versioned)")
    return ap.parse_args(argv)


def destinos(args: argparse.Namespace) -> tuple[Path, Path]:
    """EXP-001 and EXP-002 directories, validated BEFORE reading data or writing anything.

    Gate H4 D-N1: with --salida the BASE is validated too. A base that already exists and is not empty (in particular
    any versioned runs/EXP-*, e.g. --salida runs/EXP-005) is REFUSED unless --sobrescribir; before, only
    <base>/EXP-001 and <base>/EXP-002 were checked, which do not exist inside another run and let the write through."""
    if args.salida:
        base = resolve_under(args.salida, RUNS, "output (--salida)")
        refuse_overwrite([base], args.sobrescribir)
    elif args.sobrescribir:
        return RUNS / "EXP-001", RUNS / "EXP-002"
    else:
        base = fresh_dir(RUNS, "EXP-001-002")
    d1, d2 = base / "EXP-001", base / "EXP-002"
    refuse_overwrite([d1, d2], args.sobrescribir)
    return d1, d2


def main(argv: list[str] | None = None) -> int:
    global RUN1, RUN2, CMD
    args = argumentos(argv)
    RUN1, RUN2 = destinos(args)
    modo = acquire_heavy_lock()
    CMD = " ".join([".venv/bin/python", "src/nucleo/experimentos.py", *(sys.argv[1:] if argv is None else argv)])
    print(f"[experimentos] lock: {modo}; output: {RUN1.relative_to(RAIZ)} and {RUN2.relative_to(RAIZ)}", flush=True)
    t0 = time.time()
    RUN1.mkdir(parents=True, exist_ok=True)
    RUN2.mkdir(parents=True, exist_ok=True)
    paises = {p: AG.calcular(p, *FA.FINAL) for p in AG.PAISES}
    for p, ag in paises.items():
        assert pd.Timestamp(ag["dmax"].max()) < pd.Timestamp("2019-01-01"), f"LEAK {p}"
    datos = [AG.ruta_deteccion(p) for p in AG.PAISES] + [AG.DISP]
    extra = {"commit": commit(), "marca_si": FA.MARCA_SI, "candado_memoria": modo,
             "anti_fuga": "only 2012-02-01 → 2018-12-31; asserts in agregados.py, factores.py and here",
             "exploratorio": True}
    out1, met1 = [], {}
    exp001(paises, out1, met1)
    (RUN1 / "informe.md").write_text("\n".join(out1), encoding="utf-8")
    (RUN1 / "metricas.json").write_text(json.dumps(met1, indent=2, ensure_ascii=False, default=str))
    manifiesto(RUN1, SEMILLA, datos, {"ventana": FA.FINAL, "chequeo": ["2012-02", "2015-12", "2016-01", "2018-12"],
                                     "B": B}, CMD, extra)
    out2, met2, series = [], {}, {}
    exp002(paises, out2, met2, series)
    for p, s in series.items():
        s.to_csv(RUN2 / f"serie_pais_chequeo_{p}.csv", index=False)
    (RUN2 / "informe.md").write_text("\n".join(out2) + ADENDA_BETA, encoding="utf-8")
    (RUN2 / "metricas.json").write_text(json.dumps(met2, indent=2, ensure_ascii=False, default=str))
    salidas = sorted(str(x.relative_to(RAIZ)) for x in (RAIZ / "data/processed").glob("factores_*")) + \
        sorted(str(x.relative_to(RAIZ)) for x in (RAIZ / "data/processed").glob("intervalos_*"))
    manifiesto(RUN2, SEMILLA, datos, {"ventana_final": FA.FINAL, "ventana_desarrollo": FA.DESARROLLO,
                                     "n0k": MO.N0K, "n0s_grid": [str(x) for x in MO.N0S_GRID], "tol_n0": MO.TOL_N0,
                                     "aoi_tesela_grados": MO.AOI_CELDAS05 * 0.5, "B": B},
               CMD, {**extra, "salidas": salidas})
    print(f"done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
