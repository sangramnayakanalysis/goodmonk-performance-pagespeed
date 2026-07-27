"""
dashboard_data.py
==================
Builds the JSON files the static dashboard (GitHub Pages, no server)
reads. Pulls fresh history from Google Sheets for every configured
page, computes aggregate stats, per-page trends, and diagnostic
opportunities, and writes everything atomically into
dashboard/data/*.json.

Output files:
  summary.json   — KPI strip: totals, averages, best/worst, last run
  pages.json     — one entry per page: latest metrics, per-metric traffic
                    -light tiers, score trend vs last week, top diagnostic
                    opportunities, and overall status color
  trends.json    — { daily|weekly|monthly: { overall: [...], pages: {
                    <page name>: [...] } } } aggregated series for charts
  history.json   — full flattened history (used for search/filter/export)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Optional

import config
import google_sheet
from logger import get_logger
from utils import now_iso, write_json

log = get_logger("dashboard_data")


# --- Traffic-light tiers -----------------------------------------------

def _f(value) -> Optional[float]:
    """Best-effort float() that treats None/'' as missing instead of raising."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_tier(score: Optional[float]) -> str:
    if score is None:
        return "grey"
    if score >= config.SCORE_GREEN_MIN:
        return "green"
    if score >= config.SCORE_AMBER_MIN:
        return "yellow"
    return "red"


def _lower_is_better_tier(value: Optional[float], green_max: float, amber_max: float) -> str:
    """For metrics where smaller is healthier (LCP, CLS, TTFB, TBT)."""
    if value is None:
        return "grey"
    if value < green_max:
        return "green"
    if value <= amber_max:
        return "yellow"
    return "red"


_TIER_ORDER = {"green": 0, "yellow": 1, "red": 2, "grey": 0}


def _status_color(score: Optional[float], lcp: Optional[float]) -> str:
    """Overall page/KPI classification: the worse of the Score tier and the
    LCP tier (a page with a green score but a badly-blown LCP still needs
    attention). None score (no successful run yet) is "grey" (unknown),
    distinct from "red" (critical)."""
    if score is None:
        return "grey"
    score_tier = _score_tier(score)
    lcp_tier = _lower_is_better_tier(lcp, config.LCP_GREEN_MAX, config.LCP_AMBER_MAX) if lcp is not None else "green"
    return max([score_tier, lcp_tier], key=lambda t: _TIER_ORDER[t])


def _metric_tiers(latest: Optional[dict]) -> dict:
    """Per-metric traffic-light tiers for one page's latest run — powers
    the expanded page cards (fix #5)."""
    if not latest:
        return {"score": "grey", "lcp": "grey", "cls": "grey", "ttfb": "grey", "tbt": "grey"}

    score = _f(latest.get("Performance Score"))
    lcp = _f(latest.get("LCP"))
    cls = _f(latest.get("CLS"))
    ttfb = _f(latest.get("TTFB"))
    tbt_seconds = _f(latest.get("TBT"))
    tbt_ms = tbt_seconds * 1000 if tbt_seconds is not None else None

    return {
        "score": _score_tier(score),
        "lcp": _lower_is_better_tier(lcp, config.LCP_GREEN_MAX, config.LCP_AMBER_MAX),
        "cls": _lower_is_better_tier(cls, config.CLS_GREEN_MAX, config.CLS_AMBER_MAX),
        "ttfb": _lower_is_better_tier(ttfb, config.TTFB_GREEN_MAX, config.TTFB_AMBER_MAX),
        "tbt": _lower_is_better_tier(tbt_ms, config.TBT_GREEN_MAX_MS, config.TBT_AMBER_MAX_MS),
    }


# --- Score trend (vs ~last week) ----------------------------------------

def _score_trend(ok_rows: list[dict]) -> Optional[int]:
    """Whole-point delta between the latest score and the score from
    roughly a week earlier (closest run on/before that date, falling back
    to the earliest available run if history is shorter than a week).
    Returns None if there's fewer than 2 successful runs to compare."""
    if len(ok_rows) < 2:
        return None
    try:
        latest = ok_rows[-1]
        latest_date = datetime.strptime(str(latest["Date"]), "%Y-%m-%d")
        target_date = latest_date - timedelta(days=7)

        candidates = [
            r for r in ok_rows[:-1]
            if datetime.strptime(str(r["Date"]), "%Y-%m-%d") <= target_date
        ]
        baseline = candidates[-1] if candidates else ok_rows[0]

        latest_score = _f(latest.get("Performance Score"))
        baseline_score = _f(baseline.get("Performance Score"))
        if latest_score is None or baseline_score is None:
            return None
        return round(latest_score - baseline_score)
    except (ValueError, KeyError):
        return None


# --- Diagnostic opportunities ("why is this page slow") -----------------

def _parse_opportunities(latest: Optional[dict]) -> list[dict]:
    if not latest:
        return []
    raw = latest.get("Top Opportunities")
    if not raw:
        return []
    try:
        opportunities = json.loads(raw)
        return opportunities if isinstance(opportunities, list) else []
    except (TypeError, ValueError):
        return []


# --- Trend series helpers -------------------------------------------------

def _period_key(date_str: str, granularity: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    if granularity == "daily":
        return date_str
    if granularity == "weekly":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return d.strftime("%Y-%m")  # monthly


def _series_from_rows(rows: list[dict], granularity: str) -> list[dict]:
    """Buckets a flat list of OK rows into a sorted period series with
    averaged score/LCP/Speed Index. Shared by the overall (all-pages) and
    per-page trend builders so the aggregation logic only lives once."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        date_str = str(r.get("Date"))
        try:
            key = _period_key(date_str, granularity)
        except ValueError:
            continue
        buckets[key].append(r)

    series = []
    for key in sorted(buckets.keys()):
        bucket_rows = buckets[key]
        s = [v for v in (_f(r.get("Performance Score")) for r in bucket_rows) if v is not None]
        l = [v for v in (_f(r.get("LCP")) for r in bucket_rows) if v is not None]
        f = [v for v in (_f(r.get("Fully Loaded")) for r in bucket_rows) if v is not None]  # Speed Index
        series.append({
            "period": key,
            "avg_score": round(mean(s), 2) if s else None,
            "avg_lcp": round(mean(l), 2) if l else None,
            "avg_fully_loaded": round(mean(f), 2) if f else None,
        })
    return series


def build_all(last_run_status: str = "completed", next_run_iso: str | None = None) -> None:
    all_rows: list[dict] = []
    page_entries: list[dict] = []
    rows_by_page: dict[str, list[dict]] = {}

    for page in config.PAGES:
        try:
            rows = google_sheet.read_history(page.sheet_name)
        except Exception as e:  # noqa: BLE001 — one broken sheet must not blank the whole dashboard
            log.error("Could not read history for %s: %s", page.sheet_name, e)
            rows = []

        for r in rows:
            r["_page_name"] = page.name
            r["_sheet_name"] = page.sheet_name
            r["_url"] = page.url
        all_rows.extend(rows)
        rows_by_page[page.name] = rows

        ok_rows = [r for r in rows if r.get("Status") == "OK" and r.get("Performance Score") not in (None, "")]
        latest = ok_rows[-1] if ok_rows else None

        score = _f(latest["Performance Score"]) if latest else None
        lcp = _f(latest.get("LCP")) if latest else None

        page_entries.append({
            "name": page.name,
            "sheet_name": page.sheet_name,
            "url": page.url,
            "latest": latest,
            "status_color": _status_color(score, lcp),
            "metric_tiers": _metric_tiers(latest),
            "score_trend": _score_trend(ok_rows),
            "top_opportunities": _parse_opportunities(latest),
            "total_runs": len(rows),
            "failed_runs": sum(1 for r in rows if r.get("Status") == "Failed"),
        })

    # --- summary.json --------------------------------------------------
    ok_rows_all = [r for r in all_rows if r.get("Status") == "OK" and r.get("Performance Score") not in (None, "")]
    scores = [float(r["Performance Score"]) for r in ok_rows_all]
    best = max(page_entries, key=lambda p: (p["latest"] or {}).get("Performance Score", -1) if p["latest"] else -1, default=None)
    worst = min(
        (p for p in page_entries if p["latest"]),
        key=lambda p: p["latest"].get("Performance Score", 101),
        default=None,
    )

    # generated_at and next_scheduled_run are both IST timestamps (with an
    # explicit +05:30 offset baked into the ISO string) — generated_at via
    # utils.now_iso(), next_scheduled_run passed in from main.py's
    # now_ist()-based calculation. The dashboard JS renders both explicitly
    # in Asia/Kolkata regardless of the viewer's own browser timezone.
    summary = {
        "generated_at": now_iso(),
        "last_run_status": last_run_status,
        "total_urls": len(config.PAGES),
        "average_score": round(mean(scores), 2) if scores else None,
        "best_page": best["name"] if best else None,
        "worst_page": worst["name"] if worst else None,
        "healthy_count": sum(1 for p in page_entries if p["status_color"] == "green"),
        "warning_count": sum(1 for p in page_entries if p["status_color"] == "yellow"),
        "critical_count": sum(1 for p in page_entries if p["status_color"] == "red"),
        "no_data_count": sum(1 for p in page_entries if p["status_color"] == "grey"),
    }
    summary["next_scheduled_run"] = next_run_iso
    write_json(config.DASHBOARD_DATA_DIR / "summary.json", summary)

    # --- pages.json ------------------------------------------------------
    write_json(config.DASHBOARD_DATA_DIR / "pages.json", page_entries)

    # --- trends.json -------------------------------------------------
    # Per-page series so trend charts can show one page at a time (fix #3)
    # instead of a meaningless 16-page average. "overall" is kept as the
    # default/all-pages view.
    trends: dict[str, dict] = {}
    for granularity in ("daily", "weekly", "monthly"):
        trends[granularity] = {
            "overall": _series_from_rows(ok_rows_all, granularity),
            "pages": {
                name: _series_from_rows(
                    [r for r in rows if r.get("Status") == "OK" and r.get("Performance Score") not in (None, "")],
                    granularity,
                )
                for name, rows in rows_by_page.items()
            },
        }
    write_json(config.DASHBOARD_DATA_DIR / "trends.json", trends)

    # --- history.json (flattened, for search/filter/export) ------------
    write_json(config.DASHBOARD_DATA_DIR / "history.json", all_rows)

    log.info("Dashboard data written: %d page(s), %d total history row(s).", len(page_entries), len(all_rows))


if __name__ == "__main__":
    build_all()
