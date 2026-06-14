#!/usr/bin/env python3
"""Cross-platform utility to create a desktop shortcut for Institutional Alpha."""

import os
import sys
import subprocess
from pathlib import Path

def create_windows_shortcut(repo_root: Path) -> tuple[bool, str]:
    """Create a Windows desktop shortcut (.lnk) via PowerShell WScript.Shell."""
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if not desktop.exists():
        return False, "Could not locate Desktop directory."

    target_exe = repo_root / "Run_Alpha_Terminal.exe"
    if not target_exe.exists():
        # Fallback to run.py if the exe launcher is not found
        target_exe = repo_root / "run.py"

    shortcut_path = desktop / "Institutional Alpha Terminal.lnk"

    # PowerShell command to create the shortcut
    ps_cmd = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
    $Shortcut.TargetPath = "{target_exe}"
    $Shortcut.WorkingDirectory = "{repo_root}"
    """

    if target_exe.suffix == ".py":
        # If pointing to run.py, run it with python interpreter
        python_exe = sys.executable
        ps_cmd += f"""
        $Shortcut.TargetPath = "{python_exe}"
        $Shortcut.Arguments = "run.py --terminal"
        """

    ps_cmd += """
    $Shortcut.Save()
    """

    try:
        subprocess.run(
            ["powershell", "-Command", ps_cmd],
            check=True,
            capture_output=True,
            text=True
        )
        return True, f"Shortcut successfully created on Desktop: {shortcut_path}"
    except subprocess.CalledProcessError as e:
        return False, f"PowerShell command failed: {e.stderr}"
    except Exception as e:
        return False, str(e)


def create_unix_shortcut(repo_root: Path) -> tuple[bool, str]:
    """Create a Linux/macOS desktop launcher or symlink."""
    if sys.platform == "darwin":
        # macOS: Create a simple executable command script on Desktop
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            return False, "Could not locate Desktop directory."

        shortcut_path = desktop / "Institutional Alpha Terminal.command"
        launcher_content = f"""#!/bin/bash
cd "{repo_root}"
export PYTHONIOENCODING="utf-8"
./run_alpha_terminal.sh
"""
        try:
            shortcut_path.write_text(launcher_content)
            shortcut_path.chmod(0o755)  # Make executable
            return True, f"Launcher command created on Desktop: {shortcut_path}"
        except Exception as e:
            return False, str(e)
    else:
        # Linux: Create a standard .desktop file
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home() / ".local" / "share" / "applications"

        shortcut_path = desktop / "institutional-alpha.desktop"
        launcher_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Institutional Alpha Terminal
Comment=Multi-factor equity valuation engine TUI
Exec=bash -c 'cd "{repo_root}" && ./run_alpha_terminal.sh'
Terminal=true
Categories=Finance;Office;
"""
        try:
            shortcut_path.write_text(launcher_content)
            shortcut_path.chmod(0o755)
            return True, f"Desktop launcher created: {shortcut_path}"
        except Exception as e:
            return False, str(e)


def create_shortcut() -> tuple[bool, str]:
    """Main entry point to detect platform and create shortcut."""
    repo_root = Path(__file__).parent.parent.resolve()
    if sys.platform == "win32":
        return create_windows_shortcut(repo_root)
    else:
        return create_unix_shortcut(repo_root)


def main() -> None:
    print("⏳ Creating desktop shortcut for Institutional Alpha...")
    success, msg = create_shortcut()
    if success:
        print(f"✅ {msg}")
    else:
        print(f"❌ Failed: {msg}")


if __name__ == "__main__":
    main()
