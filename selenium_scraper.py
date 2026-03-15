"""
Production-Grade Infinite Scroll Scraper
Target: https://scrapingclub.com/exercise/list_infinite_scroll/
Description: Class-based Selenium scraper with headless Chrome, lazy-load handling,
             real-time CSV append, and graceful error handling.
"""

import csv
import logging
import os
import time
from typing import Dict, List, Set

import undetected_chromedriver as uc
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# Configure logging: outputs to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('selenium_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Known item ceiling for this exercise — used as a hard stop
KNOWN_ITEM_LIMIT = 60


class InfiniteScrollScraper:
    """
    Selenium scraper for infinite-scroll pages using a class-based structure.
    Implements the context manager protocol to guarantee WebDriver cleanup.
    """

    def __init__(self, url: str, output_file: str, item_limit: int = KNOWN_ITEM_LIMIT):
        self.url = url
        self.output_file = output_file
        self.item_limit = item_limit
        self.driver: uc.Chrome = None
        # Tracks names of already-processed items to prevent duplicate CSV rows
        self._seen_names: Set[str] = set()

    def __enter__(self) -> 'InfiniteScrollScraper':
        self.driver = self._configure_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed cleanly.")
        # Return False to never suppress exceptions from the with-block
        return False

    # ------------------------------------------------------------------
    # Driver configuration
    # ------------------------------------------------------------------

    def _configure_driver(self) -> uc.Chrome:
        """
        Builds a Chrome instance using undetected_chromedriver.

        NOTE: headless=False is intentional.
        scrapingclub.com performs a server-side headless-browser check and
        hard-redirects ANY headless Chrome (including the new headless mode and
        undetected_chromedriver) to adorarama.com before the page renders.
        Running in visible mode with a minimised window is the only reliable
        bypass short of using a residential proxy.  The window opens, collects
        all 60 items, and closes automatically.
        """
        options = uc.ChromeOptions()

        # Realistic User-Agent to mimic an authentic browser session
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-minimized')   # Minimised — stays out of the way
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        # headless=False — required because scrapingclub.com blocks all headless agents
        driver = uc.Chrome(options=options, headless=False, use_subprocess=True, version_main=144)

        logger.info("Visible Chrome (minimised) configured and launched.")
        return driver

    # ------------------------------------------------------------------
    # Page interaction helpers
    # ------------------------------------------------------------------

    def _wait_for_initial_load(self):
        """
        Blocks until at least one div.post is present in the DOM.
        Raises TimeoutException (caught in run()) if the page never loads.
        """
        logger.info("Waiting for initial page content...")
        WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.post'))
        )
        logger.info("Initial content confirmed in DOM.")

    def _scroll_to_bottom(self):
        """
        Scrolls to the very bottom of the page via JavaScript to trigger
        the AJAX call, then waits 2 seconds for the DOM to populate.
        """
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # Deliberate pause — AJAX needs time to append new nodes

    def _scroll_element_into_view(self, element) -> bool:
        """
        Scrolls a specific element into the visible viewport.
        This is the critical step that forces lazy-loaded images to set their src.

        Args:
            element: The WebElement to bring into view.

        Returns:
            True on success, False if the scroll itself raised an exception.
        """
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(0.4)  # Short pause to let the browser trigger the lazy-load
            return True
        except Exception as e:
            logger.warning(f"scrollIntoView failed: {e}")
            return False

    def _get_item_count(self) -> int:
        """Returns the live count of div.post nodes currently in the DOM."""
        return len(self.driver.find_elements(By.CSS_SELECTOR, 'div.post'))

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    def _extract_new_items(self) -> List[Dict[str, str]]:
        """
        Iterates over every div.post container currently in the DOM and extracts
        name, price, and image URL for items not yet seen.

        Lazy-loaded images are handled by calling scrollIntoView() before reading
        the src attribute — this forces the browser to load the actual image URL.

        Returns:
            List of dicts for items not yet recorded in self._seen_names.
        """
        new_items: List[Dict[str, str]] = []

        try:
            containers = self.driver.find_elements(By.CSS_SELECTOR, 'div.post')
        except NoSuchElementException:
            logger.warning("find_elements returned nothing for 'div.post'.")
            return new_items

        for container in containers:
            try:
                # --- Item name: h4 > a text ---
                name_el = container.find_element(By.CSS_SELECTOR, 'h4 > a')
                name = name_el.text.strip()

                # Skip duplicates — we may re-scan already-saved items on each pass
                if name in self._seen_names:
                    continue

                # --- Price: h5 text ---
                try:
                    price = container.find_element(By.CSS_SELECTOR, 'h5').text.strip()
                except NoSuchElementException:
                    price = 'N/A'
                    logger.warning(f"Price element missing for: {name}")

                # --- Image URL: scroll into view first, then read src ---
                # img.card-img-top may have an empty src until it enters the viewport
                try:
                    img_el = container.find_element(By.CSS_SELECTOR, 'img.card-img-top')
                    self._scroll_element_into_view(img_el)
                    image_url = img_el.get_attribute('src') or ''
                except NoSuchElementException:
                    image_url = ''
                    logger.warning(f"Image element missing for: {name}")

                new_items.append({
                    'name': name,
                    'price': price,
                    'image_url': image_url
                })
                self._seen_names.add(name)

            except NoSuchElementException as e:
                logger.error(f"Skipping malformed container — missing element: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error extracting item: {e}")
                continue

        return new_items

    # ------------------------------------------------------------------
    # CSV output
    # ------------------------------------------------------------------

    def _save_to_csv(self, items: List[Dict[str, str]]):
        """
        Appends a batch of items to the output CSV file immediately.
        This real-time write strategy ensures data is preserved even if
        the script crashes mid-run.

        Headers are written only once — when the file is first created.
        UTF-8 encoding is enforced to correctly handle non-ASCII characters.

        Args:
            items: List of product dicts to append.
        """
        if not items:
            return

        # Detect whether the file already has content to avoid duplicate headers
        write_header = not (
            os.path.isfile(self.output_file) and os.path.getsize(self.output_file) > 0
        )
        fieldnames = ['name', 'price', 'image_url']

        with open(self.output_file, 'a', newline='', encoding='utf-8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerows(items)

        logger.info(f"Appended {len(items)} new rows to '{self.output_file}'.")

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    def run(self):
        """
        Orchestrates the full scrape:
          1. Loads the page and waits for initial content.
          2. Enters the infinite scroll loop.
          3. After each scroll, extracts and saves any new items.
          4. Terminates when the item count plateaus or the known limit is hit.
          5. Performs one final extraction pass to catch the last-loaded batch.
        """
        logger.info(f"Navigating to: {self.url}")
        self.driver.get(self.url)

        try:
            self._wait_for_initial_load()
        except TimeoutException:
            logger.error("Timed out waiting for initial div.post — aborting run.")
            return

        previous_count = 0

        while True:
            current_count = self._get_item_count()
            logger.info(f"DOM item count: {current_count} | Saved: {len(self._seen_names)}")

            # --- Termination condition 1: reached the known page ceiling ---
            if current_count >= self.item_limit:
                logger.info(
                    f"Item limit of {self.item_limit} reached. Stopping scroll loop."
                )
                break

            # --- Termination condition 2: DOM count stopped growing ---
            if current_count == previous_count and previous_count > 0:
                logger.info("DOM count unchanged after scroll — page exhausted.")
                break

            # Extract and immediately persist any new items in this batch
            new_items = self._extract_new_items()
            if new_items:
                self._save_to_csv(new_items)

            previous_count = current_count
            self._scroll_to_bottom()

        # Final pass: captures the last batch loaded by the terminal scroll
        logger.info("Running final extraction pass on fully-loaded DOM...")
        final_items = self._extract_new_items()
        if final_items:
            self._save_to_csv(final_items)

        logger.info(
            f"Scraping complete. Total unique items saved: {len(self._seen_names)}"
        )


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main():
    """Configures paths and launches the scraper inside a context manager."""
    target_url = 'https://scrapingclub.com/exercise/list_infinite_scroll/'
    output_file = 'scraped_products.csv'

    # Clear any previous run's output for a clean result
    if os.path.exists(output_file):
        os.remove(output_file)
        logger.info(f"Removed existing '{output_file}' for a clean run.")

    with InfiniteScrollScraper(url=target_url, output_file=output_file) as scraper:
        scraper.run()


if __name__ == '__main__':
    main()
