import os
import sys

project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign, Card

with get_db_session() as db:
    c = db.query(Campaign).filter(Campaign.id == 17749).first()
    if c:
        card = db.query(Card).filter(Card.id == c.card_id).first()
        print(f"ID: {c.id}")
        print(f"Title: {c.title}")
        print(f"URL: {c.tracking_url}")
        print(f"Bank/Card: {card.name if card else 'Unknown'}")
        print(f"Eligible Cards: {c.eligible_cards}")
        print(f"Conditions: {c.conditions}")
        print(f"Raw Text Preview: {c.description[:500] if c.description else ''}")
    else:
        print("Campaign not found.")
