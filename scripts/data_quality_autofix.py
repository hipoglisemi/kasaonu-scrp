import os
import sys
import re
from datetime import datetime

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign
from src.services.ai_parser_golden import AIParserGolden, _create_default_client
import requests
from bs4 import BeautifulSoup

def autofix_campaigns():
    # Read the IDs from the report
    report_path = os.path.join(project_root, 'GEMMA_31B_DENETIM_RAPORU.md')
    if not os.path.exists(report_path):
        print(f"Rapor bulunamadı: {report_path}")
        return

    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract IDs: ### 🚨 ID: 14798
    ids = re.findall(r'### 🚨 ID:\s*(\d+)', content)
    ids = [int(i) for i in ids]
    
    print(f"Rapordan {len(ids)} adet ID bulundu.")

    if not ids:
        return

    db = SessionLocal()
    campaigns = db.query(Campaign).filter(Campaign.id.in_(ids)).all()
    print(f"Veritabanında {len(campaigns)} adet eşleşen kampanya bulundu.")

    # We will use GoldenParser as it contains the excluded_cards logic
    client = _create_default_client()
    parser = AIParserGolden(model_client=client)

    for camp in campaigns:
        bank_name = camp.card.bank.name if camp.card and camp.card.bank else "Genel"
        print(f"\n[{camp.id}] Düzeltiliyor: {camp.title} ({bank_name})")
        
        url = camp.tracking_url
        if not url:
            print(f"   ⚠️ URL yok, atlanıyor.")
            continue

        try:
            print(f"   🌐 İçerik çekiliyor (URL: {url})...")
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            html_content = resp.text

            print(f"   🧠 AI Golden Parser'a gönderiliyor...")
            # We use parse_campaign instead of parse_api_campaign to utilize the GoldenParser instance
            ai_data = parser.parse_campaign(
                raw_html=html_content,
                bank_name=bank_name,
                title=camp.title
            )
            
            if ai_data and not ai_data.get("_ai_failed"):
                # Update Campaign
                # GoldenParser structure handling
                camp.participation = ai_data.get('participation', camp.participation)
                
                # Check what was excluded
                excluded = ai_data.get('excluded_cards', [])
                if excluded:
                    print(f"   🛡️ Çıkarılan kartlar: {excluded}")

                cards = ai_data.get('cards', [])
                camp.eligible_cards = ", ".join(cards) if cards else None
                
                conditions = ai_data.get('conditions', camp.conditions)
                camp.conditions = "\n".join(conditions) if isinstance(conditions, list) else conditions
                
                print(f"   ✅ Başarılı! (Katılım: {str(camp.participation)[:30]}..., Kartlar: {camp.eligible_cards})")
            else:
                print(f"   ❌ AI Parse başarısız oldu.")

            db.commit()
        except Exception as e:
            print(f"   ❌ Hata: {e}")
            db.rollback()

    db.close()

if __name__ == "__main__":
    autofix_campaigns()
