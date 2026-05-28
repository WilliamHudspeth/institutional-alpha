"""Terminal state management with immutable dataclasses.

Centralized state objects that drive all UI rendering and composition.
Enables predictable state mutations and panel reactivity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SecurityState:
    """Immutable state container for a loaded security."""

    ticker: str
    name: str
    price: float
    pwev: float
    verdict: str
    confidence: str
    growth: str | None = None
    wacc: str | None = None
    terminal_growth: str | None = None
    synthesis: str | None = None
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    signals: dict[str, str] = field(default_factory=dict)
    wacc_info: dict[str, Any] | None = None
    last_updated: datetime = field(default_factory=datetime.now)
    is_stale: bool = False
    history: list[float] = field(default_factory=list)

    @property
    def implied_move(self) -> float:
        """Compute implied move from PWEV relative to current price."""
        if self.price <= 0:
            return 0.0
        return (self.pwev / self.price) - 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for legacy rendering functions."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "price": self.price,
            "pwev": self.pwev,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "growth": self.growth,
            "wacc": self.wacc,
            "terminal": self.terminal_growth,
            "synthesis": self.synthesis,
            "scenarios": self.scenarios,
            "signals": self.signals,
            "wacc_info": self.wacc_info,
        }


@dataclass
class TerminalUIState:
    """Complete terminal state snapshot."""

    active_security: SecurityState | None = None
    loaded_securities: dict[str, SecurityState] = field(default_factory=dict)
    ui_mode: str = "main_menu"  # main_menu, quick_rec, deep_dive, factor_score, thesis, backtest
    selected_ticker: str | None = None
    is_loading: bool = False
    error_message: str | None = None
    warning_message: str | None = None
    last_action: str | None = None
    last_action_timestamp: datetime = field(default_factory=datetime.now)

    def get_active_security(self) -> SecurityState | None:
        """Get the currently active security, ensuring it exists."""
        if self.selected_ticker and self.selected_ticker in self.loaded_securities:
            return self.loaded_securities[self.selected_ticker]
        return self.active_security

    def set_active_security(self, state: SecurityState) -> None:
        """Set active security and cache it."""
        self.active_security = state
        self.selected_ticker = state.ticker
        self.loaded_securities[state.ticker] = state

    def mark_loading(self) -> None:
        """Mark system as loading."""
        self.is_loading = True
        self.error_message = None
        self.warning_message = None

    def mark_loaded(self) -> None:
        """Mark system as finished loading."""
        self.is_loading = False

    def set_error(self, msg: str) -> None:
        """Set an error message."""
        self.error_message = msg
        self.is_loading = False

    def set_warning(self, msg: str) -> None:
        """Set a warning message."""
        self.warning_message = msg

    def clear_messages(self) -> None:
        """Clear all temporary messages."""
        self.error_message = None
        self.warning_message = None


@dataclass
class BayesianState:
    """State for Bayesian thesis updating."""

    ticker: str
    prior_weights: dict[str, float]
    posterior_weights: dict[str, float]
    evidence_type: str
    evidence_reliability: float
    timestamp: datetime = field(default_factory=datetime.now)
