"""Configuration and settings management.

Provides:
- Pydantic-based configuration system
- Environment variable overrides
- YAML/JSON file loading
- Structured logging setup
- Component-specific loggers

Usage:
    from iam.config import get_settings, configure_logging

    # Get settings
    settings = get_settings()
    print(settings.terminal.width)

    # Configure logging
    configure_logging(structured=False)
"""

from iam.config.logging_config import (
    LOGGER_ANALYTICS,
    LOGGER_DATA,
    LOGGER_FACTORS,
    LOGGER_INTEGRATION,
    LOGGER_PIPELINE,
    LOGGER_UI,
    LOGGER_VALUATION,
    PerformanceLogger,
    configure_logging,
    get_logger,
)
from iam.config.settings import (
    AsyncConfig,
    DataSourceConfig,
    FactorWeightsConfig,
    LoggingConfig,
    PipelineConfig,
    RiskLimitsConfig,
    TerminalConfig,
    TerminalSettings,
    get_settings,
    set_settings,
)
from iam.config.secrets import SecretsManager

__all__ = [
    # Settings classes
    "TerminalSettings",
    "FactorWeightsConfig",
    "DataSourceConfig",
    "TerminalConfig",
    "PipelineConfig",
    "AsyncConfig",
    "LoggingConfig",
    "RiskLimitsConfig",
    "SecretsManager",
    # Settings functions
    "get_settings",
    "set_settings",
    # Logging
    "configure_logging",
    "get_logger",
    "PerformanceLogger",
    # Component loggers
    "LOGGER_PIPELINE",
    "LOGGER_FACTORS",
    "LOGGER_DATA",
    "LOGGER_VALUATION",
    "LOGGER_UI",
    "LOGGER_INTEGRATION",
    "LOGGER_ANALYTICS",
]
