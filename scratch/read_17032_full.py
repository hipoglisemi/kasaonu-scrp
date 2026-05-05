import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign

db = SessionLocal()
c = db.query(Campaign).filter(Campaign.id == 17032).first()
if c:
    print(f"ID: {c.id}")
    print(f"TITLE: {c.title}")
    print("-" * 30)
    print(f"DESCRIPTION:\n{c.description}")
    print("-" * 30)
    print(f"CONDITIONS:\n{c.conditions}")
    print("-" * 30)
    print(f"CLEAN_TEXT:\n{c.clean_text}")
    print("-" * 30)
    print(f"ELIGIBLE_CARDS: {c.eligible_cards}")
else:
    print("Not found")
db.close()
