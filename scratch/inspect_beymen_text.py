import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db_session
from src.models import Campaign
from src.services.text_cleaner import clean_campaign_text

def inspect_beymen():
    with get_db_session() as db:
        c = db.query(Campaign).filter(Campaign.id == 18703).first()
        if not c:
            print("❌ Campaign 18703 not found!")
            return
            
        print("====== RAW TEXT ======")
        print(c.clean_text[:1000])
        print("...")
        print(c.clean_text[-1000:])
        
        print("\n====== DYNAMICALLY CLEANED TEXT ======")
        cleaned = clean_campaign_text(c.clean_text, title=c.title)
        print(cleaned)

if __name__ == "__main__":
    inspect_beymen()
