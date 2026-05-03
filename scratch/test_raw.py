import sys
import os

project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.ai_parser_golden import AIParserGolden
import requests
from bs4 import BeautifulSoup

url = "https://www.wingscard.com.tr/kampanyalar/bridgestoneda-taksit-firsati"
response = requests.get(url, timeout=20)
soup = BeautifulSoup(response.content, 'html.parser')

body_el = soup.find("body")
raw_html = str(body_el) if body_el else str(soup)

parser = AIParserGolden()
result = parser.parse_campaign(raw_html, bank_name="Akbank", title="Wings")
print("AI RAW RESULT:", result.get('cards'))
