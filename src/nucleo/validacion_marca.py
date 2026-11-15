""""Unusual" flag U1 + I2 with the EXACT 6c-q rule of ADR-0006 (+ "unusual season", U-season).

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

This is the Python reference of the rule the app implements in JS (parity test: tests/paridad_marca.json).
The single test (src/nucleo/validacion_rt05.py) uses the same function. Nothing here reads data.

Rule 6c-q (ADR-0006), to the letter:
  1. TYPE 6 quantile (Hyndman-Fan; Weibull): position h = (N+1)*p over the sorted base x_1 <= ... <= x_N,
     CLAMPED to the minimum and maximum:  h <= 1 -> x_1 ;  h >= N -> x_N ;  otherwise j = floor(h), g = h - j,
     q = x_j + g*(x_{j+1} - x_j).
     EXACTNESS (blocking item B1 of gate O-2; same as app/js/marca.js): EVERY decision (value > p90, value < p10,
     p10 > 0, median >= 5, season) is taken with the exact RATIONAL threshold (fractions.Fraction, p = 1/10, 1/2, 9/10
     and the exact binary value of each datum), never with its floating-point approximation. Example the float gets
     wrong: N = 13, (N+1)*0.1 = 1.4000000000000001, so a value EQUAL to the exact p10 came out "unusually low".
     The p10/median/p90 that are RETURNED (tooltip, JSON) are floats (the float closest to the exact rational);
     they are not used to decide. The internal *_x keys (Fraction) are not serialised.
     p90 and p10 of the SAME CALENDAR MONTH in the base, WITHOUT the evaluated year (guaranteed by whoever builds the base).
  2. STRICT inequality: high if value > p90; low if value < p10. Equal to the threshold is not flagged.
  3. "Unusually low" only if p10 > 0.
  4. "Base >= 5" = the MEDIAN (type 6 quantile with p = 0.5) of the same month in the base is >= 5; otherwise
     "insufficient data".
  I2 (harmonisation uncertainty): the rule is evaluated at BOTH ends of the IC80 (of the month's era):
     unusual            if both ends meet the rule (in the same direction);
     typical            if neither meets it;
     possibly_unusual   otherwise.
     Observed VIIRS months: no interval (lo = hi = value).
  RT-09 text: ratio to the median, "2.3× the <base> median" (1 decimal, half-up rounding of the exact binary,
     same as JS Number.prototype.toFixed).
  Unusual season (U-season): the fire-year cumulative up to day D exceeds (strictly) the type 6 p90 of the base
     cumulatives on the same day. ADR-0006 sets no minimum base for this flag: none is applied
     (optional parameter `mediana_minima`, None by default = the ADR rule as written).

Returned dict keys (estado = state, direccion = direction, mediana = median, razon_mediana = ratio to the median,
inusual = unusual) are part of the JSON contract with the app and are kept as they are.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Iterable, Sequence

P_ALTO = 0.9
P_BAJO = 0.1
MEDIANA_MINIMA = 5.0

# States (the names are a contract with the app; in English because they are public interface).
INSUFFICIENT = "insufficient"
INCOMPLETE = "incomplete"
UNUSUAL = "unusual"
POSSIBLY = "possibly_unusual"
TYPICAL = "typical"
HIGH, LOW, NONE = "high", "low", "none"


def _limpia(base: Iterable[float]) -> list[float]:
    """Base as a sorted list of finite floats. A non-finite value in the base is an error of whoever builds it."""
    xs = [float(v) for v in base]
    if any(not math.isfinite(v) for v in xs):
        raise ValueError("the base contains NaN/inf: incomplete months do not enter the base")
    return sorted(xs)


def _p_racional(p) -> Fraction:
    """p as a short rational (0.1 -> 1/10, 0.9 -> 9/10, 0.5 -> 1/2), NOT the binary value of 0.1."""
    return p if isinstance(p, Fraction) else Fraction(p).limit_denominator(1000)


def cuantil_t6_exacto(base_ordenada: Sequence[float], p) -> Fraction | None:
    """Clamped type 6 quantile, EXACT (Fraction), over an ALREADY SORTED finite base. None if it is empty."""
    x = base_ordenada
    n = len(x)
    if n == 0:
        return None
    h = (n + 1) * _p_racional(p)
    if h <= 1:
        return Fraction(x[0])
    if h >= n:
        return Fraction(x[n - 1])
    j = math.floor(h)
    g = h - j
    return Fraction(x[j - 1]) + g * (Fraction(x[j]) - Fraction(x[j - 1]))


def cuantil_t6(base: Iterable[float], p: float) -> float:
    """Clamped type 6 quantile (ADR-0006 6c-q, step 1), as a float (the closest to the exact one). NaN if the base is empty."""
    q = cuantil_t6_exacto(_limpia(base), p)
    return float("nan") if q is None else float(q)


def umbrales(base: Iterable[float]) -> dict:
    """Type 6 p10, median and p90 of the base (floats for reporting), N, and the exact *_x (Fraction) for deciding."""
    x = _limpia(base)
    q10, q50, q90 = (cuantil_t6_exacto(x, p) for p in (Fraction(1, 10), Fraction(1, 2), Fraction(9, 10)))
    f = lambda q: float("nan") if q is None else float(q)  # noqa: E731
    return {"n": len(x), "p10": f(q10), "mediana": f(q50), "p90": f(q90), "p10_x": q10, "mediana_x": q50, "p90_x": q90}


def publico(u: dict) -> dict:
    """Thresholds without the internal exact keys (*_x), for serialising."""
    return {k: v for k, v in u.items() if not k.endswith("_x")}


def base_suficiente(u: dict) -> bool:
    """Step 4: median of the same month in the base >= 5 (and a non-empty base). Exact comparison."""
    return u["n"] > 0 and u["mediana_x"] is not None and u["mediana_x"] >= MEDIANA_MINIMA


def regla_u1(valor: float, u: dict) -> str:
    """U1 on a value (steps 2 and 3) with thresholds already computed and a sufficient base. Returns high | low | none.

    EXACT float <-> Fraction comparison (Python compares the exact binary value of the float with the rational; +-inf
    and NaN behave as in float: inf > p90, NaN meets nothing)."""
    v = float(valor)
    if v > u["p90_x"]:
        return HIGH
    if u["p10_x"] > 0 and v < u["p10_x"]:
        return LOW
    return NONE


def marca(valor: float, base: Sequence[float], lo: float | None = None, hi: float | None = None) -> dict:
    """U1 + I2 flag of one month (AOI or spatial unit) against the base of the same calendar month without the evaluated year.

    valor   : value of the month (observed VIIRS or harmonised VIIRS-eq). NaN -> "incomplete".
    lo, hi  : ends of the IC80 of the harmonised value; None -> observed month (lo = hi = value).
    Returns {estado, direccion, u1, u1_lo, u1_hi, p10, mediana, p90, n, razon_mediana}.
    """
    u = umbrales(base)
    out = {"p10": u["p10"], "mediana": u["mediana"], "p90": u["p90"], "n": u["n"], "razon_mediana": razon_mediana(valor, u["mediana"])}
    if valor is None or not math.isfinite(float(valor)):
        return {**out, "estado": INCOMPLETE, "direccion": None, "u1": None, "u1_lo": None, "u1_hi": None}
    if not base_suficiente(u):
        return {**out, "estado": INSUFFICIENT, "direccion": None, "u1": None, "u1_lo": None, "u1_hi": None}
    v = float(valor)
    lo_v = v if lo is None else float(lo)
    hi_v = v if hi is None else float(hi)
    if lo_v > hi_v:
        raise ValueError("lo > hi")
    e_v, e_lo, e_hi = regla_u1(v, u), regla_u1(lo_v, u), regla_u1(hi_v, u)
    if e_lo == e_hi and e_lo != NONE:
        estado, direccion = UNUSUAL, e_lo
    elif e_lo == NONE and e_hi == NONE:
        estado, direccion = TYPICAL, None
    else:
        estado = POSSIBLY
        flags = {e for e in (e_lo, e_hi) if e != NONE}
        direccion = flags.pop() if len(flags) == 1 else "both"
    return {**out, "estado": estado, "direccion": direccion, "u1": e_v, "u1_lo": e_lo, "u1_hi": e_hi}


def razon_mediana(valor: float, mediana: float) -> float | None:
    """value / base median (RT-09). None if the median is not > 0 or the value is not finite."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or not (isinstance(mediana, (int, float)) and math.isfinite(mediana)) or mediana <= 0:
        return None
    return v / mediana


def texto_razon(valor: float, mediana: float, nombre_base: str) -> str | None:
    """"2.3× the <base> median" with 1 decimal and half-up rounding of the exact binary value (= JS toFixed(1))."""
    r = razon_mediana(valor, mediana)
    if r is None:
        return None
    s = str(Decimal(r).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return f"{s}× the {nombre_base} median"


def temporada_inusual(acumulado: float, acumulados_base: Sequence[float], mediana_minima: float | None = None) -> dict:
    """U-season: fire-year cumulative up to day D > type 6 p90 of the base cumulatives on the same day (strict)."""
    u = umbrales(acumulados_base)
    if u["n"] == 0 or (mediana_minima is not None and u["mediana_x"] < mediana_minima):
        return {"inusual": None, "estado": INSUFFICIENT, **publico(u)}
    v = float(acumulado)
    if not math.isfinite(v):
        return {"inusual": None, "estado": INCOMPLETE, **publico(u)}
    alto = bool(v > u["p90_x"])        # exact, strict
    return {"inusual": alto, "estado": UNUSUAL if alto else TYPICAL, **publico(u)}


def inicio_anio_fuego(medianas_mensuales: Sequence[float]) -> int:
    """ADR-0010 6b: the fire year starts the month after the climatological minimum (1-12; tie -> first minimum)."""
    m = list(medianas_mensuales)
    if len(m) != 12:
        raise ValueError("12 monthly medians are expected")
    i = min(range(12), key=lambda k: (m[k], k))
    return (i + 1) % 12 + 1


def es_marcado(m: dict) -> str:
    """3-class categorical U1 flag for kappa (high | low | none); None if insufficient/incomplete."""
    if m["estado"] in (INSUFFICIENT, INCOMPLETE):
        return None
    return m["u1"]


if __name__ == "__main__":  # minimal self-check
    assert cuantil_t6([1, 2, 3, 4, 5, 6, 7], 0.9) == 7 and cuantil_t6([1, 2, 3, 4, 5, 6, 7], 0.1) == 1
    xs = list(range(1, 14))
    assert abs(cuantil_t6(xs, 0.9) - 12.6) < 1e-12 and abs(cuantil_t6(xs, 0.1) - 1.4) < 1e-12
    assert cuantil_t6([3, 1, 2, 4], 0.5) == 2.5
    assert marca(7, [1, 2, 3, 4, 5, 6, 7])["estado"] == INSUFFICIENT          # median 4 < 5
    assert marca(70, [10, 20, 30, 40, 50, 60, 70])["estado"] == TYPICAL       # equal to p90: not flagged
    assert marca(71, [10, 20, 30, 40, 50, 60, 70])["direccion"] == HIGH
    assert marca(9, [0, 0, 10, 20, 30, 40, 50])["estado"] == TYPICAL         # p10 = 0: no low flag
    assert marca(60, [10, 20, 30, 40, 50, 60, 70], lo=30, hi=90)["estado"] == POSSIBLY
    assert texto_razon(4.5, 2, "2012–2025") == "2.3× the 2012–2025 median"   # 2.25 -> 2.3 (half-up, like JS)
    assert inicio_anio_fuego([5, 4, 3, 2, 1, 0, 1, 2, 3, 4, 5, 6]) == 7
    b13 = [1, 6, 8, 10, 12, 15, 15, 20, 25, 30, 40, 60, 70]            # exact p10 = 1 + 0.4*5 = 3; p90 = 60 + 0.6*10 = 66
    assert marca(3, b13)["estado"] == TYPICAL and marca(66, b13)["estado"] == TYPICAL   # exact ties: not flagged
    assert marca(2.999999, b13)["direccion"] == LOW and marca(66.000001, b13)["direccion"] == HIGH
    print("validacion_marca: OK")
