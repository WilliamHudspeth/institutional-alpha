"""A fixture that keeps tests offline by answering the live adapter's EDGAR request locally.

``YFinanceAdapter.fetch`` asks SEC EDGAR for the 10-K geographic mix through the module-level
``_edgar_revenue_mix``. Tests that drive ``fetch`` (directly or through the pipeline) use this
fixture so they never reach the network; the answer is "no mix", which is what the adapter
produced before the EDGAR wiring existed. Used per test module via
``pytestmark = pytest.mark.usefixtures("no_edgar")``; deliberately NOT in tests/conftest.py.
"""

from __future__ import annotations

import pytest

from iam.data.edgar.geography import GeographicMixResult
from iam.data.providers import yfinance_adapter


@pytest.fixture()
def no_edgar(monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(ticker, as_of, client=None):
        return GeographicMixResult(reason="EDGAR is not queried in this test")

    monkeypatch.setattr(yfinance_adapter, "_edgar_revenue_mix", offline)
