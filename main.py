"""
main.py
=======
Entry point. Run with:

    python main.py                # normal run — resumes an interrupted run if one exists
    python main.py --no-resume    # force a fresh run of every page
    python main.py --workers 8    # override concurrency for this run

This is what the GitHub Actions workflow calls. It:
  1. Runs the PageSpeed Insights batch (scheduler.run_batch)
  2. Rebuilds the dashboard JSON from fresh Sheets data (dashboard_data.build_all)
  3. Sends the summary email (email_report.send_report)
  4. Clears run state on a fully successful run, so the next run starts clean

Timezone: next_run is computed in IST via utils.now_ist() — see that
module's docstring for why plain datetime.now() isn't used.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

import dashboard_data
import email_report
import scheduler
from logger import get_logger, setup_logging
from utils import now_ist

log = get_logger("main")


def main() -> int:
    parser = argparse.ArgumentParser(description="GoodMonk Performance Command Center — run everything.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore saved run state; test every page.")
    parser.add_argument("--workers", type=int, default=None, help="Override MAX_WORKERS for this run.")
    parser.add_argument("--skip-email", action="store_true", help="Skip sending the summary email.")
    tier_group = parser.add_mutually_exclusive_group()
    tier_group.add_argument("--priority", action="store_true",
                             help="Run only the 6 priority pages (Homepage, Shop All, H50+, FNM, "
                                  "Plant Protein Roti, Fiber Fix). Meant for the hourly schedule.")
    tier_group.add_argument("--secondary", action="store_true",
                             help="Run only the secondary (non-priority) pages. Meant for the "
                                  "once-daily 2 AM IST schedule.")
    args = parser.parse_args()

    tier = "priority" if args.priority else "secondary" if args.secondary else "all"

    setup_logging()
    log.info("=== GoodMonk Performance Command Center run starting (tier=%s) ===", tier)

    results = scheduler.run_batch(resume=not args.no_resume, workers=args.workers, tier=tier)

    if not results:
        log.info("No results produced (nothing to run, or everything was already completed). Exiting.")
        return 0

    failed = sum(1 for r in results if not r.success)
    status = "completed" if failed == 0 else "completed_with_failures"

    # Next run: priority/all pages run every hour (cron "0 * * * *"), so
    # next_scheduled_run is simply the next top-of-the-hour boundary in
    # IST. Secondary pages instead run once daily at 2 AM IST — see
    # .github/workflows/monitor.yml.
    now = now_ist()
    if tier == "secondary":
        next_run = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
    else:
        next_run = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))

    try:
        dashboard_data.build_all(last_run_status=status, next_run_iso=next_run.isoformat())
    except Exception as e:  # noqa: BLE001 — dashboard regeneration must never fail the whole run
        log.error("Failed to rebuild dashboard data: %s", e)

    if not args.skip_email:
        email_report.send_report(results)

    if failed == 0:
        scheduler.clear_run_state()

    log.info("=== Run finished. %d/%d pages succeeded. ===", len(results) - failed, len(results))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
