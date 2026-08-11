"""
journey_config.py
==================
Configuration for the Customer Journey monitoring module only.
Deliberately NOT part of config.py — journey.py, journey_data.py, and
journey_email.py should be deletable as a unit without touching
anything the existing PageSpeed monitoring depends on.

Page URLs are read from config.PAGES (the project's existing single
source of truth for URLs) rather than duplicated here — see
_homepage_url() etc. below. Everything else journey-specific lives in
this file.
"""

from __future__ import annotations

import config  # read-only: only config.PAGES / config.BASE_DIR are used, nothing is written back

BASE_DIR = config.BASE_DIR
DATA_DIR = BASE_DIR / "data"
DASHBOARD_DATA_DIR = config.DASHBOARD_DATA_DIR
CAPTURES_DIR = DASHBOARD_DATA_DIR / "journey_captures"

JOURNEY_RUNS_FILE = DATA_DIR / "journey_runs.json"
JOURNEY_DASHBOARD_FILE = DASHBOARD_DATA_DIR / "journey.json"

for _dir in (DATA_DIR, DASHBOARD_DATA_DIR, CAPTURES_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


def _homepage_url() -> str:
    return next((p.url for p in config.PAGES if p.name == "Homepage"), "https://www.goodmonk.in/")


def _collection_url() -> str:
    return next((p.url for p in config.PAGES if p.name == "Shop All"), "https://www.goodmonk.in/collections/all")


def _product_url() -> str:
    # A stable, always-in-stock product used purely as a monitoring probe.
    return next((p.url for p in config.PAGES if p.name == "FNM"), "https://www.goodmonk.in/products/good-monk")


HOMEPAGE_URL = _homepage_url()
COLLECTION_URL = _collection_url()
PRODUCT_URL = _product_url()

# --- Browser / run behaviour -------------------------------------------
HEADLESS = True
NAV_TIMEOUT_MS = 30_000
ACTION_TIMEOUT_MS = 15_000
RUN_INTERVAL_MINUTES = 15  # informational — actual schedule lives in the workflow cron

# --- Retry logic ----------------------------------------------------------
RETRY_WAIT_SECONDS = 60

# --- Capture retention ------------------------------------------------
MAX_CAPTURES_KEPT = 5      # oldest failure-capture folders beyond this are pruned
MAX_RUNS_KEPT = 500        # data/journey_runs.json is capped, oldest entries dropped

# --- Journey step names, in order (used by journey.py and the dashboard) --
STEP_NAMES = [
    "Homepage",
    "Collection",
    "Product Page",
    "Images Loaded",
    "Product Name Visible",
    "Price Visible",
    "Add To Cart Button Visible",
    "Add To Cart Clicked",
    "Cart Updated",
    "Checkout Page Opened",
]

# --- Business impact copy, keyed by the step name that failed -------------
# Plain-English text for the email alert and the dashboard — mirrors the
# dashboard's business.js dictionary pattern but on the Python side.
BUSINESS_IMPACT = {
    "Homepage": "The website may be down or unreachable — customers cannot start shopping at all.",
    "Collection": "Customers cannot browse products — the category/shop page isn't loading correctly.",
    "Product Page": "A product page failed to load — customers can't view or buy this item.",
    "Images Loaded": "Product images aren't displaying — customers can't see what they're buying.",
    "Product Name Visible": "The product title isn't showing — the page may be broken or mislabelled.",
    "Price Visible": "The price isn't visible — customers can't tell how much the product costs.",
    "Add To Cart Button Visible": "The Add To Cart button is missing or hidden — customers cannot buy this product.",
    "Add To Cart Clicked": "Clicking Add To Cart isn't working — customers are blocked from purchasing.",
    "Cart Updated": "The cart isn't updating after Add To Cart — customers may think their action failed and leave.",
    "Checkout Page Opened": "Checkout isn't opening — customers who are ready to pay cannot complete their purchase.",
}

SUGGESTED_CAUSE = {
    "Homepage": "Site outage, DNS issue, or hosting problem.",
    "Collection": "Collection page template error or app/theme conflict.",
    "Product Page": "Product page template error, or the product was unpublished/deleted.",
    "Images Loaded": "CDN issue, broken image reference, or slow image loading.",
    "Product Name Visible": "Theme/template change affecting the product title element.",
    "Price Visible": "Pricing app conflict or theme change affecting the price element.",
    "Add To Cart Button Visible": "Product out of stock, or a theme/app change hid the button.",
    "Add To Cart Clicked": "JavaScript error, app conflict, or button handler broken.",
    "Cart Updated": "Cart drawer/app conflict, or slow cart API response.",
    "Checkout Page Opened": "Checkout redirect broken, or Shopify checkout configuration issue.",
}
