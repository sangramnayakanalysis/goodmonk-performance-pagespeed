/* =====================================================================
   journey.js — Customer Journey tab module
   ---------------------------------------------------------------------
   PLUGIN ARCHITECTURE CONTRACT
   Fully self-contained: fetches only dashboard/data/journey.json
   (written by journey_data.py), renders only into #tab-journey. Shares
   no state or function calls with app.js, overview.js, settings.js, or
   history.js. Deleting this file + journey.css only removes this tab.
   ===================================================================== */

const GMJourney = (() => {
  const DATA_BASE = "data";
  let initialized = false;

  async function fetchJSON(path) {
    const res = await fetch(`${DATA_BASE}/${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return res.json();
  }

  function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function formatIST(isoString) {
    if (!isoString) return "—";
    try {
      return new Date(isoString).toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata", day: "2-digit", month: "short",
        hour: "2-digit", minute: "2-digit",
      }) + " IST";
    } catch (_) { return isoString; }
  }

  function healthText(color) {
    return { green: "Healthy", yellow: "Needs Attention", red: "Critical", grey: "Not Monitoring Yet" }[color] || "Not Monitoring Yet";
  }

  function kpi(label, value, colorClass) {
    return `<div class="gm-journey-kpi">
      <div class="label">${escapeHTML(label)}</div>
      <div class="value ${colorClass || ""}">${escapeHTML(value)}</div>
    </div>`;
  }

  function renderKPIs(data) {
    const el = document.getElementById("gm-journey-kpis");
    const healthColor = data.overall_health || "grey";
    el.innerHTML = [
      kpi("Overall Health", healthText(healthColor), healthColor),
      kpi("Today's Runs", data.today_runs ?? "—"),
      kpi("Success % (last 30)", data.success_pct_last_30 != null ? `${data.success_pct_last_30}%` : "—",
          data.success_pct_last_30 == null ? "" : data.success_pct_last_30 >= 90 ? "green" : data.success_pct_last_30 >= 70 ? "yellow" : "red"),
      kpi("Failure % (last 30)", data.failure_pct_last_30 != null ? `${data.failure_pct_last_30}%` : "—"),
      kpi("Avg Journey Time", data.avg_journey_seconds != null ? `${data.avg_journey_seconds}s` : "—"),
    ].join("");
  }

  function renderLatestSteps(data) {
    const el = document.getElementById("gm-journey-steps");
    const steps = data.latest_run ? data.latest_run.steps : null;
    if (!steps || !steps.length) {
      el.innerHTML = `<div class="gm-empty">No journey runs recorded yet.</div>`;
      return;
    }
    el.innerHTML = steps.map((s) => `
      <div class="gm-journey-step ${s.status}">
        <span class="dot"></span>${escapeHTML(s.name)}
      </div>`).join("");
  }

  function renderFailure(data) {
    const el = document.getElementById("gm-journey-failure");
    const f = data.latest_confirmed_failure;
    if (!f) {
      el.style.display = "none";
      el.innerHTML = "";
      return;
    }
    el.style.display = "block";
    const screenshotHTML = f.capture_dir
      ? `<img src="data/journey_captures/${encodeURIComponent(f.capture_dir)}/screenshot.png" alt="Failure screenshot" loading="lazy" />`
      : `<div class="row"><i>No screenshot captured for this failure.</i></div>`;

    el.innerHTML = `
      <h3>⚠ Confirmed Customer Journey Failure</h3>
      <div class="row"><b>Failed Step</b>${escapeHTML(f.failed_step)}</div>
      <div class="row"><b>When</b>${escapeHTML(formatIST(f.finished_at))}</div>
      <div class="row"><b>Retry Status</b>Retried once — failed both attempts (confirmed, not transient)</div>
      <div class="row"><b>Business Impact</b>${escapeHTML(f.business_impact)}</div>
      <div class="row"><b>Suggested Cause</b>${escapeHTML(f.suggested_cause)}</div>
      ${screenshotHTML}
    `;
  }

  function renderHistory(data) {
    const tbody = document.getElementById("gm-journey-history-tbody");
    const timeline = data.timeline || [];
    if (!timeline.length) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="gm-empty">No runs yet.</div></td></tr>`;
      return;
    }
    tbody.innerHTML = timeline.map((r) => `
      <tr>
        <td>${escapeHTML(formatIST(r.started_at))}</td>
        <td><span class="gm-journey-status-chip ${r.overall_status}">${escapeHTML((r.overall_status || "").toUpperCase())}</span></td>
        <td>${escapeHTML(r.failed_step || "—")}</td>
        <td>${escapeHTML(r.attempt)}</td>
        <td>${escapeHTML(r.duration_seconds)}s</td>
      </tr>`).join("");
  }

  async function render() {
    let data;
    try {
      data = await fetchJSON("journey.json");
    } catch (err) {
      console.error("[GMJourney] failed to load journey.json:", err);
      document.getElementById("gm-journey-kpis").innerHTML = `<div class="gm-empty">Couldn't load journey data yet.</div>`;
      return;
    }
    renderKPIs(data);
    renderLatestSteps(data);
    renderFailure(data);
    renderHistory(data);
  }

  function init() {
    if (initialized) { render(); return; }
    initialized = true;
    render();
  }

  return { init };
})();
