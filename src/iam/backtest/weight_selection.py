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
import itertools
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

from iam.backtest.calibration import _json_safe
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

# Bump when a candidate's definition changes, so the ledger counts it as a new trial.
CANDIDATE_VERSION = 2

# Below these, a race is refused rather than run: a date with a handful of names
# gives a rank IC of +/-1, and a few months cannot support CPCV.
MIN_NAMES_PER_DATE = 20
MIN_DATES = 36


# --------------------------------------------------------------------------- #
# Trial ledger
# --------------------------------------------------------------------------- #


def _config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _git(*args: str) -> str | None:
    try:
        out = subprocess.check_output(  # nosec B603 B607 - fixed argv, no shell
            ["git", *args], cwd=Path(__file__).parent, stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def _git_state() -> tuple[str | None, bool | None]:
    """(HEAD SHA, whether the working tree has uncommitted changes) of this checkout."""
    sha = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return sha, (bool(status) if status is not None else None)


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
        sha, dirty = _git_state()
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_sha": sha,
            "git_dirty": dirty,
            "config_hash": _config_hash(config),
            "kind": kind,
            "name": name,
            "config": config,
            "result": result or {},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            # Strict JSON: NaN/inf become null.
            f.write(json.dumps(_json_safe(record), sort_keys=True, default=str, allow_nan=False))
            f.write("\n")
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
    if not np.all(np.isfinite(v)):
        raise ValueError("cannot project a vector with NaN or inf onto the simplex")
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
    means, _ = ic_mean_and_se(ctx.ic, ctx.nw_lags)
    positive = np.isfinite(means) & (means > 0)
    if not positive.any():
        return np.array(ctx.prior, dtype=float)
    return np.asarray(positive / positive.sum(), dtype=float)


def candidate_shrunk_icir(ctx: CandidateContext) -> np.ndarray:
    means, ses = ic_mean_and_se(ctx.ic, ctx.nw_lags)
    means = means * ctx.haircut
    sds = np.nanstd(ctx.ic, axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        icir = np.where(sds > 0, means / sds, np.nan)
    data_w = empirical_bayes_data_weight(means, ses)
    return _blend(data_w, _normalise(icir), ctx.prior)


def candidate_shrunk_iccov(ctx: CandidateContext) -> np.ndarray:
    means, ses = ic_mean_and_se(ctx.ic, ctx.nw_lags)
    means = means * ctx.haircut
    usable = np.isfinite(means)
    if usable.sum() < 2 or len(ctx.ic) < 2:
        return np.array(ctx.prior, dtype=float)
    # The haircut discounts the expected IC, not its noise: scaling the IC series
    # before estimating Sigma would cancel it (Sigma^-1 would undo the scaling).
    sigma = ledoit_wolf_shrinkage(ctx.ic[:, usable])
    raw = np.zeros(len(means))
    try:
        raw[usable] = np.linalg.solve(sigma, means[usable])
    except np.linalg.LinAlgError:
        raw[usable] = np.linalg.lstsq(sigma, means[usable], rcond=None)[0]
    # A near-singular covariance (very short training folds) can return inf/NaN.
    signal = project_to_simplex(raw) if np.all(np.isfinite(raw)) and np.any(raw > 0) else None
    data_w = empirical_bayes_data_weight(means, ses)
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


def cpcv_paths(n_dates: int, n_groups: int, k_test_groups: int) -> list[list[tuple[int, int]]]:
    """Recombine CPCV splits into backtest paths (Lopez de Prado 2018, ch. 12).

    Splits follow ``get_cpcv_splits``: groups are ``np.array_split`` of the dates and
    test sets are ``itertools.combinations`` of groups in order. Each group is tested
    in C(n-1, k-1) splits; path p takes the p-th of those for every group, so each
    path covers every date exactly once. Returns, per path, ``(split, group)`` pairs.
    """
    combos = list(itertools.combinations(range(n_groups), k_test_groups))
    occurrences = {g: [s for s, c in enumerate(combos) if g in c] for g in range(n_groups)}
    n_paths = len(occurrences[0]) if n_dates >= n_groups else 0
    return [[(occurrences[g][p], g) for g in range(n_groups)] for p in range(n_paths)]


def select_winner(
    path_ic: dict[str, list[float]],
    pbo: float | None,
    spa_pvalue: float | None,
) -> tuple[str, bool, dict[str, float], list[str]]:
    """Apply the selection rule. Returns (winner, promoted, win_fraction, reasons).

    A challenger is promoted only if it beats the prior on at least
    ``MIN_PATH_WIN_FRACTION`` of paths, PBO is below ``MAX_PBO`` and the SPA p-value
    is below ``SPA_ALPHA``. Otherwise the prior is kept, with the reasons.
    """
    prior_paths = np.array(path_ic[PRIOR], dtype=float)
    win_fraction: dict[str, float] = {}
    for n, ics in path_ic.items():
        if n == PRIOR:
            continue
        p = np.array(ics, dtype=float)
        ok = np.isfinite(p) & np.isfinite(prior_paths)
        win_fraction[n] = float(np.mean(p[ok] > prior_paths[ok])) if ok.any() else 0.0

    eligible = [n for n, w in win_fraction.items() if w >= MIN_PATH_WIN_FRACTION]
    if not eligible:
        return (
            PRIOR,
            False,
            win_fraction,
            [f"no challenger beat the prior on at least {MIN_PATH_WIN_FRACTION:.0%} of paths"],
        )
    best = max(eligible, key=lambda n: float(np.nanmean(path_ic[n])))
    reasons = []
    if pbo is None or not pbo < MAX_PBO:
        reasons.append(f"PBO {pbo} is not below {MAX_PBO}")
    if spa_pvalue is None or not spa_pvalue < SPA_ALPHA:
        reasons.append(f"SPA p-value {spa_pvalue} is not below {SPA_ALPHA}")
    if reasons:
        return PRIOR, False, win_fraction, reasons
    return best, True, win_fraction, [f"{best} beat the prior on {win_fraction[best]:.0%} of paths"]


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
    oos_ic_by_path: list[pd.DataFrame]  # per path: (T, N) OOS rank IC, each date once
    full_sample_weights: dict[str, np.ndarray]
    pbo: float | None = None  # median over paths
    spa_pvalue: float | None = None  # median over paths
    dsr: float | None = None  # median over paths
    n_trials: int | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _median(values: list[float]) -> float | None:
    finite = [v for v in values if v is not None and np.isfinite(v)]
    return float(np.median(finite)) if finite else None


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
    min_names_per_date: int = MIN_NAMES_PER_DATE,
    min_dates: int = MIN_DATES,
    literature_factors: Iterable[str] = LITERATURE_FACTORS,
    candidates: dict[str, Callable[[CandidateContext], np.ndarray]] | None = None,
    ledger: TrialLedger | None = None,
    spa_n_boot: int = 2000,
    seed: int | None = 0,
) -> HorseRaceResult:
    """Run the pre-registered candidate horse race over the development period.

    ``factor_scores_by_date[d]`` is an (n_d, K) array of factor scores in
    ``factor_names`` order, centred within each date (rank-normalise them first): a
    missing score is treated as neutral (0) when forming a composite.
    ``returns_by_date[d]`` holds the matching h-month forward returns. Monthly dates
    are assumed: purge and embargo are both ``horizon_months`` months. Dates with
    fewer than ``min_names_per_date`` usable returns are dropped, and fewer than
    ``min_dates`` remaining dates is a failure, not a result.
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

    dates = sorted(
        d
        for d in dates
        if d in factor_scores_by_date
        and d in returns_by_date
        and int(np.isfinite(returns_by_date[d]).sum()) >= min_names_per_date
    )
    haircut = haircut_vector(factor_names, literature_factors)
    nw_lags = max(3, horizon_months - 1)

    def _failed(status: str) -> HorseRaceResult:
        return HorseRaceResult(
            status=status,
            winner=PRIOR,
            promoted=False,
            reasons=[status],
            factor_names=factor_names,
            candidate_names=names,
            path_oos_ic={},
            win_fraction={},
            oos_ic_by_path=[],
            full_sample_weights={PRIOR: prior_n},
        )

    if len(dates) < max(min_dates, n_groups):
        return _failed(
            f"failed: {len(dates)} usable dates (each with at least {min_names_per_date} "
            f"names); at least {max(min_dates, n_groups)} are required"
        )

    gap_days = 31 * horizon_months
    splits = get_cpcv_splits(
        dates,
        n_groups=n_groups,
        k_test_groups=k_test_groups,
        purge_days=gap_days,
        embargo_days=gap_days,
    )
    groups = np.array_split(np.arange(len(dates)), n_groups)
    ic_all = factor_ic_matrix(dates, factor_scores_by_date, returns_by_date)

    # oos[s][j, i]: OOS rank IC of candidate j on date i, from split s.
    oos: list[np.ndarray] = []
    for train_idx, test_idx in splits:
        pred = np.full((len(names), len(dates)), np.nan)
        if len(train_idx) >= 2:
            ctx = CandidateContext(
                ic=ic_all[train_idx], prior=prior_n, haircut=haircut, nw_lags=nw_lags
            )
            for j, n in enumerate(names):
                w = cands[n](ctx)
                for i in test_idx:
                    d = dates[i]
                    composite = np.nan_to_num(factor_scores_by_date[d], nan=0.0) @ w
                    pred[j, i] = _rank_ic(composite, returns_by_date[d])
        oos.append(pred)

    paths = cpcv_paths(len(dates), n_groups, k_test_groups)
    index = pd.DatetimeIndex(dates)
    path_frames: list[pd.DataFrame] = []
    for path in paths:
        series = np.full((len(dates), len(names)), np.nan)
        for s, g in path:
            series[groups[g], :] = oos[s][:, groups[g]].T
        path_frames.append(pd.DataFrame(series, index=index, columns=names))

    path_ic = {n: [float(f[n].mean()) for f in path_frames] for n in names}
    if not any(np.isfinite(path_ic[PRIOR])):
        return _failed(
            "failed: no finite out-of-sample IC; check for missing factor scores or returns"
        )

    # Overfitting statistics per path, summarised by the median.
    challengers = [n for n in names if n != PRIOR]
    pbos, spa_ps = [], []
    for f in path_frames:
        clean = f.dropna()
        n_part = min(16, len(clean) // 2)
        n_part -= n_part % 2
        if n_part >= 2 and clean.shape[1] >= 2:
            pbos.append(probability_of_backtest_overfitting(clean.to_numpy(), n_part))
        if challengers and len(clean) > 1:
            spa = superior_predictive_ability(
                clean[challengers].to_numpy(),
                clean[PRIOR].to_numpy(),
                block_prob=1.0 / (2 * max(horizon_months, 1)),
                n_boot=spa_n_boot,
                seed=seed,
            )
            spa_ps.append(spa["spa_pvalue"])
    pbo, spa_p = _median(pbos), _median(spa_ps)

    winner, promoted, win_fraction, reasons = select_winner(path_ic, pbo, spa_p)

    full_ctx = CandidateContext(ic=ic_all, prior=prior_n, haircut=haircut, nw_lags=nw_lags)
    full_weights = {n: cands[n](full_ctx) for n in names}

    def _ir(n: str) -> float:
        irs = []
        for f in path_frames:
            col = f[n].dropna()
            if len(col) > 2 and col.std(ddof=1) > 0:
                irs.append(float(col.mean() / col.std(ddof=1)))
        return float(np.median(irs)) if irs else float("nan")

    oos_ir = {n: _ir(n) for n in names}

    n_trials = len(names)
    trial_irs = [v for v in oos_ir.values() if np.isfinite(v)]
    if ledger is not None:
        for n in names:
            ledger.append(
                kind="weight_candidate",
                name=n,
                config={
                    "candidate": n,
                    "candidate_version": CANDIDATE_VERSION,
                    "factor_names": factor_names,
                    "prior": prior_n.round(6).tolist(),
                    "horizon_months": horizon_months,
                    "n_groups": n_groups,
                    "k_test_groups": k_test_groups,
                    "min_names_per_date": min_names_per_date,
                    "nw_lags": nw_lags,
                    "max_data_weight": MAX_DATA_WEIGHT,
                    "literature_haircut": LITERATURE_HAIRCUT,
                    "literature_factors": sorted(set(literature_factors)),
                    "period": [str(dates[0].date()), str(dates[-1].date())],
                },
                result={
                    "mean_path_oos_ic": float(np.nanmean(path_ic[n])),
                    "oos_ir": oos_ir[n],
                    "win_fraction_vs_prior": win_fraction.get(n),
                    "weights": full_weights[n].round(6).tolist(),
                },
            )
        n_trials = max(n_trials, ledger.n_trials())
        # Dispersion of Sharpe ratios across every distinct trial on record, not
        # just this run's handful of correlated candidates.
        latest: dict[str, float] = {}
        for r in ledger.records():
            ir = r.get("result", {}).get("oos_ir")
            if isinstance(ir, int | float) and np.isfinite(ir):
                latest[r["config_hash"]] = float(ir)
        if len(latest) >= 2:
            trial_irs = list(latest.values())

    # DSR per path for the selected spec. Overlapping h-month labels leave about
    # T/h independent observations.
    dsrs = []
    var_trials = float(np.var(trial_irs, ddof=1)) if len(trial_irs) > 1 else 0.0
    for f in path_frames:
        col = f[winner].dropna()
        n_obs = len(col) // max(horizon_months, 1)
        if n_obs > 2 and col.std(ddof=1) > 0:
            dsrs.append(
                deflated_sharpe_ratio(
                    observed_sr=float(col.mean() / col.std(ddof=1)),
                    n_obs=n_obs,
                    n_trials=n_trials,
                    var_trials=var_trials,
                )
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
        oos_ic_by_path=path_frames,
        full_sample_weights=full_weights,
        pbo=pbo,
        spa_pvalue=spa_p,
        dsr=_median(dsrs),
        n_trials=n_trials,
        extras={"oos_ir": oos_ir, "n_dates": len(dates), "n_paths": len(paths)},
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
