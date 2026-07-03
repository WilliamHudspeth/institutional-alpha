"""Repo integrity guards.

Codifies bug patterns hit during automated/dispatched development sessions
(Hermes, opencode) where a process died mid-write or drifted from an
existing convention, and the breakage wasn't caught until manual review:

1. A file left syntactically broken (unterminated string) after a crashed
   write — src/iam/reports/html.py, twice.
2. A pytest marker used in tests/ but never registered in pyproject.toml,
   which fails test *collection* (not just the one test) under
   --strict-markers.
3. A package whose __init__.py imports submodules that don't exist yet
   (src/iam/reports/__init__.py importing csv.py/pdf.py before they were
   written) — breaks on first real import, not on syntax check.
4. A pydantic model field left as a bare `= Field` (the FieldInfo builder
   itself, not a call) by a truncated write — syntactically legal Python,
   so ast.parse doesn't catch it; only surfaces when the model is
   constructed and pydantic explains the missing required field.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
TESTS_ROOT = REPO_ROOT / "tests"

_SKIP_DIR_NAMES = {"__pycache__", ".git", ".venv", "venv", "build", "dist"}


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def test_all_source_and_test_files_parse():
    """Every .py file under src/ and tests/ must be valid Python.

    Catches files left mid-write by a crashed automated session (a
    truncated triple-quoted string is syntactically invalid, even though
    the file "exists" and has plausible-looking content at a glance).
    """
    broken = []
    for path in list(_iter_python_files(SRC_ROOT)) + list(_iter_python_files(TESTS_ROOT)):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            broken.append(f"{path.relative_to(REPO_ROOT)}: {e}")
    assert not broken, "Files with syntax errors:\n" + "\n".join(broken)


def test_all_pytest_markers_are_registered():
    """Every @pytest.mark.<name> used in tests/ must be declared in pyproject.toml.

    An unregistered marker fails collection of the ENTIRE suite under
    --strict-markers, not just the one test using it (see: the missing
    "functional" marker, which broke all ~990 other tests too).
    """
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    markers_block = re.search(r"markers\s*=\s*\[(.*?)\]", pyproject_text, re.DOTALL)
    assert markers_block, "pyproject.toml has no [tool.pytest.ini_options] markers list"
    registered = set(re.findall(r'"(\w+):', markers_block.group(1)))

    # Built-in markers pytest always understands, never declared explicitly.
    builtin = {"parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings"}

    used = set()
    marker_pattern = re.compile(r"pytest\.mark\.(\w+)")
    for path in _iter_python_files(TESTS_ROOT):
        used.update(marker_pattern.findall(path.read_text(encoding="utf-8")))

    unregistered = used - registered - builtin
    assert not unregistered, (
        f"Markers used in tests/ but not registered in pyproject.toml: {unregistered}. "
        "Add them to [tool.pytest.ini_options].markers or --strict-markers will fail "
        "collection of the whole suite."
    )


def _iter_iam_subpackages():
    import iam

    for info in pkgutil.iter_modules(iam.__path__, prefix="iam."):
        if info.ispkg:
            yield info.name


@pytest.mark.parametrize("package_name", list(_iter_iam_subpackages()))
def test_iam_subpackage_imports_cleanly(package_name):
    """Every top-level src/iam/<pkg>/__init__.py must actually import.

    Catches an __init__.py that declares a public API importing from
    submodules that don't exist yet (or no longer exist) — a package can
    parse as valid Python (each file is syntactically fine on its own)
    while still being completely broken to import.
    """
    importlib.import_module(package_name)


def _iter_pydantic_model_classes():
    import iam

    for info in pkgutil.walk_packages(iam.__path__, prefix="iam."):
        try:
            module = importlib.import_module(info.name)
        except Exception:
            continue
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and getattr(obj, "__module__", None) == info.name
                and hasattr(obj, "model_fields")
            ):
                yield f"{info.name}.{name}", obj


@pytest.mark.parametrize(
    "qualname_and_cls", list(_iter_pydantic_model_classes()), ids=lambda p: p[0]
)
def test_pydantic_model_fields_have_real_defaults(qualname_and_cls):
    """No pydantic model field's default may be the bare `Field` builder itself.

    `x: int = Field` (no call) is syntactically valid Python — the field's
    default becomes the `pydantic.fields.Field` function object, not a
    sensible value or FieldInfo. This is the exact shape a crashed
    mid-write left in governance/models.py's AssumptionOverride class: the
    file "parsed" and "imported" fine, but the field was silently broken.
    """
    import pydantic

    qualname, cls = qualname_and_cls
    broken = [
        field_name
        for field_name, field_info in cls.model_fields.items()
        if field_info.default is pydantic.fields.Field
    ]
    assert not broken, f"{qualname} has fields defaulting to the bare Field builder: {broken}"
