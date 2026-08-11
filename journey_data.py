"""
journey_data.py
================
Reads data/journey_runs.json (the compact run log journey.py appends
to) and writes dashboard/data/journey.json — the one file the
Customer Journey dashboard tab reads. Mirrors the shape of
dashboard_data.py / settings_data.py but is fully independent: it
never reads or writes summary.json, pages.json, trends.json, or
history.json.
"""

from __future__ import annotations

from datetime import datetime

import journey_config as jc
from logger import get_logger
from utils import now_iso, read_json, write_json

log = get_logger("journey_data")


def _today_str() -> str:
    return datetime.fromisoformat(now_iso()).strftime("%Y-%m-%d")


def build_journey_dashboard() -> None:
    runs = read_json(jc.JOURNEY_RUNS_FILE, default=[])

    today = _today_str()
    today_runs = [r for r in runs if str(r.get("started_at", "")).startswith(today)]
    today_pass = sum(1 for r in today_runs if r.get("overall_status") == "pass")
    today_fail = len(today_runs) - today_pass

    last_30 = runs[-30:]
    last_30_pass = sum(1 for r in last_30 if r.get("overall_status") == "pass")
    success_pct = round(100 * last_30_pass / len(last_30), 1) if last_30 else None
    failure_pct = round(100 - success_pct, 1) if success_pct is not None else None

    durations = [r.get("duration_seconds") for r in last_30 if r.get("duration_seconds") is not None]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else None

    latest = runs[-1] if runs else None
    latest_failed = next((r for r in reversed(runs) if r.get("overall_status") == "fail" and r.get("attempt") == 2), None)

    if not runs:
        overall_health = "grey"
    elif latest and latest.get("overall_status") == "fail" and latest.get("attempt") == 2:
        overall_health = "red"
    elif today_fail > 0:
        overall_health = "yellow"
    else:
        overall_health = "green"

    dashboard = {
        "generated_at": now_iso(),
        "overall_health": overall_health,
        "today_runs": len(today_runs),
        "today_pass": today_pass,
        "today_fail": today_fail,
        "success_pct_last_30": success_pct,
        "failure_pct_last_30": failure_pct,
        "avg_journey_seconds": avg_duration,
        "latest_run": latest,
        "latest_confirmed_failure": (
            {
                **latest_failed,
                "business_impact": jc.BUSINESS_IMPACT.get(latest_failed.get("failed_step"), ""),
                "suggested_cause": jc.SUGGESTED_CAUSE.get(latest_failed.get("failed_step"), ""),
            }
            if latest_failed else None
        ),
        "timeline": runs[-30:][::-1],  # most recent first, capped — powers the dashboard timeline view
        "step_names": jc.STEP_NAMES,
    }

    write_json(jc.JOURNEY_DASHBOARD_FILE, dashboard)
    log.info("journey.json written (%d total runs, %d today).", len(runs), len(today_runs))


if __name__ == "__main__":
    build_journey_dashboard()
