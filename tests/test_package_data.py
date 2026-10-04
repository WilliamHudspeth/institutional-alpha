"""Every non-Python file shipped inside ``src/iam`` must be declared as
package data, or a regular (non-editable) install silently drops it."""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "iam"


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib needs Python 3.11+")
def test_all_package_data_is_declared():
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = config["tool"]["setuptools"]["package-data"]["iam"]
    data_files = [
        f.relative_to(PKG).as_posix()
        for f in PKG.rglob("*")
        if f.is_file() and f.suffix not in {".py", ".pyc"} and "__pycache__" not in f.parts
    ]
    assert data_files, "expected at least the reference ERP table"
    undeclared = [f for f in data_files if not any(fnmatch.fnmatch(f, p) for p in patterns)]
    assert not undeclared, f"not declared in [tool.setuptools.package-data]: {undeclared}"
