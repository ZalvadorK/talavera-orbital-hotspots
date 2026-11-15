"""Tests for pendientes(): a `run` test without its required threshold blocks the freeze and the single-test guard.

SI-generated (AI): Claude Code wrote this during the event (night relay, 15-Nov ~04:40 Puebla); reviewed by the team.

Defect fixed: with `pruebas.P5: run` and `umbrales.P5.criterio: null` (and `pendiente_lote3: false`), neither
registrar_hashes() nor guarda_prueba() refused, because pendientes() only looked at `pendiente_lote3`. Now every test
with `run` whose required threshold (UMBRALES_REQUERIDOS, or its own `umbrales.<test>` block) is absent or null is
pending. Every config here is a TEMPORARY YAML in tmp_path, derived from config/validacion.yaml; the real config, the
real config/validacion.hashes.json and data/processed are never written (the fake repository root is tmp_path) and no
test run is ever started. No hashes of the real repository are registered.
Modified 15-Nov ~14:00 Puebla (Claude Code, SI-generated): the real config now carries the lot-3 decision (nothing
pending; P5 and clases_I05 run with their thresholds). The temporary configs start from the PRE-DECISION state of the
optional tests (P5 / clases_I05 not_run, P5 criterion null, no M1), so these tests keep exercising the guard.
Run:  flock data/.pesado.lock .venv/bin/python -m pytest -q -p no:cacheprovider src/nucleo
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nucleo import runguard as RG  # noqa: E402
from nucleo import validacion_rt05 as V  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REAL_CFG = yaml.safe_load((ROOT / "config/validacion.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Fake repository root in tmp_path (SYNTHETIC input bytes); git faked so that the tag exists and `git show`
    returns the registered hashes (the guard then fails only for the reason under test)."""
    proc = tmp_path / "data/processed"
    proc.mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "runs").mkdir()
    (tmp_path / "src/nucleo").mkdir(parents=True)
    for name, data in (("deteccion_mexico.parquet", b"SYNTHETIC-mx"), ("disponibilidad_plataforma_dia.csv", b"f,p\n")):
        (proc / name).write_bytes(data)
    state = {"en_tag": ""}

    def fake_git(*a):
        if a[:2] == ("tag", "-l"):
            return V.TAG
        if a and a[0] == "show":
            return state["en_tag"]
        if a and a[0] in ("rev-list", "rev-parse"):
            return "abc1234"
        return ""

    monkeypatch.setattr(V, "RAIZ", tmp_path)
    monkeypatch.setattr(V, "PROC", proc)
    monkeypatch.setattr(V, "CONFIG", tmp_path / "config/validacion.yaml")
    monkeypatch.setattr(V, "HASHES", tmp_path / "config/validacion.hashes.json")
    monkeypatch.setattr(V, "git", fake_git)
    monkeypatch.setattr(V, "cargar_interfaz", lambda modo: (object(), False))
    return {"root": tmp_path, "state": state}


def _cfg(tmp_path: Path, mutate) -> dict:
    """Temporary YAML in tmp_path: the real config with lot 3 marked as fixed, then `mutate(cfg)`; read back from disk."""
    cfg = copy.deepcopy(REAL_CFG)
    cfg["umbrales"]["pendiente_lote3"] = False
    cfg["pruebas"].update(P5="not_run", clases_I05="not_run")     # pre-decision state of the optional tests
    cfg["umbrales"]["P5"] = {"criterio": None}
    cfg["umbrales"].pop("M1", None)
    mutate(cfg)
    f = tmp_path / "config/validacion.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return yaml.safe_load(f.read_text(encoding="utf-8"))


def _args(**kw):
    base = {"prueba_unica": True, "re_corrida_documentada": None, "i05_exploratorio": False, "p5_exploratorio": False,
            "sobrescribir": False}
    return argparse.Namespace(**{**base, **kw})


def _set(**pruebas):
    def m(cfg):
        cfg["pruebas"].update(pruebas)
    return m


# ------------------------------------------------------------------ pendientes()
def test_real_config_nothing_pending_after_lot3():
    """Real config after the lot-3 decision (Salvador, 15-Nov): nothing pending, P5 and clases_I05 run with thresholds."""
    assert V.pendientes(REAL_CFG) == []
    assert REAL_CFG["umbrales"]["pendiente_lote3"] is False
    assert REAL_CFG["pruebas"]["P5"] == "run" and REAL_CFG["umbrales"]["P5"]["criterio"] == "mismos_que_P2_P2b_P3"
    assert REAL_CFG["pruebas"]["clases_I05"] == "run" and REAL_CFG["umbrales"]["M1"]["min_modis_por_mes"] == 10


def test_nothing_pending_when_lot3_fixed_and_optional_tests_off(tmp_path):
    assert V.pendientes(_cfg(tmp_path, lambda c: None)) == []


def test_p5_run_with_null_criterion_is_pending(tmp_path):
    assert V.pendientes(_cfg(tmp_path, _set(P5="run"))) == ["/umbrales/P5/criterio (pruebas.P5: run)"]


def test_p5_run_with_absent_criterion_is_pending(tmp_path):
    def m(c):
        c["pruebas"]["P5"] = "run"
        del c["umbrales"]["P5"]
    assert V.pendientes(_cfg(tmp_path, m)) == ["/umbrales/P5/criterio (pruebas.P5: run)"]


def test_p5_run_with_criterion_set_is_not_pending(tmp_path):
    def m(c):
        c["pruebas"]["P5"] = "run"
        c["umbrales"]["P5"]["criterio"] = "mismos_que_P2_P2b_P3"
    assert V.pendientes(_cfg(tmp_path, m)) == []


def test_p5_not_run_with_null_criterion_is_not_pending(tmp_path):
    assert V.pendientes(_cfg(tmp_path, _set(P5="not_run"))) == []


def test_clases_i05_run_without_m1_threshold_is_pending(tmp_path):
    assert V.pendientes(_cfg(tmp_path, _set(clases_I05="run"))) == [
        "/umbrales/M1/min_modis_por_mes (pruebas.clases_I05: run)"]

    def m_null(c):
        c["pruebas"]["clases_I05"] = "run"
        c["umbrales"]["M1"] = {"min_modis_por_mes": None}
    assert V.pendientes(_cfg(tmp_path, m_null)) == ["/umbrales/M1/min_modis_por_mes (pruebas.clases_I05: run)"]

    def m_era_null(c):                                       # one number per era, one of them still null
        c["pruebas"]["clases_I05"] = "run"
        c["umbrales"]["M1"] = {"min_modis_por_mes": {"TA": 10, "T": None}}
    assert V.pendientes(_cfg(tmp_path, m_era_null)) == ["/umbrales/M1/min_modis_por_mes (pruebas.clases_I05: run)"]

    def m_ok(c):                                             # SYNTHETIC value, only to exercise the check
        c["pruebas"]["clases_I05"] = "run"
        c["umbrales"]["M1"] = {"min_modis_por_mes": 10}
    assert V.pendientes(_cfg(tmp_path, m_ok)) == []


def test_any_run_test_with_null_in_its_own_block_is_pending(tmp_path):
    """Same shape, other tests: a null inside a core threshold, or a future test S3 switched on with a null block."""
    def m(c):
        c["umbrales"]["P3"]["cobertura"] = [0.75, None]
        c["pruebas"]["S3"] = "run"
        c["umbrales"]["S3"] = {"umbral": None}
    assert V.pendientes(_cfg(tmp_path, m)) == ["/umbrales/P3 (pruebas.P3: run)", "/umbrales/S3 (pruebas.S3: run)"]


def test_core_test_without_its_block_is_pending(tmp_path):
    def m(c):
        del c["umbrales"]["J2_bloque"]
    assert V.pendientes(_cfg(tmp_path, m)) == ["/umbrales/J2_bloque (pruebas.J2: run)"]


def test_lot3_and_run_tests_are_listed_together(tmp_path):
    def m(c):
        c["umbrales"]["pendiente_lote3"] = True
        c["pruebas"]["P5"] = "run"
    assert V.pendientes(_cfg(tmp_path, m)) == ["/umbrales", "/umbrales/P5/criterio (pruebas.P5: run)"]


# ------------------------------------------------------------------ registrar_hashes() and the single-test guard
@pytest.mark.parametrize("mut", [_set(P5="run"), _set(clases_I05="run"), _set(P5="run", clases_I05="run")],
                         ids=["P5", "clases_I05", "both"])
def test_registrar_hashes_refuses_and_writes_nothing(repo, mut):
    cfg = _cfg(repo["root"], mut)
    with pytest.raises(SystemExit) as e:
        V.registrar_hashes(cfg)
    assert "REFUSED: pending thresholds" in str(e.value) and "(pruebas." in str(e.value)
    assert not V.HASHES.exists()


@pytest.mark.parametrize("mut", [_set(P5="run"), _set(clases_I05="run")], ids=["P5", "clases_I05"])
def test_guard_refuses_run_test_without_threshold(repo, mut):
    """Freeze with a complete config (fake root), then switch the test on without its threshold: the guard refuses."""
    V.registrar_hashes(_cfg(repo["root"], lambda c: None))
    repo["state"]["en_tag"] = V.HASHES.read_text(encoding="utf-8")
    cfg = _cfg(repo["root"], mut)
    with pytest.raises(SystemExit) as e:
        V.guarda_prueba(cfg, _args())
    assert "pending thresholds" in str(e.value) and "(pruebas." in str(e.value)


def test_guard_and_registrar_pass_with_thresholds_set(repo):
    def m(c):                                                # SYNTHETIC M1 value, only to exercise the check
        c["pruebas"].update(P5="run", clases_I05="run")
        c["umbrales"]["P5"]["criterio"] = "mismos_que_P2_P2b_P3"
        c["umbrales"]["M1"] = {"min_modis_por_mes": 10}
    cfg = _cfg(repo["root"], m)
    V.registrar_hashes(cfg)                                  # writes only the fake root's hashes file (tmp_path)
    assert V.HASHES.exists() and V.HASHES.is_relative_to(repo["root"])
    repo["state"]["en_tag"] = V.HASHES.read_text(encoding="utf-8")
    assert V.guarda_prueba(cfg, _args())["tag"] == V.TAG


def test_verdict_notice_names_the_pending_threshold(tmp_path):
    cfg = _cfg(tmp_path, _set(P5="run"))
    out = V.veredicto({"paises": {}}, cfg, "desarrollo")
    assert out["umbrales_fijados"] is False and "P5/criterio" in out["aviso"]
    lot3 = _cfg(tmp_path, lambda c: c["umbrales"].update(pendiente_lote3=True))
    assert "(pendiente_lote3)" in V.veredicto({"paises": {}}, lot3, "desarrollo")["aviso"]       # unchanged text
    assert "aviso" not in V.veredicto({"paises": {}}, REAL_CFG, "desarrollo")                   # real config: fixed


# ------------------------------------------------------------------ refuse_overwrite names the caller's flag
def test_refuse_overwrite_flag_name(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f").write_text("x")
    with pytest.raises(SystemExit) as e:
        RG.refuse_overwrite([tmp_path / "d"], overwrite=False)
    assert "Use --salida <new directory>" in str(e.value)
    with pytest.raises(SystemExit) as e:
        RG.refuse_overwrite([tmp_path / "d"], overwrite=False, new_flag="--exp <new EXP folder>")
    assert "Use --exp <new EXP folder>" in str(e.value) and "--salida" not in str(e.value)


def test_validar_exp_message_names_exp(repo):
    d = repo["root"] / "runs/EXP-004"
    d.mkdir()
    (d / "metricas.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        V.validar_exp(str(d), "desarrollo")
    assert "--exp <new EXP folder>" in str(e.value) and "--salida" not in str(e.value)
