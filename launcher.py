#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path

# Add src to path so we can import iam
sys.path.insert(0, str(Path(__file__).parent / "src"))

def run_bootstrap():
    """Run the bootstrap script to ensure environment is ready."""
    try:
        from iam.bootstrap import initialize_system
        return initialize_system()
    except Exception as e:
        print(f"Error running bootstrap: {e}")
        return False

def main():
    # Check for basic dependencies
    try:
        import rich
        import textual
        import yfinance
    except ImportError:
        print("Dependencies missing. Running First Run Setup...")
        if not run_bootstrap():
            print("Setup failed. Please install dependencies manually.")
            sys.exit(1)
        # Re-import after installation
        import rich
        import textual

    from iam.launcher import main as launcher_main
    launcher_main()

if __name__ == "__main__":
    main()
