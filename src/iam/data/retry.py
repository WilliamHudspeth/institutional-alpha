"""Shared retry/backoff utility for the data layer.

This is the single retry implementation for flaky external data calls.
Both :mod:`iam.data.fetcher` (via the :func:`with_retry` decorator) and
:mod:`iam.data.providers.yfinance_adapter` (via :func:`retry_call`) build on
it, so backoff behavior is defined in exactly one place.

Backoff schedule (before retry ``i``, zero-indexed)::

    delay = base_delay * (2 ** i) + uniform(0, jitter)

``jitter=0`` (the default) reproduces the deterministic doubling that
``fetcher.with_retry`` historically used; ``jitter=1.0`` reproduces the
jittered schedule the yfinance adapter historically used.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    jitter: float = 0.0,
    rate_limiter: Any | None = None,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    description: str | None = None,
) -> T:
    """Call ``func`` with exponential backoff, returning its first success.

    Args:
        func: zero-argument callable to invoke (wrap args in a lambda/closure).
        attempts: total number of attempts (>= 1), not "retries after the first".
        base_delay: initial backoff delay in seconds; doubles each retry.
        jitter: adds ``uniform(0, jitter)`` seconds to each delay (0 = none).
        rate_limiter: optional object with an ``is_allowed() -> bool`` method
            (e.g. :class:`iam.validation.rate_limiter.RateLimiter`); each
            attempt blocks until it allows the call.
        retry_on: exception types that trigger a retry; anything else
            propagates immediately.
        description: human-readable label for log messages (defaults to
            ``func.__name__``).

    Raises:
        The last exception raised by ``func`` once all attempts are exhausted.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    label = description or getattr(func, "__name__", "call")
    last_exception: BaseException | None = None

    for attempt in range(attempts):
        try:
            if rate_limiter is not None:
                while not rate_limiter.is_allowed():
                    time.sleep(0.1)
            return func()
        except retry_on as exc:
            last_exception = exc
            if attempt == attempts - 1:
                break
            delay = base_delay * (2**attempt)
            if jitter > 0:
                delay += random.uniform(0, jitter)
            logger.warning(
                "Attempt %d/%d failed for %s: %s. Retrying in %.2fs",
                attempt + 1,
                attempts,
                label,
                exc,
                delay,
            )
            time.sleep(delay)

    assert last_exception is not None  # attempts >= 1 guarantees this
    raise last_exception


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    rate_limit_per_sec: int = 5,
    jitter: float = 0.0,
):
    """Decorator form of :func:`retry_call` with built-in rate limiting.

    ``max_retries`` counts retries *after* the first attempt (so the wrapped
    function is called at most ``max_retries + 1`` times), matching the
    historical ``iam.data.fetcher.with_retry`` contract.
    """
    from iam.validation.rate_limiter import RateLimiter

    limiter = RateLimiter(max_calls=rate_limit_per_sec, period_seconds=1.0)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry_call(
                lambda: func(*args, **kwargs),
                attempts=max_retries + 1,
                base_delay=base_delay,
                jitter=jitter,
                rate_limiter=limiter,
                description=func.__name__,
            )

        return wrapper

    return decorator
