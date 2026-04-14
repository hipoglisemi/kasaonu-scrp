import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.database import get_db_session
from src.models import Campaign, Card, Bank
from sqlalchemy import func

db = get_db_session()
# Count empty ai_marketing_text
empty_count = db.query(Campaign).filter((Campaign.ai_marketing_text == None) | (Campaign.ai_marketing_text == '')).count()
print(f"Total campaigns with empty ai_marketing_text: {empty_count}")

# Group by bank to see which scrapers are failing
results = db.query(Bank.name, func.count(Campaign.id))\
    .join(Card, Card.bank_id == Bank.id)\
    .join(Campaign, Campaign.card_id == Card.id)\
    .filter((Campaign.ai_marketing_text == None) | (Campaign.ai_marketing_text == ''))\
    .group_by(Bank.name).all()

print("\nEmpty counts by Bank:")
for bank_name, count in results:
    print(f"- {bank_name}: {count}")

# Check recent ones (today)
from datetime import datetime
today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
today_empty = db.query(Campaign).filter(Campaign.created_at >= today).filter((Campaign.ai_marketing_text == None) | (Campaign.ai_marketing_text == '')).count()
print(f"\nEmpty campaigns created TODAY: {today_empty}")

# List the last 15 empty ones with title and url
print("\nLast 15 empty campaigns:")
last_ones = db.query(Campaign.id, Campaign.title, Campaign.tracking_url)\
    .filter((Campaign.ai_marketing_text == None) | (Campaign.ai_marketing_text == ''))\
    .order_by(Campaign.created_at.desc()).all()
for cid, title, url in last_ones:
    print(f"[{cid}] {title} | URL: {url}")
