"""Individual growth estimators from historical, fundamental, and market data.

Implements the four primary pillars of corporate growth estimation (Damodaran,
*Investment Valuation* ch. 11): log-linear historical revenue and operating
income trends, reinvestment-driven fundamental growth (ROIC x RR or ROE x
retention), analyst forward EPS growth, and reverse-DCF market-implied growth,
alongside uncertainty floors calibrated to empirical persistence studies
(Mauboussin, Callahan and Majd, *The Base Rate Book*, 2016; Chan, Karceski and
Lakonishok, "The Level and Persistence of Growth Rates", JF 2003).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any

from iam.data.security import Security
from iam.engine.market_implied import MarketImpliedEngine
from iam.growth.types import GrowthEstimate

MODEL_ERROR: dict[str, float] = {
    "historical_revenue": 0.04,
    "historical_operating_income": 0.06,
    "fundamental": 0.06,
    "fundamental_approx": 0.08,
    # Empirical: unbiased (-0.3 pts) but 10 pts mean absolute error vs realised 3y growth
    # in the point-in-time backtest, with ~no rank correlation (book ROIC distortions).
    "normalised_fundamental": 0.12,
    "analyst_forward": 0.10,
}

MAX_YEARS = 5


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _trend(
    values_most_recent_first: Sequence[float | None],
    max_years: int = MAX_YEARS,
) -> tuple[float, int, float] | None:
    """Fit an OLS log-linear trend on the leading positive run (oldest t = 0)."""
    positive_run: list[float] = []
    for v in values_most_recent_first:
        if v is None or v <= 0:
            break
        positive_run.append(float(v))
        if len(positive_run) == max_years + 1:
            break

    n_pts = len(positive_run)
    if n_pts < 3:
        return None

    chronological = list(reversed(positive_run))
    logs = [math.log(v) for v in chronological]
    t_mean = (n_pts - 1) / 2.0
    y_mean = sum(logs) / n_pts

    num = sum((t - t_mean) * (y - y_mean) for t, y in enumerate(logs))
    den = sum((t - t_mean) ** 2 for t in range(n_pts))
    slope = num / den if den > 0 else 0.0

    value = math.exp(slope) - 1.0
    n_years = n_pts - 1
    yoy_logs = [logs[i + 1] - logs[i] for i in range(n_years)]
    sd = statistics.stdev(yoy_logs) if len(yoy_logs) >= 2 else 0.0
    return value, n_years, sd


def historical_revenue(security: Security) -> GrowthEstimate:
    """Estimate 5-year revenue growth via OLS log-linear trend over up to 5 years."""
    method = "historical_revenue"
    rev_hist = security.fundamentals.revenue_history or []
    res = _trend(rev_hist, max_years=MAX_YEARS)
    if res is None:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="At least 3 positive annual values are needed for historical revenue trend.",
        )

    value, n_years, sd = res
    model_err = MODEL_ERROR[method]
    std_error = math.sqrt((sd**2) / n_years + model_err**2)
    confidence = _clamp(1.0 - std_error / 0.25, 0.1, 1.0)
    return GrowthEstimate(
        method=method,
        value=value,
        std_error=std_error,
        horizon_years=5,
        confidence=confidence,
        inputs={"n_years": float(n_years), "sd": sd},
    )


def historical_operating_income(security: Security) -> GrowthEstimate:
    """Estimate 5-year operating-income growth from revenue and margin history."""
    method = "historical_operating_income"
    f = security.fundamentals
    rev_hist = f.revenue_history or []
    margin_hist = f.operating_margin_history or []
    n = min(len(rev_hist), len(margin_hist))
    op_inc: list[float | None] = []
    for i in range(n):
        r = rev_hist[i]
        m = margin_hist[i]
        op_inc.append(r * m if (r is not None and m is not None) else None)

    res = _trend(op_inc, max_years=MAX_YEARS)
    if res is None:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="At least 3 positive annual operating income values are needed.",
        )

    value, n_years, sd = res
    model_err = MODEL_ERROR[method]
    std_error = math.sqrt((sd**2) / n_years + model_err**2)
    confidence = _clamp(1.0 - std_error / 0.25, 0.1, 1.0)
    return GrowthEstimate(
        method=method,
        value=value,
        std_error=std_error,
        horizon_years=5,
        confidence=confidence,
        inputs={"n_years": float(n_years), "sd": sd},
    )


def fundamental(security: Security) -> GrowthEstimate:
    """Estimate 5-year fundamental growth from reinvestment rate and return on capital."""
    method = "fundamental"
    f = security.fundamentals
    sector = security.sector or ""
    is_financial = "Financial" in sector
    no_reinv_metrics = f.ebitda_ttm is None and f.capex_ttm is None and f.fcf_ttm is None

    if is_financial or no_reinv_metrics:
        if (
            f.net_income_ttm is None
            or f.book_equity is None
            or f.book_equity <= 0
            or f.payout_ratio is None
        ):
            return GrowthEstimate(
                method=method,
                value=None,
                std_error=None,
                horizon_years=5,
                confidence=0.0,
                reason="Equity fundamental growth requires net_income_ttm, positive book_equity, and payout_ratio.",
            )
        roe = f.net_income_ttm / f.book_equity
        retention = _clamp(1.0 - f.payout_ratio, -0.5, 1.5)
        value = _clamp(retention * roe, -0.10, 0.40)
        std_error = MODEL_ERROR["fundamental"]
        confidence = _clamp(1.0 - std_error / 0.25, 0.1, 1.0)
        return GrowthEstimate(
            method=method,
            value=value,
            std_error=std_error,
            horizon_years=5,
            confidence=confidence,
            inputs={"roe": roe, "retention": retention},
        )

    if f.revenue_ttm is None or f.operating_margin is None:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="Fundamental growth requires revenue_ttm and operating_margin.",
        )

    tax = _clamp(f.effective_tax_rate, 0.0, 0.35) if f.effective_tax_rate is not None else 0.21
    ebit = f.revenue_ttm * f.operating_margin
    nopat = ebit * (1.0 - tax)
    if nopat <= 0:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="NOPAT must be positive for fundamental reinvestment growth.",
        )

    roic: float | None = None
    if f.roic_history and f.roic_history[0] is not None:
        roic = float(f.roic_history[0])
    elif f.book_equity is not None:
        invested_capital = f.book_equity + (f.total_debt or 0.0) - (f.cash_and_equivalents or 0.0)
        if invested_capital > 0:
            roic = nopat / invested_capital

    if roic is None:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="ROIC unavailable (neither roic_history nor positive invested capital).",
        )

    notes: list[str] = []
    if f.ebitda_ttm is not None and f.capex_ttm is not None:
        da = f.ebitda_ttm - ebit
        net_capex = abs(f.capex_ttm) - da
        working_capital = -(f.change_in_working_capital or 0.0)
        rr_raw = (net_capex + working_capital) / nopat
        std_error = MODEL_ERROR["fundamental"]
    elif f.fcf_ttm is not None:
        rr_raw = 1.0 - f.fcf_ttm / nopat
        std_error = MODEL_ERROR["fundamental_approx"]
        notes.append("Reinvestment rate approximated from free cash flow.")
    else:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="Reinvestment requires (ebitda_ttm and capex_ttm) or fcf_ttm.",
        )

    rr = _clamp(rr_raw, -0.5, 1.5)
    value = _clamp(rr * roic, -0.10, 0.40)
    confidence = _clamp(1.0 - std_error / 0.25, 0.1, 1.0)
    return GrowthEstimate(
        method=method,
        value=value,
        std_error=std_error,
        horizon_years=5,
        confidence=confidence,
        inputs={"reinvestment_rate": rr, "roic": roic},
        notes=tuple(notes),
    )


def analyst_forward(security: Security) -> GrowthEstimate:
    """Estimate 1-year forward EPS growth from trailing and forward P/E ratios."""
    method = "analyst_forward"
    m = security.market
    if m.pe_ttm is None or m.pe_forward is None or m.pe_ttm <= 0 or m.pe_forward <= 0:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=1,
            confidence=0.0,
            reason="Analyst forward EPS growth requires positive pe_ttm and pe_forward.",
        )

    raw = m.pe_ttm / m.pe_forward - 1.0
    value = _clamp(raw, -0.5, 1.0)
    return GrowthEstimate(
        method=method,
        value=value,
        std_error=MODEL_ERROR[method],
        horizon_years=1,
        confidence=0.5,
        inputs={"pe_ttm": float(m.pe_ttm), "pe_forward": float(m.pe_forward)},
    )


def market_implied(
    security: Security,
    engine_result: Any = None,
    value: float | None = None,
) -> GrowthEstimate:
    """Extract 10-year market-implied growth from reverse DCF without using it in DCF."""
    method = "market_implied"
    if value is not None:
        conf = (
            float(engine_result.confidence)
            if (
                engine_result is not None and getattr(engine_result, "confidence", None) is not None
            )
            else 0.5
        )
        return GrowthEstimate(
            method=method,
            value=float(value),
            std_error=None,
            horizon_years=10,
            confidence=conf,
            inputs={"implied_growth": float(value)},
        )

    res = engine_result
    if res is None:
        try:
            res = MarketImpliedEngine().compute(security)
        except Exception as exc:
            return GrowthEstimate(
                method=method,
                value=None,
                std_error=None,
                horizon_years=10,
                confidence=0.0,
                reason=f"MarketImpliedEngine failed: {exc}",
            )

    comp = getattr(res, "components", None) or {}
    implied = comp.get("implied_growth")
    conf_raw = getattr(res, "confidence", None)
    conf = float(conf_raw) if conf_raw is not None else 0.5

    if implied is None:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=10,
            confidence=0.0,
            reason="Market-implied growth not available in engine result.",
        )

    return GrowthEstimate(
        method=method,
        value=float(implied),
        std_error=None,
        horizon_years=10,
        confidence=conf,
        inputs={"implied_growth": float(implied)},
    )


def normalised_fundamental(security: Security) -> GrowthEstimate:
    """Estimate 5-year normalised fundamental growth (Damodaran growth lectures)."""
    method = "normalised_fundamental"
    f = security.fundamentals
    sector = security.sector or ""

    if "Financial" in sector:
        ni_hist = f.net_income_history or []
        payout_hist = f.equity_payout_history or []
        be_hist = f.book_equity_history or []
        limit = min(len(ni_hist), len(payout_hist), max(0, len(be_hist) - 1))
        usable_fin: list[tuple[float, float, float]] = []
        for i in range(limit):
            ni_i = ni_hist[i]
            pay_i = payout_hist[i]
            be_prev = be_hist[i + 1]
            if ni_i is None or pay_i is None or be_prev is None or be_prev <= 0:
                break
            usable_fin.append((float(ni_i), float(pay_i), float(be_prev)))
            if len(usable_fin) == MAX_YEARS:
                break

        n = len(usable_fin)
        if n < 3:
            return GrowthEstimate(
                method=method,
                value=None,
                std_error=None,
                horizon_years=5,
                confidence=0.0,
                reason="At least 3 years with net income, payout, and positive beginning equity are required.",
            )

        sum_ni = sum(x[0] for x in usable_fin)
        if sum_ni <= 0:
            return GrowthEstimate(
                method=method,
                value=None,
                std_error=None,
                horizon_years=5,
                confidence=0.0,
                reason="cumulative net income not positive",
            )

        sum_payout = sum(x[1] for x in usable_fin)
        sum_be = sum(x[2] for x in usable_fin)
        roe_bar = sum_ni / sum_be
        retention = _clamp(1.0 - sum_payout / sum_ni, 0.0, 1.0)
        value = _clamp(retention * roe_bar, -0.10, 0.40)

        roes = [ni_i / be_i for ni_i, _, be_i in usable_fin]
        sd_roe = statistics.stdev(roes) if len(roes) >= 2 else 0.0
        std_error = math.sqrt(MODEL_ERROR[method] ** 2 + ((retention * sd_roe) ** 2) / n)
        confidence = _clamp(1.0 - std_error / 0.25, 0.1, 1.0)
        return GrowthEstimate(
            method=method,
            value=value,
            std_error=std_error,
            horizon_years=5,
            confidence=confidence,
            inputs={
                "retention": retention,
                "roe_normalised": roe_bar,
                "n_years": n,
            },
        )

    nopat_hist = f.nopat_history or []
    reinv_hist = f.reinvestment_history or []
    ic_hist = f.invested_capital_history or []
    limit = min(len(nopat_hist), len(reinv_hist), max(0, len(ic_hist) - 1))
    usable_op: list[tuple[float, float, float]] = []
    for i in range(limit):
        nopat_i = nopat_hist[i]
        reinv_i = reinv_hist[i]
        ic_prev = ic_hist[i + 1]
        if nopat_i is None or reinv_i is None or ic_prev is None or ic_prev <= 0:
            break
        usable_op.append((float(nopat_i), float(reinv_i), float(ic_prev)))
        if len(usable_op) == MAX_YEARS:
            break

    n = len(usable_op)
    if n < 3:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="At least 3 years with NOPAT, reinvestment, and positive beginning invested capital are required.",
        )

    sum_nopat = sum(x[0] for x in usable_op)
    if sum_nopat <= 0:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="cumulative NOPAT not positive",
        )

    rr = _clamp(sum(x[1] for x in usable_op) / sum_nopat, -0.5, 1.0)
    roics = [nopat_i / ic_i for nopat_i, _, ic_i in usable_op]
    roic_bar_raw = statistics.median(roics)
    if roic_bar_raw <= 0:
        return GrowthEstimate(
            method=method,
            value=None,
            std_error=None,
            horizon_years=5,
            confidence=0.0,
            reason="normalised ROIC not positive",
        )

    roic_bar = _clamp(roic_bar_raw, 0.0, 0.60)
    roic_now = _clamp(roics[0], 0.0, 0.60)
    g_reinv = rr * roic_bar

    notes: list[str] = []
    if roic_now > 0:
        g_eff_annual = _clamp((roic_bar / roic_now) ** (1.0 / 3.0) - 1.0, -0.15, 0.15)
        g_eff = g_eff_annual * (3.0 / 5.0)
    else:
        g_eff = 0.0
        notes.append("current ROIC not positive; no efficiency term")

    if roic_bar < 0.08:
        notes.append(
            "normalised ROIC below a typical cost of capital: this growth adds little value"
        )

    value = _clamp(g_reinv + g_eff, -0.10, 0.40)

    sd_roic = statistics.stdev(roics) if len(roics) >= 2 else 0.0
    rrs = [_clamp(reinv_i / nopat_i, -1.0, 2.0) for nopat_i, reinv_i, _ in usable_op if nopat_i > 0]
    sd_rr = statistics.stdev(rrs) if len(rrs) >= 2 else 0.0
    std_error = math.sqrt(
        MODEL_ERROR[method] ** 2 + ((rr * sd_roic) ** 2) / n + ((roic_bar * sd_rr) ** 2) / n
    )
    confidence = _clamp(1.0 - std_error / 0.25, 0.1, 1.0)

    return GrowthEstimate(
        method=method,
        value=value,
        std_error=std_error,
        horizon_years=5,
        confidence=confidence,
        inputs={
            "reinvestment_rate": rr,
            "roic_normalised": roic_bar,
            "roic_now": roic_now,
            "g_reinvestment": g_reinv,
            "g_efficiency": g_eff,
            "n_years": n,
        },
        notes=tuple(notes),
    )
