#!/usr/bin/env python3
"""TUI Launchpoint for Institutional Alpha."""

import argparse
import sys
import subprocess
from pathlib import Path

# Add src to path so we can import iam modules
sys.path.insert(0, str(Path(__file__).parent / "src"))


def main():
    parser = argparse.ArgumentParser(description="Institutional Alpha TUI", add_help=False)
    parser.add_argument(
        "--demo",
        action="store_true",
        default=False,
        help=(
            "Run with labelled random mock data (visible DEMO banner on every screen). "
            "Without this flag, missing core packages surface as an error state "
            "instead of generating random data."
        ),
    )
    args, remaining = parser.parse_known_args()

    print("=== Institutional Alpha TUI Setup Wizard ===")
    from iam.bootstrap import initialize_system

    if not initialize_system():
        print("[X] Setup Wizard failed. Exiting.")
        sys.exit(1)

    try:
        import textual
    except ImportError:
        if not getattr(sys, "frozen", False):
            print("[!] Textual not found. Installing UI dependencies...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "textual"])

    print("\n[✓] Setup Complete! Launching Terminal UI...")
    print("=" * 42)

    # Forward --demo flag into sys.argv so alpha_terminal.main() picks it up.
    if args.demo and "--demo" not in sys.argv:
        sys.argv.append("--demo")

    from iam.ui.alpha_terminal import main as terminal_main

    terminal_main()


if __name__ == "__main__":
    main()
