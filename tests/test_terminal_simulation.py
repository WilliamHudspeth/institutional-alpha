"""Simulation test for Alpha Terminal to ensure all panels render without AttributeError."""

import unittest
from unittest.mock import MagicMock

from iam.backtest.multiple_testing import ValidationMetrics
from iam.ui.alpha_terminal import AlphaTerminal, Canvas, SecState, SystemState


class TestTerminalSimulation(unittest.TestCase):
    def setUp(self):
        self.terminal = AlphaTerminal()
        self.canvas = Canvas(24, 80)
        self.sec = SecState(ticker="AAPL")
        self.sys = SystemState()

    def test_all_panels_render(self):
        """Simulate rendering of every panel with various state configurations."""
        # 1. Test with empty/loading state
        self.sec.loading = True
        self.sys.loading = True

        for name, panel in self.terminal._panels.items():
            try:
                panel.render(self.canvas, 5, 20, 28, 78, self.sec, self.sys, ticks=1)
            except Exception as e:
                self.fail(f"Panel '{name}' failed to render in loading state: {e}")

        # 2. Test with populated data (where the bug was)
        self.sec.loading = False
        self.sys.loading = False

        # Mock ValidationMetrics with the expected factor_metrics
        mock_metrics = ValidationMetrics(
            psr=0.9,
            dsr=1.5,
            pbo=0.04,
            spa_pvalue=0.02,
            effective_tests=8.0,
            factor_metrics={"Quality": {"ic": 0.05, "p_value": 0.01, "spread": 0.04}},
        )
        self.sys.backtest_metrics = mock_metrics

        # Mock SecState results to avoid deeper package calls during UI unit test
        self.sec.score_result = MagicMock()
        self.sec.score_result.composite = 0.25
        self.sec.score_result.factor_breakdown = {}

        self.sec.pipeline_result = MagicMock()
        self.sec.pipeline_result.final_verdict = MagicMock()
        self.sec.pipeline_result.final_verdict.rating = "BUY"
        self.sec.pipeline_result.final_verdict.confidence_band = "HIGH"
        self.sec.pipeline_result.final_verdict.blended_upside = 0.15
        self.sec.pipeline_result.implied_move_pct = 0.15

        self.sec.pipeline_result.triangulation = MagicMock()
        self.sec.pipeline_result.triangulation.cluster_center = 0.12
        self.sec.pipeline_result.triangulation.spread = 0.05
        self.sec.pipeline_result.triangulation.verdict = "BUY"

        self.sec.pipeline_result.law_report = MagicMock()
        self.sec.pipeline_result.law_report.violations = []
        self.sec.pipeline_result.law_report.flags = []

        for name, panel in self.terminal._panels.items():
            try:
                panel.render(self.canvas, 5, 20, 28, 78, self.sec, self.sys, ticks=1)
            except Exception as e:
                self.fail(f"Panel '{name}' failed to render with populated data: {e}")


if __name__ == "__main__":
    unittest.main()
