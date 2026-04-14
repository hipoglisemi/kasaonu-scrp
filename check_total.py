import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database import get_db_session
from src.models import Campaign, Bank

db = get_db_session()
bank = db.query(Bank).filter(Bank.slug == 'totalenergies').first()
if not bank:
    print("Bank not found")
    sys.exit()

campaigns = db.query(Campaign).filter(
    Campaign.card.has(bank_id=bank.id)
).order_by(Campaign.created_at.desc()).limit(15).all()

for c in campaigns:
    print(f"ID: {c.id} | Created: {c.created_at} | URL: {c.tracking_url}")
    print(f"Title: {c.title}")
    length_desc = len(c.description) if c.description else 0
    length_ai = len(c.ai_marketing_text) if c.ai_marketing_text else 0
    print(f"Content length: DESC: {length_desc}, AI: {length_ai}")
    print("-" * 50)
