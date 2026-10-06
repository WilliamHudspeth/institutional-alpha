from __future__ import annotations

import os
import traceback
from typing import Any

import pandas as pd

try:
    import streamlit as st
except ImportError:  # pragma: no cover - optional GUI dependency
    st = None

from iam.compliance.disclaimers import SHORT_DISCLAIMER
from iam.integration.orchestrator import Orchestrator
from iam.pipeline.orchestrator import ValuationPipeline
from iam.reasoning.business_reality import BusinessRealityEngine

# What the card number is: integration.Orchestrator applies no arbitration adjustment to
# the value (the reliability weight is carried separately), so it is the bottom-up Ke.
COST_OF_EQUITY_CAPTION = "Cost of equity (bottom-up, no arbitration adjustment)"


def _fmt_money(value: float | None, digits: int = 2) -> str:
    """Format a monetary float value as $X.XX or 'n/a' when missing."""
    if value is None:
        return "n/a"
    return f"${value:.{digits}f}"


def _fmt_pct(value: float | None, digits: int = 2, signed: bool = False) -> str:
    """Format a fraction as a percentage or 'n/a' when missing."""
    if value is None:
        return "n/a"
    if signed:
        return f"{value * 100:+.{digits}f}%"
    return f"{value * 100:.{digits}f}%"


def _fmt_delta(value: float | None, digits: int = 2) -> str:
    """Format a numeric delta with an explicit sign or 'n/a' when missing."""
    if value is None:
        return "n/a"
    return f"{value:+.{digits}f}"


def _extract_pwev_target(report: Any) -> float | None:
    """Extract pwev_target from pipeline report, returning None when absent."""
    if report is None:
        return None
    intrinsic = getattr(report, "intrinsic", None)
    if intrinsic is None:
        return None
    components = getattr(intrinsic, "components", None)
    if not isinstance(components, dict):
        return None
    val = components.get("pwev_target")
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _extract_discount_rate(report: Any) -> float | None:
    """Extract discount rate from intrinsic assumptions or fallback to cost_of_equity."""
    if report is None:
        return None
    intrinsic = getattr(report, "intrinsic", None)
    if intrinsic is None:
        return None
    assumptions = getattr(intrinsic, "assumptions", None)
    if not isinstance(assumptions, dict):
        return None
    rate = assumptions.get("discount_rate")
    if rate is None:
        rate = assumptions.get("cost_of_equity")
    if rate is None:
        return None
    try:
        return float(rate)
    except (ValueError, TypeError):
        return None


def _pe_breakeven_html(dec: Any, be: Any, dec_note: str | None, be_note: str | None) -> str:
    """HTML for the P/E decomposition and break-even card. Missing values show as n/a."""
    import html as _html

    def _x(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.2f}x"

    def g(name: str) -> float | None:
        return getattr(dec, name, None)

    rows = (
        f"<tr><td>Commodity P/E (1/Ke)</td><td>{_x(g('commodity_pe'))}</td></tr>"
        f"<tr><td>Franchise P/E</td><td>{_x(g('franchise_pe'))}</td></tr>"
        f"<tr><td>Steady-state value / share</td><td>{_fmt_money(g('steady_state_value'))}</td></tr>"
        f"<tr><td>PVGO share of price</td><td>{_fmt_pct(g('pvgo_share'), 1)}</td></tr>"
    )
    dec_html = f"<table>{rows}</table>"
    if dec is None and dec_note:
        dec_html += f"<div>{_html.escape(dec_note)}</div>"
    if be is None:
        be_html = f"<div>n/a: {_html.escape(be_note or 'break-even unavailable')}</div>"
    elif not be.contour:
        be_html = "<div>n/a: no growth in range reaches the price at any margin</div>"
    else:
        be_rows = "".join(
            f"<tr><td>{_fmt_pct(m, 1)}</td><td>{_fmt_pct(gr, 1)}</td></tr>" for m, gr in be.contour
        )
        be_html = (
            "<table><tr><th>Operating margin</th><th>Break-even growth</th></tr>"
            f"{be_rows}</table>"
        )
    return f"<div class='card'>{dec_html}<hr/>{be_html}</div>"


def _extract_cost_of_equity(orch_result: Any) -> float | None:
    """Extract the cost of equity (bottom-up, unadjusted) from the orchestrator result dict."""
    if not isinstance(orch_result, dict):
        return None
    mr = orch_result.get("model_result")
    if mr is None:
        return None
    val = getattr(mr, "value", None)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _load_security(ticker: str) -> tuple[Any, str | None]:
    """Fetch live data for ``ticker``: ``(security, None)`` or ``(None, reason)``.

    A failed fetch returns no Security, so the caller stops instead of valuing an
    empty one (which would put invented numbers on screen).
    """
    from iam.data.providers.yfinance_adapter import fetch_security

    try:
        return fetch_security(ticker), None
    except Exception as e:  # noqa: BLE001 - shown to the user verbatim
        return None, f"Could not fetch data for {ticker}; no valuation was run. ({e})"


def main() -> None:
    if st is None:
        raise RuntimeError(
            "Streamlit is required to run the GUI. Install with: pip install streamlit"
        )

    # Page Config
    st.set_page_config(
        page_title="Institutional Alpha Terminal (IAM)",
        page_icon="📊",
        layout="wide",
    )

    # Custom Sleek CSS for Dark Terminal Theme
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');

        html, body, [data-testid="stAppViewContainer"] {
            background-color: #0d1117;
            color: #c9d1d9;
            font-family: 'Outfit', sans-serif;
        }

        .stTextInput>div>div>input {
            background-color: #161b22;
            color: #f0f6fc;
            border: 1px solid #30363d;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
        }

        .stButton>button {
            background: linear-gradient(135deg, #1f6feb 0%, #094cb5 100%);
            color: white;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            padding: 0.6rem 2rem;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(31, 111, 235, 0.3);
        }

        .stButton>button:hover {
            background: linear-gradient(135deg, #388bfd 0%, #1f6feb 100%);
            box-shadow: 0 6px 16px rgba(31, 111, 235, 0.5);
            transform: translateY(-1px);
        }

        .card {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }

        .metric-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 2rem;
            font-weight: 700;
            color: #58a6ff;
        }

        .metric-label {
            font-size: 0.9rem;
            text-transform: uppercase;
            color: #8b949e;
            letter-spacing: 1px;
        }

        .terminal-header {
            font-family: 'JetBrains Mono', monospace;
            color: #58a6ff;
            font-weight: 800;
            border-bottom: 2px solid #30363d;
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }

        .table-container {
            font-family: 'JetBrains Mono', monospace;
            width: 100%;
            border-collapse: collapse;
        }

        .table-container th {
            background-color: #21262d;
            color: #8b949e;
            text-align: left;
            padding: 8px;
            border-bottom: 2px solid #30363d;
        }

        .table-container td {
            padding: 8px;
            border-bottom: 1px solid #21262d;
        }

        .badge {
            display: inline-block;
            padding: 0.25em 0.6em;
            font-size: 75%;
            font-weight: 700;
            line-height: 1;
            text-align: center;
            white-space: nowrap;
            vertical-align: baseline;
            border-radius: 0.25rem;
        }

        .badge-bullish {
            background-color: rgba(46, 160, 67, 0.15);
            color: #3fb950;
            border: 1px solid rgba(46, 160, 67, 0.3);
        }

        .badge-bearish {
            background-color: rgba(248, 81, 73, 0.15);
            color: #f85149;
            border: 1px solid rgba(248, 81, 73, 0.3);
        }

        .badge-neutral {
            background-color: rgba(139, 148, 158, 0.15);
            color: #8b949e;
            border: 1px solid rgba(139, 148, 158, 0.3);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Header
    st.markdown(
        "<h1 style='color: #f0f6fc;'>🏛️ Institutional Alpha Terminal</h1>", unsafe_allow_html=True
    )
    st.markdown(
        "<p style='color: #8b949e;'>Multi-lens equity scoring, valuation arbitration, & expectation battlefield engine.</p>",
        unsafe_allow_html=True,
    )

    # Layout: Sidebar controls
    st.sidebar.markdown("### Valuation Control Center")
    ticker = st.sidebar.text_input("Ticker Symbol", "BLK").upper().strip()
    growth_override = st.sidebar.slider(
        "Forecast Growth Override (%)", min_value=0.0, max_value=30.0, value=8.0, step=0.5
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🧬 Research Integrity")

    # Load live backtest integrity stats
    try:
        from iam.backtest.multiple_testing import compute_validation_metrics
        from iam.engine.composite import DEFAULT_WEIGHTS

        ic_path = "data/results/ic/ic_horizon_1m.csv"
        if os.path.exists(ic_path):
            df_ic = pd.read_csv(ic_path)
            val_metrics = compute_validation_metrics(df_ic, list(DEFAULT_WEIGHTS.keys()))
            pbo = getattr(val_metrics, "pbo", None)
            dsr = getattr(val_metrics, "dsr", None)

            pbo_col = (
                "#7ee787"
                if (pbo is not None and pbo < 0.05)
                else ("#ff7b72" if pbo is not None else "#8b949e")
            )
            dsr_col = "#7ee787" if (dsr is not None and dsr > 1.0) else "#8b949e"
            pbo_display = _fmt_pct(pbo, 1)
            dsr_display = f"{dsr:.2f}x" if dsr is not None else "n/a"

            st.sidebar.markdown(
                f"""
                <div style="font-size: 0.85rem; color: #8b949e; margin-bottom: 1.0rem;">
                    Backtest Overfitting (PBO): <b style="color: {pbo_col};">{pbo_display}</b><br>
                    Deflated Sharpe (DSR): <b style="color: {dsr_col};">{dsr_display}</b>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.sidebar.info("Backtest results not found for integrity audit.")
    except Exception:
        st.sidebar.warning("Integrity layer initialization failed.")

    run_button = st.sidebar.button("Run Valuation Engine")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🧪 Portfolio Lab")
    basket_input = (
        st.sidebar.text_input("Basket (comma-separated)", "AAPL,MSFT,NVDA").upper().strip()
    )
    run_portfolio = st.sidebar.button("Run Portfolio Optimization")

    if run_button:
        with st.spinner(f"Initiating institutional pipeline for {ticker}..."):
            try:
                # 1. Initialize data & orchestrator
                security, fetch_error = _load_security(ticker)
                if security is None:
                    # Never value an empty Security: every number would be invented.
                    st.error(fetch_error)
                    st.stop()

                if security.qualitative is None:
                    security.qualitative = {}
                security.qualitative["forecast_growth"] = growth_override / 100.0

                orch = Orchestrator()
                orch_result = orch.value_security(security)

                # 2. Run valuation pipeline (full 7-stages)
                pipeline = ValuationPipeline()
                report = pipeline.run(security)

                # 3. Assess Business Reality narrative
                try:
                    reality_assessment = BusinessRealityEngine().assess(security)
                    reality_narrative = reality_assessment.narrative
                except Exception:
                    reality_narrative = "Business reality analysis unavailable."

                # ----- Render Dashboard -----
                col1, col2, col3 = st.columns(3)

                with col1:
                    verdict_rec = (
                        orch_result.get("recommendation", "n/a")
                        if isinstance(orch_result, dict)
                        else "n/a"
                    )
                    coe = _extract_cost_of_equity(orch_result)
                    st.markdown(
                        f"""
                        <div class="card">
                            <div class="metric-label">Institutional Verdict</div>
                            <div class="metric-value">{verdict_rec}</div>
                            <div style="color: #8b949e; margin-top: 0.5rem; font-size: 0.9rem;">
                                {COST_OF_EQUITY_CAPTION}: <b>{_fmt_pct(coe, 2)}</b>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with col2:
                    pwev_target = _extract_pwev_target(report)
                    st.markdown(
                        f"""
                        <div class="card">
                            <div class="metric-label">Weighted Fair Value (PWEV)</div>
                            <div class="metric-value">{_fmt_money(pwev_target)}</div>
                            <div style="color: #8b949e; margin-top: 0.5rem; font-size: 0.9rem;">
                                Probabilistic Weighted Equity Value target
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with col3:
                    # Real value from the intrinsic stage (FCFE discount rate, or the
                    # SOTP cost of equity); missing -> "n/a", never an invented 9%.
                    discount_rate = _extract_discount_rate(report)
                    st.markdown(
                        f"""
                        <div class="card">
                            <div class="metric-label">Discount Rate (WACC)</div>
                            <div class="metric-value">{_fmt_pct(discount_rate, 2)}</div>
                            <div style="color: #8b949e; margin-top: 0.5rem; font-size: 0.9rem;">
                                Baseline discount rate applied to cash flows
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # Row 2: Scenario Matrix & Battlefield
                col_left, col_right = st.columns(2)

                with col_left:
                    st.markdown(
                        "<div class='terminal-header'>📊 Probabilistic Scenario Weight Matrix</div>",
                        unsafe_allow_html=True,
                    )
                    if (
                        report
                        and report.intrinsic
                        and isinstance(report.intrinsic.components, dict)
                        and "scenarios" in report.intrinsic.components
                    ):
                        scenarios = report.intrinsic.components["scenarios"]
                        rows_html = ""
                        for case_name, data in scenarios.items():
                            prob = data.get("prob") if isinstance(data, dict) else None
                            target = data.get("target") if isinstance(data, dict) else None
                            implied_ret = data.get("upside") if isinstance(data, dict) else None
                            if implied_ret is not None and implied_ret > 0.05:
                                ret_class = "badge-bullish"
                            elif implied_ret is not None and implied_ret < -0.05:
                                ret_class = "badge-bearish"
                            else:
                                ret_class = "badge-neutral"
                            rows_html += f"""
                            <tr>
                                <td><b>{case_name}</b></td>
                                <td>{_fmt_pct(prob, 0)}</td>
                                <td>{_fmt_money(target)}</td>
                                <td><span class="badge {ret_class}">{_fmt_pct(implied_ret, 1, signed=True)}</span></td>
                            </tr>
                            """

                        st.markdown(
                            f"""
                            <table class="table-container">
                                <thead>
                                    <tr>
                                        <th>Scenario Case</th>
                                        <th>Weight</th>
                                        <th>Target Value</th>
                                        <th>Implied Return</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows_html}
                                </tbody>
                            </table>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.info("No scenario metrics available.")

                with col_right:
                    st.markdown(
                        "<div class='terminal-header'>⚔️ Valuation Battlefield (Stage 4b)</div>",
                        unsafe_allow_html=True,
                    )
                    if report and report.battlefield:
                        import html as _html

                        from iam.pipeline.battlefield import PARAM_LABELS

                        bf = report.battlefield
                        rows_html = "".join(
                            f"<tr><td>{PARAM_LABELS.get(c.parameter, c.parameter)}</td>"
                            f"<td>{_fmt_pct(getattr(c, 'value_intrinsic', None), 2)}</td>"
                            f"<td>{_fmt_pct(getattr(c, 'value_market', None), 2)}</td>"
                            f"<td>{_fmt_delta(getattr(c, 'delta_value', None), 2)}</td>"
                            f"<td>{_fmt_pct(getattr(c, 'share', None), 0)}</td></tr>"
                            for c in bf.contributions
                        )
                        gap_html = (
                            f"Market-implied value vs ours: <b>{_fmt_pct(bf.value_gap_pct, 1, signed=True)}</b>"
                            if getattr(bf, "value_gap_pct", None) is not None
                            else "Value gap not measurable."
                        )
                        st.markdown(
                            f"""
                            <div class="card">
                                <div class="metric-label">Key Disagreement</div>
                                <div style="color: #ff7b72; font-family: 'JetBrains Mono', monospace; font-size: 1.2rem; font-weight: 700; margin-bottom: 0.8rem;">
                                    {_html.escape(bf.key_disagreement)}
                                </div>
                                <table class="table-container" style="font-size: 0.9rem;">
                                    <thead>
                                        <tr>
                                            <th>Assumption</th>
                                            <th>Ours</th>
                                            <th>Market-Implied</th>
                                            <th>Value Δ/sh</th>
                                            <th>Share</th>
                                        </tr>
                                    </thead>
                                    <tbody>{rows_html}</tbody>
                                </table>
                                <div style="margin-top: 1rem; font-size: 0.9rem; color: #8b949e;">
                                    {gap_html}
                                </div>
                                <div style="font-style: italic; margin-top: 0.5rem; font-size: 0.85rem; color: #8b949e;">
                                    Value Δ = change in value if only that input moved to the market's figure.
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.info("Valuation battlefield telemetry is not active.")

                # Row 3: Business Reality & Drift Detector
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    st.markdown(
                        "<div class='terminal-header'>🧠 Business Reality Narrative</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"""
                        <div class="card" style="font-size: 0.95rem; line-height: 1.6; color: #8b949e;">
                            {reality_narrative}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with col_b2:
                    st.markdown(
                        "<div class='terminal-header'>🚨 Thesis Drift Detector</div>",
                        unsafe_allow_html=True,
                    )
                    if report and report.drift_report:
                        import html as _html

                        dr = report.drift_report
                        status_class = "badge-bearish" if dr.has_drift else "badge-bullish"
                        status_text = "DRIFT DETECTED" if dr.has_drift else "THESIS ALIGNED"
                        breach_html = "".join(
                            f"<li>{_html.escape(b.describe())}</li>" for b in dr.breaches
                        )
                        st.markdown(
                            f"""
                            <div class="card">
                                <div style="margin-bottom: 0.8rem;">
                                    Status: <span class="badge {status_class}">{status_text}</span>
                                </div>
                                <ul style="font-size: 0.9rem;">{breach_html}</ul>
                                <div style="font-size: 0.85rem; color: #8b949e;">
                                    Skipped (missing data): {_html.escape(", ".join(dr.skipped) or "none")}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if dr.source_banner:
                            st.warning(dr.source_banner)
                    elif report:
                        from iam.thesis.drift import no_thesis_message

                        st.info(no_thesis_message(report.ticker))
                    else:
                        st.info("Thesis drift metrics unavailable.")

                # Row 3b: P/E decomposition and growth x margin break-even (consensus Ke)
                st.markdown("---")
                st.markdown(
                    "<div class='terminal-header'>"
                    "🧮 P/E Decomposition & Break-even (consensus Ke)</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    _pe_breakeven_html(
                        getattr(report, "pe_decomposition", None),
                        getattr(report, "breakeven", None),
                        getattr(report, "pe_decomposition_note", None),
                        getattr(report, "breakeven_note", None),
                    ),
                    unsafe_allow_html=True,
                )

                # Row 4: TI-89 Projection & Plugins / ML
                st.markdown("---")
                col_vis, col_sys = st.columns([2, 1])
                with col_vis:
                    st.markdown(
                        "<div class='terminal-header'>🧊 TI-89 Valuation Map</div>",
                        unsafe_allow_html=True,
                    )
                    try:
                        from iam.ui.ti89_graph import ti89_figure
                        from iam.valuation.value_grid import build_value_grid

                        grid = build_value_grid(report) if report else None
                        if grid is None:
                            st.info(
                                "n/a: the valuation map needs an FCFE build-up for this ticker."
                            )
                        else:
                            fig = ti89_figure(grid)
                            if fig:
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.info("Plotly is required for 3D GUI visualization.")
                    except Exception as e:
                        st.error(f"Failed to generate TI-89 3D plot: {e}")

                with col_sys:
                    st.markdown(
                        "<div class='terminal-header'>🤖 ML & System Status</div>",
                        unsafe_allow_html=True,
                    )
                    # ML Lens
                    try:
                        from iam.ml.ml_lens import MLDiagnosticLens

                        lens = MLDiagnosticLens()
                        res = lens.compute(security)
                        color = "#ff7b72" if res.confidence < 1.0 else "#7ee787"
                        st.markdown(
                            f"""
                            <div class="card">
                                <div class="metric-label">ML Diagnostic Lens</div>
                                <div style="color: {color}; font-weight: 600; margin-top: 0.5rem;">{res.narrative}</div>
                            </div>
                        """,
                            unsafe_allow_html=True,
                        )
                    except Exception:
                        st.info("ML Diagnostics unavailable.")

                    # Plugins
                    try:
                        from iam.plugins.manager import PluginManager

                        pm = PluginManager()
                        plugins = pm.list_plugins() if hasattr(pm, "list_plugins") else []
                        st.markdown(
                            f"""
                            <div class="card" style="margin-top: 1rem;">
                                <div class="metric-label">Active Plugins</div>
                                <div style="font-size: 1.2rem; font-weight: 700; color: #58a6ff;">{len(plugins)}</div>
                            </div>
                        """,
                            unsafe_allow_html=True,
                        )
                    except Exception:
                        pass

            except Exception as e:
                st.error(f"Execution Error: {e}")
                with st.expander("Show Traceback"):
                    st.code(traceback.format_exc())

    elif run_portfolio:
        with st.spinner("Fetching basket data and running portfolio optimization..."):
            from iam.data.providers.yfinance_adapter import fetch_security
            from iam.portfolio.optimizer import OptimizationConstraints, PositionSizer

            tickers = [t.strip() for t in basket_input.split(",") if t.strip()]
            if not tickers:
                st.warning("Please enter at least one ticker.")
            else:
                expected_returns = {}
                volatilities = {}
                position_returns = {}
                valid_tickers = []

                from datetime import datetime, timedelta

                from iam.data.fetcher import RedundantDataFetcher

                price_fetcher = RedundantDataFetcher()
                hist_end = datetime.now()
                hist_start = hist_end - timedelta(days=90)

                for t in tickers:
                    try:
                        sec = fetch_security(t)
                        valid_tickers.append(t)

                        # CAPM-style expected return from beta (4.3% risk-free +
                        # 5% ERP); this is a standard proxy, not the real
                        # historical-return series, which isn't in Security yet.
                        beta = (
                            sec.market.beta if (sec.market and sec.market.beta is not None) else 1.0
                        )
                        expected_returns[t] = 0.043 + beta * 0.05

                        # Real daily returns for risk parity's covariance matrix,
                        # via the same RedundantDataFetcher the backtest module
                        # uses (not the yfinance_adapter's Security, which doesn't
                        # carry price_history).
                        prices = price_fetcher.fetch_price_history(t, hist_start, hist_end)
                        returns = (
                            prices.pct_change().dropna().tolist() if prices is not None else []
                        )
                        position_returns[t] = returns
                        # Kelly's volatility input: realized daily-return stdev
                        # annualized, falling back to the beta proxy if the price
                        # history fetch came back too short to be meaningful.
                        if len(returns) >= 5:
                            import statistics

                            volatilities[t] = statistics.stdev(returns) * (252**0.5)
                        else:
                            volatilities[t] = beta * 0.15
                    except Exception as e:
                        st.warning(f"Failed to fetch data for {t}, skipping. ({e})")

                if valid_tickers:
                    constraints = OptimizationConstraints()
                    kelly_weights = PositionSizer.size_by_kelly(
                        valid_tickers,
                        expected_returns,
                        volatilities,
                        constraints=constraints,
                    )
                    rp_weights = PositionSizer.size_by_risk_parity(
                        valid_tickers, position_returns, constraints=constraints
                    )

                    st.markdown(
                        "<div class='terminal-header'>🧪 Portfolio Optimization Results</div>",
                        unsafe_allow_html=True,
                    )

                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(
                            "<div class='card'>"
                            "<div class='metric-label'>Kelly Criterion Sizing</div>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        rows = "".join(
                            [
                                f"<tr><td><b>{t}</b></td><td>{_fmt_pct(kelly_weights.get(t) if isinstance(kelly_weights, dict) else None, 1)}</td></tr>"
                                for t in valid_tickers
                            ]
                        )
                        st.markdown(
                            f"""
                        <table class="table-container">
                            <thead><tr><th>Ticker</th><th>Kelly Target Weight</th></tr></thead>
                            <tbody>{rows}</tbody>
                        </table>
                        """,
                            unsafe_allow_html=True,
                        )

                    with col2:
                        st.markdown(
                            "<div class='card'>"
                            "<div class='metric-label'>Risk Parity (Equal Risk Contribution)</div>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        rows = "".join(
                            [
                                f"<tr><td><b>{t}</b></td><td>{_fmt_pct(rp_weights.get(t) if isinstance(rp_weights, dict) else None, 1)}</td></tr>"
                                for t in valid_tickers
                            ]
                        )
                        st.markdown(
                            f"""
                        <table class="table-container">
                            <thead><tr><th>Ticker</th><th>Risk Parity Weight</th></tr></thead>
                            <tbody>{rows}</tbody>
                        </table>
                        """,
                            unsafe_allow_html=True,
                        )

    else:
        st.info(
            "👈 Enter a ticker and press 'Run Valuation Engine' in the control center to begin, or run Portfolio Lab."
        )

    st.markdown(
        f"<div style='margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #30363d; "
        f"font-size: 0.75rem; color: #8b949e; text-align: center;'>{SHORT_DISCLAIMER}</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__" or (st is not None and hasattr(st, "runtime") and st.runtime.exists()):
    main()
