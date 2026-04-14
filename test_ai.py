import requests
from bs4 import BeautifulSoup
import os, sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.services.ai_parser import AIParser
import json

url = "https://totalenergiesistasyonlari.com.tr/kampanyalar/club-totalenergies-ten-dogum-gununuze-ozel-10-tl-yakit-puan-hediye/"
resp = requests.get(url, verify=False)
html = resp.text

parser = AIParser()
result = parser.parse_campaign_data(html, title="Doğum Günü", bank_name="Genel", tracking_url=url, force=True)
print(json.dumps(result, indent=2, ensure_ascii=False))
