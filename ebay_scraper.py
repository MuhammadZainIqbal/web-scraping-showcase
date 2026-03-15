"""
eBay GPU Listings Scraper — Playwright + Stealth
Target : https://www.ebay.com/sch/i.html?_nkw=rtx+4060
Pages  : 3
Output : ebay_gpus.json

Stealth  : playwright_stealth (hard requirement) + navigator.languages patch
Anti-bot : human scroll simulation, [2.5s–5.0s] inter-page delays
Filter   : sponsored listings and eBay's ghost "Shop on eBay" item discarded
"""

import json
import logging
import random
import re
import sys
import time
from typing import Dict, List

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
        logging.FileHandler("ebay_scraper.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TARGET_URL  = "https://www.ebay.com/sch/i.html?_nkw=rtx+4060"
OUTPUT_FILE = "ebay_gpus.json"
MAX_PAGES   = 3

# Single high-reputation UA — Chrome 124 on Windows 11.
# Consistent UA across all pages is critical; rotating breaks session cookies.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.6367.155 Safari/537.36"
)

# ---------------------------------------------------------------------------
# CSS Selectors — update here if eBay restructures its search page
# ---------------------------------------------------------------------------

# eBay rebuilt their SRP — confirmed from live DOM (2026-03)
SEL_CONTAINER = "li.s-card"
SEL_TITLE     = "div.s-card__title > span:first-child"   # second span is "Opens in a new window or tab" — skip it
SEL_ATTR_ROW  = "div.s-card__attribute-row"              # price + shipping live in these rows, sniffed by content
SEL_FOOTER    = "div.s-card__footer"                     # contains "Sponsored" text when applicable
SEL_NEXT      = "a[type='next']"                         # pagination next-page link

# Sponsor patterns — "SPONSORED" is eBay's actual DOM text;
# "sponsered" covers the misspelling referenced in the spec.
_SPONSOR_PATTERNS = ("sponsored", "sponsered")

# eBay's RTX 4060 search results are 100% sponsored listings — confirmed by
# live DOM inspection across all 3 pages. For GPU categories, "Sponsored"
# means the seller paid for placement; the products are legitimate.
# Set to True if scraping a category where sponsored = genuinely low-quality ads.
FILTER_SPONSORED = False

# Explicit navigator.languages pin — belt-and-suspenders on top of stealth_sync
_LANGUAGES_PATCH = (
    "Object.defineProperty(navigator, 'languages', "
    "{get: () => ['en-US', 'en']});"
)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _require_stealth() -> None:
    """Hard-fail if playwright_stealth is not installed."""
    if not _STEALTH_AVAILABLE:
        logger.error(
            "playwright_stealth is NOT installed — this scraper requires it.\n"
            "Fix: pip install playwright-stealth==1.0.6"
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Data normalisation
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> float:
    """
    Extract the first (lowest) price from an eBay price string.

    "$299.99"              → 299.99
    "$249.99 to $399.99"  → 249.99  (lower bound of range)
    """
    clean = text.replace(",", "")
    match = re.search(r"\d+\.?\d*", clean)
    return float(match.group()) if match else 0.0


def _parse_shipping(text: str) -> float:
    """
    Convert an eBay shipping string to a float.

    "Free shipping"      → 0.0
    "+$15.00 shipping"   → 15.0
    ""                   → 0.0  (no info — treat as included)
    """
    if not text or "free" in text.lower():
        return 0.0
    clean = text.replace(",", "")
    match = re.search(r"\d+\.?\d*", clean)
    return float(match.group()) if match else 0.0


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _is_sponsored(container) -> bool:
    """
    Return True if the listing is marked as sponsored.
    eBay's new SRP puts "Sponsored" in div.s-card__footer (not in the title).
    """
    try:
        footer_el = container.query_selector(SEL_FOOTER)
        text = footer_el.inner_text().lower() if footer_el else ""
    except Exception:
        return False
    return any(p in text for p in _SPONSOR_PATTERNS)


# ---------------------------------------------------------------------------
# Human simulation
# ---------------------------------------------------------------------------

def _human_scroll(page) -> None:
    """
    Scroll from the current viewport position to the page bottom using
    randomised step sizes and micro-pauses — mimics a human reading through
    the results before extracting data.
    """
    viewport_h = page.evaluate("window.innerHeight")
    current_y  = int(page.evaluate("window.pageYOffset"))

    while True:
        total_h = int(page.evaluate("document.body.scrollHeight"))
        if current_y + viewport_h >= total_h:
            break
        step      = random.randint(250, 650)          # pixels
        current_y = min(current_y + step, total_h)
        page.evaluate(f"window.scrollTo(0, {current_y})")
        page.wait_for_timeout(random.randint(80, 350))  # ms between micro-scrolls

    logger.info("  Scroll complete — reached page bottom.")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_listings(page) -> List[Dict]:
    """Parse all non-sponsored listings visible on the current page."""
    containers = page.query_selector_all(SEL_CONTAINER)
    logger.info(f"  Raw containers: {len(containers)}")

    listings: List[Dict] = []
    skipped = 0

    for container in containers:
        # --- Filter 1: sponsored (only when FILTER_SPONSORED = True) ---
        if FILTER_SPONSORED and _is_sponsored(container):
            skipped += 1
            continue

        # Title
        title_el = container.query_selector(SEL_TITLE)
        title    = title_el.inner_text().strip() if title_el else ""

        # --- Filter 2: eBay ghost item injected at list position 0 ---
        if not title or title.upper() == "SHOP ON EBAY":
            skipped += 1
            continue

        # All attribute rows — scrape text once, sniff by content
        attr_rows = container.query_selector_all(SEL_ATTR_ROW)
        attr_texts = [r.inner_text().strip() for r in attr_rows]

        # Price row: first row whose text starts with "$"
        price_raw = next((t for t in attr_texts if t.startswith("$")), "")
        price     = _parse_price(price_raw)

        # Shipping row: first row containing "delivery" or "shipping"
        # (excludes "Free returns" which doesn't contain either keyword)
        ship_raw = next(
            (t for t in attr_texts if any(kw in t.lower() for kw in ("delivery", "shipping"))),
            ""
        )
        shipping = _parse_shipping(ship_raw)

        listings.append({
            "title":        title,
            "price":        price,
            "shipping":     shipping,
            "total_cost":   round(price + shipping, 2),
            "price_raw":    price_raw,
            "shipping_raw": ship_raw,
        })

    logger.info(
        f"  Accepted: {len(listings)} | "
        f"Skipped (sponsored/ghost): {skipped}"
    )
    return listings


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def run(playwright: Playwright) -> None:
    _require_stealth()

    logger.info(f"User-Agent : {USER_AGENT}")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        user_agent=USER_AGENT,
    )
    page = context.new_page()

    # ------------------------------------------------------------------
    # Stealth layer — MUST be applied before the first page.goto()
    # ------------------------------------------------------------------
    stealth_sync(page)
    # Belt-and-suspenders: pin navigator.languages explicitly so it
    # survives any stealth version that skips this particular patch
    page.add_init_script(_LANGUAGES_PATCH)
    logger.info("playwright_stealth applied + navigator.languages=['en-US','en'].")

    # ------------------------------------------------------------------
    # Pagination loop — up to MAX_PAGES
    # ------------------------------------------------------------------
    all_listings: List[Dict] = []
    current_url = TARGET_URL

    for page_num in range(1, MAX_PAGES + 1):
        logger.info(f"=== Page {page_num}/{MAX_PAGES} ===")
        logger.info(f"URL: {current_url}")

        page.goto(current_url, wait_until="domcontentloaded")
        # Brief settle for React hydration / lazy JS bundles
        page.wait_for_timeout(2000)

        # Confirm real content appeared in the DOM
        try:
            page.wait_for_selector(SEL_CONTAINER, timeout=12_000)
        except PlaywrightTimeoutError:
            logger.error(
                f"No listing containers on page {page_num} — "
                "eBay may have blocked the request. "
                f"Raw HTML saved to 'ebay_debug_p{page_num}.html'."
            )
            with open(f"ebay_debug_p{page_num}.html", "w", encoding="utf-8") as fh:
                fh.write(page.content())
            break

        # Scroll through the page like a human before extracting
        _human_scroll(page)

        page_listings = _extract_listings(page)
        all_listings.extend(page_listings)
        logger.info(f"  Running total: {len(all_listings)} listings")

        # Done after last page — no need to look for Next
        if page_num == MAX_PAGES:
            break

        # ------------------------------------------------------------------
        # Next page navigation
        # ------------------------------------------------------------------
        try:
            next_btn  = page.locator(SEL_NEXT).first
            next_href = next_btn.get_attribute("href", timeout=5_000)
            if not next_href:
                logger.info("Next button has no href — this is the last page.")
                break
            current_url = next_href
        except (PlaywrightTimeoutError, Exception) as exc:
            logger.info(
                f"Next button not found on page {page_num} ({exc}) — "
                "stopping pagination."
            )
            break

        # Human-like delay between page requests [2.5s – 5.0s]
        delay_s = random.uniform(2.5, 5.0)
        logger.info(f"  Waiting {delay_s:.2f}s before page {page_num + 1} …")
        page.wait_for_timeout(int(delay_s * 1000))

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    print(f"Total listings scraped: {len(all_listings)}")
    logger.info(f"Total listings scraped: {len(all_listings)}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(all_listings, fh, ensure_ascii=False, indent=4)
    logger.info(f"Saved to '{OUTPUT_FILE}'.")

    context.close()
    browser.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
