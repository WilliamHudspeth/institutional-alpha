"""Configuration system using Pydantic.

Centralizes all configurable parameters:
- Terminal rendering settings
- Factor weights and thresholds
- Data provider configuration
- Pipeline parameters
- Risk limits
- Logging configuration

Supports YAML/TOML loading and environment variable overrides.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FactorWeightsConfig(BaseModel):
    """Base factor weights configuration."""

    quality: float = Field(default=0.20, description="Quality factor weight")
    growth: float = Field(default=0.25, description="Growth factor weight")
    value: float = Field(default=0.10, description="Value factor weight")
    momentum: float = Field(default=0.15, description="Momentum factor weight")
    sentiment: float = Field(default=0.10, description="Sentiment factor weight")
    capital_allocation: float = Field(default=0.12, description="Capital allocation weight")
    earnings_quality: float = Field(default=0.08, description="Earnings quality weight")

    class Config:
        """Pydantic config."""

        extra = "allow"  # Allow additional factors

    def get_weight(self, factor_name: str) -> float:
        """Get weight for a factor."""
        return getattr(self, factor_name, 0.0)

    def as_dict(self) -> dict[str, float]:
        """Convert to dict."""
        return {k: v for k, v in self.dict().items() if isinstance(v, (int, float))}

    def total_weight(self) -> float:
        """Sum of all weights."""
        return sum(self.as_dict().values())

    def normalize(self) -> FactorWeightsConfig:
        """Normalize weights to sum to 1.0."""
        total = self.total_weight()
        if total == 0:
            return self

        data = self.dict()
        normalized = {k: v / total for k, v in data.items() if isinstance(v, (int, float))}
        return FactorWeightsConfig(**normalized)


class DataSourceConfig(BaseModel):
    """Data source configuration."""

    primary_provider: str = Field(default="yfinance", description="Primary data provider")
    fallback_providers: list[str] = Field(default=["stooq"], description="Fallback providers")
    cache_ttl_seconds: int = Field(default=3600, description="Data cache TTL")
    max_retries: int = Field(default=3, description="Max retry attempts")
    timeout_seconds: float = Field(default=10.0, description="Request timeout")
    use_proxy: bool = Field(default=False, description="Use proxy for requests")


class TerminalConfig(BaseModel):
    """Terminal UI configuration."""

    width: int = Field(default=80, description="Terminal width")
    height: int = Field(default=40, description="Terminal height")
    refresh_rate: float = Field(default=0.1, description="Refresh rate (seconds)")
    color_mode: str = Field(default="auto", description="Color mode: auto, color, mono")
    unicode_enabled: bool = Field(default=True, description="Enable Unicode characters")
    show_debug_info: bool = Field(default=False, description="Show debug information")


class PipelineConfig(BaseModel):
    """Valuation pipeline configuration."""

    enable_dcf: bool = Field(default=True, description="Enable DCF valuation")
    enable_multiples: bool = Field(default=True, description="Enable multiples analysis")
    enable_scenario: bool = Field(default=True, description="Enable scenario analysis")
    forecast_periods: int = Field(default=10, description="DCF forecast period")
    terminal_growth_rate: float = Field(default=0.025, description="Default terminal growth")
    discount_rate_floor: float = Field(default=0.06, description="Minimum discount rate")
    discount_rate_ceiling: float = Field(default=0.15, description="Maximum discount rate")


class AsyncConfig(BaseModel):
    """Async execution configuration."""

    enabled: bool = Field(default=True, description="Enable async execution")
    max_workers: int = Field(default=4, description="Thread pool size")
    task_timeout_seconds: float = Field(default=60.0, description="Task timeout")
    enable_event_bus: bool = Field(default=True, description="Enable event bus")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Logging level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format",
    )
    log_file: str | None = Field(default=None, description="Log file path")
    log_dir: str = Field(default="./logs", description="Log directory")
    max_size_mb: int = Field(default=50, description="Max log file size")
    backup_count: int = Field(default=5, description="Number of backup logs")


class RiskLimitsConfig(BaseModel):
    """Risk management limits."""

    max_concentration: float = Field(default=0.20, description="Max position concentration")
    max_drawdown: float = Field(default=0.15, description="Max portfolio drawdown")
    var_confidence: float = Field(default=0.95, description="VaR confidence level")
    stress_test_percentile: float = Field(default=0.05, description="Stress test percentile")


class TerminalSettings(BaseModel):
    """Complete terminal configuration.

    Load from environment:
        settings = TerminalSettings()  # Loads from ~/.iam/settings.yml

    Load from file:
        settings = TerminalSettings.from_file("config.yml")

    Load from dict:
        settings = TerminalSettings(**config_dict)
    """

    factor_weights: FactorWeightsConfig = Field(default_factory=FactorWeightsConfig)
    data_source: DataSourceConfig = Field(default_factory=DataSourceConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    async_config: AsyncConfig = Field(default_factory=AsyncConfig, alias="async")
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    risk_limits: RiskLimitsConfig = Field(default_factory=RiskLimitsConfig)

    class Config:
        """Pydantic config."""

        populate_by_name = True  # Allow both field name and alias

    @classmethod
    def from_file(cls, path: str | Path) -> TerminalSettings:
        """Load settings from YAML or JSON file."""
        import json

        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Settings file not found: {path}")

        try:
            import yaml

            with open(path) as f:
                data = yaml.safe_load(f)
        except ImportError:
            # Fallback to JSON if YAML not available
            if path.suffix != ".json":
                raise ImportError("PyYAML required for .yml/.yaml files. Install with: pip install pyyaml")
            with open(path) as f:
                data = json.load(f)

        return cls(**data)

    @classmethod
    def from_env(cls) -> TerminalSettings:
        """Load settings from environment and config files.

        Looks for config in:
        1. IAM_CONFIG environment variable (file path)
        2. ~/.iam/settings.yml
        3. ./settings.yml
        4. ./config.yml
        """
        import os

        # Check environment variable
        if env_config := os.environ.get("IAM_CONFIG"):
            if Path(env_config).exists():
                return cls.from_file(env_config)

        # Check standard locations
        for path in [Path.home() / ".iam" / "settings.yml", Path("settings.yml"), Path("config.yml")]:
            if path.exists():
                return cls.from_file(path)

        # Return defaults
        return cls()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return self.model_dump(by_alias=True)

    def to_file(self, path: str | Path) -> None:
        """Save settings to file."""
        import json

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


# Global settings instance
_global_settings: TerminalSettings | None = None


def get_settings() -> TerminalSettings:
    """Get or create global settings instance."""
    global _global_settings
    if _global_settings is None:
        _global_settings = TerminalSettings.from_env()
    return _global_settings


def set_settings(settings: TerminalSettings) -> None:
    """Override global settings."""
    global _global_settings
    _global_settings = settings
