import sys
import os
sys.path.append(os.path.abspath('.'))
from src.database import get_db_session
from src.models import Campaign

db = get_db_session()
camp = db.query(Campaign).filter(Campaign.title.ilike('%Starbucks%')).order_by(Campaign.created_at.desc()).first()
if camp:
    print(f"TITLE: {camp.title}")
    print(f"PARTICIPATION: {camp.participation}")
    print(f"CONDITIONS: {camp.conditions}")
else:
    print("Not found")
