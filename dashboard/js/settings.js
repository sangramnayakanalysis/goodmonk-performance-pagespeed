/* =====================================================================
   settings.js — Settings tab module
   ---------------------------------------------------------------------
   PLUGIN ARCHITECTURE CONTRACT
   Reads only the new, additive dashboard/data/settings.json (written by
   settings_data.py). Never touches summary.json/pages.json's existing
   consumers. Fully self-contained render into #tab-settings.
   ===================================================================== */

const GMSettings = (() => {
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

  function row(label, value) {
    return `<div class="gm-settings-row"><span class="label">${escapeHTML(label)}</span><span class="value">${escapeHTML(value)}</span></div>`;
  }

  function render(settings) {
    const el = document.getElementById("gm-settings-body");
    if (!settings) {
      el.innerHTML = `<div class="gm-empty">Settings will appear after the next monitoring run.</div>`;
      return;
    }
    const m = settings.monitoring || {};
    const t = settings.thresholds || {};

    const monitoringCard = `<div class="gm-settings-card"><h3>Monitoring</h3>
      ${row("Total pages tracked", m.total_pages)}
      ${row("Priority pages (hourly)", m.priority_pages)}
      ${row("Secondary pages (daily)", m.secondary_pages)}
      ${row("Measurement mode", m.strategy)}
      ${row("Timezone", m.timezone)}
      ${row("Email alerts", settings.email_alerts_enabled ? "Enabled" : "Disabled")}
    </div>`;

    const thresholdCard = `<div class="gm-settings-card"><h3>Health Thresholds</h3>
      ${row("Score — Healthy ≥", t.score ? t.score.green_min : "—")}
      ${row("Score — Warning ≥", t.score ? t.score.amber_min : "—")}
      ${row("LCP — Healthy <", t.lcp_seconds ? `${t.lcp_seconds.green_max}s` : "—")}
      ${row("LCP — Warning <", t.lcp_seconds ? `${t.lcp_seconds.amber_max}s` : "—")}
      ${row("CLS — Healthy <", t.cls ? t.cls.green_max : "—")}
      ${row("TBT — Healthy <", t.tbt_ms ? `${t.tbt_ms.green_max}ms` : "—")}
    </div>`;

    const pagesList = (settings.pages || []).map((p) => `
      <div class="gm-settings-page-row">
        <span>${escapeHTML(p.name)}</span>
        <span class="gm-tier-chip">${escapeHTML(p.tier)}</span>
      </div>`).join("");

    const pagesCard = `<div class="gm-settings-card"><h3>Monitored Pages</h3>
      <div class="gm-settings-pages">${pagesList || '<div class="gm-empty">No pages configured.</div>'}</div>
    </div>`;

    el.innerHTML = monitoringCard + thresholdCard + pagesCard;
  }

  async function init() {
    if (initialized) return; // config rarely changes mid-session; render once
    initialized = true;
    try {
      const settings = await fetchJSON("settings.json");
      render(settings);
    } catch (err) {
      console.error("[GMSettings] failed to load settings.json:", err);
      render(null);
    }
  }

  return { init };
})();
