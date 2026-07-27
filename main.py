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
  4. Clears run state so the next scheduled run starts clean

Timezone: next_run is computed in IST via utils.now_ist() — see that
module's docstring for why plain datetime.now() isn't used.

IMPORTANT — resume-state lifetime (bug fixed here): run_state.json exists
ONLY to survive a mid-batch crash (process killed partway through a
batch) — it is NOT meant to make a later scheduled run skip pages that
succeeded in an *earlier* run. Previously, clear_run_state() only ran
when every page in that batch succeeded (`failed == 0`), and the whole
dashboard-rebuild/email/clear block was skipped entirely whenever
run_batch() returned no results (e.g. every page in the requested tier
was already marked "completed" from a past run). In practice this meant:
one page timing out on an old, since-removed run (with `failed > 0`)
left its sibling pages permanently marked "completed"; once the
priority/secondary tiers were introduced, ALL 6 priority pages already
matched that stale "completed" set, so every hourly run computed an
empty page list, returned early, and skipped dashboard_data.build_all()
+ clear_run_state() — while still exiting 0 (success). GitHub Actions
showed dozens of green runs; the dashboard never moved. Reaching the end
of main() at all (this function returning normally) means the process
did NOT crash, so run_state is now always cleared here regardless of
whether this batch had 0, some, or all pages fail — and the dashboard is
always rebuilt from whatever is currently in Sheets, even on a batch
with nothing new to test, so the dashboard can never go stale just
because a given hour happened to have nothing left to run.
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

    failed = sum(1 for r in results if not r.success)
    if not results:
        status = "completed_no_new_pages"
        log.info("No new pages to test this run (nothing pending, or everything in this tier was "
                 "already completed earlier) — rebuilding the dashboard from current Sheets data anyway.")
    else:
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

    # Rebuild the dashboard unconditionally — even a "nothing new to test"
    # run still reflects whatever is currently in Sheets, so the dashboard
    # can never silently go stale just because this particular invocation
    # had no new pages to test.
    try:
        dashboard_data.build_all(last_run_status=status, next_run_iso=next_run.isoformat())
    except Exception as e:  # noqa: BLE001 — dashboard regeneration must never fail the whole run
        log.error("Failed to rebuild dashboard data: %s", e)

    if results and not args.skip_email:
        email_report.send_report(results)

    # Reaching this point means the process ran to a normal, non-crashed
    # completion (0, some, or all pages may have failed to fetch — that's
    # recorded in Sheets/dashboard already) — so there is nothing left to
    # "resume." Always clear, so the next scheduled run starts clean
    # instead of silently inheriting a stale completed-pages set forever.
    scheduler.clear_run_state()

    log.info("=== Run finished. %d/%d pages succeeded. ===", len(results) - failed, len(results))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
