import os
import time

import pytest

from iam.config.secrets import SecretsManager
from iam.validation.rate_limiter import RateLimiter


def test_secrets_manager():
    # Set test environment variable
    os.environ["TEST_SECRET_KEY"] = "supersecretpassword"

    assert SecretsManager.get_secret("TEST_SECRET_KEY") == "supersecretpassword"
    assert SecretsManager.require_secret("TEST_SECRET_KEY") == "supersecretpassword"

    assert SecretsManager.get_secret("NON_EXISTENT_KEY", default="fallback") == "fallback"

    with pytest.raises(ValueError, match="Missing required API credentials"):
        SecretsManager.require_secret("NON_EXISTENT_KEY")


def test_rate_limiter_is_allowed():
    # 2 calls allowed per 1 second
    limiter = RateLimiter(max_calls=2, period_seconds=1.0)

    assert limiter.is_allowed() is True
    assert limiter.is_allowed() is True
    assert limiter.is_allowed() is False  # 3rd call in 1s window is blocked


def test_rate_limiter_decorator():
    limiter = RateLimiter(max_calls=2, period_seconds=0.5)

    calls = []

    @limiter.limit(block=False)
    def my_func(x):
        calls.append(x)
        return x

    assert my_func(1) == 1
    assert my_func(2) == 2

    with pytest.raises(RuntimeError, match="Rate limit exceeded"):
        my_func(3)


def test_rate_limiter_blocking_decorator():
    limiter = RateLimiter(max_calls=2, period_seconds=0.1)

    @limiter.limit(block=True)
    def my_func():
        return True

    assert my_func() is True
    assert my_func() is True

    # 3rd call will block and wait for the window to slide
    t0 = time.time()
    assert my_func() is True
    t1 = time.time()

    # Verify that it actually blocked/slept (took at least ~0.05 seconds or so)
    assert t1 - t0 >= 0.05
