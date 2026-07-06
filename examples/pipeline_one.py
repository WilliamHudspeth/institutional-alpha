"""Run the v0.4.0-rc1 valuation pipeline on a hypothetical security.

Demonstrates the sequence: Reverse DCF -> Relative -> Intrinsic -> Triangulation.

Run from repo root after `pip install -e .`:

    python examples/pipeline_one.py
"""

from iam import Fundamentals, MarketData, Security, ValuationPipeline


def main() -> None:
    # A hypothetical high-multiple software name. The reverse DCF will reveal
    # what growth the market is implicitly demanding, the relative stage will
    # check whether that demand is consistent with peers and history, and the
    # intrinsic DCF will provide an independent fair-value anchor.
    sec = Security(
        ticker="HYPCO",
        name="Hypothetical Co.",
        sector="Software",
        fundamentals=Fundamentals(
            revenue_ttm=10_000.0,
            revenue_history=[10_000, 8_500, 7_200, 6_100, 5_200],
            fcf_ttm=2_800.0,
            shares_outstanding=1_000.0,
            net_income_ttm=2_400.0,
            ebitda_ttm=3_500.0,
        ),
        market=MarketData(
            price=180.0,
            market_cap=180_000.0,
            pe_ttm=75.0,
            pe_history=[
                60,
                55,
                50,
                70,
                80,
                65,
                55,
                45,
                40,
                35,
                50,
                60,
                70,
                80,
                65,
                55,
                45,
                40,
                35,
                50,
                60,
                70,
                50,
                45,
            ],
            ev_ebitda=50.7,
            sector_ev_ebitda_median=22.0,
            fcf_yield=0.0156,
            peer_fcf_yields=[0.03, 0.025, 0.04, 0.02],
        ),
        qualitative={
            # If you believe the company can grow FCFE at 18% for the next
            # decade, drop that here. The intrinsic DCF uses these exact
            # numbers, leaving the reverse DCF to tell you what the market
            # is implicitly assuming on its own.
            "forecast_growth": 0.18,
            "forecast_discount_rate": 0.10,
            "forecast_terminal_growth": 0.025,
        },
    )

    report = ValuationPipeline().run(sec)
    print(report.explain())


if __name__ == "__main__":
    main()
