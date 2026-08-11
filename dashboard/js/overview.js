/* =====================================================================
   overview.js — CEO Overview tab module
   ---------------------------------------------------------------------
   PLUGIN ARCHITECTURE CONTRACT
   Fully self-contained. Fetches summary.json and pages.json — the SAME
   files app.js already fetches — independently, into its own local
   state. Does not read window state set by app.js, does not call any
   app.js function, does not touch any element outside #tab-overview.
   If this file is deleted, app.js and the Website Performance tab are
   completely unaffected.
   ===================================================================== */

const GMOverview = (() => {
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

  function overallHealth(summary) {
    if (!summary) return "grey";
    if (summary.critical_count > 0) return "red";
    if (summary.warning_count > 0) return "yellow";
    if (summary.healthy_count > 0) return "green";
    return "grey";
  }

  function healthText(color) {
    return { green: "Healthy", yellow: "Needs Attention", red: "Critical", grey: "No Data Yet" }[color] || "No Data Yet";
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

  function renderHero(summary) {
    const color = overallHealth(summary);
    document.getElementById("gm-ov-health").className = `gm-health-badge ${color}`;
    document.getElementById("gm-ov-health").textContent = healthText(color);
    document.getElementById("gm-ov-updated").textContent = summary ? `Last updated ${formatIST(summary.generated_at)}` : "Waiting for first run…";
  }

  function kpiCard(label, value, sub) {
    return `<div class="gm-kpi-card">
      <div class="gm-kpi-label">${escapeHTML(label)}</div>
      <div class="gm-kpi-value">${escapeHTML(value)}</div>
      ${sub ? `<div class="gm-kpi-sub">${escapeHTML(sub)}</div>` : ""}
    </div>`;
  }

  function renderKPIs(summary) {
    const el = document.getElementById("gm-ov-kpis");
    if (!summary) { el.innerHTML = `<div class="gm-empty">No data yet — the dashboard will populate after the first monitoring run.</div>`; return; }
    el.innerHTML = [
      kpiCard("Website Score", summary.average_score != null ? summary.average_score : "—", "Average across all pages"),
      kpiCard("Critical Alerts", summary.critical_count, "Pages needing urgent attention"),
      kpiCard("Products Monitored", summary.total_urls, "Pages tracked automatically"),
      kpiCard("Best Performing", summary.best_page || "—", ""),
      kpiCard("Worst Performing", summary.worst_page || "—", "Highest priority to fix"),
      kpiCard("Next Scan", formatIST(summary.next_scheduled_run), ""),
    ].join("");
  }

  function renderTopProblems(pages) {
    const el = document.getElementById("gm-ov-risks");
    const problems = pages
      .filter((p) => p.status_color === "red" || p.status_color === "yellow")
      .sort((a, b) => {
        const order = { red: 0, yellow: 1 };
        return (order[a.status_color] ?? 2) - (order[b.status_color] ?? 2);
      })
      .slice(0, 6);

    if (!problems.length) {
      el.innerHTML = `<div class="gm-empty">No pages currently at risk — everything is within target.</div>`;
      return;
    }

    el.innerHTML = problems.map((p) => {
      const score = p.latest ? p.latest["Performance Score"] : "—";
      return `<div class="gm-risk-item ${p.status_color}">
        <div>
          <div class="gm-risk-item__name">${escapeHTML(p.name)}</div>
          <div class="gm-risk-item__reason">Score ${escapeHTML(score)} · ${escapeHTML(GMBusiness.statusLabel(p.status_color))}</div>
        </div>
      </div>`;
    }).join("");
  }

  function renderBusinessExplanations(pages) {
    const el = document.getElementById("gm-ov-business");
    const atRisk = pages
      .filter((p) => (p.status_color === "red" || p.status_color === "yellow") && p.top_opportunities && p.top_opportunities.length)
      .slice(0, 5);

    if (!atRisk.length) {
      el.innerHTML = `<div class="gm-empty">No slow pages with diagnostic detail to explain right now.</div>`;
      return;
    }

    el.innerHTML = atRisk.map((p) => {
      const reasons = GMBusiness.explain(p.top_opportunities);
      const reasonsHTML = reasons.map((r) => `
        <div class="gm-business-reason"><b>${escapeHTML(r.title)}.</b> ${escapeHTML(r.plain)}</div>
      `).join("");
      const topImpact = reasons[0] ? reasons[0].impact : "";
      return `<div class="gm-business-card">
        <div class="gm-business-card__head">
          <div class="gm-business-card__title">${escapeHTML(p.name)}</div>
          <div class="gm-business-status ${p.status_color}">${escapeHTML(GMBusiness.statusLabel(p.status_color))}</div>
        </div>
        <div class="gm-business-reasons">${reasonsHTML}</div>
        ${topImpact ? `<div class="gm-business-impact"><b>Business impact:</b> ${escapeHTML(topImpact)}</div>` : ""}
      </div>`;
    }).join("");
  }

  async function render() {
    let summary = null, pages = [];
    try {
      [summary, pages] = await Promise.all([fetchJSON("summary.json"), fetchJSON("pages.json")]);
    } catch (err) {
      console.error("[GMOverview] failed to load data:", err);
      document.getElementById("gm-ov-kpis").innerHTML = `<div class="gm-empty">Couldn't load dashboard data yet.</div>`;
      return;
    }
    renderHero(summary);
    renderKPIs(summary);
    renderTopProblems(pages || []);
    renderBusinessExplanations(pages || []);
  }

  function init() {
    if (initialized) { render(); return; } // re-render on re-activation, but no double-binding
    initialized = true;
    render();
  }

  return { init };
})();
