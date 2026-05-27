"""Version and metadata for the Institutional Alpha platform."""

APP_NAME = "Institutional Alpha"
VERSION = "0.2.1-alpha"
AUTHOR = "William Hudspeth"
BUILD_DATE = "2026-05-27"
STATUS = "Research Preview"
PYTHON_MIN = "3.10"

# Version components
MAJOR = 0
MINOR = 2
PATCH = 1
PRERELEASE = "alpha"

def version_string() -> str:
    """Return full version string."""
    return f"{VERSION}"

def header() -> str:
    """Return professional header."""
    return f"""
{'='*70}
{' '*18}INSTITUTIONAL ALPHA
{' '*15}Multi-Lens Equity Research Engine
{'='*70}

Developed by {AUTHOR}
Proprietary Research Platform
Version {VERSION} ({STATUS})
Build: {BUILD_DATE}

For research and educational purposes only.
Not investment advice.

{'='*70}
"""

def metadata() -> dict:
    """Return runtime metadata."""
    import sys
    return {
        "platform": APP_NAME,
        "version": VERSION,
        "status": STATUS,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "author": AUTHOR,
        "build_date": BUILD_DATE,
    }
