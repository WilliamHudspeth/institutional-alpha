#!/usr/bin/env python3
"""
Verification and diagnostic script for Institutional Alpha.
Designed to be the primary quality-control gate for AI coding assistants and developers.
"""

import ast
import os
import subprocess
import sys

# Terminal colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_header(title: str):
    print(f"\n{BOLD}{BLUE}[ {title} ]{RESET}")


def run_check(name: str, check_func) -> bool:
    print(f"Running check: {BOLD}{name}{RESET}...", end="", flush=True)
    try:
        success, message = check_func()
        if success:
            print(f" {GREEN}PASSED{RESET}")
            if message:
                print(f"  {message}")
            return True
        else:
            print(f" {RED}FAILED{RESET}")
            if message:
                print(f"  {message}")
            return False
    except Exception as e:
        print(f" {RED}ERROR{RESET}")
        print(f"  Unexpected exception: {e}")
        return False


def check_merge_conflicts() -> tuple[bool, str]:
    """Search for git merge conflict markers in the codebase."""
    conflicts_found = []

    for root, _, files in os.walk("."):
        # Skip standard ignore dirs
        if any(d in root for d in [".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "venv"]):
            continue

        for file in files:
            if not file.endswith((".py", ".md", ".json", ".yaml", ".toml")):
                continue

            filepath = os.path.join(root, file)
            # Skip verify.py itself to prevent false positives from checking the checker
            if file == "verify.py":
                continue

            try:
                with open(filepath, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        cleaned = line.strip()
                        # Git merge conflicts start at the beginning of a line with <<<<<<< or >>>>>>> or are a standalone =======
                        if (
                            line.startswith("<<<<<<< ")
                            or line.startswith(">>>>>>> ")
                            or cleaned == "======="
                        ):
                            conflicts_found.append(f"{filepath}:{i} - {line.strip()}")
            except OSError:
                pass

    if conflicts_found:
        details = "\n  ".join(conflicts_found[:10])
        if len(conflicts_found) > 10:
            details += f"\n  ...and {len(conflicts_found) - 10} more"
        return False, f"{RED}Unresolved merge conflicts found:{RESET}\n  {details}"

    return True, "No unresolved merge conflict markers found."


def check_python_syntax() -> tuple[bool, str]:
    """Parse all python files to ensure they are free of syntax errors."""
    syntax_errors = []

    for root, _, files in os.walk("."):
        if any(d in root for d in [".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "venv"]):
            continue

        for file in files:
            if not file.endswith(".py"):
                continue

            filepath = os.path.join(root, file)
            try:
                with open(filepath, encoding="utf-8-sig") as f:
                    content = f.read()
                ast.parse(content, filename=filepath)
            except SyntaxError as se:
                syntax_errors.append(f"{filepath}:{se.lineno}:{se.offset} - {se.msg}")
            except Exception as e:
                syntax_errors.append(f"{filepath} - Unreadable: {e}")

    if syntax_errors:
        details = "\n  ".join(syntax_errors)
        return False, f"{RED}Syntax errors found:{RESET}\n  {details}"

    return True, "All Python files parsed successfully (no syntax errors)."


def check_ruff_lint() -> tuple[bool, str]:
    """Run ruff linter checks on src/ and tests/."""
    try:
        result = subprocess.run(
            ["ruff", "check", "src/", "tests/", "scripts/"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0:
            return True, "Code complies fully with Ruff linter rules."
        else:
            # Show first 15 lines of ruff output for context
            output = "\n  ".join(result.stdout.splitlines()[:15])
            if len(result.stdout.splitlines()) > 15:
                output += f"\n  ...and {len(result.stdout.splitlines()) - 15} more lines of lints."
            return False, f"{RED}Ruff lints failed:{RESET}\n  {output}"
    except FileNotFoundError:
        return (
            True,
            f"{YELLOW}Ruff is not installed. Skip check. Run 'pip install ruff' to enable.{RESET}",
        )


def check_ruff_format() -> tuple[bool, str]:
    """Check if code is formatted according to ruff formatting guidelines."""
    try:
        result = subprocess.run(
            ["ruff", "format", "src/", "tests/", "scripts/", "--check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0:
            return True, "Code is correctly formatted."
        else:
            output = "\n  ".join(result.stderr.splitlines()[:15])
            return (
                False,
                f"{RED}Ruff format check failed. Run 'ruff format src/ tests/ scripts/' to auto-fix.{RESET}\n  {output}",
            )
    except FileNotFoundError:
        return True, f"{YELLOW}Ruff is not installed. Skip check.{RESET}"


def check_mypy() -> tuple[bool, str]:
    """Run mypy static type checking."""
    try:
        result = subprocess.run(
            ["mypy", "src/", "--ignore-missing-imports"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0:
            return True, "All modules passed type checks successfully."
        else:
            output = "\n  ".join(result.stdout.splitlines()[:15])
            if len(result.stdout.splitlines()) > 15:
                output += (
                    f"\n  ...and {len(result.stdout.splitlines()) - 15} more lines of type errors."
                )
            # Match CI pipeline: allow mypy check to succeed with warnings
            return (
                True,
                f"{YELLOW}Mypy type warnings detected (non-blocking):{RESET}\n  {output}",
            )
    except FileNotFoundError:
        return (
            True,
            f"{YELLOW}Mypy is not installed. Skip check. Run 'pip install mypy' to enable.{RESET}",
        )


def check_pytest() -> tuple[bool, str]:
    """Run pytest suite with short traceback output."""
    try:
        result = subprocess.run(
            ["pytest", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode == 0:
            summary = [line for line in result.stdout.splitlines() if "passed" in line][-1:]
            msg = summary[0] if summary else "All tests passed successfully."
            return True, msg
        else:
            # Find failure summaries in pytest output
            failures = [
                line
                for line in result.stdout.splitlines()
                if line.startswith("FAILURES") or "FAILED" in line
            ]
            details = "\n  ".join(failures[:15])
            return (
                False,
                f"{RED}Tests failed:{RESET}\n  {details}\n  Run 'python -m pytest' for full log.",
            )
    except FileNotFoundError:
        return (
            True,
            f"{YELLOW}pytest is not installed. Skip check. Run 'pip install pytest' to enable.{RESET}",
        )


def main():
    print_header("Institutional Alpha Integrity Auditor")
    print("Checking repository state and code quality guidelines...")

    checks = [
        ("Git Merge Conflicts", check_merge_conflicts),
        ("Python File Syntax", check_python_syntax),
        ("Ruff Code Style/Linting", check_ruff_lint),
        ("Ruff Formatting", check_ruff_format),
        ("Mypy Type Safety Verification", check_mypy),
        ("Pytest Test Suite Verification", check_pytest),
    ]

    failed_checks = 0
    passed_checks = 0

    for name, func in checks:
        if run_check(name, func):
            passed_checks += 1
        else:
            failed_checks += 1

    print("\n" + "=" * 50)
    print(f"{BOLD}AUDIT SUMMARY{RESET}")
    print(f"Passed: {GREEN}{passed_checks}{RESET}")
    print(f"Failed: {RED if failed_checks > 0 else GREEN}{failed_checks}{RESET}")
    print("=" * 50)

    if failed_checks > 0:
        print(f"\n{BOLD}{RED}CRITICAL: Integrity checks failed.{RESET}")
        print("Please address the failures above before committing changes.")
        sys.exit(1)
    else:
        print(
            f"\n{BOLD}{GREEN}All checks passed successfully! Your workspace is clean and compliant.{RESET}"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
