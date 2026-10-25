"""Errors for the Track A (stock-by-stock, free data) builders."""

from __future__ import annotations

from iam.backtest.track_b.cache import TrackBDataError


class TrackADataError(TrackBDataError):
    """A Track A input could not be downloaded or did not have the expected layout."""
