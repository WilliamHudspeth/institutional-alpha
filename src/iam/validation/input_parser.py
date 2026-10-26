"""Input normalization for human-friendly percentage and rate inputs."""


def parse_percentage_input(user_input: str, default: float | None = None) -> float:
    """
    Safely convert human percentage input to decimal format.

    Handles both percentage notation (13) and decimal notation (0.13). A value with a "%"
    sign, or of magnitude 1 or more, is a percentage: "1" is 1%, "-5" is -5%, "1.5%" is 1.5%.
    A value below 1 in magnitude without "%" is a decimal: "0.13" is 13%.

    Args:
        user_input: User-provided string (e.g., "13", "0.13", "-5", "1.5%", "")
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

    is_percent = user_input.endswith("%")
    number = user_input[:-1].strip() if is_percent else user_input
    try:
        value = float(number)
    except ValueError:
        raise ValueError(f"Cannot parse '{user_input}' as a number")

    # "1" used to read as 100% and "-5" as -500% (only values above 1 were divided).
    if is_percent or abs(value) >= 1:
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
