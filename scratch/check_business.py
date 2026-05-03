import os
import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign, Card

with get_db_session() as db:
    card = db.query(Card).filter(Card.name == "Axess Business").first()
    if card:
        all_camps = db.query(Campaign).filter(Campaign.card_id == card.id).all()
        active = sum(1 for c in all_camps if c.is_active)
        passive = len(all_camps) - active
        print(f"Axess Business - Toplam: {len(all_camps)}, Aktif: {active}, Pasif: {passive}")
        for c in all_camps:
            if not c.is_active:
                print(f"PASİF KAMPANYA: {c.title} - {c.tracking_url}")
