"""
config.py
=========
Single source of truth for configuration. Everything environment- or
secret-specific comes from `.env` (never hardcoded) via python-dotenv.
Everything page-specific (the URL list) is defined here, in one place,
so adding a page is a one-line change and nothing else in the project
needs to know about it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# --- Paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"
DASHBOARD_DIR = BASE_DIR / "dashboard"
DASHBOARD_DATA_DIR = DASHBOARD_DIR / "data"

for _dir in (DATA_DIR, LOGS_DIR, REPORTS_DIR, DASHBOARD_DATA_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(
            f"Missing required environment variable '{key}'. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


# --- Timezone ----------------------------------------------------------------
# Every timestamp the project produces (Sheets rows, dashboard JSON, email
# reports, log files) is stamped in this timezone — never the host
# machine's own local time (which is UTC on a GitHub Actions runner but
# could be anything locally). See utils.now_ist() / now_iso() / etc.,
# which are the only functions that should ever be used to get "now".
TIMEZONE_NAME = _env("TIMEZONE", "Asia/Kolkata")
TIMEZONE = ZoneInfo(TIMEZONE_NAME)


# --- Google PageSpeed Insights ----------------------------------------------
GOOGLE_PAGESPEED_API_KEY = _env("GOOGLE_PAGESPEED_API_KEY", required=True)
PAGESPEED_API_BASE = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PAGESPEED_STRATEGY = _env("PAGESPEED_STRATEGY", "mobile")  # mobile | desktop

# Networking / retry behaviour
REQUEST_TIMEOUT_SECONDS = int(_env("REQUEST_TIMEOUT_SECONDS", "30"))
API_MAX_RETRIES = int(_env("API_MAX_RETRIES", "3"))
API_RETRY_BASE_DELAY_SECONDS = float(_env("API_RETRY_BASE_DELAY_SECONDS", "3"))
RATE_LIMIT_WAIT_SECONDS = float(_env("RATE_LIMIT_WAIT_SECONDS", "30"))

# Concurrency — no more Apps Script 6-minute wall. PageSpeed Insights'
# default free-tier quota is 25,000 requests/day and 400 requests/100
# seconds per user — MAX_WORKERS controls how many pages run in parallel,
# so tune it down if you're hitting per-second rate limits (429s).
MAX_WORKERS = int(_env("MAX_WORKERS", "4"))

# --- Google Sheets -----------------------------------------------------------
GOOGLE_SHEET_ID = _env("GOOGLE_SHEET_ID", required=True)
# Either a path to a service-account JSON key file...
GOOGLE_SERVICE_ACCOUNT_FILE = _env("GOOGLE_SERVICE_ACCOUNT_FILE", "")
# ...or the JSON contents themselves (used in CI, where a secret holds the
# whole key rather than a file path). google_sheet.py tries the file first,
# then falls back to this.
GOOGLE_SERVICE_ACCOUNT_JSON = _env("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# --- Email ---------------------------------------------------------------
SMTP_HOST = _env("SMTP_HOST", "")
smtp_port = _env("SMTP_PORT", "").strip()
SMTP_PORT = int(smtp_port) if smtp_port else 587
SMTP_USER = _env("SMTP_USER", "")
SMTP_PASSWORD = _env("SMTP_PASSWORD", "")
EMAIL_FROM = _env("EMAIL_FROM", SMTP_USER)
EMAIL_TO = [addr.strip() for addr in _env("EMAIL_TO", "").split(",") if addr.strip()]
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and EMAIL_TO)

# --- Traffic-light thresholds (3-tier: green / amber / red) ----------------
# Replaces the old single ALERT_SCORE_THRESHOLD (80) that made every page
# show red, since GoodMonk's real scores currently run 26-50. Thresholds
# below are set against our actual target (60), per the July 2026 manager
# review. Used by dashboard_data.py (page + KPI colors) and email_report.py
# (email summary colors). "Amber" is called "yellow" internally to match
# the existing status-color-yellow CSS class — same tier, same meaning.
SCORE_GREEN_MIN = float(_env("SCORE_GREEN_MIN", "60"))       # >=60 green
SCORE_AMBER_MIN = float(_env("SCORE_AMBER_MIN", "40"))       # 40-59 amber, <40 red

LCP_GREEN_MAX = float(_env("LCP_GREEN_MAX", "2.5"))          # <2.5s green
LCP_AMBER_MAX = float(_env("LCP_AMBER_MAX", "4.0"))          # 2.5-4s amber, >4s red

CLS_GREEN_MAX = float(_env("CLS_GREEN_MAX", "0.1"))          # <0.1 green
CLS_AMBER_MAX = float(_env("CLS_AMBER_MAX", "0.25"))         # 0.1-0.25 amber, >0.25 red

TTFB_GREEN_MAX = float(_env("TTFB_GREEN_MAX", "0.8"))        # <0.8s green
TTFB_AMBER_MAX = float(_env("TTFB_AMBER_MAX", "1.8"))        # 0.8-1.8s amber, >1.8s red

TBT_GREEN_MAX_MS = float(_env("TBT_GREEN_MAX_MS", "200"))    # <200ms green
TBT_AMBER_MAX_MS = float(_env("TBT_AMBER_MAX_MS", "600"))    # 200-600ms amber, >600ms red

# --- Benchmark reference lines drawn on the dashboard trend charts ---------
# (dashboard/js/app.js — static JS, so these values are mirrored there as
# constants; keep both in sync if you change them here.)
BENCHMARK_SCORE_TARGET = SCORE_GREEN_MIN       # "Our Target" line
BENCHMARK_SCORE_GOOGLE_GOOD = 90.0             # "Google Good" line
BENCHMARK_LCP_GOOD = LCP_GREEN_MAX
BENCHMARK_LCP_POOR = LCP_AMBER_MAX
BENCHMARK_SPEED_INDEX_GOOD = 3.4
BENCHMARK_SPEED_INDEX_POOR = 5.8


@dataclass(frozen=True)
class Page:
    """One monitored page: a URL and the label it's tracked under."""
    name: str
    url: str
    sheet_name: str


# --- Pages to monitor --------------------------------------------------------
# Add a new page by adding one Page(...) entry — nothing else in the
# project needs to change. Unlimited pages supported; concurrency is
# controlled by MAX_WORKERS above.
PAGES: list[Page] = [
    Page("Homepage", "https://www.goodmonk.in/", "Homepage"),
    Page("Shop All", "https://www.goodmonk.in/collections/all", "Shop_All"),
    Page("FNM", "https://www.goodmonk.in/products/good-monk", "FNM"),
    Page("H50+", "https://www.goodmonk.in/products/good-monk-50-nutrition-mix", "H50+"),
    Page("Fiber Fix", "https://www.goodmonk.in/products/fiber-fix", "FF"),
    Page("Berries", "https://www.goodmonk.in/products/instant-fruit-drink-mix-mixed-berries", "Berries"),
    Page("Orange", "https://www.goodmonk.in/products/instant-fruit-drink-mix-orange", "Orange"),
    Page("Pineapple", "https://www.goodmonk.in/products/instant-fruit-drink-mix-pineapple", "Pineapple"),
    Page("Mango", "https://www.goodmonk.in/products/instant-fruit-drink-mix-natural-mango-powder-50-less-sugar-with-8-vitamins-minerals", "Mango"),
    Page("Assorted", "https://www.goodmonk.in/products/instant-fruit-drink-mix-assorted", "Assorted"),
    Page("Milk Mix Strawberry", "https://www.goodmonk.in/products/good-monk-superhero-milk-mix-strawberry", "MM_Strawberry"),
    Page("Milk Mix Vanilla", "https://www.goodmonk.in/products/good-monk-superhero-milk-mix-vanilla", "MM_Vanilla"),
    Page("Milk Mix Chocolate", "https://www.goodmonk.in/products/good-monk-superhero-milk-mix", "MM_Chocolate"),
    Page("Slimbiotics", "https://www.goodmonk.in/products/good-monk-slimbiotics", "Slimbiotics"),
    Page("Weight Management", "https://www.goodmonk.in/products/good-monk-weight-management-program", "Weight Management"),
    Page("Plant Protein Roti", "https://www.goodmonk.in/products/plant-protein-for-rotis", "Plant Protein Roti"),
]

# --- Priority vs secondary tiers (API quota reduction) ----------------------
# Derived from PAGES above (not a separate list) so there's still exactly
# one place a page is defined.
# Priority: the 6 commercial pages from the manager review, tracked hourly.
# Secondary: everything else, tracked once daily at 2 AM IST — see
# scheduler.py / .github/workflows/monitor.yml.
_PRIORITY_PAGE_NAMES = {
    "Homepage", "Shop All", "H50+", "FNM", "Plant Protein Roti", "Fiber Fix",
}
PAGES_PRIORITY: list[Page] = [p for p in PAGES if p.name in _PRIORITY_PAGE_NAMES]
PAGES_SECONDARY: list[Page] = [p for p in PAGES if p.name not in _PRIORITY_PAGE_NAMES]

# Sheet column headers, in write order. Columns A-L are unchanged from the
# original GTmetrix-based schema so existing history keeps working with
# zero changes. Note the semantic remap now that data comes from PageSpeed
# Insights: "Onload" holds First Contentful Paint (FCP), and "Fully Loaded"
# holds Speed Index — see pagespeed.py's module docstring for the full
# field mapping. Column M ("Top Opportunities") is new: a JSON-encoded
# string of the top Lighthouse diagnostic opportunities for that run (see
# pagespeed.py extract_metrics / google_sheet.append_result) — appended,
# not inserted, so existing columns A-L keep their positions.
HISTORY_HEADERS = [
    "Date", "Time", "Performance Score", "Grade", "LCP",
    "Onload", "Fully Loaded", "TTFB", "CLS", "TBT", "Report URL", "Status",
    "Top Opportunities",
]
