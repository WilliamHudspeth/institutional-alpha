"""Public API facade for the Institutional Alpha Model (IAM).

This is the only module external code should import. It exposes:
- Security: The immutable input container
- Orchestrator: The valuation engine
- ModelResult: The structured output

All internal modules (data providers, valuation engines, arbitrators) are
wired together here and never accessed directly by users.
"""

from __future__ import annotations

from iam.data import Security
from iam.integration import Orchestrator, ModelResult

__all__ = [
    "Security",
    "Orchestrator",
    "ModelResult",
]

# Convenience: value_security as a module-level function
def value_security(security: Security, damodaran_provider=None) -> dict:
    """Quick entry point: value a security with institutional baselines.

    Args:
        security: Security object with ticker, sector, industry, revenue_mix
        damodaran_provider: Optional custom Damodaran provider (for testing)

    Returns:
        Dict with model_result, risk_profile, and recommendation

    Example:
        >>> from iam.api import Security, value_security
        >>> nvda = Security(
        ...     ticker="NVDA",
        ...     sector="Semiconductors",
        ...     industry="Semiconductors",
        ...     revenue_mix={"US": 0.44, "CN": 0.25, "TW": 0.13, "DE": 0.18},
        ... )
        >>> result = value_security(nvda)
        >>> print(f"Cost of Equity: {result['model_result'].value:.2%}")
    """
    orchestrator = Orchestrator(damodaran_provider=damodaran_provider)
    return orchestrator.value_security(security)
