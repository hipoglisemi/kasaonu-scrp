import sys
import os
import json

# Proje kök dizinini ekle
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Card, Bank
from src.services.ai_parser import get_ai_parser

def repair_by_id(campaign_id):
    db = SessionLocal()
    try:
        # 1. Kampanyayı bul
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            print(f"❌ Kampanya bulunamadı: {campaign_id}")
            return

        # 2. Banka adını bul
        card = db.query(Card).filter(Card.id == campaign.card_id).first()
        bank_name = "Bilinmeyen"
        if card:
            bank = db.query(Bank).filter(Bank.id == card.bank_id).first()
            if bank:
                bank_name = bank.name

        print(f"🛠️  Tamir Başlıyor: ID {campaign_id} ({bank_name} - {campaign.title})")
        
        # 3. AI Parser'ı çalıştır
        parser = get_ai_parser()
        # force=True diyerek cache'i atlıyoruz ve güncel kodla çalışıyoruz
        
        # Metni full context olarak alıyoruz (başlık + açıklama)
        full_text = f"{campaign.title}\n{campaign.clean_text or campaign.description or ''}"
        
        result = parser.parse_campaign_data(
            raw_text=full_text,
            title=campaign.title,
            bank_name=bank_name,
            tracking_url=campaign.tracking_url,
            force=True
        )

        # 4. Sonuçları Güncelle
        if result:
            print(f"✅ AI Analizi Tamamlandı.")
            print(f"📊 Yeni Geçerli Kartlar: {result.get('cards')}")
            
            campaign.eligible_cards = ", ".join(result.get("cards", []))
            campaign.reward_text = result.get("reward_text")
            campaign.reward_value = result.get("reward_value")
            campaign.reward_type = result.get("reward_type")
            campaign.description = result.get("description")
            campaign.conditions = "\n".join(result.get("conditions", []))
            campaign.participation = result.get("participation")
            campaign.ai_marketing_text = result.get("ai_marketing_text")
            campaign.clean_text = result.get("_clean_text")
            
            db.commit()
            print(f"💾 Veritabanı güncellendi.")
        else:
            print(f"❌ AI analizi boş döndü.")

    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("id", type=int, help="Campaign ID to repair")
    args = parser.parse_args()
    repair_by_id(args.id)
