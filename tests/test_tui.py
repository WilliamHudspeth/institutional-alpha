"""Verification tests for the Alpha Terminal TUI."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from iam.ui.alpha_terminal import (
    Canvas,
    SecState,
    WatchlistPanel,
    QuickRecPanel,
    DeepValPanel,
    FactorPanel,
    ScenarioPanel,
    BacktestPanel,
    PortfolioPanel,
    SysInfoPanel,
    LearningPanel,
)


class TestTUIElements(unittest.TestCase):
    def setUp(self):
        self.canvas = Canvas(30, 100)
        self.sec = SecState(ticker="AAPL")
        self.sec.history = [150.0] * 10
        self.sec.loading = False

    def test_canvas_draw(self):
        self.canvas.put(0, 0, "TEST", style="")
        self.assertEqual(self.canvas._back[0][0][0], "T")
        self.assertEqual(self.canvas._back[0][3][0], "T")

    def test_panels_render_without_error(self):
        panels = [
            WatchlistPanel(["AAPL", "MSFT"]),
            QuickRecPanel(),
            DeepValPanel(),
            FactorPanel(),
            ScenarioPanel(),
            BacktestPanel(),
            PortfolioPanel(),
            SysInfoPanel(),
            LearningPanel(),
        ]
        
        for panel in panels:
            # Check render operates without exceptions
            panel.render(self.canvas, 2, 28, 28, 98, self.sec, ticks=0)


if __name__ == "__main__":
    unittest.main()
