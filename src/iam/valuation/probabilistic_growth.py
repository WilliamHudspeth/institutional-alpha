"""Probabilistic growth estimation engine with regime-aware weighting.

Five independent estimators blended via inverse-variance weighting:
    1. Implied growth   — reverse DCF via Brent's method (two-stage model)
    2. Historical CAGR  — median of 3Y/5Y/10Y lookbacks, winsorized
    3. Sustainable      — ROIC × reinvestment_rate (leverage-neutral)
    4. Bottom-up build  — revenue growth + margin delta + capex efficiency
    5. Sector prior     — Damodaran-anchored baseline

Regime overlays adjust estimator variances:
    - Bubble regime:          inflate implied variance (+0.10)
    - Structural break:       inflate historical and sector variances (+0.10 / +0.05)

Margin trajectory overlays apply haircuts to mean and terminal multiple via a
sigmoid mapping of (slope, acceleration, volatility, peer deviation).

Output: (mean_growth, std_dev) for probabilistic DCF consumption.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

# ---------------------------------------------------------------------------
# Base variances per estimator (tuned for typical financial data quality)
# ---------------------------------------------------------------------------
_BASE_VAR: dict[str, float] = {
    "implied": 0.0025,  # Low when FCF is clean; rises with FCF noise
    "historical": 0.0050,  # Moderate; rises with earnings volatility
    "sustainable": 0.0100,  # ROIC estimation has meaningful uncertainty
    "bottom_up": 0.0050,  # Depends on margin data quality
    "sector": 0.0150,  # Prior only — widest
}

_LAMBDA: float = 1.0  # Regime penalty scale factor


@dataclass
class GrowthEstimate:
    name: str
    value: float  # Annual growth rate
    variance: float  # Estimator variance (lower = more reliable)
    weight: float = 0.0  # Filled by compute_weights()
    notes: str = ""


@dataclass
class GrowthEngineResult:
    mean_growth: float
    std_dev: float
    estimates: list[GrowthEstimate] = field(default_factory=list)
    growth_haircut: float = 0.0  # From margin trajectory
    terminal_haircut: float = 0.0  # From margin trajectory
    margin_trajectory_notes: str = ""
    fade_path: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mean_growth": round(self.mean_growth, 4),
            "std_dev": round(self.std_dev, 4),
            "growth_haircut": round(self.growth_haircut, 4),
            "terminal_haircut": round(self.terminal_haircut, 4),
            "margin_trajectory": self.margin_trajectory_notes,
            "estimates": [
                {
                    "name": e.name,
                    "value": round(e.value, 4),
                    "variance": round(e.variance, 4),
                    "weight": round(e.weight, 4),
                    "notes": e.notes,
                }
                for e in self.estimates
            ],
            "fade_path": [round(g, 4) for g in self.fade_path],
        }


class GrowthEstimatorEngine:
    """Probabilistic growth engine for a single security.

    Args:
        market_cap:          Enterprise value proxy (price × shares, millions)
        free_cash_flow:      Trailing twelve-month FCFF (same currency as market_cap)
        shares_outstanding:  Share count
        net_debt:            Net debt (positive = net debt, negative = net cash)
        wacc:                Weighted-average cost of capital (e.g., 0.09)
        terminal_growth:     Long-run perpetual growth (e.g., 0.025)
        growth_3y:           3-year revenue/FCF CAGR (optional)
        growth_5y:           5-year revenue/FCF CAGR (optional)
        growth_10y:          10-year revenue/FCF CAGR (optional)
        roic:                Return on invested capital (e.g., 0.15)
        reinvestment_rate:   Fraction of NOPAT reinvested (e.g., 0.40)
        revenue_growth_recent: TTM revenue growth rate
        gross_margin_current: Most-recent gross margin
        gross_margin_lag:    Gross margin one year ago
        capex_to_sales:      CapEx / Revenue ratio (reinvestment efficiency proxy)
        sector_growth_prior: Damodaran-anchored sector median growth
        margin_history:      List of quarterly operating margins, recent-first
        peer_margin_avg:     Sector peer average operating margin
        is_bubble_regime:    True when market P/E or EV/Sales far above norms
        is_structural_break: True when business model shift detected
        reliability_errors:  Per-estimator RMSE from recent calibration runs
        moat_durability:     0.0 (no moat) → 1.0 (durable moat)
    """

    def __init__(
        self,
        market_cap: float,
        free_cash_flow: float,
        shares_outstanding: float,
        net_debt: float,
        wacc: float,
        terminal_growth: float = 0.025,
        growth_3y: float | None = None,
        growth_5y: float | None = None,
        growth_10y: float | None = None,
        roic: float | None = None,
        reinvestment_rate: float | None = None,
        revenue_growth_recent: float | None = None,
        gross_margin_current: float | None = None,
        gross_margin_lag: float | None = None,
        capex_to_sales: float | None = None,
        sector_growth_prior: float = 0.06,
        margin_history: list[float] | None = None,
        peer_margin_avg: float | None = None,
        is_bubble_regime: bool = False,
        is_structural_break: bool = False,
        reliability_errors: dict[str, float] | None = None,
        moat_durability: float = 0.7,
    ) -> None:
        self.market_cap = market_cap
        self.free_cash_flow = free_cash_flow
        self.shares_outstanding = shares_outstanding
        self.net_debt = net_debt
        self.wacc = wacc
        self.terminal_growth = terminal_growth
        self.growth_3y = growth_3y
        self.growth_5y = growth_5y
        self.growth_10y = growth_10y
        self.roic = roic
        self.reinvestment_rate = reinvestment_rate
        self.revenue_growth_recent = revenue_growth_recent
        self.gross_margin_current = gross_margin_current
        self.gross_margin_lag = gross_margin_lag
        self.capex_to_sales = capex_to_sales
        self.sector_growth_prior = sector_growth_prior
        self.margin_history = margin_history or []
        self.peer_margin_avg = peer_margin_avg
        self.is_bubble_regime = is_bubble_regime
        self.is_structural_break = is_structural_break
        self.reliability_errors = reliability_errors or {}
        self.moat_durability = max(0.0, min(1.0, moat_durability))

    # ------------------------------------------------------------------
    # Reverse DCF (Brent's method)
    # ------------------------------------------------------------------

    def _dcf_value(self, growth_rate: float, years: int = 10) -> float:
        """Two-stage DCF: PV of explicit FCF path + terminal value.

        Stage 1: FCF grows at `growth_rate` for `years` years.
        Stage 2: Perpetual terminal value at `terminal_growth`.
        Returns equity value (market_cap scale) = PV of FCF stream minus net_debt.
        """
        if self.wacc <= self.terminal_growth:
            return float("inf")

        pv = 0.0
        fcf = self.free_cash_flow
        discount = 1.0
        for t in range(1, years + 1):
            fcf *= 1.0 + growth_rate
            discount /= 1.0 + self.wacc
            pv += fcf * discount

        # Terminal value at end of explicit period
        terminal_fcf = fcf * (1.0 + self.terminal_growth)
        terminal_value = terminal_fcf / (self.wacc - self.terminal_growth)
        pv += terminal_value * discount

        # Equity value = enterprise value - net debt
        equity_value = pv - self.net_debt
        return equity_value

    def implied_growth(self) -> GrowthEstimate | None:
        """Solve for the growth rate that makes DCF equal current market cap.

        Uses Brent's method on the equity value function. Returns None when
        inputs are insufficient or when the solution is not bracketed (e.g.,
        negative FCF).
        """
        if self.free_cash_flow <= 0 or self.market_cap <= 0:
            return None

        target = self.market_cap

        def objective(g: float) -> float:
            return self._dcf_value(g) - target

        # Check that solution is bracketed before calling brentq
        lo, hi = -0.20, 0.50
        try:
            f_lo = objective(lo)
            f_hi = objective(hi)
        except Exception:
            return None

        if f_lo * f_hi > 0:
            # Not bracketed — market cap not achievable within [-20%, +50%]
            # Clamp to nearest bound
            implied_g = lo if abs(f_lo) < abs(f_hi) else hi
        else:
            try:
                implied_g = brentq(objective, lo, hi, xtol=1e-6, maxiter=100)
            except ValueError:
                return None

        implied_g = max(-0.20, min(0.50, implied_g))

        # Variance: higher when far from terminal growth (harder to sustain)
        base_var = _BASE_VAR["implied"]
        distance_penalty = (implied_g - self.terminal_growth) ** 2 * 0.5
        variance = base_var + distance_penalty

        # Bubble regime: market price may embed irrational exuberance
        if self.is_bubble_regime:
            variance += 0.10

        # Reliability error override
        rmse = self.reliability_errors.get("implied", 0.0)
        variance = max(variance, rmse**2)

        return GrowthEstimate(
            name="implied",
            value=implied_g,
            variance=variance,
            notes=f"brentq solve, market_cap={self.market_cap:.0f}",
        )

    # ------------------------------------------------------------------
    # Historical CAGR
    # ------------------------------------------------------------------

    def historical_cagr(self) -> GrowthEstimate | None:
        """Median of available lookback CAGRs after winsorization.

        Uses 3Y, 5Y, 10Y if available. Clips each to [-0.15, 0.40] to
        reduce sensitivity to single anomalous years.
        """
        lookbacks = [self.growth_3y, self.growth_5y, self.growth_10y]
        valid = [g for g in lookbacks if g is not None]
        if not valid:
            return None

        clipped = [float(np.clip(g, -0.15, 0.40)) for g in valid]
        median_g = float(np.median(clipped))
        spread = float(np.std(clipped)) if len(clipped) > 1 else 0.05

        base_var = _BASE_VAR["historical"]
        variance = base_var + spread**2

        # Structural break: historical data less informative
        if self.is_structural_break:
            variance += 0.10

        rmse = self.reliability_errors.get("historical", 0.0)
        variance = max(variance, rmse**2)

        return GrowthEstimate(
            name="historical",
            value=median_g,
            variance=variance,
            notes=f"lookbacks: {[round(g, 3) for g in clipped]}, spread: {spread:.2%}",
        )

    # ------------------------------------------------------------------
    # Sustainable growth (ROIC-based, not ROE-based)
    # ------------------------------------------------------------------

    def sustainable_growth(self) -> GrowthEstimate | None:
        """ROIC × reinvestment_rate — leverage-neutral sustainable growth.

        Avoids the ROE distortion from financial leverage. Critical for
        financials and capital-light businesses.
        """
        if self.roic is None or self.roic <= 0:
            return None
        if self.reinvestment_rate is None:
            return None

        rr = max(0.0, min(1.0, self.reinvestment_rate))
        sustainable_g = self.roic * rr
        sustainable_g = max(-0.10, min(0.40, sustainable_g))

        # Variance: wider when ROIC is high (harder to sustain) or reinvestment uncertain
        base_var = _BASE_VAR["sustainable"]
        roic_penalty = max(0.0, self.roic - 0.20) ** 2  # High ROIC = less certain
        variance = base_var + roic_penalty

        rmse = self.reliability_errors.get("sustainable", 0.0)
        variance = max(variance, rmse**2)

        return GrowthEstimate(
            name="sustainable",
            value=sustainable_g,
            variance=variance,
            notes=f"ROIC: {self.roic:.2%}, reinvestment: {rr:.2%}",
        )

    # ------------------------------------------------------------------
    # Bottom-up build
    # ------------------------------------------------------------------

    def bottom_up_growth(self) -> GrowthEstimate | None:
        """Revenue growth + margin improvement + reinvestment efficiency.

        Formula: g = rev_growth + margin_delta × 0.3 + (efficiency_factor - 1) × 0.1
        where efficiency_factor = 1 / capex_to_sales (lower CapEx/Sales = more efficient).
        """
        if self.revenue_growth_recent is None:
            return None

        g = self.revenue_growth_recent

        # Margin trajectory contribution
        if self.gross_margin_current is not None and self.gross_margin_lag is not None:
            if self.gross_margin_lag > 0:
                margin_delta = self.gross_margin_current - self.gross_margin_lag
                g += margin_delta * 0.3

        # Capital efficiency contribution
        if self.capex_to_sales is not None and self.capex_to_sales > 0:
            efficiency_factor = 1.0 / self.capex_to_sales
            efficiency_factor = max(0.5, min(5.0, efficiency_factor))  # cap
            g += (efficiency_factor - 1.0) * 0.1

        g = max(-0.10, min(0.40, g))

        has_margin = self.gross_margin_current is not None and self.gross_margin_lag is not None
        base_var = _BASE_VAR["bottom_up"]
        variance = base_var if has_margin else base_var * 1.5

        rmse = self.reliability_errors.get("bottom_up", 0.0)
        variance = max(variance, rmse**2)

        return GrowthEstimate(
            name="bottom_up",
            value=g,
            variance=variance,
            notes=f"rev_growth: {self.revenue_growth_recent:.2%}",
        )

    # ------------------------------------------------------------------
    # Sector prior
    # ------------------------------------------------------------------

    def sector_prior(self) -> GrowthEstimate:
        """Damodaran-anchored sector median — always available as prior."""
        base_var = _BASE_VAR["sector"]

        if self.is_structural_break:
            base_var += 0.05

        return GrowthEstimate(
            name="sector",
            value=self.sector_growth_prior,
            variance=base_var,
            notes=f"sector prior: {self.sector_growth_prior:.2%}",
        )

    # ------------------------------------------------------------------
    # Margin trajectory haircuts
    # ------------------------------------------------------------------

    def margin_penalty_factors(self) -> tuple[float, float]:
        """Compute (growth_haircut, terminal_multiple_haircut) from margin signals.

        Analyses four signals: slope, acceleration, volatility, peer deviation.
        Each maps to a severity score in [0, 1]; the composite score passes
        through a sigmoid to produce a haircut in [0.0, 0.5] for growth and
        [0.0, 0.3] for the terminal multiple.

        Returns:
            growth_haircut:   Multiplicative factor in [0.5, 1.0]. Values < 1.0
                              mean growth is penalized.
            terminal_haircut: Multiplicative factor in [0.7, 1.0].
        """
        if not self.margin_history or len(self.margin_history) < 2:
            return 1.0, 1.0

        clean = [m for m in self.margin_history if m is not None]
        if len(clean) < 2:
            return 1.0, 1.0

        margin_array = np.array(clean, dtype=float)
        current = margin_array[0]
        n = len(margin_array)

        # Signal 1: slope (linear trend over available history)
        t = np.arange(n)
        if n >= 2:
            slope = float(np.polyfit(t, margin_array[::-1], 1)[0])  # ascending time
        else:
            slope = 0.0

        # Signal 2: acceleration (change in slope — second derivative proxy)
        if n >= 4:
            recent_slope = float(np.mean(np.diff(margin_array[:4][::-1])))
            older_slope = float(np.mean(np.diff(margin_array[n // 2 :][::-1]))) if n > 4 else 0.0
            acceleration = recent_slope - older_slope
        else:
            acceleration = 0.0

        # Signal 3: volatility (std dev of quarterly margins)
        volatility = float(np.std(margin_array)) if n >= 3 else 0.0

        # Signal 4: peer deviation (how far below peer average)
        peer_deviation = 0.0
        if self.peer_margin_avg is not None:
            peer_deviation = self.peer_margin_avg - current  # positive = below peers

        # Severity score: weighted composite
        slope_severity = max(0.0, -slope / 0.02)  # Negative slope is bad
        accel_severity = max(0.0, -acceleration / 0.01)  # Negative acceleration (worsening)
        vol_severity = min(1.0, volatility / 0.05)  # High volatility = uncertain
        peer_severity = max(0.0, peer_deviation / 0.05)  # Below-peer margin

        composite = (
            0.35 * slope_severity
            + 0.25 * accel_severity
            + 0.20 * vol_severity
            + 0.20 * peer_severity
        )
        composite = min(1.0, composite)

        # Sigmoid mapping to haircut
        def sigmoid_haircut(severity: float, max_haircut: float) -> float:
            # Sigmoid: 0 severity → 0 haircut, 1 severity → max_haircut
            x = (severity - 0.5) * 6.0
            s = 1.0 / (1.0 + math.exp(-x))
            return max_haircut * s

        growth_penalty = sigmoid_haircut(composite, 0.50)  # Up to 50% growth haircut
        terminal_penalty = sigmoid_haircut(composite, 0.30)  # Up to 30% terminal haircut

        growth_haircut = max(0.5, 1.0 - growth_penalty)
        terminal_haircut = max(0.7, 1.0 - terminal_penalty)

        notes_parts = [
            f"slope: {slope:+.4f}",
            f"accel: {acceleration:+.4f}",
            f"vol: {volatility:.4f}",
            f"peer_dev: {peer_deviation:+.4f}",
            f"composite: {composite:.3f}",
        ]
        self._margin_notes = ", ".join(notes_parts)

        return growth_haircut, terminal_haircut

    # ------------------------------------------------------------------
    # Inverse-variance weighting
    # ------------------------------------------------------------------

    def compute_weights(self, estimates: list[GrowthEstimate]) -> list[GrowthEstimate]:
        """Assign inverse-variance weights and normalize.

        w_i = 1 / (variance_i + lambda * regime_penalty_i)
        Regime penalties are already baked into each estimate's variance
        during construction, so this step simply normalizes.
        """
        total_w = sum(1.0 / e.variance for e in estimates if e.variance > 0)
        if total_w <= 0:
            for e in estimates:
                e.weight = 1.0 / len(estimates)
            return estimates

        for e in estimates:
            e.weight = (1.0 / e.variance) / total_w if e.variance > 0 else 0.0

        return estimates

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def blended_growth(self) -> GrowthEngineResult:
        """Compute blended (mean, std_dev) growth estimate.

        Steps:
            1. Collect all available estimators
            2. Assign inverse-variance weights
            3. Compute weighted mean and propagated std_dev
            4. Apply margin trajectory growth haircut
            5. Return GrowthEngineResult with full audit trail
        """
        # Collect raw estimates
        raw_estimates: list[GrowthEstimate] = []
        for est in [
            self.implied_growth(),
            self.historical_cagr(),
            self.sustainable_growth(),
            self.bottom_up_growth(),
            self.sector_prior(),
        ]:
            if est is not None:
                raw_estimates.append(est)

        if not raw_estimates:
            return GrowthEngineResult(
                mean_growth=self.terminal_growth,
                std_dev=0.05,
                estimates=[],
                fade_path=self.growth_persistence_profile(self.terminal_growth),
            )

        # Weight and normalize
        estimates = self.compute_weights(raw_estimates)

        # Weighted mean
        mean_g = sum(e.value * e.weight for e in estimates)

        # Propagated std_dev: weighted variance + inter-estimator disagreement
        weighted_var = sum(e.weight * e.variance for e in estimates)
        values = np.array([e.value for e in estimates])
        weights = np.array([e.weight for e in estimates])
        inter_disagreement = float(np.average((values - mean_g) ** 2, weights=weights))
        total_var = weighted_var + inter_disagreement
        std_dev = math.sqrt(max(0.0001, total_var))

        # Margin trajectory haircut
        growth_haircut, terminal_haircut = self.margin_penalty_factors()
        margin_notes = getattr(self, "_margin_notes", "")

        # Apply multiplicative haircut to mean (haircut in [0.5, 1.0])
        adjusted_mean = mean_g * growth_haircut

        # Constrain to plausible range
        adjusted_mean = max(-0.15, min(0.50, adjusted_mean))

        # Fade path from adjusted mean
        fade = self.growth_persistence_profile(adjusted_mean)

        return GrowthEngineResult(
            mean_growth=adjusted_mean,
            std_dev=std_dev,
            estimates=estimates,
            growth_haircut=growth_haircut,
            terminal_haircut=terminal_haircut,
            margin_trajectory_notes=margin_notes,
            fade_path=fade,
        )

    # ------------------------------------------------------------------
    # Growth persistence profile
    # ------------------------------------------------------------------

    def growth_persistence_profile(self, base_growth: float, years: int = 10) -> list[float]:
        """Exponential decay from base_growth toward terminal_growth.

        decay_speed = 1.0 - moat_durability
        High moat durability → slow decay → growth persists longer.

        g_t = terminal_g + (base_g - terminal_g) × exp(-decay × t)
        """
        decay_factor = 1.0 - self.moat_durability  # 0 (no decay) → 1 (fast decay)
        path = []
        for t in range(1, years + 1):
            g_t = self.terminal_growth + (base_growth - self.terminal_growth) * math.exp(
                -decay_factor * t * 0.5
            )
            path.append(round(g_t, 6))
        return path


# ---------------------------------------------------------------------------
# Factory: build engine from Security object
# ---------------------------------------------------------------------------


def build_engine_from_security(
    security,
    sector_growth_table: dict[str, float] | None = None,
    is_bubble_regime: bool = False,
    is_structural_break: bool = False,
    moat_durability: float = 0.7,
    reliability_errors: dict[str, float] | None = None,
) -> GrowthEstimatorEngine:
    """Construct a GrowthEstimatorEngine from a Security object.

    Pulls all available data from security.fundamentals and security.market.
    Computes CAGR lookbacks from revenue/FCF history before constructing.

    Args:
        security: Security with fundamentals and market data
        sector_growth_table: Optional sector growth overrides
        is_bubble_regime: Pass True during known market bubbles
        is_structural_break: Pass True when business model has shifted
        moat_durability: 0.0–1.0 moat persistence score
        reliability_errors: Per-estimator RMSE calibration overrides

    Returns:
        GrowthEstimatorEngine ready to call .blended_growth()
    """
    f = security.fundamentals
    m = security.market
    sector = security.sector or "Technology"

    # Market cap proxy: price × shares (or fallback)
    price = m.price if m else None
    shares = f.shares_outstanding or 1.0
    market_cap = (price * shares) if price else 0.0

    # Net debt (positive = debt-heavy)
    net_debt = getattr(f, "net_debt", 0.0) or 0.0

    # FCF
    fcf_ttm = f.fcf_ttm or 0.0

    # Historical CAGRs from FCF history (preferred) or revenue history
    hist = f.fcf_history if f.fcf_history and len(f.fcf_history) >= 3 else f.revenue_history

    def _cagr(series: list[float] | None, n: int) -> float | None:
        if not series or len(series) <= n:
            return None
        clean = [x for x in series if x is not None and x > 0]
        if len(clean) <= n:
            return None
        end, start = float(clean[0]), float(clean[n])
        if start <= 0:
            return None
        return float((end / start) ** (1.0 / n) - 1.0)

    growth_3y = _cagr(hist, 3)
    growth_5y = _cagr(hist, 5)
    growth_10y = _cagr(hist, 10)

    # Revenue growth TTM (YoY)
    rev_hist = f.revenue_history or []
    rev_growth_recent = None
    if len(rev_hist) >= 2 and rev_hist[1] and rev_hist[1] > 0:
        rev_growth_recent = rev_hist[0] / rev_hist[1] - 1.0

    # ROIC and reinvestment rate
    roic_hist = f.roic_history or []
    roic = (
        float(np.mean([r for r in roic_hist[:3] if r is not None and r > 0])) if roic_hist else None
    )
    if roic is None:
        roic = f.incremental_roic

    # Reinvestment rate: 1 - payout_ratio (default assume 40% payout)
    reinvestment_rate = getattr(f, "reinvestment_rate", None) or 0.60

    # Margin data
    op_hist = f.operating_margin_history or []
    margin_history = op_hist[:12]  # Use up to 12 quarters/years

    # Sector prior
    default_sector_table = {
        "Technology": 0.12,
        "Healthcare": 0.08,
        "Financials": 0.05,
        "Consumer": 0.05,
        "Consumer Discretionary": 0.06,
        "Consumer Staples": 0.04,
        "Industrials": 0.05,
        "Utilities": 0.03,
        "Energy": 0.04,
        "Materials": 0.04,
        "Real Estate": 0.04,
        "Communication Services": 0.07,
    }
    table = sector_growth_table or default_sector_table
    sector_prior = table.get(sector, 0.06)

    return GrowthEstimatorEngine(
        market_cap=market_cap,
        free_cash_flow=fcf_ttm,
        shares_outstanding=shares,
        net_debt=net_debt,
        wacc=0.09,
        terminal_growth=0.025,
        growth_3y=growth_3y,
        growth_5y=growth_5y,
        growth_10y=growth_10y,
        roic=roic,
        reinvestment_rate=reinvestment_rate,
        revenue_growth_recent=rev_growth_recent,
        gross_margin_current=f.operating_margin,
        gross_margin_lag=op_hist[1] if len(op_hist) >= 2 else None,
        capex_to_sales=None,  # Not in current Fundamentals schema
        sector_growth_prior=sector_prior,
        margin_history=margin_history,
        peer_margin_avg=None,  # Could be fed from a peer table
        is_bubble_regime=is_bubble_regime,
        is_structural_break=is_structural_break,
        reliability_errors=reliability_errors or {},
        moat_durability=moat_durability,
    )
