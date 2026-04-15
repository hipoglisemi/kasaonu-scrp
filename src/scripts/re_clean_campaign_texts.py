import os
import sys
from sqlalchemy.orm import Session
from tqdm import tqdm

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import SessionLocal
from src.models import Campaign, Bank, Card
from src.services.text_cleaner import clean_campaign_text

def run_cleanup():
    db = SessionLocal()
    try:
        print("🚀 Starting Bulk CleanText Cleanup...")
        
        # Get all campaigns with non-empty clean_text
        query = db.query(Campaign).filter(Campaign.clean_text.isnot(None))
        total = query.count()
        print(f"📦 Total campaigns to check: {total}")
        
        campaigns = query.all()
        cleaned_count = 0
        
        for campaign in tqdm(campaigns, desc="Cleaning Campaigns"):
            original_text = campaign.clean_text
            if not original_text:
                continue
                
            # Apply new cleaning rules
            new_text = clean_campaign_text(original_text)
            
            # If changed, update
            if new_text != original_text:
                campaign.clean_text = new_text
                cleaned_count += 1
                
                # Commit in batches
                if cleaned_count % 50 == 0:
                    db.commit()
        
        db.commit()
        print(f"\n✅ Cleanup Finished!")
        print(f"✨ Total Cleaned/Updated: {cleaned_count}")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_cleanup()
