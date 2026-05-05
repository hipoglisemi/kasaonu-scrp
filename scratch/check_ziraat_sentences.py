import sys
import os
import re

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Card, Bank

db = SessionLocal()
try:
    # Ziraat bankasını bul
    ziraat = db.query(Bank).filter(Bank.slug == 'ziraat-bankasi').first()
    if not ziraat:
        print("Ziraat Bankasi bulunamadi.")
        sys.exit()

    # Ziraat'e ait ve clean_text'i dolu olan kampanyaları çek (limit 10)
    campaigns = db.query(Campaign).join(Card).filter(
        Card.bank_id == ziraat.id,
        Campaign.clean_text != None
    ).limit(20).all()

    print(f"🔍 Toplam {len(campaigns)} dolu Ziraat kampanyası bulundu.\n")

    for c in campaigns:
        print(f"ID: {c.id} | Başlık: {c.title}")
        text = c.clean_text
        
        # 'dahil' kelimesinin geçtiği cümleleri bulalım
        # Ziraat genellikle 'dahildir' veya 'dahil değildir' der.
        matches = re.findall(r"([^.]*?dahil[^.]*?\.)", text, re.IGNORECASE | re.DOTALL)
        
        if matches:
            for i, m in enumerate(matches):
                print(f"  📌 Cümle {i+1}: {m.strip()}")
        else:
            print("  ⚠️ 'dahil' anahtar kelimesi metinde bulunamadı.")
        print("-" * 50)

finally:
    db.close()
