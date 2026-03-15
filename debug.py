"""Quick debug script to check HTML structure"""
import requests
from bs4 import BeautifulSoup

url = 'https://books.toscrape.com/'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

response = requests.get(url, headers=headers)
print(f"Status Code: {response.status_code}")
print(f"Encoding: {response.encoding}")
print(f"Content length: {len(response.content)}")
print("\n" + "="*50)
print("First 2000 characters of HTML:")
print("="*50)
print(response.text[:2000])
print("\n" + "="*50)

# Try parsing with different parsers
soup = BeautifulSoup(response.content, 'html.parser')
articles = soup.select('article.product_pod')
print(f"\nFound {len(articles)} article.product_pod elements")

# Check if there are any articles at all
all_articles = soup.find_all('article')
print(f"Found {len(all_articles)} total article elements")

# Check for product containers with different selectors
print(f"\nTrying alternative selectors:")
print(f"article: {len(soup.select('article'))}")
print(f".product_pod: {len(soup.select('.product_pod'))}")

# Print first article if found
if all_articles:
    print("\n" + "="*50)
    print("First article element:")
    print("="*50)
    print(all_articles[0].prettify()[:500])
