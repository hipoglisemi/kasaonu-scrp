import os
import sys
import time
import logging
from typing import List

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database import get_db_session
from src.models import Campaign
from src.services.ai_parser import parse_campaign

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_mismatched_ids() -> List[int]:
    """Retrieve IDs that need repair based on the diagnostic logic."""
    ids = []
    # I'll just use the IDs I know from the diagnostic earlier
    # or re-run a simplified check here.
    # For now, I'll fetch ALL active campaigns and re-parse them 
    # if they have a 'cards' discrepancy.
    # To keep it safe, I'll allow the user to pass IDs or fetch all active.
    with get_db_session() as db:
        campaigns = db.query(Campaign).filter(
            Campaign.is_active == True
        ).order_by(Campaign.id.desc()).all()
        return [c.id for c in campaigns]

def repair_campaigns(campaign_ids: List[int], batch_size: int = 20):
    total = len(campaign_ids)
    logger.info(f"🚀 Starting Bulk Repair for {total} campaigns...")
    
    count = 0
    for i in range(0, total, batch_size):
        batch = campaign_ids[i:i+batch_size]
        logger.info(f"📦 Processing batch {i//batch_size + 1} ({len(batch)} campaigns)...")
        
        with get_db_session() as db:
            for c_id in batch:
                campaign = db.query(Campaign).filter(Campaign.id == c_id).first()
                if not campaign or not campaign.clean_text:
                    continue
                
                try:
                    logger.info(f"   🔍 Re-parsing [{campaign.id}] {campaign.title}...")
                    
                    # Call AI Parser with the NEW rules
                    # Force=True to bypass cache
                    result = parse_campaign(
                        raw_text=campaign.clean_text, 
                        title=campaign.title,
                        bank_name=campaign.card.bank.name if campaign.card and campaign.card.bank else None,
                        force=True,
                        campaign_id=campaign.id
                    )
                    
                    if result and not result.get("_ai_failed"):
                        new_cards = ", ".join(result.get("cards", []))
                        old_cards = campaign.eligible_cards
                        
                        if new_cards != old_cards:
                            logger.info(f"      ✅ CARDS UPDATED: '{old_cards}' -> '{new_cards}'")
                            campaign.eligible_cards = new_cards
                            # Also update conditions to ensure they are clean
                            campaign.conditions = "\n".join(result.get("conditions", []))
                            db.commit()
                        else:
                            logger.info(f"      ℹ️ No change in cards.")
                    else:
                        logger.warning(f"      ⚠️ AI Parsing failed for {campaign.id}")
                        
                except Exception as e:
                    logger.error(f"      ❌ Error repairing {c_id}: {e}")
                    db.rollback()
                
                count += 1
                # Small delay to respect rate limits
                time.sleep(1.5)
        
        logger.info(f"✨ Batch complete. Progress: {count}/{total}")

if __name__ == "__main__":
    # Get IDs from command line if provided
    if len(sys.argv) > 1:
        target_ids = [int(i) for i in sys.argv[1].split(",")]
    else:
        # Default: Process all active campaigns
        target_ids = get_mismatched_ids()
    
    repair_campaigns(target_ids)
