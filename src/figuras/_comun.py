"""Utilidades comunes de las plantillas FIG-01..FIG-04.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

- Lienzo 1920x1080 exacto (16x9 pulgadas a 120 dpi, sin bbox 'tight').
- Colores desde figures/paleta.json (misma entidad, mismo color).
- Marca "SI-generated (AI)", fuente en el pie, unidades "hotspot detections, not fires".
- Rotulo SYNTHETIC dentro de la figura cuando los datos son de ejemplo.
- Lectura de runs/EXP-*/figdata/*.csv con candados anti-fuga (ADR-0005).

Contrato de datos (lo escriben los experimentos; ver docstring de cada figNN):
    runs/EXP-NNN/manifiesto.json   -> {"figuras": {"FIG-01": {"clm": "CLM-0NN", "titulo": "...", "fuente": "..."}}}
    runs/EXP-NNN/figdata/figNN_*.csv
Las plantillas NO leen parquets ni filas crudas: solo agregados ya calculados por el experimento.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
RUNS = RAIZ / "runs"
PALETA = json.loads((RAIZ / "figures" / "paleta.json").read_text(encoding="utf-8"))
PREVIEW_DIR = RAIZ / "figures" / "diag" / "plantillas"
FIGURAS_DIR = RAIZ / "figures"

UNIDADES = "hotspot detections, not fires"
MARCA_SI = "SI-generated (AI)"
CORTE_FUGA = pd.Timestamp("2019-01-01")
PLAT_RESERVADAS = {"Terra", "Aqua", "S-NPP"}  # >= 2019-01-01 reservadas para la prueba unica (ADR-0005)

C = PALETA["entidades"]
PAIS = PALETA["paises"]
TURNO = PALETA["turnos"]["colores"]
PRUEBA = PALETA["pruebas"]
TXT = PALETA["texto"]
TXT2 = PALETA["texto_secundario"]
REJ = PALETA["rejilla"]


def cmap_secuencial() -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list("talavera_seq", PALETA["secuencial"]["stops"])


def cmap_divergente() -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list("talavera_div", PALETA["divergente"]["stops"])


def estilo() -> None:
    """Tipografia >= 18 pt en 1920x1080 (regla 8); sin bbox tight para fijar el tamano."""
    plt.rcParams.update({
        "figure.figsize": (16, 9), "figure.dpi": 120, "savefig.dpi": 120,
        "font.size": 18, "axes.titlesize": 20, "axes.labelsize": 19,
        "xtick.labelsize": 18, "ytick.labelsize": 18, "legend.fontsize": 18,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.5, "grid.color": REJ,
        "axes.edgecolor": TXT2, "text.color": TXT, "axes.labelcolor": TXT,
        "xtick.color": TXT, "ytick.color": TXT, "figure.facecolor": "white", "axes.facecolor": "white",
        "hatch.linewidth": 1.2, "svg.fonttype": "none",
    })


def nueva_figura():
    estilo()
    return plt.figure(figsize=(16, 9), dpi=120)


def encabezado(fig, titulo: str, subtitulo: str = "", sintetico: bool = False) -> None:
    """Titulo-afirmacion (un mensaje por figura, max 2 lineas) + subtitulo con unidades."""
    fig.text(0.035, 0.965, textwrap.fill(titulo, 58), fontsize=23, fontweight="bold", ha="left", va="top",
             color=TXT, linespacing=1.15)
    if subtitulo:
        fig.text(0.035, 0.862, textwrap.fill(subtitulo, 112), fontsize=17, ha="left", va="top", color=TXT2)
    if sintetico:
        fig.text(0.965, 0.962, "SYNTHETIC DATA\nnot a result", fontsize=18, fontweight="bold",
                 ha="right", va="top", color="#7A1F00", linespacing=1.2,
                 bbox=dict(boxstyle="round,pad=0.4", fc="#FFE9D6", ec="#D55E00", lw=2))
        # sello diagonal tenue, detras de los graficos
        fig.text(0.5, 0.45, "SYNTHETIC", fontsize=130, fontweight="bold", color="#D55E00", alpha=0.06,
                 ha="center", va="center", rotation=25, zorder=0)


def cerrar(fig, ruta_base: Path, fuente: str, sintetico: bool = False) -> list[Path]:
    """Pie con fuente + marca SI; guarda PNG (1920x1080) y SVG. Devuelve las rutas."""
    pie = fuente + (" | SYNTHETIC data, illustrative only" if sintetico and "SYNTHETIC" not in fuente else "")
    fig.text(0.035, 0.010, textwrap.fill(pie, 120), fontsize=13.5, ha="left", va="bottom", color=TXT2, linespacing=1.2)
    fig.text(0.965, 0.010, MARCA_SI, fontsize=15, ha="right", va="bottom", color=TXT2, fontweight="bold")
    ruta_base = Path(ruta_base)
    ruta_base.parent.mkdir(parents=True, exist_ok=True)
    salidas = []
    for ext in (".png", ".svg"):
        p = ruta_base.with_suffix(ext)
        fig.savefig(p)  # sin bbox_inches: 1920x1080 exacto
        salidas.append(p)
    plt.close(fig)
    return salidas


# --- Lectura de runs con candados anti-fuga ----------------------------------------------------------
def auditar_fuga(df: pd.DataFrame, col_fecha: str | None = None, col_plat: str | None = None,
                 col_plat_valor: str | None = None) -> None:
    """Falla si hay filas Terra/Aqua/S-NPP con fecha >= 2019-01-01 (ADR-0005).

    `col_fecha` puede ser fecha o 'periodo_max' (fecha maxima cubierta por la fila agregada).
    """
    if col_fecha is None or col_plat is None:
        return
    f = pd.to_datetime(df[col_fecha])
    reservada = df[col_plat].isin(PLAT_RESERVADAS) & (f >= CORTE_FUGA)
    assert not reservada.any(), (
        f"ANTI-FUGA: {int(reservada.sum())} filas de Terra/Aqua/S-NPP con fecha >= 2019-01-01 (ADR-0005)")


def buscar_run(patron_csv: str, exigir_veredicto: bool = False):
    """Busca runs/EXP-*/figdata/<patron_csv>. Devuelve (Path_csv, manifiesto_dict) o None.

    `exigir_veredicto`: para figuras con resultados de la prueba unica (FIG-01, FIG-03), el run debe
    tener `verdict.json`; sin el, la figura queda en SYNTHETIC (ADR-0005: nada de la prueba antes del veredicto).
    """
    for csv in sorted(RUNS.glob(f"EXP-*/figdata/{patron_csv}")):
        run = csv.parents[1]
        if exigir_veredicto and not (run / "verdict.json").exists():
            continue
        man_p = run / "manifiesto.json"
        man = json.loads(man_p.read_text(encoding="utf-8")) if man_p.exists() else {}
        return csv, man
    return None


def meta_figura(man: dict, fig_id: str) -> dict:
    return (man.get("figuras") or {}).get(fig_id, {})


def etiqueta_eje_conteo() -> str:
    return f"Monthly {UNIDADES}"


def anotar(ax, xy, texto, xytext, color=TXT, **kw):
    ax.annotate(texto, xy=xy, xytext=xytext, fontsize=18, color=color, ha=kw.pop("ha", "left"),
                arrowprops=dict(arrowstyle="-", color=color, lw=1.5), **kw)


def rng(semilla: int = 20261114):
    return np.random.default_rng(semilla)


# --- Figuras con datos reales de calibracion: etiqueta "exploratory" y manifiesto (anadido 2026-11-15) -------
def etiqueta_exploratoria(fig, texto: str = "EXPLORATORY\ncalibration period 2012-2018") -> None:
    """Rotulo en la esquina (como el de SYNTHETIC, en tono neutro): resultados de desarrollo, no claims."""
    fig.text(0.965, 0.962, texto, fontsize=18, fontweight="bold", ha="right", va="top", color="#1A1A1A", linespacing=1.2,
             bbox=dict(boxstyle="round,pad=0.4", fc="#EDEDED", ec="#4D4D4D", lw=2))


def sha256_archivo(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def escribir_manifiesto(base: Path, fig_id: str, titulo: str, origen: dict, comando: str, entradas: list[Path],
                        extra: dict | None = None, semilla: int | None = None) -> Path:
    """figures/FIG-NN_<nombre>.manifest.json: origen (EXP/script), comando, hash de entrada, estado de claim."""
    import datetime as dt
    import platform
    man = {
        "figura": fig_id, "titulo": titulo, "marca_si": "SI-generated (AI): Claude Code wrote the script that produced this file "
                                                         "during the event; reviewed by the team.",
        "creado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "estado": "exploratory (calibration period / development); not a claim",
        "clm": "PENDING (no CLM registered; do not use in public material until one exists)",
        "origen": origen, "comando": comando, "semilla": semilla,
        "entradas": [{"ruta": str(Path(e).resolve().relative_to(RAIZ)), "sha256": sha256_archivo(Path(e)),
                      "bytes": Path(e).stat().st_size} for e in entradas],
        "salidas": [str(Path(base).with_suffix(x).relative_to(RAIZ)) for x in (".png", ".svg")],
        "python": platform.python_version(), "matplotlib": matplotlib.__version__,
        "anti_fuga": "Terra/Aqua/S-NPP >= 2019-01-01 not read (ADR-0005)",
    }
    man.update(extra or {})
    man["salidas_sha256"] = {str(Path(base).with_suffix(x).relative_to(RAIZ)): sha256_archivo(Path(base).with_suffix(x))
                             for x in (".png", ".svg") if Path(base).with_suffix(x).exists()}
    p = Path(base).with_suffix(".manifest.json")
    p.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


# --- Figuras con resultados de la PRUEBA UNICA (EXP-009), anadido 2026-11-15 tras el veredicto -----------------
EXP_PRUEBA = "EXP-009"
RUN_PRUEBA = RUNS / EXP_PRUEBA


def cargar_prueba_unica() -> tuple[dict, dict, dict]:
    """Abre la reserva SOLO por la ruta verificada: runs/EXP-009/verdict.json (modo 'prueba'). Devuelve
    (verdict, metricas, manifiesto). Falla si falta el veredicto o si no es la prueba unica."""
    vp = RUN_PRUEBA / "verdict.json"
    assert vp.exists(), f"{vp} no existe: la reserva no se abre sin veredicto (ADR-0005)"
    verdict = json.loads(vp.read_text(encoding="utf-8"))
    assert verdict.get("modo") == "prueba", "verdict.json no es de la prueba unica"
    metricas = json.loads((RUN_PRUEBA / "metricas.json").read_text(encoding="utf-8"))
    manifiesto = json.loads((RUN_PRUEBA / "manifiesto.json").read_text(encoding="utf-8"))
    assert manifiesto.get("dirty") is False and manifiesto.get("modo") == "prueba"
    return verdict, metricas, manifiesto


def etiqueta_prueba_unica(fig, texto: str = "PRE-REGISTERED SINGLE TEST\n2019-2021 (EXP-009)") -> None:
    """Rotulo de esquina para figuras de la prueba unica (reemplaza SYNTHETIC/EXPLORATORY)."""
    fig.text(0.965, 0.962, texto, fontsize=18, fontweight="bold", ha="right", va="top", color="#0B2A4A", linespacing=1.2,
             bbox=dict(boxstyle="round,pad=0.4", fc="#E6F0FA", ec="#0072B2", lw=2))
