"""Modular panel components for institutional terminal.

Decouples rendering logic into composable, reusable panels.
Each panel is responsible for one logical view section.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from iam.ui.state import TerminalUIState


class BasePanel(ABC):
    """Base class for all terminal panels.

    Panels are responsible for:
    - Rendering a logical section
    - Handling their own state
    - Supporting resize operations
    """

    def __init__(self, width: int = 80) -> None:
        self.width = width

    @abstractmethod
    def render(self, state: TerminalUIState) -> str:
        """Render the panel to string. Must return complete output."""
        pass

    def is_visible(self, state: TerminalUIState) -> bool:
        """Return whether this panel should be shown. Override for conditional rendering."""
        return True


class HeaderPanel(BasePanel):
    """System header and security identification."""

    def render(self, state: TerminalUIState) -> str:
        """Render the retro Bloomberg-style header."""
        if not state.active_security:
            return ""

        security = state.active_security
        lines = []
        lines.append("┌" + "─" * (self.width - 2) + "┐")
        lines.append(
            "│  ALPHA-TERMINAL // SYSTEM ACTIVE // COGNITIVE QUANTITATIVE MULTI-FACTOR ENGINE│".ljust(
                self.width - 1
            )
            + "│"
        )
        lines.append(
            f"│  SECURITY: {security.ticker:<10} NAME: {security.name:<26} STATUS: ONLINE         │"
        )
        lines.append("└" + "─" * (self.width - 2) + "┘")
        return "\n".join(lines)


class DecisionSheetPanel(BasePanel):
    """Executive decision sheet with verdict and confidence."""

    def render(self, state: TerminalUIState) -> str:
        """Render decision sheet with key metrics."""
        if not state.active_security:
            return ""

        security = state.active_security
        lines = []
        rule = "═" * self.width
        "─" * self.width

        lines.append(rule)
        lines.append("║  [ EXECUTIVE DECISION SHEET ]".ljust(self.width - 1) + "║")
        lines.append(rule)

        # Format values
        price_str = f"${security.price:,.2f}" if security.price > 0 else "$—"
        pwev_str = f"${security.pwev:,.2f}" if security.pwev > 0 else "$—"
        move_pct = security.implied_move
        upside_str = f"{move_pct * 100:+.1f}%" if move_pct != 0 else "—"

        lines.append(
            f"   • Current Spot Price : {price_str:<18} • consensus rating   : {security.verdict}"
        )
        lines.append(
            f"   • Fair Value (PWEV)  : {pwev_str:<18} • Arb Engine Weight : 70% Synthesis / 30% Trad"
        )
        lines.append(
            f"   • Arb Implied Move   : {upside_str:<18} • System Confidence  : [ {security.confidence} ]"
        )
        lines.append(rule)

        return "\n".join(lines)


class ForecastMetricsPanel(BasePanel):
    """Core forecast metrics and WACC details."""

    def render(self, state: TerminalUIState) -> str:
        """Render forecast assumptions and cost of capital."""
        if not state.active_security:
            return ""

        security = state.active_security
        lines = []
        "═" * self.width
        thin_rule = "─" * self.width

        lines.append("║  [ CORE FORECAST METRIC PROFILE ]".ljust(self.width - 1) + "║")
        lines.append(thin_rule)

        growth = security.growth or "—"
        wacc = security.wacc or "—"
        terminal = security.terminal_growth or "—"
        synthesis = security.synthesis or "N/A"

        lines.append(f"   Forecast Growth : {growth:<15} Discount Rate (WACC)   : {wacc}")
        lines.append(f"   Terminal Growth : {terminal:<15} Consensus Synthesis     : {synthesis}")
        lines.append(thin_rule)

        # Detailed WACC breakdown if available
        if security.wacc_info and isinstance(security.wacc_info, dict):
            ke_val = security.wacc_info.get("cost_of_equity")
            kd_val = security.wacc_info.get("cost_of_debt")
            spread_val = security.wacc_info.get("spread")
            rating_val = security.wacc_info.get("rating", "—")

            ke_str = f"{ke_val * 100:+.1f}%" if ke_val is not None else "—"
            kd_str = f"{kd_val * 100:+.1f}%" if kd_val is not None else "—"
            spread_str = f"{spread_val * 100:+.1f}%" if spread_val is not None else "—"

            lines.append("║  [ QUANTITATIVE COST OF CAPITAL DETAIL ]".ljust(self.width - 1) + "║")
            lines.append(thin_rule)
            lines.append(f"   Cost of Equity (Ke)  : {ke_str:<10} Cost of Debt (Kd)    : {kd_str}")
            lines.append(
                f"   Credit Risk Rating   : {rating_val:<10} Corporate Spread     : {spread_str}"
            )
            lines.append(thin_rule)

        return "\n".join(lines)


class ScenarioMatrixPanel(BasePanel):
    """Probabilistic scenario weight matrix."""

    def render(self, state: TerminalUIState) -> str:
        """Render scenario analysis table."""
        if not state.active_security or not state.active_security.scenarios:
            return ""

        security = state.active_security
        lines = []
        "═" * self.width
        thin_rule = "─" * self.width

        lines.append("║  [ PROBABILISTIC SCENARIO WEIGHT MATRIX ]".ljust(self.width - 1) + "║")
        lines.append(thin_rule)
        lines.append(
            f"   {'SCENARIO CASE':<16} {'WEIGHT':<8} {'TARGET VALUE':<16} {'IMPLIED RETURN':<16} THESIS"
        )

        for s in security.scenarios:
            s_name = str(s.get("name", "—"))
            s_prob = str(s.get("prob", "—"))
            target_val = s.get("target", 0.0)
            s_target = f"${target_val:,.2f}" if target_val > 0 else "—"
            s_upside = str(s.get("upside", "—"))
            s_thesis = str(s.get("thesis", ""))[:40]  # Truncate long thesis

            lines.append(f"   {s_name:<16} {s_prob:<8} {s_target:<16} {s_upside:<16} {s_thesis}")

        lines.append(thin_rule)
        return "\n".join(lines)


class DiagnosticSignalsPanel(BasePanel):
    """Multi-lens diagnostic signals from factor engines."""

    def render(self, state: TerminalUIState) -> str:
        """Render diagnostic signals from all engines."""
        if not state.active_security or not state.active_security.signals:
            return ""

        security = state.active_security
        lines = []
        rule = "═" * self.width

        lines.append(
            "║  [ MULTI-LENS DIAGNOSTIC INTERMEDIARY SIGNALS ]".ljust(self.width - 1) + "║"
        )
        lines.append(rule)

        for engine, signal in security.signals.items():
            label = str(engine).replace("_", " ").title()
            lines.append(f"   • {label:<35} : {str(signal).upper()}")

        lines.append(rule)
        return "\n".join(lines)


class StatusPanel(BasePanel):
    """Status indicators, loading states, and messages."""

    def render(self, state: TerminalUIState) -> str:
        """Render status and messages."""
        lines = []

        if state.is_loading:
            lines.append("   [ ⟳ LOADING DATA... ]")

        if state.error_message:
            lines.append(f"   [ ✗ ERROR: {state.error_message} ]")

        if state.warning_message:
            lines.append(f"   [ ⚠ WARNING: {state.warning_message} ]")

        return "\n".join(lines) if lines else ""


class PanelComposer:
    """Orchestrates panel rendering and composition.

    Manages order, visibility, spacing, and overall layout.
    """

    def __init__(self, width: int = 80) -> None:
        self.width = width
        self.panels: dict[str, BasePanel] = {}
        self._panel_order: list[str] = []

    def register_panel(self, name: str, panel: BasePanel) -> None:
        """Register a panel and add to rendering order."""
        self.panels[name] = panel
        self._panel_order.append(name)

    def render(self, state: TerminalUIState) -> str:
        """Render all visible panels in order."""
        output = []

        for panel_name in self._panel_order:
            panel = self.panels[panel_name]
            if panel.is_visible(state):
                rendered = panel.render(state)
                if rendered:
                    output.append(rendered)

        # Add status panel at bottom
        status_panel = StatusPanel(self.width)
        status = status_panel.render(state)
        if status:
            output.append("")
            output.append(status)

        return "\n".join(output)


def create_default_composer(width: int = 80) -> PanelComposer:
    """Factory for creating the standard panel composition."""
    composer = PanelComposer(width)

    composer.register_panel("header", HeaderPanel(width))
    composer.register_panel("decision", DecisionSheetPanel(width))
    composer.register_panel("forecast", ForecastMetricsPanel(width))
    composer.register_panel("scenarios", ScenarioMatrixPanel(width))
    composer.register_panel("signals", DiagnosticSignalsPanel(width))

    return composer
