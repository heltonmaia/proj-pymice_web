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
