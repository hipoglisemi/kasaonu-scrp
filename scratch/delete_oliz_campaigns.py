import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.database import get_db_session
from src.models import Campaign, Card

with get_db_session() as db:
    card = db.query(Card).filter(Card.slug == "oliz").first()
    if card:
        campaigns = db.query(Campaign).filter(Campaign.card_id == card.id).all()
        print(f"Found {len(campaigns)} Oliz campaigns. Deleting them...")
        for c in campaigns:
            db.delete(c)
        db.commit()
        print("Deleted all Oliz campaigns successfully.")
    else:
        print("Oliz card not found.")
