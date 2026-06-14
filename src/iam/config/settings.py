"""Configuration system using Pydantic  (ENHANCED drop-in replacement).

Adds, relative to the original:
    * ``DisplayConfig`` theme/accent + a real ``watchlist`` / ``coverage`` list
      (previously hardcoded as ``DEFAULT_WATCHLIST`` in the TUI).
    * ``MarketDataConfig`` for the new live quote / macro-snapshot layer.
    * Field range constraints (ge/le) so an in-app editor can validate input and
      show legal bounds.
    * A YAML-writing ``to_file`` (the original wrote JSON to a ``.yml`` path).
    * Back-compat: every original field name still exists; ``get_settings`` /
      ``set_settings`` are unchanged.

Drop this over ``src/iam/config/settings.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FactorWeightsConfig(BaseModel):
    """Base factor weights configuration."""

    quality: float = Field(default=0.20, ge=0.0, le=1.0, description="Quality factor weight")
    growth: float = Field(default=0.25, ge=0.0, le=1.0, description="Growth factor weight")
    value: float = Field(default=0.10, ge=0.0, le=1.0, description="Value factor weight")
    momentum: float = Field(default=0.15, ge=0.0, le=1.0, description="Momentum factor weight")
    sentiment: float = Field(default=0.10, ge=0.0, le=1.0, description="Sentiment factor weight")
    capital_allocation: float = Field(
        default=0.12, ge=0.0, le=1.0, description="Capital allocation weight"
    )
    earnings_quality: float = Field(
        default=0.08, ge=0.0, le=1.0, description="Earnings quality weight"
    )

    model_config = ConfigDict(extra="allow")

    def get_weight(self, factor_name: str) -> float:
        return getattr(self, factor_name, 0.0)

    def as_dict(self) -> dict[str, float]:
        return {k: v for k, v in self.model_dump().items() if isinstance(v, int | float)}

    def total_weight(self) -> float:
        return sum(self.as_dict().values())

    def normalize(self) -> FactorWeightsConfig:
        total = self.total_weight()
        if total == 0:
            return self
        data = self.model_dump()
        normalized = {k: v / total for k, v in data.items() if isinstance(v, int | float)}
        return FactorWeightsConfig(**normalized)


class DataSourceConfig(BaseModel):
    """Data source configuration."""

    primary_provider: str = Field(default="yfinance", description="Primary data provider")
    fallback_providers: list[str] = Field(default=["stooq"], description="Fallback providers")
    cache_ttl_seconds: int = Field(default=3600, ge=0, description="Data cache TTL")
    max_retries: int = Field(default=3, ge=0, le=10, description="Max retry attempts")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=120.0, description="Request timeout")
    use_proxy: bool = Field(default=False, description="Use proxy for requests")


class MarketDataConfig(BaseModel):
    """Live market-data / macro-tape layer (new)."""

    enabled: bool = Field(default=True, description="Enable the live market data layer")
    quote_ttl_seconds: float = Field(
        default=60.0, ge=5.0, le=3600.0, description="Per-quote cache TTL"
    )
    macro_ttl_seconds: float = Field(
        default=600.0, ge=30.0, le=7200.0, description="Macro snapshot cache TTL"
    )
    tick_refresh_seconds: float = Field(
        default=3.0, ge=0.5, le=60.0, description="Active-ticker live re-poll interval"
    )
    after_hours_backoff: bool = Field(
        default=True, description="Slow refresh when the US cash session is closed"
    )
    ribbon_enabled: bool = Field(default=True, description="Show the scrolling market ribbon")
    ribbon_cycle_seconds: float = Field(
        default=5.0, ge=1.0, le=30.0, description="Seconds per ribbon group before cycling"
    )


class DisplayConfig(BaseModel):
    """Watchlist, coverage and theme (new — was hardcoded in the TUI)."""

    watchlist: list[str] = Field(
        default=["TSLA", "MSFT", "AAPL", "NVDA", "META"],
        description="Tickers shown in the live watchlist",
    )
    coverage: list[str] = Field(
        default_factory=list, description="Research coverage universe (background-refreshed)"
    )
    default_ticker: str = Field(default="AAPL", description="Ticker loaded at launch")
    watchlist_sort: str = Field(
        default="manual", description="Watchlist sort: manual, change, upside, composite"
    )
    theme: str = Field(default="cyan", description="Phosphor theme: cyan, amber, green")


class TerminalConfig(BaseModel):
    """Terminal UI configuration."""

    width: int = Field(default=80, ge=40, le=400, description="Terminal width")
    height: int = Field(default=40, ge=20, le=200, description="Terminal height")
    refresh_rate: float = Field(
        default=0.1, ge=0.02, le=1.0, description="Render loop cadence (seconds)"
    )
    color_mode: str = Field(default="auto", description="Color mode: auto, color, mono")
    unicode_enabled: bool = Field(default=True, description="Enable Unicode characters")
    show_debug_info: bool = Field(default=False, description="Show debug information")
    # Forced fixed-resolution window (e.g. a square 800x800 px viewport)
    force_window: bool = Field(default=False, description="Lock the terminal to a fixed pixel size")
    window_px_width: int = Field(default=800, ge=200, le=4000, description="Forced window width (px)")
    window_px_height: int = Field(
        default=800, ge=200, le=4000, description="Forced window height (px)"
    )
    cell_px_width: int = Field(default=8, ge=4, le=32, description="Monospace cell width (px)")
    cell_px_height: int = Field(default=16, ge=6, le=48, description="Monospace cell height (px)")


class PipelineConfig(BaseModel):
    """Valuation pipeline configuration."""

    enable_dcf: bool = Field(default=True, description="Enable DCF valuation")
    enable_multiples: bool = Field(default=True, description="Enable multiples analysis")
    enable_scenario: bool = Field(default=True, description="Enable scenario analysis")
    forecast_periods: int = Field(default=10, ge=1, le=30, description="DCF forecast period")
    default_forecast_growth: float = Field(
        default=0.08, ge=-0.5, le=1.0, description="Default forecast growth when unspecified"
    )
    terminal_growth_rate: float = Field(
        default=0.025, ge=0.0, le=0.06, description="Default terminal growth"
    )
    discount_rate_floor: float = Field(
        default=0.06, ge=0.0, le=0.30, description="Minimum discount rate"
    )
    discount_rate_ceiling: float = Field(
        default=0.15, ge=0.0, le=0.40, description="Maximum discount rate"
    )


class AsyncConfig(BaseModel):
    """Async execution configuration."""

    enabled: bool = Field(default=True, description="Enable async execution")
    max_workers: int = Field(default=4, ge=1, le=32, description="Thread pool size")
    task_timeout_seconds: float = Field(default=60.0, ge=1.0, description="Task timeout")
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
    max_size_mb: int = Field(default=50, ge=1, description="Max log file size")
    backup_count: int = Field(default=5, ge=0, description="Number of backup logs")


class RiskLimitsConfig(BaseModel):
    """Risk management limits."""

    max_concentration: float = Field(
        default=0.20, ge=0.0, le=1.0, description="Max position concentration"
    )
    max_drawdown: float = Field(default=0.15, ge=0.0, le=1.0, description="Max portfolio drawdown")
    var_confidence: float = Field(
        default=0.95, ge=0.50, le=0.999, description="VaR confidence level"
    )
    stress_test_percentile: float = Field(
        default=0.05, ge=0.0, le=0.50, description="Stress test percentile"
    )


class TerminalSettings(BaseModel):
    """Complete terminal configuration."""

    factor_weights: FactorWeightsConfig = Field(default_factory=FactorWeightsConfig)
    data_source: DataSourceConfig = Field(default_factory=DataSourceConfig)
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    async_config: AsyncConfig = Field(default_factory=AsyncConfig, alias="async")
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    risk_limits: RiskLimitsConfig = Field(default_factory=RiskLimitsConfig)

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_file(cls, path: str | Path) -> TerminalSettings:
        import json

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Settings file not found: {path}")
        try:
            import yaml  # type: ignore[import-untyped]

            with open(path) as f:
                data = yaml.safe_load(f)
        except ImportError:
            if path.suffix != ".json":
                raise ImportError(
                    "PyYAML required for .yml/.yaml files. Install with: pip install pyyaml"
                )
            with open(path) as f:
                data = json.load(f)
        return cls(**(data or {}))

    @classmethod
    def from_env(cls) -> TerminalSettings:
        import os

        if env_config := os.environ.get("IAM_CONFIG"):
            if Path(env_config).exists():
                return cls.from_file(env_config)
        for path in [
            Path.home() / ".iam" / "settings.yml",
            Path("settings.yml"),
            Path("config.yml"),
        ]:
            if path.exists():
                return cls.from_file(path)
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    def to_file(self, path: str | Path) -> None:
        """Persist settings.  Writes YAML for .yml/.yaml, else JSON."""
        import json

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        if path.suffix in (".yml", ".yaml"):
            try:
                import yaml  # type: ignore[import-untyped]

                with open(path, "w") as f:
                    yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
                return
            except ImportError:
                pass  # fall through to JSON
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


# Global settings instance
_global_settings: TerminalSettings | None = None


def get_settings() -> TerminalSettings:
    global _global_settings
    if _global_settings is None:
        _global_settings = TerminalSettings.from_env()
    return _global_settings


def set_settings(settings: TerminalSettings) -> None:
    global _global_settings
    _global_settings = settings


def default_settings_path() -> Path:
    """Canonical save location for the in-app settings editor."""
    return Path.home() / ".iam" / "settings.yml"
