"""Damodaran beta calculations for the IAM valuation pipeline.

Two betas serve two different purposes:

  Stage 1 (Reverse DCF) — Yahoo's published regression beta.
    This is what the market currently prices.  Using it in the reverse DCF
    answers: "what growth rate does today's price imply, given the market's
    own view of this stock's risk?"

  Stage 3 (Intrinsic DCF) — Damodaran unlever / relever.
    The Yahoo beta is contaminated by the capital structure that existed
    *during the regression window*, not the structure the company carries
    today.  Unlevering strips out that historical debt load, then relevering
    applies the current (market-value) D/E — giving a cost of equity that
    reflects what the business actually owes now.

References: Damodaran, risk.xls and levbeta.xls workbooks.
"""

from __future__ import annotations

from iam.data.security import Security


def unlever_beta(levered_beta: float, debt_to_equity: float, tax_rate: float) -> float:
    """Remove the effect of financial leverage from a beta.

    Damodaran formula:
        Beta_unlevered = Beta_levered / [1 + (1 - tax) * D/E]
    """
    return levered_beta / (1.0 + (1.0 - tax_rate) * debt_to_equity)


def relever_beta(unlevered_beta: float, debt_to_equity: float, tax_rate: float) -> float:
    """Apply a new capital structure to an unlevered beta.

    Damodaran formula:
        Beta_relevered = Beta_unlevered * [1 + (1 - tax) * D/E]
    """
    return unlevered_beta * (1.0 + (1.0 - tax_rate) * debt_to_equity)


def market_value_of_debt(
    book_debt: float,
    interest_expense: float,
    market_rate: float,
    maturity: float,
) -> float:
    """PV of future debt obligations at the current market rate (matches levbeta.xls).

        MVD = interest * annuity_factor + book_debt * discount_factor

    Falls back to book_debt when market_rate or maturity are not positive.
    """
    if market_rate <= 0 or maturity <= 0:
        return book_debt
    discount_factor = (1.0 + market_rate) ** -maturity
    annuity_factor = (1.0 - discount_factor) / market_rate
    return float(interest_expense * annuity_factor + book_debt * discount_factor)


def get_yahoo_beta(security: Security) -> float:
    """Return the raw Yahoo Finance regression beta (Stage 1).

    Checks ``security.market.beta`` first, then falls back to
    ``security.qualitative["beta"]``, then defaults to 1.0.
    """
    if security.market.beta is not None:
        return float(security.market.beta)
    return float(security.qualitative.get("beta", 1.0))


def get_custom_beta_for_intrinsic(security: Security) -> float:
    """Compute the Damodaran unlever / relever beta for Stage 3.

    Steps:
      1. Start with the Yahoo beta (same regression beta as Stage 1).
      2. Unlever using the average D/E from the *beta regression window*
         (``security.qualitative["avg_de_ratio"]``, defaults to 0.0 if absent).
      3. Relever using the *current* market-value D/E, where debt is the PV of
         future obligations at the pre-tax cost of debt.

    Writes the intermediate values back to ``security.qualitative`` for a full
    audit trail:
      - ``beta_unlevered``
      - ``beta_stage3``
      - ``debt_market_value``
      - ``current_de_ratio``

    Qualitative keys consumed (all optional, with stated defaults):
      - ``avg_de_ratio``         — historical D/E during regression window (0.0)
      - ``tax_rate``             — marginal tax rate (0.21)
      - ``pre_tax_cost_debt``    — current pre-tax cost of debt (0.075)
      - ``debt_maturity``        — weighted average debt maturity in years (5.0)
      - ``lease_debt``           — capitalised operating lease liability (0.0)
    """
    q = security.qualitative
    tax_rate = float(q.get("tax_rate", 0.21))
    avg_de = float(q.get("avg_de_ratio", 0.0))

    yahoo_b = get_yahoo_beta(security)
    beta_unlev = unlever_beta(yahoo_b, avg_de, tax_rate)

    # Current market-value debt
    book_debt = float(security.fundamentals.total_debt or 0.0)
    interest = float(security.fundamentals.interest_expense_ttm or 0.0)
    market_rate = float(q.get("pre_tax_cost_debt", 0.075))
    maturity = float(q.get("debt_maturity", 5.0))

    debt_mv = market_value_of_debt(book_debt, interest, market_rate, maturity)
    lease_debt = float(q.get("lease_debt", 0.0))
    total_debt = debt_mv + lease_debt

    equity = float(security.market.market_cap or 1.0)
    current_de = total_debt / equity if equity > 0 else 0.0

    beta_custom = relever_beta(beta_unlev, current_de, tax_rate)

    # Audit trail
    q["beta_unlevered"] = round(beta_unlev, 6)
    q["beta_stage3"] = round(beta_custom, 6)
    q["debt_market_value"] = round(debt_mv, 2)
    q["current_de_ratio"] = round(current_de, 6)

    return beta_custom
