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


# --- Ports -------------------------------------------------------------------
def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


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


# --- Logs --------------------------------------------------------------------
def tail_lines(path: Path, n: int = 50):
    if not path.exists():
        return None
    return path.read_text(errors="replace").splitlines()[-n:]


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


# --- Process control: pid files ----------------------------------------------
def _read_pid(pidfile: Path):
    try:
        return int(pidfile.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


# --- Commands: clean / status / logs ----------------------------------------
def clean() -> None:
    print(colorize("🧹 Cleaning temporaries...", YELLOW))
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
    print(colorize("📊 PyMice Web status", BLUE))
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
    print(colorize(f"📝 Last {len(lines)} lines of {service} log:", BLUE))
    print("\n".join(lines))


# --- Process control ---------------------------------------------------------
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


def _terminate_pid(pid: int) -> None:
    """Graceful stop: SIGTERM the whole process group (lets the backend tear down
    its camera). On Windows, taskkill /T kills the process tree."""
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def _kill_pid(pid: int) -> None:
    """Force-kill the process group (POSIX SIGKILL); taskkill already forced on Windows."""
    if IS_WINDOWS:
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _wait_port_free(port: int, timeout: float) -> bool:
    """Poll until the port is released, up to `timeout` seconds."""
    steps = max(1, int(timeout / 0.2))
    for _ in range(steps):
        if not port_in_use(port):
            return True
        time.sleep(0.2)
    return not port_in_use(port)


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
        print(colorize("🐍 Starting backend...", BLUE))
        # Invoke via `python -m uvicorn` (not the uvicorn console-script): the
        # venv's console-scripts carry a stale shebang from a prior venv path,
        # so exec'ing them fails; `python -m` uses the interpreter directly.
        proc = _popen_detached(
            [str(venv_exe(venv, "python")), "-m", "uvicorn", "app.main:app",
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
    print(colorize(f"📱 Open: http://localhost:{FRONTEND_PORT}", CYAN))


def stop() -> None:
    print(colorize("🛑 Stopping PyMice Web...", YELLOW))
    targets = []  # (name, pid, port)
    for name, pidfile, port in (
        ("Backend", BACKEND_PID, BACKEND_PORT),
        ("Frontend", FRONTEND_PID, FRONTEND_PORT),
    ):
        pid = _read_pid(pidfile)
        if pid is not None:
            print(f"  Stopping {name} (PID {pid})...")
            _terminate_pid(pid)  # SIGTERM the group first
            targets.append((name, pid, port))
        pidfile.unlink(missing_ok=True)

    if not targets:
        print(colorize("⚠ Nothing was running.", YELLOW))
        return

    # Give each service a graceful window to release its port; vite in
    # particular lingers a beat after SIGTERM. Force-kill stragglers.
    for name, pid, port in targets:
        if not _wait_port_free(port, timeout=6.0):
            print(colorize(f"  {name} slow to exit — forcing...", YELLOW))
            _kill_pid(pid)
            _wait_port_free(port, timeout=3.0)

    still = [name for name, pid, port in targets if port_in_use(port)]
    if still:
        print(colorize(f"⚠ Still bound: {', '.join(still)} — check manually.", YELLOW))
    else:
        print(colorize("✓ Services stopped.", GREEN))


def restart() -> None:
    stop()
    time.sleep(2)
    start()


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
  1) Start
  2) Stop
  3) Restart
  4) Status
  5) Backend logs
  6) Frontend logs
  7) Clean
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
