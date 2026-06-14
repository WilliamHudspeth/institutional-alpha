"""Free-data credentials: where API keys live and how to set them.

This project is designed to run on **entirely free data**. Most of the stack
needs *no key at all* (SEC EDGAR, Yahoo/yfinance, Stooq). Two optional premium
feeds — Financial Modeling Prep and Tiingo — have perpetual free tiers; adding
their free keys simply promotes them ahead of the keyless sources. Nothing here
is required to run a backtest.

Key resolution precedence (first hit wins):
    1. explicit argument passed in code
    2. environment variable (e.g. FMP_API_KEY)
    3. user credentials file: ~/.institutional-alpha/credentials.json

The credentials file is created with 0600 permissions and lives in the user's
home directory — never in the repo — so keys are never committed. Set keys
interactively from the terminal with:

    python -m iam.config.credentials

Stdlib only.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path


def _config_dir() -> Path:
    """Resolve the config dir live each call so IAM_CONFIG_DIR is always honored."""
    return Path(os.environ.get("IAM_CONFIG_DIR", Path.home() / ".institutional-alpha"))


def _creds_file() -> Path:
    return _config_dir() / "credentials.json"


# Module-level CONFIG_DIR / CREDENTIALS_FILE remain available but are computed
# dynamically via PEP 562 so they reflect the current environment, not import time.
def __getattr__(name: str):
    if name == "CONFIG_DIR":
        return _config_dir()
    if name == "CREDENTIALS_FILE":
        return _creds_file()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass(frozen=True)
class Provider:
    key: str  # internal id / credentials-file key
    label: str  # human name
    env_var: str  # environment variable checked second
    needs_key: bool  # False => keyless (SEC just needs a contact UA)
    signup_url: str
    free_tier: str  # short description of the free allowance
    instructions: str  # how to get the key, in plain steps


# The full free-data registry. Order = the order shown in the setup wizard.
PROVIDERS: dict[str, Provider] = {
    "sec_edgar": Provider(
        key="sec_edgar",
        label="SEC EDGAR (official filings)",
        env_var="SEC_USER_AGENT",
        needs_key=False,
        signup_url="https://www.sec.gov/os/accessing-edgar-data",
        free_tier="Free, no key. 10 requests/sec. Requires a contact User-Agent.",
        instructions=(
            "No account needed. The SEC only asks that automated requests declare a\n"
            "  descriptive User-Agent containing your name and email, e.g.\n"
            "      'Will Hudspeth will@example.com'\n"
            "  Enter that contact string below (used only as the request header)."
        ),
    ),
    "fmp": Provider(
        key="fmp",
        label="Financial Modeling Prep (FMP)",
        env_var="FMP_API_KEY",
        needs_key=True,
        signup_url="https://site.financialmodelingprep.com/developer/docs",
        free_tier="Free forever: 250 requests/day, no credit card.",
        instructions=(
            "1. Go to https://site.financialmodelingprep.com and enter your email to sign up.\n"
            "2. Verify your email and log in.\n"
            "3. Open the Dashboard — your free API key is shown there.\n"
            "4. Paste it below. The free plan gives 250 requests/day, perpetually."
        ),
    ),
    "tiingo": Provider(
        key="tiingo",
        label="Tiingo (EOD prices)",
        env_var="TIINGO_API_KEY",
        needs_key=True,
        signup_url="https://www.tiingo.com",
        free_tier="Free tier: ~50 requests/hour of end-of-day prices.",
        instructions=(
            "1. Sign up at https://www.tiingo.com (free).\n"
            "2. Log in and open https://www.tiingo.com/account/api/token\n"
            "3. Copy your API token and paste it below.\n"
            "   Free tier covers EOD prices; fundamentals are a paid add-on."
        ),
    ),
}


def _read_file() -> dict[str, str]:
    cf = _creds_file()
    if not cf.exists():
        return {}
    try:
        data = json.loads(cf.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_file(data: dict[str, str]) -> None:
    cf = _creds_file()
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(data, indent=2))
    # Lock down to owner read/write only (best-effort; no-op on some platforms).
    try:
        cf.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover
        pass


def get_key(provider: str, explicit: str | None = None) -> str | None:
    """Resolve a key: explicit arg > env var > credentials file > None."""
    if explicit:
        return explicit
    prov = PROVIDERS.get(provider)
    if prov is not None:
        env_val = os.environ.get(prov.env_var)
        if env_val:
            return env_val
    return _read_file().get(provider)


def set_key(provider: str, value: str) -> None:
    """Persist a key to the user credentials file (0600)."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Known: {sorted(PROVIDERS)}")
    data = _read_file()
    data[provider] = value.strip()
    _write_file(data)


def clear_key(provider: str) -> None:
    data = _read_file()
    if provider in data:
        del data[provider]
        _write_file(data)


def status() -> dict[str, dict[str, str | bool]]:
    """Per-provider configuration status (no secrets revealed)."""
    out: dict[str, dict[str, str | bool]] = {}
    for name, prov in PROVIDERS.items():
        explicit_env = bool(os.environ.get(prov.env_var))
        in_file = name in _read_file()
        configured = explicit_env or in_file
        source = "env" if explicit_env else ("file" if in_file else "not set")
        out[name] = {
            "label": prov.label,
            "needs_key": prov.needs_key,
            "configured": configured,
            "source": source,
            "free_tier": prov.free_tier,
        }
    return out


def configure_interactive() -> None:
    """Terminal wizard to add/update free-data credentials."""
    print("\n" + "=" * 70)
    print("  INSTITUTIONAL ALPHA — Free Data Source Setup")
    print("=" * 70)
    print(
        "\nThis program runs on free data. SEC EDGAR, Yahoo, and Stooq need NO key.\n"
        "FMP and Tiingo have free tiers — adding their keys is optional and just\n"
        "promotes them ahead of the keyless sources.\n"
    )
    st = status()
    for name, prov in PROVIDERS.items():
        cur = st[name]
        flag = "✓ configured" if cur["configured"] else "— not set"
        print("-" * 70)
        print(f"{prov.label}   [{flag} via {cur['source']}]")
        print(f"  Free tier: {prov.free_tier}")
        print(f"  {prov.instructions}")
        prompt = (
            "  Enter contact User-Agent (blank to skip): "
            if not prov.needs_key
            else "  Paste key (blank to skip, '-' to clear): "
        )
        try:
            entered = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            return
        if entered == "-":
            clear_key(name)
            print("  cleared.")
        elif entered:
            set_key(name, entered)
            print("  saved.")
        else:
            print("  skipped.")
    print("-" * 70)
    print(f"\nCredentials stored at: {_creds_file()}")
    print("You can re-run this anytime with:  python -m iam.config.credentials\n")


if __name__ == "__main__":
    configure_interactive()
