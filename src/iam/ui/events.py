"""Event bus for decoupled, reactive terminal architecture.

Enables:
- Panel subscription to events
- Real-time streaming updates
- Async data loading notifications
- Factor completion signals
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class EventType(Enum):
    """Enumeration of all terminal events."""

    # Security events
    SECURITY_LOADED = "security_loaded"
    SECURITY_UPDATED = "security_updated"
    SECURITY_STALE = "security_stale"

    # Pipeline events
    PIPELINE_START = "pipeline_start"
    PIPELINE_PROGRESS = "pipeline_progress"
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_ERROR = "pipeline_error"

    # Factor events
    FACTOR_COMPLETE = "factor_complete"
    FACTOR_ERROR = "factor_error"

    # Data events
    PRICE_TICK = "price_tick"
    DATA_REFRESH = "data_refresh"

    # UI events
    MODE_CHANGED = "mode_changed"
    SELECTION_CHANGED = "selection_changed"

    # Thesis events
    BAYESIAN_UPDATE = "bayesian_update"
    SCENARIO_CHANGE = "scenario_change"


@dataclass
class Event:
    """Immutable event with type, payload, and timestamp."""

    event_type: EventType
    payload: dict[str, Any]
    timestamp: datetime
    source: str = "system"

    def __post_init__(self) -> None:
        """Ensure timestamp is set."""
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now())


class EventBus:
    """Central event dispatcher for terminal events.

    Handlers can subscribe to specific event types.
    Supports both synchronous and asynchronous event processing.
    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._event_history: list[Event] = []
        self._max_history = 1000

    def subscribe(
        self, event_type: EventType, handler: Callable[[Event], None]
    ) -> Callable[[], None]:
        """Subscribe to an event type. Returns unsubscribe function."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        self._subscribers[event_type].append(handler)

        # Return unsubscribe function
        def unsubscribe() -> None:
            if event_type in self._subscribers:
                self._subscribers[event_type].remove(handler)

        return unsubscribe

    def subscribe_any(self, handler: Callable[[Event], None]) -> Callable[[], None]:
        """Subscribe to all event types."""
        unsubs = []
        for event_type in EventType:
            unsubs.append(self.subscribe(event_type, handler))

        def unsubscribe_all() -> None:
            for unsub in unsubs:
                unsub()

        return unsubscribe_all

    def emit(self, event_type: EventType, payload: dict[str, Any], source: str = "system") -> None:
        """Emit an event to all subscribers."""
        event = Event(
            event_type=event_type,
            payload=payload,
            timestamp=datetime.now(),
            source=source,
        )

        # Track history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        # Dispatch to subscribers
        if event_type in self._subscribers:
            for handler in self._subscribers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    # Log but don't crash on handler error
                    print(f"Error in event handler: {e}")

    def get_history(self, event_type: EventType | None = None, limit: int = 100) -> list[Event]:
        """Retrieve event history, optionally filtered by type."""
        if event_type is None:
            return self._event_history[-limit:]

        return [e for e in self._event_history if e.event_type == event_type][-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        self._event_history.clear()


# Global event bus instance
_global_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def emit_event(event_type: EventType, payload: dict[str, Any], source: str = "system") -> None:
    """Convenience function to emit events to global bus."""
    get_event_bus().emit(event_type, payload, source)


def subscribe_to_event(
    event_type: EventType, handler: Callable[[Event], None]
) -> Callable[[], None]:
    """Convenience function to subscribe to global bus."""
    return get_event_bus().subscribe(event_type, handler)
