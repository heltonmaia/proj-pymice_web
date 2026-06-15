import socket
from pathlib import Path

import run


def test_imports_and_constants():
    assert run.BACKEND_PORT == 8765
    assert run.FRONTEND_PORT == 5765
    assert run.PYMICE_DIR.name == "pymice"


# --- venv resolution ---------------------------------------------------------
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


# --- ports -------------------------------------------------------------------
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


# --- clean targets -----------------------------------------------------------
def test_clean_targets_preserve_models_experiments_integrations():
    targets = run.clean_dir_targets(Path("/b"), Path("/b/logs"))
    names = {t.name for t in targets}
    assert "roi_templates" in names
    assert "videos" in names and "tracking" in names and "analysis" in names
    assert "models" not in names
    assert "experiments" not in names
    assert all("integrations.json" not in str(t) for t in targets)


# --- log tail ----------------------------------------------------------------
def test_tail_lines_returns_last_n(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("\n".join(str(i) for i in range(100)))
    lines = run.tail_lines(f, n=50)
    assert lines[0] == "50"
    assert lines[-1] == "99"
    assert len(lines) == 50


def test_tail_lines_missing_file(tmp_path):
    assert run.tail_lines(tmp_path / "nope.log") is None


# --- colorize ----------------------------------------------------------------
def test_colorize_disabled_returns_raw():
    assert run.colorize("hi", run.RED, enabled=False) == "hi"


def test_colorize_enabled_wraps():
    assert run.colorize("hi", run.RED, enabled=True) == f"{run.RED}hi{run.RESET}"


# --- parser / dispatch -------------------------------------------------------
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
