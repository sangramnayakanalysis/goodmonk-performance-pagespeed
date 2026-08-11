"""
journey.py
==========
Customer Journey monitoring bot. Simulates a normal shopper using a
real headless browser (Playwright) and verifies they can reach
checkout — WITHOUT ever submitting an OTP, entering personal details,
or completing payment. Observe-only: never modifies the Shopify store,
never places a real order.

Flow (per journey_config.STEP_NAMES):
  Homepage -> Collection -> Product Page -> Images Loaded ->
  Product Name Visible -> Price Visible -> Add To Cart Button Visible ->
  Add To Cart Clicked -> Cart Updated -> Checkout Page Opened. STOP.

Retry logic:
  Run fails -> wait 60s -> run again.
    - Second run succeeds -> log only, no alert (transient blip).
    - Second run also fails -> capture screenshot + console errors +
      HTML of the failed step, send an URGENT email, and persist the
      failure to data/journey_runs.json for the dashboard.

This module is fully independent: it does not import main.py,
scheduler.py, dashboard_data.py, or email_report.py. It only reads
config.py (via journey_config) for the site's existing page URLs.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import journey_config as jc
from logger import get_logger
from utils import now_iso, read_json, write_json

log = get_logger("journey")


@dataclass
class StepResult:
    name: str
    status: str = "pending"  # pending | pass | fail
    duration_ms: int = 0
    error: str = ""


@dataclass
class JourneyRun:
    run_id: str
    started_at: str
    finished_at: str = ""
    overall_status: str = "fail"  # pass | fail
    attempt: int = 1
    failed_step: Optional[str] = None
    duration_seconds: float = 0.0
    steps: list = field(default_factory=list)  # list[StepResult]
    console_errors: list = field(default_factory=list)
    capture_dir: Optional[str] = None  # relative path under dashboard/data/journey_captures/


class JourneyStepError(Exception):
    """Raised internally when a single step's verification fails."""


def _run_once(attempt: int):
    """
    Executes the full journey once. Returns (run, page, context, browser, pw)
    — the run record plus the live Playwright page/context/browser/driver
    handles, still open, so the caller can capture a screenshot/HTML from
    the exact failure point before closing them. Untyped on purpose:
    playwright's types are only imported lazily inside this function (see
    below), so they can't appear in the module-level signature.
    """
    from playwright.sync_api import sync_playwright  # imported lazily so the rest of the
                                                       # project never requires playwright installed

    run = JourneyRun(run_id=str(uuid.uuid4())[:8], started_at=now_iso(), attempt=attempt)
    console_errors: list[str] = []
    start = time.monotonic()

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=jc.HEADLESS)
    context = browser.new_context()
    page = context.new_page()
    page.set_default_navigation_timeout(jc.NAV_TIMEOUT_MS)
    page.set_default_timeout(jc.ACTION_TIMEOUT_MS)
    page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda exc: console_errors.append(f"[pageerror] {exc}"))

    def step(name: str, fn) -> None:
        s = StepResult(name=name)
        t0 = time.monotonic()
        try:
            fn()
            s.status = "pass"
        except Exception as e:  # noqa: BLE001 — step-level isolation, by design
            s.status = "fail"
            s.error = str(e)[:400]
            run.failed_step = name
            run.steps.append(s)
            s.duration_ms = int((time.monotonic() - t0) * 1000)
            raise JourneyStepError(f"{name}: {s.error}") from e
        s.duration_ms = int((time.monotonic() - t0) * 1000)
        run.steps.append(s)

    try:
        step("Homepage", lambda: page.goto(jc.HOMEPAGE_URL, wait_until="domcontentloaded"))
        step("Collection", lambda: page.goto(jc.COLLECTION_URL, wait_until="domcontentloaded"))
        step("Product Page", lambda: page.goto(jc.PRODUCT_URL, wait_until="domcontentloaded"))

        def _verify_images():
            imgs = page.locator("main img, .product img, img").first
            imgs.wait_for(state="visible")
        step("Images Loaded", _verify_images)

        def _verify_title():
            title = page.locator("h1").first
            title.wait_for(state="visible")
            if not (title.inner_text() or "").strip():
                raise JourneyStepError("Product title element is empty")
        step("Product Name Visible", _verify_title)

        def _verify_price():
            price = page.locator("[class*='price'], [data-price], .price").first
            price.wait_for(state="visible")
        step("Price Visible", _verify_price)

        atc_selector = "button[name='add'], button:has-text('Add to cart'), button:has-text('Add To Cart')"

        def _verify_atc_visible():
            page.locator(atc_selector).first.wait_for(state="visible")
        step("Add To Cart Button Visible", _verify_atc_visible)

        def _click_atc():
            page.locator(atc_selector).first.click()
        step("Add To Cart Clicked", _click_atc)

        def _verify_cart():
            page.wait_for_timeout(1500)  # allow cart drawer/AJAX cart to settle
            cart_marker = page.locator(
                "[class*='cart-count'], [class*='cart-drawer'], a[href*='/cart']"
            ).first
            cart_marker.wait_for(state="visible")
        step("Cart Updated", _verify_cart)

        def _proceed_to_checkout():
            checkout_link = page.locator(
                "a[href*='/checkout'], button:has-text('Checkout'), input[name='checkout']"
            ).first
            if checkout_link.count() > 0:
                checkout_link.first.click()
            else:
                page.goto(jc.HOMEPAGE_URL.rstrip("/") + "/checkout", wait_until="domcontentloaded")
        step("Checkout Page Opened", _proceed_to_checkout)

        def _verify_checkout_opened():
            page.wait_for_timeout(2000)
            url = page.url
            if "checkout" not in url:
                raise JourneyStepError(f"URL after checkout click does not look like checkout: {url}")
        # Verification folded into the same "Checkout Page Opened" step's
        # already-recorded result rather than a separate step, since the
        # click and the URL check are one logical action per the spec's
        # 10-step list ending at "Verify Checkout page opened".
        _verify_checkout_opened()

        run.overall_status = "pass"

    except JourneyStepError as e:
        run.overall_status = "fail"
        log.warning("Journey attempt %d FAILED at step '%s': %s", attempt, run.failed_step, e)
    except Exception as e:  # noqa: BLE001 — any unexpected browser/nav error still counts as a fail
        run.overall_status = "fail"
        run.failed_step = run.failed_step or "Unknown"
        log.error("Journey attempt %d crashed unexpectedly: %s", attempt, e)

    run.finished_at = now_iso()
    run.duration_seconds = round(time.monotonic() - start, 2)
    run.console_errors = console_errors[:20]

    return run, page, context, browser, pw


def _capture_failure(run: JourneyRun, page) -> None:
    """Only called on a SECOND consecutive failure. Saves a screenshot,
    the page HTML, and the console error log into their own folder, then
    prunes older capture folders beyond MAX_CAPTURES_KEPT."""
    folder = jc.CAPTURES_DIR / run.run_id
    folder.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(folder / "screenshot.png"), full_page=True)
    except Exception as e:  # noqa: BLE001
        log.error("Could not capture screenshot: %s", e)
    try:
        (folder / "page.html").write_text(page.content(), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.error("Could not capture HTML: %s", e)
    write_json(folder / "console.json", run.console_errors)
    run.capture_dir = run.run_id

    _prune_old_captures()


def _prune_old_captures() -> None:
    folders = sorted(
        [f for f in jc.CAPTURES_DIR.iterdir() if f.is_dir()],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for stale in folders[jc.MAX_CAPTURES_KEPT:]:
        for child in stale.glob("*"):
            child.unlink(missing_ok=True)
        stale.rmdir()


def _persist_run(run: JourneyRun) -> None:
    runs = read_json(jc.JOURNEY_RUNS_FILE, default=[])
    runs.append({
        "run_id": run.run_id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "overall_status": run.overall_status,
        "attempt": run.attempt,
        "failed_step": run.failed_step,
        "duration_seconds": run.duration_seconds,
        "steps": [{"name": s.name, "status": s.status, "duration_ms": s.duration_ms, "error": s.error} for s in run.steps],
        "console_errors": run.console_errors,
        "capture_dir": run.capture_dir,
    })
    runs = runs[-jc.MAX_RUNS_KEPT:]
    write_json(jc.JOURNEY_RUNS_FILE, runs)


def run_journey() -> JourneyRun:
    """Runs the journey once; on failure, waits and retries once more
    per the spec's retry logic. Never raises — always returns a
    JourneyRun with overall_status set."""
    run, page, context, browser, pw = _run_once(attempt=1)

    if run.overall_status == "pass":
        page.close(); context.close(); browser.close(); pw.stop()
        _persist_run(run)
        log.info("Journey OK (run_id=%s, %.1fs)", run.run_id, run.duration_seconds)
        return run

    # First attempt failed — close this browser, wait, retry.
    page.close(); context.close(); browser.close(); pw.stop()
    log.warning("Journey failed on first attempt — waiting %ds before retry.", jc.RETRY_WAIT_SECONDS)
    time.sleep(jc.RETRY_WAIT_SECONDS)

    run2, page2, context2, browser2, pw2 = _run_once(attempt=2)

    if run2.overall_status == "pass":
        page2.close(); context2.close(); browser2.close(); pw2.stop()
        _persist_run(run2)
        log.info("Journey OK on retry (run_id=%s) — first failure ignored as transient.", run2.run_id)
        return run2

    # Second consecutive failure — capture evidence before closing, then alert.
    _capture_failure(run2, page2)
    page2.close(); context2.close(); browser2.close(); pw2.stop()
    _persist_run(run2)
    log.error("Journey FAILED twice (run_id=%s, step=%s) — sending alert.", run2.run_id, run2.failed_step)

    try:
        import journey_email
        journey_email.send_failure_alert(run2)
    except Exception as e:  # noqa: BLE001 — alerting must never crash the monitor
        log.error("Failed to send journey failure email: %s", e)

    return run2


if __name__ == "__main__":
    result = run_journey()
    print(f"Journey {result.overall_status.upper()} — run_id={result.run_id}, "
          f"failed_step={result.failed_step}, duration={result.duration_seconds}s")

    try:
        import journey_data
        journey_data.build_journey_dashboard()
    except Exception as e:  # noqa: BLE001
        log.error("Failed to rebuild journey dashboard data: %s", e)

    try:
        import insights_data
        insights_data.build_insights()
    except Exception as e:  # noqa: BLE001
        log.error("Failed to rebuild business insights data: %s", e)
