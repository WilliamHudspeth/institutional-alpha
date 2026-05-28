"""
concept_library_expanded.py – Detailed explanations, examples, and references for all institutional finance concepts.

Includes extended definitions, concrete examples, common pitfalls, academic references, and code locations.
"""

EXPANDED_CONCEPTS = {
    "Information Coefficient (IC)": {
        "extended": (
            "The Information Coefficient measures the cross‑sectional correlation between a factor score "
            "(e.g., a composite of value, quality, momentum) and the subsequent return of a stock. "
            "Unlike simple correlation, the IC typically uses Spearman's rank correlation, which tests whether "
            "higher‑ranked scores correspond to higher‑ranked returns, ignoring outliers.\n\n"
            "A positive IC of 0.05 means that, on average, a stock with a factor score one rank higher outperforms "
            "a stock one rank lower by approximately 5 basis points per month. The IC is the raw signal of predictive power, "
            "before accounting for transaction costs, liquidity, or volatility."
        ),
        "example": (
            "Suppose you rank 100 stocks by their P/E ratio (lowest P/E gets rank 1, highest gets rank 100). "
            "You also rank them by forward 1‑month return (highest return gets rank 1). "
            "If the Spearman rank correlation between the two rankings is 0.08, your IC is 0.08. "
            "That means low‑P/E stocks modestly outperform high‑P/E stocks in the next month on average."
        ),
        "pitfall": (
            "IC ignores transaction costs, liquidity, and volatility of the signal. "
            "A high IC that is highly volatile (low ICIR) can be useless in practice because the signal "
            "works only sporadically. Also, IC is measured on a long‑only or long‑short basis; "
            "a long‑only portfolio of the top decile may still lose money in a bear market even if IC is positive. "
            "Always check ICIR and IC decay across horizons before deploying a factor."
        ),
        "reference": (
            "Grinold, R. & Kahn, R. (2000). 'Active Portfolio Management' – defines IC as the cornerstone of the "
            "fundamental law of active management. CFA Level III curriculum covers IC as part of factor analysis."
        ),
        "code_ref": "src/iam/backtest/metrics.py: ic_spearman() → uses scipy.stats.spearmanr(score_ranks, return_ranks)"
    },
    "IC Information Ratio (ICIR)": {
        "extended": (
            "ICIR is the Information Coefficient scaled by its own volatility. It measures the consistency and reliability of the signal. "
            "ICIR = mean(IC) / std(IC). A high IC that appears only in a few months (high volatility) yields a low ICIR, "
            "indicating the signal is unreliable and data-dependent. A low but consistent IC is often preferable.\n\n"
            "ICIR above 0.5 is generally considered good; above 1.0 is excellent (very consistent signal). "
            "ICIR is used to rank factors before including them in a multi‑factor model and to allocate capital to factors."
        ),
        "example": (
            "Factor A has monthly ICs over 48 months: [0.06, 0.05, 0.07, 0.04, 0.055, ...] → mean=0.055, std=0.0128 → ICIR=4.3 (excellent, very consistent).\n"
            "Factor B has monthly ICs: [0.12, -0.03, 0.08, -0.05, 0.01, ...] → mean=0.03, std=0.08 → ICIR=0.375 (poor, highly inconsistent). "
            "Factor A is preferable even though it has a lower mean IC."
        ),
        "pitfall": (
            "ICIR can be artificially inflated by taking too short a measurement period (e.g., one month of data) "
            "or by using a volatile but high‑mean IC that occurs by chance. Always compute ICIR over a multi‑year rolling window (ideally 5+ years). "
            "Also, ICIR itself is noisy; compute it with Newey‑West confidence intervals."
        ),
        "reference": (
            "Grinold & Kahn (2000). Also Damodaran's lectures on factor performance and robustness. "
            "CFA curriculum on performance evaluation and information ratio."
        ),
        "code_ref": "src/iam/backtest/metrics.py: compute_statistics() → icir = mean_ic / std_ic with Newey-West t-stat"
    },
    "Newey‑West HAC Standard Errors": {
        "extended": (
            "In time‑series regressions, errors are often correlated (autocorrelation) and have changing variance "
            "(heteroskedasticity). Ordinary least squares standard errors become too small, leading to false statistical significance. "
            "The Newey‑West estimator produces consistent standard errors by incorporating autocorrelation up to a chosen lag.\n\n"
            "It is the gold standard for any time‑series backtest where overlapping horizons (e.g., 12‑month returns) are used, "
            "because overlapping observations are inherently autocorrelated."
        ),
        "example": (
            "If you regress monthly IC against a constant to test if the mean IC is different from zero using OLS, "
            "ordinary t‑statistic might be 2.5 (significant at 5%). After applying Newey‑West with 6 lags (for 6‑month correlation), "
            "the t‑statistic may drop to 1.6 (not significant). The Newey‑West adjustment reveals that the IC is not as significant as naive tests suggest."
        ),
        "pitfall": (
            "Choosing too few lags underestimates autocorrelation; too many lags over‑corrects and adds noise. "
            "A rule of thumb: lags = floor(4*(n/100)^(2/9)), which is used by statsmodels by default. "
            "Always report both OLS and Newey‑West t‑stats side by side."
        ),
        "reference": (
            "Newey, W. & West, K. (1987). 'A Simple, Positive Semi‑Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix.' "
            "Econometrica 55, 703-708."
        ),
        "code_ref": "src/iam/backtest/metrics.py: compute_statistics() → uses statsmodels.stats.sandwich_covariance.cov_hac()"
    },
    "Walk‑Forward Optimization": {
        "extended": (
            "Traditional backtesting optimises weights on the entire historical dataset, then tests on the same data – "
            "this is severe overfitting. Walk‑forward splits the timeline into a rolling training window (e.g., 5 years) "
            "and a subsequent out‑of‑sample test window (e.g., 1 year).\n\n"
            "The optimal weights from the training window are applied to the test window without re‑optimisation, and the process rolls forward by one year. "
            "The average test‑window performance is a true measure of robustness and forward‑looking signal quality."
        ),
        "example": (
            "For monthly data from 2010‑2025 (192 months):\n"
            "Window 1: train Jan 2010–Dec 2014 (60 months) → optimize weights → test Jan–Dec 2015\n"
            "Window 2: train Jan 2011–Dec 2015 (60 months) → optimize weights → test Jan–Dec 2016\n"
            "...\n"
            "Window 10: train Jan 2020–Dec 2024 (60 months) → optimize weights → test Jan–Dec 2025\n"
            "Final performance = average IC (or Sharpe, return) across all 10 test windows."
        ),
        "pitfall": (
            "Walk‑forward still requires careful choice of window lengths. Too short a training window (e.g., 12 months) leads to unstable and noisy weights; "
            "too long a training window (e.g., 10+ years) may not adapt to regime changes. Use the longest training period that still captures recent regimes, "
            "typically 3–5 years. Also, ensure no look‑ahead bias: the optimisation at time t should only use data up to time t."
        ),
        "reference": (
            "Pardo, R. (2008). 'The Evaluation and Optimization of Trading Strategies.' Wiley. "
            "Arnott, R., et al. (2016). 'How Can 'Smart Beta' Go Horribly Wrong?' discusses overfitting risks."
        ),
        "code_ref": "src/iam/backtest/weight_optimizer.py: WalkForwardOptimizer.run() – rolling window with no look‑ahead"
    },
    "Multi‑Horizon IC": {
        "extended": (
            "A factor may predict returns at different time horizons (1 month, 3 months, 6 months, 12 months, etc.). "
            "Plotting IC against horizon shows how quickly the signal decays and reveals the nature of the factor. "
            "Fast decay (IC halves after 3 months) suggests the factor is capturing very short‑term anomalies (momentum, microstructure); "
            "slow decay (IC still strongly positive after 12 months) indicates a structural factor like value or quality."
        ),
        "example": (
            "Factor IC across horizons:\n"
            "Value factor: 1m IC = 0.03, 3m IC = 0.035, 6m IC = 0.032, 12m IC = 0.028 (slow decay, structural).\n"
            "Momentum factor: 1m IC = 0.06, 3m IC = 0.02, 6m IC = 0.001, 12m IC = -0.01 (fast decay, mean-reversion)."
        ),
        "pitfall": (
            "Long‑horizon IC uses overlapping returns, which introduces autocorrelation. "
            "For example, 12‑month returns on daily data overlap 11 times. Use Newey‑West standard errors to test significance. "
            "Also, 12‑month IC computed on daily data is less reliable than 12‑month IC on monthly data because the effective sample size is lower."
        ),
        "reference": (
            "Grinold & Kahn (2000) – Chapter on 'The Information Horizon.' "
            "Mclean, R. & Pontiff, J. (2016). 'Does Academic Research Destroy Stock Return Predictability?' studies decay in anomaly strength."
        ),
        "code_ref": "src/iam/backtest/runner.py: discovers fwd_ret_21d, fwd_ret_63d, fwd_ret_126d, fwd_ret_252d columns and computes IC for each"
    },
    "Value‑Weighted IC": {
        "extended": (
            "Standard IC treats all stocks equally in the rank correlation calculation. Value‑weighted IC weights each stock's contribution by its market capitalisation. "
            "This is more relevant for institutional investors who cannot take large positions in micro‑caps without moving the market. "
            "It also reduces the influence of illiquid stocks, which often have extreme returns and can distort IC."
        ),
        "example": (
            "A micro‑cap with market cap $10M (0.001% of total market) has a factor score of 0.9 and returns +50% in a month. "
            "In equal‑weighted IC, that stock contributes equally to the IC calculation (large influence). "
            "In value‑weighted IC, its contribution is scaled to nearly zero because no real portfolio can take a material position. "
            "The result: IC_vw is lower and more realistic for institutional deployment."
        ),
        "pitfall": (
            "Value‑weighted IC can still be influenced by a few large caps if they move together. "
            "Use winsorisation (cap weights at, say, 5% of total market cap) or exclude the top decile from the IC calculation if you're focused on decile spread, not individual stocks."
        ),
        "reference": (
            "Fama, E. & French, K. (1993). 'Common risk factors in the returns on stocks and bonds.' "
            "Blitz, D., et al. (2011). 'Evaluating Multiple Criteria for Scorecard Assessment' discusses IC measurement."
        ),
        "code_ref": "src/iam/backtest/metrics.py: ic_value_weighted() – weighted Spearman rank correlation using market cap as weights"
    },
    "Sector Neutralization": {
        "extended": (
            "A factor's IC may be inflated by sector timing effects rather than genuine stock selection. "
            "Sector‑neutral IC removes sector‑level correlations by computing the IC within each sector and then taking a weighted average. "
            "This isolates the stock‑picking skill from sector allocation skill."
        ),
        "example": (
            "A 'value' factor has IC = 0.05 when computed across all stocks. But if the value factor is highly correlated with the tech sector, "
            "and the tech sector happened to outperform in the test period, the IC is inflated. "
            "Computing IC within each of the 11 sectors (technology, healthcare, etc.) separately and averaging yields IC_neutral = 0.02, "
            "a more honest measure of the factor's stock‑selection power."
        ),
        "pitfall": (
            "Sector‑neutral IC requires enough stocks per sector. If a sector has only 5 stocks, the IC estimate is very noisy. "
            "Use a broader sector definition (e.g., GICS 2‑digit) rather than sub‑industries."
        ),
        "reference": "Arnott, R., et al. 'Fundamental Indexation' discusses the importance of factor purity.",
        "code_ref": "src/iam/backtest/metrics.py: ic_sector_neutral() – weighted average of within‑sector IC"
    },
    "Shrinkage (Bayesian / Empirical)": {
        "extended": (
            "Shrinkage pulls extreme parameter estimates toward a more conservative prior, reducing variance at the cost of a small bias. "
            "In factor weighting, instead of using the raw optimised weights (which can be extreme and overfit), "
            "we blend them with equal weights (or another prior): Final weight = λ * w_optimised + (1‑λ) * w_prior.\n\n"
            "λ typically ranges from 0.5–0.8. Shrinkage is a form of regularisation and is mathematically equivalent to adding an L2 penalty "
            "(ridge regression) to the optimisation problem."
        ),
        "example": (
            "Optimised weights (unconstrained): [0.6, 0.3, 0.1] for [value, quality, momentum]. "
            "Prior (equal weights): [0.33, 0.33, 0.33]. "
            "With λ=0.7, final = 0.7*[0.6,0.3,0.1] + 0.3*[0.33,0.33,0.33] = [0.42+0.099, 0.21+0.099, 0.07+0.099] = [0.519, 0.309, 0.172]. "
            "The extreme weight on value is pulled down; the near‑zero weight on momentum is pulled up."
        ),
        "pitfall": (
            "Shrinking too much (λ too low, e.g., 0.3) discards the signal and reverts to equal weight, losing predictive power. "
            "Shrinking too little (λ near 1.0) keeps overfitting. Use cross‑validation (e.g., K‑fold) to choose λ. "
            "Alternatively, set λ = 1 - (estimation_error_variance / true_signal_variance) from bootstrap analysis."
        ),
        "reference": (
            "Ledoit, O. & Wolf, M. (2004). 'Honey, I Shrunk the Sample Covariance Matrix.' "
            "James, W. & Stein, C. (1961). 'Estimation with Quadratic Loss.' Proc. Fourth Berkeley Symposium."
        ),
        "code_ref": "src/iam/backtest/weight_optimizer.py: OptimizerConfig.shrinkage_lambda – applied in weight_optimizer.run()"
    },
    "Reverse DCF (Expectations Investing)": {
        "extended": (
            "Instead of forecasting growth to find a price, reverse DCF solves for the growth rate that would justify the current price. "
            "It forces you to articulate explicitly: 'What must be true for this price to be fair?'\n\n"
            "You hold all other inputs constant (Ke, terminal growth, margins) and solve for the implied growth during the high‑growth period. "
            "If the implied growth is implausibly high (e.g., 30% annually for a mature company), the stock is overvalued. "
            "If it is achievable but demanding (e.g., 12% for a growing company), the stock is reasonably priced but offers little margin of safety."
        ),
        "example": (
            "Stock trading at $100, Ke=10%, terminal g=4%, current annual FCFE=$5, forecast period=5 years. "
            "Using the two‑stage DCF formula and solving for the 5‑year growth rate g gives g_implied = 15%. "
            "If you believe the company cannot grow faster than 10%, the stock is overvalued. "
            "If you believe it can sustain 12%, the stock offers modest margin of safety."
        ),
        "pitfall": (
            "Reverse DCF results are highly sensitive to the terminal growth assumption. "
            "Always run a two‑variable sensitivity table (growth × margin, or growth × Ke) to see the joint set of break‑even assumptions. "
            "Also, ensure the terminal value is realistic given long‑term industry growth rates."
        ),
        "reference": (
            "Mauboussin, M. & Rappaport, A. (2021). 'Expectations Investing: Reading Market Prices for Better Returns.' "
            "Damodaran, A. (2012). 'Implicit Growth Rates' lecture on valuation."
        ),
        "code_ref": "src/iam/backtest/runner.py – reverse DCF computed as part of Stage 1 snapshot valuation"
    },
    "Commodity P/E vs. Franchise P/E (PVGO)": {
        "extended": (
            "The total P/E can be decomposed into two components:\n"
            "1. Commodity P/E = 1/Ke. This is the P/E of a company with zero growth in earnings (all FCFEs paid out, no reinvestment).\n"
            "2. Franchise P/E = Actual P/E – 1/Ke. This is the premium investors pay for the expectation of future growth opportunities (Present Value of Growth Opportunities, PVGO).\n\n"
            "If the franchise P/E is large (e.g., >10x), most of the stock's value depends on future growth assumptions. "
            "A small miss in growth assumptions will cause a large price decline."
        ),
        "example": (
            "Stock with Ke=8% → commodity P/E = 1/0.08 = 12.5x. Actual P/E = 25x. Franchise P/E = 25 - 12.5 = 12.5x. "
            "Thus 50% of the stock's value is based on growth expectations. If expected growth disappoints, the stock could fall from 25x to 12.5x, a 50% loss."
        ),
        "pitfall": (
            "The commodity P/E assumes no growth and no reinvestment – it is an extreme lower bound. "
            "A well‑managed company with moderate reinvestment and a modest return on invested capital (ROIC > Ke) should trade above the commodity P/E even without optionality. "
            "Do not use commodity P/E as a valuation floor."
        ),
        "reference": (
            "Miller, M. & Modigliani, F. (1961). 'Dividend Policy, Growth, and the Valuation of Shares.' "
            "Damodaran, A. (2012). 'Growth and PVGO' in Investment Valuation."
        ),
        "code_ref": "src/iam/backtest/runner.py – P/E decomposition in snapshot and report generation"
    },
    "Geographic‑Mix‑Weighted ERP": {
        "extended": (
            "The Equity Risk Premium (ERP) – the additional return demanded for holding stocks vs. risk‑free bonds – varies by country "
            "due to different political, economic, and currency risks. Using a single US ERP (e.g., 5%) for a globally diversified company understates the true cost of capital.\n\n"
            "Correct method: For each country where the company earns revenue, take that country's ERP (from Damodaran's country risk dataset), "
            "weight by the revenue share (not listing domicile), and sum. The blended ERP is then used in CAPM."
        ),
        "example": (
            "Company: 60% US revenue (ERP 5.0%), 30% UK revenue (ERP 5.6%), 10% Brazil revenue (ERP 8.2%).\n"
            "Blended ERP = 0.6*5.0 + 0.3*5.6 + 0.1*8.2 = 3.0 + 1.68 + 0.82 = 5.5%.\n"
            "Using just US ERP (5%) would understate the cost of equity."
        ),
        "pitfall": (
            "Revenue mix is not static – update it annually from company filings. Also, if the company has significant foreign currency exposure, "
            "the ERP should reflect currency risk, which is partially captured in the country's default spread but not fully. "
            "Consider adding a currency risk premium (1‑2%) if exposure is large."
        ),
        "reference": (
            "Damodaran, A. (2026). 'Country Risk and Equity Risk Premiums – April 2026 update.' "
            "Stulz, R. (1995). 'The Cost of Capital in Internationally Integrated Markets.'"
        ),
        "code_ref": "src/iam/backtest/runner.py – geo_blended_erp() uses Damodaran country ERP file"
    },
    "Terminal Growth Capped at Risk‑Free Rate": {
        "extended": (
            "In a Gordon Growth Model (perpetuity formula for terminal value), the perpetual growth rate (g) cannot exceed the risk‑free rate (Rf) "
            "of the currency in which cash flows are denominated. Why? Because in the long run, no company can grow faster than the nominal economy. "
            "Rf approximates nominal GDP growth (real growth + inflation). If g > Rf, the company's value becomes negative (denominator Ke-g → 0) or the company "
            "eventually becomes larger than the entire economy – both impossible."
        ),
        "example": (
            "If Rf = 4.3% (US 10‑year Treasury), you may use g_terminal = 4.3% (extreme upper bound) or 3.5% (conservative, assuming the company grows slower than nominal GDP in perpetuity). "
            "Using 5% would violate the law of large numbers and produce an invalid valuation."
        ),
        "pitfall": (
            "Some analysts justify g > Rf by saying 'the company operates in a high‑growth emerging market.' "
            "Even in that case, the long‑run growth for a specific firm cannot exceed that country's long‑run nominal GDP growth, "
            "which is approximated by that country's risk‑free rate (e.g., Brazil 10‑year government bond yield ≈ 10‑11%). "
            "Use Brazil's Rf for the terminal growth cap, not the US Rf."
        ),
        "reference": (
            "Damodaran, A. (2012). 'Investment Valuation' – Chapter 11 on Terminal Value. "
            "Gordon, M. (1962). 'The Investment, Financing, and Valuation of the Corporation.' perpetuity formula origin."
        ),
        "code_ref": "src/iam/backtest/runner.py – terminal_growth = min(estimated_growth, risk_free_rate)"
    },
    "Through‑Cycle Normalisation": {
        "extended": (
            "Cyclical industries (e.g., commodities, private credit, semiconductors, airlines) have earnings that swing wildly with the economy. "
            "Valuing them at the peak (expansion) will overstate value; at the trough (contraction) will understate.\n\n"
            "The solution: estimate normalised earnings over a full cycle (typically 10 years) by assigning probabilities to different economic phases "
            "(expansion, compression, contraction, recovery), computing earnings in each phase, and computing a probability‑weighted average. "
            "Then apply a normalised growth rate to the cycle‑average base."
        ),
        "example": (
            "Private credit firm earnings by phase:\n"
            "Expansion (AUM growth, low defaults): FRE = $500M (30% probability, 3 years per cycle)\n"
            "Compression (AUM plateau): FRE = $350M (20% probability, 2 years)\n"
            "Contraction (rising defaults): FRE = $200M (30% probability, 3 years)\n"
            "Recovery (defaults normalise): FRE = $300M (20% probability, 2 years)\n"
            "Normalised FRE = 0.30*500 + 0.20*350 + 0.30*200 + 0.20*300 = 150+70+60+60 = $340M."
        ),
        "pitfall": (
            "The weighting of cycle phases is subjective and requires historical analysis. "
            "Use historical data on the frequency and duration of recessions for that specific industry. "
            "Also, normalisation assumes the cycle is stationary (repeating); in the presence of structural change (e.g., regulatory shift), "
            "normalisation may not work and scenario‑based valuation is better."
        ),
        "reference": (
            "Damodaran, A. (2012). 'Cyclical and Commodity Companies' lecture. "
            "Damodaran sector‑specific tools include through‑cycle templates."
        ),
        "code_ref": "src/iam/backtest/runner.py – normalised_earnings() weights phases by duration"
    },
    "Operating Leverage as Disguised Beta": {
        "extended": (
            "Operating leverage means a company has high fixed costs relative to variable costs. When revenue falls, profits fall more than proportionally. "
            "This amplifies earnings volatility – exactly what equity beta measures. A company with high operating leverage has higher equity risk and should demand a higher Ke.\n\n"
            "If you only use an industry beta, you may miss this amplification. The adjustment: β_adjusted = β_industry * (1 + fixed_cost_ratio/(1‑fixed_cost_ratio)). "
            "For example, a software company with fixed costs = 80% of total costs has 4x the leverage factor and thus much higher beta than a typical software firm."
        ),
        "example": (
            "SaaS company with 80% fixed costs (R&D, infrastructure), 20% variable (hosting, support). "
            "Fixed_cost_ratio = 0.80. Industry beta = 0.8. Leverage factor = 1 + 0.8/0.2 = 5. "
            "Adjusted beta = 0.8 * 5 = 4.0 – much more volatile than the industry average. "
            "This correctly reflects that a revenue decline of 30% would cause operating income to fall 75% or more."
        ),
        "pitfall": (
            "If the industry beta already includes the average operating leverage of firms in that industry, you may double‑count. "
            "Only adjust when your company's fixed cost ratio differs significantly from the industry average (>10 percentage points). "
            "Also, fixed costs can shift (e.g., automation increases fixed costs), so re‑check annually."
        ),
        "reference": (
            "Damodaran, A. (2012). 'The Determinants of Betas: Operating and Financial Leverage.' "
            "Hamada, R. (1972). 'The Effect of the Firm's Capital Structure on Systemic Risk.'"
        ),
        "code_ref": "src/iam/backtest/runner.py – fixed_cost_ratio → beta_adjusted = beta_industry * (1 + leverage_factor)"
    },
    "Bottom‑Up Beta": {
        "extended": (
            "Instead of regressing a stock's historical returns against the market (which gives a noisy beta estimate, especially for small/illiquid stocks), "
            "bottom‑up beta uses the median unlevered beta of a broad peer group from the same industry, then relevers to your company's debt/equity ratio.\n\n"
            "This approach is more stable and forward‑looking because it reflects the business risk of the sector (not company‑specific noise) and can be adjusted "
            "for the company's actual capital structure. For cyclical companies or those with short trading history, bottom‑up is far more reliable than regression."
        ),
        "example": (
            "Peer group: 30 large software companies (Oracle, Salesforce, ServiceNow, etc.). "
            "Median unlevered beta from Damodaran data = 1.0 (capturing sector business risk).\n"
            "Target company: D (total debt) = $2B, E (equity value) = $4B, so D/E = 0.5. Tax rate = 25%.\n"
            "Levered beta = 1.0 * (1 + (1‑0.25)*0.5) = 1.0 * 1.375 = 1.375. "
            "If the company paid off all debt, its beta would drop to 1.0."
        ),
        "pitfall": (
            "Choosing the wrong peer group (e.g., including conglomerates with different business mixes) distorts the estimate. "
            "Use Damodaran's GICS classifications for standardisation. Also, unlevered beta can change over time as technology shifts, "
            "so refresh your peer group annually. If your company's business is very different from peers (e.g., it has recurring revenue while competitors don't), "
            "consider a separate beta adjustment."
        ),
        "reference": (
            "Damodaran, A. (2026). 'Betas by Sector – April 2026' dataset with unlevered and levered betas by industry. "
            "Hamada, R. (1972). 'The Effect of the Firm's Capital Structure on Systemic Risk.'"
        ),
        "code_ref": "src/iam/backtest/runner.py – get_damodaran_beta(sector) returns unlevered, then relever using target D/E"
    },
    "Two‑Stage DCF with Linear Fade": {
        "extended": (
            "A standard two‑stage DCF assumes growth abruptly drops from high (e.g., 15%) to terminal (e.g., 4%) after a fixed number of years. "
            "More realistic: a linear fade where both growth and margins decline gradually over a transition period (e.g., years 6‑10).\n\n"
            "For each year t during the fade, growth = g_high + (g_terminal - g_high) * (t / fade_years). "
            "This smoother transition better captures real-world dynamics where competitive advantages erode gradually, not overnight."
        ),
        "example": (
            "g_high = 12% (years 1‑5), g_terminal = 4% (year 11+), fade_years = 5 (years 6‑10).\n"
            "Year 6: g = 12% + (4‑12)*1/5 = 12 - 1.6 = 10.4%\n"
            "Year 7: g = 12 - 3.2 = 8.8%\n"
            "Year 8: g = 12 - 4.8 = 7.2%\n"
            "Year 9: g = 12 - 6.4 = 5.6%\n"
            "Year 10: g = 12 - 8.0 = 4.0% (terminal). "
            "This gradual transition is more realistic than jumping from 12% to 4% in a single year."
        ),
        "pitfall": (
            "Linear fade is still an approximation. Some industries may have convex (faster initial decay) or concave (slower initial decay) fade patterns. "
            "Sensitivity analysis on the fade length and the shape of the fade (linear, quadratic, exponential) is recommended. "
            "Also, if the fade crosses into negative growth (g < 0), the model is broken – cap g_t at some minimum (e.g., 0%)."
        ),
        "reference": (
            "Damodaran, A. (2012). 'DCF with Fading Growth' lecture notes and templates. "
            "Copeland, Koller, Murrin (2000). 'Valuation: Measuring and Managing the Value of Companies' – multi‑stage DCF models."
        ),
        "code_ref": "src/iam/backtest/runner.py – two_stage_dcf() with linear fade in fcfe forecast"
    },
    "Probability‑Weighted Scenarios": {
        "extended": (
            "Instead of a single base case, assign explicit probabilities to multiple scenarios (e.g., bear 20%, base 60%, bull 20%). "
            "The intrinsic value is the probability‑weighted average of scenario values: V = Σ p_i * V_i.\n\n"
            "This approach explicitly acknowledges uncertainty and prevents the false precision of a single point estimate. "
            "It also forces discipline: you must articulate what each scenario entails (revenue growth, margins, Ke, terminal growth) and assign probabilities "
            "based on historical likelihood or expert judgment."
        ),
        "example": (
            "Bear scenario (20% probability): Revenue CAGR = 5%, margin declines to 25%, Ke = 12%, terminal g = 2%. Value = $60.\n"
            "Base scenario (60% probability): Revenue CAGR = 12%, margin stable at 35%, Ke = 10%, terminal g = 4%. Value = $100.\n"
            "Bull scenario (20% probability): Revenue CAGR = 20%, margin expands to 40%, Ke = 8%, terminal g = 5%. Value = $150.\n"
            "Weighted value = 0.2*60 + 0.6*100 + 0.2*150 = 12 + 60 + 30 = $102."
        ),
        "pitfall": (
            "Probabilities are subjective and often over‑confident. Always show a sensitivity matrix (e.g., what if probs are 30/40/30 instead of 20/60/20?). "
            "Also, scenarios should be internally consistent – if you assume high revenue growth, you should also assume higher capex/reinvestment and lower margins, not higher. "
            "Use scenario analysis as a check on model consistency."
        ),
        "reference": (
            "Damodaran, A. (2012). 'Probabilistic Approaches to Valuation: Scenarios and Simulation.' "
            "Copeland, Koller, Murrin (2000). Multiple scenario valuation."
        ),
        "code_ref": "src/iam/backtest/runner.py – Aladdin example with bear/base/bull weights 0.2/0.6/0.2"
    },
    "Exponentially Weighted Average (EWA) Forecaster": {
        "extended": (
            "EWA gives more weight to recent observations and exponentially decreasing weight to older data. "
            "It is more responsive to regime changes than a simple moving average and is mathematically equivalent to an exponential smoothing model.\n\n"
            "Weight for observation t‑k = (1‑λ)^k, with λ (smoothing factor) typically 0.1–0.3. "
            "As λ increases, recent data is weighted more heavily. Used to forecast volatility, correlations, factor returns, or market regimes."
        ),
        "example": (
            "Monthly factor returns over 6 months: +2%, +1.5%, +2.5%, +1%, +1.8%, +2.2% (oldest to most recent).\n"
            "With λ=0.2 (giving 20% weight to most recent month):\n"
            "EWA_forecast = 0.2*2.2 + 0.2*0.8*(1.8) + 0.2*0.8²*(1) + ... ≈ weighted average heavily favoring the most recent months.\n"
            "This adapts quickly to the market entering a higher‑return regime."
        ),
        "pitfall": (
            "Choosing λ too high (e.g., 0.5) makes the forecast too noisy and reactive to short‑term noise. "
            "Too low (e.g., 0.05) makes it sluggish and slow to adapt. Optimise λ in‑sample using minimum forecast error, or use a fixed rule "
            "(e.g., λ = 2/(N+1) where N is a chosen effective sample size)."
        ),
        "reference": (
            "Brown, R. (1959). 'Statistical Forecasting for Inventory Control.' Wiley. "
            "Hastie, T., Tibshirani, R., Friedman, J. (2009). 'The Elements of Statistical Learning' – exponential smoothing chapter."
        ),
        "code_ref": "src/iam/backtest/weight_optimizer.py – used in online learning and factor return forecasting (see comments)"
    },
    "Multi‑Armed Bandit / Hedge Algorithm": {
        "extended": (
            "An online learning method for allocating capital among competing factor strategies without a priori knowledge of which factors are best. "
            "Treat each factor as an 'arm'. After each period, update the weight of each factor based on its recent performance.\n\n"
            "The Hedge algorithm: w_{t+1,i} = w_{t,i} * exp(η * contribution_{t,i}) / Z_t, where contribution is the factor's signed performance "
            "(IC * signal magnitude or Sharpe ratio). Factors that correctly predicted returns get increased weight; others decrease. "
            "Over time, the algorithm adapts to identify the best factors without explicit forecasting."
        ),
        "example": (
            "Start with equal weights [0.33, 0.33, 0.33] for [value, momentum, quality]. \n"
            "Month 1: value IC = 0.05 (positive), momentum IC = -0.02 (negative), quality IC = 0.03.\n"
            "Hedge update: value weight increases, momentum decreases, quality stays moderate.\n"
            "After 12 months of this process, weights might be [0.5, 0.1, 0.4], reflecting which factors worked best."
        ),
        "pitfall": (
            "The learning rate η must be tuned. Too large → overreacts to noise; too small → slow adaptation. "
            "Also, bandit algorithms assume the reward distribution is stationary – not true in financial markets where regimes change. "
            "Use a combination of Hedge algorithm + regime detection for best results. Also, the algorithm can go unstable if some factors "
            "are highly correlated; monitor for weight explosion."
        ),
        "reference": (
            "Auer, P., Cesa‑Bianchi, N., & Freund, Y. (2002). 'The Nonstochastic Multiarmed Bandit Problem.' SIAM Journal on Computing, 32, 48-77. "
            "Arora, S., Hazan, E., & Kale, S. (2012). 'The Multiplicative Weights Update Method: A Meta‑Algorithm and Applications.' Theory of Computing."
        ),
        "code_ref": "src/iam/backtest/weight_optimizer.py – online_update() function shows Hedge algorithm example"
    },
    "Bayesian Thesis Engine / Posterior Updating": {
        "extended": (
            "Start with a prior probability of a stock's investment thesis (e.g., 'This company will grow at 15% for 5 years'). "
            "As new evidence arrives (quarterly earnings, macro data, competitive moves), update the probability using Bayes' rule:\n\n"
            "Posterior = Likelihood(evidence | thesis) * Prior / Evidence_marginal.\n\n"
            "This is formal, quantitative, and forces you to articulate exactly what evidence would change your mind and by how much. "
            "It also naturally handles multiple theses in competition – the most consistent thesis gains probability mass."
        ),
        "example": (
            "Prior probability of 'grow at 15% for 5 years' = 60%. Prior probability of 'grow at 8% for 5 years' = 40%.\n"
            "New evidence: Q1 shows 10% revenue growth (relative to 12% expected for 15% path, 7% expected for 8% path).\n"
            "Likelihood(10% | 15% thesis) ≈ 0.2 (unlikely but possible)\n"
            "Likelihood(10% | 8% thesis) ≈ 0.5 (more consistent)\n"
            "Posterior(15% thesis) = 0.2*0.6 / (0.2*0.6 + 0.5*0.4) = 0.12 / 0.32 = 37.5% (drops from 60%).\n"
            "Your conviction in the 15% growth thesis should fall after seeing only 10% growth."
        ),
        "pitfall": (
            "Assigning the likelihood function P(evidence | thesis) is highly subjective. "
            "Calibrate using historical base rates (e.g., 'how often did companies claiming 15% sustainable growth actually achieve 12%+ growth in the subsequent year?'). "
            "Also, be careful of confirmation bias – assign realistic likelihoods to evidence that would refute your thesis, not just evidence that confirms it."
        ),
        "reference": (
            "Tufano, P. (1996). 'Bayesian Analysis in Finance' – case studies in probabilistic thesis updating. "
            "Gelman, A., et al. (2013). 'Bayesian Data Analysis' – comprehensive treatment of Bayesian inference."
        ),
        "code_ref": "src/iam/backtest/runner.py – thesis engine to be implemented in Phase 3.2; currently stores thesis in metadata"
    },
    "Load‑Bearing Assumption Drift Detection": {
        "extended": (
            "Every investment thesis rests on a few critical assumptions (e.g., 'gross margin will stay above 40%', 'customer acquisition cost will not rise more than 10% annually'). "
            "Monitor these assumptions in real time. If they drift beyond a pre‑set tolerance, the thesis is at risk and the model should automatically lower conviction or trigger a manual review.\n\n"
            "This is most critical for valuation‑based factors, where a single margin assumption change can swing intrinsic value by 20–30%."
        ),
        "example": (
            "Assumption: ROIC > 18% for the next 5 years (load‑bearing because valuation is sensitive to ROIC). "
            "Alert tolerance: if ROIC falls below 16% (2pp threshold), trigger a review.\n"
            "After a year, ROIC drops to 15% and stays there. Drift detection flags this and reduces the position size from 4% to 2% of portfolio."
        ),
        "pitfall": (
            "Tolerances that are too tight cause many false alarms and desensitise the team ('alert fatigue'). "
            "Too wide miss real deterioration. Use historical volatility of the metric (e.g., 2 standard deviations) to set dynamic tolerances. "
            "Also, a single quarter of miss should not trigger an alert – use a rolling 3‑quarter or annual average to reduce noise."
        ),
        "reference": "Risk management standard in quantitative funds (e.g., BlackRock's Aladdin Risk, RiskMetrics).",
        "code_ref": "src/iam/backtest/runner.py – drift_monitor logic planned for Phase 3.2"
    },
    "Narrative‑Consistency Validation": {
        "extended": (
            "Check that the numerical inputs to a valuation model do not contradict each other. "
            "For example, if a company has 25% revenue growth, it must reinvest a portion of earnings to achieve that growth. "
            "The reinvestment rate should be consistent with the sustainable growth equation: g = ROIC * reinvestment_rate.\n\n"
            "If not, the model is internally inconsistent and its output is invalid. Consistency checks catch fundamental errors before you bet capital on them."
        ),
        "example": (
            "Assume Company X grows revenue at 20% annually but has ROIC = 12% and payout ratio = 80% (reinvestment = 20%). "
            "Sustainable growth = ROIC * reinvestment = 12% * 20% = 2.4%, far below 20%. The model is contradictory. "
            "Either the revenue growth assumption is wrong, or the ROIC/payout assumptions are wrong. Something must give."
        ),
        "pitfall": (
            "Short‑term growth can exceed sustainable growth due to external financing (debt, equity raises) or one‑time events (asset sales). "
            "Validation should apply primarily to the terminal period or an average over 5+ years. Also, the sustainable growth formula "
            "g = ROIC * reinvestment assumes all reinvestment earns the ROIC; in reality, new capital may earn less until it scales. "
            "Use conservatism: apply g = (ROIC - cost_of_capital) * reinvestment + cost_of_capital to be stricter."
        ),
        "reference": (
            "Damodaran, A. (2012). 'The Consistency Rule' in Investment Valuation. "
            "Palepu, K., Healy, P., Bernard, V. (2004). 'Business Analysis and Valuation' – consistency analysis chapter."
        ),
        "code_ref": "src/iam/backtest/runner.py – validate_growth_consistency() checks g ≤ ROIC * reinvestment_rate"
    },
    "Manifest.json Reproducibility": {
        "extended": (
            "Every backtest run saves a manifest file containing: git commit hash, Python environment, configuration parameters, factor weights, data source versions, "
            "and cryptographic hashes of input files. This makes any result auditable and reproducible months or years later. "
            "If a colleague asks 'Why did we get IC=0.04 in March 2025?', you can check the exact code, data, and config state at that time from the manifest."
        ),
        "example": (
            "manifest.json from a March 2025 backtest includes:\n"
            "{\n"
            "  'git_commit': 'a1b2c3d',\n"
            "  'git_branch': 'main',\n"
            "  'python_version': '3.12.2',\n"
            "  'backtest_config': {'start_date': '2015-01-31', 'end_date': '2025-03-31', 'min_market_cap': 50000000},\n"
            "  'factor_weights': {'value': 0.3, 'quality': 0.4, 'momentum': 0.2},\n"
            "  'data_sources': {'prices': 'yfinance', 'fundamentals': 'sec_edgar'},\n"
            "  'universe_hash': 'abc123def456',\n"
            "  'price_hash': 'xyz789',\n"
            "  'timestamp': '2025-03-31T18:32:45Z'\n"
            "}"
        ),
        "pitfall": (
            "Manifest must be generated automatically at runtime, not manually. Also, it should include the exact version of all imported libraries "
            "(using pip freeze output) to avoid hidden dependency changes. Without this, reproducing 'the same code' may yield different results "
            "if a library like numpy or scipy released a new version with algorithmic improvements."
        ),
        "reference": "Open science best practices – reproducible research (cf. Nature reproducibility guidance).",
        "code_ref": "src/iam/backtest/manifest.py – BacktestManifest class, generated in runner.py after backtest completion"
    },
}
