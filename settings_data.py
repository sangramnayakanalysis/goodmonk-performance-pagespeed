"""
settings_data.py
=================
Plugin-style companion to dashboard_data.py — NOT a modification of it.

Writes exactly one new, additive file: dashboard/data/settings.json.
This lets the new "Settings" dashboard tab show live config values
(thresholds, monitored pages, schedule) without dashboard_data.py,
summary.json, pages.json, trends.json, or history.json changing shape
in any way. If this module is ever deleted, nothing else in the
project breaks — the existing dashboard has no dependency on it.

Called additively from main.py, right after dashboard_data.build_all().
"""

from __future__ import annotations

import config
from logger import get_logger
from utils import now_iso, write_json

log = get_logger("settings_data")


def build_settings() -> None:
    settings = {
        "generated_at": now_iso(),
        "monitoring": {
            "total_pages": len(config.PAGES),
            "priority_pages": len(config.PAGES_PRIORITY),
            "secondary_pages": len(config.PAGES_SECONDARY),
            "strategy": config.PAGESPEED_STRATEGY,
            "priority_schedule": "Every hour",
            "secondary_schedule": "Once daily (2:00 AM IST)",
            "timezone": config.TIMEZONE_NAME,
        },
        "thresholds": {
            "score": {"green_min": config.SCORE_GREEN_MIN, "amber_min": config.SCORE_AMBER_MIN},
            "lcp_seconds": {"green_max": config.LCP_GREEN_MAX, "amber_max": config.LCP_AMBER_MAX},
            "cls": {"green_max": config.CLS_GREEN_MAX, "amber_max": config.CLS_AMBER_MAX},
            "ttfb_seconds": {"green_max": config.TTFB_GREEN_MAX, "amber_max": config.TTFB_AMBER_MAX},
            "tbt_ms": {"green_max": config.TBT_GREEN_MAX_MS, "amber_max": config.TBT_AMBER_MAX_MS},
        },
        "email_alerts_enabled": config.EMAIL_ENABLED,
        "pages": [
            {"name": p.name, "url": p.url, "tier": "Priority" if p in config.PAGES_PRIORITY else "Secondary"}
            for p in config.PAGES
        ],
    }
    write_json(config.DASHBOARD_DATA_DIR / "settings.json", settings)
    log.info("settings.json written (%d pages).", len(config.PAGES))


if __name__ == "__main__":
    build_settings()
