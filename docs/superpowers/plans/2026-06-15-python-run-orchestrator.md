# Python Run Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `pymice/run.sh` and `pymice/run.bat` with one stdlib-only, cross-platform `pymice/run.py` control script.

**Architecture:** A single file `pymice/run.py` (standard library only) resolves all paths from its own location, finds the project virtualenv itself, and invokes its `uvicorn`/`npm` directly — no activation. Pure helpers (venv resolution, port check, clean targets, log tail, color, arg parsing) are unit-tested; process-lifecycle commands are written against those helpers and verified by a manual smoke test.

**Tech Stack:** Python 3.11 stdlib (`argparse`, `subprocess`, `socket`, `os`, `signal`, `shutil`, `pathlib`), pytest for the helper unit tests.

---

## Reference: confirmed environment facts

- The venv resolves at `REPO_ROOT/uv-env` (symlink → `/mnt/hd3/uv-common/pymice-react-venv`); it contains `bin/python`, `bin/uvicorn`, `bin/pytest`. So `find_venv()` returns `REPO_ROOT/uv-env` on this machine.
- There is **no** `pymice/uv-env` and **no** pytest config file at the repo root, so running pytest from `pymice/` uses no inherited config.
- `REPO_ROOT` = the `proj-pymice_web/` dir; `PYMICE_DIR` = `proj-pymice_web/pymice/`.
- Run all `pytest` commands below from `pymice/` using the venv interpreter: `../uv-env/bin/python -m pytest …` (works without activating the venv).

## File Structure

- **Create `pymice/run.py`** — the entire control script. One responsibility: orchestrate backend+frontend lifecycle.
- **Create `pymice/tests/conftest.py`** — puts `pymice/` on `sys.path` so `import run` works under pytest.
- **Create `pymice/tests/test_run.py`** — unit tests for the pure helpers.
- **Delete `pymice/run.sh`, `pymice/run.bat`.**
- **Modify `CLAUDE.md`** — Running/Layout sections.
- **Modify `README.md`** — Quick Start.

---

### Task 1: Scaffold `run.py` (importable config block) + test harness

**Files:**
- Create: `pymice/run.py`
- Create: `pymice/tests/conftest.py`
- Test: `pymice/tests/test_run.py`

- [ ] **Step 1: Write the failing test**

Create `pymice/tests/test_run.py`:

```python
import socket
from pathlib import Path

import run


def test_imports_and_constants():
    assert run.BACKEND_PORT == 8765
    assert run.FRONTEND_PORT == 5765
    assert run.PYMICE_DIR.name == "pymice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run'`.

- [ ] **Step 3: Create the conftest so `import run` resolves**

Create `pymice/tests/conftest.py`:

```python
import sys
from pathlib import Path

# Put pymice/ (which contains run.py) on sys.path for `import run`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

- [ ] **Step 4: Create `run.py` with the config block**

Create `pymice/run.py`:

```python
#!/usr/bin/env python3
"""PyMice Web — unified cross-platform control script.

Single entry point replacing the old run.sh / run.bat. Standard library only;
runs under any Python interpreter and locates the project virtualenv itself.

Usage:
    python run.py [start|stop|restart|status|clean|logs {backend,frontend}|update|menu]
    python run.py            # interactive menu
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# --- Paths & config (resolved from this file, CWD-independent) ---------------
PYMICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PYMICE_DIR.parent
BACKEND_DIR = PYMICE_DIR / "backend"
FRONTEND_DIR = PYMICE_DIR / "frontend"
LOG_DIR = PYMICE_DIR / "logs"

BACKEND_PORT = 8765
FRONTEND_PORT = 5765

BACKEND_PID = LOG_DIR / "backend.pid"
FRONTEND_PID = LOG_DIR / "frontend.pid"
BACKEND_LOG = LOG_DIR / "backend.log"
FRONTEND_LOG = LOG_DIR / "frontend.log"

IS_WINDOWS = os.name == "nt"

# --- ANSI colors -------------------------------------------------------------
RESET = "\033[0m"
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"

COLOR_ENABLED = sys.stdout.isatty()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add pymice/run.py pymice/tests/conftest.py pymice/tests/test_run.py
git commit -m "feat(run): scaffold stdlib run.py config block + test harness"
```

---

### Task 2: Virtualenv resolution helpers

**Files:**
- Modify: `pymice/run.py`
- Test: `pymice/tests/test_run.py`

- [ ] **Step 1: Add the failing tests**

Append to `pymice/tests/test_run.py`:

```python
def test_venv_exe_posix():
    venv = Path("/x/venv")
    assert run.venv_exe(venv, "uvicorn", is_windows=False) == venv / "bin" / "uvicorn"


def test_venv_exe_windows():
    venv = Path("/x/venv")
    assert run.venv_exe(venv, "uvicorn", is_windows=True) == venv / "Scripts" / "uvicorn.exe"


def test_venv_candidates_override_first():
    cands = run.venv_candidates(Path("/repo"), Path("/repo/pymice"), "/custom/venv")
    assert cands[0] == Path("/custom/venv")
    assert Path("/repo/uv-env") in cands
    assert Path("/repo/.venv") in cands


def test_venv_candidates_no_override():
    cands = run.venv_candidates(Path("/repo"), Path("/repo/pymice"), None)
    assert cands[0] == Path("/repo/uv-env")


def test_find_venv_picks_first_existing(tmp_path):
    good = tmp_path / "good"
    (good / "bin").mkdir(parents=True)
    (good / "bin" / "python").write_text("")
    assert run.find_venv([tmp_path / "missing", good], is_windows=False) == good


def test_find_venv_none_when_absent(tmp_path):
    assert run.find_venv([tmp_path / "nope"], is_windows=False) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k venv`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'venv_exe'`.

- [ ] **Step 3: Implement the helpers**

Append to `pymice/run.py`:

```python
# --- Virtualenv resolution ---------------------------------------------------
def venv_exe(venv: Path, name: str, is_windows: bool = IS_WINDOWS) -> Path:
    if is_windows:
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def venv_candidates(repo_root: Path, pymice_dir: Path, env_override) -> list:
    cands = []
    if env_override:
        cands.append(Path(env_override))
    cands += [
        repo_root / "uv-env",
        repo_root / ".venv",
        pymice_dir / "uv-env",
        pymice_dir / ".venv",
    ]
    return cands


def find_venv(candidates, is_windows: bool = IS_WINDOWS):
    for cand in candidates:
        if venv_exe(cand, "python", is_windows).exists():
            return cand
    return None


def require_venv() -> Path:
    venv = find_venv(venv_candidates(REPO_ROOT, PYMICE_DIR, os.environ.get("PYMICE_VENV")))
    if venv is None:
        print(colorize("✗ Virtualenv not found.", RED))
        print("  Looked for uv-env / .venv under the repo and pymice/, plus $PYMICE_VENV.")
        print("  Set PYMICE_VENV=/path/to/venv or create the uv-env symlink.")
        sys.exit(1)
    return venv
```

> Note: `require_venv` calls `colorize`, added in Task 6. It is only invoked at runtime (inside `start`), never at import, so the forward reference is fine.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k venv`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add pymice/run.py pymice/tests/test_run.py
git commit -m "feat(run): venv resolution helpers (self-locating, no activation)"
```

---

### Task 3: Port check

**Files:**
- Modify: `pymice/run.py`
- Test: `pymice/tests/test_run.py`

- [ ] **Step 1: Add the failing tests**

Append to `pymice/tests/test_run.py`:

```python
def test_port_in_use_true_for_listening_socket():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert run.port_in_use(port) is True
    finally:
        srv.close()


def test_port_in_use_false_for_closed_port():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()
    assert run.port_in_use(port) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k port`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'port_in_use'`.

- [ ] **Step 3: Implement**

Append to `pymice/run.py`:

```python
# --- Ports -------------------------------------------------------------------
def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k port`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add pymice/run.py pymice/tests/test_run.py
git commit -m "feat(run): stdlib port_in_use (replaces lsof/netstat)"
```

---

### Task 4: Clean targets (preserve list)

**Files:**
- Modify: `pymice/run.py`
- Test: `pymice/tests/test_run.py`

- [ ] **Step 1: Add the failing test**

Append to `pymice/tests/test_run.py`:

```python
def test_clean_targets_preserve_models_experiments_integrations():
    targets = run.clean_dir_targets(Path("/b"), Path("/b/logs"))
    names = {t.name for t in targets}
    assert "roi_templates" in names
    assert "videos" in names and "tracking" in names and "analysis" in names
    assert "models" not in names
    assert "experiments" not in names
    assert all("integrations.json" not in str(t) for t in targets)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k clean_targets`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'clean_dir_targets'`.

- [ ] **Step 3: Implement**

Append to `pymice/run.py`:

```python
# --- Clean -------------------------------------------------------------------
def clean_dir_targets(backend_dir: Path, log_dir: Path) -> list:
    temp = backend_dir / "temp"
    return [
        temp / "videos",
        temp / "tracking",
        temp / "analysis",
        temp / "roi_templates",
        log_dir,
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k clean_targets`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add pymice/run.py pymice/tests/test_run.py
git commit -m "feat(run): clean target list (preserve models/experiments/integrations)"
```

---

### Task 5: Log tail helper

**Files:**
- Modify: `pymice/run.py`
- Test: `pymice/tests/test_run.py`

- [ ] **Step 1: Add the failing tests**

Append to `pymice/tests/test_run.py`:

```python
def test_tail_lines_returns_last_n(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("\n".join(str(i) for i in range(100)))
    lines = run.tail_lines(f, n=50)
    assert lines[0] == "50"
    assert lines[-1] == "99"
    assert len(lines) == 50


def test_tail_lines_missing_file(tmp_path):
    assert run.tail_lines(tmp_path / "nope.log") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k tail`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'tail_lines'`.

- [ ] **Step 3: Implement**

Append to `pymice/run.py`:

```python
# --- Logs --------------------------------------------------------------------
def tail_lines(path: Path, n: int = 50):
    if not path.exists():
        return None
    return path.read_text(errors="replace").splitlines()[-n:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k tail`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add pymice/run.py pymice/tests/test_run.py
git commit -m "feat(run): tail_lines helper for logs command"
```

---

### Task 6: Color helper

**Files:**
- Modify: `pymice/run.py`
- Test: `pymice/tests/test_run.py`

- [ ] **Step 1: Add the failing tests**

Append to `pymice/tests/test_run.py`:

```python
def test_colorize_disabled_returns_raw():
    assert run.colorize("hi", run.RED, enabled=False) == "hi"


def test_colorize_enabled_wraps():
    assert run.colorize("hi", run.RED, enabled=True) == f"{run.RED}hi{run.RESET}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k colorize`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'colorize'`.

- [ ] **Step 3: Implement**

Append to `pymice/run.py`:

```python
# --- Output helpers ----------------------------------------------------------
def colorize(text: str, color: str, enabled=None) -> str:
    if enabled is None:
        enabled = COLOR_ENABLED
    if not enabled:
        return text
    return f"{color}{text}{RESET}"


def _enable_windows_ansi() -> None:
    """Enable ANSI escape processing on legacy Windows consoles (Win10+)."""
    if IS_WINDOWS:
        os.system("")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k colorize`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add pymice/run.py pymice/tests/test_run.py
git commit -m "feat(run): colorize helper + windows ANSI enable"
```

---

### Task 7: Argument parser + command table

**Files:**
- Modify: `pymice/run.py`
- Test: `pymice/tests/test_run.py`

- [ ] **Step 1: Add the failing tests**

Append to `pymice/tests/test_run.py`:

```python
def test_parser_logs_requires_service():
    args = run.build_parser().parse_args(["logs", "backend"])
    assert args.command == "logs"
    assert args.service == "backend"


def test_parser_no_command_is_none():
    args = run.build_parser().parse_args([])
    assert args.command is None


def test_commands_table_matches_parser():
    expected = {"start", "stop", "restart", "status", "clean", "logs", "update", "menu"}
    assert set(run.COMMANDS) == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k "parser or commands_table"`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'build_parser'`.

- [ ] **Step 3: Implement the parser and dispatch table**

Append to `pymice/run.py`. The lambdas reference command functions defined in Tasks 8–10; they are only *called* at runtime via `main()`, so defining the table now is safe (Python resolves the names lazily inside the lambda body).

```python
# --- CLI ---------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run.py", description="PyMice Web control script.")
    sub = parser.add_subparsers(dest="command")
    for name in ("start", "stop", "restart", "status", "clean", "update", "menu"):
        sub.add_parser(name)
    logs_p = sub.add_parser("logs")
    logs_p.add_argument("service", choices=["backend", "frontend"])
    return parser


COMMANDS = {
    "start": lambda args: start(),
    "stop": lambda args: stop(),
    "restart": lambda args: restart(),
    "status": lambda args: status(),
    "clean": lambda args: clean(),
    "logs": lambda args: show_logs(args.service),
    "update": lambda args: update(),
    "menu": lambda args: menu(),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v -k "parser or commands_table"`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add pymice/run.py pymice/tests/test_run.py
git commit -m "feat(run): argparse subcommands + dispatch table"
```

---

### Task 8: `clean()`, `status()`, `show_logs()` implementations

**Files:**
- Modify: `pymice/run.py`

These build on already-tested helpers; verify by running the commands (no new unit tests).

- [ ] **Step 1: Implement the three commands**

Append to `pymice/run.py`:

```python
# --- Process control: pid files ----------------------------------------------
def _read_pid(pidfile: Path):
    try:
        return int(pidfile.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


# --- Commands: clean / status / logs ----------------------------------------
def clean() -> None:
    print(colorize("\U0001f9f9 Cleaning temporaries...", YELLOW))
    for cache in BACKEND_DIR.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    for pyc in BACKEND_DIR.rglob("*.pyc"):
        pyc.unlink(missing_ok=True)
    for target in clean_dir_targets(BACKEND_DIR, LOG_DIR):
        if target.exists():
            for child in target.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        else:
            target.mkdir(parents=True, exist_ok=True)
    print(colorize("✓ Clean done (models, experiments, integrations.json preserved).", GREEN))


def status() -> None:
    print(colorize("\U0001f4ca PyMice Web status", BLUE))
    for name, port, pidfile in (
        ("Backend", BACKEND_PORT, BACKEND_PID),
        ("Frontend", FRONTEND_PORT, FRONTEND_PID),
    ):
        if port_in_use(port):
            pid = _read_pid(pidfile)
            suffix = f" (PID {pid})" if pid else ""
            print(f"  {name}: {colorize('● RUNNING', GREEN)} on {port}{suffix}")
        else:
            print(f"  {name}: {colorize('○ STOPPED', RED)}")
    print()
    print(f"  Frontend:    http://localhost:{FRONTEND_PORT}")
    print(f"  Backend API: http://localhost:{BACKEND_PORT}")
    print(f"  API Docs:    http://localhost:{BACKEND_PORT}/docs")


def show_logs(service: str) -> None:
    log_path = {"backend": BACKEND_LOG, "frontend": FRONTEND_LOG}[service]
    lines = tail_lines(log_path)
    if lines is None:
        print(colorize(f"✗ No log file at {log_path}", RED))
        return
    print(colorize(f"\U0001f4dd Last {len(lines)} lines of {service} log:", BLUE))
    print("\n".join(lines))
```

> Note: `_read_pid` is defined here (above `status`) because `status()` needs it; the remaining process helpers come in Task 9.

- [ ] **Step 2: Verify `clean` runs and preserves protected paths**

Run (from `pymice/`, with a protected file present to prove it survives):

```bash
cd pymice
mkdir -p backend/temp/models backend/temp/experiments
touch backend/temp/models/keep.pt backend/temp/integrations.json
../uv-env/bin/python run.py clean
ls backend/temp/models/keep.pt backend/temp/integrations.json
```

Expected: clean prints the green "Clean done" line; both `keep.pt` and `integrations.json` still exist.

- [ ] **Step 3: Verify `status` runs**

Run: `cd pymice && ../uv-env/bin/python run.py status`
Expected: prints Backend/Frontend STOPPED (assuming nothing running) and the three URLs. No traceback.

- [ ] **Step 4: Commit**

```bash
git add pymice/run.py
git commit -m "feat(run): clean/status/logs command implementations"
```

---

### Task 9: Process control + `start()` / `stop()` / `restart()`

**Files:**
- Modify: `pymice/run.py`

- [ ] **Step 1: Implement process helpers**

Append to `pymice/run.py`:

```python
# --- Process control ---------------------------------------------------------
def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _popen_detached(cmd, cwd: Path, log_path: Path) -> subprocess.Popen:
    log_f = open(log_path, "ab")
    kwargs = dict(
        cwd=str(cwd),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )
    if IS_WINDOWS:
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _stop_pid(pid: int) -> None:
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)  # graceful: lets backend tear down camera
    except (ProcessLookupError, PermissionError):
        return
    for _ in range(50):  # wait up to ~5s for clean exit
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
```

- [ ] **Step 2: Implement `start` / `stop` / `restart`**

Append to `pymice/run.py`:

```python
# --- Commands: start / stop / restart ---------------------------------------
def start() -> None:
    if port_in_use(BACKEND_PORT) and port_in_use(FRONTEND_PORT):
        print(colorize("⚠ Services already running.", YELLOW))
        status()
        return

    venv = require_venv()
    npm = shutil.which("npm")
    if shutil.which("node") is None or npm is None:
        print(colorize("✗ node/npm not found in PATH.", RED))
        sys.exit(1)

    clean()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for sub in ("videos", "models", "tracking", "analysis"):
        (BACKEND_DIR / "temp" / sub).mkdir(parents=True, exist_ok=True)

    if not port_in_use(BACKEND_PORT):
        print(colorize("\U0001f40d Starting backend...", BLUE))
        proc = _popen_detached(
            [str(venv_exe(venv, "uvicorn")), "app.main:app",
             "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
            cwd=BACKEND_DIR,
            log_path=BACKEND_LOG,
        )
        BACKEND_PID.write_text(str(proc.pid))
        print(colorize(f"✓ Backend started (PID {proc.pid})", GREEN))

    if not port_in_use(FRONTEND_PORT):
        if not (FRONTEND_DIR / "node_modules").exists():
            print("  Installing frontend deps (npm install)...")
            subprocess.run([npm, "install"], cwd=str(FRONTEND_DIR), check=False)
        print(colorize("⚛ Starting frontend...", BLUE))
        proc = _popen_detached(
            [npm, "run", "dev", "--", "--host", "0.0.0.0", "--port", str(FRONTEND_PORT)],
            cwd=FRONTEND_DIR,
            log_path=FRONTEND_LOG,
        )
        FRONTEND_PID.write_text(str(proc.pid))
        print(colorize(f"✓ Frontend started (PID {proc.pid})", GREEN))

    print()
    print(colorize(f"\U0001f4f1 Open: http://localhost:{FRONTEND_PORT}", CYAN))


def stop() -> None:
    print(colorize("\U0001f6d1 Stopping PyMice Web...", YELLOW))
    stopped = False
    for name, pidfile in (("Backend", BACKEND_PID), ("Frontend", FRONTEND_PID)):
        pid = _read_pid(pidfile)
        if pid is not None:
            print(f"  Stopping {name} (PID {pid})...")
            _stop_pid(pid)
            stopped = True
        pidfile.unlink(missing_ok=True)
    for name, port in (("Backend", BACKEND_PORT), ("Frontend", FRONTEND_PORT)):
        if port_in_use(port):
            print(colorize(f"⚠ {name} port {port} still bound — check manually.", YELLOW))
    print(colorize("✓ Services stopped." if stopped else "⚠ Nothing was running.",
                   GREEN if stopped else YELLOW))


def restart() -> None:
    stop()
    time.sleep(2)
    start()
```

- [ ] **Step 3: Smoke test the full lifecycle**

Run from `pymice/` (this starts the real servers):

```bash
cd pymice
../uv-env/bin/python run.py start
sleep 6
../uv-env/bin/python run.py status
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/docs
../uv-env/bin/python run.py stop
../uv-env/bin/python run.py status
```

Expected:
- `start` prints backend + frontend PIDs.
- first `status` shows both `RUNNING`.
- curl prints `200`.
- `stop` prints "Services stopped." with no "still bound" warnings.
- second `status` shows both `STOPPED`.

If a "still bound" warning appears, wait 2s and re-run `status`; if still bound, inspect `logs/*.log`.

- [ ] **Step 4: Commit**

```bash
git add pymice/run.py
git commit -m "feat(run): start/stop/restart with process-group teardown (SIGTERM first)"
```

---

### Task 10: `update()`, `menu()`, `main()` + entry point

**Files:**
- Modify: `pymice/run.py`

- [ ] **Step 1: Implement update, menu, main**

Append to `pymice/run.py`:

```python
# --- Commands: update / menu ------------------------------------------------
def update() -> None:
    print(colorize("⬇ git pull...", BLUE))
    result = subprocess.run(["git", "-C", str(REPO_ROOT), "pull"])
    if result.returncode == 0:
        print(colorize("✓ Updated.", GREEN))
    else:
        print(colorize("✗ git pull failed.", RED))
        sys.exit(result.returncode)


MENU_TEXT = """
PyMice Web — control
  1) Start      2) Stop       3) Restart    4) Status
  5) Backend logs   6) Frontend logs   7) Clean
  0) Exit
"""


def menu() -> None:
    actions = {
        "1": start,
        "2": stop,
        "3": restart,
        "4": status,
        "5": lambda: show_logs("backend"),
        "6": lambda: show_logs("frontend"),
        "7": clean,
    }
    while True:
        print(colorize(MENU_TEXT, CYAN))
        try:
            choice = input("Choose: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice == "0":
            return
        action = actions.get(choice)
        if action is None:
            print(colorize("Invalid option.", RED))
            continue
        action()
        input("\nPress Enter to continue...")


# --- Entry point -------------------------------------------------------------
def main(argv=None) -> None:
    _enable_windows_ansi()
    args = build_parser().parse_args(argv)
    if args.command is None:
        menu()
        return
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full unit-test suite (no regressions)**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v`
Expected: PASS (all tests from Tasks 1–7 green).

- [ ] **Step 3: Smoke test the CLI surface**

```bash
cd pymice
../uv-env/bin/python run.py --help
echo 0 | ../uv-env/bin/python run.py menu
```

Expected:
- `--help` lists subcommands `start stop restart status clean update menu logs`.
- piping `0` into `menu` prints the menu once and exits cleanly (exit code 0).

> Do **not** run `run.py update` here — it performs a real `git pull` on the current branch. Its wiring is already confirmed by `update` appearing in `--help` and the `test_commands_table_matches_parser` unit test. Verify `update` manually only when you actually intend to pull.

- [ ] **Step 4: Commit**

```bash
git add pymice/run.py
git commit -m "feat(run): update/menu/main entry point + dispatch wiring"
```

---

### Task 11: Delete the old shell scripts

**Files:**
- Delete: `pymice/run.sh`, `pymice/run.bat`

- [ ] **Step 1: Remove both scripts**

```bash
git rm pymice/run.sh pymice/run.bat
```

- [ ] **Step 2: Confirm nothing else references them**

Run: `grep -rn --include='*.md' --include='*.sh' --include='*.json' -e 'run\.sh' -e 'run\.bat' . | grep -v docs/superpowers`
Expected: only matches inside `CLAUDE.md` / `README.md` (handled in Tasks 12–13). If any script/config references them, note it for follow-up.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(run): remove run.sh and run.bat (superseded by run.py)"
```

---

### Task 12: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Layout block**

Replace:

```
│   ├── run.sh            # Unified start/stop/status script
```

with:

```
│   ├── run.py            # Unified cross-platform start/stop/status script (stdlib)
```

- [ ] **Step 2: Update the first two Running bullets**

Replace this bullet:

```
- Preferred: `./pymice/run.sh start` (also: `status`, `stop`, `restart`, `clean`, `logs [backend|frontend]`, or run with no args for interactive menu). `run.sh` uses relative paths, so launch it from `pymice/`. A `run.bat` exists for Windows; keep it in sync if you change `run.sh` semantics.
```

with:

```
- Preferred: `python pymice/run.py start` (also: `status`, `stop`, `restart`, `clean`, `logs [backend|frontend]`, `update`, or run with no args for interactive menu). `run.py` is stdlib-only and resolves every path from its own location, so it runs from any CWD. It is the single cross-platform entry point (the old `run.sh`/`run.bat` were removed).
```

Replace this bullet:

```
- **`run.sh` does not activate the venv** — it requires `$VIRTUAL_ENV` to already be set and will exit with an error otherwise. Activate `uv-env/bin/activate` first. (README.md claims `run.sh` auto-activates the environment — that is stale; trust this file.)
```

with:

```
- **`run.py` locates the venv itself** — it searches `uv-env`/`.venv` (repo root, then `pymice/`) and `$PYMICE_VENV`, then calls that venv's `uvicorn` directly. No `source .../activate` needed; invoke it with the system Python.
```

- [ ] **Step 3: Update the clean/startup bullet's first clause**

Replace the opening of the third Running bullet:

```
- `run.sh start` also calls `clean_temporaries` and the backend `startup_event` clears
```

with:

```
- `run.py start` also runs its `clean()` step and the backend `startup_event` clears
```

(Leave the remainder of that bullet — the temp/preserved-paths detail — unchanged.)

- [ ] **Step 4: Verify no stale references remain**

Run: `grep -n -e 'run\.sh' -e 'run\.bat' CLAUDE.md`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): point Running/Layout at run.py"
```

---

### Task 13: Update `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the unified-script section**

In the "Recommended Method: Unified Script" section, replace the `run.sh` usage block:

````
```bash
# Make script executable (first time)
chmod +x run.sh

# Start frontend + backend
./run.sh start

# Check services status
./run.sh status

# Stop services
./run.sh stop

# Restart
./run.sh restart

# Interactive menu
./run.sh
```
````

with:

````
```bash
# Start frontend + backend (run from pymice/)
python run.py start

# Check services status
python run.py status

# Stop services
python run.py stop

# Restart
python run.py restart

# Interactive menu
python run.py
```
````

- [ ] **Step 2: Fix the stale venv claim**

Replace:

```
- `run.sh` automatically activates the correct environment
```

with:

```
- `run.py` locates the venv automatically (uv-env / .venv / $PYMICE_VENV) — no manual activation needed
```

- [ ] **Step 3: Verify no stale references remain**

Run: `grep -n -e 'run\.sh' -e 'run\.bat' README.md`
Expected: no output (or only inside a "Manual Installation" section that intentionally shows `uvicorn` directly — if `run.sh`/`run.bat` still appear there, replace with `python run.py` equivalents).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): quick start uses run.py"
```

---

### Task 14: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Byte-compile the script**

Run: `cd pymice && ../uv-env/bin/python -m py_compile run.py`
Expected: no output, exit 0 (no syntax errors).

- [ ] **Step 2: Full unit-test suite**

Run: `cd pymice && ../uv-env/bin/python -m pytest tests/test_run.py -v`
Expected: all tests pass.

- [ ] **Step 3: End-to-end lifecycle once more**

```bash
cd pymice
../uv-env/bin/python run.py start
sleep 6
../uv-env/bin/python run.py status      # both RUNNING
../uv-env/bin/python run.py logs backend | tail -5
../uv-env/bin/python run.py stop
../uv-env/bin/python run.py status      # both STOPPED
```

Expected: start → RUNNING → logs show uvicorn startup lines → stop → STOPPED, with no Python tracebacks and no "still bound" warnings after stop.

- [ ] **Step 4: Confirm the backend's existing pytest suite is untouched**

Run: `cd pymice/backend && ../../uv-env/bin/python -m pytest -q`
Expected: the pre-existing experiment-recording suite still passes (this change touched nothing under `backend/`).

- [ ] **Step 5: Final review of the working tree**

Run: `git status` and `git log --oneline -14`
Expected: clean tree (only the intended new/deleted/modified files committed); the task commits are present in order.

---

## Self-Review Notes

- **Spec coverage:** single stdlib `run.py` (Tasks 1–10) ✓; delete both scripts (Task 11) ✓; self-locating venv + `PYMICE_VENV` override (Task 2) ✓; `port_in_use` replacing lsof/netstat (Task 3) ✓; graceful SIGTERM + process-group kill (Task 9) ✓; clean preserve-list (Task 4) ✓; logs as dump, no follow (Tasks 5/8) ✓; `update` + interactive menu (Tasks 7/10) ✓; CWD-independence (Task 1 constants) ✓; docs updates (Tasks 12–13) ✓; helper unit tests + manual smoke (Tasks 1–10, 14) ✓.
- **Type/name consistency:** `venv_exe`, `venv_candidates`, `find_venv`, `require_venv`, `port_in_use`, `clean_dir_targets`, `tail_lines`, `colorize`, `build_parser`, `COMMANDS`, `_read_pid`, `_pid_alive`, `_popen_detached`, `_stop_pid`, `start`/`stop`/`restart`/`status`/`clean`/`show_logs`/`update`/`menu`/`main` — names are used identically across tasks and the dispatch table.
- **Forward references:** `COMMANDS`/`require_venv`/`status`/`show_logs` reference functions defined in later tasks but only invoke them at runtime (never at import), so partial-file states between tasks still import cleanly; unit tests added per task only touch helpers already defined by that task.
