"""
journey_email.py
=================
Sends the "URGENT — Customer Journey Failure" alert. Deliberately
independent of email_report.py (different trigger, different content,
different urgency) — only reads config.py for SMTP_* values, exactly
like email_report.py does, but shares no code or state with it so
either can be changed/removed without affecting the other.

Only called by journey.py, and only after a SECOND consecutive
failure (see journey.py's retry logic) — a single transient failure
never sends email.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText

import config
import journey_config as jc
from logger import get_logger

log = get_logger("journey_email")


def _build_html(run) -> str:
    impact = jc.BUSINESS_IMPACT.get(run.failed_step, "This step failing may prevent customers from completing a purchase.")
    cause = jc.SUGGESTED_CAUSE.get(run.failed_step, "Unknown — see console errors and captured HTML for detail.")
    console_html = "".join(f"<div style='font-family:monospace;font-size:11px;color:#B91C1C;'>{e}</div>" for e in run.console_errors[:10])

    steps_html = ""
    for s in run.steps:
        color = "#2FB673" if s.status == "pass" else "#E05252"
        icon = "✓" if s.status == "pass" else "✗"
        steps_html += f"""<div style="padding:4px 0;color:{color};">{icon} {s.name}
            {f'<span style="color:#94A3B8;font-size:12px;">— {s.error}</span>' if s.error else ""}</div>"""

    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:640px;margin:auto;color:#1B2233;">
      <h2 style="color:#E05252;margin-bottom:4px;">🚨 Urgent — Customer Journey Failure</h2>
      <p style="color:#6B7488;margin-top:0;">GoodMonk Website · {run.finished_at}</p>

      <table style="width:100%;font-size:14px;margin:16px 0;border-collapse:collapse;">
        <tr><td style="padding:6px 0;color:#6B7488;width:160px;">Website</td><td>{jc.HOMEPAGE_URL}</td></tr>
        <tr><td style="padding:6px 0;color:#6B7488;">Failed Step</td><td><b style="color:#E05252;">{run.failed_step}</b></td></tr>
        <tr><td style="padding:6px 0;color:#6B7488;">Attempts</td><td>2 of 2 (confirmed, not transient)</td></tr>
        <tr><td style="padding:6px 0;color:#6B7488;">Duration</td><td>{run.duration_seconds}s</td></tr>
      </table>

      <h3 style="margin-bottom:4px;">Business Impact</h3>
      <p style="color:#3A4256;margin-top:0;">{impact}</p>

      <h3 style="margin-bottom:4px;">Suggested Cause</h3>
      <p style="color:#3A4256;margin-top:0;">{cause}</p>

      <h3 style="margin-bottom:4px;">Journey Steps</h3>
      <div style="background:#F5F7FB;border-radius:10px;padding:12px 16px;">{steps_html}</div>

      {"<h3 style='margin-bottom:4px;'>Console Errors</h3>" + console_html if console_html else ""}

      <p style="color:#94A3B8;font-size:12px;margin-top:20px;">
        A screenshot is attached below if one could be captured. This monitor never submits real
        orders — it only verifies customers can browse, add to cart, and reach checkout.
      </p>
    </div>
    """


def send_failure_alert(run) -> None:
    if not config.EMAIL_ENABLED:
        log.info("Email not configured — skipping journey failure alert.")
        return

    subject = f"URGENT — Customer Journey Failure ({run.failed_step or 'Unknown step'})"

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = ", ".join(config.EMAIL_TO)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(_build_html(run), "html"))
    msg.attach(alt)

    if run.capture_dir:
        screenshot_path = jc.CAPTURES_DIR / run.capture_dir / "screenshot.png"
        if screenshot_path.exists():
            try:
                with open(screenshot_path, "rb") as f:
                    img = MIMEImage(f.read())
                    img.add_header("Content-Disposition", "attachment", filename="failure_screenshot.png")
                    msg.attach(img)
            except Exception as e:  # noqa: BLE001
                log.error("Could not attach screenshot: %s", e)

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.EMAIL_FROM, config.EMAIL_TO, msg.as_string())
        log.info("Journey failure alert sent to %s.", ", ".join(config.EMAIL_TO))
    except Exception as e:  # noqa: BLE001 — alert failure must never crash the monitor
        log.error("Failed to send journey failure alert: %s", e)
