"""
insights_config.py
===================
Configuration for the Business Insights module only. Deliberately
separate from config.py, journey_config.py — this module can be
deleted without affecting PageSpeed monitoring, Customer Journey
monitoring, or the Settings tab.
"""

from __future__ import annotations

import config

BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR
DASHBOARD_DATA_DIR = config.DASHBOARD_DATA_DIR

DAILY_HISTORY_FILE = DATA_DIR / "business_daily_history.json"
INSIGHTS_DASHBOARD_FILE = DASHBOARD_DATA_DIR / "insights.json"

MAX_DAILY_HISTORY_KEPT = 90  # ~3 months of daily snapshots
WEEKLY_TREND_DAYS = 7

# --- Business Health Score weights (must sum to 1.0) -----------------------
# Performance: average PageSpeed score across all pages (0-100 already).
# Journey: customer journey success % over the last 30 runs.
# Alerts: inverse of how many pages are currently critical/warning.
# Availability: whether the last monitoring runs completed cleanly.
# If a component has no data yet (e.g. Journey monitoring just started),
# its weight is redistributed proportionally across the remaining
# components rather than counted as zero — see insights_data.py.
SCORE_WEIGHTS = {
    "performance": 0.40,
    "journey": 0.30,
    "alerts": 0.20,
    "availability": 0.10,
}

SCORE_BANDS = [
    (80, "green", "Good"),
    (60, "yellow", "Fair"),
    (40, "yellow", "Needs Attention"),
    (0, "red", "Critical"),
]


def band_for_score(score) -> tuple[str, str]:
    if score is None:
        return "grey", "No Data"
    for threshold, color, label in SCORE_BANDS:
        if score >= threshold:
            return color, label
    return "red", "Critical"
