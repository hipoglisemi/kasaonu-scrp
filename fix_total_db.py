import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database import get_db_session
from src.models import Campaign, Bank, CampaignBrand
from datetime import datetime, timedelta

db = get_db_session()
bank = db.query(Bank).filter(Bank.slug == 'totalenergies').first()

if not bank:
    print("Total energies bank not found")
    sys.exit()

recently_added = db.query(Campaign).filter(
    Campaign.card.has(bank_id=bank.id),
    Campaign.created_at >= (datetime.utcnow() - timedelta(days=2))
).all()

count = 0
for c in recently_added:
    # If the text is empty OR it has the trailing slash, let's delete it so the next run fixes it.
    is_empty = not c.description or len(c.description) < 10
    has_trailing = c.tracking_url and c.tracking_url.endswith('/')
    
    if is_empty or has_trailing:
        print(f"Deleting Campaign ID {c.id} - Title: {c.title} (Empty: {is_empty}, Trailing: {has_trailing})")
        # Delete associations first
        db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).delete()
        db.delete(c)
        count += 1

db.commit()
print(f"Deleted {count} faulty TotalEnergies campaigns.")
