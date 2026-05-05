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
    print(f"Title: {c.title}")
    print(f"Text:\n{c.clean_text or c.description}")
else:
    print("Not found")
db.close()
