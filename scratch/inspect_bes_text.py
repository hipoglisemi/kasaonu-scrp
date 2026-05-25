import urllib.request
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.text_cleaner import clean_campaign_text

url = "https://www.teb.com.tr/sizin-icin/bes-3-taksit/"

try:
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        
    cleaned = clean_campaign_text(html, title="TEB Kredi Kartlarınızla BES Ödemelerinize Faizsiz 3 Taksit!")
    
    print("====== CLEANED LIVE TEXT ======")
    print(cleaned)
except Exception as e:
    print(f"❌ Error: {e}")
