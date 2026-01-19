"""Logging configuration for Inventor Exporter.

Provides structured logging to console and file with configurable levels.
Uses Python's standard logging module with dictConfig for flexibility.
"""

import logging
import logging.config
from pathlib import Path
from typing import Optional

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
            "stream": "ext://sys.stderr",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "inventor_export.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 3,
        },
    },
    "loggers": {
        "inventor_exporter": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
            "propagate": False,
        },
    },
    "root": {
        "level": "WARNING",
        "handlers": ["console"],
    },
}


def setup_logging(
    log_file: Optional[Path] = None,
    console_level: str = "INFO",
    file_level: str = "DEBUG",
) -> None:
    """
    Configure logging for the application.

    Args:
        log_file: Path to log file. If None, uses default in current directory.
        console_level: Minimum level for console output (DEBUG, INFO, WARNING, ERROR)
        file_level: Minimum level for file output (DEBUG, INFO, WARNING, ERROR)

    Should be called once at application startup.

    Example:
        setup_logging(log_file=Path("export.log"), console_level="DEBUG")
    """
    import copy
    config = copy.deepcopy(LOGGING_CONFIG)

    if log_file is not None:
        config["handlers"]["file"]["filename"] = str(log_file)

    config["handlers"]["console"]["level"] = console_level.upper()
    config["handlers"]["file"]["level"] = file_level.upper()

    logging.config.dictConfig(config)

    logger = logging.getLogger("inventor_exporter")
    logger.debug("Logging initialized")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a module.

    Args:
        name: Module name, usually __name__ for automatic module hierarchy

    Returns:
        Logger instance under the inventor_exporter namespace

    Example:
        logger = get_logger(__name__)
        logger.info("Processing assembly...")
    """
    return logging.getLogger(f"inventor_exporter.{name}")
