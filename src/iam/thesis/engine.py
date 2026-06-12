"""Thesis engine for evaluating bull/base/bear scenarios."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from iam.data.security import Security
from iam.thesis.bayesian.evidence import Evidence
from iam.thesis.bayesian.priors import ScenarioPrior
from iam.thesis.bayesian.updater import BayesianUpdater


@dataclass
class ThesisEvaluation:
    """The result of evaluating multiple thesis scenarios."""

    best_case: float | None
    worst_case: float | None
    spread: float | None
    narrative: str
    warnings: list[str] = field(default_factory=list)
    expected_value: float | None = None
    posteriors: list[ScenarioPrior] = field(default_factory=list)


class ThesisEngine:
    """Evaluates multiple thesis scenarios for a given Security."""

    def evaluate(self, security: Security) -> ThesisEvaluation:
        warnings: list[str] = []

        if not security.theses:
            return ThesisEvaluation(None, None, None, "No theses defined.", warnings)

        # Gather limits
        lows = [t.fair_value_low for t in security.theses if t.fair_value_low is not None]
        highs = [t.fair_value_high for t in security.theses if t.fair_value_high is not None]

        worst_case = min(lows) if lows else None
        best_case = max(highs) if highs else None
        spread = (
            (best_case - worst_case) if (best_case is not None and worst_case is not None) else None
        )

        self._validate_scenarios(security, warnings)

        return ThesisEvaluation(
            best_case=best_case,
            worst_case=worst_case,
            spread=spread,
            narrative=f"Evaluated {len(security.theses)} scenarios.",
            warnings=warnings,
        )

    def simulate(
        self,
        security: Security,
        valuation_fn: Callable[[Security], float],
        spread_pct: float = 0.05,
    ) -> ThesisEvaluation:
        """Dynamically simulate thesis assumptions and update their fair value ranges.

        Temporarily injects each thesis's assumptions into `security.qualitative`,
        runs the provided `valuation_fn` to compute a point-estimate fair value,
        and expands it into a low/high range.
        """
        warnings: list[str] = []

        if not security.theses:
            return ThesisEvaluation(None, None, None, "No theses defined.", warnings)

        original_qualitative = (
            security.qualitative.copy() if security.qualitative is not None else None
        )

        try:
            for thesis in security.theses:
                # Reset qualitative dictionary for each thesis
                security.qualitative = (
                    original_qualitative.copy() if original_qualitative is not None else {}
                )

                for assumption in thesis.assumptions:
                    security.qualitative[assumption.name] = assumption.value

                try:
                    # Dynamically calculate the fair value point estimate
                    fv_point = valuation_fn(security)

                    # Generate ranges around the dynamic point estimate
                    thesis.fair_value_low = fv_point * (1 - spread_pct)
                    thesis.fair_value_high = fv_point * (1 + spread_pct)
                except Exception as e:
                    warnings.append(f"Failed to simulate thesis '{thesis.label}': {e}")
        finally:
            # Ensure total reversion to the original state
            security.qualitative = original_qualitative

        evaluation = self.evaluate(security)
        evaluation.narrative = f"Dynamically simulated {len(security.theses)} scenarios."
        evaluation.warnings.extend(warnings)
        return evaluation

    def calculate_sensitivity(
        self,
        security: Security,
        valuation_fn: Callable[[Security], float],
        assumption_name: str,
        perturbation: float = 0.10,
    ) -> list[tuple[str, float, float]]:
        """Calculates how fair value changes if a specific assumption is shifted by a percentage.

        Temporarily perturbs an assumption within each thesis, runs the provided
        `valuation_fn`, and returns the before/after point-estimate fair values.

        Returns:
            A list of tuples: (thesis_label, original_fair_value, perturbed_fair_value)
        """
        results: list[tuple[str, float, float]] = []

        if not security.theses:
            return results

        original_qualitative = (
            security.qualitative.copy() if security.qualitative is not None else None
        )

        try:
            for thesis in security.theses:
                target_asm = next(
                    (a for a in thesis.assumptions if a.name == assumption_name), None
                )
                if not target_asm or not isinstance(target_asm.value, int | float):
                    continue

                # Reset qualitative dictionary for this thesis
                security.qualitative = (
                    original_qualitative.copy() if original_qualitative is not None else {}
                )
                for assumption in thesis.assumptions:
                    security.qualitative[assumption.name] = assumption.value

                try:
                    base_fv = valuation_fn(security)

                    # Perturb the specific assumption
                    security.qualitative[assumption_name] = target_asm.value * (1 + perturbation)
                    perturbed_fv = valuation_fn(security)

                    results.append((thesis.label, base_fv, perturbed_fv))
                except Exception:
                    continue
        finally:
            security.qualitative = original_qualitative

        return results

    def calculate_expected_value(
        self, security: Security, priors: list[ScenarioPrior]
    ) -> float | None:
        """Calculates the probability-weighted Expected Value (EV) across scenarios."""
        if not security.theses or not priors:
            return None

        # Map probabilities case-insensitively
        prior_map = {p.label.lower(): p.probability for p in priors}
        expected_value = 0.0
        total_prob = 0.0

        for thesis in security.theses:
            prob = prior_map.get(thesis.label.lower(), 0.0)
            if thesis.fair_value_low is not None and thesis.fair_value_high is not None:
                midpoint = (thesis.fair_value_low + thesis.fair_value_high) / 2.0
                expected_value += midpoint * prob
                total_prob += prob

        if total_prob == 0:
            return None

        return expected_value / total_prob

    def apply_evidence(
        self, security: Security, priors: list[ScenarioPrior], evidence: Evidence
    ) -> ThesisEvaluation:
        """Updates scenario probabilities based on new evidence and recalculates the Expected Value."""
        updater = BayesianUpdater()
        posteriors = updater.update(priors, evidence)

        evaluation = self.evaluate(security)
        evaluation.posteriors = posteriors
        evaluation.expected_value = self.calculate_expected_value(security, posteriors)
        evaluation.narrative += f"\nApplied Evidence: '{evidence.description}'"

        return evaluation

    def render_report(
        self, evaluation: ThesisEvaluation, current_price: float | None = None
    ) -> str:
        """Generates a text-based actionable report from the evaluation."""
        lines = [
            "=== THESIS ENGINE REPORT ===",
            evaluation.narrative,
        ]

        if evaluation.worst_case is not None and evaluation.best_case is not None:
            lines.append(
                f"Consensus Range: {evaluation.worst_case:.2f} - {evaluation.best_case:.2f}"
            )
        else:
            lines.append("Consensus Range: Insufficient data")

        if evaluation.expected_value is not None:
            lines.append(f"Expected Value (EV): {evaluation.expected_value:.2f}")

        if (
            evaluation.spread is not None
            and evaluation.worst_case is not None
            and evaluation.best_case is not None
        ):
            lines.append(f"Spread: {evaluation.spread:.2f}")
            lines.append("---")

            # Actionable logic based on spread size relative to midpoint
            midpoint = (evaluation.worst_case + evaluation.best_case) / 2
            if midpoint != 0 and (evaluation.spread / abs(midpoint)) > 0.30:
                lines.append("VERDICT: [HIGH DISPERSION] - Thesis range is wide; exercise caution.")
            else:
                lines.append("VERDICT: [CONSOLIDATED] - Scenarios are tightly aligned.")

            # Actionable logic based on current market price
            if current_price is not None:
                if current_price > evaluation.best_case or current_price < evaluation.worst_case:
                    lines.append(
                        f"ACTION:  [OUT OF RANGE] - Market price ({current_price:.2f}) is outside thesis bounds."
                    )
                else:
                    lines.append(
                        f"ACTION:  [IN RANGE] - Market price ({current_price:.2f}) is within thesis bounds."
                    )
        else:
            lines.append("---")
            lines.append("VERDICT: [INCOMPLETE] - Cannot compute dispersion.")

        if evaluation.warnings:
            lines.append("WARNINGS:")
            for w in evaluation.warnings:
                lines.append(f"  • {w}")

        if evaluation.posteriors:
            lines.append("---")
            lines.append("PROBABILITY DISTRIBUTION:")
            for p in evaluation.posteriors:
                lines.append(f"  • [{p.label}] : {p.probability:.1%}")

        return "\n".join(lines)

    def render_sensitivity_report(
        self, results: list[tuple[str, float, float]], assumption_name: str, perturbation: float
    ) -> str:
        """Generates a text-based tornado chart for sensitivity results."""
        if not results:
            return "No sensitivity data to display."

        lines = [
            "=== SENSITIVITY ANALYSIS ===",
            f"Assumption: '{assumption_name}' perturbed by {perturbation:+.1%}",
            "---",
        ]

        for thesis_label, base_fv, perturbed_fv in results:
            if base_fv == 0:
                continue

            delta_pct = (perturbed_fv - base_fv) / abs(base_fv)
            # Scale: 1% impact = 2 blocks for visibility
            blocks = int(abs(delta_pct) * 100 * 2)
            bar = "█" * blocks

            lines.append(f"[{thesis_label}]")
            lines.append(f"  Base FV: {base_fv:.2f} -> Perturbed FV: {perturbed_fv:.2f}")
            lines.append(f"  Impact:  {delta_pct:+.2%}  |{bar}")
            lines.append("---")

        return "\n".join(lines)

    def _validate_scenarios(self, security: Security, warnings: list[str]) -> None:
        """Check for logical inconsistencies between competing scenarios."""
        bull = next((t for t in security.theses if t.label.lower() == "bull"), None)
        bear = next((t for t in security.theses if t.label.lower() == "bear"), None)

        if bull and bear and bull.fair_value_low is not None and bear.fair_value_high is not None:
            # Compare the top end of the bear case against the bottom end of the bull case
            if bull.fair_value_low <= bear.fair_value_high:
                warnings.append(
                    f"Overlap Warning: Bull low ({bull.fair_value_low:.2f}) is not strictly greater than Bear high ({bear.fair_value_high:.2f})."
                )
