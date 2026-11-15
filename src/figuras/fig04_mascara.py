#!/usr/bin/env python3
"""FIG-04 · "A volcano is not a wildfire": mascara estatica antes/despues cerca del Popocatepetl, datos reales.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Mensaje (titulo-afirmacion): la mascara estatica (ADR-0002/0003; diferenciador ADR-0007), ajustada solo con S-NPP 2012-2018,
quita las detecciones del crater (type = 1) tambien en un sensor que nunca vio (NOAA-20) y deja casi todas las de vegetacion
(type = 0). Todas las cifras se CALCULAN de la tabla. El titulo solo sale si se cumple un chequeo de coherencia (UMBRAL_*:
crater removido >= 95 % y vegetacion removida <= 5 % en NOAA-20); si no, el script falla. Los umbrales NO se presentan como
criterio pre-registrado: no consta en ningun documento commiteado que se escribieran antes de ver la figura.
Independencia: la serie independiente es NOAA-20 SOLO desde 2019-01-01 (NOAA-20 >= 2019 esta permitido por ADR-0005); NOAA-20
2018-04..2018-12 se excluye porque se solapa con la ventana de ajuste de la mascara (2012-2018).

Datos (data/processed/, SOLO lectura, con candado de memoria):
  deteccion_mexico.parquet   plataforma, type, en_mascara, en_serie, flag_nrt, lat/lon, acq_date_utc
  mascara_estatica_mexico.parquet   celdas de 0.01 grados de la mascara (lat100, lon100; huella 3x3)
  Fila-grupos (anti-fuga ADR-0005: NO se lee Terra, Aqua ni S-NPP >= 2019-01-01):
    * S-NPP    2012-01-20 .. 2018-12-31  -> en la ventana en que se construyo la mascara (DENTRO de muestra)
    * NOAA-20  en_serie, procesamiento estandar (sin NRT), acq_date_utc >= 2019-01-01 -> otro sensor, fuera de la ventana de ajuste
  Ventana: 61 x 61 celdas de 0.01 grados centradas en la celda del crater (la de mas type = 1).

Uso:
  flock data/.pesado.lock .venv/bin/python src/figuras/fig04_mascara.py --real     # consulta DuckDB + dibuja + manifiesto
  .venv/bin/python src/figuras/fig04_mascara.py                                     # redibuja desde figures/figdata/
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comun as K  # noqa: E402

FIG_ID = "FIG-04"
NOMBRE = "FIG-04_mask_before_after_popocatepetl"
FIGDATA = K.FIGURAS_DIR / "figdata" / f"{NOMBRE}.csv"
FIGDATA_MASC = K.FIGURAS_DIR / "figdata" / f"{NOMBRE}_footprint.csv"
PROC = K.RAIZ / "data" / "processed"
SEMI = 30                    # celdas de 0.01 grados a cada lado del crater (61 x 61)
UMBRAL_CRATER = 95.0         # % minimo de type=1 de NOAA-20 removido por la mascara (chequeo de coherencia del titulo)
UMBRAL_VEG = 5.0             # % maximo de type=0 de NOAA-20 removido
GRUPOS = [("snpp", "S-NPP", "S-NPP 2012-2018", "in-sample: the mask was fit here"),
          ("noaa20", "NOAA-20", "NOAA-20 2019-01 to 2026-07", "independent: other sensor, after the 2012-2018 fitting window")]
SQL_BASE = """
SELECT '{g}' AS grupo, floor(latitude*100)::INT AS lat100, floor(longitude*100)::INT AS lon100,
       count(*) AS n_all,
       count(*) FILTER (WHERE type = 0) AS n_t0, count(*) FILTER (WHERE type = 1) AS n_t1,
       count(*) FILTER (WHERE type IS NULL OR type NOT IN (0, 1)) AS n_otro,
       count(*) FILTER (WHERE en_mascara) AS n_mask,
       min(acq_date_utc) AS f_min, max(acq_date_utc) AS f_max
FROM '{det}'
WHERE {filtro}
  AND floor(latitude*100) BETWEEN {la0} AND {la1} AND floor(longitude*100) BETWEEN {lo0} AND {lo1}
GROUP BY 1, 2, 3
"""
FILTROS = {
    "snpp": "plataforma = 'S-NPP' AND acq_date_utc BETWEEN DATE '2012-01-20' AND DATE '2018-12-31'",
    "noaa20": "plataforma = 'NOAA-20' AND en_serie AND NOT flag_nrt AND acq_date_utc >= DATE '2019-01-01'",
}


def consultar() -> tuple[pd.DataFrame, pd.DataFrame, list[Path]]:
    import duckdb
    det, mas = PROC / "deteccion_mexico.parquet", PROC / "mascara_estatica_mexico.parquet"
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='600MB'; PRAGMA threads=2")
    # celda del crater = la de mas type = 1 en S-NPP dentro de la mascara (solo para centrar la vista)
    cl = con.execute(f"""SELECT floor(latitude*100)::INT, floor(longitude*100)::INT, count(*) c FROM '{det}'
                         WHERE plataforma='S-NPP' AND type=1 AND acq_date_utc BETWEEN DATE '2012-01-20' AND DATE '2018-12-31'
                         GROUP BY 1,2 ORDER BY c DESC LIMIT 1""").fetchone()
    la, lo = cl[0], cl[1]
    la0, la1, lo0, lo1 = la - SEMI, la + SEMI, lo - SEMI, lo + SEMI
    parts = []
    for g, _, _, _ in GRUPOS:
        parts.append(con.execute(SQL_BASE.format(g=g, det=det, filtro=FILTROS[g], la0=la0, la1=la1, lo0=lo0, lo1=lo1)).df())
    df = pd.concat(parts, ignore_index=True)
    f = con.execute(f"SELECT lat100, lon100, nucleo FROM '{mas}' WHERE lat100 BETWEEN {la0} AND {la1} AND lon100 BETWEEN {lo0} AND {lo1}").df()
    df["f_min"] = df["f_min"].astype(str); df["f_max"] = df["f_max"].astype(str)
    # anti-fuga: ningun grupo toca Terra/Aqua/S-NPP >= 2019
    assert df[df.grupo == "snpp"].f_max.max() <= "2018-12-31", "ANTI-FUGA fig04: S-NPP >= 2019 (ADR-0005)"
    assert df[df.grupo == "noaa20"].f_min.min() >= "2019-01-01", "fig04: NOAA-20 independiente debe empezar >= 2019-01-01"
    # coherencia: la bandera por deteccion coincide con la huella de la mascara; no hay celdas mixtas
    foot = set(zip(f.lat100, f.lon100))
    dentro = np.array([(a, b) in foot for a, b in zip(df.lat100, df.lon100)])
    assert ((df.n_mask > 0) == dentro).all() and ((df.n_mask == 0) | (df.n_mask == df.n_all)).all(), \
        "fig04: en_mascara no coincide con la huella de mascara_estatica o hay celdas mixtas"
    df["crater_lat100"], df["crater_lon100"] = la, lo
    FIGDATA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(FIGDATA, index=False)
    f.assign(crater_lat100=la, crater_lon100=lo).to_csv(FIGDATA_MASC, index=False)
    return df, f, [det, mas]


def rejilla(df: pd.DataFrame, la: int, lo: int, col: str) -> np.ndarray:
    n = 2 * SEMI + 1
    Z = np.zeros((n, n))
    np.add.at(Z, (df.lat100.values - (la - SEMI), df.lon100.values - (lo - SEMI)), df[col].values)
    return Z


def cifras(df: pd.DataFrame) -> dict:
    out = {}
    for g, _, _, _ in GRUPOS:
        d = df[df.grupo == g]
        t1, t0 = int(d.n_t1.sum()), int(d.n_t0.sum())
        t1m, t0m = int(d.loc[d.n_mask > 0, "n_t1"].sum()), int(d.loc[d.n_mask > 0, "n_t0"].sum())
        out[g] = dict(t1=t1, t1_quitado=t1m, t0=t0, t0_quitado=t0m, otro=int(d.n_otro.sum()), todo=int(d.n_all.sum()),
                      pct_t1=100 * t1m / t1 if t1 else float("nan"), pct_t0=100 * t0m / t0 if t0 else float("nan"),
                      f_min=d.f_min.min(), f_max=d.f_max.max())
    return out


def titulo_y_chequeo(c: dict) -> str:
    n = c["noaa20"]
    assert n["pct_t1"] >= UMBRAL_CRATER and n["pct_t0"] <= UMBRAL_VEG, (
        f"FIG-04: chequeo de coherencia no cumplido (crater removido {n['pct_t1']:.1f}% < {UMBRAL_CRATER}% o vegetacion {n['pct_t0']:.1f}% > "
        f"{UMBRAL_VEG}%): el titulo-afirmacion no se sostiene; reportar como resultado negativo")
    return "A volcano is not a wildfire: a mask fit on S-NPP also removes the crater in NOAA-20"


def dibujar(df: pd.DataFrame, foot: pd.DataFrame):
    la, lo = int(df.crater_lat100.iloc[0]), int(df.crater_lon100.iloc[0])
    n = 2 * SEMI + 1
    ext = [(lo - SEMI) / 100, (lo + SEMI + 1) / 100, (la - SEMI) / 100, (la + SEMI + 1) / 100]
    clat, clon = (la + 0.5) / 100, (lo + 0.5) / 100
    c = cifras(df)
    tit = titulo_y_chequeo(c)
    fig = K.nueva_figura()
    K.encabezado(fig, tit, f"Detections per 0.01-degree cell near Popocatepetl, Mexico ({K.UNIDADES}); log colour scale; "
                           "hatched = masked, not zero")
    K.etiqueta_exploratoria(fig, "EXPLORATORY\nmask fit 2012-2018")
    M = np.zeros((n, n))
    M[foot.lat100.values - (la - SEMI), foot.lon100.values - (lo - SEMI)] = 1
    tot_max = max(float(rejilla(df[df.grupo == g], la, lo, "n_all").max()) for g, *_ in GRUPOS)
    norm = LogNorm(vmin=1, vmax=max(tot_max, 2.0))
    cm = K.cmap_secuencial().copy()
    cm.set_bad("white")
    asp = 1.0 / np.cos(np.radians(clat))
    gsg = {"snpp": fig.add_gridspec(1, 2, left=0.055, right=0.44, top=0.70, bottom=0.30, wspace=0.12),
           "noaa20": fig.add_gridspec(1, 2, left=0.50, right=0.885, top=0.70, bottom=0.30, wspace=0.12)}
    cax = fig.add_axes([0.915, 0.30, 0.014, 0.40])
    xs = np.linspace(ext[0], ext[1], n + 1)[:-1] + 0.005
    ys = np.linspace(ext[2], ext[3], n + 1)[:-1] + 0.005
    im = None
    for g, plat, rot, sub in GRUPOS:
        Z = rejilla(df[df.grupo == g], la, lo, "n_all")
        for k in (0, 1):
            gi = k if g == 'snpp' else k + 2
            ax = fig.add_subplot(gsg[g][k])
            z = Z if k == 0 else np.where(M > 0, 0, Z)
            im = ax.imshow(np.ma.masked_where(z <= 0, z), origin="lower", extent=ext, cmap=cm, norm=norm, aspect=asp,
                           interpolation="nearest", zorder=2)
            if k == 1:
                ax.contourf(xs, ys, M, levels=[0.5, 1.5], colors="none", hatches=["xx"], zorder=3)
                ax.contour(xs, ys, M, levels=[0.5], colors="#000000", linewidths=1.8, zorder=4)
            ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.grid(False)
            for s in ("top", "right"):
                ax.spines[s].set_visible(True)
            ax.set_xticks([round(clon - 0.2, 1), round(clon + 0.2, 1)])
            ax.set_xticklabels([f"{abs(round(clon - 0.2, 1)):.1f}W", f"{abs(round(clon + 0.2, 1)):.1f}W"], fontsize=17)
            ax.set_yticks([round(clat - 0.2, 1), round(clat + 0.2, 1)])
            ax.set_yticklabels([f"{round(clat - 0.2, 1):.1f}N", f"{round(clat + 0.2, 1):.1f}N"] if gi == 0 else [], fontsize=17)
            ax.set_title("Before" if k == 0 else "After mask", loc="left", fontsize=19, fontweight="bold", color=K.TXT, pad=6)
            if k == 0:
                ax.annotate("crater cell", xy=(clon, clat), xytext=(clon - 0.20, clat + 0.21), fontsize=17, fontweight="bold",
                            arrowprops=dict(arrowstyle="-|>", lw=2.0, color="black"), zorder=7,
                            bbox=dict(fc="white", ec="none", pad=1.0, alpha=0.9))
            if k == 1 and g == "snpp":
                ax.legend(handles=[mpatches.Patch(fc="white", ec="black", hatch="xx", label="masked")], loc="lower left",
                          fontsize=16, frameon=True, framealpha=0.95, handlelength=1.2, borderpad=0.3)
        # cabecera de grupo y cifras calculadas
        x0 = 0.055 if g == "snpp" else 0.50
        cc = c[g]
        fig.text(x0, 0.775, f"{plat}, {rot.split(' ', 1)[1]}", fontsize=21, fontweight="bold",
                 color=K.C[plat], ha="left", va="center")
        fig.text(x0, 0.215, f"Crater: {cc['t1']:,} \u2192 {cc['t1'] - cc['t1_quitado']:,}  ({cc['pct_t1']:.0f}% removed)",
                 fontsize=18, fontweight="bold", color=K.TXT, ha="left", va="center")
        fig.text(x0, 0.172, f"Vegetation: {cc['t0']:,} \u2192 {cc['t0'] - cc['t0_quitado']:,}  ({cc['pct_t0']:.1f}% removed)",
                 fontsize=18, fontweight="bold", color=K.TXT, ha="left", va="center")
        fig.text(x0, 0.128, sub[0].upper() + sub[1:], fontsize=16, color=K.TXT2, ha="left", va="center")
    cb = fig.colorbar(im, cax=cax)
    cb.set_label("Detections per cell", fontsize=17)
    cb.ax.tick_params(labelsize=16)
    return fig, tit, c


def main(real: bool = False) -> list[Path]:
    if real:
        df, foot, entradas = consultar()
    else:
        assert FIGDATA.exists() and FIGDATA_MASC.exists(), "falta figures/figdata/ (corre --real con flock)"
        df, foot, entradas = pd.read_csv(FIGDATA), pd.read_csv(FIGDATA_MASC), None
    fig, tit, c = dibujar(df, foot)
    fuente = ("Data: NASA FIRMS VIIRS 375 m (S-NPP 2012-01 to 2018-12; NOAA-20 2019-01 to 2026-07, standard processing), Mexico, "
              "attribute type: 0 vegetation fire, 1 active volcano; static mask built from S-NPP 2012-2018 | analysis: this project")
    base = K.FIGURAS_DIR / NOMBRE
    salidas = K.cerrar(fig, base, fuente)
    if entradas is not None:
        K.escribir_manifiesto(
            base, FIG_ID, tit,
            origen={"experimento": "none (direct query of the series; mask from src/datos/tabla_analitica.py, ADR-0007 differentiator)",
                    "script_figura": "src/figuras/fig04_mascara.py",
                    "datos": "data/processed/deteccion_mexico.parquet (S-NPP 2012-01-20..2018-12-31; NOAA-20 en_serie, sin NRT, >= 2019-01-01); "
                             "data/processed/mascara_estatica_mexico.parquet",
                    "figdata": [str(FIGDATA.relative_to(K.RAIZ)), str(FIGDATA_MASC.relative_to(K.RAIZ))],
                    "chequeo_coherencia_titulo": f"(umbral no pre-registrado) NOAA-20: crater (type 1) removido >= {UMBRAL_CRATER}% y vegetacion (type 0) <= {UMBRAL_VEG}%"},
            comando="flock data/.pesado.lock .venv/bin/python src/figuras/fig04_mascara.py --real",
            entradas=entradas + [Path(__file__).resolve()], semilla=None,
            extra={"clm": "CLM-109 (hallazgo medido: efecto de la mascara en el crater del Popocatepetl; ledger: borrador al 2026-11-15, "
                          "necesita registrar las cifras de este manifiesto como EVD) + CLM-103 (metodo de la mascara, verificado). "
                          "Sigue EXPLORATORY (mascara ajustada en 2012-2018; no es resultado de la prueba unica); sin CLM-109 verificado no se cita la cifra.",
                   "cifras": c, "ventana": f"61x61 celdas de 0.01 grados centradas en la celda del crater",
                   "nota_dentro_de_muestra": "S-NPP 2012-2018 es la ventana de construccion de la mascara: 100 % de type=1 es por construccion; "
                                             "la evidencia independiente es NOAA-20",
                   "nota_type_otro": "type 2/3/ausente se cuentan aparte (n_otro) y no entran en las dos cifras del pie"})
    return salidas


if __name__ == "__main__":
    print(*main("--real" in sys.argv), sep="\n")
