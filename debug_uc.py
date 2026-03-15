"""Debug: screenshot with undetected_chromedriver"""
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time

options = uc.ChromeOptions()
options.add_argument('--window-size=1920,1080')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = uc.Chrome(options=options, headless=True, use_subprocess=True, version_main=144)
driver.get('https://scrapingclub.com/exercise/list_infinite_scroll/')
time.sleep(5)

driver.save_screenshot('debug_uc.png')
print(f"Title: {driver.title}")
print(f"URL:   {driver.current_url}")
posts = driver.find_elements(By.CSS_SELECTOR, 'div.post')
print(f"div.post count: {len(posts)}")
print(f"Source length: {len(driver.page_source)}")
print("\nFirst 1500 chars of source:")
print(driver.page_source[:1500])

driver.quit()
