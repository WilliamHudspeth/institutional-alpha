import time
from collections import deque
from collections.abc import Callable
from functools import wraps
from typing import Any


class RateLimiter:
    """Sliding-window rate limiter utility.

    Tracks timestamps of calls and blocks (or sleeps/raises) if limit exceeded.
    """

    def __init__(self, max_calls: int, period_seconds: float):
        """
        Args:
            max_calls: Maximum number of calls allowed in the period.
            period_seconds: The time period in seconds.
        """
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.calls = deque()  # type: ignore

    def is_allowed(self) -> bool:
        """Check if call is allowed under the rate limit, removing expired timestamps."""
        now = time.time()
        # Remove timestamps older than the sliding window
        while self.calls and self.calls[0] <= now - self.period_seconds:
            self.calls.popleft()

        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False

    def limit(self, block: bool = False) -> Callable:
        """Decorator to rate-limit a function.

        Args:
            block: If True, blocks/sleeps until rate limit reset.
                   If False, raises RuntimeError.
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                while not self.is_allowed():
                    if block:
                        # Sleep until the oldest call expires
                        sleep_time = self.calls[0] + self.period_seconds - time.time()
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                    else:
                        raise RuntimeError(
                            f"Rate limit exceeded: max {self.max_calls} calls "
                            f"per {self.period_seconds}s window."
                        )
                return func(*args, **kwargs)

            return wrapper

        return decorator
