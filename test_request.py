"""Direct test of make_request_with_retry"""
import sys
sys.path.append('.')
from scraper import make_request_with_retry
from bs4 import BeautifulSoup

url = 'https://books.toscrape.com/'
print(f"Testing make_request_with_retry with: {url}\n")

response = make_request_with_retry(url)

if response:
    print(f"Response received:")
    print(f"  Status code: {response.status_code}")
    print(f"  Encoding: {response.encoding}")
    print(f"  Content length: {len(response.content)}")
    print(f"  Text length: {len(response.text)}")

    # Try parsing
    soup = BeautifulSoup(response.text, 'html.parser')
    articles = soup.select('article.product_pod')
    print(f"\n  Articles found with soup.select('article.product_pod'): {len(articles)}")

    # Show first 500 chars
    print(f"\n  First 500 chars of response.text:")
    print(response.text[:500])
else:
    print("ERROR: No response received!")
