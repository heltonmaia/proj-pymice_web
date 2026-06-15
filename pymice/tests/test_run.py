import socket
from pathlib import Path

import run


def test_imports_and_constants():
    assert run.BACKEND_PORT == 8765
    assert run.FRONTEND_PORT == 5765
    assert run.PYMICE_DIR.name == "pymice"
