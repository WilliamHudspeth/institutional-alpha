#!/usr/bin/env python3
"""
learning_module.py – Interactive educational tool for institutional finance concepts.

Usage:
    python -m iam.learning_module --mode interactive
    python -m iam.learning_module --mode quiz --quiz_questions 20
    python -m iam.learning_module --concept "Information Coefficient" --detailed
    python -m iam.learning_module --mode report
    python -m iam.learning_module --mode markdown > concepts.md
"""

import random

try:
    from iam.concept_library_expanded import EXPANDED_CONCEPTS

    HAS_EXPANDED = True
except ImportError:
    HAS_EXPANDED = False

# Concept Library – definitions + where to find them in the code
CONCEPTS = {
    "Information Coefficient (IC)": {
        "definition": "Cross‑sectional Spearman rank correlation between a factor score and forward return. Measures raw predictive power.",
        "code_ref": "src/iam/backtest/metrics.py: ic_spearman() → computes IC and IC rank",
        "formula": "ρ = 1 - 6∑d_i² / (n(n²-1))",
    },
    "IC Information Ratio (ICIR)": {
        "definition": "Mean IC divided by standard deviation of IC. Measures consistency of predictive power.",
        "code_ref": "src/iam/backtest/metrics.py: compute_statistics() → icir = mean_ic / std_ic",
        "formula": "ICIR = μ_IC / σ_IC",
    },
    "Newey‑West HAC Standard Errors": {
        "definition": "Heteroskedasticity and autocorrelation consistent errors for time‑series IC.",
        "code_ref": "src/iam/backtest/metrics.py: compute_statistics() → uses statsmodels cov_hac",
        "formula": "NW estimator accounts for autocorrelation up to lag L = 4*(n/100)^(2/9)",
    },
    "Walk‑Forward Optimization": {
        "definition": "Rolling training/testing windows to avoid overfitting. Optimise weights on past 5 years, test on next year.",
        "code_ref": "src/iam/backtest/runner.py: run_backtest() → multi-date backtesting",
        "formula": "Train window = 60 months, test = 12 months",
    },
    "Multi‑Horizon IC": {
        "definition": "Compute Information Coefficient at multiple forward return horizons (21d, 63d, 126d, 252d) to characterize signal timing.",
        "code_ref": "src/iam/backtest/runner.py: discover and compute IC for all horizons",
        "formula": "IC_21d, IC_63d, IC_126d, IC_252d measure momentum vs fundamental characteristics",
    },
    "Value‑Weighted IC": {
        "definition": "Weighted Spearman rank correlation using market cap as weights. Validates signal works in large-cap portfolios.",
        "code_ref": "src/iam/backtest/metrics.py: ic_value_weighted()",
        "formula": "ρ_vw = weighted rank correlation using market cap",
    },
    "Shrinkage (Bayesian / Empirical)": {
        "definition": "Pull extreme weights toward a prior (e.g., equal weight) to reduce estimation error.",
        "code_ref": "src/iam/backtest/calibration.py: ic_to_reliability_bayesian()",
        "formula": "w_final = λ·w_opt + (1‑λ)·w_prior",
    },
    "Reverse DCF (Expectations Investing)": {
        "definition": "Take current price as given, solve for implied growth assumptions.",
        "code_ref": "src/iam/engine/valuation.py: reverse_dcf methods",
        "formula": "Solve P = Σ FCFE_t / (1+Ke)^t for growth g",
    },
    "Commodity P/E vs. Franchise P/E (PVGO)": {
        "definition": "Decompose P/E into zero‑growth value (1/Ke) and premium for future growth.",
        "code_ref": "src/iam/engine/valuation.py: commodity_pe(), franchise_pe()",
        "formula": "Franchise P/E = Actual P/E – 1/Ke",
    },
    "Sum‑of‑the‑Parts (SOTP)": {
        "definition": "Value each business segment with its own Ke, then sum.",
        "code_ref": "src/iam/engine/valuation.py: sum_of_parts()",
        "formula": "V_total = Σ V_segment – corporate overhead – net debt",
    },
    "Segment‑Specific Cost of Equity (Ke)": {
        "definition": "Use different discount rates for different business units based on their risk profile.",
        "code_ref": "src/iam/engine/cost_of_capital.py: segment_cost_of_equity()",
        "formula": "Ke_seg = Rf + β_seg * ERP_blended",
    },
    "Geographic‑Mix‑Weighted ERP": {
        "definition": "Weight country ERPs by revenue footprint, not listing domicile.",
        "code_ref": "src/iam/engine/erp.py: geo_blended_erp()",
        "formula": "ERP_blended = Σ (w_i * ERP_i) for each country i",
    },
    "Terminal Growth Capped at Risk‑Free Rate": {
        "definition": "Perpetuity growth cannot exceed Rf (proxy for long‑run nominal GDP growth).",
        "code_ref": "src/iam/engine/valuation.py: terminal_growth = min(estimated_growth, Rf)",
        "formula": "g_terminal ≤ Rf",
    },
    "Through‑Cycle Normalisation of Cyclical Earnings": {
        "definition": "Use average earnings over full cycle (expansion, contraction, distress, recovery) instead of peak.",
        "code_ref": "src/iam/engine/cyclical.py: normalised_earnings()",
        "formula": "FRE_norm = Σ p_phase * FRE_phase",
    },
    "Operating Leverage as Disguised Beta": {
        "definition": "High fixed costs magnify earnings volatility, increasing equity beta.",
        "code_ref": "src/iam/engine/cost_of_capital.py: beta_adjustment_for_leverage()",
        "formula": "β_adjusted = β_sector * (1 + fixed_cost_ratio / (1‑fixed_cost_ratio))",
    },
    "Bottom‑Up Beta": {
        "definition": "Use industry median unlevered beta from broad peer set, then relever for target's debt.",
        "code_ref": "src/iam/engine/cost_of_capital.py: relever_beta()",
        "formula": "βL = βu * (1 + (1‑t) * D/E)",
    },
    "Two‑Stage DCF with Linear Fade": {
        "definition": "High growth for 5 years, then gradual decline to terminal growth over 5 years.",
        "code_ref": "src/iam/engine/valuation.py: two_stage_dcf()",
        "formula": "g_t = g_high + (g_term - g_high) * (t / fade_years)",
    },
    "Probability‑Weighted Scenarios": {
        "definition": "Assign probabilities to bear/base/bull cases and compute expected value.",
        "code_ref": "src/iam/engine/scenarios.py: scenario_valuation()",
        "formula": "E[V] = Σ p_i * V_i",
    },
    "Narrative‑Consistency Validation": {
        "definition": "Check that model inputs don't contradict each other (e.g., high growth without reinvestment).",
        "code_ref": "src/iam/validation/narrative.py: validate_growth_consistency()",
        "formula": "g_implied = ROIC * (1 - payout)",
    },
    "Tail‑Risk Stress Test": {
        "definition": "Simulate extreme macro scenarios (yen carry unwind, credit crisis) and compute floor value.",
        "code_ref": "src/iam/engine/stress.py: stress_test()",
        "formula": "Stressed Ke = Rf+shock + β*(ERP+shock), FCFE *= contraction_factor",
    },
    "Composite Score (BlackRock Aladdin style)": {
        "definition": "Weighted blend of 10 orthogonal factors (value, quality, momentum, earnings revisions, etc.) with 3 penalties.",
        "code_ref": "src/iam/engine/composite.py: score()",
        "formula": "Score = w1*value + w2*quality + ... + w10*momentum - penalties",
    },
    "Manifest.json Reproducibility": {
        "definition": "Capture git commit, config, and all parameters for every backtest run.",
        "code_ref": "src/iam/backtest/manifest.py: BacktestManifest",
        "formula": "Ensures exact replication and audit trail",
    },
    "Regression-Based Backtesting": {
        "definition": "Rank factors cross-sectionally and measure correlation with forward returns using Spearman rank correlation.",
        "code_ref": "src/iam/backtest/runner.py: run_backtest()",
        "formula": "Cross-sectional Spearman of score ranks vs fwd_return ranks",
    },
    "Sector Neutralization": {
        "definition": "Remove sector-level effects from IC by computing correlation within sectors, not across.",
        "code_ref": "src/iam/backtest/metrics.py: ic_sector_neutral()",
        "formula": "IC_neutral = Σ w_s * IC_s (within-sector IC)",
    },
    "Model Limitations & Edge Cases": {
        "definition": "Where the quantitative model's assumptions break down, such as with pre-revenue tech, high-debt cyclicals, or deep distress situations.",
        "code_ref": "src/iam/engine/valuation.py (where limits are applied), src/iam/validation/narrative.py",
        "formula": "Confidence = f(Data Quality, Earnings Stability, Leverage)",
    },
    "Backtest Validation Metrics": {
        "definition": "Key performance indicators for signals. Includes Information Coefficient (predictive power), Hit Rate (% profitable trades), and Sharpe Ratio (risk-adjusted return).",
        "code_ref": "src/iam/backtest/metrics.py: compute_statistics()",
        "formula": "Sharpe = (μ_ret - R_f) / σ_ret, Hit Rate = count(ret > 0) / N",
    },
    "Institutional Comparisons": {
        "definition": "Unlike opaque black-box terminal scores (e.g. Bloomberg/Refinitiv), this engine provides a transparent, customizable pipeline prioritizing theory-first reasoning over static formulas.",
        "code_ref": "src/iam/pipeline/orchestrator.py",
        "formula": "Alpha = Theory + Transparency",
    },
}

# Quiz Questions
QUIZ_QUESTIONS = [
    {
        "question": "What is the first step in a 'Narrative-Numbers Loop' valuation?",
        "options": [
            "Build a discounted cash flow spreadsheet",
            "Determine the appropriate risk-free rate",
            "Ask what kind of business this actually is and write its story",
            "Calculate the company's historical P/E multiple",
        ],
        "correct": 2,
        "concept": "Narrative‑Consistency Validation",
    },
    {
        "question": "Why does a rigorous valuation framework reject a single firm-wide WACC for a conglomerate?",
        "options": [
            "It is mathematically impossible to calculate",
            "Different business segments have different risk profiles",
            "Regulators require segment-level discounting",
            "It always produces a higher valuation",
        ],
        "correct": 1,
        "concept": "Segment‑Specific Cost of Equity",
    },
    {
        "question": "A company trades at $100. Using reverse DCF, you find the market is pricing 25% annual FCFE growth for 5 years. If you believe the maximum sustainable growth is 10%, the stock is most likely:",
        "options": ["Undervalued", "Fairly valued", "Overvalued", "Impossible to determine"],
        "correct": 2,
        "concept": "Reverse DCF",
    },
    {
        "question": "A global company earns 40% from Europe (ERP 6.0%), 50% from US (ERP 5.0%), 10% from Asia (ERP 7.0%). What is the geographically‑weighted ERP?",
        "options": ["5.00%", "5.40%", "5.70%", "6.00%"],
        "correct": 2,
        "concept": "Geographic‑Mix‑Weighted ERP",
    },
    {
        "question": "According to the exogenous terminal growth cap, a firm's perpetual growth rate should NOT exceed:",
        "options": [
            "Nominal GDP growth of the world",
            "The risk‑free rate (Rf)",
            "The company's historical growth rate",
            "The inflation rate",
        ],
        "correct": 1,
        "concept": "Terminal Growth Capped at Rf",
    },
    {
        "question": "You are valuing a private credit firm. Its current FRE is $500M (peak), but through‑cycle average is $350M. Which should you use?",
        "options": [
            "$500M peak",
            "$500M with a 30% risk premium",
            "$350M to avoid overvaluing a cyclical peak",
            "Average of $500M and $350M",
        ],
        "correct": 2,
        "concept": "Through‑Cycle Normalisation of Cyclical Earnings",
    },
    {
        "question": "A stock has a cost of equity (Ke) of 8%. What is its 'commodity P/E' (zero‑growth value)?",
        "options": ["8.0x", "10.0x", "12.5x", "15.0x"],
        "correct": 2,
        "concept": "Commodity P/E vs. Franchise P/E",
    },
    {
        "question": "Which risk should be handled as a probability‑weighted cash flow adjustment rather than an addition to the discount rate?",
        "options": [
            "Market beta",
            "Country equity risk premium",
            "Idiosyncratic risk of losing a single large client",
            "Systematic interest rate risk",
        ],
        "correct": 2,
        "concept": "Narrative‑Consistency Validation",
    },
    {
        "question": "Why is the terminal period often 60‑80% of a DCF's intrinsic value?",
        "options": [
            "Because discount rates are lower in the terminal period",
            "Because most present value comes from beyond the explicit forecast",
            "Because analysts inflate terminal growth",
            "Because near‑term cash flows are irrelevant",
        ],
        "correct": 1,
        "concept": "Terminal Growth Capped at Rf",
    },
    {
        "question": "In an Information Coefficient (IC) backtest, what does a positive IC of 0.03 suggest?",
        "options": [
            "The signal is worthless",
            "The signal has a weak but real predictive power",
            "The signal is perfectly predictive",
            "The signal is mean-reverting",
        ],
        "correct": 1,
        "concept": "Information Coefficient (IC)",
    },
    {
        "question": "What does Value-Weighted IC measure?",
        "options": [
            "How well the signal predicts returns equally across all companies",
            "How well the signal predicts returns in large-cap portfolios where real capital deploys",
            "The average IC across all sectors",
            "The IC adjusted for dividends",
        ],
        "correct": 1,
        "concept": "Value‑Weighted IC",
    },
    {
        "question": "Multi-Horizon IC (21d, 63d, 126d, 252d) helps identify whether a signal is:",
        "options": [
            "Statistical noise",
            "Momentum-driven or fundamental in nature",
            "Sector-specific",
            "Country-specific",
        ],
        "correct": 1,
        "concept": "Multi‑Horizon IC",
    },
    {
        "question": "What does Sector-Neutral IC tell you?",
        "options": [
            "The IC after removing sector-level correlations",
            "The IC only within a single sector",
            "The IC weighted by sector profitability",
            "The IC adjusted for sector volatility",
        ],
        "correct": 0,
        "concept": "Sector Neutralization",
    },
    {
        "question": "The 'Composite Score' in institutional-alpha blends how many orthogonal factors?",
        "options": ["5", "8", "10", "15"],
        "correct": 2,
        "concept": "Composite Score (BlackRock Aladdin style)",
    },
    {
        "question": "Why is Manifest.json important in backtesting?",
        "options": [
            "It makes the backtest faster",
            "It ensures exact reproducibility with git SHA and config hash",
            "It compresses backtest results",
            "It is required by regulators",
        ],
        "correct": 1,
        "concept": "Manifest.json Reproducibility",
    },
    {
        "question": "A company has two divisions: stable software (low beta) and volatile trading (high beta). Using a single company‑wide WACC would most likely:",
        "options": [
            "Correctly value both",
            "Under‑value software and over‑value trading",
            "Over‑value software and under‑value trading",
            "Have no effect",
        ],
        "correct": 2,
        "concept": "Segment‑Specific Cost of Equity",
    },
    {
        "question": "In a reverse DCF, if market price implies 3% 5‑year FCFE growth but you believe the company can grow at 8%, the stock is likely:",
        "options": ["Overvalued", "Undervalued", "Fairly valued", "Cannot determine"],
        "correct": 1,
        "concept": "Reverse DCF (Expectations Investing)",
    },
    {
        "question": "A firm's actual P/E is 18x and Ke is 9%. What is its franchise P/E (premium for growth)?",
        "options": ["6.9x", "9.0x", "11.1x", "18.0x"],
        "correct": 0,
        "concept": "Commodity P/E vs. Franchise P/E (PVGO)",
    },
    {
        "question": "Which justifies using terminal growth = risk‑free rate of 4%?",
        "options": [
            "Company has a strong brand",
            "Company operates in a high‑growth emerging market",
            "Company cannot outgrow the nominal economy forever",
            "Rf is always the maximum possible growth",
        ],
        "correct": 2,
        "concept": "Terminal Growth Capped at Risk‑Free Rate",
    },
    {
        "question": "A Sum‑of‑the‑Parts valuation with a conglomerate discount:",
        "options": [
            "Is always 15%",
            "Should be applied before segment discounting",
            "May be reduced if synergies exist",
            "Is required by accounting standards",
        ],
        "correct": 2,
        "concept": "Sum‑of‑the‑Parts (SOTP)",
    },
]

# True/False questions
TF_QUESTIONS = [
    {
        "question": "A reverse DCF is used to derive the market's implied growth expectations from the current price.",
        "correct": True,
        "concept": "Reverse DCF",
    },
    {
        "question": "A conglomerate discount should always be applied after SOTP valuation, regardless of synergies.",
        "correct": False,
        "concept": "SOTP",
    },
    {
        "question": "Using a US‑only ERP for a global company is a common simplification that rigorous frameworks accept as adequate.",
        "correct": False,
        "concept": "Geographic‑Mix‑Weighted ERP",
    },
    {
        "question": "Operating leverage can increase a company's equity beta because fixed costs magnify earnings volatility.",
        "correct": True,
        "concept": "Operating Leverage as Disguised Beta",
    },
    {
        "question": "The commodity P/E is calculated as 1 divided by the cost of equity (Ke).",
        "correct": True,
        "concept": "Commodity P/E vs. Franchise P/E",
    },
    {
        "question": "If a company has a franchise P/E greater than zero, it means the market expects excess returns on future investments.",
        "correct": True,
        "concept": "Commodity P/E vs. Franchise P/E",
    },
    {
        "question": "A terminal growth rate of 5% is always safe to use as long as the risk‑free rate is 4%.",
        "correct": False,
        "concept": "Terminal Growth Capped at Risk‑Free Rate",
    },
    {
        "question": "Idiosyncratic risks are best handled by adding a premium to the discount rate rather than scenario‑adjusted cash flows.",
        "correct": False,
        "concept": "Narrative‑Consistency Validation",
    },
    {
        "question": "Epistemic humility in valuation means refusing to produce a single point estimate and instead presenting ranges and scenarios.",
        "correct": True,
        "concept": "Narrative‑Consistency Validation",
    },
    {
        "question": "The Information Coefficient (IC) measures how well a factor predicts returns.",
        "correct": True,
        "concept": "Information Coefficient (IC)",
    },
]

ALL_QUESTIONS = QUIZ_QUESTIONS + TF_QUESTIONS


class LearningModule:
    def __init__(self):
        self.concepts = CONCEPTS
        self.expanded = EXPANDED_CONCEPTS if HAS_EXPANDED else {}
        self.questions = ALL_QUESTIONS.copy()
        random.shuffle(self.questions)

    def explain_concept(self, concept_name: str, detailed: bool = False) -> str:
        """Return definition + code reference for a concept."""
        if concept_name not in self.concepts:
            similar = [c for c in self.concepts if concept_name.lower() in c.lower()]
            if similar:
                concept_name = similar[0]
            else:
                return f"Concept '{concept_name}' not found. Try one of: {', '.join(list(self.concepts.keys())[:10])}..."

        # Use expanded version if available and requested
        if detailed and concept_name in self.expanded:
            return self._explain_detailed(concept_name)

        c = self.concepts[concept_name]
        return f"""
📘 {concept_name}
─────────────────────────────────────────────
{c["definition"]}

🔧 Code reference: {c["code_ref"]}
🧮 Formula: {c.get("formula", "N/A")}
"""

    def _explain_detailed(self, concept_name: str) -> str:
        """Return detailed explanation with examples, pitfalls, and references."""
        if concept_name not in self.expanded:
            return f"Detailed explanation not available for '{concept_name}'"
        c = self.expanded[concept_name]
        return f"""
📘 {concept_name}
{"═" * 70}

**Definition & Context:**
{c["extended"]}

**Concrete Example:**
{c["example"]}

**⚠️  Common Pitfall:**
{c["pitfall"]}

**📚 Academic References:**
{c["reference"]}

**🔧 Code Location:**
{c["code_ref"]}
"""

    def run_quiz(self, num_questions: int = None) -> tuple[int, int]:
        """Run interactive quiz, return (score, total)."""
        qs = self.questions
        if num_questions and num_questions < len(qs):
            qs = random.sample(qs, num_questions)
        score = 0
        for i, q in enumerate(qs, 1):
            print(f"\nQuestion {i}/{len(qs)}")
            print(q["question"])
            if "options" in q:  # multiple choice
                for idx, opt in enumerate(q["options"]):
                    print(f"  {chr(65 + idx)}. {opt}")
                answer = input("Your answer (A/B/C/D): ").strip().upper()
                correct_idx = q["correct"]
                if answer and ord(answer) - 65 == correct_idx:
                    print("✅ Correct!")
                    score += 1
                else:
                    correct_letter = chr(65 + correct_idx)
                    print(
                        f"❌ Wrong. Correct answer: {correct_letter}. {q['options'][correct_idx]}"
                    )
            else:  # true/false
                answer = input("True or False? (T/F): ").strip().upper()
                is_correct = (answer == "T" and q["correct"]) or (
                    answer == "F" and not q["correct"]
                )
                if is_correct:
                    print("✅ Correct!")
                    score += 1
                else:
                    print(f"❌ Wrong. Correct answer: {'True' if q['correct'] else 'False'}")
            # Show concept
            concept = q.get("concept", "General")
            print(f"📚 Related concept: {concept}")
        print(f"\n🎯 Final score: {score}/{len(qs)} ({score / len(qs) * 100:.1f}%)")
        return score, len(qs)

    def generate_html_report(self, output_file: str = "learning_report.html"):
        """Create a standalone HTML report with glossary and quiz."""
        html = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Institutional Alpha – Learning Module</title>
<style>
body { font-family: 'Segoe UI', sans-serif; max-width: 1000px; margin: auto; padding: 20px; background: #f5f5f5; }
h1, h2 { color: #1a3d72; }
.card { background: white; border-left: 4px solid #9a6f1e; margin: 15px 0; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.code { font-family: monospace; background: #eee; padding: 6px; border-radius: 4px; }
.footer { margin-top: 40px; font-size: 12px; color: gray; text-align: center; }
</style>
</head>
<body>
<h1>📚 Institutional Alpha – Learning Module</h1>
<p>Concepts from the Damodaran‑aligned valuation framework, with code references from the <code>institutional-alpha</code> backtest engine.</p>
<h2>📖 Glossary</h2>
"""
        for name, data in self.concepts.items():
            html += f"""
<div class='card'>
    <strong>{name}</strong><br>
    {data["definition"]}<br>
    <span class='code'>🔧 Code: {data["code_ref"]}</span>
    {f"<br>🧮 Formula: {data['formula']}" if data.get("formula") else ""}
</div>"""
        html += "<h2>📝 Sample Quiz Questions</h2><ul>"
        for q in random.sample(self.questions, min(10, len(self.questions))):
            html += f"<li><strong>{q['question']}</strong><br>"
            if "options" in q:
                html += "<ul>" + "".join(f"<li>{opt}</li>" for opt in q["options"]) + "</ul>"
            else:
                html += f"<em>Answer: {q['correct']}</em>"
            html += f"<br><span style='font-size:0.9em; color:#666;'>Concept: {q.get('concept', '')}</span></li>"
        html += "</ul><div class='footer'>Generated by learning_module.py – run again for updated content.</div></body></html>"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML report saved to {output_file}")

    def generate_markdown_notes(self, output_file: str = "concepts.md") -> None:
        """Generate detailed markdown notes for all concepts."""
        source = self.expanded if HAS_EXPANDED else self.concepts
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Institutional Alpha – Concept Library\n\n")
            f.write(
                "Comprehensive reference for institutional finance concepts in the backtest engine.\n\n"
            )
            f.write("---\n\n")
            for i, (name, data) in enumerate(sorted(source.items()), 1):
                f.write(f"## {i}. {name}\n\n")
                if HAS_EXPANDED and "extended" in data:
                    f.write(f"### Definition\n{data['extended']}\n\n")
                    f.write(f"### Example\n{data['example']}\n\n")
                    f.write(f"### Common Pitfall\n{data['pitfall']}\n\n")
                    f.write(f"### References\n{data['reference']}\n\n")
                    f.write(f"### Code Location\n```\n{data['code_ref']}\n```\n\n")
                else:
                    f.write(f"**Definition:** {data['definition']}\n\n")
                    f.write(f"**Code reference:** {data['code_ref']}\n\n")
                    if data.get("formula"):
                        f.write(f"**Formula:** {data['formula']}\n\n")
                f.write("---\n\n")
        print(f"Markdown notes saved to {output_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Institutional Alpha Learning Module")
    parser.add_argument(
        "--mode",
        choices=["interactive", "quiz", "report", "concept", "markdown"],
        default="interactive",
        help="Mode: interactive, quiz, concept lookup, report (HTML), or markdown export",
    )
    parser.add_argument("--concept", type=str, help="Concept name to explain (for --mode concept)")
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed explanation with examples (requires expanded library)",
    )
    parser.add_argument("--quiz_questions", type=int, default=10, help="Number of quiz questions")
    args = parser.parse_args()

    lm = LearningModule()

    if args.mode == "concept" and args.concept:
        print(lm.explain_concept(args.concept, detailed=args.detailed))
    elif args.mode == "quiz":
        lm.run_quiz(args.quiz_questions)
    elif args.mode == "report":
        lm.generate_html_report()
    elif args.mode == "markdown":
        lm.generate_markdown_notes()
    else:  # interactive
        while True:
            print("\n" + "=" * 50)
            print("📖 Institutional Alpha Learning Module")
            print("=" * 50)
            print("1. Explain a concept")
            print("2. Take a quiz")
            print("3. Generate HTML report")
            print("4. Generate Markdown notes")
            print("5. List all concepts")
            print("0. Exit")
            choice = input("Select option: ").strip()
            if choice == "1":
                concept = input("Enter concept name (or partial): ")
                detailed_opt = (
                    input("Detailed explanation? (y/n, default n): ").strip().lower() == "y"
                )
                print(lm.explain_concept(concept, detailed=detailed_opt))
            elif choice == "2":
                n = input("Number of questions (default 10): ")
                n = int(n) if n.isdigit() else 10
                lm.run_quiz(n)
            elif choice == "3":
                lm.generate_html_report()
            elif choice == "4":
                lm.generate_markdown_notes()
            elif choice == "5":
                for c in sorted(lm.concepts.keys()):
                    print(f"  • {c}")
            elif choice == "0":
                break
            else:
                print("Invalid choice")
        print("Goodbye!")


if __name__ == "__main__":
    main()
