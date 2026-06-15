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
