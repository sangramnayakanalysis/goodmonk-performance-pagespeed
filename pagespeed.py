"""
pagespeed.py
============
Google PageSpeed Insights API v5 client — replaces gtmetrix.py.

Unlike GTmetrix (start test -> poll -> fetch report), PageSpeed Insights
is a single synchronous call that runs a Lighthouse audit and returns
the full result directly, so there's no polling step here.

Field mapping onto the existing Metrics/Sheets shape (unchanged Sheets
headers — see config.HISTORY_HEADERS — so google_sheet.py, dashboard_data.py,
and the dashboard's app.js all keep working with zero changes, since they
key off the Sheet's header text, not these Python attribute names):

  Metrics.performance_score  <- lighthouseResult.categories.performance.score * 100
  Metrics.grade              <- computed from performance_score (see grade_for_score)
  Metrics.lcp                <- audit "largest-contentful-paint"     (seconds)
  Metrics.onload              <- audit "first-contentful-paint" (FCP) (seconds)
                                  [renamed meaning: GTmetrix's onload_time -> now FCP,
                                   per the "Onload/FCP" column requirement]
  Metrics.fully_loaded        <- audit "speed-index"                  (seconds)
                                  [renamed meaning: GTmetrix's fully_loaded_time -> now
                                   Speed Index, per the "Fully Loaded/Speed Index" column]
  Metrics.ttfb                <- audit "server-response-time", if present (seconds)
  Metrics.cls                 <- audit "cumulative-layout-shift"      (unitless)
  Metrics.tbt                 <- audit "total-blocking-time"          (seconds)
  Metrics.report_url          <- constructed pagespeed.web.dev deep link
  Metrics.inp                 <- field data (CrUX) INP, if the URL has enough real-user
                                  traffic for Google to report it — not written to Sheets
                                  (no INP column in the preserved schema), but logged and
                                  available on the Metrics object for the email report /
                                  future dashboard use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

import requests

import config
from logger import get_api_logger, get_logger
from utils import RateLimitedError, retry_with_backoff

log = get_logger("pagespeed")
api_log = get_api_logger()


@dataclass
class Metrics:
    performance_score: Optional[float] = None
    grade: str = "N/A"
    lcp: Optional[float] = None            # seconds
    onload: Optional[float] = None         # seconds — First Contentful Paint (FCP)
    fully_loaded: Optional[float] = None   # seconds — Speed Index
    ttfb: Optional[float] = None           # seconds, if available
    cls: Optional[float] = None
    tbt: Optional[float] = None            # seconds
    inp: Optional[float] = None            # seconds, field data — not persisted to Sheets
    report_url: Optional[str] = None
    status: str = "OK"                     # "OK" | "Error"
    error_message: str = ""


@dataclass
class PageResult:
    page_name: str
    sheet_name: str
    url: str
    metrics: Metrics = field(default_factory=Metrics)
    success: bool = False
    error_message: str = ""


class PageSpeedError(Exception):
    """Raised for PageSpeed Insights failures for one page (invalid URL,
    malformed response, non-transient API error, etc.)."""


def grade_for_score(score: Optional[float]) -> str:
    """Maps a 0-100 performance score to a letter grade, per spec:
    90-100=A, 80-89=B, 70-79=C, 50-69=D, below 50=F."""
    if score is None:
        return "N/A"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def _build_report_url(url: str) -> str:
    """PageSpeed Insights doesn't persist a fetchable historical report the
    way GTmetrix does — the closest equivalent is a deep link into the
    public pagespeed.web.dev UI pre-filled with this URL and strategy,
    which re-runs (rather than replays) the audit when opened."""
    return f"https://pagespeed.web.dev/report?url={quote(url, safe='')}&form_factor={config.PAGESPEED_STRATEGY}"


def _raise_for_response(resp: requests.Response, context: str) -> None:
    if resp.status_code == 429:
        raise RateLimitedError(f"{context}: rate limited (429)")

    if resp.status_code == 403:
        # Google APIs report both per-day quota exhaustion and per-key
        # restriction problems as 403 — treat quota-shaped ones as
        # rate-limited (worth a longer cooldown + retry), everything else
        # as a terminal error. RESOURCE_EXHAUSTED is the standard Google
        # API status string for quota exhaustion; older PageSpeed/Sheets
        # style APIs sometimes instead use reason strings like
        # dailyLimitExceeded / userRateLimitExceeded / rateLimitExceeded.
        try:
            error_body = resp.json().get("error", {})
        except ValueError:
            error_body = {}
        reason = str(error_body.get("status", "")).upper()
        reasons_list = " ".join(
            str(e.get("reason", "")) for e in error_body.get("errors", [])
        ).upper()
        quota_signal = reason + " " + reasons_list
        if any(s in quota_signal for s in ("QUOTA", "RATE", "RESOURCE_EXHAUSTED", "LIMIT")):
            raise RateLimitedError(f"{context}: quota exceeded (403 {reason or reasons_list})")
        raise PageSpeedError(f"{context}: HTTP 403 {reason}: {resp.text[:300]}")

    if resp.status_code >= 500:
        raise RuntimeError(f"{context}: server error {resp.status_code}: {resp.text[:300]}")

    if not resp.ok:
        # Non-retryable-in-spirit client error (invalid URL, bad request,
        # malformed key, etc.) — still passes through the same retry
        # wrapper as everything else, matching this project's existing
        # "retry every failure up to API_MAX_RETRIES" pattern.
        message = resp.text[:300]
        try:
            message = resp.json().get("error", {}).get("message", message)
        except ValueError:
            pass
        raise PageSpeedError(f"{context}: HTTP {resp.status_code}: {message}")


@retry_with_backoff(
    max_retries=config.API_MAX_RETRIES,
    base_delay_seconds=config.API_RETRY_BASE_DELAY_SECONDS,
    rate_limit_wait_seconds=config.RATE_LIMIT_WAIT_SECONDS,
    label="runPagespeed",
)
def _call_pagespeed(url: str) -> dict:
    """Runs one PageSpeed Insights audit and returns the raw JSON response."""
    params = {
        "url": url,
        "key": config.GOOGLE_PAGESPEED_API_KEY,
        "strategy": config.PAGESPEED_STRATEGY,
        "category": "performance",
    }
    try:
        resp = requests.get(
            config.PAGESPEED_API_BASE,
            params=params,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout as e:
        raise PageSpeedError(f"runPagespeed({url}): request timed out after {config.REQUEST_TIMEOUT_SECONDS}s") from e
    except requests.exceptions.ConnectionError as e:
        raise PageSpeedError(f"runPagespeed({url}): connection error: {e}") from e

    api_log.debug("GET %s (strategy=%s) -> %s", url, config.PAGESPEED_STRATEGY, resp.status_code)
    _raise_for_response(resp, f"runPagespeed({url})")

    data = resp.json()
    if "error" in data:
        err = data["error"]
        raise PageSpeedError(f"runPagespeed({url}): Google API error {err.get('code')}: {err.get('message')}")

    return data


def _audit_seconds(audits: dict, audit_id: str) -> Optional[float]:
    audit = audits.get(audit_id)
    if not audit:
        return None
    value = audit.get("numericValue")
    if value is None:
        return None
    return round(value / 1000, 2)


def extract_metrics(data: dict, url: str) -> Metrics:
    lighthouse = data.get("lighthouseResult")
    if not lighthouse:
        return Metrics(status="Error", error_message="Response missing lighthouseResult", report_url=_build_report_url(url))

    try:
        audits = lighthouse.get("audits", {})
        perf_category = lighthouse.get("categories", {}).get("performance", {})
        raw_score = perf_category.get("score")
        score = round(raw_score * 100, 1) if raw_score is not None else None

        cls_raw = audits.get("cumulative-layout-shift", {}).get("numericValue")
        cls = round(cls_raw, 3) if cls_raw is not None else None

        # Field data (real-user CrUX) INP — only present when Google has
        # enough real-user traffic for this URL; genuinely optional.
        inp = None
        loading_experience = data.get("loadingExperience") or data.get("originLoadingExperience") or {}
        inp_metric = loading_experience.get("metrics", {}).get("INTERACTION_TO_NEXT_PAINT")
        if inp_metric and inp_metric.get("percentile") is not None:
            inp = round(inp_metric["percentile"] / 1000, 2)

        metrics = Metrics(
            performance_score=score,
            grade=grade_for_score(score),
            lcp=_audit_seconds(audits, "largest-contentful-paint"),
            onload=_audit_seconds(audits, "first-contentful-paint"),
            fully_loaded=_audit_seconds(audits, "speed-index"),
            ttfb=_audit_seconds(audits, "server-response-time"),
            cls=cls,
            tbt=_audit_seconds(audits, "total-blocking-time"),
            inp=inp,
            report_url=_build_report_url(url),
            status="OK",
        )
    except (KeyError, TypeError, AttributeError) as e:
        return Metrics(status="Error", error_message=f"Malformed PageSpeed response: {e}", report_url=_build_report_url(url))

    return metrics


def run_single_page(page_name: str, sheet_name: str, url: str) -> PageResult:
    """
    Full pipeline for one page: call PSI -> extract metrics. Never raises —
    always returns a PageResult, with success=False and error_message set
    on failure (invalid URL, timeout, quota exceeded, 429, malformed
    response, etc.), so a ThreadPoolExecutor batch can never be taken down
    by one bad page. Retries are handled inside _call_pagespeed via the
    retry_with_backoff decorator (API_MAX_RETRIES attempts, per config).
    """
    result = PageResult(page_name=page_name, sheet_name=sheet_name, url=url)
    try:
        data = _call_pagespeed(url)
        metrics = extract_metrics(data, url)
        if metrics.status == "Error":
            raise PageSpeedError(metrics.error_message or "metric extraction failed")
        result.metrics = metrics
        result.success = True
        log.info("OK  %-24s score=%s grade=%s lcp=%ss inp=%s", sheet_name,
                  metrics.performance_score, metrics.grade, metrics.lcp, metrics.inp)
    except Exception as e:  # noqa: BLE001 — page-level isolation boundary, by design
        result.success = False
        result.error_message = str(e)
        log.error("FAIL %-24s %s", sheet_name, e)
    return result
