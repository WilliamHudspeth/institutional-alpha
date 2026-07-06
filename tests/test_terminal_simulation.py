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

        # Use real objects for simulation to catch attribute errors
        from iam.portfolio import Portfolio, Position

        positions = [
            Position(
                ticker="AAPL",
                name="Apple",
                quantity=100,
                entry_price=150,
                current_price=180,
                weight=0.4,
                conviction="HIGH",
            ),
            Position(
                ticker="MSFT",
                name="Microsoft",
                quantity=150,
                entry_price=300,
                current_price=350,
                weight=0.6,
                conviction="MODERATE",
            ),
        ]
        self.sys.portfolio = Portfolio(positions=positions)

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

        self.sec.pipeline_result.battlefield = MagicMock()
        self.sec.pipeline_result.battlefield.market_growth = 0.12
        self.sec.pipeline_result.battlefield.intrinsic_growth = 0.08
        self.sec.pipeline_result.battlefield.market_margin = 0.25
        self.sec.pipeline_result.battlefield.intrinsic_margin = 0.20
        self.sec.pipeline_result.battlefield.market_roic = 0.15
        self.sec.pipeline_result.battlefield.intrinsic_roic = 0.18
        self.sec.pipeline_result.battlefield.growth_gap = -0.04
        self.sec.pipeline_result.battlefield.margin_gap = -0.05
        self.sec.pipeline_result.battlefield.roic_gap = 0.03
        self.sec.pipeline_result.battlefield.alignment_score = 0.45  # float for comparisons
        self.sec.pipeline_result.battlefield.expectation_mismatch_score = 65.0
        self.sec.pipeline_result.battlefield.growth_overlap = 0.40  # float for comparisons

        self.sec.pipeline_result.law_report = MagicMock()
        self.sec.pipeline_result.law_report.violations = []
        self.sec.pipeline_result.law_report.flags = []

        self.sec.pipeline_result.market_implied_engine = MagicMock()
        self.sec.pipeline_result.market_implied_engine.implied = MagicMock()
        self.sec.pipeline_result.market_implied_engine.implied.growth_vs_history_max = 1.5
        
        self.sec.pipeline_result.intrinsic = None
        self.sec.pipeline_result.relative = None

        for name, panel in self.terminal._panels.items():
            try:
                panel.render(self.canvas, 5, 20, 28, 78, self.sec, self.sys, ticks=1)
            except Exception as e:
                self.fail(f"Panel '{name}' failed to render with populated data: {e}")

    def test_panels_with_none_values(self):
        """Ensure panels handle None values for key metrics without crashing."""
        self.sec.loading = False
        self.sys.loading = False

        # Set key fields to None to simulate incomplete data
        self.sec.score_result = MagicMock()
        self.sec.score_result.composite = None
        self.sec.score_result.factor_breakdown = {"quality": MagicMock(value=None, confidence=None)}

        self.sec.pipeline_result = MagicMock()
        self.sec.pipeline_result.final_verdict = MagicMock()
        self.sec.pipeline_result.final_verdict.rating = None
        self.sec.pipeline_result.final_verdict.blended_upside = None

        self.sec.pipeline_result.triangulation = MagicMock()
        self.sec.pipeline_result.triangulation.cluster_center = None
        self.sec.pipeline_result.triangulation.spread = None
        self.sec.pipeline_result.triangulation.verdict = None

        self.sec.pipeline_result.battlefield = MagicMock()
        self.sec.pipeline_result.battlefield.market_growth = None
        self.sec.pipeline_result.battlefield.intrinsic_growth = None
        self.sec.pipeline_result.battlefield.market_margin = None
        self.sec.pipeline_result.battlefield.intrinsic_margin = None
        self.sec.pipeline_result.battlefield.market_roic = None
        self.sec.pipeline_result.battlefield.intrinsic_roic = None
        self.sec.pipeline_result.battlefield.growth_gap = None
        self.sec.pipeline_result.battlefield.margin_gap = None
        self.sec.pipeline_result.battlefield.roic_gap = None
        self.sec.pipeline_result.battlefield.alignment_score = None
        self.sec.pipeline_result.battlefield.expectation_mismatch_score = None
        self.sec.pipeline_result.battlefield.growth_overlap = None

        self.sec.pipeline_result.market_implied_engine = MagicMock()
        self.sec.pipeline_result.market_implied_engine.implied = MagicMock()
        self.sec.pipeline_result.market_implied_engine.implied.growth_vs_history_max = None

        self.sec.pipeline_result.intrinsic = None
        self.sec.pipeline_result.relative = None

        for name, panel in self.terminal._panels.items():
            try:
                panel.render(self.canvas, 5, 20, 28, 78, self.sec, self.sys, ticks=1)
            except Exception as e:
                self.fail(f"Panel '{name}' crashed with None values: {e}")


if __name__ == "__main__":
    unittest.main()
