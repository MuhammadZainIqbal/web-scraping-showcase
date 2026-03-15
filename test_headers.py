"""Test different header configurations"""
import requests
from bs4 import BeautifulSoup

url = 'https://books.toscrape.com/'

# Test 1: Full headers from scraper.py
headers_full = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Referer': 'https://www.google.com/'
}

# Test 2: Simple headers
headers_simple = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

print("Test 1: Full headers")
print("=" * 50)
response1 = requests.get(url, headers=headers_full)
print(f"Status: {response1.status_code}")
print(f"Content length: {len(response1.content)}")
soup1 = BeautifulSoup(response1.text, 'html.parser')
articles1 = soup1.select('article.product_pod')
print(f"Articles found: {len(articles1)}")

print("\nTest 2: Simple headers")
print("=" * 50)
response2 = requests.get(url, headers=headers_simple)
print(f"Status: {response2.status_code}")
print(f"Content length: {len(response2.content)}")
soup2 = BeautifulSoup(response2.text, 'html.parser')
articles2 = soup2.select('article.product_pod')
print(f"Articles found: {len(articles2)}")

print("\nTest 3: No headers")
print("=" * 50)
response3 = requests.get(url)
print(f"Status: {response3.status_code}")
print(f"Content length: {len(response3.content)}")
soup3 = BeautifulSoup(response3.text, 'html.parser')
articles3 = soup3.select('article.product_pod')
print(f"Articles found: {len(articles3)}")
