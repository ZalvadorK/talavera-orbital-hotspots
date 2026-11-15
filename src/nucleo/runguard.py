"""Run guards for the nucleo scripts: the shared heavy-memory lock and safe output paths.

SI-generated (AI): Claude Code wrote this during the event (gate D1 repair, 15-Nov ~02:30 Puebla); reviewed by the team.
Modified 15-Nov ~04:40 Puebla by Claude Code (SI-generated): `new_flag` parameter of refuse_overwrite.

Heavy lock (data/.pesado.lock: one DuckDB-heavy job at a time, 600 MB / 2 threads)
------------------------------------------------------------------------------------
`acquire_heavy_lock()` works whether or not the script is launched under `flock(1)`:

* Under ``flock data/.pesado.lock <cmd>`` (the documented way): util-linux flock keeps its locked descriptor open in
  the child. We find it in /proc/self/fd and call flock(LOCK_EX) on THAT open file description, which already owns the
  lock, so it returns at once (no self-deadlock). Mode reported: "inherited".
* Without flock: the script opens the lock file and takes LOCK_EX itself, polling every second and printing a message
  every 30 s, up to `timeout` seconds (default 3600, env NUCLEO_LOCK_TIMEOUT); then it exits with a clear error.
  The descriptor stays open in a module global, so the lock is held until the process exits. Mode: "acquired".
* If no descriptor is inherited but an ancestor process is ``flock ... data/.pesado.lock ...`` (a flock build that
  closes the descriptor), taking our own lock would deadlock against our own parent, so the ancestor's lock is
  trusted. Mode: "ancestor".

Output guards
-------------
`resolve_under(path, base)` resolves a user path (relative paths are relative to the repository root) and refuses
anything outside `base` (e.g. runs/) BEFORE any file is written. `refuse_overwrite(paths, overwrite, new_flag)` refuses to
write into existing outputs (and says which of them are versioned in git) unless `--sobrescribir` was given; the
message names the caller's own output option (`new_flag`: --salida by default, --exp for validacion_rt05.py).
`fresh_dir(base, stem)` returns a new, non-existing directory name with a UTC timestamp.
"""
from __future__ import annotations

import datetime as dt
import errno
import fcntl
import os
import subprocess
import time
from pathlib import Path

__all__ = ["LOCK_PATH", "acquire_heavy_lock", "resolve_under", "refuse_overwrite", "fresh_dir", "tracked_files"]

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "data/.pesado.lock"
_HELD: dict[str, int] = {}          # lock path -> descriptor kept open for the life of the process


def _inherited_fd(lock: Path) -> int | None:
    target = os.path.realpath(lock)
    try:
        names = os.listdir("/proc/self/fd")
    except OSError:
        return None
    for name in names:
        try:
            if os.path.realpath(os.readlink(f"/proc/self/fd/{name}")) == target:
                return int(name)
        except OSError:
            continue
    return None


def _ancestor_flock(lock: Path) -> int | None:
    """PID of an ancestor whose command line is `flock ... <lock> ...`, else None (Linux /proc only)."""
    target = os.path.realpath(lock)
    pid = os.getppid()
    for _ in range(32):
        if pid <= 1:
            return None
        try:
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            cwd = os.readlink(f"/proc/{pid}/cwd")
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return None
        args = [a.decode(errors="replace") for a in argv if a]
        if args and os.path.basename(args[0]) == "flock":
            for a in args[1:]:
                if not a.startswith("-") and os.path.realpath(os.path.join(cwd, a)) == target:
                    return pid
        pid = int(stat.rsplit(")", 1)[1].split()[1])      # field 4 = ppid
    return None


def acquire_heavy_lock(lock: str | Path = LOCK_PATH, timeout: float | None = None, quiet: bool = False) -> str:
    """Hold the shared heavy-memory lock for the rest of the process. Returns "inherited" | "acquired" | "ancestor"
    (or "held" if this process already took it). Raises SystemExit with a clear message on timeout."""
    lock = Path(lock)
    key = os.path.realpath(lock)
    if key in _HELD:
        return "held"
    if timeout is None:
        timeout = float(os.environ.get("NUCLEO_LOCK_TIMEOUT", "3600"))
    fd = _inherited_fd(lock)
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)      # same open file description as flock(1): immediate
            _HELD[key] = fd
            return "inherited"
        except OSError as e:
            if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise
            fd = None                                         # inherited but not the holder: wait like anyone else
    if _ancestor_flock(lock) is not None:
        if not quiet:
            print(f"[lock] {lock.name}: held by the parent flock process; continuing under that lock")
        _HELD[key] = -1
        return "ancestor"
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_RDONLY | os.O_CREAT, 0o664)
    t0 = time.monotonic()
    next_msg = 0.0
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _HELD[key] = fd
            return "acquired"
        except OSError as e:
            if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                os.close(fd)
                raise
        waited = time.monotonic() - t0
        if waited >= timeout:
            os.close(fd)
            raise SystemExit(f"REFUSED: the memory lock {lock} is still busy after {waited:.0f} s (another heavy job "
                             f"is running). Retry later or launch with `flock {lock.relative_to(ROOT) if lock.is_relative_to(ROOT) else lock} <command>`.")
        if not quiet and waited >= next_msg:
            print(f"[lock] waiting for {lock.name} (another heavy job is running; {waited:.0f} s)…", flush=True)
            next_msg += 30.0
        time.sleep(1.0)


def resolve_under(path: str | Path, base: str | Path, what: str = "output") -> Path:
    """Resolve `path` (relative -> relative to the repository root) and require it strictly inside `base`."""
    base_r = Path(base).resolve()
    p = Path(path)
    p = (p if p.is_absolute() else ROOT / p).resolve()
    if p == base_r or not p.is_relative_to(base_r):
        raise SystemExit(f"REFUSED: the {what} {path!s} is outside {base_r.relative_to(ROOT) if base_r.is_relative_to(ROOT) else base_r}/ "
                         f"(it resolves to {p}); nothing was written.")
    return p


def tracked_files(path: str | Path) -> list[str]:
    """Files under `path` that are versioned in git (empty if git is unavailable)."""
    try:
        r = subprocess.run(["git", "ls-files", "--", str(Path(path).resolve().relative_to(ROOT))], cwd=ROOT,
                           capture_output=True, text=True, timeout=10)
        return [x for x in r.stdout.splitlines() if x]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def refuse_overwrite(paths: list[str | Path], overwrite: bool, new_flag: str = "--salida <new directory>") -> None:
    """Refuse (SystemExit) if any path exists (a file, or a non-empty directory) and `overwrite` is False.
    `new_flag` is the caller's own option for choosing another output, quoted in the message (default
    "--salida <new directory>"; validacion_rt05.py passes "--exp <new EXP folder>")."""
    if overwrite:
        return
    found = []
    for p in map(Path, paths):
        if (p.is_file()) or (p.is_dir() and any(p.iterdir())):
            n = len(tracked_files(p))
            found.append(f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}"
                         + (f" ({n} file(s) versioned in git)" if n else ""))
    if found:
        raise SystemExit("REFUSED: the output already exists and is not overwritten without --sobrescribir:\n  - " + "\n  - ".join(found)
                         + f"\nUse {new_flag} or, if you really want to replace it, --sobrescribir.")


def fresh_dir(base: str | Path, stem: str) -> Path:
    """A directory name under `base` that does not exist yet: <stem>-rerun-<UTC yyyymmddTHHMMSSZ>[-n]."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = Path(base) / f"{stem}-rerun-{stamp}"
    n = 1
    while d.exists():
        n += 1
        d = Path(base) / f"{stem}-rerun-{stamp}-{n}"
    return d
