
import os
import sys
import argparse

# Dynamic path setup to ensure we can import src modules
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign
from sqlalchemy import or_

def repair_marketing_text(dry_run=True):
    """
    Repair script to populate missing ai_marketing_text from description.
    """
    print(f"🚀 Starting ai_marketing_text repair (Dry Run: {dry_run})")
    print("-" * 60)

    with get_db_session() as db:
        # Find campaigns where ai_marketing_text is NULL or empty
        query = db.query(Campaign).filter(
            or_(
                Campaign.ai_marketing_text == None,
                Campaign.ai_marketing_text == ""
            )
        )
        
        campaigns = query.all()
        total_count = len(campaigns)
        
        print(f"🔍 Found {total_count} campaigns with missing ai_marketing_text.")
        
        repaired_count = 0
        for campaign in campaigns:
            # We use description as the source for ai_marketing_text if missing
            if campaign.description:
                source_content = campaign.description
                
                if not dry_run:
                    campaign.ai_marketing_text = source_content
                
                repaired_count += 1
                if repaired_count % 10 == 0:
                    print(f"   Processed {repaired_count}/{total_count}...")
            else:
                print(f"   ⚠️ Skipping ID {campaign.id} (description is also empty)")

        if not dry_run:
            db.commit()
            print(f"✅ Successfully updated {repaired_count} campaigns.")
        else:
            print(f"🧪 Dry run complete. {repaired_count} campaigns would be updated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair missing ai_marketing_text in database.")
    parser.add_argument("--execute", action="store_true", help="Execute the changes (default is dry-run)")
    args = parser.parse_args()

    repair_marketing_text(dry_run=not args.execute)
