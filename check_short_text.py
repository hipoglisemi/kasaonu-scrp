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

def check_short_campaigns(threshold=200):
    db = SessionLocal()
    try:
        # Query active campaigns with short clean_text
        short_campaigns = db.query(Campaign).filter(
            Campaign.is_active == True,
            func.length(Campaign.clean_text) < threshold
        ).all()

        print(f"\n🔍 Found {len(short_campaigns)} active campaigns with clean_text < {threshold} chars.\n")

        # Group by Bank/Card for better overview
        report = {}
        for c in short_campaigns:
            card = db.query(Card).filter(Card.id == c.card_id).first()
            bank = db.query(Bank).filter(Bank.id == card.bank_id).first() if card else None
            bank_name = bank.name if bank else "Unknown"
            
            if bank_name not in report:
                report[bank_name] = []
            
            report[bank_name].append({
                "id": c.id,
                "title": c.title,
                "length": len(c.clean_text) if c.clean_text else 0,
                "url": c.tracking_url
            })

        for bank, camps in sorted(report.items()):
            print(f"🏦 {bank} ({len(camps)} campaigns)")
            for camp in camps:
                print(f"   - [{camp['id']}] (len: {camp['length']}) {camp['title'][:60]}...")
            print("")

    finally:
        db.close()

if __name__ == "__main__":
    threshold = 200
    if len(sys.argv) > 1:
        threshold = int(sys.argv[1])
    check_short_campaigns(threshold)
