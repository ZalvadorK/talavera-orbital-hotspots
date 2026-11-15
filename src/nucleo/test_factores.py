"""Minimal tests of the core contract (lane A).

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
The test data built here are SYNTHETIC (they are not observations).

Usage (reads data/processed -> with the lock):
  flock data/.pesado.lock .venv/bin/python -m pytest -q src/nucleo/test_factores.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factores as FA  # noqa: E402
import modelo as MO  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
HAY_DATOS = (RAIZ / "data/processed/factores_mexico.parquet").exists()


# ------------------------------------------------------------------------------------ SYNTHETIC
def F_sintetico() -> pd.DataFrame:
    """SYNTHETIC: made-up factors with round values to check the weighting logic."""
    filas = []
    for r, k in (("TA", 4.0), ("T", 9.0), ("A", 7.0)):
        for mes in range(1, 13):
            for tu in ("D", "N"):
                filas.append({"reloj": r, "mes": mes, "turno": tu, "celda1": "19_-99", "k": k, "s": 0.5,
                              "w": k * 0.5, "n_cal": 100})
    return pd.DataFrame(filas)


def disp_sintetica() -> pd.DataFrame:
    """SYNTHETIC: 4 days. 01 both; 02 Terra without data; 03 Terra only (Aqua has no row); 04 neither."""
    return pd.DataFrame([
        ("2016-02-01", "Terra", 10, 5, False, ""), ("2016-02-01", "Aqua", 12, 6, False, ""),
        ("2016-02-02", "Terra", 0, 0, True, "aviso_oficial"), ("2016-02-02", "Aqua", 30, 3, False, ""),
        ("2016-02-03", "Terra", 9, 1, False, ""),
        ("2016-02-04", "Terra", 0, 0, True, "aviso_oficial"), ("2016-02-04", "Aqua", 0, 0, True, "regla_datos"),
    ], columns=["fecha", "plataforma", "n_mx", "n_ar", "sin_datos", "fuente"])


def det_sintetica() -> pd.DataFrame:
    """SYNTHETIC: MODIS detections."""
    return pd.DataFrame({
        "plataforma": ["Terra", "Aqua", "Terra", "Aqua", "Terra", "Aqua", "Terra", "Aqua"],
        "acq_date_utc": ["2016-02-01", "2016-02-01", "2016-02-02", "2016-02-02", "2016-02-03", "2016-02-01",
                         "2016-02-04", "2016-02-04"],
        "mes": [2] * 8, "turno": ["D", "D", "D", "D", "N", "D", "D", "D"],
        "celda1": ["19_-99", "19_-99", "19_-99", "19_-99", "19_-99", "20_-100", "19_-99", "19_-99"],
    })


def test_pesos_dia_con_hueco_sintetico():
    w = FA.pesos_modis(det_sintetica(), F_sintetico(), disp_sintetica())
    esperado = [2.0, 2.0,      # day with both -> TA (4 x 0.5)
                0.0, 3.5,      # Terra without data -> Terra weighs 0, Aqua uses clock A (7 x 0.5)
                4.5,           # Terra only -> clock T (9 x 0.5)
                4.0,           # cell without its own factor -> s = 1 -> w = k(TA)
                np.nan, np.nan]  # day with neither -> NaN (incomplete month)
    np.testing.assert_allclose(w, esperado, equal_nan=True)


def test_pesos_fuera_de_cobertura():
    det = det_sintetica().assign(acq_date_utc="2016-03-01")
    with pytest.raises(ValueError):
        FA.pesos_modis(det, F_sintetico(), disp_sintetica())
    w = FA.pesos_modis(det, F_sintetico(), disp_sintetica(), fuera_cobertura="disponible")
    assert np.isfinite(w).all()


def test_pesos_rechaza_viirs():
    det = det_sintetica().assign(plataforma="S-NPP")
    with pytest.raises(ValueError):
        FA.pesos_modis(det, F_sintetico(), disp_sintetica())


def test_encogimiento_sintetico():
    """SYNTHETIC: with n0s=inf s=1; with a finite n0s, s lies between 1 and the raw ratio of the cell."""
    v = pd.DataFrame({"celda1": ["a", "a", "b", "b"], "turno": ["D"] * 4, "mes": [1, 2, 1, 2],
                      "anio": [2013] * 4, "S": [400.0, 400.0, 100.0, 100.0], "M": [100.0, 100.0, 100.0, 100.0]})
    aj = MO.ajustar(v, "TA", math.inf)
    assert np.allclose(aj.s(["a", "b"], ["D", "D"]), 1.0)
    aj = MO.ajustar(v, "TA", 10.0)
    sa, sb = aj.s(["a", "b"], ["D", "D"])
    assert 1.0 < sa < 1.6 and 0.4 < sb < 1.0     # k ~ 2.5 -> raw ratios 1.6 and 0.4


# ------------------------------------------------------------------------------------ anti-leak
def test_antifuga_factores():
    with pytest.raises(AssertionError):
        FA.factores("mexico", "2012-02-01", "2019-01-01")
    with pytest.raises(AssertionError):
        FA.factores("argentina", "2012-02-01", "2021-12-31")


def test_antifuga_agregados():
    import agregados as AG
    with pytest.raises(AssertionError):
        AG.calcular("mexico", "2012-02-01", "2019-06-30")


# ------------------------------------------------------------------------------------ contract with real data
@pytest.mark.skipif(not HAY_DATOS, reason="no generated factors")
@pytest.mark.parametrize("pais", ["mexico", "argentina"])
def test_contrato_factores(pais):
    F = FA.factores(pais, "2012-02-01", "2018-12-31")
    assert list(F.columns) == FA.COLUMNAS
    assert set(F["reloj"]) == {"TA", "T", "A"}
    assert set(F["mes"]) == set(range(1, 13)) and set(F["turno"]) == {"D", "N"}
    assert F["celda1"].str.fullmatch(r"-?\d+_-?\d+").all()
    assert np.allclose(F["w"], F["k"] * F["s"])
    assert (F["k"] > 0).all() and (F["s"] > 0).all() and (F["n_cal"] >= 0).all()
    # each (reloj, mes, turno) has a single k
    assert (F.groupby(["reloj", "mes", "turno"])["k"].nunique() == 1).all()
    pd.testing.assert_frame_equal(F, pd.read_parquet(RAIZ / f"data/processed/factores_{pais}.parquet")[FA.COLUMNAS])


@pytest.mark.skipif(not HAY_DATOS, reason="no generated intervals")
@pytest.mark.parametrize("pais", ["mexico", "argentina"])
def test_contrato_intervalo(pais):
    for tramo in ("TA", "T"):
        for nivel in ("1deg", "pais", "aoi"):
            lo, hi = FA.intervalo(pais, 100.0, tramo, nivel)
            assert 0 <= lo < 1 < hi < 10
    lo_ta, hi_ta = FA.intervalo(pais, 100.0, "TA", "1deg")
    lo_t, hi_t = FA.intervalo(pais, 100.0, "T", "1deg")
    assert hi_t / lo_t > hi_ta / lo_ta          # Terra only is wider
    assert FA.intervalo(pais, 0.0, "TA", "pais") == (0.0, math.inf)


@pytest.mark.skipif(not HAY_DATOS, reason="no data")
def test_disponibilidad():
    d = FA.disponibilidad("global")
    assert {"fecha", "plataforma", "sin_datos"} <= set(d.columns)
    assert pd.to_datetime(d["fecha"]).max() < pd.Timestamp("2019-01-01")
    assert "n" in FA.disponibilidad("mexico").columns


@pytest.mark.skipif(not HAY_DATOS, reason="no data")
def test_pesos_reales_feb2016_coinciden_con_agregado():
    """Per-detection weights (contract) summed = R1 prediction of the aggregate (Feb-2016 MX, with a Terra gap)."""
    import agregados as AG
    con = AG.conectar()
    det = con.execute(f"""SELECT plataforma, acq_date_utc, mes, turno, celda1
        FROM read_parquet('{AG.ruta_deteccion('mexico')}')
        WHERE en_calibracion AND NOT en_mascara AND procesamiento='estandar' AND plataforma IN ('Terra','Aqua')
          AND acq_date_utc BETWEEN DATE '2016-02-01' AND DATE '2016-02-29'""").df()
    con.close()
    F = FA.factores("mexico", "2012-02-01", "2018-12-31")
    w = FA.pesos_modis(det, F, FA.disponibilidad())
    assert np.isfinite(w).all()
    assert (w[(det["plataforma"] == "Terra").values & pd.to_datetime(det["acq_date_utc"]).dt.day.between(19, 27).values] == 0).all()
    ag = AG.calcular("mexico", "2012-02-01", "2018-12-31")
    ag = ag[ag["ym"] == "2016-02"]
    meta = FA.calibrar("mexico", "2012-02-01", "2018-12-31")["meta"]
    aj = {r: MO.ajustar(MO.vista_reloj(AG.calcular("mexico", "2012-02-01", "2018-12-31"), r), r, float(meta["n0s"]))
          for r in MO.RELOJES}
    assert abs(w.sum() - np.nansum(MO.predecir_r1(ag, aj))) / w.sum() < 1e-9
