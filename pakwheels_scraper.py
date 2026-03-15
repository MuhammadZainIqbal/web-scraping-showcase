"""
PakWheels Used Car Scraper — Playwright + Stealth Layer
Target : https://www.pakwheels.com/used-cars/search/-/?q=honda+civic
Output : pakwheels_civics.json  (first MAX_RESULTS listings)

Stealth  : playwright_stealth + Chrome-family UA, 1920×1080, en-US locale
Anti-bot : fixed settle delay + wait_for_selector + Cloudflare CAPTCHA polling
"""

import json
import logging
import random
import re
import time

from playwright.sync_api import Playwright, TimeoutError as PlaywrightTimeoutError, sync_playwright

try:
    from playwright_stealth import stealth_sync
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("pakwheels_scraper.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TARGET_URL        = "https://www.pakwheels.com/used-cars/search/-/?q=honda+civic"
OUTPUT_FILE       = "pakwheels_civics.json"
DEBUG_HTML_FILE   = "pakwheels_debug.html"   # written only if 0 listings found
MAX_RESULTS       = 20
CAPTCHA_TIMEOUT_S = 120   # seconds to wait for manual CAPTCHA solving

# ---------------------------------------------------------------------------
# CSS Selectors — adjust here if PakWheels updates its markup
# ---------------------------------------------------------------------------

SEL_CONTAINER = "li.classified-listing"        # outer wrapper for each listing
SEL_TITLE     = "a.car-name"                   # heading link (title + href)
SEL_PRICE     = "div.price-details"            # main price block
SEL_ATTRS     = "ul.search-vehicle-info-2 li"  # year / mileage / fuel chips

# ---------------------------------------------------------------------------
# User-Agents — Chrome-family only; mixing engines on Chromium is detectable
# ---------------------------------------------------------------------------

USER_AGENTS = [
    # Chrome 124 — Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.6367.155 Safari/537.36",
    # Chrome 124 — macOS Sonoma
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.6367.155 Safari/537.36",
    # Edge 124 — Windows 10
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.6367.155 Safari/537.36 Edg/124.0.0.0",
]

# Phrases present in Cloudflare's interstitial / CAPTCHA pages
_CAPTCHA_PHRASES = ["verify you are human", "just a moment", "checking your browser"]

# Fallback JS patch when playwright_stealth is absent
_WEBDRIVER_PATCH = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_price(price_text: str) -> int:
    """
    Convert PakWheels price strings to a pure integer (PKR).

    Examples:
        "PKR 21 lacs"      →  2_100_000
        "PKR 2.1 crore"    → 21_000_000
        "PKR 23,50,000"    →  2_350_000   (already full digits)
    """
    text = price_text.lower().strip()
    # Extract the leading numeric value (handles commas and decimals)
    match = re.search(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return 0
    number = float(match.group())
    if "crore" in text:
        return int(number * 10_000_000)
    if "lac" in text:          # covers "lac" and "lacs"
        return int(number * 100_000)
    return int(number)         # already a raw integer string


def _page_has_captcha(page) -> bool:
    """Return True if Cloudflare's challenge/CAPTCHA page is active."""
    try:
        title = page.title().lower()
        body  = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        return False
    return any(p in title or p in body for p in _CAPTCHA_PHRASES)


def _wait_for_captcha_resolution(page, timeout_s: int) -> bool:
    """
    Poll every 5 s for up to *timeout_s* seconds waiting for the human to
    solve the CAPTCHA in the open browser window.

    Returns True  if the challenge was cleared before the deadline.
    Returns False if it was not.
    """
    logger.warning(
        "CAPTCHA detected — please solve it in the open browser window. "
        f"Waiting up to {timeout_s}s …"
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(5)
        if not _page_has_captcha(page):
            logger.info("CAPTCHA resolved — continuing.")
            return True
    logger.error(
        f"CAPTCHA was NOT resolved within {timeout_s}s. Aborting scrape."
    )
    return False


def _extract_attrs(container) -> dict:
    """
    Pull year / mileage / fuel-type from the attribute chip list.
    Positional: chip[0]=year, chip[1]=mileage, chip[2]=fuel type.
    Returns empty strings for any missing chip.
    """
    chips = container.query_selector_all(SEL_ATTRS)
    values = [c.inner_text().strip() for c in chips]
    return {
        "year":      values[0] if len(values) > 0 else "",
        "mileage":   values[1] if len(values) > 1 else "",
        "fuel_type": values[2] if len(values) > 2 else "",
    }


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def run(playwright: Playwright) -> None:
    selected_ua = random.choice(USER_AGENTS)
    logger.info(f"User-Agent  : {selected_ua}")
    logger.info(f"Stealth pkg : {_STEALTH_AVAILABLE}")

    browser = playwright.chromium.launch(headless=False)

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        user_agent=selected_ua,
    )
    page = context.new_page()

    # ------------------------------------------------------------------
    # Stealth patches — must be applied BEFORE page.goto
    # ------------------------------------------------------------------
    if _STEALTH_AVAILABLE:
        stealth_sync(page)
        logger.info("playwright_stealth patches applied.")
    else:
        page.add_init_script(_WEBDRIVER_PATCH)
        logger.info("Manual navigator.webdriver patch applied (fallback).")

    # ------------------------------------------------------------------
    # Navigation + Cloudflare wait
    # ------------------------------------------------------------------
    logger.info(f"Navigating to: {TARGET_URL}")
    page.goto(TARGET_URL, wait_until="load")

    # Cloudflare's bot-management JS sends continuous background XHR heartbeats
    # that permanently prevent "networkidle" from firing — it will always timeout.
    # Instead: fixed 3s settle delay to let the CF challenge script execute, then
    # wait for actual page content to appear in the DOM.
    logger.info("Settling after load (3s) …")
    page.wait_for_timeout(3000)

    # ------------------------------------------------------------------
    # CAPTCHA check
    # ------------------------------------------------------------------
    if _page_has_captcha(page):
        resolved = _wait_for_captcha_resolution(page, CAPTCHA_TIMEOUT_S)
        if not resolved:
            context.close()
            browser.close()
            return
        # Brief settle after the CAPTCHA redirect completes
        page.wait_for_timeout(3000)

    # Wait for the first listing container — confirms real content loaded.
    # Times out cleanly if the page is still blocked or selectors are wrong.
    logger.info(f"Waiting for listing containers (selector: {SEL_CONTAINER}) …")
    try:
        page.wait_for_selector(SEL_CONTAINER, timeout=15_000)
    except PlaywrightTimeoutError:
        logger.error(
            f"Timed out waiting for '{SEL_CONTAINER}'. "
            "Page may still be blocked or selector needs updating. "
            f"Raw HTML saved to '{DEBUG_HTML_FILE}'."
        )
        with open(DEBUG_HTML_FILE, "w", encoding="utf-8") as fh:
            fh.write(page.content())
        context.close()
        browser.close()
        return

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------
    containers = page.query_selector_all(SEL_CONTAINER)
    logger.info(f"Listing containers found: {len(containers)}")

    # Safety net — if nothing matched, dump the raw HTML for selector debugging
    if not containers:
        logger.error(
            f"0 containers matched '{SEL_CONTAINER}'. "
            f"Raw HTML saved to '{DEBUG_HTML_FILE}' — "
            "inspect it to correct the selector constants at the top of this file."
        )
        with open(DEBUG_HTML_FILE, "w", encoding="utf-8") as fh:
            fh.write(page.content())
        context.close()
        browser.close()
        return

    cars = []
    for container in containers[:MAX_RESULTS]:
        # Title + URL
        title_el = container.query_selector(SEL_TITLE)
        title    = title_el.inner_text().strip() if title_el else ""
        href     = title_el.get_attribute("href")  if title_el else ""
        url      = f"https://www.pakwheels.com{href}" if href and href.startswith("/") else href

        # Price — parsed to a pure integer
        price_el   = container.query_selector(SEL_PRICE)
        price_raw  = price_el.inner_text().strip() if price_el else ""
        price_int  = parse_price(price_raw)

        # Year / Mileage / Fuel type
        attrs = _extract_attrs(container)

        cars.append({
            "title":      title,
            "url":        url,
            "price_pkr":  price_int,
            "price_raw":  price_raw,
            "year":       attrs["year"],
            "mileage":    attrs["mileage"],
            "fuel_type":  attrs["fuel_type"],
        })

        logger.info(f"  [{len(cars):02d}] {title} — PKR {price_int:,}")

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    print(f"Total listings scraped: {len(cars)}")
    logger.info(f"Total listings scraped: {len(cars)}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(cars, fh, ensure_ascii=False, indent=4)
    logger.info(f"Results saved to '{OUTPUT_FILE}'.")

    context.close()
    browser.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
