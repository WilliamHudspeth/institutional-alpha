"""Regression tests for real bugs surfaced by the mypy cleanup (no network)."""

from __future__ import annotations

from unittest.mock import patch

from iam.backtest import snapshots
from iam.data.security import Fundamentals, MarketData, Security


def _base_security() -> Security:
    return Security(
        ticker="TEST",
        sector="Technology",
        industry="Software",
        fundamentals=Fundamentals(shares_outstanding=1_000_000.0, total_debt=1.0),
    )


def test_run_thesis_engine_builds_assumptions_without_error(capsys):
    """Assumption is a pydantic model: positional construction raised TypeError,
    which run_thesis_engine swallowed and reported as a generic ERROR."""
    from iam.ui import menu

    with (
        patch(
            "iam.data.providers.yfinance_adapter.fetch_security",
            return_value=_base_security(),
        ),
        patch.object(menu, "safe_input", side_effect=lambda prompt, default=None: default),
    ):
        menu.run_thesis_engine("TEST")
    out = capsys.readouterr().out
    assert "ERROR" not in out
    assert "THESIS ANALYSIS" in out


def test_build_snapshot_freezes_price_and_debt(tmp_path):
    """build_snapshot used dataclasses.replace() on pydantic models (TypeError)."""
    base = _base_security()
    snapshots.reset_snapshot_cache()
    try:
        with patch.object(snapshots, "_fetch_snapshot_data", return_value=(10.0, 500.0)):
            snap = snapshots.build_snapshot(
                base,
                "2024-01-02",
                cache_dir=tmp_path / "c",
                fetcher=object(),  # type: ignore[arg-type]
            )
    finally:
        snapshots.reset_snapshot_cache()
    assert isinstance(snap.market, MarketData)
    assert snap.market.price == 10.0
    assert snap.market.market_cap == 10.0 * 1_000_000.0
    assert snap.fundamentals.total_debt == 500.0
    assert base.fundamentals.total_debt == 1.0  # original untouched
