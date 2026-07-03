"""Environment bootstrap and system initialization for Institutional Alpha."""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REQUIRED_PYTHON_VERSION = (3, 10)
REQUIRED_DIRECTORIES = [
    "data/cache",
    "data/universe",
    "data/results",
    "logs",
]


def check_python_version():
    """Verify that the current Python version meets requirements."""
    if sys.version_info < REQUIRED_PYTHON_VERSION:
        print(
            f"[!] Institutional Alpha requires Python {REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]}+"
        )
        print(f"    Current version: {sys.version.split()[0]}")
        return False
    print(f"[✓] Python {sys.version.split()[0]} detected")
    return True


def ensure_directories():
    """Create required directories if they don't exist."""
    project_root = Path(__file__).parent.parent.parent
    for d in REQUIRED_DIRECTORIES:
        path = project_root / d
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            print(f"[✓] Created directory: {d}")
        else:
            print(f"[✓] Directory ready: {d}")


def check_dependencies():
    """Check if required dependencies are installed, install if missing."""
    try:
        import pydantic  # noqa: F401
        import rich  # noqa: F401
        import textual  # noqa: F401
        import yaml  # noqa: F401
        import yfinance  # noqa: F401

        print("[✓] Core dependencies detected")
        return True
    except ImportError:
        print("[!] Missing dependencies. Attempting automatic installation...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])  # nosec
            print("[✓] Dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[X] Failed to install dependencies: {e}")
            return False


def init_config():
    """Ensure configuration files exist."""
    project_root = Path(__file__).parent.parent.parent
    example_config = project_root / "config.example.yml"
    user_config = project_root / "config.yml"

    if not user_config.exists() and example_config.exists():
        shutil.copy(example_config, user_config)
        print("[✓] Created user configuration from template (config.yml)")
    elif user_config.exists():
        print("[✓] Configuration loaded")
    else:
        print("[!] config.example.yml not found. Please ensure it exists in the root.")


def initialize_system():
    """Run all bootstrap steps."""
    print("Initializing Institutional Alpha Environment...")
    print("=" * 40)

    steps = [check_python_version, ensure_directories, check_dependencies, init_config]

    for step in steps:
        if step() is False:
            print("\n[X] Bootstrap failed. Please troubleshoot and try again.")
            return False

    print("\nInstitutional Alpha Ready")
    print("=" * 40)
    return True


if __name__ == "__main__":
    initialize_system()
