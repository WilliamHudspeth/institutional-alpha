import PyInstaller.__main__
import sys

def build():
    # Hidden imports to ensure these libraries are bundled correctly
    hidden_imports = [
        "--hidden-import=yfinance",
        "--hidden-import=sklearn",
        "--hidden-import=streamlit",
        "--hidden-import=plotly",
    ]
    
    # Common arguments for single-executable generation
    common_args = [
        "--onefile",
        "--noconfirm", # Overwrite output directory without asking
        "--clean"
    ] + hidden_imports
    
    print("Building launch_tui...")
    PyInstaller.__main__.run([
        "launch_tui.py",
        "--name=launch_tui"
    ] + common_args)
    
    print("Building launch_gui...")
    PyInstaller.__main__.run([
        "launch_gui.py",
        "--name=launch_gui"
    ] + common_args)

if __name__ == "__main__":
    build()
