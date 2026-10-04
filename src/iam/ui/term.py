"""Terminal control and escape processing helpers."""

import ctypes
import sys

# Win32 API constants (WinBase.h / WinCon.h)
# STD_OUTPUT_HANDLE: Standard output device identifier (-11)
STD_OUTPUT_HANDLE: int = -11

# ENABLE_VIRTUAL_TERMINAL_PROCESSING: Flag (0x0004) for SetConsoleMode to enable ANSI/VT sequence parsing
ENABLE_VIRTUAL_TERMINAL_PROCESSING: int = 0x0004

# INVALID_HANDLE_VALUE: Value (-1) returned when GetStdHandle fails
INVALID_HANDLE_VALUE: int = -1

# ANSI escape sequence: \033[2J clears the full screen, \033[H repositions cursor to row 1, col 1
ANSI_CLEAR_SCREEN: str = "\033[2J\033[H"

_vt_initialized: bool = False


def enable_windows_vt() -> bool:
    """Enable ANSI/VT escape sequence processing on Windows console stdout.

    Returns True if successfully enabled, False on failure or unsupported platforms.
    Never raises an exception (e.g. when stdout is not attached to a console).
    """
    if sys.platform != "win32":
        return False

    try:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        kernel32 = getattr(windll, "kernel32", None)
        if kernel32 is None:
            return False

        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        if handle in (None, 0, INVALID_HANDLE_VALUE):
            return False

        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False

        new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if not kernel32.SetConsoleMode(handle, new_mode):
            return False

        return True
    except Exception:
        return False


def clear_screen() -> None:
    """Clear the terminal screen and move cursor to home position via ANSI escapes.

    Does not spawn a subprocess. Lazily enables Windows virtual terminal
    processing once on win32.
    """
    global _vt_initialized
    if sys.platform == "win32" and not _vt_initialized:
        enable_windows_vt()
        _vt_initialized = True

    sys.stdout.write(ANSI_CLEAR_SCREEN)
    sys.stdout.flush()
