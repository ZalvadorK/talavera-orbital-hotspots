#!/usr/bin/env python3
"""FIG-02 · "Relojes": factor k (detecciones VIIRS por deteccion MODIS) por reloj x mes x turno x pais.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Mensaje (titulo-afirmacion): una deteccion MODIS vale entre ~3 y ~18 detecciones VIIRS segun el reloj (Terra o Terra+Aqua),
el turno y el mes; por eso no sirve un solo factor por sensor (ADR-0003, RT-06 b/c).
El titulo usa SOLO los relojes que alimentan la serie (T y TA). El reloj A (Aqua sola) es de RESPALDO, con pocas detecciones
de noche (p. ej. MX nov-dic: 71 y 109; k hasta 34.7, IC95 hasta 74): se dibuja aparte (discontinuo, tenue) y se rotula;
no entra en el rango del titulo. Eje y hasta 80 para no recortar ninguna banda.
Los extremos del titulo se CALCULAN de la tabla (no se escriben a mano).

Origen: EXP-002 (src/nucleo/experimentos.py -> factores_<pais>.parquet, calibracion final 2012-02-01..2018-12-31,
n0k = 20, estimador k_r(mes, turno) = (S_mt + n0k*k_r(turno)) / (M_mt + n0k); modelo.py).
  * Estimacion puntual: columna k de data/processed/factores_<pais>.parquet (se verifica contra el CSV de EXP-002
    runs/EXP-002/k_reloj_mes_turno_<pais>.csv y contra la reconstruccion desde los agregados).
  * IC: NO existen en el parquet. Se calculan aqui, EXPLORATORIOS: bootstrap por bloque-ano (se remuestrean los 7 anos de
    calibracion con reemplazo, B = 1000, semilla 42) sobre data/processed/factores_agregados_<pais>_2012-02-01_2018-12-31.parquet
    (conteos por celda x ano x mes x turno), recalculando k con la misma formula. Percentiles 2.5-97.5. Con 7 bloques el IC
    es aproximado (se declara en la figura).
Candado anti-fuga: solo lee la ventana de calibracion (anio <= 2018); assert explicito (ADR-0005).

Uso (lee data/processed/**: SIEMPRE con candado de memoria):
  flock data/.pesado.lock .venv/bin/python src/figuras/fig02_relojes.py --real      # calcula + dibuja + manifiesto
  .venv/bin/python src/figuras/fig02_relojes.py                                      # solo redibuja desde figures/figdata/ (CSV)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as K  # noqa: E402

FIG_ID = "FIG-02"
NOMBRE = "FIG-02_clock_factors"
FIGDATA = K.FIGURAS_DIR / "figdata" / f"{NOMBRE}.csv"
PROC = K.RAIZ / "data" / "processed"
VENTANA = "2012-02-01_2018-12-31"
PAISES = ["mexico", "argentina"]
ROT_PAIS = {"mexico": "Mexico", "argentina": "Argentina"}
RELOJES = ["T", "A", "TA"]                     # Terra solo, Aqua solo, ambos (R1, ADR-0003)
ETQ = {"T": "Terra", "A": "Aqua only", "TA": "Both"}      # "Both" = dias con Terra y Aqua (reloj TA)
COL = {"T": K.C["Terra"], "A": K.C["Aqua"], "TA": "#1A1A1A"}   # TA: sin entrada en paleta.json; negro, distinto por marcador
MK = {"T": "o", "A": "^", "TA": "s"}
TURNOS = [("D", "Day pass"), ("N", "Night pass")]
MESES = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
N0K = 20.0
B = 1000
SEMILLA = 42


def _k_desde_conteos(S: np.ndarray, M: np.ndarray, n0k: float = N0K) -> np.ndarray:
    """S, M: (..., 12, 2[D,N]) -> k (..., 12, 2). k_r(turno) = sum S / sum M; encogimiento de modelo.ajustar()."""
    sm = M.sum(axis=-2, keepdims=True)
    kd = S.sum(axis=-2, keepdims=True) / np.where(sm == 0, np.nan, sm)
    return (S + n0k * kd) / (M + n0k)


def _conteos_por_ano(ag: pd.DataFrame, reloj: str) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Replica modelo.vista_reloj: S y M por (ano, mes, turno) en los dias en que el reloj existe."""
    if reloj == "TA":
        m, M = ag["t_ok"] & ag["a_ok"], ag["T"] + ag["A"]
    elif reloj == "T":
        m, M = ag["t_ok"], ag["T"]
    else:
        m, M = ag["a_ok"], ag["A"]
    v = ag.loc[m, ["anio", "mes", "turno", "S"]].copy()
    v["M"] = M[m].astype(float).values
    anios = sorted(ag["anio"].unique().tolist())
    Sa = np.zeros((len(anios), 12, 2)); Ma = np.zeros_like(Sa)
    g = v.groupby(["anio", "mes", "turno"])[["S", "M"]].sum()
    for (a, mes, t), r in g.iterrows():
        Sa[anios.index(a), mes - 1, 0 if t == "D" else 1] = r["S"]
        Ma[anios.index(a), mes - 1, 0 if t == "D" else 1] = r["M"]
    return Sa, Ma, anios


def calcular() -> tuple[pd.DataFrame, list[Path]]:
    filas, entradas = [], []
    g = np.random.default_rng(SEMILLA)
    for pais in PAISES:
        pf = PROC / f"factores_{pais}.parquet"
        pa = PROC / f"factores_agregados_{pais}_{VENTANA}.parquet"
        pc = K.RAIZ / "runs" / "EXP-002" / f"k_reloj_mes_turno_{pais}.csv"
        entradas += [pf, pa, pc]
        F = pd.read_parquet(pf, columns=["reloj", "mes", "turno", "k"])
        kp = F.groupby(["reloj", "mes", "turno"])["k"].first()
        ag = pd.read_parquet(pa)
        assert int(ag["anio"].max()) <= 2018 and int(ag["anio"].min()) >= 2012, "ANTI-FUGA fig02: solo 2012-2018 (ADR-0005)"
        csv = pd.read_csv(pc, header=[0, 1], skiprows=[2], index_col=0)
        for r in RELOJES:
            Sa, Ma, anios = _conteos_por_ano(ag, r)
            k_rec = _k_desde_conteos(Sa.sum(0), Ma.sum(0))
            w = g.multinomial(len(anios), np.full(len(anios), 1 / len(anios)), size=B)      # (B, anios) multiplicidades
            kb = _k_desde_conteos(np.einsum("ba,amt->bmt", w, Sa), np.einsum("ba,amt->bmt", w, Ma))
            lo, hi = np.nanpercentile(kb, 2.5, axis=0), np.nanpercentile(kb, 97.5, axis=0)
            for ti, t in enumerate(("D", "N")):
                for m in range(1, 13):
                    k = float(kp.loc[(r, m, t)])
                    assert abs(k - k_rec[m - 1, ti]) < 1e-9 * max(1, abs(k)), f"{pais} {r} {m} {t}: k parquet != reconstruccion"
                    assert abs(k - float(csv[(r, t)].loc[m])) < 1e-9 * max(1, abs(k)), f"{pais} {r} {m} {t}: k parquet != CSV EXP-002"
                    filas.append((ROT_PAIS[pais], r, t, m, k, float(lo[m - 1, ti]), float(hi[m - 1, ti]),
                                  int(Sa.sum(0)[m - 1, ti]), int(Ma.sum(0)[m - 1, ti])))
    df = pd.DataFrame(filas, columns=["pais", "reloj", "turno", "mes", "k", "ic_lo", "ic_hi", "S_cal", "M_cal"])
    dentro = ((df.ic_lo <= df.k * 1.0001) & (df.k <= df.ic_hi * 1.0001)).mean()
    print(f"fraccion de k puntuales dentro de su IC bootstrap: {dentro:.3f}")
    FIGDATA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(FIGDATA, index=False)
    return df, entradas


def _etiquetas_directas(ax, x, items, ymin, ymax, sep_frac=0.075):
    """items: [(y, texto, color)]; separa en log para que no se pisen (sep_frac = fraccion de la altura del eje)."""
    lo, hi = np.log(ymin), np.log(ymax)
    pos = sorted([(np.log(y), t, c) for y, t, c in items])
    ys = [p[0] for p in pos]
    sep = sep_frac * (hi - lo) * 1.6
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1] + sep)
    for y, (_, t, c) in zip(ys, pos):
        ax.text(x, np.exp(y), t, color=c, fontsize=17, fontweight="bold", ha="left", va="center", clip_on=False)


def _rango_serie(df: pd.DataFrame) -> tuple[float, float]:
    """Rango de k de los relojes que usa la serie (T y TA); el reloj A (respaldo) se excluye."""
    d = df[df.reloj.isin(["T", "TA"])]
    return float(d.k.min()), float(d.k.max())


def _titulo(df: pd.DataFrame) -> str:
    lo, hi = _rango_serie(df)
    return (f"One MODIS detection is worth about {lo:.0f} to {hi:.0f} VIIRS detections "
            "(Terra and Terra+Aqua clocks)")


def dibujar(df: pd.DataFrame):
    fig = K.nueva_figura()
    K.encabezado(fig, _titulo(df),
                 "k = S-NPP VIIRS detections per MODIS detection (hotspot detections, not fires), 2012-2018 calibration, by pass and month; "
                 "Aqua only (dashed) = backup clock; bands: 95% year-block bootstrap (7 years)")
    K.etiqueta_exploratoria(fig)
    gs = fig.add_gridspec(2, 2, left=0.115, right=0.862, top=0.755, bottom=0.17, wspace=0.44, hspace=0.12)
    YMIN, YMAX = 2.0, 80.0
    for i, pais in enumerate(["Mexico", "Argentina"]):
        for j, (t, tt) in enumerate(TURNOS):
            ax = fig.add_subplot(gs[i, j])
            d = df[(df.pais == pais) & (df.turno == t)]
            items = []
            for r in RELOJES:
                x = d[d.reloj == r].sort_values("mes")
                resp = r == "A"                                   # reloj de respaldo: tenue y discontinuo
                ax.fill_between(x.mes, x.ic_lo, x.ic_hi, color=COL[r], alpha=0.08 if resp else 0.18, lw=0, zorder=2)
                ax.plot(x.mes, x.k, "--" if resp else "-", marker=MK[r], ms=6.0 if resp else 7.5, lw=1.8 if resp else 2.8,
                        color=COL[r], alpha=0.75 if resp else 1.0, mec="white", mew=1.0, zorder=3)
                items.append((float(x.k.iloc[-1]), ETQ[r], COL[r]))
            _etiquetas_directas(ax, 12.45, items, YMIN, YMAX)
            ax.set_yscale("log"); ax.set_ylim(YMIN, YMAX)
            ax.set_yticks([2, 5, 10, 20, 50]); ax.set_yticklabels(["2", "5", "10", "20", "50"]); ax.minorticks_off()
            ax.set_xlim(0.7, 12.4); ax.set_xticks(range(1, 13)); ax.set_xticklabels(MESES)
            ax.tick_params(axis="x", labelbottom=(i == 1), labelsize=17)
            if i == 0:
                ax.set_title(tt + (" (Terra 10:30 / Aqua 13:30)" if t == "D" else " (Terra 22:30 / Aqua 01:30)"),
                             loc="left", fontsize=19, fontweight="bold")
            if i == 0 and t == "N":                      # nota del reloj de respaldo con sus propias cifras
                a = d[(d.reloj == "A") & (d.mes.isin([11, 12]))].sort_values("mes")
                ax.text(0.03, 0.03, f"Backup clock, few detections (Nov/Dec: {int(a.M_cal.iloc[0])}, {int(a.M_cal.iloc[1])})\n"
                        f"k up to {a.k.max():.0f}, CI extends to {a.ic_hi.max():.0f}", transform=ax.transAxes, fontsize=16,
                        color=K.TXT2, ha="left", va="bottom", bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.5), zorder=6)
            if i == 1:
                ax.set_xlabel("Calendar month")
            if j == 0:
                ax.set_ylabel("k (x, log scale)", fontsize=18)
                ax.text(-0.22, 0.5, pais, transform=ax.transAxes, rotation=90, fontsize=22, fontweight="bold",
                        color=K.PAIS[pais], ha="center", va="center")
    return fig


def main(real: bool = False) -> list[Path]:
    if real:
        df, entradas = calcular()
    else:
        assert FIGDATA.exists(), "falta figures/figdata/ (corre --real con flock)"
        df, entradas = pd.read_csv(FIGDATA), None
    fig = dibujar(df)
    fuente = ("Data: NASA FIRMS MODIS Collection 6 (2000-2022) and 6.1 (2023 on) (Terra, Aqua) and VIIRS 375 m S-NPP, Mexico and Argentina, 2012-02 to 2018-12 "
              "(calibration window); k from EXP-002 (shrunk monthly ratio, n0k = 20); bands exploratory | analysis: this project")
    base = K.FIGURAS_DIR / NOMBRE
    salidas = K.cerrar(fig, base, fuente)
    if entradas is not None:
        K.escribir_manifiesto(
            base, FIG_ID, _titulo(df),
            origen={"experimento": "EXP-002", "script_experimento": "src/nucleo/experimentos.py", "script_figura": "src/figuras/fig02_relojes.py",
                    "datos": "data/processed/factores_{mexico,argentina}.parquet (k); factores_agregados_*_2012-02-01_2018-12-31.parquet (IC); "
                             "runs/EXP-002/k_reloj_mes_turno_*.csv (verificacion)",
                    "figdata": str(FIGDATA.relative_to(K.RAIZ)), "ic": f"bootstrap por bloque-ano, B={B}, percentiles 2.5-97.5, exploratorio"},
            comando="flock data/.pesado.lock .venv/bin/python src/figuras/fig02_relojes.py --real",
            entradas=entradas + [Path(__file__).resolve()], semilla=SEMILLA,
            extra={"clm": "CLM-102 (metodo: factores por pais, reloj, mes y turno, calibracion 2012-02 -> 2018-12; ledger: borrador al 2026-11-15). "
                          "El rango 'about 3 to 18' es una cifra descriptiva de calibracion SIN entrada propia en el ledger: no usarla en texto publico "
                          "sin registrarla (o citar solo CLM-102 sin cifra). Sigue EXPLORATORY (periodo de calibracion, no es resultado de la prueba unica).",
                   "k_min_T_TA": _rango_serie(df)[0], "k_max_T_TA": _rango_serie(df)[1],
                   "k_max_A_respaldo": float(df[df.reloj == "A"].k.max()), "ic_hi_max_A_respaldo": float(df[df.reloj == "A"].ic_hi.max()),
                   "nota": "titulo usa solo relojes T y TA; A (Aqua sola) es respaldo con pocas detecciones nocturnas; eje hasta 80, sin recorte",
                   "filas": int(len(df))})
    return salidas


if __name__ == "__main__":
    print(*main("--real" in sys.argv), sep="\n")
