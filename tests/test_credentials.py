"""Tests for the free-data credentials layer."""

from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture()
def creds(tmp_path, monkeypatch):
    """Reload the credentials module pointed at an isolated temp config dir."""
    monkeypatch.setenv("IAM_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    import iam.config.credentials as c

    importlib.reload(c)
    return c


def test_set_get_roundtrip_via_file(creds):
    assert creds.get_key("fmp") is None
    creds.set_key("fmp", "ABC123")
    assert creds.get_key("fmp") == "ABC123"
    assert creds.CREDENTIALS_FILE.exists()


def test_env_var_overrides_file(creds, monkeypatch):
    creds.set_key("fmp", "FROM_FILE")
    monkeypatch.setenv("FMP_API_KEY", "FROM_ENV")
    assert creds.get_key("fmp") == "FROM_ENV"


def test_explicit_arg_overrides_everything(creds, monkeypatch):
    creds.set_key("fmp", "FROM_FILE")
    monkeypatch.setenv("FMP_API_KEY", "FROM_ENV")
    assert creds.get_key("fmp", explicit="FROM_ARG") == "FROM_ARG"


def test_clear_key(creds):
    creds.set_key("tiingo", "X")
    creds.clear_key("tiingo")
    assert creds.get_key("tiingo") is None


def test_unknown_provider_rejected(creds):
    with pytest.raises(ValueError):
        creds.set_key("bloomberg", "X")


def test_status_reports_source_without_leaking_secret(creds, monkeypatch):
    creds.set_key("fmp", "SECRET")
    st = creds.status()
    assert st["fmp"]["configured"] is True
    assert st["fmp"]["source"] == "file"
    # the secret value must never appear in status output
    assert "SECRET" not in str(st)
    # sec_edgar is keyless
    assert st["sec_edgar"]["needs_key"] is False


def test_fmp_source_picks_up_stored_key(creds):
    creds.set_key("fmp", "STORED_FMP")
    from iam.backtest.sources.fmp_source import FMPSource

    src = FMPSource()  # no explicit key, no env -> must read the file
    assert src.is_available() is True
    assert src.api_key == "STORED_FMP"


@pytest.mark.skipif(
    os.name == "nt", reason="Windows chmod does not support POSIX group/other permissions"
)
def test_credentials_file_is_owner_only(creds):
    import stat

    creds.set_key("fmp", "X")
    mode = creds.CREDENTIALS_FILE.stat().st_mode
    # no group/other permissions
    assert not (mode & (stat.S_IRWXG | stat.S_IRWXO))
