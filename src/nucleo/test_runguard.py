"""Tests for nucleo.runguard (gate D1: lock + safe outputs) and the CLI of experimentos.py / m1_clases.py.

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

No data file is read: the lock tests use a temporary lock file; the CLI tests only use --help and refused paths
(which must exit before any data is read or any file is written).
Run:  flock data/.pesado.lock .venv/bin/python -m pytest -q -p no:cacheprovider src/nucleo
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nucleo import runguard as RG  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
SNIPPET = ("import sys; sys.path.insert(0, {src!r}); from nucleo.runguard import acquire_heavy_lock; "
           "print(acquire_heavy_lock({lock!r}, timeout={t}, quiet=True))")


def _run(args, timeout=60, **kw):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout, **kw)


def _snippet(lock, t=5):
    return SNIPPET.format(src=str(ROOT / "src"), lock=str(lock), t=t)


def test_lock_acquired_without_flock(tmp_path):
    r = _run([PY, "-c", _snippet(tmp_path / "x.lock")])
    assert r.returncode == 0 and r.stdout.strip() == "acquired", r.stderr


def test_lock_inherited_under_flock_no_deadlock(tmp_path):
    lock = tmp_path / "x.lock"
    r = _run(["flock", str(lock), PY, "-c", _snippet(lock)], timeout=30)
    assert r.returncode == 0 and r.stdout.strip() in ("inherited", "ancestor"), (r.stdout, r.stderr)


def test_lock_busy_times_out_with_clear_message(tmp_path):
    lock = tmp_path / "x.lock"
    holder = subprocess.Popen(["flock", str(lock), "sleep", "20"])
    try:
        for _ in range(50):                 # wait until the holder has the lock
            if _run(["flock", "-n", str(lock), "true"]).returncode != 0:
                break
        r = _run([PY, "-c", _snippet(lock, t=2)], timeout=30)
        assert r.returncode != 0 and "lock" in r.stderr and "busy" in r.stderr, (r.stdout, r.stderr)
    finally:
        holder.kill()
        holder.wait()


def test_resolve_under_refuses_outside(tmp_path):
    runs = ROOT / "runs"
    assert RG.resolve_under("runs/EXP-XYZ", runs) == runs / "EXP-XYZ"
    for bad in ("/tmp/x", "runs/../docs", "runs", str(tmp_path)):
        with pytest.raises(SystemExit):
            RG.resolve_under(bad, runs)


def test_refuse_overwrite(tmp_path):
    (tmp_path / "d").mkdir()
    RG.refuse_overwrite([tmp_path / "d", tmp_path / "missing"], overwrite=False)   # empty dir / missing: fine
    (tmp_path / "d" / "f").write_text("x")
    with pytest.raises(SystemExit):
        RG.refuse_overwrite([tmp_path / "d"], overwrite=False)
    RG.refuse_overwrite([tmp_path / "d"], overwrite=True)


def test_fresh_dir_is_new(tmp_path):
    d = RG.fresh_dir(tmp_path, "EXP-001-002")
    assert not d.exists() and d.name.startswith("EXP-001-002-rerun-")


@pytest.mark.parametrize("script", ["src/nucleo/experimentos.py", "src/nucleo/m1_clases.py"])
def test_help_runs_nothing(script):
    canon = [ROOT / "runs/EXP-001", ROOT / "runs/EXP-002", ROOT / "runs/EXP-005/m1_clases", ROOT / "docs/03-nucleo/m1-clases-dev.md"]
    snap = lambda: {str(f): f.stat().st_mtime_ns for c in canon for f in ([c] if c.is_file() else c.rglob("*"))}  # noqa: E731
    runs_before = sorted(x.name for x in (ROOT / "runs").iterdir())
    before = snap()
    r = _run([PY, script, "--help"])
    assert r.returncode == 0 and "--sobrescribir" in r.stdout and "--salida" in r.stdout
    assert snap() == before and sorted(x.name for x in (ROOT / "runs").iterdir()) == runs_before


@pytest.mark.parametrize("script,args", [
    ("src/nucleo/experimentos.py", ["--salida", "{tmp}/outside_runs"]),
    ("src/nucleo/experimentos.py", ["--salida", "runs"]),            # contains EXP-001 / EXP-002 (versioned)
    ("src/nucleo/m1_clases.py", ["--salida", "runs/EXP-005/m1_clases"]),   # existing, versioned
    ("src/nucleo/m1_clases.py", ["--salida", "runs/zz-test", "--doc", "{tmp}/m1.md"]),
])
def test_refused_before_reading_data(script, args, tmp_path):
    r = _run([PY, script, *(a.format(tmp=tmp_path) for a in args)], timeout=60)
    assert r.returncode != 0 and "REFUSED" in r.stderr, (r.stdout, r.stderr)
    assert "lock" not in r.stdout                                     # refused before taking the lock / reading data
    assert not (ROOT / "runs/zz-test").exists() and not any(tmp_path.iterdir())


def test_validacion_rt05_refuses_exp_outside_runs(tmp_path):
    out = tmp_path / "exp_outside"
    r = _run([PY, "src/nucleo/validacion_rt05.py", "--modo", "desarrollo", "--exp", str(out)], timeout=60)
    assert r.returncode != 0 and "REFUSED" in r.stderr and "outside runs/" in r.stderr, (r.stdout, r.stderr)
    assert not out.exists()
