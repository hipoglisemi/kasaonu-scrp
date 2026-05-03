import os
import sys

# Add current dir to path
sys.path.insert(0, os.path.abspath("."))

from src.models import Campaign
from src.database import get_db

def get_url(cid):
    db = next(get_db())
    c = db.query(Campaign).filter(Campaign.id == cid).first()
    if c:
        print(f"URL: {c.tracking_url}")
    else:
        print("Not found")

if __name__ == "__main__":
    get_url(17843)
