import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models import Campaign
from src.database import SessionLocal

db = SessionLocal()
for cid in [18078, 18079]:
    c = db.query(Campaign).filter(Campaign.id == cid).first()
    if c:
        print(f"[{c.id}] {c.title}")
        print(f"URL: {c.tracking_url}")
        print(f"Participation: {c.participation}")
        print("-" * 50)
db.close()
