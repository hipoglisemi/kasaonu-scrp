import os
import sys
sys.path.append(os.path.abspath('.'))

from src.scrapers.on_digital import ONDigitalScraper
from bs4 import BeautifulSoup

scraper = ONDigitalScraper()
scraper.setup_driver()

url = "https://on.com.tr/king-kampanyasi"
scraper.driver.get(url)

import time
time.sleep(3)
for frac in [0.33, 0.66, 1.0]:
    scraper.driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {frac});")
    time.sleep(1)

soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')

print("=== ALL .raw-data ELEMENTS ===")
for i, el in enumerate(soup.select('.raw-data')):
    print(f"[{i}]: {el.get_text(separator=' ', strip=True)[:100]}...")

print("\n=== ALL .box-content ELEMENTS ===")
for i, el in enumerate(soup.select('.box-content')):
    print(f"[{i}]: {el.get_text(separator=' ', strip=True)[:100]}...")

print("\n=== FINDING 'Kampanya Detayları' h2 ===")
for h2 in soup.select('h2'):
    if 'Kampanya Detayları'.lower() in h2.get_text().lower():
        print(f"Found h2: {h2.get_text()}")
        parent = h2.find_parent()
        print(f"Parent tag: {parent.name}, classes: {parent.get('class')}")
        ul = parent.find('ul')
        if ul:
            print(f"Found ul within parent, has {len(ul.find_all('li'))} items")

scraper.close_driver()
