"""Tests for os.system cleanup and terminal helper functions."""

import io
import os
import pathlib
import subprocess
import sys
from unittest.mock import MagicMock


def test_clear_screen_writes_ansi_and_no_subprocess(monkeypatch):
    """clear_screen writes exactly '\033[2J\033[H' to stdout and invokes no subprocess."""
    from iam.ui.term import clear_screen

    # Patch os.system and subprocess to ensure no subprocess is spawned
    def boom(*args, **kwargs):
        raise AssertionError("Subprocess or os.system should not be invoked")

    monkeypatch.setattr(os, "system", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "call", boom)
    monkeypatch.setattr(subprocess, "check_call", boom)

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)

    clear_screen()
    assert buf.getvalue() == "\033[2J\033[H"


def test_enable_windows_vt_non_win32(monkeypatch):
    """enable_windows_vt returns False without raising on non-win32."""
    from iam.ui.term import enable_windows_vt

    monkeypatch.setattr(sys, "platform", "linux")
    assert enable_windows_vt() is False

    monkeypatch.setattr(sys, "platform", "darwin")
    assert enable_windows_vt() is False


def test_enable_windows_vt_ctypes_failure(monkeypatch):
    """enable_windows_vt returns False without raising when ctypes calls fail."""
    from iam.ui.term import enable_windows_vt

    monkeypatch.setattr(sys, "platform", "win32")

    import ctypes

    mock_windll = MagicMock()
    mock_kernel32 = MagicMock()
    # GetStdHandle fails (returns 0 or invalid)
    mock_kernel32.GetStdHandle.return_value = 0
    mock_windll.kernel32 = mock_kernel32
    monkeypatch.setattr(ctypes, "windll", mock_windll, raising=False)

    assert enable_windows_vt() is False

    # Simulate GetConsoleMode failing
    mock_kernel32.GetStdHandle.return_value = 1234
    mock_kernel32.GetConsoleMode.return_value = 0
    assert enable_windows_vt() is False

    # Simulate SetConsoleMode failing
    mock_kernel32.GetConsoleMode.return_value = 1
    mock_kernel32.SetConsoleMode.return_value = 0
    assert enable_windows_vt() is False

    # Simulate exception in ctypes
    mock_kernel32.GetConsoleMode.side_effect = RuntimeError("Console error")
    assert enable_windows_vt() is False


def test_enable_windows_vt_success(monkeypatch):
    """enable_windows_vt returns True when console mode is updated."""
    from iam.ui.term import ENABLE_VIRTUAL_TERMINAL_PROCESSING, STD_OUTPUT_HANDLE, enable_windows_vt

    monkeypatch.setattr(sys, "platform", "win32")

    import ctypes

    mock_windll = MagicMock()
    mock_kernel32 = MagicMock()
    mock_kernel32.GetStdHandle.return_value = 1234

    # GetConsoleMode succeeds and sets mode
    def fake_get_console_mode(handle, mode_ref):
        mode_ref._obj.value = 0x0001
        return 1

    mock_kernel32.GetConsoleMode.side_effect = fake_get_console_mode
    mock_kernel32.SetConsoleMode.return_value = 1
    mock_windll.kernel32 = mock_kernel32
    monkeypatch.setattr(ctypes, "windll", mock_windll, raising=False)

    assert enable_windows_vt() is True
    mock_kernel32.GetStdHandle.assert_called_with(STD_OUTPUT_HANDLE)
    mock_kernel32.SetConsoleMode.assert_called_with(
        1234, 0x0001 | ENABLE_VIRTUAL_TERMINAL_PROCESSING
    )


def test_clear_screen_lazy_vt_on_win32(monkeypatch):
    """clear_screen calls enable_windows_vt lazily once on win32."""
    import iam.ui.term as term

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(term, "_vt_initialized", False)

    vt_calls = []
    monkeypatch.setattr(term, "enable_windows_vt", lambda: vt_calls.append(1) or True)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)

    term.clear_screen()
    assert len(vt_calls) == 1

    # Second call should not invoke enable_windows_vt again
    term.clear_screen()
    assert len(vt_calls) == 1


def test_launcher_diagnostics_calls_subprocess_run(monkeypatch):
    """Launcher diagnostics runs scripts/verify.py via subprocess.run without shell=True."""
    import iam.launcher as launcher

    calls = []

    def mock_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", mock_run)

    launcher.run_diagnostics()

    assert len(calls) == 1
    argv, kwargs = calls[0]
    expected_verify = str(
        pathlib.Path(launcher.__file__).resolve().parent.parent.parent / "scripts" / "verify.py"
    )
    assert argv == [sys.executable, expected_verify]
    assert kwargs.get("shell") is not True
    assert kwargs.get("check") is False


def test_launcher_diagnostics_script_missing(monkeypatch, capsys):
    """Launcher diagnostics prints a clear message if verify.py is missing."""
    import iam.launcher as launcher

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kwargs: calls.append(argv))

    orig_is_file = pathlib.Path.is_file

    def fake_is_file(p):
        if "verify.py" in str(p):
            return False
        return orig_is_file(p)

    monkeypatch.setattr(pathlib.Path, "is_file", fake_is_file)

    launcher.run_diagnostics()

    assert len(calls) == 0
    captured = capsys.readouterr()
    assert (
        "not found" in captured.out.lower()
        or "not found" in captured.err.lower()
        or "missing" in captured.out.lower()
    )


def test_launcher_main_menu_choice_d(monkeypatch):
    """Option D in launcher.main_menu runs diagnostics."""
    import iam.launcher as launcher

    calls = []
    monkeypatch.setattr(launcher, "clear_screen", lambda: None)
    monkeypatch.setattr(launcher, "display_welcome_dashboard", lambda: None)
    monkeypatch.setattr(launcher, "run_diagnostics", lambda: calls.append("diagnostics"))

    inputs = iter(["D", "", "Q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    launcher.main_menu()
    assert calls == ["diagnostics"]


def test_alpha_terminal_uses_enable_windows_vt(monkeypatch):
    """alpha_terminal.start uses enable_windows_vt instead of os.system on win32."""
    import iam.ui.alpha_terminal as terminal

    def boom(*args, **kwargs):
        raise AssertionError("os.system was called")

    monkeypatch.setattr(os, "system", boom)
    monkeypatch.setattr(sys, "platform", "win32")

    vt_enabled = []
    monkeypatch.setattr(terminal, "enable_windows_vt", lambda: vt_enabled.append(True) or True)

    term = terminal.AlphaTerminal()
    monkeypatch.setattr(term, "_resize", lambda: None)
    monkeypatch.setattr(term, "_async_load", lambda x: None)
    monkeypatch.setattr(term, "_async_load_system", lambda: None)
    monkeypatch.setattr(term, "_main_loop", lambda: None)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)

    term.start()
    assert len(vt_enabled) == 1


def test_no_os_system_in_src_iam():
    """Verify that no 'os.system(' calls remain in src/iam."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    src_iam = repo_root / "src" / "iam"
    violations = []

    for py_file in src_iam.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if "os.system(" in line:
                violations.append(f"{py_file.relative_to(repo_root)}:{line_no}: {line.strip()}")

    assert not violations, "Found os.system calls in src/iam:\n" + "\n".join(violations)
