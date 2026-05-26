"""Yahoo Finance data adapter for the IAM framework."""

import logging
from typing import Optional

import yfinance as yf
import pandas as pd

from iam.data.security import Security, Fundamentals, MarketData

logger = logging.getLogger(__name__)

class YFinanceAdapter:
    """Fetches live data from Yahoo Finance and maps it to IAM data structures."""

    def fetch(self, ticker: str) -> Security:
        """Fetch data for a ticker and return a populated Security object."""
        logger.info(f"Fetching data for {ticker} via yfinance...")
        yt = yf.Ticker(ticker)
        
        # Info dictionary contains most TTM metrics and multiples
        info = yt.info
        
        # Fetch financials for historical series
        try:
            financials = yt.financials
        except Exception:
            financials = pd.DataFrame()

        return Security(
            ticker=ticker.upper(),
            name=info.get("shortName", ticker.upper()),
            sector=info.get("sector", "Unknown"),
            fundamentals=self._build_fundamentals(info, financials, yt),
            market=self._build_market_data(info),
            qualitative={}  # Left empty for the user to inject their thesis later
        )

    def _build_fundamentals(self, info: dict, financials: pd.DataFrame, yt: yf.Ticker) -> Fundamentals:
        f = Fundamentals()
        
        # Basic TTM Metrics
        f.revenue_ttm = info.get("totalRevenue")
        f.fcf_ttm = info.get("freeCashflow")
        f.shares_outstanding = info.get("sharesOutstanding")
        f.net_income_ttm = info.get("netIncomeToCommon")
        f.ebitda_ttm = info.get("ebitda")
        f.total_debt = info.get("totalDebt")
        f.cash_and_equivalents = info.get("totalCash")
        
        # Operating Margin TTM
        if info.get("operatingMargins"):
            f.operating_margin = info.get("operatingMargins")

        # --- EXTRACT CASH FLOW DATA (Working Capital, SBC, Capex) ---
        try:
            cf = yt.cashflow
            if not cf.empty:
                # 1. Working Capital Quality
                if "Change In Working Capital" in cf.index:
                    wc_val = cf.loc["Change In Working Capital"].iloc[0]
                    f.change_in_working_capital = float(wc_val) if pd.notnull(wc_val) else None

                # 2. Stock Based Compensation (Used for SBC/Revenue check)
                if "Stock Based Compensation" in cf.index:
                    sbc_val = cf.loc["Stock Based Compensation"].iloc[0]
                    f.sbc_ttm = float(sbc_val) if pd.notnull(sbc_val) else 0.0

                # 3. Capital Expenditures (Used for Capex Authenticity check)
                if "Capital Expenditure" in cf.index:
                    # yfinance returns Capex as a negative number; we take absolute for the factor
                    capex_val = cf.loc["Capital Expenditure"].iloc[0]
                    f.capex_ttm = abs(float(capex_val)) if pd.notnull(capex_val) else None
        except Exception as e:
            logger.warning(f"Failed to parse cash flow statement for {yt.ticker}: {e}")
            
        # Parse History
        if not financials.empty:
            try:
                # Revenue History
                if "Total Revenue" in financials.index:
                    rev_series = financials.loc["Total Revenue"].dropna()
                    f.revenue_history = rev_series.tolist()
                    
                # Operating Margin History
                if "Operating Income" in financials.index and "Total Revenue" in financials.index:
                    op_inc = financials.loc["Operating Income"]
                    rev = financials.loc["Total Revenue"]
                    margins = (op_inc / rev).dropna()
                    f.operating_margin_history = margins.tolist()
            except Exception as e:
                logger.warning(f"Failed to parse historical financials: {e}")

        return f

    def _build_market_data(self, info: dict) -> MarketData:
        m = MarketData()
        
        m.price = info.get("currentPrice") or info.get("regularMarketPrice")
        m.market_cap = info.get("marketCap")
        m.pe_ttm = info.get("trailingPE")
        
        # Enterprise Multiples
        m.ev_ebitda = info.get("enterpriseToEbitda")
        m.ev_sales = info.get("enterpriseToRevenue")
        
        # Free Cash Flow Yield calculation
        fcf = info.get("freeCashflow")
        market_cap = info.get("marketCap")
        if fcf is not None and market_cap is not None and market_cap > 0:
            m.fcf_yield = fcf / market_cap
            
        return m
