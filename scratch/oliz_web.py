import requests
from bs4 import BeautifulSoup
import json

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
try:
    r = requests.get('https://oliz.com.tr/oliz_avantajlari', headers=headers, verify=False)
    soup = BeautifulSoup(r.text, 'html.parser')
    scripts = soup.find_all('script')
    for s in scripts:
        if s.string and 'campaign' in s.string.lower():
            print("Found campaign data in script!")
    
    # Try fetching via web api if they have one
    r_api = requests.get('https://oliz.com.tr/api/campaigns', headers=headers, verify=False)
    print(f"Web API Status: {r_api.status_code}")
except Exception as e:
    print(e)
