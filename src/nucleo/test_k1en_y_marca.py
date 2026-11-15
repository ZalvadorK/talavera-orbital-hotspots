"""Tests for the K1-en rewrites (baseline, leak audit, trend, provenance), the exact 6c-q rule and S8 / I-05 helpers.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

Golden values were produced with the pre-event development toolkit on the same inputs (bit-identical; the
equivalence check over random inputs lives outside the product). Synthetic inputs only; no data file is read here
except config/validacion.yaml and the factor metadata (*.json) in test_leak_design.
Run:  flock data/.pesado.lock .venv/bin/python -m pytest -q -p no:cacheprovider src/nucleo
"""
from __future__ import annotations

import json
import math
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nucleo import validacion_marca as VM  # noqa: E402
from nucleo.baseline import apply_ratio, global_count_ratio  # noqa: E402
from nucleo.leak_audit import Partition, audit_design, audit_leak, temporal_partition  # noqa: E402
from nucleo.provenance import sha256_file, write_manifest  # noqa: E402
from nucleo.trend import pettitt, seasonal_sen_slope, sen_slope  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ baseline (M1)
def test_global_count_ratio_golden():
    g = global_count_ratio([5, 0, 12, 7, 30, 1, 0, 9], [1, 2, 3, 0, 6, 1, 1, 2], n_boot=500, seed=42)
    assert g == {"ratio": 4.0, "ci95": [1.8984848484848484, 5.7015625], "n": 8}


def test_global_count_ratio_deterministic_and_validated():
    a, b = np.arange(1, 40, dtype=float), np.arange(2, 41, dtype=float)
    assert global_count_ratio(a, b, 200, 7) == global_count_ratio(a, b, 200, 7)
    assert global_count_ratio(a, b, 200, 7)["ci95"][0] <= a.sum() / b.sum() <= global_count_ratio(a, b, 200, 7)["ci95"][1]
    with pytest.raises(ValueError):
        global_count_ratio([1, 2], [1, 2, 3])
    with pytest.raises(ValueError):
        global_count_ratio([], [])
    assert list(apply_ratio(2.5, [0, 2, 4])) == [0.0, 5.0, 10.0]


# ------------------------------------------------------------------ leak audit
def _df(n=24):
    return pd.DataFrame({"g": np.arange(n) % 6, "t": pd.date_range("2012-01-01", periods=n, freq="MS"), "v": np.arange(n)})


def test_audit_leak_clean_temporal():
    df = _df()
    p = temporal_partition(df, "t", ("2012-01-01", "2012-12-31"), ("2013-01-01", "2013-12-31"))
    rep = audit_leak(df, p, time_col="t")
    assert rep["ok"] and rep["findings"] == [] and rep["train"] == 12 and rep["test"] == 12


def test_audit_leak_blocking_findings():
    df = _df()
    p = Partition(np.arange(0, 14), np.arange(12, 24), None, "x")
    rep = audit_leak(df, p, group_col="g", time_col="t")
    assert not rep["ok"]
    kinds = [f.split(":")[0] for f in rep["findings"]]
    assert kinds.count("BLOCKING") == 3 and kinds.count("WARNING") == 1      # indices, identical rows, groups + overlap


def test_audit_leak_warning_only_is_ok():
    df = _df()
    p = Partition(np.array([0, 5]), np.array([3]), None, "x")
    rep = audit_leak(df, p, time_col="t")
    assert rep["ok"] and rep["findings"][0].startswith("WARNING")


HAY_FACTORES = (ROOT / "data/processed").is_dir() and any((ROOT / "data/processed").glob("factores_*_*.json"))


@pytest.mark.skipif(not HAY_FACTORES, reason="no data: data/processed missing or without factores_*_*.json metadata "
                                            "(empty factor_windows); as in test_factores (gate H4 D-N4)")
def test_leak_design_preregistered():
    rep = audit_design()
    assert rep["ok"], rep
    for c in rep["countries"].values():
        assert c["train"] == 83 and c["test"] == 36 and c["findings"] == []
    assert rep["factor_windows"] and all(w["ok"] for w in rep["factor_windows"].values())


# ------------------------------------------------------------------ trend
def test_pettitt_golden():
    p = pettitt([1, 2, 1.5, 2.2, 1.1, 5, 6, 5.5, 6.2, 5.1])
    assert (p["change_index"], p["K"], p["p"]) == (4, 25.0, 0.06614250297660204)
    assert p["mean_before"] == pytest.approx(1.56) and p["mean_after"] == pytest.approx(5.56)


def test_sen_slopes():
    assert sen_slope([0, 2, 4, 6, 100]) == 2.0
    yrs = np.repeat([2016, 2017, 2018], 12)
    mes = np.tile(np.arange(1, 13), 3)
    y = 10 * np.sin(mes) + 0.3 * (yrs - 2016)            # strong seasonality + 0.3/year trend
    s, n = seasonal_sen_slope(y, yrs, mes)
    assert s == pytest.approx(0.3) and n == 36
    y2 = y.copy()
    y2[0] = np.nan
    assert seasonal_sen_slope(y2, yrs, mes)[1] == 34
    assert math.isnan(seasonal_sen_slope([1.0], [2016], [1])[0])


# ------------------------------------------------------------------ provenance
def test_write_manifest(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    m = write_manifest(tmp_path / "run", 42, [f, tmp_path / "missing"], {"a": 1}, comando="cmd", extra={"k": "v"})
    d = json.loads(m.read_text())
    assert d["semilla"] == 42 and d["comando"] == "cmd" and d["k"] == "v" and d["config"] == {"a": 1}
    assert d["datos"] == [{"ruta": str(f), "mb": 0.0, "sha256": sha256_file(f)}]
    assert sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    with pytest.raises(TypeError):
        write_manifest(tmp_path / "r2", 1, desconocido=True)


# ------------------------------------------------------------------ exact rule 6c-q (gate B1)
B13 = [1, 6, 8, 10, 12, 15, 15, 20, 25, 30, 40, 60, 70]           # p10 = 3, p90 = 66 (exact), median 15
B14 = [2, 6, 8, 10, 12, 15, 15, 20, 25, 30, 40, 50, 60, 80]       # p10 = 4, p90 = 70, median 17.5


def test_exact_thresholds():
    u = VM.umbrales(B13)
    assert u["p10_x"] == Fraction(3) and u["p90_x"] == Fraction(66) and u["mediana_x"] == Fraction(15)
    assert u["p10"] == 3.0 and VM.cuantil_t6(B13, 0.1) == 3.0      # float 14*0.1 = 1.4000000000000001 no longer leaks
    assert VM.umbrales(B14)["p10_x"] == 4 and VM.umbrales(B14)["p90_x"] == 70 and VM.umbrales(B14)["mediana_x"] == Fraction(35, 2)


@pytest.mark.parametrize("base,valor,estado,direccion", [
    (B13, 3.0, VM.TYPICAL, None), (B13, 66.0, VM.TYPICAL, None), (B13, 2.0, VM.UNUSUAL, VM.LOW), (B13, 67.0, VM.UNUSUAL, VM.HIGH),
    (B14, 4.0, VM.TYPICAL, None), (B14, 70.0, VM.TYPICAL, None), (B14, 3.999999, VM.UNUSUAL, VM.LOW), (B14, 70.000001, VM.UNUSUAL, VM.HIGH),
])
def test_exact_ties(base, valor, estado, direccion):
    m = VM.marca(valor, base)
    assert (m["estado"], m["direccion"]) == (estado, direccion)


def test_exact_ties_interval_and_season():
    assert VM.marca(10, B13, lo=3, hi=20)["estado"] == VM.TYPICAL
    assert VM.marca(70, B13, lo=66, hi=80)["estado"] == VM.POSSIBLY
    assert VM.marca(100, B13, lo=70, hi=math.inf)["estado"] == VM.UNUSUAL
    t = VM.temporada_inusual(66.0, B13)
    assert t["inusual"] is False and not any(k.endswith("_x") for k in t)
    assert VM.temporada_inusual(66.0000001, B13)["inusual"] is True
    assert not any(k.endswith("_x") for k in VM.marca(3, B13))


def test_median_exactly_five_is_sufficient():
    assert VM.marca(100.0, [0, 1, 2, 5, 6, 8, 9])["estado"] == VM.UNUSUAL
    assert VM.marca(100.0, [0, 1, 2, 4, 6, 8, 9])["estado"] == VM.INSUFFICIENT


# ------------------------------------------------------------------ S8 and I-05 helpers (validacion_rt05)
@pytest.fixture(scope="module")
def V():
    import importlib
    return importlib.import_module("nucleo.validacion_rt05")


def test_count_classes(V):
    assert V.etiquetas_clase([10, 30, 100]) == ["<10", "10-30", "30-100", ">=100"]
    assert list(V.clase_de([0, 9.99, 10, 29.5, 30, 99, 100, 1e6], [10, 30, 100])) == [0, 0, 1, 1, 2, 2, 3, 3]


def test_expected_count_median_with_zeros(V):
    cal = pd.DataFrame({"plataforma": ["Terra", "Aqua", "Terra", "Aqua", "S-NPP"], "anio": [2016, 2016, 2016, 2017, 2016],
                        "mes": [1, 1, 2, 1, 1], "celda1": ["19_-98"] * 5, "n": [4, 6, 3, 20, 99]})
    meses = [(2016, 1), (2016, 2), (2016, 3), (2017, 1), (2017, 2)]
    e = V.conteo_esperado(cal, cal.celda1, meses, set(), "TA")
    assert e.loc["19_-98"] == 3.0                                       # monthly T+A = [10, 3, 0, 20, 0] -> median 3
    assert V.conteo_esperado(cal, cal.celda1, meses, {(2016, 3), (2017, 2)}, "TA").loc["19_-98"] == 10.0
    assert V.conteo_esperado(cal, cal.celda1, meses, set(), "T").loc["19_-98"] == 0.0


def test_s8_reports_known_slopes(V):
    filas = []
    for b, tr_s, tr_h in (("6_-33", 0.10, 0.10), ("6_-32", 0.20, 0.0)):
        for y in (2016, 2017, 2018):
            for m in range(1, 13):
                lvl = 50 + 30 * math.sin(m)
                filas.append({"bloque": b, "anio": y, "mes": m, "excluido": False, "testigo_ok": False,
                              "S": math.exp(math.log(lvl + 1) + tr_s * (y - 2016)) - 1,
                              "H_TA": math.exp(math.log(lvl + 1) + tr_h * (y - 2016)) - 1, "W": 0.0})
    B = pd.DataFrame(filas)
    B["M1"] = B["H_TA"]
    B["M0"] = B["H_TA"] / 5
    cfg = {"pseudoconteo_log": 1, "n_boot": 50, "s8": {"min_pares_por_bloque": 6, "poblacion": "p2"}}
    out = V.prueba_S8(B, np.ones(len(B), bool), {"objetivo": "S-NPP", "testigo": "NOAA-20"}, cfg, np.random.default_rng(1))
    assert out["decide"] is False and out["n_bloques"] == 2
    assert out["por_bloque"]["6_-33"]["objetivo"] == pytest.approx(0.10, abs=1e-4)
    assert out["por_bloque"]["6_-32"]["H_TA"] == pytest.approx(0.0, abs=1e-4)
    assert out["diferencia_objetivo_menos_H_TA"]["mediana_bloques"] == pytest.approx(0.10, abs=1e-3)
    assert out["techo_gemelos"]["n_bloques"] == 0


def test_config_s8_and_i05_preregistered_state():
    import yaml
    cfg = yaml.safe_load((ROOT / "config/validacion.yaml").read_text(encoding="utf-8"))
    assert cfg["pruebas"]["S8"] == "run" and cfg["s8"]["decide"] is False         # ADR-0012 option 2
    assert cfg["pruebas"]["clases_I05"] == "run"                                  # lot 3 point 9 (Salvador, 15-Nov)
    assert cfg["umbrales"]["M1"]["min_modis_por_mes"] == 10
    assert cfg["i05"]["cortes_conteo_modis"] == [10, 30, 100]
