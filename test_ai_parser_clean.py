import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.services.ai_parser import AIParser
import requests
from bs4 import BeautifulSoup

url = "https://totalenergiesistasyonlari.com.tr/kampanyalar/club-totalenergies-ten-dogum-gununuze-ozel-10-tl-yakit-puan-hediye/"
resp = requests.get(url, verify=False)
html = resp.text

parser = AIParser()
cleaned = parser._clean_text(html)
print("--- CLEANED TEXT START ---")
print(cleaned)
print("--- CLEANED TEXT END ---")
print("Length:", len(cleaned))
