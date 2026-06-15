# Design: Single Python Orchestrator (`run.py`)

- **Date:** 2026-06-15
- **Status:** Approved (design phase)
- **Author:** Helton Maia (with Claude Code)
- **Topic:** Replace `pymice/run.sh` and `pymice/run.bat` with one cross-platform, stdlib-only `pymice/run.py`.

## Context & Motivation

The project ships two launchers that have drifted apart and accumulated platform-specific bugs:

| Aspect | `run.sh` (Linux) | `run.bat` (Windows) |
|---|---|---|
| Logs | working `tail -f` | `backlogs`/`frontlogs` are **broken stubs** (just `echo`) |
| `update` (git pull) | absent | present |
| Venv | **requires** `$VIRTUAL_ENV` already active, refuses to run otherwise | **activates** it (`activate.bat`) |
| PID detection | real PID of the launched process | `tasklist \| findstr node` — fragile, grabs the first matching node/uvicorn, can kill the wrong process |
| Dependency checks | verifies `python3`/`node` | none |

Maintaining two sources of truth means every change must be ported by hand, and the Windows side is already behind. A single stdlib Python orchestrator gives one source of truth, fixes the Windows bugs, and is genuinely cross-platform.

## Goals

- One entry point: `python run.py <command>` works identically on Linux, macOS, and Windows.
- Zero install: runs under **any** Python (system interpreter included), using only the standard library, **before** any virtualenv is active.
- The script locates the project virtualenv itself and invokes its executables directly — no "activation" step required.
- Behavioral parity with today's `run.sh` core, plus the `update` command and interactive menu, minus the Windows bugs.

## Non-Goals

- No production/serving mode. Frontend stays dev-only (`npm run dev`), matching current behavior. (YAGNI.)
- No third-party dependencies (`rich`, `click`, `colorama`, etc.).
- No process supervision/auto-restart/daemonization beyond detached start + PID files.
- No changes to backend/frontend application code.

## Resolved Decisions

1. **Scope:** Delete both `run.sh` and `run.bat`. `run.py` is the single entry point.
2. **Dependencies:** Standard library only. Runs with the system Python.
3. **Internal structure:** Single file `pymice/run.py` (functions per command + `argparse` dispatch). Not a package.
4. **Extras kept:** interactive menu (no-arg) and `update` (git pull).
5. **`logs`:** prints the last ~50 lines of the log file and exits — no live follow (keeps it fully stdlib/cross-platform).
6. **`clean`:** keeps `temp/roi_templates` in the wipe list. Preserves `temp/models`, `temp/experiments`, `temp/integrations.json`.
7. **Venv override:** `PYMICE_VENV` environment variable is supported as an override.

## Architecture

Single file `pymice/run.py`:

- Shebang `#!/usr/bin/env python3`; marked executable.
- Standard library only: `argparse`, `subprocess`, `socket`, `os`, `sys`, `signal`, `shutil`, `pathlib`, `time`, `platform`.
- **All paths resolve from `Path(__file__).resolve().parent`** (the `pymice/` dir), so the script is CWD-independent — an improvement over `run.sh`, which must be invoked from `pymice/`.
- Dispatch via `argparse` subcommands; running with no arguments opens the interactive menu.

Key path constants (derived, not hardcoded):
- `PYMICE_DIR = Path(__file__).resolve().parent`
- `REPO_ROOT = PYMICE_DIR.parent`
- `BACKEND_DIR = PYMICE_DIR / "backend"`
- `FRONTEND_DIR = PYMICE_DIR / "frontend"`
- `LOG_DIR = PYMICE_DIR / "logs"`
- `BACKEND_PORT = 8765`, `FRONTEND_PORT = 5765`

## Components (functions in the file)

### Virtualenv resolution
- `find_venv() -> Path`: returns the first existing candidate, in order:
  1. `$PYMICE_VENV` (if set)
  2. `REPO_ROOT / "uv-env"`
  3. `REPO_ROOT / ".venv"`
  4. `PYMICE_DIR / "uv-env"`
  5. `PYMICE_DIR / ".venv"`

  A candidate counts as valid only if its platform bin dir contains a `python`/`python.exe`. If none found → exit with a clear message pointing at `uv-env` / `PYMICE_VENV`.
- `venv_exe(name) -> Path`: `<venv>/bin/<name>` on POSIX, `<venv>/Scripts/<name>.exe` on Windows. Used to call `uvicorn` directly — **no activation**.

### Port check
- `port_in_use(port) -> bool`: `socket.socket().connect_ex(("127.0.0.1", port)) == 0`. Replaces `lsof` (Linux) and `netstat | findstr` (Windows) with one stdlib check.

### Start
- `start()`:
  1. If both ports already in use → print status, exit 0.
  2. Verify dependencies: `shutil.which("node")`, `shutil.which("npm")`, and `find_venv()`. Missing → clear error, non-zero exit. (Fixes `run.bat`, which checked nothing.)
  3. `mkdir -p logs` and `backend/temp/{videos,models,tracking,analysis}`.
  4. Backend: launch `venv_exe("uvicorn") app.main:app --host 0.0.0.0 --port 8765`, cwd=`BACKEND_DIR`, stdout/stderr → `logs/backend.log`, detached. Write PID → `logs/backend.pid`.
  5. Frontend: `npm install` if `frontend/node_modules` is missing, then `npm run dev -- --host 0.0.0.0 --port 5765`, cwd=`FRONTEND_DIR`, stdout/stderr → `logs/frontend.log`, detached. Write PID → `logs/frontend.pid`.
  6. Print success banner + URLs.
- **Detached launch, per OS:**
  - POSIX: `subprocess.Popen(..., start_new_session=True)` so each child leads its own process group. (Cleanly covers `npm run dev` → `vite` children.)
  - Windows: `creationflags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`.

### Stop
- `stop()`:
  1. For each of backend/frontend, read the PID file and terminate the **whole process group**:
     - POSIX: `os.killpg(os.getpgid(pid), SIGTERM)`, wait up to ~5s, then `SIGKILL` if still alive.
     - Windows: `taskkill /PID <pid> /T /F`.
  2. **SIGTERM first** (not an immediate kill): lets the backend run its `experiment → camera → watchdog` shutdown so the camera LED is released (per CLAUDE.md). This is a correctness improvement over `run.bat`'s immediate `/F`.
  3. Remove PID files. Stale/missing PID files are tolerated (warn, continue).
  4. Killing the process group makes the orphaned-`vite` problem moot, so the `lsof`-based port fallback from `run.sh` is not needed. If a port is still bound after the group kill, print a warning telling the user to check manually (no stdlib-only cross-platform "kill by port").

### Status
- `status()`: per service, port check + PID (from PID file, if present) + the three URLs (frontend, backend API, API docs).

### Clean
- `clean()`:
  - Remove every `__pycache__` dir and `*.pyc` under `backend/`.
  - Empty (contents only) `backend/temp/{videos,tracking,analysis,roi_templates}` and `logs/`, creating any that are missing.
  - **Preserve** `backend/temp/models`, `backend/temp/experiments`, `backend/temp/integrations.json`.

### Logs
- `logs(service)`: validate `service in {backend, frontend}`; print the last ~50 lines of `logs/<service>.log` (or a "no log yet" notice) and exit. No live follow.

### Update
- `update()`: `git -C REPO_ROOT pull`, streaming output; report success/failure by return code.

### Menu
- `menu()`: numeric interactive menu (parity with the existing scripts): Start / Stop / Restart / Status / Backend logs / Frontend logs / Clean / Exit. Loops until Exit.

### Output / colors
- ANSI color constants. Enable virtual-terminal processing on Windows (`os.system("")` / `ctypes` `SetConsoleMode`). Colors are suppressed when `not sys.stdout.isatty()`.

### CLI dispatch
- `argparse` with subcommands: `start`, `stop`, `restart`, `status`, `clean`, `logs {backend,frontend}`, `update`, `menu`. No subcommand → `menu()`.
- `restart()` = `stop()` + short pause + `start()`.

## Error Handling

- Missing venv → message naming the searched candidates and `PYMICE_VENV`.
- Missing `node`/`npm` → message naming the missing tool; non-zero exit.
- Already running (both ports up) → print status, exit 0 (not an error).
- Orphan/stale PID file → warn and continue (don't crash).
- `git pull` failure (`update`) → surface the non-zero exit and stderr.

## Testing Strategy

- **Unit (pytest), pure helpers only** — new file `pymice/tests/test_run.py`, no asyncio:
  - `venv_exe()` path construction per platform (monkeypatch `os.name` / `platform.system`).
  - venv candidate search order in `find_venv()` (tmp dirs).
  - `clean` target list (assert `models`/`experiments`/`integrations.json` are NOT in the wipe set; `roi_templates` IS).
  - argparse dispatch table maps each command to the right handler.
- **Manual smoke test** for the real process lifecycle (`start` → `status` → `logs` → `stop`) on Linux; Windows verified by the Windows maintainer.
- Process-spawning paths are not unit-tested (subprocess/OS-bound); they are covered by the smoke test.

## Files Touched

- **Add:** `pymice/run.py`, `pymice/tests/test_run.py`.
- **Delete:** `pymice/run.sh`, `pymice/run.bat`.
- **Update docs:**
  - `CLAUDE.md` — "Running" / "Commands" sections: replace `run.sh`/`run.bat` references with `python run.py …`; drop the "does not activate the venv" caveat (no longer applicable); note the script is CWD-independent and resolves the venv itself.
  - `README.md` — Quick Start: replace the `run.sh` block with `python run.py …`.
