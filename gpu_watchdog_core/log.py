from __future__ import annotations

import logging
import os
import sys
from typing import Optional


logger = logging.getLogger("gpu_watchdog")

RESET = "\033[0m"
TIME_COLOR = "\033[32m"
LOCATION_COLOR = "\033[36m"
LEVEL_COLORS = {
    "DEBUG": "\033[34m",
    "INFO": "\033[1;37m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[1;37;41m",
}


class LoguruLikeFormatter(logging.Formatter):
    def __init__(self, color: bool = False) -> None:
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        log_time = f"{self.formatTime(record, self.datefmt)}.{int(record.msecs):03d}"
        log_level = f"{record.levelname:<8}"
        log_location = f"{record.module}:{record.funcName}:{record.lineno}"
        log_message = record.message

        if self.color:
            level_color = LEVEL_COLORS.get(record.levelname, "")
            log_time = f"{TIME_COLOR}{log_time}{RESET}"
            log_location = (
                f"{LOCATION_COLOR}{record.module}{RESET}:"
                f"{LOCATION_COLOR}{record.funcName}{RESET}:"
                f"{LOCATION_COLOR}{record.lineno}{RESET}"
            )
            if level_color:
                log_level = f"{level_color}{log_level}{RESET}"
                log_message = f"{level_color}{log_message}{RESET}"

        formatted = f"{log_time} | {log_level} | {log_location} - {log_message}"
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            formatted = f"{formatted}\n{record.exc_text}"
        if record.stack_info:
            formatted = f"{formatted}\n{self.formatStack(record.stack_info)}"
        return formatted


def should_colorize(color: Optional[bool] = None) -> bool:
    if color is not None:
        return color
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stderr.isatty()


def configure_logging(level: str = "INFO", color: Optional[bool] = None) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(LoguruLikeFormatter(color=should_colorize(color)))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )

if __name__ == "__main__":
    configure_logging(level="DEBUG")
    logger.debug("test")
    logger.info("test")
    logger.warning("test")
    logger.error("test")
    logger.critical("test")
