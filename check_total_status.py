import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.database import get_db_session
from src.models import Campaign, Bank

db = get_db_session()
bank = db.query(Bank).filter(Bank.slug == 'totalenergies').first()
if not bank:
    print("Bank not found")
    sys.exit()

active_count = db.query(Campaign).filter(Campaign.card.has(bank_id=bank.id), Campaign.is_active == True).count()
inactive_count = db.query(Campaign).filter(Campaign.card.has(bank_id=bank.id), Campaign.is_active == False).count()

print(f"TotalEnergies - Active: {active_count}, Inactive: {inactive_count}")

active = db.query(Campaign).filter(Campaign.card.has(bank_id=bank.id), Campaign.is_active == True).all()
for a in active:
    print(f"ACTIVE: {a.title} ({a.tracking_url})")
