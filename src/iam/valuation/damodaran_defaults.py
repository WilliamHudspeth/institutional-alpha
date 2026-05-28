from dataclasses import dataclass

COUNTRY_ERPS = {
    "Abu Dhabi": 0.0487,
    "Albania": 0.0889,
    "Algeria": 0.1006,
    "Andorra (Principality of)": 0.063,
    "Angola": 0.1264,
    "Argentina": 0.1394,
    "Armenia": 0.0889,
    "Aruba": 0.0708,
    "Australia": 0.0423,
    "Austria": 0.0459,
    "Azerbaijan": 0.0708,
    "Bahamas": 0.1006,
    "Bahrain": 0.1135,
    "Bangladesh": 0.1135,
    "Barbados": 0.1135,
    "Belarus": 0.3089,
    "Belgium": 0.0501,
    "Belize": 0.1394,
    "Benin": 0.1006,
    "Bermuda": 0.0533,
    "Bolivia": 0.1977,
    "Bosnia and Herzegovina": 0.1264,
    "Botswana": 0.063,
    "Brazil": 0.0747,
    "Brunei": 0.0501,
    "Bulgaria": 0.063,
    "Burkina Faso": 0.1394,
    "Cambodia": 0.1135,
    "Cameroon": 0.1394,
    "Canada": 0.0423,
    "Cape Verde": 0.1135,
    "Cayman Islands": 0.0501,
    "Chile": 0.0533,
    "China": 0.0514,
    "Colombia": 0.0708,
    "Congo (Democratic Republic of)": 0.1264,
    "Congo (Republic of)": 0.1589,
    "Cook Islands": 0.1006,
    "Costa Rica": 0.0813,
    "Croatia": 0.0578,
    "Cuba": 0.1977,
    "Curacao": 0.0708,
    "Cyprus": 0.0578,
    "Czech Republic": 0.0501,
    "Côte d'Ivoire": 0.0813,
    "Denmark": 0.0423,
    "Dominican Republic": 0.0813,
    "Ecuador": 0.1718,
    "Egypt": 0.1394,
    "El Salvador": 0.1264,
    "Estonia": 0.0514,
    "Ethiopia": 0.1589,
    "Fiji": 0.1006,
    "Finland": 0.0459,
    "France": 0.0501,
    "Gabon": 0.1589,
    "Gambia": 0.1135,
    "Georgia": 0.0813,
    "Germany": 0.0423,
    "Ghana": 0.1394,
    "Greece": 0.0708,
    "Guatemala": 0.0747,
    "Guernsey (States of)": 0.0514,
    "Guinea": 0.1589,
    "Guinea-Bissau": 0.1394,
    "Guyana": 0.063,
    "Haiti": 0.1718,
    "Honduras": 0.1006,
    "Hong Kong": 0.0501,
    "Hungary": 0.0669,
    "Iceland": 0.0514,
    "India": 0.0708,
    "Indonesia": 0.0669,
    "Iran": 0.1394,
    "Iraq": 0.1394,
    "Ireland": 0.0501,
    "Isle of Man": 0.0501,
    "Israel": 0.063,
    "Italy": 0.0669,
    "Jamaica": 0.0889,
    "Japan": 0.0514,
    "Jersey (States of)": 0.0501,
    "Jordan": 0.0889,
    "Kazakhstan": 0.063,
    "Kenya": 0.1394,
    "Korea": 0.0487,
    "Korea, D.P.R.": 0.1977,
    "Kuwait": 0.0514,
    "Kyrgyzstan": 0.1264,
    "Laos": 0.1589,
    "Latvia": 0.0578,
    "Lebanon": 0.3089,
    "Liberia": 0.1589,
    "Libya": 0.0813,
    "Liechtenstein": 0.0423,
    "Lithuania": 0.0533,
    "Luxembourg": 0.0423,
    "Macao": 0.0501,
    "Macedonia": 0.0889,
    "Madagascar": 0.1264,
    "Malawi": 0.1718,
    "Malaysia": 0.0578,
    "Maldives": 0.1589,
    "Mali": 0.1589,
    "Malta": 0.0533,
    "Mauritius": 0.0708,
    "Mexico": 0.0669,
    "Moldova": 0.1264,
    "Mongolia": 0.1006,
    "Montenegro": 0.1006,
    "Montserrat": 0.0708,
    "Morocco": 0.0747,
    "Mozambique": 0.1718,
    "Myanmar": 0.1977,
    "Namibia": 0.1006,
    "Nepal": 0.0889,
    "Netherlands": 0.0423,
    "New Zealand": 0.0423,
    "Nicaragua": 0.1135,
    "Niger": 0.1718,
    "Nigeria": 0.1264,
    "Norway": 0.0423,
    "Oman": 0.0708,
    "Pakistan": 0.1394,
    "Panama": 0.0708,
    "Papua New Guinea": 0.1135,
    "Paraguay": 0.0708,
    "Peru": 0.063,
    "Philippines": 0.0669,
    "Poland": 0.0533,
    "Portugal": 0.0578,
    "Qatar": 0.0487,
    "Ras Al Khaimah (Emirate of)": 0.0578,
    "Romania": 0.0708,
    "Russia": 0.0813,
    "Rwanda": 0.1135,
    "Saudi Arabia": 0.0501,
    "Senegal": 0.1394,
    "Serbia": 0.0813,
    "Sharjah": 0.0747,
    "Sierra Leone": 0.1264,
    "Singapore": 0.0423,
    "Slovakia": 0.0578,
    "Slovenia": 0.0578,
    "Solomon Islands": 0.1394,
    "Somalia": 0.1718,
    "South Africa": 0.0813,
    "Spain": 0.0578,
    "Sri Lanka": 0.1977,
    "St. Maarten": 0.0813,
    "St. Vincent & the Grenadines": 0.1264,
    "Sudan": 0.3089,
    "Suriname": 0.1394,
    "Swaziland": 0.1135,
    "Sweden": 0.0423,
    "Switzerland": 0.0423,
    "Syria": 0.1977,
    "Taiwan": 0.0501,
    "Tajikistan": 0.1264,
    "Tanzania": 0.1006,
    "Thailand": 0.063,
    "Togo": 0.1264,
    "Trinidad and Tobago": 0.0813,
    "Tunisia": 0.1394,
    "Turkey (updated February 2026)": 0.0889,
    "Turks and Caicos Islands": 0.063,
    "Uganda": 0.1264,
    "Ukraine": 0.1977,
    "United Arab Emirates": 0.0487,
    "United Kingdom": 0.0501,
    "United States": 0.0446,
    "Uruguay": 0.063,
    "Uzbekistan": 0.0889,
    "Venezuela": 0.3089,
    "Vietnam": 0.0813,
    "Yemen, Republic": 0.1977,
    "Zambia": 0.1589,
    "Zimbabwe": 0.1589,
}

from dataclasses import field


@dataclass
class CompanyProfile:
    ticker: str
    sector: str  # exact Damodaran sector name, Jan 2026
    revenue_mix: dict[str, float]  # region -> weight, e.g. {"Americas":0.642, "EMEA":0.302}
    d_to_e: float = 0.0  # market D/E for Hamada
    tax_rate: float = 0.21
    rf: float = 0.0430  # analysis-date risk-free rate

    def normalized_mix(self) -> dict[str, float]:
        total = sum(self.revenue_mix.values())
        if total == 0:
            raise ValueError("revenue_mix sums to zero")
        # tolerate rounding, always normalize to 1.0
        return {k: v / total for k, v in self.revenue_mix.items()}


@dataclass
class DamodaranUniverse:
    us_erp: float  # Damodaran US ERP, decimal
    region_erps: dict[str, float]  # region -> ERP
    sector_beta_u: dict[str, float]  # sector -> unlevered beta

    # NEW: Store sector median multiples
    sector_multiples: dict[str, dict[str, float]] = field(default_factory=dict)


# Damodaran Synthetic Rating Spreads (Large Cap, Non-Financial) based on Interest Coverage Ratio (EBIT / Interest)
SYNTHETIC_RATING_SPREADS = [
    (8.50, 0.0069, "AAA/Aaa"),
    (6.50, 0.0085, "AA/Aa2"),
    (5.50, 0.0107, "A+/A1"),
    (4.25, 0.0118, "A/A2"),
    (3.00, 0.0133, "A-/A3"),
    (2.50, 0.0171, "BBB/Baa2"),
    (2.25, 0.0231, "BB+/Ba1"),
    (2.00, 0.0277, "BB/Ba2"),
    (1.75, 0.0405, "B+/B1"),
    (1.50, 0.0486, "B/B2"),
    (1.25, 0.0594, "B-/B3"),
    (0.80, 0.0946, "CCC/Caa"),
    (0.65, 0.1335, "CC/Ca"),
    (0.20, 0.1754, "C/C"),
    (-100000.0, 0.2000, "D/D"),  # Fallback for negative/abysmal coverage
]


def build_geographic_erp(profile: CompanyProfile, uni: DamodaranUniverse) -> float:
    """Revenue-weighted ERP. Missing region falls back to US ERP."""
    mix = profile.normalized_mix()
    total = 0.0
    for region, weight in mix.items():
        erp = uni.region_erps.get(region, uni.us_erp)
        total += weight * erp
    return round(total, 4)


def get_unlevered_beta(profile: CompanyProfile, uni: DamodaranUniverse) -> float:
    try:
        return uni.sector_beta_u[profile.sector]
    except KeyError:
        raise KeyError(f"Sector '{profile.sector}' not found in beta table")


def lever_beta(beta_u: float, d_to_e: float, tax_rate: float) -> float:
    # Hamada: beta_l = beta_u * [1 + (1 - tax) * D/E]
    return beta_u * (1 + (1 - tax_rate) * d_to_e)


def cost_of_equity(rf: float, beta_l: float, erp: float) -> float:
    return rf + beta_l * erp


def cap_terminal_growth(g: float, rf: float) -> float:
    # Enforce g_terminal <= rf
    return g if g <= rf else rf


def get_synthetic_spread(ebit: float, interest_expense: float) -> tuple[float, str]:
    """Calculates synthetic debt spread and rating based on Interest Coverage Ratio."""
    if interest_expense <= 0:
        return SYNTHETIC_RATING_SPREADS[0][1], SYNTHETIC_RATING_SPREADS[0][2]  # AAA if no interest

    icr = ebit / interest_expense
    for threshold, spread, rating in SYNTHETIC_RATING_SPREADS:
        if icr > threshold:
            return spread, rating
    return SYNTHETIC_RATING_SPREADS[-1][1], SYNTHETIC_RATING_SPREADS[-1][2]


def build_wacc(
    ke: float, ebit: float, interest_expense: float, rf: float, d_to_e: float, tax_rate: float
) -> dict:
    """Calculates firm-specific WACC using synthetic debt ratings."""
    spread, rating = get_synthetic_spread(ebit, interest_expense)
    cost_of_debt = rf + spread
    after_tax_kd = cost_of_debt * (1 - tax_rate)

    weight_debt = d_to_e / (1 + d_to_e)
    weight_equity = 1 / (1 + d_to_e)

    wacc = (ke * weight_equity) + (after_tax_kd * weight_debt)
    return {
        "wacc": wacc,
        "cost_of_equity": ke,
        "cost_of_debt": cost_of_debt,
        "rating": rating,
        "spread": spread,
    }


def build_ke_for_company(profile: CompanyProfile, uni: DamodaranUniverse) -> dict:
    erp = build_geographic_erp(profile, uni)
    beta_u = get_unlevered_beta(profile, uni)
    beta_l = lever_beta(beta_u, profile.d_to_e, profile.tax_rate)
    ke = cost_of_equity(profile.rf, beta_l, erp)
    return {
        "ticker": profile.ticker,
        "geo_erp": erp,
        "beta_u": round(beta_u, 4),
        "beta_l": round(beta_l, 4),
        "ke": round(ke, 4),
        "rf": profile.rf,
    }


if __name__ == "__main__":
    uni = DamodaranUniverse(
        us_erp=0.0503,
        region_erps={"Americas": 0.0503, "EMEA": 0.0590, "APAC": 0.0620},
        sector_beta_u={
            "Investments & Asset Management": 0.59,  # n=283, Jan 2026
            "Software (System & Application)": 0.95,
            "Semiconductors": 1.18,
        },
    )

    blk = CompanyProfile(
        ticker="BLK",
        sector="Investments & Asset Management",
        revenue_mix={"Americas": 0.642, "EMEA": 0.302, "APAC": 0.056},
        d_to_e=0.15,
    )

    nvda = CompanyProfile(
        ticker="NVDA",
        sector="Semiconductors",
        revenue_mix={"Americas": 0.44, "EMEA": 0.18, "APAC": 0.38},
        d_to_e=0.05,
    )

    print(build_ke_for_company(blk, uni))
    # {'ticker': 'BLK', 'geo_erp': 0.054, 'beta_u': 0.59, 'beta_l': 0.6599, 'ke': 0.0786, 'rf': 0.043}

    print(build_ke_for_company(nvda, uni))
    # {'ticker': 'NVDA', 'geo_erp': 0.0559, 'beta_u': 1.18, 'beta_l': 1.239, 'ke': 0.1123, 'rf': 0.043}
