"""End-to-end example: build a hypothetical security and score it.

Run from the repo root after `pip install -e .`:

    python examples/score_one.py
"""

from iam import Fundamentals, MacroContext, MarketData, Security, score


def main() -> None:
    # A hypothetical high-quality compounder
    sec = Security(
        ticker="EXAMPLE",
        name="Example Inc.",
        sector="Software",
        industry="Application Software",
        fundamentals=Fundamentals(
            revenue_ttm=10_000.0,
            revenue_history=[10_000, 8_500, 7_200, 6_100, 5_200],  # most recent first
            gross_margin=0.78,
            gross_margin_history=[0.78, 0.77, 0.76, 0.75, 0.74],
            operating_margin=0.32,
            operating_margin_history=[0.32, 0.30, 0.28, 0.25, 0.22],
            net_income_ttm=2_400.0,
            fcf_ttm=2_800.0,
            fcf_history=[2_800, 2_300, 1_800, 1_400, 1_100],
            capex_ttm=300.0,
            sbc_ttm=600.0,
            total_debt=1_500.0,
            cash_and_equivalents=4_000.0,
            interest_expense_ttm=80.0,
            ebitda_ttm=3_500.0,
            debt_maturity_within_24m=200.0,
            current_ratio=2.5,
            roic_history=[0.28, 0.27, 0.26, 0.24, 0.22],
            incremental_roic=0.30,
            shares_outstanding=1_000.0,
            shares_outstanding_history=[1_000, 1_005, 1_010, 1_015, 1_020],
            accruals_ratio=0.02,
            one_time_adjustments_count_5y=1,
        ),
        market=MarketData(
            price=180.0,
            market_cap=180_000.0,
            enterprise_value=177_500.0,  # market cap minus net cash
            pe_ttm=75.0,
            pe_forward=55.0,
            ev_ebitda=50.7,
            fcf_yield=0.0156,
            sector_ev_ebitda_median=22.0,
            peer_fcf_yields=[0.03, 0.025, 0.04, 0.02],
            hedge_fund_ownership_pct=0.12,
            retail_ownership_pct=0.18,
            short_interest_pct_float=0.03,
            options_call_put_skew=1.3,
            passive_index_ownership_pct=0.22,
            analyst_revisions_breadth_30d=0.4,
            earnings_surprise_history=[0.05, 0.03, 0.04, 0.06],
        ),
        macro=MacroContext(
            real_rate_10y=0.018,
            real_rate_trend="flat",
            liquidity_index=0.1,
            credit_spread_hy=0.035,
            yield_curve_slope_10y_2y=0.005,
            pmi_direction="expanding",
            dxy_trend="flat",
        ),
        qualitative={
            # 0 = weak/none, 1 = very strong
            "equity_currency_strength": 0.7,
            "network_effect_strength":  0.6,
            "talent_attraction":        0.8,
            "acquisition_optionality":  0.5,
            "narrative_reinforcement":  0.6,
            "tam_remaining":            0.7,
            "geographic_expansion":     0.5,
            "adjacency_potential":      0.6,
            "recurring_revenue_mix":    0.9,
            # Penalty inputs: 0 = no risk, 1 = severe risk
            "operational_complexity":   0.3,
            "supply_chain_dependency":  0.2,
            "regulatory_risk":          0.3,
            "geographic_risk":          0.2,
            "integration_risk":         0.1,
        },
    )

    result = score(sec)
    print(result.explain())


if __name__ == "__main__":
    main()
