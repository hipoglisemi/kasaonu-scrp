import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.database import get_db_session
from src.models import Campaign

db = get_db_session()
c = db.query(Campaign).filter(Campaign.id == 17032).first()
if c:
    print(f"ID: {c.id}")
    print(f"Title: {c.title}")
    print(f"Description: {c.description}")
    print(f"AI Marketing Text: {c.ai_marketing_text}")
else:
    print("Campaign not found")
