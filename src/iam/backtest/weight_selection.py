"""Pre-registered weight horse race (Rung 2 of docs/research/backtest-strategy.md).

Instead of fitting free weights, a small fixed set of candidates competes against
the prior weights out of sample:

- A. ``prior``: the hand-set weights, unchanged.
- B. ``equal``: 1/N over factors whose training-period rank IC is positive.
- C. ``shrunk_icir``: positive ICIR weights blended with the prior, factor by factor,
  with the data weight set by empirical Bayes.
- D. ``shrunk_iccov``: Sigma_IC^-1 E[IC] with Ledoit-Wolf shrinkage of Sigma_IC,
  projected to the simplex and blended with the prior the same way.

Every candidate is refitted inside each CPCV training fold and scored on the test
fold. A challenger replaces the prior only if it beats it on at least 70% of paths,
PBO over the candidate set is below 0.5, and Hansen's SPA rejects "no candidate
beats the prior" at 10%. Every candidate evaluated is recorded in a
:class:`TrialLedger`, which supplies the trial count for the deflated Sharpe ratio.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from iam.backtest.cpcv import get_cpcv_splits
from iam.backtest.metrics import newey_west_se_rigorous
from iam.backtest.multiple_testing import deflated_sharpe_ratio
from iam.backtest.overfitting import probability_of_backtest_overfitting
from iam.backtest.spa import superior_predictive_ability
from iam.backtest.weight_optimizer import _rank_ic, ledoit_wolf_shrinkage

logger = logging.getLogger(__name__)

# Factors whose premium comes from the published literature (value, quality,
# momentum, accruals). Their in-sample ICs are halved before weighting: McLean and
# Pontiff (2016) find returns 58% lower after publication.
LITERATURE_FACTORS: frozenset[str] = frozenset(
    {"intrinsic_value", "relative_value", "quality", "sentiment", "earnings_quality"}
)
LITERATURE_HAIRCUT = 0.5

# No factor's weight may be driven more than 70% by one sample.
MAX_DATA_WEIGHT = 0.7

# Selection rule thresholds.
MIN_PATH_WIN_FRACTION = 0.70
MAX_PBO = 0.5
SPA_ALPHA = 0.10

PRIOR = "prior"


# --------------------------------------------------------------------------- #
# Trial ledger
# --------------------------------------------------------------------------- #


def _config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(  # nosec B603 B607 - fixed argv, no shell
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


class TrialLedger:
    """Append-only JSONL record of every specification evaluated.

    Each line holds a timestamp, git SHA, configuration hash, the kind and name of
    the trial, its configuration and its development-period result. Hand edits to
    the default weights are trials too and should be recorded with
    ``kind="manual"``.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def append(
        self,
        kind: str,
        name: str,
        config: dict[str, Any],
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_sha": _git_sha(),
            "config_hash": _config_hash(config),
            "kind": kind,
            "name": name,
            "config": config,
            "result": result or {},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        return record

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def n_trials(self) -> int:
        """Distinct specifications tried (re-running an identical config is not a new trial)."""
        return len({r["config_hash"] for r in self.records()})

    def file_hash(self) -> str | None:
        """SHA-256 of the ledger file, for the run manifest."""
        if not self.path.exists():
            return None
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #


def factor_ic_matrix(
    dates: list[pd.Timestamp],
    factor_scores_by_date: dict[pd.Timestamp, np.ndarray],
    returns_by_date: dict[pd.Timestamp, np.ndarray],
) -> np.ndarray:
    """(T, K) matrix of per-date rank ICs, one column per factor (NaN where undefined)."""
    rows = []
    for d in dates:
        scores, rets = factor_scores_by_date[d], returns_by_date[d]
        rows.append([_rank_ic(scores[:, k], rets) for k in range(scores.shape[1])])
    return np.asarray(rows, dtype=float)


def haircut_vector(factor_names: list[str], literature: Iterable[str]) -> np.ndarray:
    lit = set(literature)
    return np.array([LITERATURE_HAIRCUT if n in lit else 1.0 for n in factor_names])


def ic_mean_and_se(ic: np.ndarray, nw_lags: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-factor mean IC and its Newey-West standard error (NaN when undefined)."""
    means, ses = [], []
    for k in range(ic.shape[1]):
        col = pd.Series(ic[:, k]).dropna()
        means.append(float(col.mean()) if len(col) else float("nan"))
        _, _, se = newey_west_se_rigorous(col, nlags=nw_lags)
        ses.append(float(se))
    return np.array(means), np.array(ses)


def empirical_bayes_data_weight(
    ic_means: np.ndarray, ic_ses: np.ndarray, cap: float = MAX_DATA_WEIGHT
) -> np.ndarray:
    """Per-factor weight on the data, tau^2 / (tau^2 + se_k^2), capped.

    tau^2, the spread of true ICs across factors, is estimated by method of moments
    (James-Stein / Efron-Morris): the cross-factor variance of mean ICs minus the
    average sampling variance. When sampling noise explains all the dispersion,
    tau^2 is zero and every factor stays at its prior. Factors with an undefined
    mean or standard error get zero data weight.
    """
    ok = np.isfinite(ic_means) & np.isfinite(ic_ses)
    weights = np.zeros(len(ic_means))
    if ok.sum() < 2:
        return weights
    m, se2 = ic_means[ok], ic_ses[ok] ** 2
    tau2 = max(0.0, float(np.var(m, ddof=1) - np.mean(se2)))
    if tau2 == 0.0:
        return weights
    weights[ok] = np.minimum(cap, tau2 / (tau2 + se2))
    return weights


def project_to_simplex(v: np.ndarray) -> np.ndarray:
    """Euclidean projection onto {w >= 0, sum(w) = 1} (Duchi et al. 2008)."""
    v = np.asarray(v, dtype=float)
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    idx = np.arange(1, len(v) + 1)
    rho = np.nonzero(u * idx > (css - 1.0))[0][-1]
    theta = (css[rho] - 1.0) / (rho + 1.0)
    return np.asarray(np.maximum(v - theta, 0.0), dtype=float)


def _normalise(w: np.ndarray) -> np.ndarray | None:
    w = np.where(np.isfinite(w), np.maximum(w, 0.0), 0.0)
    total = w.sum()
    return w / total if total > 0 else None


def _blend(data_w: np.ndarray, signal: np.ndarray | None, prior: np.ndarray) -> np.ndarray:
    """Factor-wise blend d_k * signal_k + (1 - d_k) * prior_k, renormalised."""
    if signal is None:
        return np.array(prior, dtype=float)
    blended = data_w * signal + (1.0 - data_w) * prior
    out = _normalise(blended)
    return out if out is not None else prior.copy()


# --------------------------------------------------------------------------- #
# Candidates
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CandidateContext:
    """What a candidate may learn from: the training-fold IC matrix only."""

    ic: np.ndarray  # (T_train, K) per-date rank ICs
    prior: np.ndarray
    haircut: np.ndarray
    nw_lags: int


def candidate_prior(ctx: CandidateContext) -> np.ndarray:
    return np.array(ctx.prior, dtype=float)


def candidate_equal(ctx: CandidateContext) -> np.ndarray:
    means = np.nanmean(ctx.ic, axis=0) if len(ctx.ic) else np.full(len(ctx.prior), np.nan)
    positive = np.isfinite(means) & (means > 0)
    if not positive.any():
        return np.array(ctx.prior, dtype=float)
    return positive / positive.sum()


def candidate_shrunk_icir(ctx: CandidateContext) -> np.ndarray:
    means, ses = ic_mean_and_se(ctx.ic, ctx.nw_lags)
    means = means * ctx.haircut
    sds = np.nanstd(ctx.ic, axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        icir = np.where(sds > 0, means / sds, np.nan)
    data_w = empirical_bayes_data_weight(means, ses * ctx.haircut)
    return _blend(data_w, _normalise(icir), ctx.prior)


def candidate_shrunk_iccov(ctx: CandidateContext) -> np.ndarray:
    means, ses = ic_mean_and_se(ctx.ic, ctx.nw_lags)
    means = means * ctx.haircut
    usable = np.isfinite(means)
    if usable.sum() < 2 or len(ctx.ic) < 2:
        return np.array(ctx.prior, dtype=float)
    sigma = ledoit_wolf_shrinkage(ctx.ic[:, usable] * ctx.haircut[usable])
    raw = np.zeros(len(means))
    try:
        raw[usable] = np.linalg.solve(sigma, means[usable])
    except np.linalg.LinAlgError:
        raw[usable] = np.linalg.lstsq(sigma, means[usable], rcond=None)[0]
    signal = project_to_simplex(raw) if np.any(raw > 0) else None
    data_w = empirical_bayes_data_weight(means, ses * ctx.haircut)
    return _blend(data_w, signal, ctx.prior)


CANDIDATES: dict[str, Callable[[CandidateContext], np.ndarray]] = {
    PRIOR: candidate_prior,
    "equal": candidate_equal,
    "shrunk_icir": candidate_shrunk_icir,
    "shrunk_iccov": candidate_shrunk_iccov,
}


# --------------------------------------------------------------------------- #
# Horse race
# --------------------------------------------------------------------------- #


@dataclass
class HorseRaceResult:
    status: str
    winner: str
    promoted: bool
    reasons: list[str]
    factor_names: list[str]
    candidate_names: list[str]
    path_oos_ic: dict[str, list[float]]  # mean OOS IC per CPCV path
    win_fraction: dict[str, float]  # share of paths beating the prior
    oos_ic_by_date: pd.DataFrame  # (T, N) OOS rank IC, averaged across paths covering each date
    full_sample_weights: dict[str, np.ndarray]
    pbo: float | None = None
    spa_pvalue: float | None = None
    dsr: float | None = None
    n_trials: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def run_horse_race(
    dates: list[pd.Timestamp],
    factor_scores_by_date: dict[pd.Timestamp, np.ndarray],
    returns_by_date: dict[pd.Timestamp, np.ndarray],
    factor_names: list[str],
    prior_weights: np.ndarray | dict[str, float],
    *,
    horizon_months: int = 1,
    n_groups: int = 6,
    k_test_groups: int = 2,
    literature_factors: Iterable[str] = LITERATURE_FACTORS,
    candidates: dict[str, Callable[[CandidateContext], np.ndarray]] | None = None,
    ledger: TrialLedger | None = None,
    spa_n_boot: int = 2000,
    seed: int | None = 0,
) -> HorseRaceResult:
    """Run the pre-registered candidate horse race over the development period.

    ``factor_scores_by_date[d]`` is an (n_d, K) array of factor scores in
    ``factor_names`` order (rank-normalise them within each date first);
    ``returns_by_date[d]`` holds the matching h-month forward returns. Monthly dates
    are assumed: purge and embargo are both ``horizon_months`` months.
    """
    cands = dict(candidates or CANDIDATES)
    if PRIOR not in cands:
        cands = {PRIOR: candidate_prior, **cands}
    names = list(cands)
    k = len(factor_names)

    if isinstance(prior_weights, dict):
        prior = np.array([prior_weights.get(n, 0.0) for n in factor_names], dtype=float)
    else:
        prior = np.asarray(prior_weights, dtype=float)
    prior_n = _normalise(prior)
    if prior_n is None or len(prior) != k:
        raise ValueError("prior_weights must give a positive weight vector over factor_names")

    dates = sorted(d for d in dates if d in factor_scores_by_date and d in returns_by_date)
    haircut = haircut_vector(factor_names, literature_factors)
    nw_lags = max(3, horizon_months - 1)

    def _empty(status: str) -> HorseRaceResult:
        return HorseRaceResult(
            status=status,
            winner=PRIOR,
            promoted=False,
            reasons=[status],
            factor_names=factor_names,
            candidate_names=names,
            path_oos_ic={},
            win_fraction={},
            oos_ic_by_date=pd.DataFrame(columns=names),
            full_sample_weights={PRIOR: prior_n},
        )

    try:
        gap_days = 31 * horizon_months
        splits = get_cpcv_splits(
            dates,
            n_groups=n_groups,
            k_test_groups=k_test_groups,
            purge_days=gap_days,
            embargo_days=gap_days,
        )
    except ValueError as e:
        return _empty(f"failed: {e}")

    ic_all = factor_ic_matrix(dates, factor_scores_by_date, returns_by_date)

    path_ic: dict[str, list[float]] = {n: [] for n in names}
    sums = np.zeros((len(dates), len(names)))
    counts = np.zeros((len(dates), len(names)))

    for train_idx, test_idx in splits:
        if len(train_idx) < 2:
            continue
        ctx = CandidateContext(
            ic=ic_all[train_idx], prior=prior_n, haircut=haircut, nw_lags=nw_lags
        )
        fold_ics: dict[str, list[float]] = {}
        for j, n in enumerate(names):
            w = cands[n](ctx)
            per_date = []
            for i in test_idx:
                d = dates[i]
                ic = _rank_ic(factor_scores_by_date[d] @ w, returns_by_date[d])
                per_date.append(ic)
                if np.isfinite(ic):
                    sums[i, j] += ic
                    counts[i, j] += 1
            fold_ics[n] = per_date
        for n in names:
            vals = [v for v in fold_ics[n] if np.isfinite(v)]
            path_ic[n].append(float(np.mean(vals)) if vals else float("nan"))

    with np.errstate(invalid="ignore"):
        oos = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
    oos_df = pd.DataFrame(oos, index=pd.DatetimeIndex(dates), columns=names)

    prior_paths = np.array(path_ic[PRIOR])
    win_fraction = {}
    for n in names:
        if n == PRIOR:
            continue
        p = np.array(path_ic[n])
        ok = np.isfinite(p) & np.isfinite(prior_paths)
        win_fraction[n] = float(np.mean(p[ok] > prior_paths[ok])) if ok.any() else 0.0

    # Overfitting statistics over the candidate set.
    clean = oos_df.dropna()
    pbo = None
    n_part = min(16, len(clean) // 2)
    n_part -= n_part % 2
    if n_part >= 2 and clean.shape[1] >= 2:
        pbo = probability_of_backtest_overfitting(clean.to_numpy(), n_partitions=n_part)

    challengers = [n for n in names if n != PRIOR]
    spa_p = None
    if challengers and len(clean) > 1:
        spa = superior_predictive_ability(
            clean[challengers].to_numpy(),
            clean[PRIOR].to_numpy(),
            block_prob=1.0 / max(horizon_months, 1),
            n_boot=spa_n_boot,
            seed=seed,
        )
        spa_p = spa["spa_pvalue"]

    # Full-sample weights, for reporting and as the frozen spec if promoted.
    full_ctx = CandidateContext(ic=ic_all, prior=prior_n, haircut=haircut, nw_lags=nw_lags)
    full_weights = {n: cands[n](full_ctx) for n in names}

    # Ledger: one trial per candidate method, plus the DSR from the ledger count.
    n_trials = len(names)
    if ledger is not None:
        for n in names:
            ledger.append(
                kind="weight_candidate",
                name=n,
                config={
                    "candidate": n,
                    "factor_names": factor_names,
                    "prior": prior_n.round(6).tolist(),
                    "horizon_months": horizon_months,
                    "n_groups": n_groups,
                    "k_test_groups": k_test_groups,
                    "literature_factors": sorted(set(literature_factors)),
                    "period": [str(dates[0].date()), str(dates[-1].date())] if dates else None,
                },
                result={
                    "mean_path_oos_ic": float(np.nanmean(path_ic[n])) if path_ic[n] else None,
                    "win_fraction_vs_prior": win_fraction.get(n),
                    "weights": full_weights[n].round(6).tolist(),
                },
            )
        n_trials = max(n_trials, ledger.n_trials())

    # Selection rule.
    eligible = [n for n in challengers if win_fraction.get(n, 0.0) >= MIN_PATH_WIN_FRACTION]
    reasons: list[str] = []
    winner = PRIOR
    promoted = False
    if not eligible:
        reasons.append(
            f"no challenger beat the prior on at least {MIN_PATH_WIN_FRACTION:.0%} of CPCV paths"
        )
    else:
        best = max(eligible, key=lambda n: float(np.nanmean(path_ic[n])))
        if pbo is None or pbo >= MAX_PBO:
            reasons.append(f"PBO {pbo} is not below {MAX_PBO}")
        if spa_p is None or spa_p >= SPA_ALPHA:
            reasons.append(f"SPA p-value {spa_p} is not below {SPA_ALPHA}")
        if not reasons:
            winner, promoted = best, True
            reasons.append(f"{best} beat the prior on {win_fraction[best]:.0%} of paths")

    dsr = None
    series = clean[winner] if winner in clean else pd.Series(dtype=float)
    if len(series) > 2 and series.std(ddof=1) > 0:
        irs = clean.mean() / clean.std(ddof=1)
        dsr = deflated_sharpe_ratio(
            observed_sr=float(series.mean() / series.std(ddof=1)),
            n_obs=len(series),
            n_trials=n_trials,
            var_trials=float(np.nanvar(irs.to_numpy(), ddof=1)) if len(irs) > 1 else 0.0,
        )

    return HorseRaceResult(
        status="success",
        winner=winner,
        promoted=promoted,
        reasons=reasons,
        factor_names=factor_names,
        candidate_names=names,
        path_oos_ic=path_ic,
        win_fraction=win_fraction,
        oos_ic_by_date=oos_df,
        full_sample_weights=full_weights,
        pbo=pbo,
        spa_pvalue=spa_p,
        dsr=dsr,
        n_trials=n_trials,
    )


def format_horse_race_report(result: HorseRaceResult) -> str:
    """Plain-text summary: per-candidate path IC, win rate, weights and the decision."""
    lines = [
        f"Weight horse race: {result.status}",
        f"Decision: {'PROMOTE ' + result.winner if result.promoted else 'keep prior'}",
        *[f"  - {r}" for r in result.reasons],
        f"PBO: {result.pbo}  SPA p: {result.spa_pvalue}  DSR: {result.dsr}  "
        f"trials: {result.n_trials}",
        "",
        f"{'Candidate':<14} {'mean OOS IC':>12} {'wins vs prior':>14}",
    ]
    for n in result.candidate_names:
        ics = result.path_oos_ic.get(n, [])
        mean = float(np.nanmean(ics)) if ics else float("nan")
        win = result.win_fraction.get(n)
        win_txt = f"{win:.0%}" if win is not None else "-"
        lines.append(f"{n:<14} {mean:>12.4f} {win_txt:>14}")
    lines.append("")
    header = f"{'Factor':<26}" + "".join(f"{n:>14}" for n in result.full_sample_weights)
    lines.append(header)
    for i, f in enumerate(result.factor_names):
        row = f"{f:<26}" + "".join(f"{w[i]:>14.4f}" for w in result.full_sample_weights.values())
        lines.append(row)
    return "\n".join(lines)
