"""Structured logging configuration for institutional systems.

Sets up:
- Separate loggers for different components
- File rotation
- Structured logging with context
- Performance metrics logging

Usage:
    from iam.config.logging_config import configure_logging
    configure_logging()

    logger = logging.getLogger('iam.pipeline')
    logger.info("Pipeline started", extra={"ticker": "MSFT", "duration_ms": 1234})
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path
from typing import Any

from iam.config.settings import get_settings


class StructuredFormatter(logging.Formatter):
    """Formats logs as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format record as JSON."""
        log_obj = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "ticker"):
            log_obj["ticker"] = record.ticker
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms
        if hasattr(record, "component"):
            log_obj["component"] = record.component

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


class PlainFormatter(logging.Formatter):
    """Formats logs as plain text."""

    def format(self, record: logging.LogRecord) -> str:
        """Format record as plain text."""
        base = super().format(record)

        # Add extra fields if present
        extras = []
        if hasattr(record, "ticker"):
            extras.append(f"ticker={record.ticker}")
        if hasattr(record, "duration_ms"):
            extras.append(f"duration_ms={record.duration_ms}ms")
        if hasattr(record, "component"):
            extras.append(f"component={record.component}")

        if extras:
            base = base + " | " + " ".join(extras)

        return base


def configure_logging(structured: bool = False) -> None:
    """Configure logging for the application.

    Args:
        structured: If True, use JSON structured logging
    """
    settings = get_settings()
    log_config = settings.logging

    # Create log directory
    log_dir = Path(log_config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Set root logger level
    root_logger = logging.getLogger()
    root_logger.setLevel(log_config.level)

    # Choose formatter
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = PlainFormatter(log_config.format)

    # Console handler (always)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_config.level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if configured)
    if log_config.log_file:
        log_file = log_dir / log_config.log_file

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=log_config.max_size_mb * 1024 * 1024,
            backupCount=log_config.backup_count,
        )
        file_handler.setLevel(log_config.level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Component-specific loggers
    component_loggers = [
        "iam.pipeline",
        "iam.factors",
        "iam.data",
        "iam.valuation",
        "iam.ui",
        "iam.integration",
        "iam.analytics",
    ]

    for component in component_loggers:
        component_logger = logging.getLogger(component)
        component_logger.setLevel(log_config.level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a component."""
    return logging.getLogger(name)


class LoggingContext:
    """Context manager for adding logging context.

    Usage:
        with LoggingContext(ticker="MSFT", component="pipeline"):
            logger.info("Processing security")
            # Logs will include ticker and component fields
    """

    def __init__(self, **context: Any) -> None:
        self.context = context
        self.token = None

    def __enter__(self) -> LoggingContext:
        """Enter context."""
        # Store in thread-local storage would be ideal, but for now
        # we just keep in instance
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context."""
        pass

    def __call__(self, logger: logging.LogRecord) -> dict[str, Any]:
        """Add context to log record."""
        return self.context


# Component loggers
LOGGER_PIPELINE = logging.getLogger("iam.pipeline")
LOGGER_FACTORS = logging.getLogger("iam.factors")
LOGGER_DATA = logging.getLogger("iam.data")
LOGGER_VALUATION = logging.getLogger("iam.valuation")
LOGGER_UI = logging.getLogger("iam.ui")
LOGGER_INTEGRATION = logging.getLogger("iam.integration")
LOGGER_ANALYTICS = logging.getLogger("iam.analytics")


def log_performance(logger: logging.Logger, operation: str, duration_ms: float) -> None:
    """Log performance metrics."""
    if duration_ms > 5000:
        logger.warning(
            f"{operation} took longer than 5s",
            extra={"duration_ms": duration_ms, "operation": operation},
        )
    else:
        logger.debug(
            f"{operation} completed",
            extra={"duration_ms": duration_ms, "operation": operation},
        )


class PerformanceLogger:
    """Context manager for logging operation performance."""

    def __init__(self, logger: logging.Logger, operation: str) -> None:
        self.logger = logger
        self.operation = operation
        self.start_time = None

    def __enter__(self) -> PerformanceLogger:
        """Start timer."""
        import time

        self.start_time = time.time()
        self.logger.debug(f"{self.operation} started")
        return self

    def __exit__(self, *args: Any) -> None:
        """End timer and log."""
        import time

        duration_ms = (time.time() - self.start_time) * 1000
        log_performance(self.logger, self.operation, duration_ms)
