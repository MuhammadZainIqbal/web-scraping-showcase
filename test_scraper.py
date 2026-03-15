"""Test the actual scrape_page function"""
import sys
sys.path.append('.')
from scraper import scrape_page, logger
import logging

# Set logging to DEBUG to see more details
logger.setLevel(logging.DEBUG)

url = 'https://books.toscrape.com/'
print(f"Testing scrape_page function with: {url}\n")

products, next_url = scrape_page(url)

print(f"\nResults:")
print(f"  Products found: {len(products)}")
print(f"  Next URL: {next_url}")

if products:
    print(f"\nFirst product:")
    import json
    print(json.dumps(products[0], indent=2))
