/* =====================================================================
   history.js — standalone History tab module
   ---------------------------------------------------------------------
   PLUGIN ARCHITECTURE CONTRACT
   Reads the SAME history.json app.js already reads, into its own local
   state, and renders into #tab-history only. This is deliberately a
   different, simpler view (recent runs, one filter, capped row count)
   from the full search/filter/export table already inside the Website
   Performance tab — that table (app.js's renderHistoryTable /
   getFilteredHistory) is completely untouched.

   Journey History / Email History (per the original spec) will slot in
   here once Phase 2 (journey.js) exists — this module already reserves
   a "source" concept for that, it just has nothing but "performance"
   to show yet.
   ===================================================================== */

const GMHistory = (() => {
  const DATA_BASE = "data";
  const MAX_ROWS = 300;
  let initialized = false;
  let rows = [];

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

  function populatePageFilter() {
    const sel = document.getElementById("gm-hist-page");
    const names = [...new Set(rows.map((r) => r._page_name))].sort();
    sel.innerHTML = `<option value="all">All pages</option>` +
      names.map((n) => `<option value="${escapeHTML(n)}">${escapeHTML(n)}</option>`).join("");
  }

  function renderTable() {
    const search = (document.getElementById("gm-hist-search").value || "").toLowerCase();
    const pageFilter = document.getElementById("gm-hist-page").value;
    const statusFilter = document.getElementById("gm-hist-status").value;

    const filtered = rows
      .filter((r) => pageFilter === "all" || r._page_name === pageFilter)
      .filter((r) => statusFilter === "all" || r.Status === statusFilter)
      .filter((r) => !search || (r._page_name || "").toLowerCase().includes(search))
      .slice(-MAX_ROWS)
      .reverse();

    const tbody = document.getElementById("gm-hist-tbody");
    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="6"><div class="gm-empty">No history rows match this filter.</div></td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map((r) => `
      <tr>
        <td>${escapeHTML(r.Date)} ${escapeHTML(r.Time)}</td>
        <td>${escapeHTML(r._page_name)}</td>
        <td>${escapeHTML(r["Performance Score"])}</td>
        <td>${escapeHTML(r.Grade)}</td>
        <td>${escapeHTML(r.LCP)}s</td>
        <td>${escapeHTML(r.Status)}</td>
      </tr>`).join("");
  }

  function bindControls() {
    document.getElementById("gm-hist-search").addEventListener("input", renderTable);
    document.getElementById("gm-hist-page").addEventListener("change", renderTable);
    document.getElementById("gm-hist-status").addEventListener("change", renderTable);
  }

  async function init() {
    if (initialized) return;
    initialized = true;
    try {
      rows = await fetchJSON("history.json");
    } catch (err) {
      console.error("[GMHistory] failed to load history.json:", err);
      rows = [];
    }
    populatePageFilter();
    bindControls();
    renderTable();
  }

  return { init };
})();
