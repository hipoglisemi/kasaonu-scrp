import os
import sys
import json
import urllib3
import requests
from bs4 import BeautifulSoup
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign
from src.services.ai_parser_golden import parse_api_campaign

SUSPICIOUS_IDS = [
    19272, # Akbank Dyson
    19351, # Dünya Katılım Koton
    19463, # Türk Telekom Sil Süpür
    19367, # VakıfBank Akaryakıt
    15822, # Opet Kasko
    19283, # Halkbank Antalya TROY
    12103, # Halkbank Bitaksi
    18782, # Halkbank Premium Yurt Dışı
    12106, # Halkbank Bitaksi Parafly
]

def clean_html_content(html: str, bank_name: str) -> str:
    """Temiz ve gürültüsüz html içeriği çeker (paraf.py veya akbank.py gibi)."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove script and style
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()
        
    text = soup.get_text(separator="\n", strip=True)
    return text[:8000]

def repair_suspicious_campaigns():
    print("🚀 Starting Suspicious Date-Extended Campaigns Repair...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    with get_db_session() as db:
        campaigns = db.query(Campaign).filter(Campaign.id.in_(SUSPICIOUS_IDS)).all()
        
        for c in campaigns:
            print(f"\n🔎 Inspecting ID: #{c.id} | {c.title[:50]}...")
            print(f"   Current DB Dates: {c.start_date} -> {c.end_date}")
            print(f"   URL: {c.tracking_url}")
            
            try:
                # Fetch fresh page HTML
                r = requests.get(c.tracking_url, headers=headers, verify=False, timeout=20)
                if r.status_code != 200:
                    print(f"   ❌ HTTP status {r.status_code}, skipping.")
                    continue
                    
                clean_text = clean_html_content(r.text, "")
                
                # Parse strictly with Gemini
                print(f"   🧠 Parsing content with Gemini parser...")
                ai_data = parse_api_campaign(
                    title=c.title,
                    short_description=None,
                    content_html=clean_text,
                    bank_name="Audit",
                    scraper_sector=None,
                    tracking_url=c.tracking_url,
                    og_title=None
                )
                
                if not ai_data or ai_data.get("error"):
                    print("   ⚠️  AI parser could not extract dates.")
                    continue
                    
                real_start = ai_data.get("start_date")
                real_end = ai_data.get("end_date")
                
                print(f"   🎯 Gemini Parsed Dates: {real_start} -> {real_end}")
                
                if real_start or real_end:
                    # Update database with correct official dates
                    c.start_date = real_start if real_start else c.start_date
                    c.end_date = real_end if real_end else c.end_date
                    c.is_approved = False # Require manual validation
                    
                    # If end date is in the past, deactivate it immediately
                    if real_end:
                        end_dt = datetime.strptime(real_end, "%Y-%m-%d").date()
                        today = datetime.now().date()
                        if end_dt < today:
                            c.is_active = False
                            print(f"   💤 Campaign expired on {real_end}, deactivating (is_active=False)")
                            
                    print(f"   ✅ DB successfully repaired for ID: #{c.id}!")
                else:
                    print("   ⚠️  No valid dates found in parsing, DB untouched.")
                    
            except Exception as ex:
                print(f"   ❌ Repair exception: {ex}")
                
        db.commit()
    print("\n🏁 Repair completed and DB changes committed!")

if __name__ == "__main__":
    repair_suspicious_campaigns()
