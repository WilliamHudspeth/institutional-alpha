"""Async data loading layer for non-blocking terminal operations.

Enables parallel data fetching, computation, and UI updates while keeping
the terminal responsive. Uses ThreadPoolExecutor for CPU-bound work like
factor scoring and DCF calculations.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from iam.ui.events import EventType, emit_event

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncDataLoader:
    """Non-blocking data loader for terminal operations.

    Manages:
    - Parallel data fetching
    - Background computation
    - Event emission on completion
    - Error handling and timeouts
    """

    def __init__(self, max_workers: int = 4) -> None:
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, Any] = {}

    def load_security_async(
        self,
        ticker: str,
        loader_fn: Callable[[str], dict[str, Any]],
        on_complete: Callable[[str, dict[str, Any]], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """Load a security's data asynchronously.

        Args:
            ticker: Security ticker symbol
            loader_fn: Function that loads security data (blocking)
            on_complete: Callback when loading completes
            on_error: Callback if loading fails
        """
        task_id = f"load_{ticker}"

        def worker() -> tuple[str, dict[str, Any]]:
            """Worker function that loads data."""
            try:
                emit_event(
                    EventType.PIPELINE_START,
                    {"ticker": ticker, "task": "load_security"},
                    source="async_loader",
                )

                result = loader_fn(ticker)

                emit_event(
                    EventType.SECURITY_LOADED,
                    {"ticker": ticker, "success": True},
                    source="async_loader",
                )

                if on_complete:
                    on_complete(ticker, result)

                return ticker, result
            except Exception as e:
                emit_event(
                    EventType.PIPELINE_ERROR,
                    {"ticker": ticker, "error": str(e)},
                    source="async_loader",
                )

                if on_error:
                    on_error(ticker, e)

                raise

        future = self.executor.submit(worker)
        self._tasks[task_id] = future

    def compute_pipeline_async(
        self,
        ticker: str,
        pipeline_fn: Callable[[str], dict[str, Any]],
        on_complete: Callable[[str, dict[str, Any]], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """Run valuation pipeline asynchronously.

        Args:
            ticker: Security ticker
            pipeline_fn: Pipeline computation function (blocking)
            on_complete: Callback on success
            on_error: Callback on error
        """
        task_id = f"pipeline_{ticker}"

        def worker() -> tuple[str, dict[str, Any]]:
            """Worker function that runs pipeline."""
            try:
                emit_event(
                    EventType.PIPELINE_START,
                    {"ticker": ticker, "task": "run_pipeline"},
                    source="async_loader",
                )

                result = pipeline_fn(ticker)

                emit_event(
                    EventType.PIPELINE_COMPLETE,
                    {"ticker": ticker, "success": True},
                    source="async_loader",
                )

                if on_complete:
                    on_complete(ticker, result)

                return ticker, result
            except Exception as e:
                emit_event(
                    EventType.PIPELINE_ERROR,
                    {"ticker": ticker, "error": str(e)},
                    source="async_loader",
                )

                if on_error:
                    on_error(ticker, e)

                raise

        future = self.executor.submit(worker)
        self._tasks[task_id] = future

    def score_factors_async(
        self,
        ticker: str,
        factor_fn: Callable[[str], dict[str, float]],
        on_complete: Callable[[str, dict[str, float]], None] | None = None,
    ) -> None:
        """Score factors asynchronously.

        Args:
            ticker: Security ticker
            factor_fn: Factor scoring function
            on_complete: Callback on completion
        """
        task_id = f"factors_{ticker}"

        def worker() -> tuple[str, dict[str, float]]:
            """Worker that scores factors."""
            try:
                emit_event(
                    EventType.FACTOR_COMPLETE,
                    {"ticker": ticker, "status": "computing"},
                    source="async_loader",
                )

                result = factor_fn(ticker)

                emit_event(
                    EventType.FACTOR_COMPLETE,
                    {"ticker": ticker, "status": "complete"},
                    source="async_loader",
                )

                if on_complete:
                    on_complete(ticker, result)

                return ticker, result
            except Exception as e:
                emit_event(
                    EventType.FACTOR_ERROR,
                    {"ticker": ticker, "error": str(e)},
                    source="async_loader",
                )
                raise

        future = self.executor.submit(worker)
        self._tasks[task_id] = future

    def get_task(self, task_id: str) -> Any:
        """Get a submitted task future."""
        return self._tasks.get(task_id)

    def is_task_complete(self, task_id: str) -> bool:
        """Check if a task has completed."""
        future = self._tasks.get(task_id)
        if future is None:
            return False
        return future.done()

    def get_task_result(self, task_id: str, timeout: float = 5.0) -> Any:
        """Get result from a completed task."""
        future = self._tasks.get(task_id)
        if future is None:
            raise ValueError(f"Task {task_id} not found")

        try:
            return future.result(timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

    def wait_for_task(self, task_id: str, timeout: float = 30.0) -> Any:
        """Block until task completes and return result."""
        future = self._tasks.get(task_id)
        if future is None:
            raise ValueError(f"Task {task_id} not found")

        return future.result(timeout=timeout)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""
        future = self._tasks.get(task_id)
        if future is None:
            return False
        return future.cancel()

    def shutdown(self) -> None:
        """Shutdown executor and wait for pending tasks."""
        self.executor.shutdown(wait=True)

    def __enter__(self) -> AsyncDataLoader:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.shutdown()


# Global async loader instance
_global_loader: AsyncDataLoader | None = None


def get_async_loader(max_workers: int = 4) -> AsyncDataLoader:
    """Get or create global async loader."""
    global _global_loader
    if _global_loader is None:
        _global_loader = AsyncDataLoader(max_workers=max_workers)
    return _global_loader
