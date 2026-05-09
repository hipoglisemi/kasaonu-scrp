import os
import sys
import time
from typing import List

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Card, Bank
from src.services.ai_parser_golden import get_golden_parser
import requests
from bs4 import BeautifulSoup

def upgrade_marketing_text():
    db = SessionLocal()
    parser = get_golden_parser()
    
    print("🔍 Searching for campaigns with duplicate marketing text...")
    
    # Find campaigns where marketing text is identical to description
    campaigns = db.query(Campaign).join(Card).join(Bank).filter(
        Campaign.is_active == True,
        Campaign.ai_marketing_text == Campaign.description
    ).all()
    
    total = len(campaigns)
    print(f"📊 Found {total} campaigns to upgrade.")
    
    if total == 0:
        print("✅ No campaigns need upgrading.")
        return

    success_count = 0
    
    for i, c in enumerate(campaigns):
        print(f"[{i+1}/{total}] Upgrading ID: {c.id} - {c.title[:40]}...")
        
        try:
            # 1. Fetch HTML to get full context for a high-quality marketing text
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
            resp = requests.get(c.tracking_url, headers=headers, timeout=15, verify=False)
            resp.raise_for_status()
            
            # 2. Parse with AI
            # We use the full golden parser but we will ONLY save the marketing text
            ai_data = parser.parse_campaign(
                raw_html=resp.text,
                bank_name=c.card.bank.name,
                title=c.title
            )
            
            if ai_data and ai_data.get("ai_marketing_text"):
                new_mkt = ai_data["ai_marketing_text"]
                
                # Double check that AI didn't just return the description again
                if new_mkt.strip() != c.description.strip():
                    c.ai_marketing_text = new_mkt
                    db.commit()
                    print(f"   ✨ Success! New Marketing Text: {new_mkt[:60]}...")
                    success_count += 1
                else:
                    print(f"   ⚠️ AI still returned identical text. Skipping.")
            else:
                print(f"   ❌ AI failed to generate marketing text.")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            db.rollback()
            
        # Be polite to the API
        time.sleep(2)

    print(f"\n🏁 Finished. Successfully upgraded {success_count}/{total} campaigns.")
    db.close()

if __name__ == "__main__":
    upgrade_marketing_text()
