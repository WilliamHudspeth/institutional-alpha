#!/usr/bin/env bash
# ==============================================================================
#  Institutional Alpha Terminal — macOS & Linux Launcher
# ==============================================================================

# Dynamic path resolution to support execution from any directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 1. Detect Python Interpreter
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo -e "\033[31mError: Python interpreter could not be resolved.\033[0m"
    echo "Please ensure Python 3.10+ is installed and configured in your shell path."
    echo ""
    read -n 1 -s -r -p "Press any key to exit..."
    exit 1
fi

# 2. Hard-code UTF-8 environment variable for clean TUI sparkline rendering
export PYTHONIOENCODING="utf-8"

# 3. Execute Terminal GUI
$PYTHON_BIN alpha_terminal.py
