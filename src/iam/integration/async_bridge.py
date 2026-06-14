"""Bridge between async data layer and existing pipeline/factor systems.

Enables non-blocking integration of:
- Pipeline orchestrator
- Factor engines
- Thesis engine
- Backtest harness

Allows existing blocking code to run asynchronously without modification.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from iam.data.async_loader import get_async_loader
from iam.ui.events import EventType, emit_event

logger = logging.getLogger(__name__)


class AsyncPipelineAdapter:
    """Bridges async loader with ValuationPipeline."""

    def __init__(self) -> None:
        self.loader = get_async_loader(max_workers=4)

    def run_pipeline_async(
        self,
        ticker: str,
        pipeline_fn: Callable[[str], dict[str, Any]],
        on_complete: Callable[[str, dict[str, Any]], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> str:
        """Run pipeline asynchronously.

        Args:
            ticker: Security ticker
            pipeline_fn: Pipeline execution function (blocking)
            on_complete: Success callback
            on_error: Error callback

        Returns:
            Task ID for tracking
        """
        task_id = f"pipeline_{ticker}"

        def wrapped_pipeline() -> dict[str, Any]:
            """Wrapped pipeline that emits progress events."""
            try:
                result = pipeline_fn(ticker)
                emit_event(
                    EventType.PIPELINE_COMPLETE,
                    {"ticker": ticker, "success": True},
                    source="pipeline_adapter",
                )
                return result
            except Exception as e:
                emit_event(
                    EventType.PIPELINE_ERROR,
                    {"ticker": ticker, "error": str(e)},
                    source="pipeline_adapter",
                )
                raise

        self.loader.compute_pipeline_async(
            ticker,
            wrapped_pipeline,
            on_complete=on_complete,
            on_error=on_error,  # type: ignore
        )

        return task_id

    def get_pipeline_result(self, ticker: str, timeout: float = 60.0) -> dict[str, Any]:
        """Wait for and retrieve pipeline result."""
        task_id = f"pipeline_{ticker}"
        _, result = self.loader.wait_for_task(task_id, timeout=timeout)
        return result  # type: ignore


class AsyncFactorAdapter:
    """Bridges async loader with factor engines."""

    def __init__(self) -> None:
        self.loader = get_async_loader(max_workers=4)

    def score_factors_async(
        self,
        ticker: str,
        factor_fn: Callable[[str], dict[str, float]],
        on_complete: Callable[[str, dict[str, float]], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> str:
        """Score factors asynchronously.

        Args:
            ticker: Security ticker
            factor_fn: Factor scoring function
            on_complete: Success callback
            on_error: Error callback

        Returns:
            Task ID
        """
        self.loader.score_factors_async(ticker, factor_fn, on_complete, on_error)  # type: ignore
        return f"factors_{ticker}"

    def get_factor_result(self, ticker: str, timeout: float = 30.0) -> dict[str, float]:
        """Wait for and retrieve factor scores."""
        task_id = f"factors_{ticker}"
        _, result = self.loader.wait_for_task(task_id, timeout=timeout)
        return result  # type: ignore


class AsyncSecurityDataAdapter:
    """Bridges async loader with data providers."""

    def __init__(self) -> None:
        self.loader = get_async_loader(max_workers=8)

    def fetch_security_async(
        self,
        ticker: str,
        fetch_fn: Callable[[str], dict[str, Any]],
        on_complete: Callable[[str, dict[str, Any]], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> str:
        """Fetch security data asynchronously.

        Args:
            ticker: Security ticker
            fetch_fn: Data fetching function
            on_complete: Success callback
            on_error: Error callback

        Returns:
            Task ID
        """
        self.loader.load_security_async(ticker, fetch_fn, on_complete, on_error)
        return f"security_{ticker}"

    def get_security_result(self, ticker: str, timeout: float = 10.0) -> dict[str, Any]:
        """Wait for and retrieve security data."""
        task_id = f"security_{ticker}"
        _, result = self.loader.wait_for_task(task_id, timeout=timeout)
        return result  # type: ignore


class ParallelWorkflow:
    """Execute multiple tasks in parallel and collect results.

    Example:
        workflow = ParallelWorkflow()
        workflow.add_pipeline(ticker, pipeline_fn)
        workflow.add_factors(ticker, factors_fn)
        workflow.add_security_data(ticker, data_fn)
        results = workflow.execute_and_wait(timeout=60)
    """

    def __init__(self) -> None:
        self.pipeline_adapter = AsyncPipelineAdapter()
        self.factor_adapter = AsyncFactorAdapter()
        self.data_adapter = AsyncSecurityDataAdapter()
        self.tasks: dict[str, str] = {}

    def add_pipeline(
        self,
        ticker: str,
        pipeline_fn: Callable[[str], dict[str, Any]],
    ) -> None:
        """Add a pipeline task."""
        task_id = self.pipeline_adapter.run_pipeline_async(ticker, pipeline_fn)
        self.tasks[f"pipeline_{ticker}"] = task_id

    def add_factors(
        self,
        ticker: str,
        factor_fn: Callable[[str], dict[str, float]],
    ) -> None:
        """Add a factor scoring task."""
        task_id = self.factor_adapter.score_factors_async(ticker, factor_fn)
        self.tasks[f"factors_{ticker}"] = task_id

    def add_security_data(
        self,
        ticker: str,
        fetch_fn: Callable[[str], dict[str, Any]],
    ) -> None:
        """Add a security data fetch task."""
        task_id = self.data_adapter.fetch_security_async(ticker, fetch_fn)
        self.tasks[f"data_{ticker}"] = task_id

    def execute_and_wait(self, timeout: float = 60.0) -> dict[str, Any]:
        """Execute all tasks and wait for completion."""
        results = {}

        for task_name in self.tasks:
            try:
                if task_name.startswith("pipeline_"):
                    ticker = task_name.replace("pipeline_", "")
                    results[task_name] = self.pipeline_adapter.get_pipeline_result(ticker, timeout)
                elif task_name.startswith("factors_"):
                    ticker = task_name.replace("factors_", "")
                    results[task_name] = self.factor_adapter.get_factor_result(ticker, timeout)
                elif task_name.startswith("data_"):
                    ticker = task_name.replace("data_", "")
                    results[task_name] = self.data_adapter.get_security_result(ticker, timeout)
            except Exception as e:
                logger.error(f"Task {task_name} failed: {e}")
                results[task_name] = None  # type: ignore

        return results

    def execute_non_blocking(self) -> None:
        """Execute all tasks without blocking (fire and forget)."""
        # Tasks are already submitted to executor
        pass
