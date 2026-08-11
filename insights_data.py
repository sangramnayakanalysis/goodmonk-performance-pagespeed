"""
insights_data.py
=================
Executive Business Intelligence module. Reads the dashboard JSON files
three OTHER modules already produce — summary.json / pages.json
(dashboard_data.py, untouched), journey.json (journey_data.py,
untouched) — and combines them into one Business Health Score plus the
structured data the "Business Insights" tab needs.

Design choice — no duplicate translation logic: this file computes
NUMBERS and RAW Lighthouse issue titles only. It deliberately does NOT
re-implement the Lighthouse-title -> plain-English dictionary that
already lives in dashboard/js/business.js — that translation happens
client-side in insights.js by calling business.js's explainOne(), so
there is exactly one place that dictionary is maintained.

Design choice — no live AI model call: there is no LLM API wired into
this project's infrastructure. "Today's Website Status" is a
deterministic, rule-based narrative built from real numbers below —
NOT a live generative AI call. Framed honestly as "automated summary"
in the UI, not "AI-generated", to avoid overstating what this does.

Called additively at the end of BOTH main.py (after the PageSpeed run)
and journey.py (after the Customer Journey run) — see the small
try/except-wrapped call each of those files makes. Either call alone
is enough to refresh insights.json; calling it from both just keeps it
current regardless of which pipeline ran most recently.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import insights_config as ic
from logger import get_logger
from utils import now_iso, read_json, write_json

log = get_logger("insights_data")


def _today_str() -> str:
    return datetime.fromisoformat(now_iso()).strftime("%Y-%m-%d")


def _yesterday_str() -> str:
    return (datetime.fromisoformat(now_iso()) - timedelta(days=1)).strftime("%Y-%m-%d")


# --- Score components (each 0-100, or None if no data yet) -----------------

def _performance_component(summary: dict | None) -> float | None:
    if not summary:
        return None
    return summary.get("average_score")


def _journey_component(journey: dict | None) -> float | None:
    if not journey:
        return None
    return journey.get("success_pct_last_30")


def _alerts_component(summary: dict | None) -> float | None:
    if not summary:
        return None
    total = summary.get("total_urls") or 0
    if not total:
        return None
    critical = summary.get("critical_count", 0)
    warning = summary.get("warning_count", 0)
    penalty = (critical * 15) + (warning * 5)
    return max(0.0, 100.0 - penalty)


def _availability_component(summary: dict | None, journey: dict | None) -> float | None:
    if not summary and not journey:
        return None
    score = 100.0
    status = (summary or {}).get("last_run_status")
    if status == "completed_with_failures":
        score -= 25
    elif status not in ("completed", "completed_no_new_pages", None):
        score -= 10
    if (journey or {}).get("overall_health") == "red":
        score -= 30
    elif (journey or {}).get("overall_health") == "yellow":
        score -= 10
    return max(0.0, score)


def _weighted_score(components: dict[str, float | None]) -> float | None:
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return None
    total_weight = sum(ic.SCORE_WEIGHTS[k] for k in available)
    if total_weight == 0:
        return None
    return round(sum(v * ic.SCORE_WEIGHTS[k] for k, v in available.items()) / total_weight, 1)


# --- Top lists (raw data only — no English translation here) --------------

def _top_slow_pages(pages: list[dict], limit: int = 5) -> list[dict]:
    scored = [p for p in pages if p.get("latest") and p["latest"].get("Performance Score") is not None]
    scored.sort(key=lambda p: p["latest"]["Performance Score"])
    out = []
    for p in scored[:limit]:
        top_issue = (p.get("top_opportunities") or [{}])[0]
        out.append({
            "name": p["name"],
            "score": p["latest"]["Performance Score"],
            "status_color": p.get("status_color"),
            "top_issue_title": top_issue.get("title"),
        })
    return out


def _top_failed_journeys(journey: dict | None, limit: int = 5) -> list[dict]:
    if not journey:
        return []
    timeline = journey.get("timeline") or []
    failures = [r for r in timeline if r.get("overall_status") == "fail" and r.get("attempt") == 2]
    return [
        {"run_id": r.get("run_id"), "finished_at": r.get("finished_at"), "failed_step": r.get("failed_step")}
        for r in failures[:limit]
    ]


def _most_common_issue(pages: list[dict]) -> dict | None:
    counts: dict[str, int] = {}
    for p in pages:
        for opp in (p.get("top_opportunities") or [])[:1]:  # each page's #1 issue only
            title = opp.get("title")
            if title:
                counts[title] = counts.get(title, 0) + 1
    if not counts:
        return None
    title, freq = max(counts.items(), key=lambda kv: kv[1])
    return {"title": title, "page_count": freq}


# --- Daily history (compare-with-yesterday support) ------------------------

def _load_daily_history() -> list[dict]:
    return read_json(ic.DAILY_HISTORY_FILE, default=[])


def _save_today_snapshot(history: list[dict], today_entry: dict) -> list[dict]:
    history = [h for h in history if h.get("date") != today_entry["date"]]  # replace today's entry if it exists
    history.append(today_entry)
    history.sort(key=lambda h: h["date"])
    history = history[-ic.MAX_DAILY_HISTORY_KEPT:]
    write_json(ic.DAILY_HISTORY_FILE, history)
    return history


def _pages_slower_than_yesterday(pages: list[dict], yesterday_snapshot: dict | None) -> int:
    if not yesterday_snapshot:
        return 0
    yesterday_scores = yesterday_snapshot.get("page_scores", {})
    count = 0
    for p in pages:
        latest = p.get("latest")
        if not latest or latest.get("Performance Score") is None:
            continue
        prev = yesterday_scores.get(p["name"])
        if prev is not None and latest["Performance Score"] < prev:
            count += 1
    return count


def build_insights() -> None:
    summary = read_json(ic.DASHBOARD_DATA_DIR / "summary.json", default=None)
    pages = read_json(ic.DASHBOARD_DATA_DIR / "pages.json", default=[])
    journey = read_json(ic.DASHBOARD_DATA_DIR / "journey.json", default=None)

    components = {
        "performance": _performance_component(summary),
        "journey": _journey_component(journey),
        "alerts": _alerts_component(summary),
        "availability": _availability_component(summary, journey),
    }
    business_score = _weighted_score(components)
    score_color, score_label = ic.band_for_score(business_score)

    history = _load_daily_history()
    yesterday_snapshot = next((h for h in history if h.get("date") == _yesterday_str()), None)
    pages_slower = _pages_slower_than_yesterday(pages, yesterday_snapshot)

    today_entry = {
        "date": _today_str(),
        "business_score": business_score,
        "average_score": (summary or {}).get("average_score"),
        "critical_count": (summary or {}).get("critical_count"),
        "journey_success_pct": (journey or {}).get("success_pct_last_30"),
        "checkout_failures_today": (journey or {}).get("today_fail"),
        "page_scores": {
            p["name"]: p["latest"]["Performance Score"]
            for p in pages if p.get("latest") and p["latest"].get("Performance Score") is not None
        },
    }
    history = _save_today_snapshot(history, today_entry)

    overall_health_label = ic.band_for_score((summary or {}).get("average_score"))[1] if summary else "No Data"

    insights = {
        "generated_at": now_iso(),
        "business_score": business_score,
        "business_score_color": score_color,
        "business_score_label": score_label,
        "components": {k: (round(v, 1) if v is not None else None) for k, v in components.items()},
        "overall_website_health": overall_health_label,
        "customer_journey_health": (journey or {}).get("overall_health", "grey"),
        "critical_issues_count": (summary or {}).get("critical_count", 0),
        "checkout_failures_today": (journey or {}).get("today_fail", 0),
        "pages_slower_than_yesterday": pages_slower,
        "most_common_issue": _most_common_issue(pages),
        "top_slow_pages": _top_slow_pages(pages),
        "top_failed_journeys": _top_failed_journeys(journey),
        "daily_history": history[-ic.MAX_DAILY_HISTORY_KEPT:],
        "weekly_trend": history[-ic.WEEKLY_TREND_DAYS:],
    }

    write_json(ic.INSIGHTS_DASHBOARD_FILE, insights)
    log.info("insights.json written (business_score=%s, %d days of history).", business_score, len(history))


if __name__ == "__main__":
    build_insights()
