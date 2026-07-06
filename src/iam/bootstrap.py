"""Environment bootstrap and system initialization for Institutional Alpha.

Diagnostic/status output goes through the stdlib ``logging`` module (not
``print``) so it can be filtered, redirected, and captured like the rest of
the framework's diagnostics. This module is the reference example for the
codebase-wide print() -> logging migration.
"""

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
        logger.error(
            "Institutional Alpha requires Python %d.%d+ (current version: %s)",
            REQUIRED_PYTHON_VERSION[0],
            REQUIRED_PYTHON_VERSION[1],
            sys.version.split()[0],
        )
        return False
    logger.info("Python %s detected", sys.version.split()[0])
    return True


def ensure_directories():
    """Create required directories if they don't exist."""
    project_root = Path(__file__).parent.parent.parent
    for d in REQUIRED_DIRECTORIES:
        path = project_root / d
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            logger.info("Created directory: %s", d)
        else:
            logger.debug("Directory ready: %s", d)


def check_dependencies():
    """Check if required dependencies are installed, install if missing."""
    try:
        import pydantic  # noqa: F401
        import rich  # noqa: F401
        import textual  # noqa: F401
        import yaml  # noqa: F401
        import yfinance  # noqa: F401

        logger.info("Core dependencies detected")
        return True
    except ImportError:
        logger.warning("Missing dependencies. Attempting automatic installation...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])  # nosec
            logger.info("Dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Failed to install dependencies: %s", e)
            return False


def init_config():
    """Ensure configuration files exist."""
    project_root = Path(__file__).parent.parent.parent
    example_config = project_root / "config.example.yml"
    user_config = project_root / "config.yml"

    if not user_config.exists() and example_config.exists():
        shutil.copy(example_config, user_config)
        logger.info("Created user configuration from template (config.yml)")
    elif user_config.exists():
        logger.info("Configuration loaded")
    else:
        logger.warning("config.example.yml not found. Please ensure it exists in the root.")


def initialize_system():
    """Run all bootstrap steps."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info("Initializing Institutional Alpha Environment...")

    steps = [check_python_version, ensure_directories, check_dependencies, init_config]

    for step in steps:
        if step() is False:
            logger.error("Bootstrap failed. Please troubleshoot and try again.")
            return False

    logger.info("Institutional Alpha Ready")
    return True


if __name__ == "__main__":
    # Running the module directly is a diagnostic action — surface the log
    # output on the console the way the old print() calls did.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    initialize_system()
