import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

class SecretsManager:
    """Utility for safely loading API secrets without leaking/printing them."""

    @staticmethod
    def get_secret(key: str, default: Any = None) -> Any:
        """Retrieve a secret from the environment.
        
        Logs masked debug info rather than raw values.
        """
        val = os.environ.get(key)
        if val is None:
            logger.debug(f"Secret key '{key}' not found in environment. Using default.")
            return default
        
        # Mask secrets: e.g. "mysecret123" -> "myse******"
        masked = val[:4] + "*" * (len(val) - 4) if len(val) > 4 else "***"
        logger.debug(f"Retrieved secret key '{key}' (val: {masked})")
        return val

    @staticmethod
    def require_secret(key: str) -> str:
        """Require a secret to be set, raising ValueError if missing."""
        val = SecretsManager.get_secret(key)
        if not val:
            raise ValueError(
                f"Missing required API credentials. Please set environment variable: {key}"
            )
        return val
