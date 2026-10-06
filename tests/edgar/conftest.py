"""EDGAR test guard: any attempt to reach the network through ``requests`` fails loudly."""

from __future__ import annotations

import pytest
import requests.adapters


@pytest.fixture(autouse=True)
def _no_live_edgar(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(self, request, **kwargs):
        raise AssertionError(f"live network call attempted in an EDGAR test: {request.url}")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", blocked)
