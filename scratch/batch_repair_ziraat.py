import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.scrapers.ziraat import ZiraatScraper
from src.database import SessionLocal
from src.models import Campaign

def repair_batch(ids):
    scraper = ZiraatScraper()
    db = SessionLocal()
    try:
        for cid in ids:
            campaign = db.query(Campaign).filter(Campaign.id == cid).first()
            if not campaign:
                print(f"❌ ID {cid} bulunamadı.")
                continue
                
            print(f"\n🚀 Processing ID {cid}: {campaign.title}")
            url = campaign.tracking_url
            if not url:
                print(f"  ⚠️ URL yok, atlanıyor.")
                continue
                
            res = scraper._process_campaign({"url": url, "list_end_date": "31.12.2026"})
            print(f"  ✅ Sonuç: {res}")
            
            # Son hali kontrol et
            db.refresh(campaign)
            print(f"  📊 Geçerli Kartlar: {campaign.eligible_cards}")
            
    finally:
        db.close()

if __name__ == "__main__":
    repair_batch([16975, 16555, 15203])
