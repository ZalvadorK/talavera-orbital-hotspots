#!/usr/bin/env python3
"""FIG-03 · Transferencia Mexico <-> Argentina (T1/T2): B, G y delta kappa frente a los umbrales pre-registrados.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

DATOS REALES de la prueba unica pre-registrada (tag prereg-v1 @ 90e10ce): runs/EXP-009, metricas.transferencia
(la reserva se abre SOLO por la ruta verificada, _comun.cargar_prueba_unica; nada se vuelve a correr).

Mensaje (titulo-afirmacion, CLM-108): los factores no viajaron entre paises, salvo la forma de Argentina aplicada
en Mexico (T2 AR->MX pasa los tres criterios); T1 (todos los parametros) no pasa en ninguna direccion; T2 MX->AR falla
solo en delta kappa.  Resultado mixto/negativo, reportado tal cual.

Criterio (config/validacion.yaml umbrales.T; PREREGISTRATION §4): transferible si |log B| <= 0.10, G <= 1.15 y
delta kappa >= -0.05.  B = sum S / sum S_hat; G = MdALE_transfer / MdALE_local; delta kappa = kappa_transfer - kappa_local
(bloque 3 grados x mes).  EXP-009 reporta estas metricas SOLO como puntos (sin IC): se rotula en la figura.

Uso:
  flock data/.pesado.lock .venv/bin/python src/figuras/fig03_transferencia.py --real    # lee runs/EXP-009, escribe figdata + figura + manifiesto
  .venv/bin/python src/figuras/fig03_transferencia.py                                     # redibuja desde figures/figdata/
(`--final` es alias de `--real`, por scripts/reproducir.sh.)
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as K  # noqa: E402

FIG_ID = "FIG-03"
NOMBRE = "FIG-03_transfer_mx_ar"
FIGDATA = K.FIGURAS_DIR / "figdata" / f"{NOMBRE}.csv"
CLM = "CLM-108"
LOGB_MAX, G_MAX, DK_MIN = 0.10, 1.15, -0.05     # config/validacion.yaml -> umbrales.T
DIRS = [("mexico->argentina", "Mexico → Argentina"), ("argentina->mexico", "Argentina → Mexico")]
MODOS = [("T1", "T1: all parameters", K.PRUEBA["T1_all_parameters"], "o"),
         ("T2", "T2: shape only", K.PRUEBA["T2_shape_only"], "s")]
TITULO = "Conversion factors did not travel between countries, except Argentina's shape applied in Mexico"
SUBTITULO = ("Transfer of the MODIS-to-VIIRS conversion at 3-degree block x month: T1 moves all parameters, T2 moves the shape and keeps the "
             "target country's own level. Filled marker = criterion met; units: hotspot detections, not fires.")
FUENTE = ("Data: NASA FIRMS standard processing, MODIS Collection 6 (2000-2022) and 6.1 (2023 on) (Terra, Aqua) and VIIRS 375 m (S-NPP, NOAA-20), Mexico and Argentina, held-out test "
          "2019-2021, one pre-registered run (EXP-009, tag prereg-v1). Point estimates: EXP-009 computes no CI for the transfer metrics. "
          "Prior exposure to 2019-2025 data is declared in the pre-registration (section 2) and accompanies this result | analysis: this project")


def extraer() -> tuple[pd.DataFrame, list[Path], dict]:
    verdict, met, man = K.cargar_prueba_unica()
    filas = []
    for d, _ in DIRS:
        for m, _, _, _ in MODOS:
            t = met["transferencia"][d][m]
            p_b, p_g, p_k = abs(t["log_B"]) <= LOGB_MAX, t["G"] <= G_MAX, t["delta_kappa"] >= DK_MIN
            ok = bool(verdict["veredicto"]["transferencia"][d][m])
            assert ok == (p_b and p_g and p_k), f"{d} {m}: el veredicto de EXP-009 no coincide con los umbrales"
            filas.append(dict(direccion=d, modo=m, B=t["B"], log_B=t["log_B"], G=t["G"], kappa_transfer=t["kappa_transfer"],
                              kappa_local=t["kappa_local"], delta_kappa=t["delta_kappa"], pasa_logB=p_b, pasa_G=p_g,
                              pasa_dkappa=p_k, transferible=ok))
    entradas = [K.RUN_PRUEBA / n for n in ("verdict.json", "metricas.json", "manifiesto.json")]
    return pd.DataFrame(filas), entradas, man


def _marca(ax, x, y, col, mk, ok, txt):
    ax.plot([x], [y], mk, color=col, ms=17, mec=col, mew=2.5, mfc=col if ok else "white", zorder=4)
    ax.text(x, y + 0.34, f"{txt}  {'pass' if ok else 'fail'}", fontsize=18, fontweight="bold", ha="center", va="bottom",
            color=K.TXT, zorder=6, bbox=dict(fc="white", ec="none", pad=1.0, alpha=1.0))


def dibujar(df: pd.DataFrame):
    fig = K.nueva_figura()
    fig.text(0.035, 0.965, textwrap.fill(TITULO, 54), fontsize=23, fontweight="bold", ha="left", va="top", color=K.TXT, linespacing=1.15)
    fig.text(0.035, 0.862, textwrap.fill(SUBTITULO, 112), fontsize=17, ha="left", va="top", color=K.TXT2)
    K.etiqueta_prueba_unica(fig)
    gs = fig.add_gridspec(2, 3, left=0.235, right=0.975, top=0.70, bottom=0.17, wspace=0.12, hspace=0.50)
    cols = [("log_B", "Level bias: log B\npass if |log B| <= 0.10", (-0.30, 0.26), (-LOGB_MAX, LOGB_MAX), "{:+.2f}", "pasa_logB"),
            ("G", "Error ratio vs local: G\npass if G <= 1.15", (1.0, 1.30), (1.0, G_MAX), "{:.2f}", "pasa_G"),
            ("delta_kappa", "Change in kappa vs local\npass if >= -0.05", (-0.125, 0.025), (DK_MIN, 0.025), "{:+.3f}", "pasa_dkappa")]
    for i, (dk, dtxt) in enumerate(DIRS):
        d = df[df.direccion == dk].set_index("modo")
        for j, (campo, ctitulo, xlim, banda, fmt, pk) in enumerate(cols):
            ax = fig.add_subplot(gs[i, j])
            ax.axvspan(*banda, color="#DDE9DD", alpha=0.9, zorder=0)
            for yk, (m, _, col, mk) in zip((1, 0), MODOS):
                r = d.loc[m]
                _marca(ax, r[campo], yk, col, mk, bool(r[pk]), fmt.format(r[campo]))
            for edge in banda:
                if xlim[0] < edge < xlim[1]:
                    ax.axvline(edge, color=K.TXT, ls="--", lw=2, zorder=1)
            ax.set_xlim(*xlim)
            ax.set_ylim(-0.55, 1.85)
            ax.grid(axis="y", visible=False)
            ax.spines["left"].set_visible(False)
            ax.set_title(ctitulo, loc="left", fontsize=18, fontweight="bold", color=K.TXT, pad=8) if i == 0 else None
            ax.tick_params(axis="x", labelsize=17)
            if j == 0:
                ax.set_yticks([1, 0])
                ax.set_yticklabels([f"{m}: {'transferable' if d.loc[m].transferible else 'NOT transferable'}" for m, *_ in MODOS],
                                   fontsize=18)
                ax.tick_params(axis="y", length=0)
            else:
                ax.set_yticks([])
        pos = fig.axes[-1].get_position()
        fig.text(0.035, pos.y1 + (0.075 if i == 0 else 0.03), dtxt, fontsize=21, fontweight="bold", ha="left", va="center", color=K.TXT)
    return fig


def main(real: bool = False) -> list[Path]:
    if real:
        df, entradas, man = extraer()
        FIGDATA.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(FIGDATA, index=False)
    else:
        assert FIGDATA.exists(), "falta figures/figdata/FIG-03 (corre --real)"
        df, entradas, man = pd.read_csv(FIGDATA), None, None
    fig = dibujar(df)
    base = K.FIGURAS_DIR / NOMBRE
    salidas = K.cerrar(fig, base, FUENTE)
    if entradas is not None:
        K.escribir_manifiesto(
            base, FIG_ID, TITULO,
            origen={"experimento": K.EXP_PRUEBA, "commit_experimento": man["commit"], "tag": man["guarda"]["tag"],
                    "script_figura": "src/figuras/fig03_transferencia.py", "figdata": str(FIGDATA.relative_to(K.RAIZ)),
                    "campos": "metricas.transferencia.<dir>.<T1|T2>: B, log_B, G, kappa_transfer, kappa_local, delta_kappa; "
                              "verdict.veredicto.transferencia (coherencia verificada contra los umbrales)",
                    "ic": "ninguno: EXP-009 reporta las metricas de transferencia como puntos"},
            comando="flock data/.pesado.lock .venv/bin/python src/figuras/fig03_transferencia.py --real",
            entradas=entradas + [FIGDATA, Path(__file__).resolve()], semilla=man["semilla"],
            extra={"estado": "single pre-registered test result (EXP-009); published only with the prior-exposure statement",
                   "clm": CLM, "clm_nota": "CLM-108 (transferencia MX<->AR, T1/T2): en el ledger esta 'borrador / pendiente de verdict.json' al generar "
                          "la figura; debe pasar a verificado (EVD con verdict.json) antes de publicar",
                   "rotulo_figura": "PRE-REGISTERED SINGLE TEST 2019-2021 (EXP-009)",
                   "umbrales": {"abs_log_B_max": LOGB_MAX, "G_max": G_MAX, "delta_kappa_min": DK_MIN, "fuente": "config/validacion.yaml umbrales.T"},
                   "anti_fuga": "n/a tras el veredicto; reserva abierta solo por runs/EXP-009/verdict.json (modo prueba, dirty=false)",
                   "veredicto": {f"{r.direccion} {r.modo}": bool(r.transferible) for r in df.itertuples()}})
    return salidas


if __name__ == "__main__":
    print(*main("--real" in sys.argv or "--final" in sys.argv), sep="\n")
