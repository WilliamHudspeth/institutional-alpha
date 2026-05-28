#!/usr/bin/env python3
"""Bayesian thesis updating: evidence → posterior probability revision.

Demonstrates:
- Creating initial thesis with scenarios
- Incorporating evidence (earnings, guidance, macro)
- Bayesian probability updates
- Confidence tracking
- Thesis evolution
"""

from datetime import datetime

from iam.thesis.bayesian.evidence import Evidence, ScenarioLikelihood
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.bayesian.ui import (
    ThesisTimeline,
    format_bayesian_update_full,
    format_scenario_migration,
)
from iam.thesis.bayesian.updater import BayesianUpdater


def main() -> None:
    """Run Bayesian thesis example."""

    print("\n" + "=" * 80)
    print("BAYESIAN THESIS UPDATING EXAMPLE")
    print("=" * 80 + "\n")

    ticker = "MSFT"
    initial_price = 450.0

    # 1. Create initial thesis with three scenarios
    print("1. INITIAL INVESTMENT THESIS")
    print("-" * 80)

    priors = [
        ScenarioPrior(label="Bear Case", probability=0.20),
        ScenarioPrior(label="Base Case", probability=0.60),
        ScenarioPrior(label="Bull Case", probability=0.20),
    ]

    print(f"Ticker: {ticker}")
    print(f"Initial Price: ${initial_price:.2f}")
    print("")

    prior_dict = {p.label: p.probability for p in priors}
    print("Initial Scenario Probabilities:")
    for scenario, prob in prior_dict.items():
        bar = "█" * int(prob * 30)
        print(f"  {scenario:<15} {bar:<30} {prob:.1%}")
    print("")

    # Create timeline tracker
    timeline = ThesisTimeline(ticker, prior_dict)

    # 2. Evidence 1: Earnings Beat
    print("\n2. EVIDENCE 1: EARNINGS BEAT")
    print("-" * 80)

    earnings_evidence = Evidence(
        type="EARNINGS_BEAT",
        description="Q1 EPS beat by 8%, raised FY guidance by 5%",
        likelihoods={
            "Bear Case": ScenarioLikelihood(0.15),  # Low prob of beat under bear
            "Base Case": ScenarioLikelihood(0.60),  # Expected under base
            "Bull Case": ScenarioLikelihood(0.95),  # Very likely under bull
        },
        reliability=0.95,  # High reliability (official earnings)
    )

    print(f"Evidence: {earnings_evidence.description}")
    print(f"Reliability: {earnings_evidence.reliability:.0%}")
    print("")

    print("Likelihoods (P(Evidence|Scenario)):")
    for scenario, likelihood in earnings_evidence.likelihoods.items():
        prob = likelihood.probability
        print(f"  {scenario:<15} {prob:.2f}x (dampened: {earnings_evidence.get_dampened_likelihood(scenario):.2f}x)")
    print("")

    # Update thesis with evidence
    posteriors_1 = BayesianUpdater.update(priors, earnings_evidence)
    posterior_dict_1 = {p.label: p.probability for p in posteriors_1}

    print("Updated Scenario Probabilities:")
    for scenario, prob in posterior_dict_1.items():
        prior = prior_dict[scenario]
        change = prob - prior
        direction = "↑" if change > 0 else "↓" if change < 0 else "="
        print(f"  {scenario:<15} {prior:.1%} → {prob:.1%}  {direction} {abs(change):+.1%}")
    print("")

    timeline.add_update(
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "EARNINGS_BEAT",
        prior_dict,
        posterior_dict_1,
    )

    priors = posteriors_1  # Update priors for next evidence

    # 3. Evidence 2: Macro Shock
    print("\n3. EVIDENCE 2: MACRO SHOCK")
    print("-" * 80)

    macro_evidence = Evidence(
        type="MACRO_SHOCK",
        description="Fed hawkish pivot, 25bp more hikes expected. Tech valuation pressure.",
        likelihoods={
            "Bear Case": ScenarioLikelihood(0.70),  # Likely under bear
            "Base Case": ScenarioLikelihood(0.45),  # Moderate impact on base
            "Bull Case": ScenarioLikelihood(0.20),  # Hurts bull case
        },
        reliability=0.75,  # Medium reliability (macro forecasting is noisy)
    )

    print(f"Evidence: {macro_evidence.description}")
    print(f"Reliability: {macro_evidence.reliability:.0%}")
    print("")

    print("Likelihoods:")
    for scenario, likelihood in macro_evidence.likelihoods.items():
        prob = likelihood.probability
        print(f"  {scenario:<15} {prob:.2f}x (dampened: {macro_evidence.get_dampened_likelihood(scenario):.2f}x)")
    print("")

    posteriors_2 = BayesianUpdater.update(priors, macro_evidence)
    posterior_dict_2 = {p.label: p.probability for p in posteriors_2}

    print("Updated Scenario Probabilities:")
    for scenario, prob in posterior_dict_2.items():
        prior = prior_dict[scenario]
        current = posterior_dict_1[scenario]
        change = prob - prior
        direction = "↑" if prob > current else "↓" if prob < current else "="
        print(f"  {scenario:<15} {current:.1%} → {prob:.1%}  {direction} {abs(change):+.1%}")
    print("")

    timeline.add_update(
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "MACRO_SHOCK",
        posterior_dict_1,
        posterior_dict_2,
    )

    priors = posteriors_2

    # 4. Evidence 3: Analyst Upgrade
    print("\n4. EVIDENCE 3: ANALYST UPGRADE")
    print("-" * 80)

    analyst_evidence = Evidence(
        type="ANALYST_UPGRADE",
        description="Goldman Sachs upgraded to BUY, $550 PT (23% upside). AI TAM expansion.",
        likelihoods={
            "Bear Case": ScenarioLikelihood(0.25),  # Skeptical on bear
            "Base Case": ScenarioLikelihood(0.70),  # Supportive of base
            "Bull Case": ScenarioLikelihood(0.85),  # Very bullish
        },
        reliability=0.65,  # Medium reliability (analyst estimates variable)
    )

    print(f"Evidence: {analyst_evidence.description}")
    print(f"Reliability: {analyst_evidence.reliability:.0%}")
    print("")

    posteriors_3 = BayesianUpdater.update(priors, analyst_evidence)
    posterior_dict_3 = {p.label: p.probability for p in posteriors_3}

    print("Updated Scenario Probabilities:")
    for scenario, prob in posterior_dict_3.items():
        current = posterior_dict_2[scenario]
        change = prob - current
        direction = "↑" if change > 0 else "↓" if change < 0 else "="
        print(f"  {scenario:<15} {current:.1%} → {prob:.1%}  {direction} {abs(change):+.1%}")
    print("")

    timeline.add_update(
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ANALYST_UPGRADE",
        posterior_dict_2,
        posterior_dict_3,
    )

    # 5. Summary comparison
    print("\n5. THESIS EVOLUTION SUMMARY")
    print("-" * 80)

    prior_max = max(prior_dict.values())
    final_max = max(posterior_dict_3.values())
    final_most_likely = max(posterior_dict_3.items(), key=lambda x: x[1])[0]

    confidence_delta = final_max - prior_max

    print(f"Initial Thesis Confidence: {prior_max:.1%} ({max(prior_dict.items(), key=lambda x: x[1])[0]})")
    print(f"Final Thesis Confidence:   {final_max:.1%} ({final_most_likely})")
    print(f"Confidence Delta:          {confidence_delta:+.1%}")
    print("")

    if confidence_delta > 0.05:
        print("✓ EVIDENCE INCREASED CONVICTION IN MOST LIKELY SCENARIO")
    elif confidence_delta < -0.05:
        print("⚠ EVIDENCE INCREASED UNCERTAINTY")
    else:
        print("= CONVICTION STABLE")
    print("")

    # 6. Full update visualization
    print("\n6. FINAL BAYESIAN UPDATE VISUALIZATION")
    print("-" * 80)

    final_update = format_bayesian_update_full(
        ticker=ticker,
        evidence_type="ANALYST_UPGRADE",
        evidence_description=analyst_evidence.description,
        evidence_reliability=analyst_evidence.reliability,
        prior_probs=posterior_dict_2,
        posterior_probs=posterior_dict_3,
        scenario_impacts={
            s: analyst_evidence.get_dampened_likelihood(s) for s in analyst_evidence.likelihoods.keys()
        },
    )
    print(final_update)

    # 7. Timeline
    print("\n7. THESIS EVOLUTION TIMELINE")
    print("-" * 80)

    for line in timeline.format_timeline():
        print(line)

    print("=" * 80)
    print("Bayesian theorem enables:")
    print("  ✓ Formal probability updating (not subjective rationalizing)")
    print("  ✓ Evidence reliability weighting (preventing overfitting)")
    print("  ✓ Scenario tracking (bear/base/bull probabilities)")
    print("  ✓ Confidence measurement (when do we increase/decrease conviction)")
    print("  ✓ Thesis audit trail (what evidence moved us)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
