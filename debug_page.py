"""Debug: screenshot what the headless browser actually loads"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1920,1080')
options.add_argument(
    'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

driver = webdriver.Chrome(options=options)
driver.get('https://scrapingclub.com/exercise/list_infinite_scroll/')
time.sleep(5)

# Save screenshot
driver.save_screenshot('debug_screenshot.png')
print(f"Page title: {driver.title}")
print(f"Current URL: {driver.current_url}")

# Count elements
posts = driver.find_elements(By.CSS_SELECTOR, 'div.post')
print(f"div.post count: {len(posts)}")

# Dump the first 3000 chars of page source
source = driver.page_source
print(f"\nPage source length: {len(source)}")
print("\nFirst 2000 chars of page source:")
print(source[:2000])

driver.quit()
