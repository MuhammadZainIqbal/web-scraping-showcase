"""Debug script to check exact product structure"""
import requests
from bs4 import BeautifulSoup

url = 'https://books.toscrape.com/'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, 'html.parser')  # Using response.text instead
articles = soup.select('article.product_pod')

print(f"Found {len(articles)} products\n")

if articles:
    first = articles[0]
    print("="*50)
    print("FIRST PRODUCT FULL HTML:")
    print("="*50)
    print(first.prettify())
    print("\n" + "="*50)
    print("DATA EXTRACTION TEST:")
    print("="*50)

    # Test title extraction
    title_elem = first.select_one('h3 > a')
    print(f"Title element found: {title_elem is not None}")
    if title_elem:
        print(f"  - href: {title_elem.get('href')}")
        print(f"  - title attribute: {title_elem.get('title')}")
        print(f"  - text content: {title_elem.get_text(strip=True)}")

    # Test price
    price_elem = first.select_one('p.price_color')
    print(f"\nPrice element found: {price_elem is not None}")
    if price_elem:
        print(f"  - text: {price_elem.get_text(strip=True)}")

    # Test availability
    avail_elem = first.select_one('p.instock.availability')
    print(f"\nAvailability element found: {avail_elem is not None}")
    if avail_elem:
        print(f"  - text: {avail_elem.get_text(strip=True)}")
