#!/usr/bin/env python3
"""Genera figures/paleta.json: tokens de color aptos para daltonismo (app y figuras).

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Uso:  .venv/bin/python src/figuras/paleta.py
No lee datos. Calcula (a) contraste WCAG texto/relleno y (b) distancia minima CIELAB (dE76)
entre colores de una misma familia bajo simulacion de protanopia/deuteranopia/tritanopia
(Machado et al. 2009, severidad 1.0), y la guarda en el JSON para auditoria.

Reglas: nada se comunica solo por color; cada estado lleva ademas trama (hatch) y etiqueta.
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
from matplotlib import colormaps
from matplotlib.colors import to_hex, to_rgb

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "figures" / "paleta.json"

# --- Entidades (mismo color en todas las figuras y en la app; regla 6) -------------------------
ENTIDADES = {
    "Terra": "#D55E00",            # Okabe-Ito vermillion
    "Aqua": "#56B4E9",             # Okabe-Ito sky blue
    "S-NPP": "#009E73",            # Okabe-Ito bluish green
    "NOAA-20": "#0072B2",          # Okabe-Ito blue
    "VIIRS-equivalent": "#000000",  # serie armonizada
    "unharmonized_M0": "#8C8C8C",   # control sin armonizar
    "baseline_M1": "#E69F00",       # razon_conteos (Okabe-Ito orange)
}
PAISES = {"Mexico": "#CC79A7", "Argentina": "#332288"}  # Okabe-Ito reddish purple; Tol indigo
TURNOS = {"day": "#E69F00", "night": "#4D4D4D"}          # naranja; gris oscuro (+ linea discontinua)
PRUEBAS = {"native": "#000000", "T1_all_parameters": "#AA4499", "T2_shape_only": "#999933"}

# --- Estados del calendario --------------------------------------------------------------------
# relleno, borde, trama, color del texto, etiqueta publica (ingles), nota de uso.
ESTADOS = {
    "unusual_high": ("#D55E00", "#7A3600", "", "#FFFFFF", "Unusually high", "Ambos extremos del IC80 > p90 (ADR-0006)"),
    "unusual_low": ("#0072B2", "#00334F", "", "#FFFFFF", "Unusually low", "Ambos extremos < p10 y p10 > 0"),
    "possibly_unusual": ("#F6D2B0", "#D55E00", "///", "#1A1A1A", "Possibly unusual", "Solo un extremo del IC80 cumple la regla"),
    "typical": ("#CFCFCF", "#8C8C8C", "", "#1A1A1A", "Typical", "Ningun extremo cumple la regla"),
    "no_data": ("#FFFFFF", "#6B6B6B", "xx", "#1A1A1A", "No data", "Plataforma sin datos: NO es cero"),
    "insufficient": ("#F5F5F5", "#B0B0B0", "..", "#1A1A1A", "Insufficient data", "Mediana base < 5 (6a)"),
}
# Capas superpuestas (se combinan con cualquier estado; no sustituyen su relleno)
SUPERPUESTOS = {
    "provisional": {"borde": "#CC79A7", "estilo_borde": "dashed", "grosor_px": 3, "trama": "",
                    "etiqueta": "Provisional (NRT)", "nota": "Cola NRT desde ago-2026; FIRMS la reemplaza"},
    "estimated": {"borde": "#000000", "estilo_borde": "solid", "grosor_px": 1, "trama": "\\\\\\",
                  "etiqueta": "Estimated (from MODIS)", "nota": "Era Terra / Terra+Aqua; lleva intervalo"},
    "incomplete": {"borde": "#000000", "estilo_borde": "dotted", "grosor_px": 2, "trama": "++",
                   "etiqueta": "Incomplete month", "nota": "T-16: hueco de plataforma"},
    "lower_confidence": {"borde": "#000000", "estilo_borde": "dashdot", "grosor_px": 2, "trama": "",
                         "etiqueta": "Lower confidence (indicative)", "nota": "Era Terra sola dic-2000 a jun-2002"},
}

FONDO = "#FFFFFF"
TEXTO = "#1A1A1A"
TEXTO_SECUNDARIO = "#4D4D4D"
REJILLA = "#D9D9D9"


# --- Utilidades de color -----------------------------------------------------------------------
def _lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _luminancia(hex_):
    r, g, b = _lin(to_rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    hi, lo = max(la, lb), min(la, lb)
    return float((hi + 0.05) / (lo + 0.05))


def _lab(rgb_lin):
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = m @ rgb_lin / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


_CVD = {
    "protanopia": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]),
    "deuteranopia": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]]),
    "tritanopia": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]),
    "normal": np.eye(3),
}


def _simular(hex_, tipo):
    lin = _lin(to_rgb(hex_))
    return np.clip(_CVD[tipo] @ lin, 0, 1)


def min_de(colores: dict[str, str]) -> dict:
    """Menor dE76 entre pares, por tipo de vision; devuelve el par mas cercano."""
    out = {}
    for tipo in _CVD:
        mejor = (1e9, None)
        for (na, ca), (nb, cb) in combinations(colores.items(), 2):
            d = float(np.linalg.norm(_lab(_simular(ca, tipo)) - _lab(_simular(cb, tipo))))
            if d < mejor[0]:
                mejor = (d, f"{na}~{nb}")
        out[tipo] = {"min_dE76": round(mejor[0], 1), "par": mejor[1]}
    return out


def rampa(nombre: str, n: int, a: float = 0.0, b: float = 1.0) -> list[str]:
    cm = colormaps[nombre]
    return [to_hex(cm(x)) for x in np.linspace(a, b, n)]


def construir() -> dict:
    sec = rampa("cividis", 9)                    # conteos (perceptual uniforme, apta para CVD)
    div = rampa("RdBu_r", 11)                    # anomalias: azul (menos) - blanco (0) - rojo (mas)
    estados = {}
    for k, (fill, edge, hatch, txt, etiqueta, nota) in ESTADOS.items():
        estados[k] = {"relleno": fill, "borde": edge, "trama": hatch, "texto": txt, "etiqueta": etiqueta,
                      "nota": nota, "contraste_texto": round(contraste(txt, fill), 2)}
    fam_estados = {k: v[0] for k, v in ESTADOS.items() if k not in ("no_data",)}
    pal = {
        "version": 1,
        "generado_por": "src/figuras/paleta.py",
        "marca_si": "SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.",
        "principios": [
            "Nada se comunica solo por color: cada estado lleva trama y etiqueta.",
            "Secuencial = conteos (cividis, 0 = claro). Divergente = anomalias, centrado en 0 (RdBu_r).",
            "Misma entidad, mismo color en figuras y app.",
            "No data se dibuja con trama 'xx' sobre blanco: nunca como un cero.",
        ],
        "fondo": FONDO, "texto": TEXTO, "texto_secundario": TEXTO_SECUNDARIO, "rejilla": REJILLA,
        "categorica_okabe_ito": ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"],
        "entidades": ENTIDADES,
        "paises": PAISES,
        "turnos": {"colores": TURNOS, "linea": {"day": "solid", "night": "dashed"}},
        "pruebas": PRUEBAS,
        "secuencial": {
            "uso": "conteos de hotspot detections (mapas de calor, calendario); usar escala log si hay ordenes de magnitud",
            "base": "matplotlib cividis", "stops": sec, "sin_datos": "#FFFFFF",
        },
        "divergente": {
            "uso": "anomalias y razones a la mediana; centro = 0 (o 1 en razon, en log). Simetrico: vmin = -vmax",
            "base": "matplotlib RdBu_r (ColorBrewer RdBu)", "stops": div, "centro": div[5],
        },
        "estados": estados,
        "superpuestos": SUPERPUESTOS,
        "auditoria_daltonismo": {
            "metodo": "Machado et al. 2009, severidad 1.0, dE76 en CIELAB; menor distancia entre pares de la familia",
            "umbral_recomendado_dE76": 10,
            "entidades": min_de(ENTIDADES),
            "paises_y_turnos": min_de({**{f"pais_{k}": v for k, v in PAISES.items()}, **{f"turno_{k}": v for k, v in TURNOS.items()}}),
            "estados_rellenos": min_de(fam_estados),
            "nota": "Los pares con dE bajo se distinguen ademas por trama, estilo de linea o marcador (regla 'no solo color').",
        },
    }
    return pal


def main() -> None:
    pal = construir()
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(pal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("escrito", SALIDA)
    for fam, r in pal["auditoria_daltonismo"].items():
        if isinstance(r, dict) and "normal" in r:
            print(fam, {t: (v["min_dE76"], v["par"]) for t, v in r.items()})


if __name__ == "__main__":
    main()
