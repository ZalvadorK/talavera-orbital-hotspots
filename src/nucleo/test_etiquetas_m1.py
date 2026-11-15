"""Tests for the lot-3 decision in the core: rule M1 ('too_few_modis', never 'reliable'), the I-05 class verdict, the
Terra-only era (always 'indicative', even if P5 passes), both P3 coverages in the verdict, and the frozen YAML values.

SI-generated (AI): Claude Code wrote this during the event (15-Nov ~14:00 Puebla); reviewed by the team.
All verdict inputs here are SYNTHETIC dictionaries (no data file is read except config/validacion.yaml). No hashes are
registered and no test run is started.
Modified 15-Nov ~14:30 Puebla by Claude Code (SI-generated): gate B-G1 option A - rule 3b also applies with clases_I05 run.
Run:  flock data/.pesado.lock .venv/bin/python -m pytest -q -p no:cacheprovider src/nucleo
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nucleo import validacion_rt05 as V  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REAL_CFG = yaml.safe_load((ROOT / "config/validacion.yaml").read_text(encoding="utf-8"))
U = REAL_CFG["umbrales"]
CORTES = [10, 30, 100]


# ------------------------------------------------------------------ frozen config = lot-3 decision (Salvador, 15-Nov)
def test_yaml_thresholds_are_table_4_3_unchanged():
    """Lot 3 point 5: the 7c thresholds of D2-S-07 table 4.3, unchanged; 7c-bis cap 0.50; none null."""
    assert U["P2"] == {"kappa_min": 0.60, "cociente_gemelos_min": 0.75, "escala": "bloque3"}
    assert U["P2b"] == {"precision_unusual_min": 0.80, "precision_typical_min": 0.95,
                        "cobertura_ic80_bloque": [0.75, 0.85], "indeterminado_max": 0.50}
    assert U["P3"] == {"cobertura": [0.75, 0.85]}
    assert U["P4"] == {"skill_ic95_inferior_mayor_que": 0.0}
    assert U["J1"] == {"media_abs_max": 0.10, "ic95_dentro_de": 0.15, "anio_abs_max": 0.15}
    assert U["J2_bloque"] == {"media_abs_max": 0.05}
    assert U["T"] == {"log_sesgo_abs_max": 0.10, "G_max": 1.15, "delta_kappa_min": -0.05}
    assert V.pendientes(REAL_CFG) == []


def test_yaml_rules_of_lot3():
    assert REAL_CFG["p3"]["poblacion"] == "excluye_s0"
    assert REAL_CFG["marca"]["kappa"] == "u1_3clases"
    assert REAL_CFG["j1"] == {"ventana": ["2003-01-01", "2011-12-31"], "excluir_meses_con_hueco_terra": True}
    assert REAL_CFG["meses_excluidos_huecos_viirs"] == []          # verified list (FIRMS missing_data, 0 days in W2)
    assert REAL_CFG["modos"]["desarrollo"]["calibracion"][0] == REAL_CFG["modos"]["prueba"]["calibracion"][0] == "2012-02-01"
    assert REAL_CFG["pruebas"]["S8"] == "run" and REAL_CFG["s8"]["decide"] is False
    assert REAL_CFG["pruebas"]["E1b"] == "run"


# ------------------------------------------------------------------ M1 helpers
def test_min_modis_per_era_and_threshold():
    assert V.min_modis_por_mes(U, "TA") == 10.0 and V.min_modis_por_mes(U, "T") == 10.0
    assert V.min_modis_por_mes({"M1": {"min_modis_por_mes": {"TA": 10, "T": 6}}}, "T") == 6.0
    assert V.min_modis_por_mes({}, "TA") is None
    assert V.demasiado_pocos(9.5, 10.0) is True and V.demasiado_pocos(10, 10.0) is False
    assert V.demasiado_pocos(None, 10.0) is None and V.demasiado_pocos(5, None) is None


def test_clase_m1_positions():
    assert [V.clase_M1(k, CORTES, 10) for k in range(4)] == ["too_few", "ok", "ok", "ok"]
    assert [V.clase_M1(k, CORTES, 15) for k in range(4)] == ["too_few", "straddles", "ok", "ok"]
    assert V.clase_M1(0, CORTES, None) is None


# ------------------------------------------------------------------ I-05 verdict applies M1
def _i05_clase(kc=0.7, coc=0.9, pu=0.9, pt=0.97, cob=0.8, ind=0.3):
    return {"kappa_cruzado": {"punto": kc}, "cociente_pareado": {"punto": coc},
            "P2b": {"precision_unusual": pu, "precision_typical": pt, "cobertura_ic80": cob, "pct_indeterminado": ind}}


def _res_i05(**over):
    clases = {"<10": _i05_clase(), "10-30": _i05_clase(), "30-100": _i05_clase(ind=0.6), ">=100": _i05_clase()}
    clases.update(over)
    return {"paises": {"mexico": {"E1c": {"clases_I05": {"modo": "run", "cortes_conteo_modis": CORTES,
                                                           "resultados": {"juntas": clases}}}}}}


def test_i05_class_below_m1_is_too_few_even_if_it_passes():
    v = V.veredicto(_res_i05(), REAL_CFG, "desarrollo")
    c = v["por_pais"]["mexico"]["clases_I05"]["juntas"]
    assert c["<10"]["P2"] is True and c["<10"]["P2b"] is True                 # it would pass ...
    assert c["<10"]["reliable"] is False and c["<10"]["etiqueta"] == V.TOO_FEW  # ... but rule M1 forbids 'reliable'
    assert c["10-30"]["reliable"] is True and c["10-30"]["etiqueta"] == V.RELIABLE
    assert c["30-100"]["P2b"] is False and c["30-100"]["etiqueta"] == V.INDICATIVE   # 7c-bis cap 0.50
    assert v["M1"]["min_modis_por_mes"] == 10 and v["M1"]["etiqueta"] == V.TOO_FEW
    assert v["regla_etiqueta"].startswith("I-05 rule 3b + count classes")
    assert v["umbrales_fijados"] is True and "aviso" not in v


def test_i05_class_too_few_also_when_metrics_missing():
    v = V.veredicto(_res_i05(**{"<10": {}}), REAL_CFG, "desarrollo")
    c = v["por_pais"]["mexico"]["clases_I05"]["juntas"]["<10"]
    assert c["reliable"] is False and c["etiqueta"] == V.TOO_FEW


# ------------------------------------------------------------------ label of an estimated month (etiqueta_estimacion)
def _v_pais(p2=True, p2b=True, i05=None, p5=None):
    v = {"E1c": {"P2_bloque3": p2, "P2b_7cbis_reliable": p2b}, "escala_publicada_7gbis": "E1c"}
    if i05 is not None:
        v["clases_I05"] = i05
    if p5 is not None:
        v["P5_era_terra_sola"] = {"P5": p5, "etiqueta_era": "indicative (Terra only)"}
    return v


def test_too_few_modis_is_never_reliable():
    for v in (_v_pais(), _v_pais(i05={"juntas": {"<10": {"reliable": True, "etiqueta": "reliable"}}}), None):
        for tramo in ("TA", "T"):
            e = V.etiqueta_estimacion(v, tramo, 4.0, U, CORTES, n_celdas=5000)
            assert e["etiqueta"] == V.TOO_FEW


def test_terra_only_is_indicative_even_if_p5_passes():
    e = V.etiqueta_estimacion(_v_pais(p5=True), "T", 500.0, U, CORTES, n_celdas=5000)
    assert e["etiqueta"] == V.INDICATIVE and "P5_passed_still_indicative" in e["motivos"]
    assert V.etiqueta_estimacion(_v_pais(p5=False), "T", 500.0, U, CORTES)["etiqueta"] == V.INDICATIVE


def test_rule_3b_when_classes_not_run():
    assert V.etiqueta_estimacion(_v_pais(), "TA", 50.0, U, CORTES, n_celdas=900)["etiqueta"] == V.RELIABLE
    small = V.etiqueta_estimacion(_v_pais(), "TA", 50.0, U, CORTES, n_celdas=720)       # Puebla box: < one block
    assert small["etiqueta"] == V.INDICATIVE and "aoi_smaller_than_block" in small["motivos"]
    failed = V.etiqueta_estimacion(_v_pais(p2b=False), "TA", 50.0, U, CORTES, n_celdas=5000)
    assert failed["etiqueta"] == V.INDICATIVE and "country_test_not_passed" in failed["motivos"]


_I05 = {"juntas": {"<10": {"reliable": False, "etiqueta": V.TOO_FEW},
                  "10-30": {"reliable": True, "etiqueta": V.RELIABLE},
                  "30-100": {"reliable": False, "etiqueta": V.INDICATIVE},
                  ">=100": {"reliable": True, "etiqueta": V.RELIABLE}}}


def test_i05_rule_by_count_class_on_top_of_rule_3b():
    """Country passed P2+P2b and AOI >= one block: then the count class decides between reliable and indicative."""
    v = _v_pais(p2=True, p2b=True, i05=_I05)
    assert V.etiqueta_estimacion(v, "TA", 12.0, U, CORTES, n_celdas=900)["etiqueta"] == V.RELIABLE
    e = V.etiqueta_estimacion(v, "TA", 30.0, U, CORTES, n_celdas=5000)                   # 30 goes to 30-100
    assert e["etiqueta"] == V.INDICATIVE and "count_class_30-100_not_reliable" in e["motivos"]
    assert V.etiqueta_estimacion(v, "TA", 100.0, U, CORTES, n_celdas=5000)["etiqueta"] == V.RELIABLE
    assert V.etiqueta_estimacion(v, "TA", 9.99, U, CORTES, n_celdas=5000)["etiqueta"] == V.TOO_FEW
    assert V.etiqueta_estimacion(v, "TA", 12.0, U, CORTES, n_celdas=900)["regla"] == "I-05 rule 3b + count classes"


def test_rule_3b_still_in_force_when_classes_run():
    """Gate B-G1 (option A; ADR-0014 point 9, PREREG section 4/5): a reliable count class never overrides rule 3b."""
    failed = _v_pais(p2=True, p2b=False, i05=_I05)                 # AR dev case: P2b_7cbis_reliable = False
    for n, med in ((720, 50.0), (100, 150.0), (5000, 150.0)):
        e = V.etiqueta_estimacion(failed, "TA", med, U, CORTES, n_celdas=n)
        assert e["etiqueta"] == V.INDICATIVE and "country_test_not_passed" in e["motivos"]
    passed = _v_pais(p2=True, p2b=True, i05=_I05)
    for n in (720, 100, None):                                     # Puebla box (720 cells) < one 3-degree block
        e = V.etiqueta_estimacion(passed, "TA", 150.0, U, CORTES, n_celdas=n)
        assert e["etiqueta"] == V.INDICATIVE and "aoi_smaller_than_block" in e["motivos"]
    no_p2 = _v_pais(p2=False, p2b=True, i05=_I05)
    assert V.etiqueta_estimacion(no_p2, "TA", 150.0, U, CORTES, n_celdas=5000)["etiqueta"] == V.INDICATIVE


def test_rule_3b_uses_published_scale_7gbis():
    v = {"E1c": {"P2_bloque3": False, "P2b_7cbis_reliable": False}, "E1b": {"P2_bloque3": True, "P2b_7cbis_reliable": True},
         "escala_publicada_7gbis": "E1b", "clases_I05": _I05}
    assert V.etiqueta_estimacion(v, "TA", 150.0, U, CORTES, n_celdas=900)["etiqueta"] == V.RELIABLE
    v["escala_publicada_7gbis"] = "E1c"
    assert V.etiqueta_estimacion(v, "TA", 150.0, U, CORTES, n_celdas=900)["etiqueta"] == V.INDICATIVE


def test_no_verdict_or_unknown_count_is_never_reliable():
    assert V.etiqueta_estimacion(None, "TA", 500.0, U, CORTES, n_celdas=5000)["etiqueta"] == V.INDICATIVE
    e = V.etiqueta_estimacion(_v_pais(), "TA", None, U, CORTES, n_celdas=5000)
    assert e["etiqueta"] == V.INDICATIVE and "expected_modis_count_unknown" in e["motivos"]
    with pytest.raises(ValueError):
        V.etiqueta_estimacion(_v_pais(), "A", 50.0, U, CORTES)


# ------------------------------------------------------------------ both P3 coverages in the verdict (lot 3 point 7)
def _p3(inc=0.83, exc=0.80, n_inc=100, n_exc=82):
    return {"cobertura": inc, "cobertura_excluye_Shat_cero": exc, "poblacion_veredicto": "excluye_s0",
            "n_excluidos_Shat_cero": n_inc - n_exc,
            "poblaciones": {"incluye_s0": {"cobertura": inc, "ic95": [0.8, 0.86], "n": n_inc},
                            "excluye_s0": {"cobertura": exc, "ic95": [0.77, 0.83], "n": n_exc}}}


def test_verdict_reports_both_p3_coverages_and_excluded_n():
    res = {"paises": {"mexico": {"E1c": {"P3_P4": {"P3": _p3(inc=0.86, exc=0.80)}}}}}
    v = V.veredicto(res, REAL_CFG, "desarrollo")
    E = v["por_pais"]["mexico"]["E1c"]
    assert v["P3_poblacion"] == "excluye_s0"
    assert E["P3"] is True                                   # 0.80 (without S_hat = 0) decides; 0.86 would fail
    pc = E["P3_coberturas"]
    assert pc["incluye_s0"]["cobertura"] == 0.86 and pc["excluye_s0"]["cobertura"] == 0.80
    assert pc["n_excluidos_Shat_cero"] == 18 and pc["decide"] == "excluye_s0"


def test_resumen_p3_recomputes_excluded_n_for_old_blocks():
    p3 = _p3()
    p3.pop("n_excluidos_Shat_cero")
    assert V.resumen_P3(p3)["n_excluidos_Shat_cero"] == 18
    assert V.resumen_P3({}) is None
