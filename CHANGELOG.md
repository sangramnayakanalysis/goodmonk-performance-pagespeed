# GoodMonk Performance Command Center — Manager Review Fixes

Implements all 6 items from the July 2026 review, in priority order. Every
existing feature (Sheets schema, dashboard JSON keys, GitHub Actions
deploy step, auto-refresh, dark mode, CSV/Excel export) still works —
nothing was rebuilt, only extended. 12 files touched; full diff verified
against the original upload, nothing else changed.

---

## 1. Traffic-light thresholds (`config.py`, `dashboard_data.py`, `email_report.py`)

**Was:** one hard threshold (`ALERT_SCORE_THRESHOLD = 80`) — with real
scores at 26-50, every page showed red permanently.

**Now:** 3-tier system in `config.py` (`SCORE_GREEN_MIN=60`,
`SCORE_AMBER_MIN=40`, plus matching pairs for LCP/CLS/TTFB/TBT), all
overridable via `.env`. `dashboard_data.py` computes a `metric_tiers`
dict per page (one tier per metric) and the overall `status_color` is
the worse of Score/LCP. `email_report.py`'s summary email now colors
against the same 60/40 bar instead of the old 80/65.

## 2. Benchmark lines on charts (`dashboard/index.html`, `dashboard/js/app.js`)

Added the Chart.js annotation plugin via CDN. `app.js` draws dashed
reference lines with labels on all 3 trend charts: Score (60 "Our
Target", 90 "Google Good"), LCP (2.5 "Good", 4 "Poor"), and the third
chart — renamed **Speed Index Trend** (it was already Speed Index data
under the old "Fully Loaded" label, per the PSI field mapping — just
mislabeled) — gets 3.4/5.8 "Good"/"Poor" lines.

## 3. Page selector + per-page trends (`dashboard_data.py`, `dashboard/index.html`, `dashboard/js/app.js`)

`trends.json` restructured from a flat array to
`{daily/weekly/monthly: {overall: [...], pages: {<name>: [...]}}}` —
`dashboard_data.py` now buckets each page's own history separately, not
just the 16-page blend. A dropdown above the charts (priority pages
first, per the brief) lets you pick one page or "All Pages"; `app.js`
swaps the active series and re-renders all 3 charts. `app.js` has a
defensive fallback for the old flat-array shape so the dashboard won't
break on the JSON already committed until the next scheduled run
regenerates it.

## 4. Google diagnostic opportunities (`pagespeed.py`, `google_sheet.py`, `dashboard_data.py`, `dashboard/js/app.js`)

`pagespeed.py` now extracts `lighthouseResult.audits` entries where
`details.type == "opportunity"` and `numericValue > 0`, sorts by
savings, keeps top 5. **Persisted this to a new Sheets column** (`Top
Opportunities`, column M — JSON-encoded) rather than only an in-memory
run state, so it's reliably available for every page's *latest* row
regardless of resume/tier state. Note: `google_sheet.py`'s header-write
range was hardcoded to `A1:L1`; fixed it to compute the range from
`len(HISTORY_HEADERS)` so it doesn't silently truncate the new column.
Each page card now shows a "Why is this page slow?" list (top 3).

## 5. Expanded page cards (`dashboard_data.py`, `dashboard/js/app.js`, `dashboard/css/style.css`)

Cards now show Score, LCP, CLS, TTFB, TBT (each independently
color-coded per its own tier), a score trend arrow vs ~1 week ago
(`dashboard_data.py`'s new `_score_trend()`), the top diagnosed issue in
one line, and the top-3 opportunities list from fix #4. New CSS for the
metrics grid, trend arrow colors, and opportunities list; card min-width
bumped 230px → 260px for the extra content.

## 6. Hourly priority / daily secondary tiers (`config.py`, `scheduler.py`, `main.py`, `.github/workflows/monitor.yml`)

`config.py` derives `PAGES_PRIORITY` (Homepage, Shop All, H50+, FNM,
Plant Protein Roti, Fiber Fix) and `PAGES_SECONDARY` (the other 10) from
the existing `PAGES` list — no duplicated page definitions. `main.py` /
`scheduler.py` take `--priority` / `--secondary` flags. The workflow now
has two cron triggers: `0 * * * *` (hourly → `--priority`) and
`30 20 * * *` (20:30 UTC = 2 AM IST → `--secondary`); a new step reads
`github.event.schedule` to pick the right flag automatically, with a
`tier` dropdown for manual runs.

---

## Testing performed

- Every modified `.py` file: `ast.parse` + `py_compile` clean.
- `dashboard_data.build_all()` run end-to-end against mocked Sheets data
  (16 pages, 10 rows each) — verified `summary.json`, `pages.json`,
  `trends.json`, `history.json` all produce the expected new shapes.
- `app.js` loaded in a real jsdom DOM (actual `index.html` + `app.js`,
  Chart.js stubbed since jsdom has no canvas) against both the new mock
  data *and* the original pre-migration JSON already in the repo — zero
  runtime exceptions either way, page selector populates, granularity
  toggle works, all 16 cards render.
- Full recursive diff against the original upload confirms exactly the
  12 files above changed and nothing else.

## Not built (per your "Not Built Yet" list — unchanged, still pending)

AI recommended actions via Claude API, AI diagnosis in alert emails,
executive summary panel for Jitin, funnel panel.
