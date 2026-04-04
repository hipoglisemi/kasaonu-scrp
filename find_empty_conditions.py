import os
import sys
from sqlalchemy import func
from sqlalchemy.orm import Session

# Ensure src in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Card, Bank

def find_empty_conditions_campaigns(min_clean_text=1000, max_conditions=50):
    db = SessionLocal()
    try:
        # Query active campaigns where clean_text is present but conditions is suspiciously short or empty
        candidates = db.query(Campaign).filter(
            Campaign.is_active == True,
            func.length(Campaign.clean_text) >= min_clean_text,
            (Campaign.conditions == None) | (func.length(Campaign.conditions) < max_conditions)
        ).all()

        print(f"\n🔍 Found {len(candidates)} active campaigns with long clean_text but EMPTY/SHORT conditions.\n")

        report = {}
        for c in candidates:
            card = db.query(Card).filter(Card.id == c.card_id).first()
            bank = db.query(Bank).filter(Bank.id == card.bank_id).first() if card else None
            bank_name = bank.name if bank else "Unknown"
            
            if bank_name not in report:
                report[bank_name] = []
            
            report[bank_name].append({
                "id": c.id,
                "title": c.title,
                "clean_text_len": len(c.clean_text),
                "conditions_len": len(c.conditions) if c.conditions else 0,
                "url": c.tracking_url
            })

        for bank, camps in sorted(report.items()):
            print(f"🏦 {bank} ({len(camps)} campaigns)")
            for camp in camps:
                print(f"   - [{camp['id']}] Text: {camp['clean_text_len']} | Cond: {camp['conditions_len']} | {camp['title'][:60]}...")
            print("")

    finally:
        db.close()

if __name__ == "__main__":
    find_empty_conditions_campaigns()
