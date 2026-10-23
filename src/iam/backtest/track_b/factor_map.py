"""Map engine factors to JKP factors, and build Track B priors and candidate E.

Each backtestable engine factor is linked to the JKP factors that measure the
same idea (Section 5, Rung 2 of the backtest strategy). A link records the
engine's own direction on the JKP characteristic: +1 if the composite favours
stocks with high values of it, -1 if it favours low values. Penalties count by
their effect on the composite, so ``leverage_penalty`` favours low debt.

JKP returns are already signed by the literature's direction, so the sign used
for an engine factor is ``engine_direction * jkp_direction``. A link where the two
disagree comes out with sign -1: the Track B return then shows what the engine's
bet would have earned, and a negative Sharpe ratio is evidence against the prior.

Factors with no JKP counterpart (qualitative inputs, positioning data, or no
cross-sectional variation) are listed in ``UNMAPPED`` with the reason.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from iam.backtest.weight_selection import (
    CandidateContext,
    _blend,
    empirical_bayes_data_weight,
    ic_mean_and_se,
)

from .cache import TrackBDataError
from .jkp import jkp_directions, jkp_wide

# Prior-estimation window: before Track A starts in 2010 (Section 5, Rung 2).
PRIOR_WINDOW_START = "1963-07-01"
PRIOR_WINDOW_END = "2009-12-31"
MIN_MONTHS_FOR_SHARPE = 60
CANDIDATE_E = "track_b"


@dataclass(frozen=True)
class JKPLink:
    jkp: str  # JKP factor code, e.g. "ival_me"
    engine_direction: int  # +1: the composite favours high values of the characteristic
    label: str  # JKP's descriptive name


ENGINE_TO_JKP: dict[str, tuple[JKPLink, ...]] = {
    "intrinsic_value": (
        JKPLink("ival_me", +1, "Intrinsic value-to-market"),
        JKPLink("fcf_me", +1, "Free cash flow-to-price"),
        JKPLink("ocf_me", +1, "Operating cash flow-to-market"),
    ),
    # Proxy only: no JKP factor compares implied with demonstrated growth. Long
    # equity duration and low book-to-market both mean the price leans on distant,
    # high growth, which the factor scores as hard expectations.
    "expectations_difficulty": (
        JKPLink("eq_dur", -1, "Equity duration"),
        JKPLink("be_me", +1, "Book-to-market equity"),
    ),
    "quality": (
        JKPLink("qmj", +1, "Quality minus Junk: Composite"),
        JKPLink("qmj_prof", +1, "Quality minus Junk: Profitability"),
        JKPLink("qmj_safety", +1, "Quality minus Junk: Safety"),
        JKPLink("gp_at", +1, "Gross profits-to-assets"),
        JKPLink("ebit_bev", +1, "Return on net operating assets"),
        JKPLink("chcsho_12m", -1, "Net stock issues"),
    ),
    # JKP sorts are market-wide; the engine compares with sector peers, so this
    # link tests the valuation idea, not the peer adjustment.
    "relative_value": (
        JKPLink("ebitda_mev", +1, "Ebitda-to-market enterprise value"),
        JKPLink("ni_me", +1, "Earnings-to-price"),
        JKPLink("fcf_me", +1, "Free cash flow-to-price"),
        JKPLink("sale_me", +1, "Sales-to-market"),
    ),
    # Analyst revisions and news sentiment have no JKP counterpart.
    "sentiment": (
        JKPLink("ret_6_1", +1, "Price momentum t-6 to t-1"),
        JKPLink("ret_12_1", +1, "Price momentum t-12 to t-1"),
        JKPLink("niq_su", +1, "Standardized earnings surprise"),
        JKPLink("saleq_su", +1, "Standardized Revenue surprise"),
    ),
    "earnings_quality": (
        JKPLink("oaccruals_at", -1, "Operating accruals"),
        JKPLink("taccruals_at", -1, "Total accruals"),
        JKPLink("oaccruals_ni", -1, "Percent operating accruals"),
    ),
    "leverage_penalty": (
        JKPLink("netdebt_me", -1, "Net debt-to-price"),
        JKPLink("debt_me", -1, "Debt-to-market"),
        JKPLink("o_score", -1, "Ohlson O-score"),
        JKPLink("z_score", +1, "Altman Z-score"),
    ),
    # A PEG-like penalty on high P/E for the growth delivered: favours high E/P.
    "fragility_penalty": (JKPLink("ni_me", +1, "Earnings-to-price"),),
}

# Theme cross-check: JKP themes are signed like their factors, and each listed
# theme points the same way as the engine factor.
ENGINE_TO_JKP_THEME: dict[str, str] = {
    "intrinsic_value": "value",
    "relative_value": "value",
    "quality": "quality",
    "sentiment": "momentum",
    "earnings_quality": "accruals",
    "leverage_penalty": "low_leverage",
}

UNMAPPED: dict[str, str] = {
    "reflexivity": "qualitative inputs only",
    "reinvestment_runway": "qualitative inputs only (TAM, adjacencies)",
    "crowding": "needs ownership and positioning data JKP does not publish",
    "macro_regime": "no cross-sectional variation; tested by Rung 4 instead",
    "execution_risk_penalty": "qualitative inputs only",
}


def link_signs(directions: dict[str, int]) -> dict[str, dict[str, int]]:
    """Sign applied to each JKP return for each engine factor; raises on unknown codes."""
    missing = sorted({lk.jkp for links in ENGINE_TO_JKP.values() for lk in links} - set(directions))
    if missing:
        raise TrackBDataError(f"JKP data lacks mapped factors {missing}")
    return {
        engine: {lk.jkp: lk.engine_direction * directions[lk.jkp] for lk in links}
        for engine, links in ENGINE_TO_JKP.items()
    }


def engine_factor_returns(jkp_long: pd.DataFrame) -> pd.DataFrame:
    """Monthly Track B return for each mapped engine factor.

    The equal-weighted mean of its signed JKP returns, for months where every
    linked JKP factor has a return (so the mix does not change over time).
    """
    signs = link_signs(jkp_directions(jkp_long))
    wide = jkp_wide(jkp_long)
    out = {}
    for engine, by_code in signs.items():
        cols = list(by_code)
        signed = wide[cols] * pd.Series(by_code)
        out[engine] = signed.mean(axis=1).where(signed.notna().all(axis=1))
    return pd.DataFrame(out).dropna(how="all")


def engine_theme_returns(jkp_theme_long: pd.DataFrame) -> pd.DataFrame:
    """Monthly JKP theme return for each engine factor in ``ENGINE_TO_JKP_THEME``."""
    wide = jkp_wide(jkp_theme_long)
    missing = sorted(set(ENGINE_TO_JKP_THEME.values()) - set(wide.columns))
    if missing:
        raise TrackBDataError(f"JKP theme data lacks themes {missing}")
    return pd.DataFrame({e: wide[t] for e, t in ENGINE_TO_JKP_THEME.items()})


def window_stats(
    returns: pd.DataFrame,
    start: str = PRIOR_WINDOW_START,
    end: str = PRIOR_WINDOW_END,
    min_months: int = MIN_MONTHS_FOR_SHARPE,
) -> pd.DataFrame:
    """Annualised mean, volatility and Sharpe ratio per column over [start, end].

    Factor returns are long-short, so the Sharpe ratio uses no risk-free rate.
    Columns with fewer than ``min_months`` returns get NaN.
    """
    window = returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    n = window.notna().sum()
    mean = window.mean() * 12
    vol = window.std(ddof=1) * np.sqrt(12)
    sharpe = (mean / vol).where(n >= min_months)
    return pd.DataFrame({"n_months": n, "ann_mean": mean, "ann_vol": vol, "sharpe": sharpe})


def window_correlations(
    returns: pd.DataFrame, start: str = PRIOR_WINDOW_START, end: str = PRIOR_WINDOW_END
) -> pd.DataFrame:
    return returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].corr()


def sharpe_vector(stats: pd.DataFrame, factor_names: Iterable[str]) -> np.ndarray:
    """Sharpe ratios in ``factor_names`` order, NaN for factors without Track B data."""
    sharpe = stats["sharpe"]
    return np.array([sharpe.get(n, np.nan) for n in factor_names], dtype=float)


def track_b_target(sharpes: np.ndarray, prior: np.ndarray) -> np.ndarray | None:
    """Weights before shrinkage: mapped factors share their prior mass by positive Sharpe.

    Factors without Track B evidence (NaN) keep their prior weight, so candidate E
    only re-allocates among factors the evidence covers. Returns None if no mapped
    factor has a positive Sharpe ratio.
    """
    prior = np.asarray(prior, dtype=float)
    sharpes = np.asarray(sharpes, dtype=float)
    mapped = np.isfinite(sharpes)
    positive = np.where(mapped, np.maximum(sharpes, 0.0), 0.0)
    if positive.sum() <= 0:
        return None
    target = prior.copy()
    target[mapped] = prior[mapped].sum() * positive[mapped] / positive.sum()
    total = target.sum()
    return target / total if total > 0 else None


def make_track_b_candidate(sharpes: np.ndarray) -> Callable[[CandidateContext], np.ndarray]:
    """Candidate E: the Track B target shrunk to the prior with the empirical-Bayes weight.

    ``sharpes`` is aligned with the horse race's ``factor_names`` (see
    :func:`sharpe_vector`). The data weight is estimated from the training fold's
    ICs exactly as for candidate C, so E differs from the prior only as far as the
    Track A evidence allows.
    """
    sharpes = np.asarray(sharpes, dtype=float)

    def candidate_track_b(ctx: CandidateContext) -> np.ndarray:
        if len(sharpes) != len(ctx.prior):
            raise ValueError("sharpes must align with the horse race factor_names")
        means, ses = ic_mean_and_se(ctx.ic, ctx.nw_lags)
        data_w = empirical_bayes_data_weight(means * ctx.haircut, ses)
        return _blend(data_w, track_b_target(sharpes, ctx.prior), ctx.prior)

    return candidate_track_b
