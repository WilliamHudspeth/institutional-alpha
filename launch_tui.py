#!/usr/bin/env python3
"""TUI Launchpoint for Institutional Alpha."""
import sys
import subprocess
from pathlib import Path

# Add src to path so we can import iam modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    print("=== Institutional Alpha TUI Setup Wizard ===")
    from iam.bootstrap import initialize_system
    if not initialize_system():
        print("[X] Setup Wizard failed. Exiting.")
        sys.exit(1)
        
    try:
        import textual
    except ImportError:
        print("[!] Textual not found. Installing UI dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "textual"])

    print("\n[✓] Setup Complete! Launching Terminal UI...")
    print("=" * 42)
    from iam.ui.alpha_terminal import main as terminal_main
    terminal_main()

if __name__ == "__main__":
    main()
