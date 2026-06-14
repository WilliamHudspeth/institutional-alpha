"""Multiple-testing and selection-bias correction for the backtest gates.

The backtest advertises single-test significance gates (IR >= 0.30, |t| >= 2.0).
But the framework evaluates ~12 factors and *searches* over factor weights, so
those thresholds are applied to a large multiple-testing surface. With K trials,
the best-looking statistic is inflated by selection: a factor that clears
|t| >= 2.0 in isolation may be noise once you account for how many things were
tried. This module deflates the gates so "significant" survives scrutiny.

It is the logical next layer on top of the rigor the repo already has
(Newey-West HAC SE, sector-neutral IC, Ledoit-Wolf shrinkage):

  - **Probabilistic Sharpe Ratio (PSR)** — Bailey & Lopez de Prado. The
    probability that the *true* Sharpe/IR exceeds a benchmark, adjusted for the
    skew and (fat) kurtosis of the returns and the sample length. Because the
    `information_ratio` is mean(IC)/std(IC), this applies directly to the IR gate.

  - **Deflated Sharpe Ratio (DSR)** — PSR evaluated against the *expected maximum*
    Sharpe under N trials (the "false strategy" benchmark). This is the headline
    correction for a strategy/factor selected as the best of many.

  - **Effective number of tests** — correlated factors are not independent tests.
    The eigenvalue participation ratio of the signal correlation matrix gives an
    effective K that is < the raw count when factors overlap.

  - **FWER / FDR p-value corrections** — Holm (family-wise) and Benjamini-Hochberg
    (false-discovery-rate) over a set of factor t-stats, reporting which factors
    survive.

Pure numpy + scipy.stats (already backtest deps); fully offline-testable.

References: Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio";
Lopez de Prado (2018), "Advances in Financial Machine Learning"; Harvey, Liu &
Zhu (2016), "...and the Cross-Section of Expected Returns".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import norm

_EULER_MASCHERONI = 0.5772156649015329


# --------------------------------------------------------------------------- #
# Probabilistic Sharpe Ratio and friends
# --------------------------------------------------------------------------- #
def sharpe_standard_error(sr: float, n: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """SE of a Sharpe/IR estimate (Lo 2002, with higher-moment adjustment).

    Args:
        sr: observed Sharpe (or information ratio) per period.
        n: number of observations (periods).
        skew: skewness of the returns/IC series (0 for normal).
        kurt: NON-excess kurtosis (3 for normal).
    """
    if n < 2:
        return float("nan")
    var = (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2) / (n - 1)
    return math.sqrt(max(var, 1e-300))


def probabilistic_sharpe_ratio(
    sr: float,
    n: int,
    skew: float = 0.0,
    kurt: float = 3.0,
    sr_benchmark: float = 0.0,
) -> float:
    """P(true Sharpe > sr_benchmark) given the observed estimate.

    Returns a probability in [0, 1]. Higher n, higher sr, lower kurtosis and
    favourable skew all raise the probability.
    """
    se = sharpe_standard_error(sr, n, skew, kurt)
    if math.isnan(se) or se == 0:
        return float("nan")
    return float(norm.cdf((sr - sr_benchmark) / se))


def min_track_record_length(
    sr: float,
    skew: float = 0.0,
    kurt: float = 3.0,
    sr_benchmark: float = 0.0,
    confidence: float = 0.95,
) -> float:
    """Minimum number of observations for PSR(sr) >= confidence.

    Tells you how long a track record must be before the IR/Sharpe is credible
    at the chosen confidence. Returns inf if sr <= benchmark.
    """
    if sr <= sr_benchmark:
        return float("inf")
    z = norm.ppf(confidence)
    numer = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    return 1.0 + numer * (z / (sr - sr_benchmark)) ** 2  # type: ignore


def expected_max_sharpe(
    n_trials: int,
    var_trials: float,
    mean_trials: float = 0.0,
    effective_trials: float | None = None,
) -> float:
    """Expected maximum Sharpe across N independent trials (false-strategy theorem).

    Approximates E[max of N draws from N(mean_trials, var_trials)] via the
    extreme-value expansion used in Bailey & Lopez de Prado. This is the bar a
    *selected best* strategy must clear to be more than luck.
    """
    n = effective_trials if effective_trials is not None else float(n_trials)
    if n < 1.0:
        return mean_trials
    if n == 1.0 or var_trials <= 0:
        return mean_trials
    sigma = math.sqrt(var_trials)
    g = _EULER_MASCHERONI
    z1 = norm.ppf(1.0 - 1.0 / n)
    z2 = norm.ppf(1.0 - 1.0 / (n * math.e))
    return mean_trials + sigma * ((1.0 - g) * z1 + g * z2)  # type: ignore


def deflated_sharpe_ratio(
    observed_sr: float,
    n_obs: int,
    n_trials: int,
    var_trials: float,
    skew: float = 0.0,
    kurt: float = 3.0,
    mean_trials: float = 0.0,
    effective_trials: float | None = None,
) -> float:
    """Deflated Sharpe Ratio: PSR benchmarked against the expected max over trials.

    Args:
        observed_sr: the selected strategy/factor's observed Sharpe/IR.
        n_obs: number of observations (periods) in its track record.
        n_trials: how many strategies/factors/weight-vectors were tried.
        var_trials: variance of the Sharpe estimates across those trials.
        skew, kurt: higher moments of the selected series (kurt non-excess).
        mean_trials: mean Sharpe across trials (usually ~0 for a factor zoo).
        effective_trials: effective number of independent trials.

    Returns P(true Sharpe > expected-max-under-selection) in [0, 1]. A DSR below
    ~0.95 means the result is not distinguishable from the best of N lucky tries.
    """
    sr_star = expected_max_sharpe(
        n_trials, var_trials, mean_trials, effective_trials=effective_trials
    )
    return probabilistic_sharpe_ratio(observed_sr, n_obs, skew, kurt, sr_benchmark=sr_star)


# --------------------------------------------------------------------------- #
# Effective number of tests
# --------------------------------------------------------------------------- #
def effective_num_tests(correlation: np.ndarray) -> float:
    """Effective number of independent tests from a signal correlation matrix.

    Uses the eigenvalue participation ratio:  (sum lambda)^2 / sum(lambda^2).
    Equals K when the K factors are uncorrelated and tends to 1 as they become
    perfectly correlated. Correlated factors should not each count as a fresh
    independent test in a Bonferroni-style correction.
    """
    c = np.asarray(correlation, dtype=float)
    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        raise ValueError("correlation must be a square matrix")
    k = c.shape[0]
    if k <= 1:
        return float(k)
    eig = np.linalg.eigvalsh(c)
    eig = np.clip(eig, 0.0, None)
    s = eig.sum()
    s2 = (eig**2).sum()
    if s2 <= 0:
        return float(k)
    return float(s**2 / s2)


# --------------------------------------------------------------------------- #
# Family-wise (Holm) and false-discovery-rate (Benjamini-Hochberg) corrections
# --------------------------------------------------------------------------- #
def _two_sided_p_from_t(t: float) -> float:
    return float(2.0 * (1.0 - norm.cdf(abs(t))))


@dataclass
class FactorVerdict:
    name: str
    t_stat: float
    raw_p: float
    holm_p: float
    bh_p: float
    survives_holm: bool
    survives_bh: bool


@dataclass
class MultipleTestingReport:
    verdicts: list[FactorVerdict]
    n_factors: int
    effective_tests: float | None
    fwer_alpha: float
    fdr_alpha: float
    notes: list[str] = field(default_factory=list)

    @property
    def survivors_holm(self) -> list[str]:
        return [v.name for v in self.verdicts if v.survives_holm]

    @property
    def survivors_bh(self) -> list[str]:
        return [v.name for v in self.verdicts if v.survives_bh]

    def explain(self) -> str:
        lines = [
            f"Multiple testing over {self.n_factors} factors"
            + (f" (~{self.effective_tests:.1f} effective)" if self.effective_tests else "")
            + f"; FWER alpha={self.fwer_alpha}, FDR alpha={self.fdr_alpha}",
        ]
        for v in sorted(self.verdicts, key=lambda x: x.raw_p):
            flag = "HOLM✓" if v.survives_holm else "     "
            bh = "BH✓" if v.survives_bh else "   "
            lines.append(
                f"  {v.name:24s} t={v.t_stat:+5.2f}  p={v.raw_p:.4f}"
                f"  holm={v.holm_p:.4f} {flag}  bh={v.bh_p:.4f} {bh}"
            )
        lines.append(f"Survivors (Holm/FWER): {self.survivors_holm or 'none'}")
        lines.append(f"Survivors (BH/FDR):    {self.survivors_bh or 'none'}")
        return "\n".join(lines)


def correct_factor_tests(
    t_stats: dict[str, float],
    *,
    fwer_alpha: float = 0.05,
    fdr_alpha: float = 0.10,
    effective_tests: float | None = None,
) -> MultipleTestingReport:
    """Apply Holm (FWER) and Benjamini-Hochberg (FDR) to a set of factor t-stats.

    Args:
        t_stats: {factor_name: t_statistic}.
        effective_tests: optional effective number of tests (e.g. from
            effective_num_tests on the signal correlation matrix). When given,
            Holm uses it instead of the raw count, so correlated factors are not
            over-penalised.
    """
    names = list(t_stats)
    m = len(names)
    if m == 0:
        return MultipleTestingReport(
            [], 0, effective_tests, fwer_alpha, fdr_alpha, notes=["No factors supplied."]
        )

    raw_p = {n: _two_sided_p_from_t(t_stats[n]) for n in names}
    m_eff = effective_tests if effective_tests is not None else float(m)

    # Holm step-down using the (possibly effective) number of tests.
    order = sorted(names, key=lambda n: raw_p[n])
    holm_p: dict[str, float] = {}
    running = 0.0
    for i, n in enumerate(order):
        # Multiplier floored at 1: a hypothesis is always tested at least
        # against itself, so a fractional effective count can't invert it.
        adj = min(1.0, raw_p[n] * max(1.0, m_eff - i))
        running = max(running, adj)  # enforce monotonicity
        holm_p[n] = running

    # Benjamini-Hochberg step-up (FDR) on the raw count.
    bh_p: dict[str, float] = {}
    prev = 1.0
    for i in range(m - 1, -1, -1):
        n = order[i]
        rank = i + 1
        adj = min(prev, raw_p[n] * m / rank)
        bh_p[n] = adj
        prev = adj

    verdicts = [
        FactorVerdict(
            name=n,
            t_stat=t_stats[n],
            raw_p=raw_p[n],
            holm_p=holm_p[n],
            bh_p=bh_p[n],
            survives_holm=holm_p[n] <= fwer_alpha,
            survives_bh=bh_p[n] <= fdr_alpha,
        )
        for n in names
    ]
    notes = []
    naive = [n for n in names if raw_p[n] <= fwer_alpha]
    holm_survivors = [v.name for v in verdicts if v.survives_holm]
    if len(naive) > len(holm_survivors):
        dropped = sorted(set(naive) - set(holm_survivors))
        notes.append(
            f"{len(dropped)} factor(s) pass the naive single-test gate but FAIL "
            f"family-wise correction: {dropped}. These are likely selection artifacts."
        )
    return MultipleTestingReport(
        verdicts=verdicts,
        n_factors=m,
        effective_tests=effective_tests,
        fwer_alpha=fwer_alpha,
        fdr_alpha=fdr_alpha,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Validation Metrics Suite
# --------------------------------------------------------------------------- #
@dataclass
class ValidationMetrics:
    psr: float
    dsr: float
    pbo: float
    spa_pvalue: float
    effective_tests: float
    fwer_significant_factors: int = 0
    fdr_significant_factors: int = 0


def compute_validation_metrics(df: pd.DataFrame, factor_names: list[str]) -> ValidationMetrics:
    """Compute comprehensive validation metrics for a backtest result DataFrame."""
    import warnings

    import pandas as pd

    # 1. psr (Probabilistic Sharpe Ratio)
    psr_val = float("nan")
    if "ic" in df.columns:
        ic_series = df["ic"].dropna()
        if len(ic_series) > 2:
            avg_ic = ic_series.mean()
            std_ic = ic_series.std()
            ir = avg_ic / std_ic if std_ic > 0 else 0.0
            skew = float(ic_series.skew()) if not pd.isna(ic_series.skew()) else 0.0
            kurt = float(ic_series.kurtosis()) + 3.0 if not pd.isna(ic_series.kurtosis()) else 3.0
            psr_val = probabilistic_sharpe_ratio(ir, len(ic_series), skew, kurt, sr_benchmark=0.0)

    # 2. dsr (Deflated Sharpe Ratio)
    dsr_val = float("nan")
    if "ic" in df.columns:
        ic_series = df["ic"].dropna()
        if len(ic_series) > 2:
            avg_ic = ic_series.mean()
            std_ic = ic_series.std()
            ir = avg_ic / std_ic if std_ic > 0 else 0.0
            skew = float(ic_series.skew()) if not pd.isna(ic_series.skew()) else 0.0
            kurt = float(ic_series.kurtosis()) + 3.0 if not pd.isna(ic_series.kurtosis()) else 3.0

            # calculate individual factor irs
            factor_irs = []
            for f in factor_names:
                col = f"ic_{f}"
                if col in df.columns:
                    s_f = df[col].dropna()
                    if len(s_f) > 2:
                        ir_f = s_f.mean() / s_f.std() if s_f.std() > 0 else 0.0
                        factor_irs.append(ir_f)
            var_trials = np.var(factor_irs) if len(factor_irs) > 1 else 0.01
            # n_trials represents the count of factors evaluated
            n_trials = len(factor_names)

            if var_trials > 0:
                # DSR explicitly uses actual trials without eigenvalue adjustment
                dsr_val = deflated_sharpe_ratio(
                    observed_sr=ir,
                    n_obs=len(ic_series),
                    n_trials=n_trials,
                    var_trials=var_trials,
                    skew=skew,
                    kurt=kurt,
                    mean_trials=0.0,
                    effective_trials=None,
                )

    # 3. pbo (Probability of Backtest Overfitting)
    pbo_val = float("nan")
    factor_cols = [f"ic_{f}" for f in factor_names if f"ic_{f}" in df.columns]
    if factor_cols:
        clean_df = df[factor_cols].dropna()
        if len(clean_df) >= 4 and len(factor_cols) >= 2:
            perf_matrix = clean_df.values
            n_partitions = min(16, len(perf_matrix) // 2)
            if n_partitions % 2 != 0:
                n_partitions -= 1
            if n_partitions >= 2:
                from iam.backtest.overfitting import probability_of_backtest_overfitting

                try:
                    pbo_val = probability_of_backtest_overfitting(
                        perf_matrix, n_partitions=n_partitions
                    )
                except Exception:
                    pass

    # 4. spa_pvalue (Hansen's Superior Predictive Ability against alternative single factors)
    spa_val = float("nan")
    if "ic" in df.columns:
        composite_ic = df["ic"].dropna()
        if factor_cols:
            equal_weight_ic = df[factor_cols].mean(axis=1).reindex(composite_ic.index).dropna()

            alts_dict = {"composite": composite_ic}
            for f_key in ["quality", "relative_value", "intrinsic_value", "momentum"]:
                col_name = f"ic_{f_key}"
                if col_name in df.columns:
                    alts_dict[f_key] = df[col_name]

            alts_df = pd.DataFrame(alts_dict)
            alts_df["benchmark"] = equal_weight_ic
            alts_df = alts_df.dropna()

            if len(alts_df) > 10:
                from iam.backtest.spa import superior_predictive_ability

                strat_returns = alts_df[list(alts_dict.keys())].values
                bench_returns = alts_df["benchmark"].values
                try:
                    spa_res = superior_predictive_ability(
                        strat_returns, benchmark_returns=bench_returns, seed=42
                    )
                    spa_val = spa_res["spa_pvalue"]
                except Exception:
                    pass

    # 5. effective_tests
    m_eff = float("nan")
    if len(factor_cols) > 1:
        ic_df = df[factor_cols].copy()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            corr_df = ic_df.fillna(0).corr(method="spearman").clip(-0.999, 0.999)
        corr_df = corr_df.fillna(0.0)
        corr_matrix = corr_df.values.copy()
        np.fill_diagonal(corr_matrix, 1.0)
        m_eff = effective_num_tests(corr_matrix)

    # 6. FWER and FDR significant factor counts
    fwer_sig = 0
    fdr_sig = 0
    t_stats_dict = {}
    for f in factor_names:
        col = f"ic_{f}"
        if col in df.columns:
            s_f = df[col].dropna()
            if len(s_f) > 2:
                from iam.backtest.metrics import newey_west_se_rigorous

                t_stat, _, _ = newey_west_se_rigorous(s_f, nlags=3)
                if not np.isnan(t_stat):
                    t_stats_dict[f] = t_stat

    if t_stats_dict:
        mt_report = correct_factor_tests(
            t_stats_dict, effective_tests=m_eff if not np.isnan(m_eff) else None
        )
        fwer_sig = len(mt_report.survivors_holm)
        fdr_sig = len(mt_report.survivors_bh)

    return ValidationMetrics(
        psr=psr_val,
        dsr=dsr_val,
        pbo=pbo_val,
        spa_pvalue=spa_val,
        effective_tests=m_eff,
        fwer_significant_factors=fwer_sig,
        fdr_significant_factors=fdr_sig,
    )
