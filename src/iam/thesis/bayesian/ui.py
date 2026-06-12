"""UI rendering for Bayesian thesis updates.

Displays:
- Scenario probability migration
- Confidence delta tracking
- Evidence impact visualization
- Thesis evolution timeline
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iam.ui.panels import BasePanel

if TYPE_CHECKING:
    from iam.ui.state import TerminalUIState


class BayesianUpdatePanel(BasePanel):
    """Display Bayesian update results."""

    def render(self, state: TerminalUIState) -> str:
        """Render Bayesian update visualization."""
        # Placeholder - will be integrated with BayesianState
        return ""


def format_scenario_migration(
    prior_probs: dict[str, float],
    posterior_probs: dict[str, float],
) -> list[str]:
    """Format scenario probability changes.

    Args:
        prior_probs: Dict mapping scenario name -> prior probability
        posterior_probs: Dict mapping scenario name -> posterior probability

    Returns:
        List of formatted lines
    """
    lines = []

    lines.append("SCENARIO PROBABILITY MIGRATION")
    lines.append("-" * 70)
    lines.append(f"{'Scenario':<20} {'Prior':<15} {'Posterior':<15} {'Change':<15}")
    lines.append("-" * 70)

    all_scenarios = set(prior_probs.keys()) | set(posterior_probs.keys())

    for scenario_name in sorted(all_scenarios):
        prior = prior_probs.get(scenario_name, 0.0)
        posterior = posterior_probs.get(scenario_name, 0.0)
        change = posterior - prior

        direction = "↑" if change > 0 else "↓" if change < 0 else "="
        _probability_bar(posterior, width=30)

        lines.append(
            f"{scenario_name:<20} {prior:>13.1%}  {posterior:>13.1%}  "
            f"{direction} {abs(change):>12.1%}"
        )

    return lines


def format_evidence_summary(
    evidence_type: str,
    description: str,
    reliability: float,
    scenario_impacts: dict[str, float],
) -> list[str]:
    """Format evidence and its impact.

    Args:
        evidence_type: Type of evidence
        description: Description of what happened
        reliability: How reliable is this evidence (0-1)
        scenario_impacts: Dict mapping scenario -> likelihood

    Returns:
        List of formatted lines
    """
    lines = []

    lines.append("EVIDENCE IMPACT ANALYSIS")
    lines.append("-" * 70)
    lines.append(f"Type: {evidence_type}")
    lines.append(f"Description: {description}")
    lines.append(f"Reliability: {reliability:.0%}")
    lines.append("")

    lines.append("Likelihood under each scenario:")
    for scenario, likelihood in sorted(scenario_impacts.items(), key=lambda x: x[1], reverse=True):
        bar = _likelihood_bar(likelihood, width=40)
        lines.append(f"  {scenario:<15} {bar} {likelihood:.2f}x")

    return lines


def format_confidence_delta(
    prior_max_prob: float,
    posterior_max_prob: float,
    most_likely_scenario: str,
) -> list[str]:
    """Format confidence change in most likely scenario.

    Args:
        prior_max_prob: Highest probability in prior
        posterior_max_prob: Highest probability in posterior
        most_likely_scenario: Name of most likely scenario

    Returns:
        List of formatted lines
    """
    lines = []

    delta = posterior_max_prob - prior_max_prob

    lines.append("CONFIDENCE DELTA")
    lines.append("-" * 70)
    lines.append(f"Most Likely Scenario: {most_likely_scenario}")
    lines.append(f"Prior Confidence: {prior_max_prob:.1%}")
    lines.append(f"Posterior Confidence: {posterior_max_prob:.1%}")
    lines.append(f"Change: {delta:+.1%}")
    lines.append("")

    if delta > 0.05:
        lines.append("✓ EVIDENCE INCREASED CONFIDENCE")
        lines.append("  Market signal aligns with thesis assumptions")
    elif delta < -0.05:
        lines.append("⚠ EVIDENCE REDUCED CONFIDENCE")
        lines.append("  Increased uncertainty across scenarios")
    else:
        lines.append("= CONFIDENCE UNCHANGED")
        lines.append("  Evidence distributed across scenarios")

    return lines


def format_bayesian_update_full(
    ticker: str,
    evidence_type: str,
    evidence_description: str,
    evidence_reliability: float,
    prior_probs: dict[str, float],
    posterior_probs: dict[str, float],
    scenario_impacts: dict[str, float],
) -> str:
    """Format complete Bayesian update for display.

    Args:
        ticker: Security ticker
        evidence_type: Type of evidence
        evidence_description: What happened
        evidence_reliability: How reliable (0-1)
        prior_probs: Prior scenario probabilities
        posterior_probs: Posterior scenario probabilities
        scenario_impacts: Likelihood multipliers

    Returns:
        Formatted string for display
    """
    lines = []

    rule = "═" * 80
    lines.append(rule)
    lines.append(f"BAYESIAN THESIS UPDATE | {ticker}".ljust(80))
    lines.append(rule)
    lines.append("")

    # Evidence summary
    for line in format_evidence_summary(
        evidence_type, evidence_description, evidence_reliability, scenario_impacts
    ):
        lines.append(line)
    lines.append("")

    # Scenario migration
    for line in format_scenario_migration(prior_probs, posterior_probs):
        lines.append(line)
    lines.append("")

    # Confidence delta
    prior_max = max(prior_probs.values()) if prior_probs else 0
    posterior_max = max(posterior_probs.values()) if posterior_probs else 0
    most_likely = max(posterior_probs.items(), key=lambda x: x[1])[0] if posterior_probs else ""

    for line in format_confidence_delta(prior_max, posterior_max, most_likely):
        lines.append(line)

    lines.append(rule)

    return "\n".join(lines)


def _probability_bar(prob: float, width: int = 30) -> str:
    """Create visual probability bar.

    Args:
        prob: Probability 0-1
        width: Bar width in characters

    Returns:
        Visual bar
    """
    filled = int(prob * width)
    return "█" * filled + "░" * (width - filled)


def _likelihood_bar(likelihood: float, width: int = 30) -> str:
    """Create visual likelihood bar.

    Args:
        likelihood: Likelihood multiplier (1.0 = neutral)
        width: Bar width

    Returns:
        Visual bar
    """
    if likelihood >= 1.0:
        # Bullish (likelihood > 1)
        scaled = min((likelihood - 1.0) * width / 2, width)
        return "→" * int(scaled) + " " * (width - int(scaled))
    else:
        # Bearish (likelihood < 1)
        scaled = min((1.0 - likelihood) * width / 2, width)
        return "←" * int(scaled) + " " * (width - int(scaled))


class ThesisTimeline:
    """Track thesis evolution over time."""

    def __init__(self, ticker: str, initial_probabilities: dict[str, float]) -> None:
        self.ticker = ticker
        self.events: list[dict] = [
            {
                "timestamp": None,
                "event": "Initial Thesis",
                "probabilities": initial_probabilities.copy(),
            }
        ]

    def add_update(
        self,
        timestamp: str,
        evidence_type: str,
        prior_probs: dict[str, float],
        posterior_probs: dict[str, float],
    ) -> None:
        """Add an update to the timeline."""
        self.events.append(
            {
                "timestamp": timestamp,
                "event": evidence_type,
                "prior": prior_probs,
                "posterior": posterior_probs,
                "probabilities": posterior_probs.copy(),
            }
        )

    def format_timeline(self) -> list[str]:
        """Format thesis evolution timeline."""
        lines = []

        lines.append(f"THESIS EVOLUTION TIMELINE | {self.ticker}")
        lines.append("=" * 80)
        lines.append("")

        for i, event in enumerate(self.events):
            timestamp = event.get("timestamp", "Initial")
            event_type = event.get("event", "—")
            probs = event.get("probabilities", {})

            lines.append(f"[{i}] {timestamp:<15} | {event_type}")

            # Show scenario probabilities
            for scenario, prob in sorted(probs.items(), key=lambda x: x[1], reverse=True):
                bar = _probability_bar(prob, width=25)
                lines.append(f"     {scenario:<15} {bar} {prob:.1%}")

            lines.append("")

        return lines
