#!/usr/bin/env python3
"""GUI Launchpoint for Institutional Alpha."""
import sys
import subprocess
from pathlib import Path

# Add src to path so we can import iam modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    print("=== Institutional Alpha GUI Setup Wizard ===")
    from iam.bootstrap import initialize_system
    if not initialize_system():
        print("[X] Setup Wizard failed. Exiting.")
        sys.exit(1)
        
    try:
        import streamlit
    except ImportError:
        if not getattr(sys, 'frozen', False):
            print("[!] Streamlit not found. Installing UI dependencies...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit"])
    
    gui_path = Path(__file__).parent / "src" / "iam" / "ui" / "gui.py"
    print(f"\n[✓] Setup Complete! Launching GUI server...")
    print("=" * 42)
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(gui_path)])

if __name__ == "__main__":
    main()
