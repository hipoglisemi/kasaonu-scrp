"""
Dyson kampanyası adli analizi - Axess kart üzerindeki tüm Dyson kampanyalarını listeler.
"""
import sys
import os
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

from src.database import get_db_session
from src.models import Campaign, Card

with get_db_session() as db:
    # Axess kartını bul
    axess_card = db.query(Card).filter(Card.name == "Axess").first()
    if not axess_card:
        print("❌ Axess kartı bulunamadı!")
        sys.exit(1)
    
    print(f"✅ Axess Card ID: {axess_card.id}\n")

    # Tüm Dyson kampanyalarını bul (aktif + pasif)
    dyson_campaigns = db.query(Campaign).filter(
        Campaign.title.ilike('%dyson%')
    ).order_by(Campaign.id.desc()).all()

    print(f"📋 Toplam Dyson Kampanyası (tüm kartlar): {len(dyson_campaigns)}\n")
    print(f"{'ID':<8} {'Card ID':<10} {'Aktif':<8} {'Onaylı':<8} {'Oluşturma':<22} {'Güncelleme':<22} {'Başlık'}")
    print("-" * 120)
    for c in dyson_campaigns:
        print(f"{c.id:<8} {c.card_id:<10} {'✅' if c.is_active else '❌':<8} {'✅' if c.is_approved else '❌':<8} {str(c.created_at)[:19]:<22} {str(c.updated_at)[:19]:<22} {c.title[:50]}")
    
    print()
    
    # Axess'e özel filtreleme
    axess_dyson = [c for c in dyson_campaigns if c.card_id == axess_card.id]
    print(f"\n🎯 Axess kartına ait Dyson kampanyaları: {len(axess_dyson)}")
    print("-" * 120)
    for c in axess_dyson:
        print(f"\nID        : {c.id}")
        print(f"Başlık    : {c.title}")
        print(f"Aktif     : {'✅ Evet' if c.is_active else '❌ Pasif'}")
        print(f"Onaylı    : {'✅ Evet' if c.is_approved else '❌ Hayır'}")
        print(f"Tracking  : {c.tracking_url}")
        print(f"Slug      : {c.slug}")
        print(f"Oluşturma : {c.created_at}")
        print(f"Güncelleme: {c.updated_at}")
        print(f"Başlangıç : {c.start_date}")
        print(f"Bitiş     : {c.end_date}")
