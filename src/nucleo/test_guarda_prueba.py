"""Tests for the H4 gate defects D-N1, D-N2, D-N3, D-N5, provenance.git_dirty, P5 (prepared) and the P3 populations.

SI-generated (AI): Claude Code wrote this during the event (gate H4 dry-run fixes, 15-Nov ~03:30 Puebla); reviewed by
the team.

NO real test run is ever started here: the single-test guard is exercised on a fake repository root in tmp_path
(monkeypatch of RAIZ / PROC / CONFIG / HASHES / git), and no data file of data/processed is read. All data frames
below are SYNTHETIC (not observations). The CLI checks only use refused invocations of the DEVELOPMENT mode, which
exit before taking the lock or reading data.
Run:  flock data/.pesado.lock .venv/bin/python -m pytest -q -p no:cacheprovider src/nucleo
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nucleo import provenance as PV  # noqa: E402
from nucleo import validacion_rt05 as V  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def _run(args, timeout=60):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------ fake repository for the single-test guard
@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Fake root: config/validacion.yaml, data/processed inputs (SYNTHETIC bytes), runs/. git is faked: the tag exists
    and `git show prereg-v1:config/validacion.hashes.json` returns whatever is in state['en_tag']."""
    proc = tmp_path / "data/processed"
    proc.mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "runs").mkdir()
    (tmp_path / "src/nucleo").mkdir(parents=True)
    (tmp_path / "config/validacion.yaml").write_text("version: 1\n", encoding="utf-8")
    for name, data in (("deteccion_mexico.parquet", b"SYNTHETIC-mx"), ("deteccion_argentina.parquet", b"SYNTHETIC-ar"),
                       ("disponibilidad_plataforma_dia.csv", b"fecha,plataforma\n"),
                       ("mascara_estatica_mexico.parquet", b"SYNTHETIC-mask"),
                       ("factores_mexico_2012-02-01_2018-12-31.parquet", b"SYNTHETIC-F"),
                       ("intervalos_mexico.json", b"{}")):
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
    return {"root": tmp_path, "proc": proc, "state": state}


CFG = {"umbrales": {"pendiente_lote3": False}, "modos": {"prueba": {"evaluacion": ["2019-01-01", "2021-12-31"]}}}


def _args(**kw):
    base = {"prueba_unica": True, "re_corrida_documentada": None, "i05_exploratorio": False, "p5_exploratorio": False,
            "sobrescribir": False}
    return argparse.Namespace(**{**base, **kw})


def _freeze(repo):
    V.registrar_hashes(CFG)
    repo["state"]["en_tag"] = V.HASHES.read_text(encoding="utf-8")
    return json.loads(V.HASHES.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ D-N5: test inputs in the hash guard
def test_registrar_hashes_includes_test_inputs(repo):
    reg = _freeze(repo)
    ent = reg["entradas_prueba"]
    assert set(ent) == {"data/processed/deteccion_mexico.parquet", "data/processed/deteccion_argentina.parquet",
                        "data/processed/disponibilidad_plataforma_dia.csv", "data/processed/mascara_estatica_mexico.parquet"}
    assert ent["data/processed/deteccion_mexico.parquet"] == V.sha256(repo["proc"] / "deteccion_mexico.parquet")
    assert "data/processed/factores_mexico_2012-02-01_2018-12-31.parquet" in reg["tablas"]   # unchanged key


def test_guard_passes_when_everything_matches(repo):
    _freeze(repo)
    g = V.guarda_prueba(CFG, _args())
    assert g["tag"] == V.TAG and g["commit_tag"] == "abc1234"


@pytest.mark.parametrize("archivo", ["deteccion_mexico.parquet", "disponibilidad_plataforma_dia.csv",
                                     "mascara_estatica_mexico.parquet"])
def test_guard_refuses_changed_input(repo, archivo):
    _freeze(repo)
    (repo["proc"] / archivo).write_bytes(b"SYNTHETIC-regenerated-after-freeze")
    with pytest.raises(SystemExit) as e:
        V.guarda_prueba(CFG, _args())
    assert f"test input changed or missing: data/processed/{archivo}" in str(e.value)


def test_guard_refuses_missing_and_new_inputs(repo):
    _freeze(repo)
    (repo["proc"] / "deteccion_argentina.parquet").unlink()
    (repo["proc"] / "mascara_estatica_argentina.parquet").write_bytes(b"SYNTHETIC-new")
    with pytest.raises(SystemExit) as e:
        V.guarda_prueba(CFG, _args())
    msg = str(e.value)
    assert "missing: data/processed/deteccion_argentina.parquet" in msg
    assert "new test input, not registered: data/processed/mascara_estatica_argentina.parquet" in msg


def test_guard_refuses_registry_without_inputs(repo):
    reg = _freeze(repo)
    reg.pop("entradas_prueba")
    V.HASHES.write_text(json.dumps(reg), encoding="utf-8")
    repo["state"]["en_tag"] = V.HASHES.read_text(encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        V.guarda_prueba(CFG, _args())
    assert "does not register the test inputs" in str(e.value)


# ------------------------------------------------------------------ D-N3: "test started" marker
def test_marker_blocks_second_run_without_verdict(repo):
    _freeze(repo)
    g = V.guarda_prueba(CFG, _args())
    d = repo["root"] / "runs/EXP-900"
    V.marcar_inicio_prueba(d, g, "EXP-900")
    m = json.loads(V.marca_prueba().read_text(encoding="utf-8"))
    assert m["intentos"][0]["commit_tag"] == "abc1234" and m["intentos"][0]["tag"] == V.TAG and m["intentos"][0]["hora_utc"]
    assert (d / V.NOMBRE_MARCA_EXP).exists() and not (d / "verdict.json").exists()
    with pytest.raises(SystemExit) as e:                           # crashed run: no verdict.json, still refused
        V.guarda_prueba(CFG, _args())
    assert "a single test was already started" in str(e.value)


def test_marker_in_exp_dir_alone_also_blocks(repo):
    _freeze(repo)
    d = repo["root"] / "runs/EXP-901"
    d.mkdir()
    (d / V.NOMBRE_MARCA_EXP).write_text("{}", encoding="utf-8")   # global marker deleted by hand: still refused
    with pytest.raises(SystemExit) as e:
        V.guarda_prueba(CFG, _args())
    assert "a single test was already started" in str(e.value)


def test_documented_rerun_appends_history(repo):
    _freeze(repo)
    V.marcar_inicio_prueba(repo["root"] / "runs/EXP-900", V.guarda_prueba(CFG, _args()), "EXP-900")
    g2 = V.guarda_prueba(CFG, _args(re_corrida_documentada="process killed (OOM)"))
    V.marcar_inicio_prueba(repo["root"] / "runs/EXP-902", g2, "EXP-902")
    m = json.loads(V.marca_prueba().read_text(encoding="utf-8"))
    assert [i["exp_arg"] for i in m["intentos"]] == ["EXP-900", "EXP-902"]
    assert m["intentos"][1]["re_corrida"] == "process killed (OOM)"


def test_marker_without_documented_rerun_is_refused(repo):
    g = {"tag": V.TAG, "commit_tag": "abc1234", "re_corrida": None}
    V.marcar_inicio_prueba(repo["root"] / "runs/EXP-900", g, "EXP-900")
    with pytest.raises(SystemExit):
        V.marcar_inicio_prueba(repo["root"] / "runs/EXP-903", g, "EXP-903")


class _LeyoDatos(Exception):
    pass


def test_correr_writes_marker_before_reading_any_data(repo, monkeypatch):
    """correr() in test mode with a faked guard: the marker must exist when the first reader is created."""
    visto = {}

    class LectorEspia:
        def __init__(self, fecha_maxima):
            visto["marca"] = V.marca_prueba().exists()
            visto["fecha_maxima"] = fecha_maxima
            raise _LeyoDatos

    monkeypatch.setattr(V, "guarda_prueba", lambda cfg, args: {"tag": V.TAG, "commit_tag": "abc1234", "re_corrida": None})
    monkeypatch.setattr(V, "Lector", LectorEspia)
    cfg = {"semilla": 42, "pruebas": {"P5": "not_run"}, "umbrales": {"pendiente_lote3": False},
           "modos": {"prueba": {"calibracion": ["2012-02-01", "2018-12-31"], "base": ["2012-02-01", "2018-12-31"],
                                "evaluacion": ["2019-01-01", "2021-12-31"], "fecha_maxima": "2021-12-31"}}}
    exp = str(repo["root"] / "runs/EXP-910")
    with pytest.raises(_LeyoDatos):
        V.correr(cfg, "prueba", exp, _args())
    assert visto == {"marca": True, "fecha_maxima": "2021-12-31"}
    assert (repo["root"] / "runs/EXP-910" / V.NOMBRE_MARCA_EXP).exists()


# ------------------------------------------------------------------ D-N2: existing --exp
def test_validar_exp_dev_refuses_existing_unless_overwrite(repo):
    d = repo["root"] / "runs/EXP-004"
    d.mkdir()
    assert V.validar_exp(str(d), "desarrollo") == d                 # empty: fine
    (d / "metricas.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        V.validar_exp(str(d), "desarrollo")
    assert V.validar_exp(str(d), "desarrollo", sobrescribir=True) == d


def test_validar_exp_test_mode_never_overwrites(repo):
    d = repo["root"] / "runs/EXP-004"
    d.mkdir()                                                         # even an EMPTY existing folder is refused
    with pytest.raises(SystemExit):
        V.validar_exp(str(d), "prueba")
    with pytest.raises(SystemExit):
        V.validar_exp(str(d), "prueba", sobrescribir=True)
    with pytest.raises(SystemExit):
        V.validar_exp(str(repo["root"] / "runs/EXP-NEW"), "prueba", sobrescribir=True)
    assert V.validar_exp(str(repo["root"] / "runs/EXP-NEW"), "prueba") == repo["root"] / "runs/EXP-NEW"


def test_cli_dev_refuses_existing_versioned_exp():
    """Real CLI, DEVELOPMENT mode only: --exp EXP-004 (exists, versioned) is refused before the lock or any read."""
    canon = ROOT / "runs/EXP-004"
    if not canon.is_dir():
        pytest.skip("runs/EXP-004 not present")
    snap = {str(f): f.stat().st_mtime_ns for f in canon.rglob("*")}
    r = _run([PY, "src/nucleo/validacion_rt05.py", "--modo", "desarrollo", "--exp", "EXP-004"])
    assert r.returncode != 0 and "REFUSED" in r.stderr and "--sobrescribir" in r.stderr, (r.stdout, r.stderr)
    assert "lock" not in r.stdout and "OK ->" not in r.stdout
    assert {str(f): f.stat().st_mtime_ns for f in canon.rglob("*")} == snap


# ------------------------------------------------------------------ D-N1: experimentos.py --salida <existing run>
def test_cli_experimentos_refuses_existing_run_as_base():
    canon = ROOT / "runs/EXP-005"
    if not canon.is_dir():
        pytest.skip("runs/EXP-005 not present")
    r = _run([PY, "src/nucleo/experimentos.py", "--salida", "runs/EXP-005"])
    assert r.returncode != 0 and "REFUSED" in r.stderr and "runs/EXP-005" in r.stderr, (r.stdout, r.stderr)
    assert "lock" not in r.stdout
    assert not (canon / "EXP-001").exists() and not (canon / "EXP-002").exists()


def test_experimentos_destinos_validates_base(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "src/nucleo"))
    import experimentos as EX
    runs = tmp_path / "runs"
    (runs / "EXP-777").mkdir(parents=True)
    (runs / "EXP-777" / "informe.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(EX, "RUNS", runs)
    with pytest.raises(SystemExit):
        EX.destinos(argparse.Namespace(salida=str(runs / "EXP-777"), sobrescribir=False))
    d1, d2 = EX.destinos(argparse.Namespace(salida=str(runs / "EXP-777"), sobrescribir=True))
    assert (d1, d2) == (runs / "EXP-777/EXP-001", runs / "EXP-777/EXP-002") and not d1.exists()
    d1, _ = EX.destinos(argparse.Namespace(salida=str(runs / "NUEVO"), sobrescribir=False))
    assert d1 == runs / "NUEVO/EXP-001" and not (runs / "NUEVO").exists()


# ------------------------------------------------------------------ provenance.git_dirty on a temporary repository
def _git(cwd, *a):
    subprocess.run(["git", "-c", "user.email=test@example.invalid", "-c", "user.name=test", "-c", "commit.gpgsign=false",
                    *a], cwd=cwd, check=True, capture_output=True, text=True)


def test_git_dirty_clean_and_modified(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    f = tmp_path / "entrada.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "src/nucleo").mkdir(parents=True)
    (tmp_path / "src/nucleo/codigo.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    monkeypatch.setattr(PV, "ROOT", tmp_path)
    assert PV.git_dirty([f]) == (False, [])                         # clean tree
    assert PV.git_dirty([f], include_code=False) == (False, [])
    f.write_text("a,b\n1,3\n", encoding="utf-8")                    # modified input
    dirty, lines = PV.git_dirty([f], include_code=False)
    assert dirty is True and lines == [" M entrada.csv"]
    _git(tmp_path, "checkout", "-q", "--", "entrada.csv")
    (tmp_path / "src/nucleo/codigo.py").write_text("x = 2\n", encoding="utf-8")   # modified code under src/nucleo
    assert PV.git_dirty([f]) == (True, [" M src/nucleo/codigo.py"])
    assert PV.git_dirty([f], include_code=False) == (False, [])
    assert PV.git_dirty([Path("/outside/the/repo.txt")], include_code=False) == (False, [])


# ------------------------------------------------------------------ P3 populations (B-R10) and P5 (B-R7), SYNTHETIC
def test_p3_populations_default_and_switch():
    cov = np.array([1, 1, 0, 1, 1, 0, 1, 1], float)
    con_shat = np.array([False, False, True, True, True, True, True, True])
    bt = V.Boot(np.array(["a|1", "a|1", "b|1", "b|1", "c|2", "c|2", "d|2", "d|2"]), 50, np.random.default_rng(0))
    out = V.p3_poblaciones(cov, con_shat, bt, {})
    assert out["poblacion_veredicto"] == "incluye_s0"
    assert out["poblaciones"]["incluye_s0"] == {"cobertura": 0.75, "ic95": out["poblaciones"]["incluye_s0"]["ic95"], "n": 8}
    assert out["poblaciones"]["excluye_s0"]["cobertura"] == pytest.approx(4 / 6, abs=1e-4)
    assert out["cobertura_excluye_Shat_cero"] == out["poblaciones"]["excluye_s0"]["cobertura"]
    U = {"P3": {"cobertura": [0.75, 0.85]}}
    p3 = {"cobertura": 0.75, **out}
    assert V.bool_P3(p3, U, {}) is True                                       # default = previous behaviour
    assert V.bool_P3(p3, U, {"p3": {"poblacion": "excluye_s0"}}) is False     # 0.667 outside [0.75, 0.85]
    with pytest.raises(SystemExit):
        V.p3_poblacion({"p3": {"poblacion": "otra"}})


def _p5_res(kc=0.65, coc=0.8, pu=0.85, pt=0.96, cob=0.8, ind=0.4, p3=0.8):
    return {"P2_P2b": {"kappa_cruzado": {"punto": kc}, "cociente_pareado": {"punto": coc},
                       "P2b": {"precision_unusual": pu, "precision_typical": pt, "cobertura_ic80_bloque": cob,
                               "pct_indeterminado": ind}},
            "P3": {"cobertura": p3, "cobertura_excluye_Shat_cero": p3}}


U_REC = {"P2": {"kappa_min": 0.60, "cociente_gemelos_min": 0.75},
         "P2b": {"precision_unusual_min": 0.80, "precision_typical_min": 0.95, "cobertura_ic80_bloque": [0.75, 0.85],
                 "indeterminado_max": 0.50},
         "P3": {"cobertura": [0.75, 0.85]}}


def test_p5_verdict_pending_threshold_by_default():
    v = V.veredicto_P5(_p5_res(), {**U_REC, "P5": {"criterio": None}}, {})
    assert v["estado"] == "pending_threshold" and v["P5"] is None and v["etiqueta_era"] == "indicative (Terra only)"
    assert V.veredicto_P5(_p5_res(), U_REC, {})["estado"] == "pending_threshold"      # key absent: same


def test_p5_verdict_with_same_thresholds_and_invalid_value():
    U = {**U_REC, "P5": {"criterio": "mismos_que_P2_P2b_P3"}}
    assert V.veredicto_P5(_p5_res(), U, {})["P5"] is True
    v = V.veredicto_P5(_p5_res(ind=0.6), U, {})                      # P2b fails on % indeterminate
    assert v["P2b"] is False and v["P5"] is False and v["etiqueta_era"] == "indicative (Terra only)"
    with pytest.raises(SystemExit):
        V.veredicto_P5(_p5_res(), {**U_REC, "P5": {"criterio": 0.6}}, {})


def test_veredicto_includes_p5_only_when_run():
    res = {"paises": {"mexico": {"P5": {**_p5_res(), "modo": "exploratory"}}}}
    cfg = {"umbrales": {**U_REC, "P5": {"criterio": None}}, "pruebas": {"P5": "not_run"}}
    assert "P5_era_terra_sola" not in V.veredicto(res, cfg, "desarrollo")["por_pais"]["mexico"]
    res["paises"]["mexico"]["P5"]["modo"] = "run"
    cfg["pruebas"]["P5"] = "run"
    assert V.veredicto(res, cfg, "desarrollo")["por_pais"]["mexico"]["P5_era_terra_sola"]["estado"] == "pending_threshold"


def test_h_terra_uses_terra_detections_and_T_factors():
    F = pd.DataFrame({"reloj": ["T", "T", "TA"], "mes": [1, 1, 1], "turno": ["D", "D", "D"],
                      "celda1": ["19_-99", "20_-99", "19_-99"], "k": [3.0, 3.0, 2.0], "s": [2.0, 1.0, 1.0],
                      "w": [6.0, 3.0, 2.0]})
    mod = pd.DataFrame({"plataforma": ["Terra", "Aqua", "Terra", "Terra"],
                        "acq_date_utc": pd.to_datetime(["2016-01-03", "2016-01-03", "2016-01-04", "2016-01-05"]),
                        "anio": [2016] * 4, "mes": [1] * 4, "turno": ["D"] * 4,
                        "celda1": ["19_-99", "19_-99", "21_-99", "20_-99"], "n": [2, 50, 1, 4]})
    P = pd.DataFrame({"celda1": ["19_-99", "20_-99", "21_-99", "22_-99"], "anio": [2016] * 4, "mes": [1] * 4})
    h = V.h_terra(mod, F, P, "2016-01-01", "2016-01-31")
    # 19_-99: 2 Terra × w 6 = 12 (Aqua ignored); 20_-99: 4 × 3 = 12; 21_-99: no factor → country k 3 × 1 = 3; 22: 0
    assert list(h) == [12.0, 12.0, 3.0, 0.0]
