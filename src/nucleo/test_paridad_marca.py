"""tests/paridad_marca.json must be up to date with src/nucleo/validacion_marca.py (gate 15-Nov: nothing checked it).

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

The JSON is the Python side of the Python <-> JS parity of the 'unusual' flag (ADR-0006 6c-q); app/tests/paridad-test.js
checks JS against it. If validacion_marca.marca() changes and the JSON is not regenerated
(`flock data/.pesado.lock .venv/bin/python tests/paridad_marca_generar.py`), the JS parity would pass against a stale
reference. These tests recompute EVERY expected field of EVERY case with the current Python reference and require exact
equality (floats compared bit for bit after the JSON round trip). Only the JSON and pure functions are used: no data file.
Run:  flock data/.pesado.lock .venv/bin/python -m pytest -q -p no:cacheprovider src/nucleo
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nucleo import validacion_marca as VM  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PARITY = ROOT / "tests/paridad_marca.json"
BASE_NAME = "2012–2018 VIIRS"          # same constant as tests/paridad_marca_generar.py (BASE_NOMBRE)
J = json.loads(PARITY.read_text(encoding="utf-8"))


def _num(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


def _in(x):
    if x is None:
        return None
    return math.inf if x == "Infinity" else float(x)


def _roundtrip(d):
    """Same serialisation as the generator, so floats compare exactly as they are stored."""
    return json.loads(json.dumps(d, ensure_ascii=False))


def expected_now(c: dict) -> dict:
    v = c["valor"]
    m = VM.marca(float("nan") if v is None else v, c["base"], _in(c["lo"]), _in(c["hi"]))
    return _roundtrip({"p10": _num(m["p10"]), "mediana": _num(m["mediana"]), "p90": _num(m["p90"]), "n": m["n"],
                       "estado": m["estado"], "direccion": m["direccion"], "u1": m["u1"],
                       "razon_mediana": _num(m["razon_mediana"]),
                       "texto_razon": VM.texto_razon(v, m["mediana"], BASE_NAME) if v is not None else None})


def test_file_shape():
    assert J["version"] >= 3 and len(J["casos"]) >= 364
    assert {c["etiqueta"] for c in J["casos"]} >= {"REAL", "SYNTHETIC"}
    assert any(c.get("tipo") == "exact_tie" for c in J["casos"]), "exact-tie cases (gate B1) are missing"
    assert len({c["id"] for c in J["casos"]}) == len(J["casos"]), "duplicate case ids"


def test_every_case_matches_current_marca():
    stale = []
    for c in J["casos"]:
        now = expected_now(c)
        if now != c["esperado"]:
            diff = {k: (c["esperado"].get(k), now.get(k)) for k in now if c["esperado"].get(k) != now.get(k)}
            stale.append(f"{c['id']}: {diff}")
    assert not stale, (f"tests/paridad_marca.json is STALE for {len(stale)} case(s) (stored, now); regenerate with "
                       "`flock data/.pesado.lock .venv/bin/python tests/paridad_marca_generar.py`:\n" + "\n".join(stale[:20]))


@pytest.mark.parametrize("c", J["temporada"], ids=lambda c: c["id"])
def test_season_cases_match(c):
    t = VM.temporada_inusual(c["acumulado"], c["base"])
    now = _roundtrip({"inusual": t["inusual"], "estado": t["estado"], "p90": None if not math.isfinite(t["p90"]) else t["p90"]})
    assert now == c["esperado"]


@pytest.mark.parametrize("c", J["anio_fuego"], ids=lambda c: c["id"])
def test_fire_year_cases_match(c):
    assert VM.inicio_anio_fuego(c["medianas"]) == c["esperado"]


def test_detects_a_stale_file():
    """The check is not vacuous: perturbing one stored expectation is caught."""
    c = next(x for x in J["casos"] if x.get("tipo") == "exact_tie")
    bad = {**c, "esperado": {**c["esperado"], "estado": "unusual" if c["esperado"]["estado"] != "unusual" else "typical"}}
    assert expected_now(bad) != bad["esperado"]
