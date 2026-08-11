/* =====================================================================
   nav.js — Top navigation module
   ---------------------------------------------------------------------
   PLUGIN ARCHITECTURE CONTRACT
   Any other module (overview.js, settings.js, history.js, journey.js,
   and any future module) can register itself here without nav.js knowing
   anything about what that module does:

     GMNav.registerTab("overview", { onActivate: () => Overview.init() });

   nav.js owns exactly one thing: which .tab-panel is visible. It never
   calls app.js, never reads app.js's `state`, and never touches any
   element that existed in index.html before this module was added
   (the "Website Performance" tab's contents are opaque to nav.js — it
   only toggles the wrapping <section>'s visibility class).
   ===================================================================== */

const GMNav = (() => {
  const tabs = new Map(); // tabId -> { onActivate, activated }

  function registerTab(tabId, { onActivate } = {}) {
    tabs.set(tabId, { onActivate: onActivate || null, activated: false });
  }

  function activate(tabId) {
    document.querySelectorAll(".gm-nav__tab").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.tab === tabId);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("is-active", panel.id === `tab-${tabId}`);
    });

    const entry = tabs.get(tabId);
    if (entry && !entry.activated && typeof entry.onActivate === "function") {
      entry.activated = true; // lazy-init each module exactly once
      try {
        entry.onActivate();
      } catch (err) {
        console.error(`[GMNav] tab "${tabId}" failed to initialize:`, err);
      }
    }

    try {
      history.replaceState(null, "", `#${tabId}`);
    } catch (_) { /* ignore — non-essential */ }
  }

  function init() {
    document.querySelectorAll(".gm-nav__tab").forEach((btn) => {
      btn.addEventListener("click", () => activate(btn.dataset.tab));
    });

    const fromHash = (location.hash || "").replace("#", "");
    const startTab = tabs.has(fromHash) ? fromHash : "performance";
    activate(startTab);
  }

  return { registerTab, activate, init };
})();

document.addEventListener("DOMContentLoaded", () => {
  // "performance" tab wraps the existing dashboard and needs no init
  // callback — app.js already boots itself independently via its own
  // DOMContentLoaded listener in app.js, untouched.
  GMNav.registerTab("performance");
  // NOTE: these use `typeof X !== "undefined"`, not `window.X &&` — the
  // modules below declare their public interface as a top-level `const`
  // (e.g. `const GMOverview = ...` in overview.js). Top-level const/let
  // in a classic script creates a lexical binding, NOT a property on
  // `window` — so `window.GMOverview` is always undefined even when the
  // module loaded and works fine. A previous version of this file used
  // `window.GMOverview && GMOverview.init()`, which silently no-opped on
  // every tab (no exception, so nothing showed in the console) — this is
  // the actual root cause of a real incident where every tab except
  // Website Performance rendered completely empty. `typeof` correctly
  // checks the lexical binding without throwing if it's ever genuinely
  // missing, so it works for const/let/var alike and still degrades
  // gracefully if a module's script is ever deleted.
  GMNav.registerTab("overview", { onActivate: () => typeof GMOverview !== "undefined" && GMOverview.init() });
  GMNav.registerTab("insights", { onActivate: () => typeof GMInsights !== "undefined" && GMInsights.init() });
  GMNav.registerTab("journey", { onActivate: () => typeof GMJourney !== "undefined" && GMJourney.init() });
  GMNav.registerTab("history", { onActivate: () => typeof GMHistory !== "undefined" && GMHistory.init() });
  GMNav.registerTab("settings", { onActivate: () => typeof GMSettings !== "undefined" && GMSettings.init() });

  GMNav.init();
});
