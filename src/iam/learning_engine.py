#!/usr/bin/env python3
"""
Institutional Alpha — Enhanced Learning Engine
===============================================

Interactive CFA / Institutional Finance learning platform integrated into
the institutional-alpha backtest engine.

Combines concept glossary, interactive quizzes, difficulty progression,
code mapping, and learning paths.

Features:
- Concept browser with code references
- Difficulty-stratified quizzes
- Concept-to-implementation mapping
- Glossary export (JSON, markdown, HTML)
- Score tracking and results analysis
- Learning paths and prerequisites

Usage:
    python -m iam.learning_engine
    python learning_module.py [--export-format json|markdown|html]
"""

import json
import random
import textwrap
from dataclasses import asdict, dataclass

try:
    from iam.concept_library_expanded import EXPANDED_CONCEPTS

    HAS_EXPANDED = True
except ImportError:
    HAS_EXPANDED = False


# ============================================================
# DATA MODELS
# ============================================================


@dataclass
class Concept:
    """Represents a core institutional finance concept."""

    name: str
    category: str  # Valuation, Risk, Quantitative, Data, etc.
    definition: str
    implementation: str  # Code file and function reference
    tags: list[str]
    difficulty: str = "intermediate"  # easy, intermediate, advanced
    prerequisites: list[str] | None = None

    def __post_init__(self):
        if self.prerequisites is None:
            self.prerequisites = []

    def to_dict(self):
        return asdict(self)


@dataclass
class Question:
    """Represents a quiz question."""

    prompt: str
    choices: list[str]
    answer: str
    explanation: str
    difficulty: str  # easy, medium, hard
    concept: str  # Links to Concept.name
    tags: list[str] | None = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def to_dict(self):
        return asdict(self)


# ============================================================
# CORE CONCEPT LIBRARY (Enhanced)
# ============================================================

CORE_CONCEPTS = [
    Concept(
        name="Reverse DCF",
        category="Valuation",
        definition=(
            "Reverse DCF starts with the current stock price and solves for the growth "
            "assumptions the market is pricing in. This forces articulation of what growth "
            "the market is expecting—a powerful check on valuation reasonableness."
        ),
        implementation="src/iam/backtest/runner.py → reverse DCF computed in Stage 1",
        tags=["expectations investing", "intrinsic value", "DCF"],
        difficulty="intermediate",
        prerequisites=[],
    ),
    Concept(
        name="Information Coefficient (IC)",
        category="Quantitative Finance",
        definition=(
            "Cross-sectional Spearman rank correlation between factor scores and "
            "forward returns. Measures raw predictive signal quality before accounting "
            "for costs or volatility."
        ),
        implementation="src/iam/backtest/metrics.py → ic_spearman()",
        tags=["factor investing", "alpha", "signal"],
        difficulty="intermediate",
        prerequisites=[],
    ),
    Concept(
        name="IC Information Ratio (ICIR)",
        category="Quantitative Finance",
        definition=(
            "Mean IC divided by the standard deviation of IC. Measures consistency and "
            "reliability of factor predictive power. A high but volatile IC (low ICIR) is "
            "less useful than a modest but consistent IC (high ICIR)."
        ),
        implementation="src/iam/backtest/metrics.py → compute_statistics() → icir",
        tags=["risk adjusted alpha", "factor stability"],
        difficulty="intermediate",
        prerequisites=["Information Coefficient (IC)"],
    ),
    Concept(
        name="Multi-Horizon IC",
        category="Quantitative Finance",
        definition=(
            "Computing IC at multiple forward return horizons (1m, 3m, 6m, 12m) to "
            "characterize signal decay. Fast decay suggests momentum/noise; slow decay "
            "suggests fundamental factor."
        ),
        implementation="src/iam/backtest/runner.py → discovers fwd_ret_* columns",
        tags=["factor timing", "signal decay"],
        difficulty="advanced",
        prerequisites=["Information Coefficient (IC)"],
    ),
    Concept(
        name="Value-Weighted IC",
        category="Quantitative Finance",
        definition=(
            "Weighted Spearman rank correlation using market cap as weights. More relevant "
            "for institutional investors who cannot take material positions in micro-caps."
        ),
        implementation="src/iam/backtest/metrics.py → ic_value_weighted()",
        tags=["portfolio construction", "institutional"],
        difficulty="advanced",
        prerequisites=["Information Coefficient (IC)"],
    ),
    Concept(
        name="SOTP Valuation",
        category="Valuation",
        definition=(
            "Sum-of-the-Parts valuation values each business segment independently using "
            "distinct assumptions and discount rates. Essential for conglomerates where "
            "segments have different risk profiles."
        ),
        implementation="src/iam/backtest/runner.py → SOTP logic",
        tags=["segments", "conglomerate", "DCF"],
        difficulty="advanced",
        prerequisites=["Reverse DCF"],
    ),
    Concept(
        name="Geographic ERP",
        category="Risk",
        definition=(
            "Weighted equity risk premium based on where a company actually generates "
            "revenue, not listing domicile. Blends country ERPs by revenue share for "
            "globally diversified companies."
        ),
        implementation="src/iam/backtest/runner.py → geo_blended_erp()",
        tags=["country risk", "cost of equity"],
        difficulty="advanced",
        prerequisites=[],
    ),
    Concept(
        name="Terminal Growth Cap",
        category="Valuation",
        definition=(
            "Terminal growth should not exceed the long-run risk-free rate. No company "
            "can outgrow the economy forever. Enforces economic consistency."
        ),
        implementation="src/iam/backtest/runner.py → terminal_growth = min(g, Rf)",
        tags=["terminal value", "perpetuity"],
        difficulty="intermediate",
        prerequisites=[],
    ),
    Concept(
        name="Through-Cycle Normalization",
        category="Valuation",
        definition=(
            "Uses normalized earnings across expansion and contraction cycles instead of "
            "peak earnings. Critical for cyclical industries (commodities, credit, semis) "
            "where peak earnings are not sustainable."
        ),
        implementation="src/iam/backtest/runner.py → normalised_earnings()",
        tags=["cyclicals", "mean reversion"],
        difficulty="advanced",
        prerequisites=[],
    ),
    Concept(
        name="Operating Leverage",
        category="Risk",
        definition=(
            "High fixed costs relative to variable costs amplify earnings volatility. "
            "This increases effective equity beta and should be reflected in the discount rate."
        ),
        implementation="src/iam/backtest/runner.py → beta_adjusted for leverage",
        tags=["beta", "fixed costs"],
        difficulty="intermediate",
        prerequisites=[],
    ),
    Concept(
        name="Walk-Forward Optimization",
        category="Backtesting",
        definition=(
            "Rolling training/testing windows that optimize weights on past data and test "
            "on out-of-sample future data. Prevents overfitting and ensures robustness."
        ),
        implementation="src/iam/backtest/weight_optimizer.py → WalkForwardOptimizer",
        tags=["backtesting", "quant"],
        difficulty="intermediate",
        prerequisites=[],
    ),
    Concept(
        name="Bootstrap Stability",
        category="Statistics",
        definition=(
            "Repeated random resampling (with replacement) of historical data to estimate "
            "the sampling distribution of optimal weights. Identifies unstable factors."
        ),
        implementation="src/iam/backtest/weight_optimizer.py → BootstrapStability",
        tags=["monte carlo", "resampling"],
        difficulty="advanced",
        prerequisites=[],
    ),
    Concept(
        name="Shrinkage (Bayesian)",
        category="Statistics",
        definition=(
            "Pull extreme parameter estimates toward a conservative prior. Reduces variance "
            "at small cost of bias. Applied to factor weights: final = λ*optimized + (1-λ)*prior."
        ),
        implementation="src/iam/backtest/weight_optimizer.py → shrinkage_lambda",
        tags=["regularization", "bias-variance"],
        difficulty="advanced",
        prerequisites=[],
    ),
    Concept(
        name="Bayesian Thesis Updating",
        category="Decision Theory",
        definition=(
            "Update investment thesis probability when new evidence arrives using Bayes' rule: "
            "Posterior = Likelihood(evidence|thesis) * Prior / Evidence_marginal. Forces "
            "quantification of belief updates."
        ),
        implementation="src/iam/backtest/runner.py → thesis engine (Phase 3.2)",
        tags=["probability", "posterior", "priors"],
        difficulty="advanced",
        prerequisites=[],
    ),
    Concept(
        name="Narrative-Consistency Validation",
        category="Validation",
        definition=(
            "Check that valuation model inputs don't contradict each other. E.g., if "
            "g=20%, then reinvestment*ROIC should equal 20%. Internal inconsistency "
            "invalidates output."
        ),
        implementation="src/iam/backtest/runner.py → validate_growth_consistency()",
        tags=["model integrity", "sanity checks"],
        difficulty="intermediate",
        prerequisites=[],
    ),
    Concept(
        name="Point-In-Time Data",
        category="Data Engineering",
        definition=(
            "Use only data available at that historical date to prevent lookahead bias. "
            "If using revised earnings, only use revisions known at that time, not current "
            "estimates."
        ),
        implementation="src/iam/backtest/prices.py → load_price_block() with date checks",
        tags=["backtesting", "data integrity"],
        difficulty="intermediate",
        prerequisites=[],
    ),
    Concept(
        name="Survivorship Bias",
        category="Data Engineering",
        definition=(
            "Bias caused by excluding failed or delisted companies from historical tests. "
            "Artificially inflates backtest returns. Must include bankrupt companies with "
            "negative returns."
        ),
        implementation="src/iam/backtest/universe.py → include delistings",
        tags=["bias", "historical data"],
        difficulty="easy",
        prerequisites=[],
    ),
    Concept(
        name="Manifest.json Reproducibility",
        category="Engineering",
        definition=(
            "Every backtest saves git commit, Python version, config, factor weights, "
            "data hashes. Enables exact reproducibility months later and audit trail."
        ),
        implementation="src/iam/backtest/manifest.py → BacktestManifest",
        tags=["reproducibility", "audit"],
        difficulty="easy",
        prerequisites=[],
    ),
    Concept(
        name="Redundant Data Fetching",
        category="Data Engineering",
        definition=(
            "Try multiple free data sources in priority order (SEC EDGAR → yfinance → Stooq). "
            "Cache in SQLite. Falls back automatically on throttle/outage."
        ),
        implementation="src/iam/data/fetcher.py → RedundantDataFetcher",
        tags=["data resilience", "fault tolerance"],
        difficulty="intermediate",
        prerequisites=[],
    ),
    Concept(
        name="Epistemic Humility",
        category="Philosophy",
        definition=(
            "Present valuation as probability distributions and scenarios rather than "
            "false point estimates. Acknowledge uncertainty and model limitations."
        ),
        implementation="src/iam/backtest/runner.py → scenario_valuation()",
        tags=["uncertainty", "risk"],
        difficulty="easy",
        prerequisites=[],
    ),
]


# ============================================================
# QUIZ BANK
# ============================================================

CORE_QUESTIONS = [
    Question(
        prompt="What does Reverse DCF calculate?",
        choices=[
            "Past intrinsic value",
            "Implied market growth expectations",
            "Historical beta",
            "Enterprise value only",
        ],
        answer="Implied market growth expectations",
        explanation=(
            "Reverse DCF solves for the growth and margin assumptions implied by "
            "the current stock price, revealing what the market is pricing in."
        ),
        difficulty="easy",
        concept="Reverse DCF",
    ),
    Question(
        prompt="Why is Point-In-Time data critical?",
        choices=[
            "It increases volatility",
            "It reduces memory usage",
            "It prevents lookahead bias in backtests",
            "It improves chart rendering",
        ],
        answer="It prevents lookahead bias in backtests",
        explanation=(
            "Using future revised data in historical tests creates artificial alpha. "
            "PIT ensures only information available at that date is used."
        ),
        difficulty="easy",
        concept="Point-In-Time Data",
    ),
    Question(
        prompt="What does Information Coefficient (IC) measure?",
        choices=[
            "Cash flow stability",
            "Factor predictive power via rank correlation",
            "Market beta",
            "Volatility clustering",
        ],
        answer="Factor predictive power via rank correlation",
        explanation=(
            "IC is Spearman rank correlation between factor scores and forward returns. "
            "Higher IC = stronger predictive signal."
        ),
        difficulty="medium",
        concept="Information Coefficient (IC)",
    ),
    Question(
        prompt="Why should terminal growth be capped at Rf?",
        choices=[
            "To reduce taxes",
            "Because firms cannot outgrow the economy forever",
            "To increase DCF speed",
            "Because CAPM requires it",
        ],
        answer="Because firms cannot outgrow the economy forever",
        explanation=(
            "A company growing faster than nominal GDP in perpetuity violates economic "
            "reality. Rf approximates long-run nominal GDP growth."
        ),
        difficulty="medium",
        concept="Terminal Growth Cap",
    ),
    Question(
        prompt="What problem does Walk-Forward optimization solve?",
        choices=[
            "Inflation risk",
            "Overfitting to historical data",
            "Liquidity constraints",
            "Accounting fraud detection",
        ],
        answer="Overfitting to historical data",
        explanation=(
            "Walk-forward rolling windows ensure models are tested out-of-sample, "
            "revealing true robustness vs. data-fitting artifacts."
        ),
        difficulty="medium",
        concept="Walk-Forward Optimization",
    ),
    Question(
        prompt="What is survivorship bias?",
        choices=[
            "Ignoring bankrupt companies from backtest data",
            "Using only monthly returns",
            "Overestimating tax impacts",
            "Incorrect beta calculation",
        ],
        answer="Ignoring bankrupt companies from backtest data",
        explanation=(
            "Excluding failed firms artificially inflates historical performance. "
            "Bankrupt companies deliver -100% returns and must be included."
        ),
        difficulty="easy",
        concept="Survivorship Bias",
    ),
    Question(
        prompt="What does ICIR measure?",
        choices=[
            "Average factor predictive power",
            "Consistency of factor predictive power",
            "Volatility of stock returns",
            "Correlation with market index",
        ],
        answer="Consistency of factor predictive power",
        explanation=(
            "ICIR = mean(IC) / std(IC). A high ICIR means the factor works reliably; "
            "low ICIR means it's erratic even if the mean IC is positive."
        ),
        difficulty="medium",
        concept="IC Information Ratio (ICIR)",
    ),
    Question(
        prompt="Why use Through-Cycle normalization for cyclicals?",
        choices=[
            "To increase earnings",
            "To average earnings across boom and bust cycles",
            "To reduce tax liability",
            "Because regulators require it",
        ],
        answer="To average earnings across boom and bust cycles",
        explanation=(
            "Peak earnings in boom years are unsustainable. Normalizing across a full "
            "cycle gives a true sustainable earnings power estimate."
        ),
        difficulty="medium",
        concept="Through-Cycle Normalization",
    ),
]


# ============================================================
# LEARNING ENGINE
# ============================================================


class LearningEngine:
    """Interactive learning platform for institutional finance concepts."""

    def __init__(self, use_expanded: bool = True):
        self.use_expanded = use_expanded and HAS_EXPANDED
        self.concepts = self._load_concepts()
        self.questions = CORE_QUESTIONS.copy()
        self.score = 0
        self.total = 0

    def _load_concepts(self) -> list[Concept]:
        """Load concepts, optionally merging with expanded library."""
        concepts = CORE_CONCEPTS.copy()

        if self.use_expanded:
            # Add expanded concepts as Concept dataclass instances
            for name, data in EXPANDED_CONCEPTS.items():
                if not any(c.name == name for c in concepts):
                    concepts.append(
                        Concept(
                            name=name,
                            category=data.get("category", "Other"),
                            definition=data["extended"][:200] + "...",
                            implementation=data["code_ref"],
                            tags=[],
                            difficulty="intermediate",
                        )
                    )

        return concepts

    def banner(self):
        """Display welcome banner."""
        print("=" * 70)
        print("INSTITUTIONAL ALPHA — LEARNING ENGINE")
        print("=" * 70)
        print()

    def menu(self):
        """Main interactive menu."""
        while True:
            print("Choose an option:\n")
            print("1. Browse Concepts")
            print("2. Take Quiz")
            print("3. Random Concept Deep-Dive")
            print("4. Export Glossary")
            print("5. Search Concepts")
            print("6. Exit")
            print()

            choice = input("Selection: ").strip()

            if choice == "1":
                self.browse_concepts()
            elif choice == "2":
                self.take_quiz()
            elif choice == "3":
                self.random_concept()
            elif choice == "4":
                self.export_glossary()
            elif choice == "5":
                self.search_concepts()
            elif choice == "6":
                print("\nGoodbye!")
                break
            else:
                print("\nInvalid selection. Please try again.\n")

    def browse_concepts(self):
        """Browse available concepts."""
        print("\nAvailable Concepts:\n")

        for idx, c in enumerate(self.concepts, 1):
            print(f"{idx:2d}. {c.name:40s} ({c.category})")

        try:
            selection = int(input("\nSelect concept #: ")) - 1
            if 0 <= selection < len(self.concepts):
                self._display_concept(self.concepts[selection])
            else:
                print("\nInvalid selection.")
        except ValueError:
            print("\nInvalid input.")

    def _display_concept(self, concept: Concept):
        """Display detailed concept information."""
        print("\n" + "=" * 70)
        print(concept.name)
        print("=" * 70)
        print(f"\nCategory: {concept.category}")
        print(f"Difficulty: {concept.difficulty}")

        if concept.prerequisites:
            print(f"Prerequisites: {', '.join(concept.prerequisites)}")

        print("\nDefinition:")
        print(textwrap.fill(concept.definition, 80))

        print("\nImplementation:")
        print(concept.implementation)

        if concept.tags:
            print("\nTags:")
            print(", ".join(concept.tags))

    def take_quiz(self):
        """Take an interactive quiz."""
        questions = self.questions.copy()
        random.shuffle(questions)

        self.score = 0
        self.total = len(questions)

        for i, q in enumerate(questions, 1):
            print("\n" + "=" * 70)
            print(f"Question {i}/{self.total}")
            print("=" * 70)
            print(q.prompt)
            print()

            for idx, choice in enumerate(q.choices, 1):
                print(f"{idx}. {choice}")

            try:
                ans = int(input("\nAnswer #: ")) - 1

                if 0 <= ans < len(q.choices):
                    selected = q.choices[ans]

                    if selected == q.answer:
                        print("\n✓ Correct!")
                        self.score += 1
                    else:
                        print("\n✗ Incorrect")
                        print(f"Correct Answer: {q.answer}")

                    print("\nExplanation:")
                    print(textwrap.fill(q.explanation, 80))
                else:
                    print("\nInvalid selection.")
            except ValueError:
                print("\nInvalid input.")

        self.show_results()

    def show_results(self):
        """Display quiz results and analysis."""
        pct = (self.score / self.total) * 100 if self.total > 0 else 0

        print("\n" + "=" * 70)
        print("QUIZ RESULTS")
        print("=" * 70)
        print(f"\nScore: {self.score}/{self.total}")
        print(f"Percentage: {pct:.1f}%")
        print()

        if pct >= 90:
            print("🏆 Institutional-Grade Understanding")
        elif pct >= 80:
            print("⭐ Strong CFA-Level Foundation")
        elif pct >= 70:
            print("✓ Solid Working Knowledge")
        elif pct >= 60:
            print("◐ Developing Understanding")
        else:
            print("◯ Needs Reinforcement")

    def random_concept(self):
        """Display a random concept."""
        c = random.choice(self.concepts)

        print()
        self._display_concept(c)

    def search_concepts(self):
        """Search concepts by name or tag."""
        query = input("\nSearch concept (name or tag): ").lower().strip()

        results = [
            c
            for c in self.concepts
            if query in c.name.lower() or any(query in tag.lower() for tag in c.tags)
        ]

        if not results:
            print(f"\nNo concepts found matching '{query}'")
        else:
            print(f"\nFound {len(results)} concept(s):\n")
            for idx, c in enumerate(results, 1):
                print(f"{idx}. {c.name} ({c.category})")

            try:
                selection = int(input("\nSelect concept #: ")) - 1
                if 0 <= selection < len(results):
                    self._display_concept(results[selection])
            except ValueError:
                print("\nInvalid input.")

    def export_glossary(self):
        """Export glossary in multiple formats."""
        print("\nExport Format:")
        print("1. JSON")
        print("2. Markdown")
        print("3. HTML")

        fmt = input("\nSelection: ").strip()

        if fmt == "1":
            self._export_json()
        elif fmt == "2":
            self._export_markdown()
        elif fmt == "3":
            self._export_html()
        else:
            print("\nInvalid selection.")

    def _export_json(self):
        """Export glossary as JSON."""
        output = [c.to_dict() for c in self.concepts]

        filename = "institutional_alpha_glossary.json"
        with open(filename, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n✓ Exported to {filename}")

    def _export_markdown(self):
        """Export glossary as Markdown."""
        filename = "institutional_alpha_glossary.md"
        with open(filename, "w") as f:
            f.write("# Institutional Alpha — Concept Glossary\n\n")
            f.write("Comprehensive reference for institutional finance concepts.\n\n")
            f.write("---\n\n")

            for c in sorted(self.concepts, key=lambda x: x.name):
                f.write(f"## {c.name}\n\n")
                f.write(f"**Category:** {c.category}\n\n")
                f.write(f"**Difficulty:** {c.difficulty}\n\n")
                f.write(f"**Definition:** {c.definition}\n\n")
                f.write(f"**Implementation:** {c.implementation}\n\n")

                if c.tags:
                    f.write(f"**Tags:** {', '.join(c.tags)}\n\n")

                if c.prerequisites:
                    f.write(f"**Prerequisites:** {', '.join(c.prerequisites)}\n\n")

                f.write("---\n\n")

        print(f"\n✓ Exported to {filename}")

    def _export_html(self):
        """Export glossary as HTML."""
        filename = "institutional_alpha_glossary.html"
        with open(filename, "w") as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Institutional Alpha — Concept Glossary</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, sans-serif; max-width: 1000px; margin: auto; padding: 20px; }
        h1 { color: #1a3d72; border-bottom: 3px solid #9a6f1e; }
        .concept { background: white; border-left: 4px solid #9a6f1e; margin: 20px 0; padding: 15px; border-radius: 8px; }
        .concept h2 { margin: 0 0 10px 0; color: #1a3d72; }
        .metadata { font-size: 0.9em; color: #666; margin: 10px 0; }
        .tags { background: #f0f0f0; padding: 8px; border-radius: 4px; font-family: monospace; }
    </style>
</head>
<body>
<h1>📚 Institutional Alpha — Concept Glossary</h1>
<p>Comprehensive reference for institutional finance concepts in the backtest engine.</p>
""")

            for c in sorted(self.concepts, key=lambda x: x.name):
                f.write(f"""
<div class="concept">
    <h2>{c.name}</h2>
    <div class="metadata">
        <strong>Category:</strong> {c.category} |
        <strong>Difficulty:</strong> {c.difficulty}
    </div>
    <p><strong>Definition:</strong> {c.definition}</p>
    <p><strong>Implementation:</strong> <code>{c.implementation}</code></p>
""")
                if c.tags:
                    f.write(f'    <div class="tags">Tags: {", ".join(c.tags)}</div>\n')
                if c.prerequisites:
                    f.write(
                        f"    <p><strong>Prerequisites:</strong> {', '.join(c.prerequisites)}</p>\n"
                    )
                f.write("</div>\n")

            f.write("""
</body>
</html>
""")

        print(f"\n✓ Exported to {filename}")


# ============================================================
# MAIN
# ============================================================


def main():
    """Main entry point."""
    engine = LearningEngine(use_expanded=HAS_EXPANDED)
    engine.banner()
    engine.menu()


if __name__ == "__main__":
    main()
