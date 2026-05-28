"""Modern terminal UI using panel composition and event-driven architecture.

Replaces the monolithic institutional_terminal.py with a composable system.
Enables progressive enhancement and real-time streaming updates.
"""

from __future__ import annotations

from typing import Any

from iam.ui.events import EventType, get_event_bus, subscribe_to_event
from iam.ui.panels import create_default_composer
from iam.ui.state import SecurityState, TerminalUIState


class ModernTerminal:
    """Terminal with event-driven panel composition.

    Combines:
    - Immutable SecurityState for data
    - Event bus for reactive updates
    - Panel composer for modular rendering
    - Async data layer integration
    """

    def __init__(self, width: int = 80) -> None:
        self.width = width
        self.state = TerminalUIState()
        self.composer = create_default_composer(width)
        self.event_bus = get_event_bus()

        # Subscribe to state-changing events
        subscribe_to_event(EventType.SECURITY_LOADED, self._on_security_loaded)
        subscribe_to_event(EventType.PIPELINE_COMPLETE, self._on_pipeline_complete)
        subscribe_to_event(EventType.PIPELINE_ERROR, self._on_pipeline_error)

    def _on_security_loaded(self, event: Any) -> None:
        """Handle security loaded event."""
        # Payload would contain ticker and security data
        pass

    def _on_pipeline_complete(self, event: Any) -> None:
        """Handle pipeline completion."""
        self.state.mark_loaded()

    def _on_pipeline_error(self, event: Any) -> None:
        """Handle pipeline error."""
        error_msg = event.payload.get("error", "Unknown error")
        self.state.set_error(error_msg)

    def load_security(self, ticker: str, data: dict[str, Any]) -> None:
        """Load security data and update state.

        Args:
            ticker: Security identifier
            data: Dictionary with security information
        """
        security_state = SecurityState(
            ticker=data.get("ticker", ticker).upper(),
            name=data.get("name", "Unknown Company"),
            price=float(data.get("price", 0.0) or 0.0),
            pwev=float(data.get("pwev", 0.0) or 0.0),
            verdict=str(data.get("verdict", "HOLD")).upper(),
            confidence=str(data.get("confidence", "—")).upper(),
            growth=data.get("growth"),
            wacc=data.get("wacc"),
            terminal_growth=data.get("terminal"),
            synthesis=data.get("synthesis"),
            scenarios=data.get("scenarios", []),
            signals=data.get("signals", {}),
            wacc_info=data.get("wacc_info"),
        )

        self.state.set_active_security(security_state)

    def render(self) -> str:
        """Render complete terminal output."""
        return self.composer.render(self.state)

    def print_output(self) -> None:
        """Print rendered output to console."""
        output = self.render()
        print(output)

    def set_error(self, message: str) -> None:
        """Set an error message."""
        self.state.set_error(message)

    def set_warning(self, message: str) -> None:
        """Set a warning message."""
        self.state.set_warning(message)

    def clear_messages(self) -> None:
        """Clear temporary messages."""
        self.state.clear_messages()


def render_security_report(ticker: str, data: dict[str, Any], width: int = 80) -> str:
    """Convenience function to render a security report using modern terminal.

    Replaces print_institutional_ui() from legacy terminal.

    Args:
        ticker: Security identifier
        data: Security data dict
        width: Terminal width

    Returns:
        Formatted report string
    """
    terminal = ModernTerminal(width=width)
    terminal.load_security(ticker, data)
    return terminal.render()


def print_security_report(ticker: str, data: dict[str, Any], width: int = 80) -> None:
    """Print a security report.

    Convenience wrapper around render_security_report().

    Args:
        ticker: Security identifier
        data: Security data dict
        width: Terminal width
    """
    output = render_security_report(ticker, data, width)
    print(output)


if __name__ == "__main__":
    # Example usage
    sample_data = {
        "ticker": "BLK",
        "name": "BlackRock, Inc.",
        "price": 1070.34,
        "verdict": "STRONG BUY",
        "growth": "14.0%",
        "wacc": "7.16%",
        "terminal": "2.5%",
        "pwev": 1600.48,
        "synthesis": "+57.0%",
        "confidence": "MODERATE",
        "scenarios": [
            {
                "name": "Bear Case",
                "prob": "20%",
                "target": 697.15,
                "upside": "-34.9%",
                "thesis": "Stressed execution",
            },
            {
                "name": "Base Case",
                "prob": "60%",
                "target": 1409.61,
                "upside": "+31.7%",
                "thesis": "Anchor assumptions",
            },
            {
                "name": "Bull Case",
                "prob": "20%",
                "target": 3076.42,
                "upside": "+187.4%",
                "thesis": "Platform leverage",
            },
        ],
        "signals": {
            "reverse_dcf": "BEARISH (-38.2%)",
            "platform_compounder": "BULLISH (+57.0%)",
            "relative_valuation": "N/A",
            "macro_overlay": "PASS",
        },
    }

    print_security_report("BLK", sample_data)
