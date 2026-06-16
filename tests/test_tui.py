"""Verification tests for the Alpha Terminal TUI."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from iam.ui.alpha_terminal import (
    BacktestPanel,
    Canvas,
    DeepValPanel,
    FactorPanel,
    LearningPanel,
    PortfolioPanel,
    QuickRecPanel,
    ScenarioPanel,
    SecState,
    SysInfoPanel,
    WatchlistPanel,
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

    @patch("os.system")
    @patch("sys.stdout.write")
    def test_no_shell_spawning_in_menu(self, mock_write, mock_system):
        from iam.ui.menu import print_menu
        print_menu()
        mock_system.assert_not_called()
        # Verify ANSI escape sequence is used to clear screen
        mock_write.assert_any_call("\033[H\033[2J")


if __name__ == "__main__":
    unittest.main()
