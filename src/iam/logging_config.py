import logging
import logging.config
import os
from typing import Any

def setup_logging(
    default_level: int = logging.INFO,
    env_key: str = "LOG_LEVEL",
    log_file: str | None = "institutional_alpha.log"
) -> None:
    """Setup logging configuration."""
    level = default_level
    value = os.getenv(env_key, None)
    if value:
        level = getattr(logging, value.upper(), default_level)

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": level,
                "propagate": True
            },
            "iam": {
                "handlers": ["console"],
                "level": level,
                "propagate": False
            },
        }
    }

    if log_file:
        config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": level,
            "formatter": "detailed",
            "filename": log_file,
            "maxBytes": 10485760, # 10MB
            "backupCount": 5,
            "encoding": "utf8",
        }
        config["loggers"][""]["handlers"].append("file")
        config["loggers"]["iam"]["handlers"].append("file")

    logging.config.dictConfig(config)
