#!/usr/bin/env python3
"""Diagnostic of the beta < 1 signal of ADR-0003 (input for the pending D2; EXPLORATORY, does not change the method).

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Answers the blocking item of the independent verifier (EXP-002, row "bias by tercile of S_hat"):
  * compares M1, G1 (chosen n0s), G1 with larger n0s (fallback c), G2 (n0s = inf) and an exploratory variant
    "B + activity term" (option b) on the SAME terciles (defined by MODIS T+A activity per 1 deg cell x month,
    which is identical to the terciles of S_hat_M1 and does not depend on the model);
  * log-log slope of S on S_hat at 1 deg x month, 1.5 deg AOI x month and country x month;
  * total bias and MAPE of the country series per variant.
Split: calibrate 2012-02 -> 2015-12, evaluate 2016-01 -> 2018-12 (inside the calibration window; 2019+ is never read).

Activity term (option b, exploratory): a(class) multiplies the TA weight according to the MODIS activity class
(T+A) of the 1 deg cell x year-month x overpass; a(class) = sum S / sum S_hat, with S_hat leave-one-year-out inside
the calibration window. The weight is still per detection (it depends only on MODIS counts; RT-11 is preserved).

The output JSON keys, variant names and tercile labels (bajo/medio/alto) are kept in Spanish: they are the schema of
the committed runs/EXP-002/diagnostico_beta/diagnostico_beta.json.

Usage:   flock data/.pesado.lock .venv/bin/python src/nucleo/diag_beta.py
Outputs: runs/EXP-002/diagnostico_beta/{diagnostico_beta.md, diagnostico_beta.json, manifiesto.json}
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
RAIZ = Path(__file__).resolve().parents[2]
import modelo as MO  # noqa: E402
from experimentos import commit  # noqa: E402
from provenance import write_manifest as manifiesto  # noqa: E402

SEMILLA = 42
FIN_CAL_CHK = "2015-12"
N0_ELEGIDO = {"mexico": 10.0, "argentina": 300.0}      # EXP-002 / factores_<pais>.json
N0_RESPALDO = (20.0, 100.0, 300.0, 1000.0)
BORDES_ACT = (0, 2, 5, 15, 50, 150, math.inf)           # T+A classes per 1 deg cell x year-month x overpass: (0,2], (2,5], ...
CMD = "flock data/.pesado.lock .venv/bin/python src/nucleo/diag_beta.py"
NOMBRE = {"mexico": "Mexico", "argentina": "Argentina"}


def ruta_ag(pais: str) -> Path:
    return RAIZ / "data" / "processed" / f"factores_agregados_{pais}_2012-02-01_2018-12-31.parquet"


def clase_act(df: pd.DataFrame) -> np.ndarray:
    m = df.groupby(["celda1", "ym", "turno"])[["T", "A"]].transform("sum").sum(axis=1).values
    c = np.digitize(m, BORDES_ACT[1:-1], right=True)              # 0 ... 5: (0,2], (2,5], ...
    return np.where(m > 0, c, -1)                                 # T+A = 0 -> -1 (no detections to weight)


def termino_actividad(cal: pd.DataFrame, n0s: float) -> dict[int, float]:
    """a(class) from leave-one-year-out TA predictions inside cal (TA days only)."""
    v = MO.vista_reloj(cal, "TA")
    v["clase"] = clase_act(cal.loc[cal["t_ok"] & cal["a_ok"]].reset_index(drop=True))
    p = MO.loyo_predicciones(v, "TA", [n0s])[n0s]
    g = p[p["clase"] >= 0].groupby("clase")[["S", "P"]].sum()
    return {int(c): float(r.S / r.P) if r.P > 0 else 1.0 for c, r in g.iterrows()}


def pendiente(x: pd.DataFrame, col: str) -> float:
    x = x[(x[col] > 0) & (x["S"] > 0)]
    return float(np.polyfit(np.log(x[col]), np.log(x["S"]), 1)[0])


def main() -> None:
    res, out = {}, []
    out.append("# EXP-002 · Diagnostic of beta < 1 (input for the pending D2; EXPLORATORY)\n")
    out.append("SI-generated (AI). Calibrates 2012-02 → 2015-12, evaluates 2016-01 → 2018-12; 2019+ is not read. "
               "**Common** terciles = terciles of MODIS activity (T+A) per 1° cell × month (≡ terciles of Ŝ_M1), "
               "the same for every variant. `act` = exploratory variant B + activity term (option b), "
               "a(T+A class per 1° cell × month × overpass) estimated with leave-one-year-out Ŝ in 2012-2015. "
               "Column names, variant names and tercile labels (bajo/medio/alto = low/medium/high) are the JSON keys. "
               f"Activity classes: edges {list(BORDES_ACT)}. Command: `{CMD}`.\n")
    for pais in ("mexico", "argentina"):
        ag = pd.read_parquet(ruta_ag(pais))
        assert ag["anio"].max() <= 2018 and ag["ym"].max() < "2019-01", "ANTI-LEAK: row >= 2019"
        cal = ag[ag["ym"] <= FIN_CAL_CHK].reset_index(drop=True)
        chk = ag[ag["ym"] > FIN_CAL_CHK].reset_index(drop=True)
        assert cal["ym"].max() < chk["ym"].min()
        n0 = N0_ELEGIDO[pais]
        vTA = MO.vista_reloj(cal, "TA")
        kM1 = float(vTA.S.sum() / vTA.M.sum())
        mods = {"M1": kM1 * (chk["T"] + chk["A"]).values}
        ajs = {}
        for nn in sorted({n0, *N0_RESPALDO, math.inf}):
            ajs[nn] = {r: MO.ajustar(MO.vista_reloj(cal, r), r, nn) for r in MO.RELOJES}
            nombre = ("G2 (n0s=∞)" if math.isinf(nn) else f"G1 n0s={nn:g}") + (" [elegido]" if nn == n0 else "")
            mods[nombre] = MO.predecir_r1(chk, ajs[nn])
        a = termino_actividad(cal, n0)
        ta = (chk["t_ok"] & chk["a_ok"]).values
        fac = np.where(ta, pd.Series(clase_act(chk)).map(a).fillna(1.0).values, 1.0)
        mods[f"act: G1 n0s={n0:g} × a(clase)"] = mods[next(k for k in mods if k.endswith("[elegido]"))] * fac
        aG2 = termino_actividad(cal, math.inf)
        facG2 = np.where(ta, pd.Series(clase_act(chk)).map(aG2).fillna(1.0).values, 1.0)
        mods["act: G2 × a(clase)"] = mods["G2 (n0s=∞)"] * facG2

        cm = MO.malla_chequeo(ag, chk, mods)
        nombres = list(mods)
        g1 = cm.groupby(["celda1", "ym"])[["S"] + nombres].sum()
        aoi = cm.assign(ti=cm.i05 // MO.AOI_CELDAS05, tj=cm.j05 // MO.AOI_CELDAS05).groupby(["ti", "tj", "ym"])[["S"] + nombres].sum()
        nac = cm.groupby("ym")[["S"] + nombres].sum()
        base = g1[g1["M1"] > 0]
        terc = pd.qcut(base["M1"], 3, labels=["bajo", "medio", "alto"])
        terc_n = pd.qcut(nac["M1"], 3, labels=["bajo", "medio", "alto"])
        filas = []
        for mo in nombres:
            st = base.assign(t=terc).groupby("t", observed=True).apply(lambda d: d.S.sum() / d[mo].sum() - 1,
                                                                       include_groups=False) * 100
            sn = nac.assign(t=terc_n).groupby("t", observed=True).apply(lambda d: d.S.sum() / d[mo].sum() - 1,
                                                                        include_groups=False) * 100
            ape = (np.abs(nac[mo] - nac["S"]) / nac["S"])
            h1 = g1[g1["S"] >= 50]
            filas.append({
                "variante": mo,
                "sesgo total %": float((cm[mo].sum() / cm["S"].sum() - 1) * 100),
                "MAPE serie país": float(ape.mean()),
                "medAPE 1°×mes (S≥50)": float((np.abs(h1[mo] - h1.S) / h1.S).median()),
                "MAE log1p 1°×mes (S>0|Ŝ>0)": float(np.abs(np.log1p(g1.loc[(g1.S > 0) | (g1[mo] > 0), "S"])
                                                           - np.log1p(g1.loc[(g1.S > 0) | (g1[mo] > 0), mo])).mean()),
                "sesgo % tercil común 1°×mes (bajo/medio/alto) [S/Ŝ−1]": " / ".join(f"{x:+.1f}" for x in st.values),
                "sesgo % tercil país×mes (n=12/12/12)": " / ".join(f"{x:+.1f}" for x in sn.values),
                "β log-log 1°×mes": pendiente(g1, mo),
                "β log-log AOI 1.5°×mes": pendiente(aoi, mo),
                "β log-log país×mes": pendiente(nac, mo),
            })
        tab = pd.DataFrame(filas)
        # coverage of the 80 % I-03 interval (LOYO residuals 2012-15, TA clock, chosen G1) by common tercile at 1 deg x month:
        # the S_hat classes of I-03 absorb the conditional bias if coverage is even across terciles.
        ri = RAIZ / "data" / "processed" / f"intervalos_{pais}_2012-02-01_{FIN_CAL_CHK}-31.json"
        tabI = json.loads(ri.read_text())["relojes"]["TA"]
        col = next(k for k in nombres if k.endswith("[elegido]"))
        lo, hi = MO.aplicar_intervalo(tabI["1deg"], base[col].values)
        dentro = pd.Series((base["S"].values >= lo) & (base["S"].values <= hi), index=base.index)
        cob = (dentro.groupby(terc.values, observed=True).mean() * 100).round(1)
        pesoS = base.assign(t=terc).groupby("t", observed=True)["S"].sum()
        pesoS = (pesoS / g1["S"].sum() * 100).round(1)
        res[pais] = {"n0s_elegido": n0, "a_clase_G1": a, "a_clase_G2": aG2,
                     "pct_S_por_tercil_comun": pesoS.to_dict(),
                     "pct_S_en_unidades_sin_MODIS": float(g1.loc[g1.M1 == 0, "S"].sum() / g1.S.sum() * 100),
                     "cobertura80_I03_1deg_por_tercil_comun_G1": cob.to_dict(),
                     "tabla": tab.to_dict(orient="records")}
        out.append(f"\n## {NOMBRE[pais]} (chosen n0s = {n0:g})\n")
        out.append(MO.md(tab) + "\n")
        out.append(f"Share of each common tercile in S-NPP 2016-18 (low/medium/high): "
                   f"{' / '.join(f'{v:.1f} %' for v in pesoS.values)}; S-NPP in 1° cell × month units without MODIS: "
                   f"{res[pais]['pct_S_en_unidades_sin_MODIS']:.1f} %.\n")
        out.append("Coverage of the 80 % I-03 interval (chosen G1, TA clock, 1° × month, units with Ŝ_M1 > 0) by common tercile "
                   f"(low/medium/high): {' / '.join(f'{v:.1f} %' for v in cob.values)}.\n")
        out.append("a(class) of the activity term (chosen G1): "
                   + ", ".join(f"{BORDES_ACT[c]}–{BORDES_ACT[c + 1]}: {v:.2f}" for c, v in sorted(a.items())) + "\n")
        out.append("a(class) of the activity term (G2): "
                   + ", ".join(f"{BORDES_ACT[c]}–{BORDES_ACT[c + 1]}: {v:.2f}" for c, v in sorted(aG2.items())) + "\n")
    dst = RAIZ / "runs" / "EXP-002" / "diagnostico_beta"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "diagnostico_beta.md").write_text("\n".join(out), encoding="utf-8")
    (dst / "diagnostico_beta.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    man = manifiesto(dst, SEMILLA, [ruta_ag(p) for p in ("mexico", "argentina")],
                     {"particion": ["2012-02", "2015-12", "2016-01", "2018-12"], "n0s_elegido": N0_ELEGIDO,
                      "n0s_respaldo": list(N0_RESPALDO), "bordes_actividad": [str(b) for b in BORDES_ACT]},
                     comando=CMD, extra={"commit_corto": commit(), "estado": "exploratory; input for the beta<1 D2"})
    print("manifest", man)
    print("\n".join(out))


if __name__ == "__main__":
    main()
