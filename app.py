import streamlit as st
import traceback
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
st.markdown("<h1 style='color: #f0f6fc;'>🏛️ Institutional Alpha Terminal</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #8b949e;'>Multi-lens equity scoring, valuation arbitration, & expectation battlefield engine.</p>", unsafe_allow_html=True)

# Layout: Sidebar controls
st.sidebar.markdown("### Valuation Control Center")
ticker = st.sidebar.text_input("Ticker Symbol", "BLK").upper().strip()
growth_override = st.sidebar.slider("Forecast Growth Override (%)", min_value=0.0, max_value=30.0, value=8.0, step=0.5)

run_button = st.sidebar.button("Run Valuation Engine")

if run_button:
    with st.spinner(f"Initiating institutional pipeline for {ticker}..."):
        try:
            # 1. Initialize data & orchestrator
            security = Security(ticker=ticker)
            if security.qualitative is None:
                security.qualitative = {}
            security.qualitative["forecast_growth"] = growth_override / 100.0

            orch = Orchestrator()
            orch_result = orch.value_security(security)
            
            # 2. Run valuation pipeline (full 7-stages)
            pipeline = ValuationPipeline()
            # Simulate or fetch synthesis upside
            synthesis_upside = 0.02  # Default baseline
            report = pipeline.run(security, synthesis_upside=synthesis_upside)
            
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
                        <div class="metric-value">{orch_result['recommendation']}</div>
                        <div style="color: #8b949e; margin-top: 0.5rem; font-size: 0.9rem;">
                            Arbitrated Cost of Equity: <b>{orch_result['model_result'].value * 100:.2f}%</b>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
            with col2:
                pwev_target = report.intrinsic.components.get("pwev_target", 0.0) if report and report.intrinsic else 0.0
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
                    unsafe_allow_html=True
                )
                
            with col3:
                discount_rate = report.intrinsic.assumptions.get("discount_rate", 0.09) if report and report.intrinsic else 0.09
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
                    unsafe_allow_html=True
                )

            # Row 2: Scenario Matrix & Battlefield
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.markdown("<div class='terminal-header'>📊 Probabilistic Scenario Weight Matrix</div>", unsafe_allow_html=True)
                if report and report.intrinsic and "scenarios" in report.intrinsic.components:
                    scenarios = report.intrinsic.components["scenarios"]
                    rows_html = ""
                    for case_name, data in scenarios.items():
                        implied_ret = data.get("upside", 0.0)
                        ret_class = "badge-bullish" if implied_ret > 0.05 else ("badge-bearish" if implied_ret < -0.05 else "badge-neutral")
                        rows_html += f"""
                        <tr>
                            <td><b>{case_name}</b></td>
                            <td>{data.get('prob', 0.0)*100:.0f}%</td>
                            <td>${data.get('target', 0.0):.2f}</td>
                            <td><span class="badge {ret_class}">{implied_ret*100:+.1f}%</span></td>
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
                        unsafe_allow_html=True
                    )
                else:
                    st.info("No scenario metrics available.")
                    
            with col_right:
                st.markdown("<div class='terminal-header'>⚔️ Valuation Battlefield (Stage 4b)</div>", unsafe_allow_html=True)
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
                                        <td>{bf.market_growth*100:.1f}%</td>
                                        <td>{bf.intrinsic_growth*100:.1f}%</td>
                                        <td>{bf.growth_gap*100:+.1f}%</td>
                                    </tr>
                                    <tr>
                                        <td>Margin</td>
                                        <td>{bf.market_margin*100:.1f}%</td>
                                        <td>{bf.intrinsic_margin*100:.1f}%</td>
                                        <td>{bf.margin_gap*100:+.1f}%</td>
                                    </tr>
                                    <tr>
                                        <td>ROIC</td>
                                        <td>{bf.market_roic*100:.1f}%</td>
                                        <td>{bf.intrinsic_roic*100:.1f}%</td>
                                        <td>{bf.roic_gap*100:+.1f}%</td>
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
                        unsafe_allow_html=True
                    )
                else:
                    st.info("Valuation battlefield telemetry is not active.")

            # Row 3: Business Reality & Drift Detector
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.markdown("<div class='terminal-header'>🧠 Business Reality Narrative</div>", unsafe_allow_html=True)
                st.markdown(
                    f"""
                    <div class="card" style="font-size: 0.95rem; line-height: 1.6; color: #8b949e;">
                        {reality_narrative}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
            with col_b2:
                st.markdown("<div class='terminal-header'>🚨 Thesis Drift Detector</div>", unsafe_allow_html=True)
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
                        unsafe_allow_html=True
                    )
                else:
                    st.info("Thesis drift metrics unavailable.")

        except Exception as e:
            st.error(f"Execution Error: {e}")
            with st.expander("Show Traceback"):
                st.code(traceback.format_exc())
else:
    st.info("👈 Enter a ticker and press 'Run Valuation Engine' in the control center to begin.")
