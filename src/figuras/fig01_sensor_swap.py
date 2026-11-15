#!/usr/bin/env python3
"""FIG-01 · "Sensor-swap vs twin-swap": swapping MODIS for VIIRS vs swapping one VIIRS satellite for its twin.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

DATOS REALES de la prueba unica pre-registrada (tag prereg-v1 @ 90e10ce), ejecutada una vez: runs/EXP-009
(verdict.json + metricas.json + manifiesto.json, dirty=false).  La reserva se abre SOLO por esa ruta verificada
(_comun.cargar_prueba_unica exige verdict.json con modo 'prueba').  Nada de esto se vuelve a correr.

Mensaje (titulo-afirmacion, CLM-104): al cambiar NOAA-20 por MODIS armonizado, el marcado de meses "inusuales"
a bloque de 3 grados cambia MAS que al cambiarlo por su gemelo S-NPP; el criterio P2 (kappa >= 0.60 y >= 0.75 x kappa
gemelos) NO se cumple en ninguno de los dos paises (escenario C).  Resultado negativo, reportado tal cual.

Lo que se dibuja (metricas.paises.<pais>.E1c.P2_P2b, escala publicada E1c, bloque 3 grados x mes):
  * twin_swap   = kappa_gemelos (S-NPP vs NOAA-20), IC95 bootstrap por bloque 3 grados x anio
  * harmonized  = kappa_cruzado (MODIS armonizado vs NOAA-20), IC95 igual
  * M1          = kappa_cruzado_M1 (razon global unica por pais): SOLO punto, EXP-009 no calcula IC
  * M0          = kappa_cruzado_M0 (MODIS sin armonizar): SOLO punto
  * lineas: 0.60 (piso absoluto) y 0.75 x kappa gemelos (umbrales fijados en config/validacion.yaml: umbrales.P2)

Uso (candado de memoria por norma del proyecto, aunque aqui no se lee data/processed):
  flock data/.pesado.lock .venv/bin/python src/figuras/fig01_sensor_swap.py --real     # lee runs/EXP-009, escribe figdata + figura + manifiesto
  .venv/bin/python src/figuras/fig01_sensor_swap.py                                      # redibuja desde figures/figdata/ (CSV)
(`--final` es alias de `--real`, por scripts/reproducir.sh.)
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as K  # noqa: E402

FIG_ID = "FIG-01"
NOMBRE = "FIG-01_sensor_swap_vs_twin_swap"
FIGDATA = K.FIGURAS_DIR / "figdata" / f"{NOMBRE}.csv"
CLM = "CLM-104"
PAISES = {"Mexico": "mexico", "Argentina": "argentina"}
FILAS = [  # (clave, etiqueta directa, color, marcador)
    ("twin_swap", "Twin swap: S-NPP vs NOAA-20 (reference)", K.C["S-NPP"], "D"),
    ("harmonized", "Sensor swap: harmonized MODIS vs NOAA-20", K.C["VIIRS-equivalent"], "o"),
    ("M1", "Baseline M1: one overall ratio (no CI)", K.C["baseline_M1"], "s"),
    ("M0", "Control M0: unharmonized MODIS (no CI)", K.C["unharmonized_M0"], "X"),
]
KAPPA_MIN, COC_MIN = 0.60, 0.75   # config/validacion.yaml -> umbrales.P2 (fijados en el congelamiento)
TITULO = "Swapping MODIS for VIIRS changes unusual-month flags more than swapping twin VIIRS satellites"
SUBTITULO = ("Agreement (Cohen kappa, 3 classes: high / none / low) of monthly 'unusual' flags per 3-degree block against NOAA-20, "
             "95% CI; units: hotspot detections, not fires. Pre-registered criterion not met in either country.")
FUENTE = ("Data: NASA FIRMS standard, MODIS Collection 6 (2000-2022) and 6.1 (2023 on) (Terra, Aqua), VIIRS 375 m (S-NPP, NOAA-20); Mexico, Argentina; "
          "held-out test 2019-2021, one pre-registered run (EXP-009, tag prereg-v1); 3-degree blocks x month, CI95 bootstrap by block x year (B=1000). "
          "Shown with the prior-exposure statement (pre-registration section 2) and its post-freeze addendum (4 more QC tables; none compares "
          "harmonized MODIS with VIIRS) | analysis: this project")


def extraer() -> tuple[pd.DataFrame, list[Path], dict]:
    """Lee runs/EXP-009 (verdict verificado) y arma la tabla larga."""
    verdict, met, man = K.cargar_prueba_unica()
    filas = []
    for pais, clave in PAISES.items():
        e = met["paises"][clave]["E1c"]["P2_P2b"]
        tw, cr = e["kappa_gemelos"], e["kappa_cruzado"]
        cp = e["cociente_pareado"]
        base = dict(pais=pais, kappa_twin=tw["punto"], umbral_twin=round(COC_MIN * tw["punto"], 4),
                    cociente=cp["punto"], coc_lo=cp["ic95"][0], coc_hi=cp["ic95"][1],
                    n_bloques=e["n_bloques"], n_bloque_meses=e["n_bloque_meses"],
                    P2_pasa=bool(verdict["veredicto"]["por_pais"][clave]["E1c"]["P2_bloque3"]))
        filas += [
            dict(base, comparacion="twin_swap", kappa=tw["punto"], ic_lo=tw["ic95"][0], ic_hi=tw["ic95"][1]),
            dict(base, comparacion="harmonized", kappa=cr["punto"], ic_lo=cr["ic95"][0], ic_hi=cr["ic95"][1]),
            dict(base, comparacion="M1", kappa=e["kappa_cruzado_M1"]["punto"], ic_lo=float("nan"), ic_hi=float("nan")),
            dict(base, comparacion="M0", kappa=e["kappa_cruzado_M0"]["punto"], ic_lo=float("nan"), ic_hi=float("nan")),
        ]
    entradas = [K.RUN_PRUEBA / n for n in ("verdict.json", "metricas.json", "manifiesto.json")]
    return pd.DataFrame(filas), entradas, man


def dibujar(df: pd.DataFrame):
    fig = K.nueva_figura()
    fig.text(0.035, 0.965, textwrap.fill(TITULO, 48), fontsize=23, fontweight="bold", ha="left", va="top", color=K.TXT, linespacing=1.15)
    fig.text(0.035, 0.862, textwrap.fill(SUBTITULO, 112), fontsize=17, ha="left", va="top", color=K.TXT2)
    K.etiqueta_prueba_unica(fig)
    axs = fig.subplots(1, 2, sharey=True, gridspec_kw=dict(left=0.03, right=0.975, top=0.77, bottom=0.20, wspace=0.06))
    for ax, pais in zip(axs, PAISES):
        d = df[df.pais == pais].set_index("comparacion")
        u_tw = float(d.loc["twin_swap"].umbral_twin)
        for i, (clave, etiqueta, col, mk) in enumerate(FILAS):
            r = d.loc[clave]
            y = len(FILAS) - 1 - i
            if pd.notna(r.ic_lo):
                ax.errorbar(r.kappa, y, xerr=[[r.kappa - r.ic_lo], [r.ic_hi - r.kappa]], fmt=mk, color=col, ms=15,
                            mec="white", mew=1.5, elinewidth=3.5, capsize=7, zorder=3)
                xt = r.ic_hi + 0.02
            else:
                ax.plot([r.kappa], [y], mk, color=col, ms=15, mec="white", mew=1.5, zorder=3)
                xt = r.kappa + 0.035
            ax.text(0.02, y + 0.30, etiqueta, fontsize=18, color=K.TXT, va="bottom", ha="left",
                    transform=ax.get_yaxis_transform(), zorder=5, bbox=dict(fc="white", ec="none", pad=1.5, alpha=1.0))
            ax.text(min(xt, 0.93), y, f"{r.kappa:.2f}", fontsize=18, va="center",
                    color=col if clave != "M0" else K.TXT2, fontweight="bold", zorder=6,
                    bbox=dict(fc="white", ec="none", pad=1.0, alpha=1.0))
        ax.axvline(KAPPA_MIN, color=K.TXT, ls="--", lw=2, zorder=1)
        ax.axvline(u_tw, color=K.TXT, ls=":", lw=2.6, zorder=1)
        ytop = len(FILAS) + 0.2
        ax.text(KAPPA_MIN + 0.012, ytop, f"kappa >= {KAPPA_MIN:.2f}", fontsize=18, color=K.TXT, va="center", ha="left")
        ax.text(u_tw - 0.012, ytop, f"{COC_MIN:.2f} x twin = {u_tw:.2f}", fontsize=18, color=K.TXT, va="center", ha="right")
        cr = d.loc["harmonized"]
        ax.text(0.99, -0.62, f"Cross / twin kappa = {cr.cociente:.2f}\n[{cr.coc_lo:.2f}, {cr.coc_hi:.2f}], needs >= {COC_MIN:.2f}\n"
                f"Criterion {'met' if cr.P2_pasa else 'NOT met'}",
                fontsize=18, color=K.TXT, ha="right", va="center", linespacing=1.25, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.35", fc="#F5F5F5", ec=K.TXT2, lw=1.5))
        ax.set_xlim(0, 1)
        ax.set_ylim(-1.35, len(FILAS) + 1.15)
        ax.set_yticks([])
        ax.text(0.02, len(FILAS) + 0.95, pais, fontsize=22, fontweight="bold", color=K.TXT, va="center", ha="left")
        ax.set_xlabel("Kappa vs NOAA-20 flags (0 = chance, 1 = identical)")
        ax.grid(axis="y", visible=False)
        ax.spines["left"].set_visible(False)
    return fig


def main(real: bool = False) -> list[Path]:
    if real:
        df, entradas, man = extraer()
        FIGDATA.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(FIGDATA, index=False)
    else:
        assert FIGDATA.exists(), "falta figures/figdata/FIG-01 (corre --real)"
        df, entradas, man = pd.read_csv(FIGDATA), None, None
    fig = dibujar(df)
    base = K.FIGURAS_DIR / NOMBRE
    salidas = K.cerrar(fig, base, FUENTE)
    if entradas is not None:
        K.escribir_manifiesto(
            base, FIG_ID, TITULO,
            origen={"experimento": K.EXP_PRUEBA, "commit_experimento": man["commit"], "tag": man["guarda"]["tag"],
                    "script_figura": "src/figuras/fig01_sensor_swap.py", "figdata": str(FIGDATA.relative_to(K.RAIZ)),
                    "campos": "metricas.paises.<pais>.E1c.P2_P2b: kappa_gemelos, kappa_cruzado, kappa_cruzado_M1, kappa_cruzado_M0, cociente_pareado; "
                              "verdict.veredicto.por_pais.<pais>.E1c.P2_bloque3",
                    "ic": "bootstrap por bloque 3 grados x anio, B=1000, percentiles 2.5-97.5 (calculado por EXP-009); M1 y M0 solo punto"},
            comando="flock data/.pesado.lock .venv/bin/python src/figuras/fig01_sensor_swap.py --real",
            entradas=entradas + [FIGDATA, Path(__file__).resolve()], semilla=man["semilla"],
            extra={"estado": "single pre-registered test result (EXP-009, scenario C); published only with the prior-exposure statement",
                   "clm": CLM, "clm_nota": "CLM-104 = veredicto sensor-swap (texto C); el ledger lo tiene en estado 'borrador' al generar la figura: "
                          "debe pasar a verificado (EVD con la ruta de verdict.json) antes de publicar",
                   "rotulo_figura": "PRE-REGISTERED SINGLE TEST 2019-2021 (EXP-009)",
                   "umbrales": {"kappa_min": KAPPA_MIN, "cociente_gemelos_min": COC_MIN, "fuente": "config/validacion.yaml umbrales.P2"},
                   "anti_fuga": "n/a tras el veredicto; reserva abierta solo por runs/EXP-009/verdict.json (modo prueba, dirty=false)",
                   "valores": {r.pais: {"kappa_twin": r.kappa_twin, "umbral_twin": r.umbral_twin, "cociente": r.cociente}
                               for r in df[df.comparacion == "harmonized"].itertuples()}})
    return salidas


if __name__ == "__main__":
    print(*main("--real" in sys.argv or "--final" in sys.argv), sep="\n")
