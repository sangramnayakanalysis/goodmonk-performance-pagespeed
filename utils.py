"""
utils.py
========
Small, dependency-free helpers shared across modules: a retry decorator
with backoff + rate-limit awareness, JSON read/write helpers, and time
formatting.

Timezone handling: every "now" helper here is IST-aware (Asia/Kolkata),
via now_ist(). This matters because plain `datetime.now()` (what this
file used before) returns the HOST MACHINE's local time — which is UTC
on a GitHub Actions runner but could be anything on a developer's own
machine, so Sheets rows and dashboard timestamps would silently drift
between environments. now_ist() always returns the same IST wall-clock
time regardless of what timezone the machine it's running on is set to.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from config import TIMEZONE
from logger import get_logger

log = get_logger("utils")

T = TypeVar("T")


class RateLimitedError(Exception):
    """Raised by API code to signal a 429 — caught specially by retry_with_backoff."""


def retry_with_backoff(
    max_retries: int,
    base_delay_seconds: float,
    rate_limit_wait_seconds: float,
    label: str = "operation",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator: retries the wrapped call on any exception, using linear
    backoff (base_delay * attempt). A RateLimitedError gets a fixed,
    longer wait instead, since a 429 needs real cooldown, not a quick
    retry. Re-raises the last error if every attempt is exhausted, so
    the caller can decide how to record the failure — nothing is
    silently swallowed.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RateLimitedError as e:
                    last_exc = e
                    log.warning("%s rate-limited (attempt %d/%d). Waiting %.0fs.",
                                label, attempt, max_retries, rate_limit_wait_seconds)
                    if attempt < max_retries:
                        time.sleep(rate_limit_wait_seconds)
                except Exception as e:  # noqa: BLE001 — intentionally broad, this is a generic retry wrapper
                    last_exc = e
                    log.warning("%s failed (attempt %d/%d): %s", label, attempt, max_retries, e)
                    if attempt < max_retries:
                        time.sleep(base_delay_seconds * attempt)
            log.error("%s failed after %d attempts: %s", label, max_retries, last_exc)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


def read_json(path: Path, default: Any = None) -> Any:
    if not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    tmp.replace(path)  # atomic on POSIX — dashboard never reads a half-written file


def now_ist() -> datetime:
    """Current time as a timezone-aware datetime in Asia/Kolkata (IST),
    regardless of the host machine's own local timezone."""
    return datetime.now(TIMEZONE)


def now_date_str() -> str:
    return now_ist().strftime("%Y-%m-%d")


def now_time_str() -> str:
    return now_ist().strftime("%H:%M:%S")


def now_iso() -> str:
    """ISO-8601 timestamp with an explicit +05:30 offset, e.g.
    '2026-07-24T16:30:00+05:30' — unambiguous regardless of where it's
    read back (Sheets, dashboard JSON, email), since the offset travels
    with the value."""
    return now_ist().isoformat(timespec="seconds")
