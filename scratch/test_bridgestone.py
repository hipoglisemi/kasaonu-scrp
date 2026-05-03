import sys
import os

project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.ai_parser_golden import parse_api_campaign
from bs4 import BeautifulSoup
import requests

url = "https://www.wingscard.com.tr/kampanyalar/bridgestoneda-taksit-firsati"
response = requests.get(url, timeout=20)
soup = BeautifulSoup(response.content, 'html.parser')
title = soup.select_one('h2.pageTitle')
title = title.get_text(strip=True) if title else "Kampanya"

body_el = soup.find("body")
raw_html = str(body_el) if body_el else str(soup)

ai_data = parse_api_campaign(
    title=title,
    short_description=title,
    content_html=raw_html,
    bank_name="Akbank",
    scraper_sector=None,
    tracking_url=url,
    force=True
)

print(ai_data.get('cards'))
