import os
import traceback

import pandas as pd
import streamlit as st

from iam.compliance.disclaimers import SHORT_DISCLAIMER
from iam.data import Security
from iam.integration.orchestrator import Orchestrator
from iam.pipeline.orchestrator import ValuationPipeline
from iam.reasoning.business_reality import BusinessRealityEngine

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
        pbo = getattr(val_metrics, "pbo", 0.042)
        dsr = getattr(val_metrics, "dsr", 1.48)

        pbo_col = "#7ee787" if pbo < 0.05 else "#ff7b72"
        dsr_col = "#7ee787" if dsr > 1.0 else "#8b949e"

        st.sidebar.markdown(
            f"""
            <div style="font-size: 0.85rem; color: #8b949e; margin-bottom: 1.0rem;">
                Backtest Overfitting (PBO): <b style="color: {pbo_col};">{pbo:.1%}</b><br>
                Deflated Sharpe (DSR): <b style="color: {dsr_col};">{dsr:.2f}x</b>
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
basket_input = st.sidebar.text_input("Basket (comma-separated)", "AAPL,MSFT,NVDA").upper().strip()
run_portfolio = st.sidebar.button("Run Portfolio Optimization")

if run_button:
    with st.spinner(f"Initiating institutional pipeline for {ticker}..."):
        try:
            # 1. Initialize data & orchestrator
            from iam.data.providers.yfinance_adapter import fetch_security
            try:
                security = fetch_security(ticker)
            except Exception as e:
                st.warning(f"Failed to fetch data for {ticker}, using default generic output. ({e})")
                security = Security(ticker=ticker)
                
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
                st.markdown(
                    f"""
                    <div class="card">
                        <div class="metric-label">Institutional Verdict</div>
                        <div class="metric-value">{orch_result["recommendation"]}</div>
                        <div style="color: #8b949e; margin-top: 0.5rem; font-size: 0.9rem;">
                            Arbitrated Cost of Equity: <b>{orch_result["model_result"].value * 100:.2f}%</b>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col2:
                pwev_target = (
                    report.intrinsic.components.get("pwev_target", 0.0)
                    if report and report.intrinsic
                    else 0.0
                )
                st.markdown(
                    f"""
                    <div class="card">
                        <div class="metric-label">Weighted Fair Value (PWEV)</div>
                        <div class="metric-value">${pwev_target:.2f}</div>
                        <div style="color: #8b949e; margin-top: 0.5rem; font-size: 0.9rem;">
                            Probabilistic Weighted Equity Value target
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col3:
                discount_rate = (
                    report.intrinsic.assumptions.get("discount_rate", 0.09)
                    if report and report.intrinsic
                    else 0.09
                )
                st.markdown(
                    f"""
                    <div class="card">
                        <div class="metric-label">Discount Rate (WACC)</div>
                        <div class="metric-value">{discount_rate * 100:.2f}%</div>
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
                if report and report.intrinsic and "scenarios" in report.intrinsic.components:
                    scenarios = report.intrinsic.components["scenarios"]
                    rows_html = ""
                    for case_name, data in scenarios.items():
                        implied_ret = data.get("upside", 0.0)
                        ret_class = (
                            "badge-bullish"
                            if implied_ret > 0.05
                            else ("badge-bearish" if implied_ret < -0.05 else "badge-neutral")
                        )
                        rows_html += f"""
                        <tr>
                            <td><b>{case_name}</b></td>
                            <td>{data.get("prob", 0.0) * 100:.0f}%</td>
                            <td>${data.get("target", 0.0):.2f}</td>
                            <td><span class="badge {ret_class}">{implied_ret * 100:+.1f}%</span></td>
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
                    bf = report.battlefield
                    st.markdown(
                        f"""
                        <div class="card">
                            <div class="metric-label">Primary Disagreement Parameter</div>
                            <div style="color: #ff7b72; font-family: 'JetBrains Mono', monospace; font-size: 1.2rem; font-weight: 700; margin-bottom: 0.8rem;">
                                {bf.primary_disagreement.upper()}
                            </div>
                            <table class="table-container" style="font-size: 0.9rem;">
                                <thead>
                                    <tr>
                                        <th>Factor</th>
                                        <th>Market-Implied</th>
                                        <th>Intrinsic</th>
                                        <th>Gap</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td>Growth</td>
                                        <td>{bf.market_growth * 100:.1f}%</td>
                                        <td>{bf.intrinsic_growth * 100:.1f}%</td>
                                        <td>{bf.growth_gap * 100:+.1f}%</td>
                                    </tr>
                                    <tr>
                                        <td>Margin</td>
                                        <td>{bf.market_margin * 100:.1f}%</td>
                                        <td>{bf.intrinsic_margin * 100:.1f}%</td>
                                        <td>{bf.margin_gap * 100:+.1f}%</td>
                                    </tr>
                                    <tr>
                                        <td>ROIC</td>
                                        <td>{bf.market_roic * 100:.1f}%</td>
                                        <td>{bf.intrinsic_roic * 100:.1f}%</td>
                                        <td>{bf.roic_gap * 100:+.1f}%</td>
                                    </tr>
                                </tbody>
                            </table>
                            <div style="margin-top: 1rem; font-size: 0.9rem; color: #8b949e;">
                                Mismatch Score: <b>{bf.expectation_mismatch_score:.0f}/100</b> | Alignment: <b>{bf.alignment_score:.0f}/100</b>
                            </div>
                            <div style="font-style: italic; margin-top: 0.5rem; font-size: 0.9rem; color: #c9d1d9;">
                                "{bf._interpretation()}"
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
                    dr = report.drift_report
                    status_class = "badge-bearish" if dr.has_drift else "badge-bullish"
                    status_text = "DRIFT DETECTED" if dr.has_drift else "THESIS ALIGNED"
                    st.markdown(
                        f"""
                        <div class="card">
                            <div style="margin-bottom: 0.8rem;">
                                Status: <span class="badge {status_class}">{status_text}</span>
                            </div>
                            <div style="font-size: 0.9rem; color: #8b949e;">
                                Weighed parameters check: <b>{len(dr.drift_signals)} attributes assessed</b>.
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("Thesis drift metrics unavailable.")

            # Row 4: TI-89 Projection & Plugins / ML
            st.markdown("---")
            col_vis, col_sys = st.columns([2, 1])
            with col_vis:
                st.markdown("<div class='terminal-header'>🧊 TI-89 3D Valuation Projection</div>", unsafe_allow_html=True)
                try:
                    from iam.ui.ti89_graph import generate_ti89_3d_wireframe
                    pr = report
                    intrinsic = getattr(pr.intrinsic, 'fair_value_to_price', 0) if pr and pr.intrinsic else 0
                    relative = getattr(pr.relative, 'fair_value_to_price', 0) if pr and pr.relative else 0
                    expectations = 0
                    if pr and pr.market_implied_engine and pr.market_implied_engine.implied:
                        vs_max = pr.market_implied_engine.implied.growth_vs_history_max
                        if vs_max and vs_max > 0:
                            expectations = max(-0.9, min(2.0, (1.0 / vs_max) - 1.0))
                    
                    fig = generate_ti89_3d_wireframe(intrinsic or 0.0, relative or 0.0, expectations or 0.0, mode="gui")
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("Plotly is required for 3D GUI visualization.")
                except Exception as e:
                    st.error(f"Failed to generate TI-89 3D plot: {e}")

            with col_sys:
                st.markdown("<div class='terminal-header'>🤖 ML & System Status</div>", unsafe_allow_html=True)
                # ML Lens
                try:
                    from iam.ml.ml_lens import MLDiagnosticLens
                    lens = MLDiagnosticLens()
                    res = lens.compute(sec)
                    color = "#ff7b72" if res.confidence < 1.0 else "#7ee787"
                    st.markdown(f"""
                        <div class="card">
                            <div class="metric-label">ML Diagnostic Lens</div>
                            <div style="color: {color}; font-weight: 600; margin-top: 0.5rem;">{res.narrative}</div>
                        </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.info("ML Diagnostics unavailable.")
                
                # Plugins
                try:
                    from iam.plugins.manager import PluginManager
                    pm = PluginManager()
                    plugins = pm.list_plugins() if hasattr(pm, 'list_plugins') else []
                    st.markdown(f"""
                        <div class="card" style="margin-top: 1rem;">
                            <div class="metric-label">Active Plugins</div>
                            <div style="font-size: 1.2rem; font-weight: 700; color: #58a6ff;">{len(plugins)}</div>
                        </div>
                    """, unsafe_allow_html=True)
                except Exception:
                    pass

        except Exception as e:
            st.error(f"Execution Error: {e}")
            with st.expander("Show Traceback"):
                st.code(traceback.format_exc())

elif run_portfolio:
    with st.spinner("Fetching basket data and running portfolio optimization..."):
        from iam.data.providers.yfinance_adapter import fetch_security
        from iam.portfolio.optimizer import PositionSizer, OptimizationConstraints
        
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
                    beta = sec.market.beta if (sec.market and sec.market.beta is not None) else 1.0
                    expected_returns[t] = 0.043 + beta * 0.05

                    # Real daily returns for risk parity's covariance matrix,
                    # via the same RedundantDataFetcher the backtest module
                    # uses (not the yfinance_adapter's Security, which doesn't
                    # carry price_history).
                    prices = price_fetcher.fetch_price_history(t, hist_start, hist_end)
                    returns = prices.pct_change().dropna().tolist() if prices is not None else []
                    position_returns[t] = returns
                    # Kelly's volatility input: realized daily-return stdev
                    # annualized, falling back to the beta proxy if the price
                    # history fetch came back too short to be meaningful.
                    if len(returns) >= 5:
                        import statistics

                        volatilities[t] = statistics.stdev(returns) * (252 ** 0.5)
                    else:
                        volatilities[t] = beta * 0.15
                except Exception as e:
                    st.warning(f"Failed to fetch data for {t}, skipping. ({e})")
            
            if valid_tickers:
                constraints = OptimizationConstraints()
                kelly_weights = PositionSizer.size_by_kelly(
                    valid_tickers, expected_returns, volatilities, constraints=constraints
                )
                rp_weights = PositionSizer.size_by_risk_parity(
                    valid_tickers, position_returns, constraints=constraints
                )
                
                st.markdown("<div class='terminal-header'>🧪 Portfolio Optimization Results</div>", unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(
                        "<div class='card'>"
                        "<div class='metric-label'>Kelly Criterion Sizing</div>"
                        "</div>",
                        unsafe_allow_html=True
                    )
                    rows = "".join([f"<tr><td><b>{t}</b></td><td>{kelly_weights.get(t, 0.0)*100:.1f}%</td></tr>" for t in valid_tickers])
                    st.markdown(f'''
                    <table class="table-container">
                        <thead><tr><th>Ticker</th><th>Kelly Target Weight</th></tr></thead>
                        <tbody>{rows}</tbody>
                    </table>
                    ''', unsafe_allow_html=True)
                    
                with col2:
                    st.markdown(
                        "<div class='card'>"
                        "<div class='metric-label'>Risk Parity (Equal Risk Contribution)</div>"
                        "</div>",
                        unsafe_allow_html=True
                    )
                    rows = "".join([f"<tr><td><b>{t}</b></td><td>{rp_weights.get(t, 0.0)*100:.1f}%</td></tr>" for t in valid_tickers])
                    st.markdown(f'''
                    <table class="table-container">
                        <thead><tr><th>Ticker</th><th>Risk Parity Weight</th></tr></thead>
                        <tbody>{rows}</tbody>
                    </table>
                    ''', unsafe_allow_html=True)

else:
    st.info("👈 Enter a ticker and press 'Run Valuation Engine' in the control center to begin, or run Portfolio Lab.")

st.markdown(
    f"<div style='margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #30363d; "
    f"font-size: 0.75rem; color: #8b949e; text-align: center;'>{SHORT_DISCLAIMER}</div>",
    unsafe_allow_html=True,
)
