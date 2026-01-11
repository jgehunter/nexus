"""Structured logging setup using rich.

Provides consistent logging configuration across the application.
"""

import logging
import sys
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def setup_logging(
    level: LogLevel = "INFO",
    show_path: bool = True,
    show_time: bool = True,
) -> logging.Logger:
    """Configure structured logging with rich output.

    Args:
        level: Logging level
        show_path: Show file path in log output
        show_time: Show timestamp in log output

    Returns:
        Configured root logger
    """
    console = Console(stderr=True)

    handler = RichHandler(
        console=console,
        show_path=show_path,
        show_time=show_time,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
    )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )

    return logging.getLogger()


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def configure_uvicorn_logging(level: LogLevel = "INFO") -> dict:
    """Get logging configuration for uvicorn.

    Returns:
        Dictionary suitable for uvicorn's log_config parameter
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(levelname)s | %(name)s | %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            },
        },
    }
