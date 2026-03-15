"""
Production-Grade Infinite Scroll Scraper — Playwright + Stealth Layer
Target: https://quotes.toscrape.com/scroll
Description: Scrolls to the bottom of an AJAX-driven infinite scroll page,
             extracts all quotes (text + author), prints the total count,
             and saves results to quotes.json.

Stealth Layer:
  - Random User-Agent rotation (Chrome / Firefox / Safari on Windows & Mac)
  - playwright_stealth (if installed) or manual navigator.webdriver patch
  - Realistic viewport (1920x1080) and locale (en-US)
  - Human-like randomised scroll delays [1.5s – 3.5s]
"""

import json
import logging
import random

from playwright.sync_api import Playwright, sync_playwright

# Optional stealth plugin — gracefully degrade if not installed
try:
    from playwright_stealth import stealth_sync
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Logging: console + file
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('playwright_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stealth constants
# ---------------------------------------------------------------------------

# Modern browser User-Agents — Chrome, Firefox, Safari across Windows & Mac
USER_AGENTS = [
    # Chrome 124 — Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 124 — macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox 125 — Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Firefox 125 — macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari 17 — macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge 124 — Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# Fallback JS patch injected before any page script runs
_WEBDRIVER_PATCH = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
"""

# Hard ceiling on scroll attempts
MAX_SCROLLS = 10


# ---------------------------------------------------------------------------
# Core scraper function
# ---------------------------------------------------------------------------

def run(playwright: Playwright) -> None:
    selected_ua = random.choice(USER_AGENTS)
    logger.info(f"Selected User-Agent: {selected_ua}")
    logger.info(f"playwright_stealth available: {_STEALTH_AVAILABLE}")

    browser = playwright.chromium.launch(headless=False)

    # Realistic context — viewport, locale, and UA set here so they apply
    # to every request/response in the context (including navigation headers)
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        user_agent=selected_ua,
    )

    page = context.new_page()

    # ------------------------------------------------------------------
    # Stealth patches — applied before page.goto so they fire on load
    # ------------------------------------------------------------------
    if _STEALTH_AVAILABLE:
        # playwright_stealth patches: webdriver flag, chrome runtime object,
        # permissions API, plugin arrays, language headers, and more.
        stealth_sync(page)
        logger.info("playwright_stealth patches applied.")
    else:
        # Minimal manual fallback: hide the navigator.webdriver flag that
        # Playwright exposes by default in automation contexts.
        page.add_init_script(_WEBDRIVER_PATCH)
        logger.info("Manual navigator.webdriver=undefined patch applied (fallback).")

    logger.info("Navigating to https://quotes.toscrape.com/scroll")
    page.goto("https://quotes.toscrape.com/scroll")

    # ------------------------------------------------------------------
    # Infinite scroll loop
    # Terminates when:
    #   (a) document.body.scrollHeight stops increasing — no more content, OR
    #   (b) MAX_SCROLLS is reached — safety ceiling
    # ------------------------------------------------------------------

    scroll_count = 0

    while scroll_count < MAX_SCROLLS:
        # Snapshot the height BEFORE scrolling
        height_before: int = page.evaluate("document.body.scrollHeight")

        # Human-like randomised delay keeps inter-scroll timing unpredictable
        delay_s = random.uniform(1.5, 3.5)
        logger.info(
            f"Scroll {scroll_count + 1}/{MAX_SCROLLS} — "
            f"height: {height_before}px — next wait: {delay_s:.2f}s"
        )

        # Scroll to the very bottom to trigger the AJAX load
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # Wait — randomised to mimic human reading/scrolling pace
        page.wait_for_timeout(int(delay_s * 1000))

        scroll_count += 1

        # Snapshot height AFTER the wait and compare
        height_after: int = page.evaluate("document.body.scrollHeight")

        if height_after == height_before:
            logger.info(
                "Page height unchanged after scroll — no more content. "
                "Stopping scroll loop."
            )
            break

    else:
        logger.info(f"Reached maximum scroll limit of {MAX_SCROLLS}. Stopping.")

    # ------------------------------------------------------------------
    # Data extraction — runs once on the fully-loaded DOM
    # ------------------------------------------------------------------

    quotes = []
    containers = page.query_selector_all("div.quote")

    for container in containers:
        text_el = container.query_selector("span.text")
        author_el = container.query_selector("small.author")

        text = text_el.inner_text().strip() if text_el else ""
        author = author_el.inner_text().strip() if author_el else ""

        quotes.append({"text": text, "author": author})

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    print(f"Total quotes found: {len(quotes)}")
    logger.info(f"Total quotes extracted: {len(quotes)}")

    output_file = "quotes.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(quotes, f, ensure_ascii=False, indent=4)

    logger.info(f"Results saved to '{output_file}'.")

    context.close()
    browser.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
