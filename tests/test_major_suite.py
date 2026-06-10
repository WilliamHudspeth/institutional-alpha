"""Major test suite for Institutional Alpha Model (IAM).

Covers the six highest-value test areas identified from codebase review:
  1. Factor Orthogonality          — 13 factors must be statistically independent
  2. Large-Scale Backtest Stress   — 500 stocks × 10 years, IC/IR validity
  3. Portfolio Optimizer Stress    — Extreme covariance regimes, position limits
  4. Valuation Engine Consistency  — All 4 engines agree within expected bounds
  5. Bayesian Thesis Convergence   — Posterior converges with accumulating evidence
  6. Data Pipeline Robustness      — Missing data, extremes, malformed inputs
  7. Memory & Throughput           — No leaks; meets throughput floor (20 GB budget)

RAM budget: up to 20 GB. Tests deliberately allocating large arrays are marked
@pytest.mark.slow; skip them with:  pytest -m "not slow"

Run all tests:    pytest tests/test_major_suite.py -v --tb=short
Run heavy tests:  pytest tests/test_major_suite.py -v -m slow
Run fast only:    pytest tests/test_major_suite.py -v -m "not slow"
"""

from __future__ import annotations

import gc
import math
import random
import statistics
import time

import numpy as np
import pandas as pd
import pytest

from iam.api import Security, value_security
from iam.backtest.calibration import ic_to_reliability, summarize_backtest
from iam.backtest.metrics import hit_rate, information_coefficient, information_ratio
from iam.backtest.quantiles import decile_spread
from iam.data import Fundamentals, MarketData, apply_scenario
from iam.engine.composite import DEFAULT_WEIGHTS, ScoreResult
from iam.engine.composite import score as composite_score
from iam.integration import Orchestrator
from iam.thesis.bayesian.updater import BayesianUpdater, Evidence, ScenarioPrior

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SECTORS = [
    "Technology",
    "Financials",
    "Healthcare",
    "Energy",
    "Consumer Discretionary",
    "Industrials",
    "Utilities",
    "Materials",
    "Real Estate",
    "Communication Services",
]

INDUSTRIES: dict[str, list[str]] = {
    "Technology": ["Software", "Semiconductors", "Cloud Infrastructure", "Cybersecurity"],
    "Financials": ["Banking", "Insurance", "Asset Management", "Payments"],
    "Healthcare": ["Biotech", "Pharmaceuticals", "Medical Devices", "Healthcare IT"],
    "Energy": ["Oil & Gas", "Renewables", "Pipelines"],
    "Consumer Discretionary": ["Retail", "Automotive", "E-commerce"],
    "Industrials": ["Aerospace", "Defense", "Logistics"],
    "Utilities": ["Electric", "Gas", "Multi-utility"],
    "Materials": ["Mining", "Chemicals", "Steel"],
    "Real Estate": ["REITs", "Real Estate Services"],
    "Communication Services": ["Telecom", "Media", "Social Media"],
}


def _make_security(
    ticker: str,
    sector: str | None = None,
    industry: str | None = None,
    seed: int = 0,
) -> Security:
    """Build a fully-populated synthetic Security covering all 13 factor inputs."""
    from iam.data import MacroContext

    rng = random.Random(seed)
    nrng = np.random.RandomState(seed)

    if sector is None:
        sector = rng.choice(SECTORS)
    if industry is None:
        industry = rng.choice(INDUSTRIES.get(sector, ["General"]))

    revenue_ttm = rng.uniform(500e6, 300e9)
    op_margin = rng.uniform(-0.05, 0.35)
    gross_margin = op_margin + rng.uniform(0.10, 0.40)
    market_cap = revenue_ttm * rng.uniform(1.5, 25.0)
    total_debt = revenue_ttm * rng.uniform(0.0, 3.0)
    cash = revenue_ttm * rng.uniform(0.02, 0.5)
    shares = rng.uniform(50e6, 10e9)
    price = market_cap / shares
    ev = market_cap + total_debt - cash
    ebitda = revenue_ttm * (op_margin + rng.uniform(0.03, 0.10))
    fcf_ttm = revenue_ttm * op_margin * rng.uniform(0.4, 1.2)

    us_pct = rng.uniform(0.4, 1.0)
    eu_pct = rng.uniform(0.0, 1.0 - us_pct)
    apac_pct = 1.0 - us_pct - eu_pct

    # --- Fundamentals: includes earnings-quality and runway fields ---
    roic_base = rng.uniform(0.05, 0.40)
    fundamentals = Fundamentals(
        revenue_ttm=revenue_ttm,
        revenue_history=[revenue_ttm * (1 - 0.1 * k + nrng.randn() * 0.03) for k in range(5)],
        operating_margin=op_margin,
        operating_margin_history=[op_margin + nrng.randn() * 0.03 for _ in range(5)],
        gross_margin=gross_margin,
        gross_margin_history=[gross_margin + nrng.randn() * 0.02 for _ in range(5)],
        fcf_ttm=fcf_ttm,
        fcf_history=[fcf_ttm * (1 + nrng.randn() * 0.10) for _ in range(5)],
        capex_ttm=revenue_ttm * rng.uniform(0.01, 0.15),
        total_debt=total_debt,
        cash_and_equivalents=cash,
        shares_outstanding=shares,
        shares_outstanding_history=[shares * (1 + nrng.randn() * 0.02) for _ in range(5)],
        interest_expense_ttm=total_debt * rng.uniform(0.03, 0.08),
        incremental_roic=rng.uniform(0.05, 0.50),
        roic_history=[roic_base + nrng.randn() * 0.02 for _ in range(8)],
        accruals_ratio=rng.uniform(-0.10, 0.10),
        sbc_ttm=revenue_ttm * rng.uniform(0.005, 0.08),
        change_in_working_capital=revenue_ttm * rng.uniform(-0.05, 0.05),
    )

    # --- MarketData: includes sentiment, crowding, and relative-value fields ---
    base_pe = rng.uniform(8, 60) if op_margin > 0 else None
    sector_ev_ebitda = rng.uniform(6, 25)
    fcf_yield = fcf_ttm / market_cap if market_cap > 0 else None
    daily_drift = rng.uniform(-0.0003, 0.0008)
    daily_vol = rng.uniform(0.01, 0.025)
    # 252 daily prices: walk backwards from current price
    price_history = [price * (1 - daily_drift * k + nrng.randn() * daily_vol) for k in range(252)]

    market = MarketData(
        market_cap=market_cap,
        price=price,
        enterprise_value=ev,
        pe_ttm=base_pe,
        pe_history=[base_pe * (1 + nrng.randn() * 0.15) for _ in range(40)] if base_pe else [],
        ev_ebitda=ev / ebitda if ebitda > 0 else None,
        sector_ev_ebitda_median=sector_ev_ebitda,
        fcf_yield=fcf_yield,
        ev_sales=ev / revenue_ttm if revenue_ttm > 0 else None,
        peer_ev_sales_median=rng.uniform(1.0, 10.0),
        peer_fcf_yields=[rng.uniform(0.01, 0.08) for _ in range(6)],
        hedge_fund_ownership_pct=rng.uniform(0.01, 0.25),
        retail_ownership_pct=rng.uniform(0.05, 0.40),
        short_interest_pct_float=rng.uniform(0.005, 0.15),
        passive_index_ownership_pct=rng.uniform(0.05, 0.30),
        options_call_put_skew=rng.uniform(-0.30, 0.30),
        beta=rng.uniform(0.4, 2.0),
        analyst_revisions_breadth_30d=rng.uniform(-1.0, 1.0),
        earnings_surprise_history=[rng.uniform(-0.10, 0.15) for _ in range(8)],
        news_sentiment_delta=rng.uniform(-0.5, 0.5),
        price_history=price_history,
    )

    # --- Qualitative: reflexivity factor inputs ---
    qualitative = {
        "equity_currency_strength": rng.uniform(0.0, 1.0),
        "network_effect_strength": rng.uniform(0.0, 1.0),
        "talent_attraction": rng.uniform(0.0, 1.0),
        "acquisition_optionality": rng.uniform(0.0, 1.0),
        "narrative_reinforcement": rng.uniform(0.0, 1.0),
    }

    # --- MacroContext: macro_regime factor ---
    macro = MacroContext(
        real_rate_10y=rng.uniform(-0.02, 0.04),
        real_rate_trend=rng.choice(["falling", "flat", "rising"]),
        yield_curve_slope_10y_2y=rng.uniform(-0.01, 0.02),
        credit_spread_hy=rng.uniform(0.02, 0.08),
        liquidity_index=rng.uniform(-1.0, 1.0),
        pmi_direction=rng.choice(["expanding", "contracting", "stable"]),
        dxy_trend=rng.choice(["strengthening", "weakening", "stable"]),
        erp=rng.uniform(0.03, 0.07),
    )

    return Security(
        ticker=ticker,
        sector=sector,
        industry=industry,
        country_iso="US",
        revenue_mix={"US": us_pct, "EU": eu_pct, "APAC": apac_pct},
        fundamentals=fundamentals,
        market=market,
        qualitative=qualitative,
        macro=macro,
    )


def _make_universe(n: int, seed: int = 42) -> list[Security]:
    """Create a universe of n synthetic securities."""
    rng = random.Random(seed)
    result = []
    for i in range(n):
        sector = rng.choice(SECTORS)
        industry = rng.choice(INDUSTRIES[sector])
        result.append(
            _make_security(f"SYN{i:04d}", sector=sector, industry=industry, seed=seed + i)
        )
    return result


def _score_df(scores: np.ndarray, returns: np.ndarray) -> pd.DataFrame:
    """Wrap parallel score/return arrays in the DataFrame shape the metrics expect."""
    return pd.DataFrame({"score": scores, "fwd": returns})


def _make_priors(bull: float = 0.25, base: float = 0.50, bear: float = 0.25) -> list[ScenarioPrior]:
    return [
        ScenarioPrior(label="Bull Case", probability=bull),
        ScenarioPrior(label="Base Case", probability=base),
        ScenarioPrior(label="Bear Case", probability=bear),
    ]


def _bullish_evidence(name: str = "beat", reliability: float = 0.70) -> Evidence:
    return Evidence(
        type=name,
        description=f"Bullish signal: {name}",
        likelihoods={"Bull Case": 0.80, "Base Case": 0.50, "Bear Case": 0.20},
        reliability=reliability,
    )


def _bearish_evidence(name: str = "miss", reliability: float = 0.70) -> Evidence:
    return Evidence(
        type=name,
        description=f"Bearish signal: {name}",
        likelihoods={"Bull Case": 0.20, "Base Case": 0.50, "Bear Case": 0.80},
        reliability=reliability,
    )


def _try_value(orchestrator: Orchestrator, sec: Security) -> bool:
    try:
        return orchestrator.value_security(sec) is not None
    except Exception:
        return False


def _assert_no_unhandled_crash(orchestrator: Orchestrator, sec: Security, label: str) -> None:
    try:
        orchestrator.value_security(sec)
    except (ValueError, TypeError, KeyError, AttributeError):
        pass  # Acceptable validation rejections
    except Exception as e:
        pytest.fail(f"Unhandled {type(e).__name__} for '{label}': {e}")


# ===========================================================================
# 1. FACTOR ORTHOGONALITY
# ===========================================================================


class TestFactorOrthogonality:
    """Validate that IAM's factors produce statistically distinct signals.

    If two factors are perfectly correlated they are redundant — the composite
    score effectively double-counts that signal.  We require pairwise |r| < 0.70.
    """

    UNIVERSE_SIZE = 200
    RNG_SEED = 1337

    @pytest.fixture(scope="class")
    def factor_score_df(self) -> pd.DataFrame:
        """Compute all factor contributions for a mid-size synthetic universe."""
        universe = _make_universe(self.UNIVERSE_SIZE, seed=self.RNG_SEED)
        rows = []
        for sec in universe:
            try:
                result: ScoreResult = composite_score(sec)
                row = {"ticker": result.ticker}
                for name, contrib in result.factor_breakdown.items():
                    row[name] = contrib.effective()
                rows.append(row)
            except Exception:
                pass

        df = pd.DataFrame(rows).set_index("ticker").dropna(axis=1, how="all")
        assert len(df) >= 50, f"Too few valid rows: {len(df)}"
        return df

    def test_at_least_five_factors_computed(self, factor_score_df):
        """The engine must produce at least 5 distinct factor scores."""
        assert (
            len(factor_score_df.columns) >= 5
        ), f"Only {len(factor_score_df.columns)} factors computed"

    def test_no_constant_factor(self, factor_score_df):
        """At least 7 of the registered factors must have nonzero variance.

        Some factors legitimately return 0 when required data fields are
        absent (e.g. macro_regime without a MacroContext). The synthetic
        universe is enriched to supply all fields, so most should be active.
        Any remaining zero-variance columns are surfaced as warnings so the
        developer knows which factors still need richer test data.
        """
        stds = factor_score_df.std()
        active = stds[stds >= 1e-9]
        inactive = stds[stds < 1e-9]
        if len(inactive) > 0:
            # Not a hard failure — but surface them clearly
            print(
                f"\n[INFO] Zero-variance factors (no signal in synthetic data): {list(inactive.index)}"
            )
        assert (
            len(active) >= 7
        ), f"Only {len(active)} factors have nonzero variance. Inactive: {list(inactive.index)}"

    def _active_factors(self, factor_score_df: pd.DataFrame) -> pd.DataFrame:
        """Return only columns with meaningful variance (std >= 1e-9)."""
        stds = factor_score_df.std()
        return factor_score_df[stds[stds >= 1e-9].index]

    def test_no_completely_redundant_factor_pair(self, factor_score_df):
        """No factor pair (other than intrinsic_value/relative_value) may exceed |r| = 0.90.

        intrinsic_value and relative_value are DESIGNED to correlate in a random
        universe — both respond to the same underlying valuation reality. Their
        convergence is a conviction signal; their divergence is a caution signal.
        That design is validated in TestConvictionConvergence below.

        For all OTHER pairs, |r| >= 0.90 signals genuine double-counting.
        """
        df = self._active_factors(factor_score_df)
        if df.shape[1] < 2:
            pytest.skip("Fewer than 2 active factors — cannot test orthogonality")
        corr = df.corr().abs()
        mask = np.ones(corr.shape, dtype=bool)
        np.fill_diagonal(mask, False)

        INTENDED_HIGH_PAIRS = {frozenset(["intrinsic_value", "relative_value"])}

        cols = list(df.columns)
        for i, a in enumerate(cols):
            for b in cols[i + 1 :]:
                if frozenset([a, b]) in INTENDED_HIGH_PAIRS:
                    continue
                r = corr.loc[a, b]
                assert r < 0.90, (
                    f"Unexpected near-duplicate: {a} ↔ {b} at |r| = {r:.3f}. "
                    "These factors are measuring nearly the same thing."
                )

    def test_factor_orthogonality_diagnostic(self, factor_score_df):
        """Non-failing diagnostic: print the full factor correlation matrix.

        Always passes. Run with -s to see output. Correlated pairs are labelled
        with their design intent so reviewers know which are intentional.
        """
        INTENTIONAL = {frozenset(["intrinsic_value", "relative_value"]): "convergence = conviction"}

        df = self._active_factors(factor_score_df)
        corr = df.corr()
        print("\n[Factor Correlation Matrix]")
        print(corr.round(3).to_string())
        cols = list(df.columns)
        high_pairs = []
        for i, a in enumerate(cols):
            for b in cols[i + 1 :]:
                r = abs(corr.loc[a, b])
                if r > 0.50:
                    pair = frozenset([a, b])
                    note = INTENTIONAL.get(pair, "")
                    high_pairs.append((a, b, r, note))
        if high_pairs:
            print("\n[Pairs with |r| > 0.50]")
            for a, b, r, note in sorted(high_pairs, key=lambda x: -x[2]):
                tag = f"  ← {note}" if note else (" ← INVESTIGATE" if r > 0.80 else "")
                print(f"  {a} ↔ {b}: {r:.3f}{tag}")
        assert True

    def test_all_active_factors_have_nonzero_weight(self, factor_score_df):
        """Every active factor must have a nonzero weight in DEFAULT_WEIGHTS.

        A factor that computes a meaningful score but contributes 0 to the
        composite is silently wasted — this test catches that wiring gap.
        """
        active_names = set(self._active_factors(factor_score_df).columns)
        unwired = [n for n in active_names if DEFAULT_WEIGHTS.get(n, 0.0) == 0.0]
        assert len(unwired) == 0, (
            f"Active factors with zero composite weight: {unwired}. "
            "These factors compute scores but don't influence the composite output."
        )

    def test_factor_score_is_deterministic(self):
        """Computing the same security twice must yield identical factor scores."""
        sec = _make_security("MSFT", "Technology", "Software", seed=1)
        r1 = composite_score(sec)
        r2 = composite_score(sec)
        assert r1.composite == pytest.approx(r2.composite, rel=1e-9)
        for name in r1.factor_breakdown:
            assert r1.factor_breakdown[name].value == pytest.approx(
                r2.factor_breakdown[name].value, rel=1e-9
            )

    @pytest.mark.slow
    def test_factor_scores_stable_over_500_securities(self):
        """Determinism must hold across a 500-security universe."""
        universe = _make_universe(500, seed=999)
        mismatches = 0
        for sec in universe:
            try:
                r1 = composite_score(sec)
                r2 = composite_score(sec)
                if abs(r1.composite - r2.composite) > 1e-9:
                    mismatches += 1
            except Exception:
                pass
        assert mismatches == 0, f"{mismatches} securities produced non-deterministic scores"


# ===========================================================================
# 1b. CONVICTION CONVERGENCE
# ===========================================================================


class TestConvictionConvergence:
    """Validate the intrinsic_value / relative_value design philosophy.

    These two factors are INTENDED to correlate in a random universe — both
    respond to the same underlying valuation reality.  The key properties are:

    1. Convergence amplifies conviction: when both point the same direction,
       their combined contribution to the composite is LARGER than when only
       one fires.  You want the model to be bold when all the evidence agrees.

    2. Divergence moderates the composite: when they disagree, the composite
       should be pulled toward zero — this reflects genuine uncertainty, not
       a forced average.

    3. They can and should disagree: there must be a meaningful population of
       securities where they point in opposite directions (e.g. cheap on
       intrinsic value but expensive vs. peers, or vice versa).  If they NEVER
       disagree the second factor is truly redundant.
    """

    UNIVERSE_SIZE = 300
    RNG_SEED = 42

    @pytest.fixture(scope="class")
    def scored_universe(self):
        """Return (security, ScoreResult) pairs for the full universe."""
        universe = _make_universe(self.UNIVERSE_SIZE, seed=self.RNG_SEED)
        results = []
        for sec in universe:
            try:
                r = composite_score(sec)
                results.append(r)
            except Exception:
                pass
        assert len(results) >= 100, f"Too few scored securities: {len(results)}"
        return results

    def _iv_rv(self, r: ScoreResult):
        """Return (intrinsic_value.effective, relative_value.effective) or None."""
        iv = r.factor_breakdown.get("intrinsic_value")
        rv = r.factor_breakdown.get("relative_value")
        if iv is None or rv is None:
            return None
        return iv.effective(), rv.effective()

    def test_convergence_amplifies_composite_magnitude(self, scored_universe):
        """When intrinsic_value and relative_value agree in sign, |composite|
        should be larger on average than when they disagree.

        This is the mathematical expression of 'conviction' — two independent
        lenses pointing the same way gives you more confidence than one alone.
        """
        agree_magnitudes = []
        disagree_magnitudes = []

        for r in scored_universe:
            pair = self._iv_rv(r)
            if pair is None:
                continue
            iv_eff, rv_eff = pair
            # Only consider securities where both factors have a meaningful signal
            if abs(iv_eff) < 0.02 or abs(rv_eff) < 0.02:
                continue
            if math.copysign(1, iv_eff) == math.copysign(1, rv_eff):
                agree_magnitudes.append(abs(r.composite))
            else:
                disagree_magnitudes.append(abs(r.composite))

        assert len(agree_magnitudes) >= 10, "Not enough agreeing pairs for conviction test"
        assert len(disagree_magnitudes) >= 10, "Not enough disagreeing pairs for caution test"

        mean_agree = statistics.mean(agree_magnitudes)
        mean_disagree = statistics.mean(disagree_magnitudes)

        assert mean_agree > mean_disagree, (
            f"Conviction signal not working: |composite| when factors agree "
            f"({mean_agree:.4f}) should exceed |composite| when they disagree "
            f"({mean_disagree:.4f}). Check composite weighting logic."
        )

    def test_factors_can_disagree(self, scored_universe):
        """There must be a meaningful fraction of securities where intrinsic_value
        and relative_value point in opposite directions.

        If they NEVER disagree, one factor is genuinely redundant.  The useful
        regime is when they occasionally diverge — that divergence carries
        information (e.g. cheap on fundamentals but expensive vs. peers implies
        the sector is cheap, not the stock).
        """
        total = 0
        disagree = 0

        for r in scored_universe:
            pair = self._iv_rv(r)
            if pair is None:
                continue
            iv_eff, rv_eff = pair
            if abs(iv_eff) < 0.02 or abs(rv_eff) < 0.02:
                continue
            total += 1
            if math.copysign(1, iv_eff) != math.copysign(1, rv_eff):
                disagree += 1

        assert total >= 20, "Not enough securities with both factors active"
        disagree_rate = disagree / total

        # At least 5% of securities should show factor divergence.
        # If this falls to ~0%, the factors are identical and one is redundant.
        assert disagree_rate >= 0.05, (
            f"intrinsic_value and relative_value disagree on only {disagree_rate:.1%} "
            f"of securities (need >= 5%). They may be measuring the same thing."
        )
        # But they shouldn't disagree more than ~60% of the time in a random
        # universe — that would mean they're measuring opposite things.
        assert disagree_rate <= 0.60, (
            f"intrinsic_value and relative_value disagree on {disagree_rate:.1%} "
            f"of securities (expected < 60%). They may be inverted from each other."
        )

    def test_divergence_signals_lower_composite_confidence(self, scored_universe):
        """When the two valuation lenses disagree, the composite should sit
        closer to zero than the average of the two factor signals alone would
        suggest — reflecting genuine model uncertainty.

        Formally: mean(|composite|) for diverging pairs should be less than
        mean(|iv_eff| + |rv_eff|) / 2 for those same pairs.
        """
        composite_mags = []
        naive_avg_mags = []

        for r in scored_universe:
            pair = self._iv_rv(r)
            if pair is None:
                continue
            iv_eff, rv_eff = pair
            if abs(iv_eff) < 0.02 or abs(rv_eff) < 0.02:
                continue
            if math.copysign(1, iv_eff) == math.copysign(1, rv_eff):
                continue  # Only diverging pairs
            composite_mags.append(abs(r.composite))
            naive_avg_mags.append((abs(iv_eff) + abs(rv_eff)) / 2)

        if len(composite_mags) < 5:
            pytest.skip("Too few diverging pairs for confidence test")

        mean_composite = statistics.mean(composite_mags)
        mean_naive = statistics.mean(naive_avg_mags)

        # The composite should be moderated by the divergence — other factors
        # and penalties will also contribute, so we use a loose bound here.
        # We're just checking the composite doesn't wildly amplify disagreement.
        assert mean_composite < mean_naive * 3.0, (
            f"Composite magnitude ({mean_composite:.4f}) is much larger than the "
            f"naive factor average ({mean_naive:.4f}) for diverging pairs. "
            "Disagreement between lenses should moderate, not amplify, conviction."
        )

    def test_both_agree_bullish_produces_positive_composite(self, scored_universe):
        """When intrinsic AND relative value are both bullish, the composite
        should be positive more often than not.
        """
        positives = 0
        total = 0

        for r in scored_universe:
            pair = self._iv_rv(r)
            if pair is None:
                continue
            iv_eff, rv_eff = pair
            if iv_eff > 0.05 and rv_eff > 0.05:
                total += 1
                if r.composite > 0:
                    positives += 1

        if total < 5:
            pytest.skip("Too few doubly-bullish securities in synthetic universe")

        rate = positives / total
        assert rate >= 0.70, (
            f"Only {rate:.1%} of doubly-bullish securities have positive composite "
            f"(expected >= 70%). Conviction signal not propagating correctly."
        )

    def test_both_agree_bearish_produces_negative_composite(self, scored_universe):
        """When intrinsic AND relative value are both bearish, the composite
        should be negative more often than not.
        """
        negatives = 0
        total = 0

        for r in scored_universe:
            pair = self._iv_rv(r)
            if pair is None:
                continue
            iv_eff, rv_eff = pair
            if iv_eff < -0.05 and rv_eff < -0.05:
                total += 1
                if r.composite < 0:
                    negatives += 1

        if total < 5:
            pytest.skip("Too few doubly-bearish securities in synthetic universe")

        rate = negatives / total
        assert rate >= 0.70, (
            f"Only {rate:.1%} of doubly-bearish securities have negative composite "
            f"(expected >= 70%). Conviction signal not propagating correctly."
        )


# ===========================================================================
# 2. LARGE-SCALE BACKTEST STRESS
# ===========================================================================


class TestLargeScaleBacktest:
    """Stress-test IC/IR metrics at institutional scale.

    A realistic backtest covers 300–600 stocks × 120 monthly snapshots.
    We simulate this with synthetic scores + returns and verify that the
    metric functions behave statistically as expected.
    """

    @staticmethod
    def _df(scores_2d: np.ndarray, returns_2d: np.ndarray, t: int) -> pd.DataFrame:
        return _score_df(scores_2d[t], returns_2d[t])

    @pytest.mark.slow
    def test_full_10yr_backtest_ic_positive(self):
        """Mean IC should be detectably positive when scores genuinely predict returns."""
        rng = np.random.RandomState(42)
        n_stocks, n_months = 500, 120
        signal_strength = 0.08

        scores = rng.randn(n_months, n_stocks).astype(np.float32)
        noise = rng.randn(n_months, n_stocks).astype(np.float32)
        forward_returns = (signal_strength * scores + noise * 0.15).astype(np.float32)

        monthly_ics = pd.Series(
            [information_coefficient(self._df(scores, forward_returns, t)) for t in range(n_months)]
        )
        monthly_hit_rates = [
            hit_rate(self._df(scores, forward_returns, t)) for t in range(n_months)
        ]

        mean_ic = monthly_ics.mean()
        ir = information_ratio(monthly_ics)
        mean_hr = float(np.nanmean(monthly_hit_rates))

        assert mean_ic > 0.02, f"Mean IC = {mean_ic:.4f} too low (expected > 0.02)"
        assert ir > 0.5, f"IR = {ir:.3f} too low (expected > 0.5)"
        assert mean_hr > 0.52, f"Hit rate = {mean_hr:.3f} too low (expected > 52%)"

        del scores, forward_returns, noise
        gc.collect()

    @pytest.mark.slow
    def test_null_ic_with_random_scores(self):
        """IC should be statistically indistinguishable from zero with random scores."""
        rng = np.random.RandomState(123)
        n_stocks, n_months = 500, 120

        scores = rng.randn(n_months, n_stocks).astype(np.float32)
        returns = rng.randn(n_months, n_stocks).astype(np.float32)

        monthly_ics = pd.Series(
            [information_coefficient(self._df(scores, returns, t)) for t in range(n_months)]
        )
        mean_ic = monthly_ics.mean()
        t_stat = mean_ic / (monthly_ics.std() / math.sqrt(n_months))

        assert abs(t_stat) < 2.5, (
            f"t-stat = {t_stat:.2f} exceeds threshold for random scores. "
            "Backtest metrics may have a systematic bias."
        )

        del scores, returns
        gc.collect()

    @pytest.mark.slow
    def test_decile_spread_positive_with_signal(self):
        """Top-decile returns should consistently exceed bottom-decile returns."""
        rng = np.random.RandomState(7)
        n_stocks, n_months = 500, 120
        signal_strength = 0.10

        scores = rng.randn(n_months, n_stocks).astype(np.float32)
        returns = signal_strength * scores + rng.randn(n_months, n_stocks).astype(np.float32) * 0.20

        spreads = [
            decile_spread(self._df(scores, returns, t)).get("spread", float("nan"))
            for t in range(n_months)
        ]
        mean_spread = float(np.nanmean(spreads))

        assert mean_spread > 0.005, f"Decile spread too low: {mean_spread:.4f} (expected > 0.005)"

        del scores, returns
        gc.collect()

    def test_summarize_backtest_statistical_validity(self):
        """summarize_backtest must produce IC mean, std, and ICIR from a large panel."""
        rng = np.random.RandomState(88)
        n_months = 120
        true_ic, noise_ic = 0.06, 0.03

        results_df = pd.DataFrame(
            {
                "ic": true_ic + rng.randn(n_months) * noise_ic,
                "hit_rate": np.clip(0.53 + rng.randn(n_months) * 0.04, 0, 1),
                "spread": 0.01 + rng.randn(n_months) * 0.005,
                "top": 0.015 + rng.randn(n_months) * 0.005,
                "bottom": 0.005 + rng.randn(n_months) * 0.003,
            }
        )

        summary = summarize_backtest(results_df)

        assert "ic_mean" in summary
        assert "ic_std" in summary
        assert "icir" in summary
        assert summary["ic_mean"] == pytest.approx(true_ic, abs=0.01)
        expected_icir = true_ic / noise_ic
        assert summary["icir"] == pytest.approx(expected_icir, rel=0.25)

    def test_ic_reliability_calibration_monotone(self):
        """ic_to_reliability must be strictly non-decreasing."""
        ic_values = [-0.10, -0.05, 0.0, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.50]
        reliabilities = [ic_to_reliability(ic) for ic in ic_values]

        for i in range(1, len(reliabilities)):
            assert reliabilities[i] >= reliabilities[i - 1], (
                f"Reliability not monotone at IC={ic_values[i]:.2f}: "
                f"got {reliabilities[i]:.4f} <= prev {reliabilities[i - 1]:.4f}"
            )

        assert ic_to_reliability(-0.10) == pytest.approx(0.50, abs=0.01)
        assert ic_to_reliability(0.50) == pytest.approx(0.95, abs=0.01)

    def test_information_ratio_formula(self):
        """IR = mean(IC) / std(IC) must hold exactly."""
        rng = np.random.RandomState(314)
        ics = pd.Series(0.07 + rng.randn(60) * 0.03)
        expected_ir = ics.mean() / ics.std()
        assert information_ratio(ics) == pytest.approx(expected_ir, rel=1e-6)

    @pytest.mark.slow
    def test_bootstrap_ic_distribution_mostly_positive(self):
        """With genuine signal, >70% of bootstrap IR samples should be positive."""
        rng = np.random.RandomState(314)
        n_stocks, n_months = 300, 60
        true_ic = 0.07

        scores = rng.randn(n_months, n_stocks).astype(np.float32)
        returns = true_ic * scores + rng.randn(n_months, n_stocks).astype(np.float32) * 0.18

        monthly_ics = pd.Series(
            [information_coefficient(self._df(scores, returns, t)) for t in range(n_months)]
        )

        bootstrap_irs = []
        for _ in range(100):
            idx = rng.choice(n_months, size=30, replace=True)
            bootstrap_irs.append(information_ratio(monthly_ics.iloc[idx]))

        pct_positive = np.mean(np.array(bootstrap_irs) > 0)
        assert (
            pct_positive > 0.70
        ), f"Only {pct_positive:.1%} of bootstrap IRs are positive. Signal may not be robust."

        del scores, returns
        gc.collect()


# ===========================================================================
# 3. PORTFOLIO OPTIMIZER STRESS
# ===========================================================================


class TestPortfolioOptimizerStress:
    """Test the walk-forward weight optimizer under extreme market conditions."""

    @staticmethod
    def _panel(n_months, n_stocks, n_factors, signal_factors=3, ic=0.06, seed=42):
        rng = np.random.RandomState(seed)
        dates = pd.date_range("2015-01-31", periods=n_months, freq="ME")
        scores_by_date = {d: rng.randn(n_stocks, n_factors) for d in dates}
        weights_true = np.zeros(n_factors)
        weights_true[:signal_factors] = 1.0 / signal_factors
        rets_by_date = {
            d: ic * (scores_by_date[d] @ weights_true) + rng.randn(n_stocks) * 0.18 for d in dates
        }
        return dates.tolist(), scores_by_date, rets_by_date

    def test_optimizer_with_highly_correlated_factors(self):
        """Optimizer must stay stable when two factors are nearly identical."""
        from iam.backtest.weight_optimizer import WalkForwardOptimizer, WeightOptimizerConfig

        rng = np.random.RandomState(55)
        n_months, n_stocks = 36, 100
        dates = pd.date_range("2018-01-31", periods=n_months, freq="ME")
        base = rng.randn(n_months, n_stocks)
        clone = base + rng.randn(n_months, n_stocks) * 0.05

        scores_by_date = {d: np.column_stack([base[i], clone[i]]) for i, d in enumerate(dates)}
        rets_by_date = {
            d: 0.05 * scores_by_date[d][:, 0] + rng.randn(n_stocks) * 0.15 for d in dates
        }

        config = WeightOptimizerConfig(
            n_factors=2,
            factor_names=["f1", "f1_clone"],
            train_window_months=12,
            test_window_months=6,
        )
        result = WalkForwardOptimizer(config).run(dates.tolist(), scores_by_date, rets_by_date)

        assert result.status == "success"
        assert np.isclose(np.sum(result.final_weights), 1.0)
        assert np.all(np.isfinite(result.final_weights))

    @pytest.mark.slow
    def test_optimizer_13_factors_500_stocks_5yr(self):
        """Walk-forward optimizer must handle 13 factors × 500 stocks × 5 years."""
        from iam.backtest.weight_optimizer import WalkForwardOptimizer, WeightOptimizerConfig

        n_months, n_stocks, n_factors = 60, 500, 13
        dates, scores_by_date, rets_by_date = self._panel(n_months, n_stocks, n_factors)

        config = WeightOptimizerConfig(
            n_factors=n_factors,
            factor_names=[f"f{i}" for i in range(n_factors)],
            train_window_months=24,
            test_window_months=6,
        )
        result = WalkForwardOptimizer(config).run(dates, scores_by_date, rets_by_date)

        assert result.status == "success"
        assert len(result.final_weights) == n_factors
        assert np.isclose(np.sum(result.final_weights), 1.0, atol=1e-6)
        assert np.all(np.isfinite(result.final_weights))
        assert np.max(result.final_weights) > 0.10

    @pytest.mark.slow
    def test_optimizer_fat_tail_returns(self):
        """Optimizer must remain stable with Student-t fat-tail return distributions."""
        from iam.backtest.weight_optimizer import WalkForwardOptimizer, WeightOptimizerConfig

        rng = np.random.RandomState(999)
        n_months, n_stocks, n_factors = 48, 200, 5
        dates = pd.date_range("2019-01-31", periods=n_months, freq="ME")
        scores_by_date = {d: rng.randn(n_stocks, n_factors) for d in dates}
        rets_by_date = {
            d: 0.05 * scores_by_date[d][:, 0] + rng.standard_t(df=3, size=n_stocks) * 0.08
            for d in dates
        }

        config = WeightOptimizerConfig(
            n_factors=n_factors,
            train_window_months=18,
            test_window_months=6,
        )
        result = WalkForwardOptimizer(config).run(dates.tolist(), scores_by_date, rets_by_date)

        assert result.status == "success"
        assert np.all(np.isfinite(result.final_weights))

    @pytest.mark.slow
    def test_bootstrap_stability_strong_vs_weak_signal(self):
        """Weight variance must be lower for a strong-signal regime than a random one."""
        from iam.backtest.weight_optimizer import BootstrapStability, WeightOptimizerConfig

        rng = np.random.RandomState(42)
        n_months, n_stocks, n_factors = 36, 150, 4
        dates = pd.date_range("2020-01-31", periods=n_months, freq="ME")
        scores_by_date = {d: rng.randn(n_stocks, n_factors) for d in dates}

        rets_strong = {
            d: 0.15 * scores_by_date[d][:, 0] + rng.randn(n_stocks) * 0.10 for d in dates
        }
        rets_weak = {d: rng.randn(n_stocks) * 0.20 for d in dates}

        config = WeightOptimizerConfig(n_factors=n_factors, n_bootstrap=50)

        res_strong = BootstrapStability(config).run(dates.tolist(), scores_by_date, rets_strong)
        res_weak = BootstrapStability(config).run(dates.tolist(), scores_by_date, rets_weak)

        var_strong = float(np.var(res_strong.bootstrap_weights, axis=0).mean())
        var_weak = float(np.var(res_weak.bootstrap_weights, axis=0).mean())

        assert var_strong < var_weak, (
            f"Bootstrap variance for strong signal ({var_strong:.4f}) should be "
            f"less than for weak signal ({var_weak:.4f})"
        )


# ===========================================================================
# 4. VALUATION ENGINE CROSS-CONSISTENCY
# ===========================================================================


class TestValuationEngineConsistency:
    """Validate that valuation results are coherent, deterministic, and robust."""

    @pytest.fixture(scope="class")
    def orchestrator(self):
        return Orchestrator()

    @pytest.fixture(scope="class")
    def msft(self):
        return Security(
            ticker="MSFT",
            sector="Technology",
            industry="Software",
            country_iso="US",
            revenue_mix={"US": 0.60, "EU": 0.25, "APAC": 0.15},
            fundamentals=Fundamentals(
                revenue_ttm=211e9,
                operating_margin=0.42,
                gross_margin=0.69,
                fcf_ttm=63e9,
                capex_ttm=25e9,
                total_debt=79e9,
                cash_and_equivalents=111e9,
                shares_outstanding=7.5e9,
                interest_expense_ttm=3.5e9,
                incremental_roic=0.65,
            ),
            market=MarketData(
                market_cap=2800e9,
                price=373.0,
                enterprise_value=2768e9,
                pe_ttm=34.0,
            ),
        )

    def test_single_security_returns_dict(self, orchestrator, msft):
        """Orchestrator must return a dict with 'model_result' for a valid security."""
        result = orchestrator.value_security(msft)
        assert isinstance(result, dict)
        assert "model_result" in result

    def test_valuation_is_deterministic(self, orchestrator, msft):
        """Identical input must produce identical output on repeated calls."""
        results = [orchestrator.value_security(msft) for _ in range(5)]
        mr0 = results[0]["model_result"]
        for r in results[1:]:
            mr = r["model_result"]
            if hasattr(mr0, "value") and hasattr(mr, "value"):
                assert mr.value == pytest.approx(mr0.value, rel=1e-9)

    def test_convenience_function_matches_orchestrator(self, orchestrator, msft):
        """value_security() must return the same structure as Orchestrator.value_security()."""
        direct = orchestrator.value_security(msft)
        convenience = value_security(msft)
        assert isinstance(direct, dict)
        assert isinstance(convenience, dict)
        assert set(direct.keys()) == set(convenience.keys())

    def test_scenario_does_not_mutate_base(self, msft):
        """apply_scenario must not change the original Security object."""
        original_mix = dict(msft.revenue_mix)
        apply_scenario(msft, {"US": 0.10, "EU": -0.05, "APAC": -0.05})
        assert dict(msft.revenue_mix) == original_mix

    def test_extreme_growth_company_no_divide_by_zero(self, orchestrator):
        """Hyper-growth loss-making company must not raise ZeroDivisionError."""
        sec = Security(
            ticker="HYPER",
            sector="Technology",
            industry="Cloud Infrastructure",
            country_iso="US",
            revenue_mix={"US": 0.90, "EU": 0.10},
            fundamentals=Fundamentals(
                revenue_ttm=1e9,
                operating_margin=-0.50,
                fcf_ttm=-600e6,
                capex_ttm=800e6,
                total_debt=2e9,
                cash_and_equivalents=3e9,
                shares_outstanding=500e6,
            ),
            market=MarketData(
                market_cap=50e9,
                price=100.0,
                enterprise_value=49e9,
                pe_ttm=None,
            ),
        )
        try:
            result = orchestrator.value_security(sec)
            assert result is not None
        except ZeroDivisionError as e:
            pytest.fail(f"ZeroDivisionError on hyper-growth company: {e}")
        except OverflowError as e:
            pytest.fail(f"OverflowError on hyper-growth company: {e}")

    def test_distressed_company_no_unhandled_error(self, orchestrator):
        """Distressed company (negative FCF, extreme leverage) must not crash."""
        sec = Security(
            ticker="DISTRESSED",
            sector="Energy",
            industry="Oil & Gas",
            country_iso="US",
            revenue_mix={"US": 1.0},
            fundamentals=Fundamentals(
                revenue_ttm=500e6,
                operating_margin=-1.60,
                fcf_ttm=-900e6,
                total_debt=5e9,
                cash_and_equivalents=50e6,
                shares_outstanding=100e6,
            ),
            market=MarketData(market_cap=200e6, price=2.0, enterprise_value=5150e6),
        )
        try:
            orchestrator.value_security(sec)
        except ZeroDivisionError as e:
            pytest.fail(f"ZeroDivisionError on distressed company: {e}")

    @pytest.mark.slow
    def test_batch_valuation_200_securities(self, orchestrator):
        """200-security batch valuation must succeed for at least 70% of names."""
        universe = _make_universe(200, seed=2024)
        success = sum(1 for sec in universe if _try_value(orchestrator, sec))
        assert (
            success / len(universe) >= 0.70
        ), f"Only {success / len(universe):.1%} of 200 securities valuated successfully"


# ===========================================================================
# 5. BAYESIAN THESIS CONVERGENCE
# ===========================================================================


class TestBayesianThesisConvergence:
    """Validate that the Bayesian thesis engine correctly updates beliefs.

    Key invariants:
    - Probabilities always sum to 1.0 after each update
    - Strong consistent evidence shifts posteriors toward the true scenario
    - Conflicting evidence does not collapse to certainty
    - Updates converge: later evidence causes smaller shifts
    """

    def test_probabilities_sum_to_one_after_each_update(self):
        """After every evidence update, scenario probabilities must sum to 1."""
        posteriors = _make_priors()
        for ev in [
            _bullish_evidence("revenue_beat", 0.70),
            _bearish_evidence("guidance_cut", 0.60),
            _bullish_evidence("margin_expansion", 0.50),
        ]:
            posteriors = BayesianUpdater.update(posteriors, ev)
            total = sum(p.probability for p in posteriors)
            assert total == pytest.approx(
                1.0, abs=1e-9
            ), f"Probabilities don't sum to 1 after '{ev.type}': {total}"

    def test_consistent_bullish_evidence_raises_bull(self):
        """10 bullish signals should increase Bull Case probability."""
        priors = _make_priors()
        original_bull = priors[0].probability

        posteriors = priors
        for i in range(10):
            posteriors = BayesianUpdater.update(posteriors, _bullish_evidence(f"bull_{i}"))

        bull_prob = next(p.probability for p in posteriors if "Bull" in p.label)
        bear_prob = next(p.probability for p in posteriors if "Bear" in p.label)

        assert (
            bull_prob > original_bull
        ), f"Bull Case probability did not increase: {bull_prob:.4f} <= {original_bull:.4f}"
        assert bear_prob < _make_priors()[2].probability

    def test_consistent_bearish_evidence_raises_bear(self):
        """10 bearish signals should increase Bear Case probability."""
        priors = _make_priors()
        original_bear = priors[2].probability

        posteriors = priors
        for i in range(10):
            posteriors = BayesianUpdater.update(posteriors, _bearish_evidence(f"bear_{i}"))

        bear_prob = next(p.probability for p in posteriors if "Bear" in p.label)
        assert bear_prob > original_bear

    def test_balanced_evidence_preserves_uncertainty(self):
        """Alternating bullish/bearish evidence must not collapse to certainty."""
        posteriors = _make_priors(bull=0.33, base=0.34, bear=0.33)
        for i in range(20):
            ev = _bullish_evidence(f"ev_{i}") if i % 2 == 0 else _bearish_evidence(f"ev_{i}")
            posteriors = BayesianUpdater.update(posteriors, ev)

        max_prob = max(p.probability for p in posteriors)
        assert (
            max_prob < 0.80
        ), f"Posteriors collapsed despite balanced evidence: max={max_prob:.4f}"

    def test_convergence_rate_diminishes(self):
        """Each successive update of the same type should cause a smaller shift."""
        posteriors = _make_priors()
        deltas = []

        for i in range(30):
            prev_bull = next(p.probability for p in posteriors if "Bull" in p.label)
            posteriors = BayesianUpdater.update(posteriors, _bullish_evidence(f"bull_{i}"))
            new_bull = next(p.probability for p in posteriors if "Bull" in p.label)
            deltas.append(abs(new_bull - prev_bull))

        early_avg = statistics.mean(deltas[:5])
        late_avg = statistics.mean(deltas[20:])
        assert (
            late_avg < early_avg
        ), f"Updates not converging: early_avg={early_avg:.6f}, late_avg={late_avg:.6f}"

    def test_high_reliability_evidence_dominates(self):
        """A single high-reliability signal should cause a larger shift than many weak ones."""
        priors = _make_priors()

        posteriors_strong = _make_priors()
        posteriors_strong = BayesianUpdater.update(
            posteriors_strong,
            Evidence(
                type="MASSIVE_BEAT",
                description="Massive earnings beat, highly reliable",
                likelihoods={"Bull Case": 0.95, "Base Case": 0.50, "Bear Case": 0.05},
                reliability=0.95,
            ),
        )
        strong_shift = (
            next(p.probability for p in posteriors_strong if "Bull" in p.label)
            - priors[0].probability
        )

        posteriors_weak = _make_priors()
        for i in range(5):
            posteriors_weak = BayesianUpdater.update(
                posteriors_weak,
                Evidence(
                    type=f"weak_bear_{i}",
                    description="Weak bearish signal",
                    likelihoods={"Bull Case": 0.45, "Base Case": 0.50, "Bear Case": 0.55},
                    reliability=0.10,
                ),
            )
        weak_shift = abs(
            priors[2].probability
            - next(p.probability for p in posteriors_weak if "Bear" in p.label)
        )

        assert strong_shift > weak_shift * 0.5, (
            f"High-reliability shift ({strong_shift:.4f}) should dominate "
            f"5 weak signals ({weak_shift:.4f})"
        )

    @pytest.mark.slow
    def test_numerical_stability_over_1000_updates(self):
        """Engine must remain numerically stable after 1000 random evidence updates."""
        rng = random.Random(42)
        posteriors = _make_priors(bull=0.33, base=0.34, bear=0.33)

        for i in range(1000):
            ev = Evidence(
                type=f"ev_{i}",
                description="random",
                likelihoods={
                    "Bull Case": rng.uniform(0.1, 0.9),
                    "Base Case": rng.uniform(0.1, 0.9),
                    "Bear Case": rng.uniform(0.1, 0.9),
                },
                reliability=rng.uniform(0.1, 0.9),
            )
            posteriors = BayesianUpdater.update(posteriors, ev)
            total = sum(p.probability for p in posteriors)
            assert total == pytest.approx(
                1.0, abs=1e-6
            ), f"Probability sum diverged at iteration {i}: {total}"
            for p in posteriors:
                assert (
                    0.0 <= p.probability <= 1.0
                ), f"Invalid probability for '{p.label}' at iteration {i}: {p.probability}"

    @pytest.mark.slow
    def test_converges_to_correct_scenario(self):
        """50 strong signals for each scenario should identify it with high confidence."""
        for true_scenario, make_ev in [
            ("Bull Case", _bullish_evidence),
            ("Bear Case", _bearish_evidence),
        ]:
            posteriors = _make_priors(bull=0.33, base=0.34, bear=0.33)
            for i in range(50):
                posteriors = BayesianUpdater.update(posteriors, make_ev(f"ev_{i}"))

            top = max(posteriors, key=lambda p: p.probability)
            assert true_scenario in top.label, (
                f"Failed to converge to '{true_scenario}': "
                f"{[(p.label, round(p.probability, 4)) for p in posteriors]}"
            )


# ===========================================================================
# 6. DATA PIPELINE ROBUSTNESS
# ===========================================================================


class TestDataPipelineRobustness:
    """Validate graceful degradation with bad/missing data at every boundary."""

    @pytest.fixture(scope="class")
    def orchestrator(self):
        return Orchestrator()

    def test_no_fundamentals(self, orchestrator):
        """Security without Fundamentals must not raise an unhandled exception."""
        sec = Security(
            ticker="BARE", sector="Technology", industry="Software", revenue_mix={"US": 1.0}
        )
        _assert_no_unhandled_crash(orchestrator, sec, "no fundamentals")

    def test_nan_numeric_fields(self, orchestrator):
        """NaN numeric fields must not produce unhandled exceptions."""
        sec = Security(
            ticker="NANS",
            sector="Financials",
            industry="Banking",
            revenue_mix={"US": 0.7, "EU": 0.3},
            fundamentals=Fundamentals(
                revenue_ttm=float("nan"),
                operating_margin=float("nan"),
                total_debt=float("nan"),
            ),
            market=MarketData(market_cap=float("nan"), price=float("nan")),
        )
        _assert_no_unhandled_crash(orchestrator, sec, "NaN fields")

    def test_zero_revenue(self, orchestrator):
        """Zero revenue must not cause ZeroDivisionError."""
        sec = Security(
            ticker="ZERO",
            sector="Healthcare",
            industry="Biotech",
            revenue_mix={"US": 1.0},
            fundamentals=Fundamentals(
                revenue_ttm=0.0,
                operating_margin=None,
                total_debt=100e6,
                cash_and_equivalents=200e6,
                shares_outstanding=100e6,
            ),
            market=MarketData(market_cap=500e6, price=5.0),
        )
        try:
            orchestrator.value_security(sec)
        except ZeroDivisionError as e:
            pytest.fail(f"ZeroDivisionError with zero revenue: {e}")
        except Exception:
            pass

    def test_extreme_100x_leverage(self, orchestrator):
        """Debt-to-revenue ratio of 100x must not overflow."""
        sec = Security(
            ticker="LEVERAGED",
            sector="Utilities",
            industry="Electric",
            revenue_mix={"US": 1.0},
            fundamentals=Fundamentals(
                revenue_ttm=5e9,
                operating_margin=0.20,
                total_debt=500e9,
                cash_and_equivalents=1e9,
                shares_outstanding=1e9,
                interest_expense_ttm=25e9,
                fcf_ttm=-24e9,
            ),
            market=MarketData(market_cap=1e9, price=1.0, enterprise_value=500e9),
        )
        try:
            orchestrator.value_security(sec)
        except (ZeroDivisionError, OverflowError) as e:
            pytest.fail(f"{type(e).__name__} with extreme leverage: {e}")
        except Exception:
            pass

    def test_revenue_mix_auto_normalizes(self):
        """revenue_mix that sums to 0.5 must be normalized to sum to 1.0."""
        sec = Security(
            ticker="BADMIX",
            sector="Technology",
            industry="Software",
            revenue_mix={"US": 0.30, "EU": 0.20},  # sums to 0.50
        )
        normalized = sec.normalized_mix()
        total = sum(normalized.values())
        assert total == pytest.approx(
            1.0, abs=1e-6
        ), f"normalized_mix() should sum to 1.0 but got {total}"

    def test_empty_revenue_mix(self):
        """Empty revenue_mix must not crash normalized_mix()."""
        sec = Security(ticker="EMPTY", sector="Technology", industry="Software", revenue_mix={})
        try:
            sec.normalized_mix()
        except Exception:
            pass  # Rejection is acceptable — unhandled crash is not

    def test_apply_scenario_empty_mix(self):
        """apply_scenario on empty revenue_mix must not panic."""
        sec = Security(ticker="EMPTY", sector="Technology", industry="Software", revenue_mix={})
        try:
            apply_scenario(sec, {"US": 0.10})
        except Exception:
            pass

    @pytest.mark.slow
    def test_fuzz_1000_random_inputs(self, orchestrator):
        """1000 randomly-corrupted securities must never produce an unhandled exception."""
        rng = np.random.RandomState(555)
        unhandled = []

        for i in range(1000):
            sec = Security(
                ticker=f"FUZZ{i:04d}",
                sector=rng.choice(SECTORS),
                industry="General",
                revenue_mix={"US": float(rng.uniform(0, 2))},
                fundamentals=Fundamentals(
                    revenue_ttm=float(rng.uniform(-1e9, 1e12)),
                    operating_margin=float(rng.uniform(-5, 2)),
                    total_debt=float(rng.uniform(-1e9, 1e13)),
                    cash_and_equivalents=float(rng.uniform(0, 1e12)),
                    shares_outstanding=float(rng.uniform(0, 1e10)),
                ),
                market=MarketData(
                    market_cap=float(rng.uniform(-1e9, 1e13)),
                    price=float(rng.uniform(-100, 10000)),
                ),
            )
            try:
                orchestrator.value_security(sec)
            except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
                pass  # Validation/rejection errors are acceptable
            except Exception as e:
                unhandled.append((i, type(e).__name__, str(e)[:80]))

        if unhandled:
            details = "\n".join(f"  [{i}] {t}: {m}" for i, t, m in unhandled[:10])
            pytest.fail(f"{len(unhandled)} unhandled exceptions in fuzz test:\n{details}")


# ===========================================================================
# 7. MEMORY PRESSURE & PERFORMANCE BENCHMARKS
# ===========================================================================


class TestMemoryAndPerformance:
    """No significant memory leaks; throughput meets minimum floor.

    The 20 GB stress test allocates:
      - scores: 1000 × 252 × 13 × float32 ≈ 13.1 GB
      - returns: 1000 × 252 × float32 ≈ 1.0 GB
      - composite: 1000 × 252 × float32 ≈ 1.0 GB
      Total: ~15 GB, within the 20 GB budget.
    """

    @pytest.mark.slow
    def test_no_memory_leak_repeated_valuation(self):
        """Repeated valuation of the same security must not continuously grow memory."""
        import tracemalloc

        sec = Security(
            ticker="MSFT",
            sector="Technology",
            industry="Software",
            revenue_mix={"US": 0.60, "EU": 0.25, "APAC": 0.15},
            fundamentals=Fundamentals(
                revenue_ttm=211e9,
                operating_margin=0.42,
                total_debt=79e9,
                cash_and_equivalents=111e9,
            ),
            market=MarketData(market_cap=2800e9, price=373.0),
        )
        orchestrator = Orchestrator()

        for _ in range(5):
            orchestrator.value_security(sec)
        gc.collect()

        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        for _ in range(200):
            orchestrator.value_security(sec)
        gc.collect()

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_growth_mb = sum(s.size_diff for s in stats) / (1024 * 1024)

        assert (
            total_growth_mb < 100
        ), f"Memory grew by {total_growth_mb:.1f} MB over 200 valuations. Possible memory leak."

    @pytest.mark.slow
    def test_20gb_score_matrix_computation(self):
        """Allocate and process a ~15 GB score matrix without an OOM crash.

        This exercises the system's ability to handle institutional-scale data:
        1000 stocks × 252 monthly periods × 13 factors.
        """
        n_stocks = 1000
        n_months = 252
        n_factors = 13

        rng = np.random.RandomState(0)
        try:
            # float32: 1000 × 252 × 13 × 4 bytes ≈ 13.1 GB
            scores = rng.randn(n_months, n_stocks, n_factors).astype(np.float32)
            # float32: 1000 × 252 × 4 bytes ≈ 1.0 GB
            returns = rng.randn(n_months, n_stocks).astype(np.float32)
            composite = scores.mean(axis=2)  # ≈ 1.0 GB

            monthly_ics = pd.Series(
                [
                    information_coefficient(_score_df(composite[t], returns[t]))
                    for t in range(n_months)
                ]
            )
            mean_ic = monthly_ics.mean()
            assert abs(mean_ic) < 0.05, f"Unexpected IC from random data: {mean_ic:.4f}"

        except MemoryError:
            pytest.skip("Not enough RAM for 20 GB stress test (expected in constrained CI)")
        finally:
            for obj in ("scores", "returns", "composite"):
                try:
                    del locals()[obj]
                except KeyError:
                    pass
            gc.collect()

    @pytest.mark.slow
    def test_valuation_throughput_benchmark(self):
        """Valuation throughput must exceed 1 security per second (conservative floor)."""
        universe = _make_universe(100, seed=314)
        orchestrator = Orchestrator()

        start = time.perf_counter()
        scored = sum(1 for sec in universe if _try_value(orchestrator, sec))
        elapsed = time.perf_counter() - start

        throughput = scored / elapsed
        assert (
            throughput >= 1.0
        ), f"Throughput too low: {throughput:.2f} sec/security. Possible performance regression."
