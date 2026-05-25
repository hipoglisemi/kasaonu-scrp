import urllib.request
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.text_cleaner import clean_campaign_text

url = "https://www.teb.com.tr/sizin-icin/beymen-6/"

try:
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        
    cleaned = clean_campaign_text(html, title="Beymen'de 6 Taksit!")
    
    print("--- CLEANED TEXT OUTPUT ---")
    print(f"Total Character Count: {len(cleaned)}")
    print("-" * 60)
    print(cleaned)
    print("-" * 60)
    
    # Check if header or footer noise is still present
    has_header_noise = "ARAMAYI KAPAT" in cleaned or "Hızlı Ürün Erişimi" in cleaned
    has_footer_noise = "Zaman Aşımı Sorgulama" in cleaned or "TEB Kariyer" in cleaned
    
    print(f"Header Noise Present: {has_header_noise}")
    print(f"Footer Noise Present: {has_footer_noise}")
except Exception as e:
    print(f"❌ Error: {e}")
