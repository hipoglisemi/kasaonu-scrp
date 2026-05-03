import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign

with get_db_session() as db:
    c = db.query(Campaign).filter(Campaign.id == 17749).first()
    print("--- RAW TEXT ---")
    print(c.description)
    print("--- CONDITIONS ---")
    print(c.conditions)
