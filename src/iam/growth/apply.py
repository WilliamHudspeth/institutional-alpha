"""Attach a computed GrowthProfile to a Security's qualitative dictionary.

Populates valuation-specific growth assumptions (DCF near-term rate and 10-year
fade path, relative valuation revenue and EPS growth rates, and market-implied
growth) while preserving any user-supplied DCF growth rate (Damodaran,
*Investment Valuation* ch. 11; Mauboussin, Callahan and Majd, *The Base Rate
Book*, 2016; Chan, Karceski and Lakonishok, "The Level and Persistence of
Growth Rates", JF 2003).
"""

from __future__ import annotations

from typing import Any

from iam.data.security import Security
from iam.growth.profile import build_growth_profile
from iam.growth.types import GrowthProfile


def ensure_growth_profile(
    security: Security,
    market_implied_value: float | None = None,
    engine_result: Any = None,
    risk_free_rate: float | None = None,
    force: bool = False,
    compute_implied: bool = False,
) -> GrowthProfile:
    """Return cached GrowthProfile or build and wire it into `security.qualitative`."""
    q = security.qualitative
    cached = q.get("growth_profile")
    if isinstance(cached, GrowthProfile) and not force:
        return cached

    profile = build_growth_profile(
        security,
        market_implied_value=market_implied_value,
        engine_result=engine_result,
        risk_free_rate=risk_free_rate,
        compute_implied=compute_implied,
    )

    existing_source = q.get("forecast_growth_source")
    has_forecast = "forecast_growth" in q

    if not has_forecast or (
        isinstance(existing_source, str) and existing_source.startswith("growth engine")
    ):
        q["forecast_growth"] = profile.dcf.value
        q["forecast_growth_path"] = list(profile.dcf_path)
        sources_str = ", ".join(profile.dcf.sources) if profile.dcf.sources else "base_rate"
        q["forecast_growth_source"] = f"growth engine (dcf: {sources_str})"
    else:
        if "forecast_growth_source" not in q:
            q["forecast_growth_source"] = "user"

    q["relative_growth_revenue"] = profile.relative_revenue.value
    q["relative_growth_eps"] = profile.relative_eps.value
    q["market_implied_growth"] = profile.expectations.value

    # Damodaran Law 2 reads an explicit reinvestment rate before falling back to 1 - FCF/NI,
    # which reads asset-light firms (FCF above net income) as reinvesting nothing. Hand it the
    # reconciled (capex - D&A + change in working capital) / NOPAT rate when the fundamental
    # estimator had the full reconciliation (no approximation note), never over another value.
    fundamental = profile.estimates.get("fundamental")
    rr = fundamental.inputs.get("reinvestment_rate") if fundamental is not None else None
    reconciled = fundamental is not None and fundamental.ok and not fundamental.notes
    ours = q.get("reinvestment_rate_source") == "growth engine"
    if rr is not None and reconciled and ("reinvestment_rate" not in q or ours):
        q["reinvestment_rate"] = rr
        q["reinvestment_rate_source"] = "growth engine"

    q["growth_profile"] = profile
    return profile
