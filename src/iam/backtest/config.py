"""Typed, frozen backtest configuration (source of truth for all paths and parameters)."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class BacktestConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    """Immutable backtest configuration with validation and computed properties."""

    universe_name: str = Field(
        "sp100", description="Universe identifier (matches data/universe/*.json)"
    )
    start: str = Field("2018-01-31", description="Start date (YYYY-MM-DD)")
    end: str = Field("2024-12-31", description="End date (YYYY-MM-DD)")
    freq: str = Field("ME", description="Evaluation frequency (ME=month-end, D=daily)")
    horizon_days: int = Field(63, ge=1, description="Primary forward return horizon in days (used for top-line IC)")
    horizons_days: list[int] = Field(
        default_factory=lambda: [21, 63, 126, 252],
        description="Multi-horizon windows in days; all are pre-computed in the price parquet",
    )
    cost_bps: float = Field(5.0, ge=0, description="Transaction cost in basis points")
    yfinance_timeout: float = Field(10.0, ge=1, description="yfinance timeout in seconds")
    stooq_timeout: float = Field(15.0, ge=1, description="Stooq timeout in seconds")
    n_jobs_io: int = Field(12, ge=1, description="Number of IO workers for price downloads")
    n_jobs_cpu: int = Field(4, ge=1, description="Number of CPU workers for scoring")
    data_root: Path = Field(Path("data"), description="Root directory for data artifacts")
    cache_dir: Path = Field(Path(".cache"), description="Cache directory for snapshots")

    @property
    def price_file(self) -> Path:
        """Path to cached price parquet file."""
        return self.data_root / "prices" / f"{self.universe_name}.parquet"

    @property
    def universe_file(self) -> Path:
        """Path to static universe JSON file."""
        return self.data_root / "universe" / f"{self.universe_name}.json"

    @property
    def snapshot_cache(self) -> Path:
        """Path to snapshot diskcache directory."""
        return self.cache_dir / "snapshots"

    @property
    def results_dir(self) -> Path:
        """Path to results directory."""
        return self.data_root / "results"

    def validate_paths(self) -> None:
        """Create necessary directories if they don't exist."""
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_cache.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        (self.data_root / "prices").mkdir(parents=True, exist_ok=True)
        (self.data_root / "universe").mkdir(parents=True, exist_ok=True)
