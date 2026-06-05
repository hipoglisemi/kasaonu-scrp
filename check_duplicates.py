from src.database import get_db_session
from src.models import Campaign

with get_db_session() as db:
    for id in [14746, 19650]:
        c = db.query(Campaign).filter(Campaign.id == id).first()
        if c:
            print(f"ID: {c.id} | Title: {c.title} | Card: {c.card_id} | URL: {c.tracking_url} | Active: {c.is_active}")
