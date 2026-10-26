"""Price coverage of the point-in-time universe, split by names that later delisted.

Free price sources (yfinance, Stooq) are not survivorship-free: they mostly lack the names that
later delisted, which are exactly the names whose omission biases a backtest. Before any IC is
computed, this report measures, for each month-end and horizon, how many universe members have
what the IC needs: a price at the month-end and either a price ``horizon`` months later or a
known delisting in between (whose return the three survivorship cases then supply).

The denominator is always the full universe. Coverage is reported for all members, for members
that later delisted (performance, voluntary or unknown delistings, plus mergers) and for
survivors, and the gate uses the WORSE of the two groups: 75% overall can hide near-zero coverage
of the delisted names, which are few but carry all of the bias (Section 3 of the backtest
strategy). A month whose later-delisted coverage is below the gate is labelled
"survivorship-biased".
"""

from __future__ import annotations

import pandas as pd

COVERAGE_GATE = 0.75
# A price counts for a month-end if it is dated within this many calendar days before it.
PRICE_TOLERANCE_DAYS = 7
# A delisting inside the horizon closes the return only if the series reaches close to it:
# exchanges often suspend trading before the Form 25 takes effect, so allow 30 days.
DELIST_PRICE_WINDOW_DAYS = 30


def _has_price_near(prices: pd.DataFrame, when: pd.Timestamp) -> set[int]:
    """CIKs with a close dated in [when - tolerance, when]."""
    lo = when - pd.Timedelta(days=PRICE_TOLERANCE_DAYS)
    window = prices[(prices["date"] > lo) & (prices["date"] <= when)]
    return set(window["cik"].astype(int))


def coverage_report(
    members: pd.DataFrame,
    prices: pd.DataFrame,
    delisted: pd.DataFrame,
    horizon_months: int = 1,
    gate: float = COVERAGE_GATE,
) -> pd.DataFrame:
    """Monthly coverage table.

    ``members``: columns ``month_end``, ``cik`` (the universe).
    ``prices``: columns ``cik``, ``date``, ``close`` (any source; one row per CIK and day).
    ``delisted``: columns ``cik``, ``effective`` (one row per delisted CIK; categories that are
    not delistings, such as transfers, must already be removed).

    A member is covered at month-end ``M`` when it has a price at ``M`` and, at ``M + h``,
    either a price or a delisting effective in ``(M, M + h]`` with a price in the
    ``DELIST_PRICE_WINDOW_DAYS`` before it (otherwise the return up to the delisting is
    unknown, whatever delisting return is then applied). "Later delisted" means a delisting
    effective after ``M`` at any time, which is known only ex post: the split is a diagnostic of
    the price source, not an input to any signal.
    """
    effective = dict(zip(delisted["cik"].astype(int), pd.to_datetime(delisted["effective"])))
    rows = []
    for month_end, group in members.groupby("month_end", sort=True):
        m = pd.Timestamp(month_end)
        # Snap to the calendar month-end first: from a business month-end such as Friday
        # 27 February, MonthEnd(1) would land on 28 February, not at the end of March.
        end = (m + pd.offsets.MonthEnd(0)) + pd.offsets.MonthEnd(horizon_months)
        priced_now = _has_price_near(prices, m)
        priced_end = _has_price_near(prices, end)
        ciks = group["cik"].astype(int)
        later = {c for c in ciks if c in effective and effective[c] > m}
        covered = set()
        for c in ciks:
            if c not in priced_now:
                continue
            if c in priced_end:
                covered.add(c)
            elif c in effective and m < effective[c] <= end:
                eff = effective[c]
                lo = max(m, eff - pd.Timedelta(days=DELIST_PRICE_WINDOW_DAYS))
                near = prices[
                    (prices["cik"] == c) & (prices["date"] > lo) & (prices["date"] <= eff)
                ]
                if not near.empty:
                    covered.add(c)
        survivors = set(ciks) - later
        n_later, n_surv = len(later), len(survivors)
        cov_all = len(covered) / len(ciks) if len(ciks) else float("nan")
        cov_later = len(covered & later) / n_later if n_later else float("nan")
        cov_surv = len(covered & survivors) / n_surv if n_surv else float("nan")
        worst = min(v for v in (cov_later, cov_surv) if v == v) if (n_later or n_surv) else cov_all
        rows.append(
            {
                "month_end": m,
                "horizon_months": horizon_months,
                "n_members": len(ciks),
                "n_covered": len(covered),
                "coverage": cov_all,
                "n_later_delisted": n_later,
                "coverage_later_delisted": cov_later,
                "n_survivors": n_surv,
                "coverage_survivors": cov_surv,
                "passes_gate": bool(worst >= gate),
                "survivorship_biased": bool(n_later and cov_later < gate),
            }
        )
    return pd.DataFrame(rows)


def summarise(report: pd.DataFrame) -> dict[str, float | int]:
    """Headline numbers for the run manifest."""
    if report.empty:
        return {"months": 0}
    return {
        "months": int(len(report)),
        "months_passing_gate": int(report["passes_gate"].sum()),
        "months_survivorship_biased": int(report["survivorship_biased"].sum()),
        "median_coverage": float(report["coverage"].median()),
        "median_coverage_later_delisted": float(report["coverage_later_delisted"].median()),
        "median_coverage_survivors": float(report["coverage_survivors"].median()),
    }
