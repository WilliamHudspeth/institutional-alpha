"""Demonstrates attaching bull/bear theses to a Security and calling show_spread()."""

from iam.data.security import Assumption, Security, Thesis, show_spread
from iam.thesis.engine import ThesisEngine

sec = Security(
    ticker="EXCO",
    name="Example Co.",
    qualitative={"revenue_growth_5y": 0.12, "terminal_margin": 0.20},  # Base assumptions
    theses=[
        Thesis(
            label="Bull",
            fair_value_low=160.0,
            fair_value_high=200.0,
            narrative="Margin expansion drives re-rating; TAM assumption holds.",
            assumptions=[
                Assumption("revenue_growth_5y", 0.18, source="user"),
                Assumption("terminal_margin", 0.30, rationale="Peer ceiling", source="user"),
            ],
        ),
        Thesis(
            label="Bear",
            fair_value_low=80.0,
            fair_value_high=110.0,
            narrative="Competition compresses margins; growth decelerates faster than consensus.",
            assumptions=[
                Assumption("revenue_growth_5y", 0.08, source="user"),
                Assumption("terminal_margin", 0.15, rationale="Structural headwinds", source="user"),
            ],
        ),
    ],
)

print(show_spread(sec))

print("\n--- Programmatic Thesis Engine Output ---")
engine = ThesisEngine()
evaluation = engine.evaluate(sec)

print(engine.render_report(evaluation, current_price=120.0))

print("\n--- Programmatic Simulation Engine Output ---")
# Mock a valuation function that behaves like your Intrinsic DCF stage.
# In the real app, you'd inject something like: 
# `lambda s: FCFEDCF().compute(s).fair_value_per_share`
def mock_intrinsic_dcf(s: Security) -> float:
    qualitative = s.qualitative or {}
    growth = qualitative.get("revenue_growth_5y", 0.10)
    margin = qualitative.get("terminal_margin", 0.20)
    # A simplistic valuation proxy: base * (1 + growth) * margin
    return 1000 * (1 + growth) * margin

simulated_evaluation = engine.simulate(sec, valuation_fn=mock_intrinsic_dcf, spread_pct=0.05)

print("\n" + engine.render_report(simulated_evaluation, current_price=120.0))

print("\nUpdated Security Theses values after simulation:")
print(show_spread(sec))

print("\n--- Sensitivity Analysis Output ---")
sensitivity_results = engine.calculate_sensitivity(
    sec, 
    valuation_fn=mock_intrinsic_dcf, 
    assumption_name="revenue_growth_5y", 
    perturbation=0.10
)
print(engine.render_sensitivity_report(sensitivity_results, "revenue_growth_5y", 0.10))

print("\n=== Bayesian Updating Example ===")

from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood

# 1. Establish Prior Beliefs
priors = [
    ScenarioPrior("Bull", 0.30),
    ScenarioPrior("Bear", 0.70)
]

# 2. Receive New Evidence
evidence = Evidence(
    description="Competitor delays major product launch, relieving margin pressure.",
    signal_strength=0.8,
    likelihoods={
        "Bull": ScenarioLikelihood(0.85),
        "Bear": ScenarioLikelihood(0.15)
    }
)

# 3. Apply Evidence and Generate Report
evaluation = engine.apply_evidence(sec, priors, evidence)
print(engine.render_report(evaluation, current_price=120.0))

