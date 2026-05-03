import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign

with get_db_session() as db:
    camp = db.query(Campaign).get(14000)
    if camp:
        print(f"TITLE: {camp.title}")
        print(f"CLEAN TEXT:\n{camp.clean_text}")
    else:
        print("Campaign not found")
