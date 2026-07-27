"""
logger.py
=========
Central logging setup. Produces:
  - logs/execution.log  — everything, rotating
  - logs/error.log      — WARNING and above only
  - logs/api.log        — PageSpeed Insights API request/response activity
  - logs/YYYY-MM-DD.log — a per-day log for quick "what happened today" review

All loggers also echo to stdout so GitHub Actions run logs show activity
live, not just after the fact.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

from config import LOGS_DIR, TIMEZONE

_FORMAT = "%(asctime)s IST | %(levelname)-8s | %(name)-12s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _now_ist() -> datetime:
    # Deliberately duplicated from utils.now_ist() rather than imported:
    # utils.py imports get_logger from this module, so importing utils
    # here would create a circular import. config.TIMEZONE is the shared
    # source of truth either way.
    return datetime.now(TIMEZONE)


def _ist_time_converter(*_args) -> time.struct_time:
    """logging.Formatter's default time converter (time.localtime) uses
    the HOST machine's local time — UTC on a GitHub Actions runner — so
    every log line was silently timestamped in UTC regardless of the rest
    of the project being IST-stamped. This forces every log record's
    %(asctime)s to Asia/Kolkata, matching Sheets/dashboard/email."""
    return _now_ist().timetuple()


def _make_formatter() -> logging.Formatter:
    formatter = logging.Formatter(_FORMAT, _DATEFMT)
    formatter.converter = _ist_time_converter
    return formatter


def _make_handler(path, level=logging.INFO) -> logging.Handler:
    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(_make_formatter())
    return handler


_configured = False


def setup_logging() -> None:
    """Idempotent — safe to call multiple times (e.g. from tests)."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(_make_formatter())
    root.addHandler(console)

    root.addHandler(_make_handler(LOGS_DIR / "execution.log", logging.INFO))
    root.addHandler(_make_handler(LOGS_DIR / "error.log", logging.WARNING))

    # Per-day log filename — was datetime.now() (host-local/UTC on CI),
    # now IST so the log file date always matches the IST date shown
    # everywhere else on the dashboard, not the UTC date.
    today = _now_ist().strftime("%Y-%m-%d")
    root.addHandler(_make_handler(LOGS_DIR / f"{today}.log", logging.INFO))

    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def get_api_logger() -> logging.Logger:
    """Separate logger + file specifically for PageSpeed Insights API traffic,
    so a busy run doesn't bury API-level detail in the general log."""
    setup_logging()
    logger = logging.getLogger("api")
    if not any(isinstance(h, RotatingFileHandler) and "api.log" in str(h.baseFilename) for h in logger.handlers):
        logger.addHandler(_make_handler(LOGS_DIR / "api.log", logging.DEBUG))
        logger.propagate = True
    return logger
