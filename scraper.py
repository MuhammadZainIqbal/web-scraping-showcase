"""
Production-Grade Web Scraper for books.toscrape.com
Author: Senior Data Engineer
Description: Modular scraper with pagination, retry logic, rate limiting, and comprehensive logging
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import logging
import re
from typing import List, Dict, Optional
from urllib.parse import urljoin


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_headers() -> Dict[str, str]:
    """
    Returns a headers dictionary to mimic a legitimate Chrome browser session.
    Using minimal but effective headers - some sites reject overly complex header combinations.
    """
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9'
    }


def make_request_with_retry(url: str, max_retries: int = 3, timeout: int = 10) -> Optional[requests.Response]:
    """
    Makes an HTTP GET request with retry logic for 5xx errors and timeouts.

    Args:
        url: The URL to fetch
        max_retries: Maximum number of retry attempts
        timeout: Request timeout in seconds

    Returns:
        Response object if successful, None otherwise
    """
    headers = get_headers()

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)

            # Check for successful response
            if response.status_code == 200:
                return response

            # Handle 5xx server errors with retry
            elif 500 <= response.status_code < 600:
                logger.warning(f"Server error {response.status_code} on attempt {attempt}/{max_retries} for {url}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    logger.error(f"Max retries reached for {url}. Status code: {response.status_code}")
                    return None

            # Handle other non-200 status codes
            else:
                logger.error(f"Request failed with status code {response.status_code} for {url}")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt}/{max_retries} for {url}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            else:
                logger.error(f"Max retries reached due to timeout for {url}")
                return None

        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error on attempt {attempt}/{max_retries} for {url}: {str(e)}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            else:
                logger.error(f"Max retries reached due to connection error for {url}")
                return None

        except Exception as e:
            logger.error(f"Unexpected error for {url}: {str(e)}")
            return None

    return None


def clean_price(price_text: str) -> float:
    """
    Cleans the price field by removing currency symbols and converting to float.

    Args:
        price_text: Raw price string (e.g., "£51.77")

    Returns:
        Price as float
    """
    try:
        # Remove all non-numeric characters except decimal point
        # This handles £, �, and any other currency symbols or encoding issues
        cleaned_price = re.sub(r'[^\d.]', '', price_text.strip())
        return float(cleaned_price) if cleaned_price else 0.0
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse price '{price_text}': {str(e)}")
        return 0.0


def clean_availability(availability_text: str) -> str:
    """
    Cleans the availability field by removing excess whitespace and newlines.

    Args:
        availability_text: Raw availability string

    Returns:
        Cleaned availability string
    """
    return ' '.join(availability_text.split()).strip()


def extract_product_data(article, base_url: str) -> Optional[Dict[str, any]]:
    """
    Extracts product data from a single article.product_pod element.
    Uses relative CSS selectors for structural stability.

    Args:
        article: BeautifulSoup article element
        base_url: Base URL for constructing absolute URLs

    Returns:
        Dictionary containing product data or None if extraction fails
    """
    try:
        # Extract title from the title attribute of h3 > a
        # Using CSS selector for stability
        title_element = article.select_one('h3 > a')
        title = title_element.get('title', '').strip() if title_element else ''

        # Extract and clean price from p.price_color
        price_element = article.select_one('p.price_color')
        price_text = price_element.get_text(strip=True) if price_element else '£0.00'
        price = clean_price(price_text)

        # Extract and clean availability from p.instock.availability
        availability_element = article.select_one('p.instock.availability')
        availability_text = availability_element.get_text(strip=True) if availability_element else 'Unknown'
        availability = clean_availability(availability_text)

        # Extract product URL and construct absolute path
        # Using h3 > a href attribute
        url_element = article.select_one('h3 > a')
        relative_url = url_element.get('href', '') if url_element else ''
        product_url = urljoin(base_url, relative_url)

        return {
            'title': title,
            'price': price,
            'availability': availability,
            'product_url': product_url
        }

    except Exception as e:
        logger.error(f"Failed to extract product data: {str(e)}")
        return None


def scrape_page(url: str) -> tuple[List[Dict[str, any]], Optional[str]]:
    """
    Scrapes a single page and extracts all product data.

    Args:
        url: The URL of the page to scrape

    Returns:
        Tuple of (list of product dictionaries, next page URL or None)
    """
    products = []

    response = make_request_with_retry(url)
    if not response:
        return products, None

    # Use response.text to let requests handle encoding properly (ISO-8859-1)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find all product containers using CSS selector
    product_containers = soup.select('article.product_pod')

    if not product_containers:
        logger.warning(f"No product containers found on {url}")
        return products, None

    # Extract data from each product
    for article in product_containers:
        product_data = extract_product_data(article, url)
        if product_data:
            products.append(product_data)

    # Check for next page using li.next > a selector
    next_button = soup.select_one('li.next > a')
    next_page_url = None

    if next_button:
        relative_next_url = next_button.get('href', '')
        next_page_url = urljoin(url, relative_next_url)

    return products, next_page_url


def scrape_all_pages(start_url: str) -> List[Dict[str, any]]:
    """
    Scrapes all pages starting from the given URL, following pagination automatically.
    Implements rate limiting between requests.

    Args:
        start_url: The starting URL to begin scraping

    Returns:
        List of all product dictionaries from all pages
    """
    all_products = []
    current_url = start_url
    page_number = 1

    while current_url:
        logger.info(f"Scraping page {page_number}...")

        products, next_page_url = scrape_page(current_url)

        if products:
            all_products.extend(products)
            logger.info(f"Extracted {len(products)} products from page {page_number}. Total: {len(all_products)}")
        else:
            logger.warning(f"No products extracted from page {page_number}")

        # Move to next page
        current_url = next_page_url
        page_number += 1

        # Rate limiting: sleep for 1 second between requests
        if current_url:
            time.sleep(1)

    logger.info(f"Scraping completed. Total products extracted: {len(all_products)}")
    return all_products


def save_to_json(data: List[Dict[str, any]], filename: str = 'books_data.json') -> None:
    """
    Saves the scraped data to a UTF-8 encoded JSON file.

    Args:
        data: List of product dictionaries
        filename: Output filename
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"Data successfully saved to {filename}")
    except Exception as e:
        logger.error(f"Failed to save data to {filename}: {str(e)}")


def main():
    """
    Main execution block for the scraper.
    """
    logger.info("Starting web scraping process...")

    # Target URL
    start_url = 'https://books.toscrape.com/'

    # Scrape all pages
    all_books = scrape_all_pages(start_url)

    # Save to JSON
    if all_books:
        save_to_json(all_books, 'books_data.json')
        logger.info(f"Scraping completed successfully. Total books: {len(all_books)}")
    else:
        logger.error("No data was scraped. Please check the logs for errors.")


if __name__ == '__main__':
    main()
