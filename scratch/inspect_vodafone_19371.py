import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db_session
from src.models import Campaign

def inspect_campaign():
    with get_db_session() as db:
        c = db.query(Campaign).filter(Campaign.id == 19371).first()
        if not c:
            print("❌ Campaign 19371 not found!")
            return
            
        print(f"==================== VODAFONE CAMPAIGN 19371 ====================")
        print(f"ID:                 {c.id}")
        print(f"Title:              {c.title}")
        print(f"Slug:               {c.slug}")
        print(f"Tracking URL:       {c.tracking_url}")
        print(f"Is Approved:        {c.is_approved}")
        print("-" * 80)
        print(f"Eligible Cards:     {c.eligible_cards}")
        print(f"Participation:      {c.participation}")
        print(f"AI Marketing Text:  {c.ai_marketing_text}")
        print("-" * 80)
        print("Clean Text:")
        print(c.clean_text[:500] if c.clean_text else "None")
        print("=================================================================")

if __name__ == "__main__":
    inspect_campaign()
