"""Financial sanity checks and assumption validation."""


# Constants: Financial guardrails
MAX_FORECAST_GROWTH = 0.40  # 40% growth is extremely aggressive
MAX_TERMINAL_GROWTH = 0.05  # Terminal growth should not exceed long-term GDP
MIN_WACC = 0.04  # WACC below 4% is unrealistic
MAX_WACC = 0.25  # WACC above 25% is speculative
MIN_MARGIN = -0.50  # Negative margins are possible but rare
MAX_MARGIN = 0.60  # Margins above 60% are exceptional


def validate_growth_rate(
    growth: float, growth_type: str = "forecast", allow_negative: bool = True
) -> None:
    """
    Validate growth rate assumptions.

    Args:
        growth: Growth rate (decimal, e.g., 0.13 for 13%)
        growth_type: Type of growth ("forecast", "terminal")
        allow_negative: Whether negative growth is allowed

    Raises:
        ValueError: If growth violates constraints
    """
    if growth_type == "forecast":
        max_growth = MAX_FORECAST_GROWTH
        if growth > max_growth:
            raise ValueError(
                f"Forecast growth {growth:.1%} exceeds maximum {max_growth:.1%} "
                "(extremely aggressive assumption)"
            )

    elif growth_type == "terminal":
        max_growth = MAX_TERMINAL_GROWTH
        if growth > max_growth:
            raise ValueError(
                f"Terminal growth {growth:.1%} exceeds maximum {max_growth:.1%} "
                "(unrealistic long-term assumption)"
            )

    if not allow_negative and growth < 0:
        raise ValueError(f"Negative growth {growth:.1%} not allowed for this context")


def validate_discount_rate(wacc: float) -> None:
    """
    Validate WACC (weighted average cost of capital).

    Args:
        wacc: Discount rate (decimal, e.g., 0.09 for 9%)

    Raises:
        ValueError: If WACC violates constraints
    """
    if wacc < MIN_WACC:
        raise ValueError(
            f"WACC {wacc:.1%} is below minimum {MIN_WACC:.1%} (unrealistically low cost of capital)"
        )

    if wacc > MAX_WACC:
        raise ValueError(
            f"WACC {wacc:.1%} exceeds maximum {MAX_WACC:.1%} (extremely high risk assumption)"
        )


def validate_wacc(wacc: float) -> None:
    """Alias for validate_discount_rate."""
    validate_discount_rate(wacc)


def validate_margin(margin: float, margin_type: str = "operating") -> None:
    """
    Validate profit margin assumptions.

    Args:
        margin: Margin (decimal, e.g., 0.25 for 25%)
        margin_type: Type of margin ("operating", "net", "gross")

    Raises:
        ValueError: If margin violates constraints
    """
    if margin < MIN_MARGIN:
        raise ValueError(f"Margin {margin:.1%} is unrealistically low")

    if margin > MAX_MARGIN:
        raise ValueError(
            f"Margin {margin:.1%} exceeds {MAX_MARGIN:.1%} (exceptional but proceed with caution)"
        )


def sanity_check_valuation(
    intrinsic_value: float, market_cap: float, ticker: str = "unknown"
) -> dict:
    """
    Check if valuation output is within plausible bounds.

    Returns:
        Dict with 'passed' (bool), 'ratio' (float), 'warnings' (list)

    Example:
        If intrinsic_value = $10 trillion and market_cap = $100 billion,
        ratio = 100x, which should fail sanity checks.
    """
    if market_cap <= 0:
        return {
            "passed": False,
            "ratio": float("inf"),
            "warnings": ["Market cap invalid or zero"],
        }

    ratio = intrinsic_value / market_cap
    warnings = []
    passed = True

    # Any ratio > 10x is suspicious for mature companies
    if ratio > 10:
        warnings.append(
            f"SUSPICIOUS: {ticker} valuation is {ratio:.1f}x market cap "
            "(verify assumption inputs carefully)"
        )

    # Ratio > 50x almost certainly indicates bad assumptions
    if ratio > 50:
        passed = False
        warnings.append(
            f"EXTREME: {ticker} valuation {ratio:.1f}x market cap "
            "suggests problematic input or assumptions"
        )

    # Trillion+ valuations should trigger hard failure unless justified
    if intrinsic_value > 1e12:
        if market_cap < 1e12:
            passed = False
            warnings.append(
                f"CRITICAL: Valuation of ${intrinsic_value:.2e} exceeds realistic bounds. "
                "This usually indicates an input normalization error (e.g., entering '100' instead of '0.10')"
            )

    return {"passed": passed, "ratio": ratio, "warnings": warnings}


def validate_all_assumptions(
    growth_rate: float,
    terminal_growth: float,
    wacc: float,
    forecast_margin: float | None = None,
) -> list[str]:
    """
    Run comprehensive assumption validation.

    Returns:
        List of warnings (empty if all assumptions valid)
    """
    warnings = []

    try:
        validate_growth_rate(growth_rate, growth_type="forecast")
    except ValueError as e:
        warnings.append(f"Forecast Growth: {e}")

    try:
        validate_growth_rate(terminal_growth, growth_type="terminal")
    except ValueError as e:
        warnings.append(f"Terminal Growth: {e}")

    try:
        validate_discount_rate(wacc)
    except ValueError as e:
        warnings.append(f"WACC: {e}")

    if forecast_margin is not None:
        try:
            validate_margin(forecast_margin)
        except ValueError as e:
            warnings.append(f"Forecast Margin: {e}")

    return warnings
