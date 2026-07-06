"""End-to-end tests: registered iam.plugins genuinely affect pipeline runs.

Covers the Stage 4a plugin bridge in iam.pipeline.orchestrator:
- explicit registration (PluginManager.register_lens / register_factor)
- file-based discovery (PluginManager.discover_plugins on the examples dir)
- the process-wide default manager (get_plugin_manager)
- the no-plugin path staying byte-for-byte compatible with the old behavior
"""

from pathlib import Path

from iam.data.security import Fundamentals, MarketData, Security
from iam.pipeline.orchestrator import ValuationPipeline
from iam.plugins.examples.fcf_yield_lens import FcfYieldLens
from iam.plugins.interfaces import IA_FactorPlugin
from iam.plugins.manager import PluginManager, get_plugin_manager, reset_plugin_manager


def _security(ticker: str = "PLUG") -> Security:
    """Fixture mirroring test_pipeline.py's FULL security (all stages fire)."""
    return Security(
        ticker=ticker,
        fundamentals=Fundamentals(
            fcf_ttm=2800,
            shares_outstanding=1000,
            revenue_history=[10000, 8500, 7200, 6100, 5200],
        ),
        market=MarketData(
            price=180,
            pe_ttm=75,
            ev_ebitda=50,
            pe_history=[60, 55, 50, 70, 80, 65, 55, 45, 40, 35, 50, 60],
            sector_ev_ebitda_median=22,
            fcf_yield=0.016,
            peer_fcf_yields=[0.03, 0.025, 0.04],
        ),
        qualitative={"forecast_growth": 0.18, "forecast_discount_rate": 0.10},
    )


def test_registered_lens_plugin_influences_pipeline_run():
    pm = PluginManager()
    pm.register_lens(FcfYieldLens)

    report = ValuationPipeline(plugin_manager=pm).run(_security())

    # Plugin output is attached to the report...
    assert report.plugin_lenses is not None
    lens = next(lr for lr in report.plugin_lenses if lr.lens_name == "fcf_yield_plugin")
    assert lens.implied_move_pct is not None
    assert 0.0 < lens.confidence <= 1.0

    # ...its narrative surfaces in triangulation notes and explain() output...
    assert any("[PLUGIN fcf_yield_plugin]" in n for n in report.triangulation.notes)
    assert "[PLUGIN fcf_yield_plugin]" in report.explain()
    assert "[PLUGINS]: 1 lens / 0 factor plugin(s) applied" in report.summary

    # ...and its weighted implied move feeds Stage 7 (synthesis arbitration).
    assert report.synthesis_upside is not None
    assert abs(report.synthesis_upside - lens.implied_move_pct) < 1e-9
    assert "[PLUGIN SYNTHESIS]" in report.summary


def test_pipeline_without_plugins_is_unchanged():
    report = ValuationPipeline(plugin_manager=PluginManager()).run(_security())

    assert report.plugin_lenses is None
    assert report.plugin_factors is None
    assert report.synthesis_upside is None
    assert not any("[PLUGIN" in n for n in report.triangulation.notes)
    assert "[PLUGIN" not in report.summary


def test_factor_plugin_results_attached_to_report():
    class MomentumFactor(IA_FactorPlugin):
        def calculate(self, data):
            history = data["fundamentals"].revenue_history
            score = (history[0] / history[-1]) - 1.0 if history else 0.0
            return {"revenue_momentum": round(score, 4)}

    pm = PluginManager()
    pm.register_factor(MomentumFactor)

    report = ValuationPipeline(plugin_manager=pm).run(_security())

    assert report.plugin_factors == {"MomentumFactor": {"revenue_momentum": 0.9231}}
    assert any("[PLUGIN FACTOR MomentumFactor]" in n for n in report.triangulation.notes)
    # A factor plugin alone provides no implied move for synthesis.
    assert report.synthesis_upside is None


def test_discovered_example_plugin_flows_through_pipeline():
    """File-based discovery -> instantiation -> pipeline influence, end to end."""
    manager = PluginManager()
    examples_dir = (
        Path(__file__).resolve().parent.parent / "src" / "iam" / "plugins" / "examples"
    )
    manager.discover_plugins(str(examples_dir))

    # Discovery picks up both the realistic lens and the trivial stub.
    assert "FcfYieldLens" in manager.lens_plugins
    assert "ExampleLens" in manager.lens_plugins

    report = ValuationPipeline(plugin_manager=manager).run(_security())

    # The stub (no narrative / implied move) is skipped by the bridge;
    # the realistic lens flows all the way through.
    names = [lr.lens_name for lr in (report.plugin_lenses or [])]
    assert names == ["fcf_yield_plugin"]
    assert report.synthesis_upside is not None


def test_default_pipeline_consults_global_plugin_manager():
    reset_plugin_manager()
    try:
        get_plugin_manager().register_lens(FcfYieldLens)
        report = ValuationPipeline().run(_security())  # no explicit manager
        assert report.plugin_lenses is not None
        assert report.plugin_lenses[0].lens_name == "fcf_yield_plugin"
    finally:
        reset_plugin_manager()


def test_broken_lens_plugin_does_not_break_the_run():
    class ExplodingLens(FcfYieldLens):
        def analyze(self, data):
            raise RuntimeError("plugin bug")

    pm = PluginManager()
    pm.register_lens(ExplodingLens)

    report = ValuationPipeline(plugin_manager=pm).run(_security())
    assert report.ticker == "PLUG"
    assert report.plugin_lenses is None
