"""Input normalization for human-friendly percentage and rate inputs."""



def parse_percentage_input(user_input: str, default: float | None = None) -> float:
    """
    Safely convert human percentage input to decimal format.

    Handles both percentage notation (13) and decimal notation (0.13).

    Args:
        user_input: User-provided string (e.g., "13", "0.13", "")
        default: Default value if input is empty (e.g., 0.08 for 8%)

    Returns:
        Decimal percentage (0.13 for 13%)

    Raises:
        ValueError: If input cannot be parsed as a number
    """
    user_input = user_input.strip()

    if not user_input:
        if default is None:
            raise ValueError("No input provided and no default specified")
        return default

    try:
        value = float(user_input)
    except ValueError:
        raise ValueError(f"Cannot parse '{user_input}' as a number")

    if value > 1:
        value /= 100

    return value


def parse_growth_rate(user_input: str, default: float = 0.08) -> float:
    """
    Parse forecast growth rate with human-friendly input handling.

    Examples:
        "13"   → 0.13 (13%)
        "0.13" → 0.13 (13%)
        "8"    → 0.08 (8%)
        ""     → default (8%)

    Args:
        user_input: User input for growth rate
        default: Default growth rate (default 8%)

    Returns:
        Growth rate as decimal (0.08 for 8%)
    """
    return parse_percentage_input(user_input, default=default)


def parse_discount_rate(user_input: str, default: float = 0.09) -> float:
    """
    Parse discount rate (WACC) with human-friendly input handling.

    Args:
        user_input: User input for discount rate
        default: Default discount rate (default 9%)

    Returns:
        Discount rate as decimal (0.09 for 9%)
    """
    return parse_percentage_input(user_input, default=default)


def parse_margin(user_input: str, default: float = 0.15) -> float:
    """
    Parse margin input (e.g., operating margin).

    Args:
        user_input: User input for margin
        default: Default margin (default 15%)

    Returns:
        Margin as decimal (0.15 for 15%)
    """
    return parse_percentage_input(user_input, default=default)
