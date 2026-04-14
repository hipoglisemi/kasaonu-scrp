import os
import sys
import re
import logging

# Set PYTHONPATH
sys.path.append(os.getcwd())

from src.database import get_db_session
from src.models import Campaign, CampaignBrand, Brand
from src.services.ai_parser import AIParser

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def run_production_clean():
    logger.info("--- 🌋 FINAL PRODUCTION CLEANUP (V4.7) STARTED ---")
    parser = AIParser()
    
    total_cleaned = 0
    total_removed_links = 0
    
    with get_db_session() as db:
        # Load all campaigns with brands
        campaigns = db.query(Campaign).all()
        logger.info(f"Analyzing {len(campaigns)} campaigns for brand integrity...")
        
        for idx, c in enumerate(campaigns):
            if not c.brands: continue
            
            # Use AIParser V4.7 Logic
            current_brands = [cb.brand.name for cb in c.brands]
            validated_brands = parser._validate_brands_against_text(
                brands=current_brands,
                clean_text=c.clean_text,
                title=c.title
            )
            
            to_remove = [b for b in current_brands if b not in validated_brands]
            
            if to_remove:
                logger.info(f"[{idx}] ❌ ID {c.id}: Removing invalid brands {to_remove}")
                for b_name in to_remove:
                    b_obj = db.query(Brand).filter(Brand.name == b_name).first()
                    if b_obj:
                        db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == c.id,
                            CampaignBrand.brand_id == b_obj.id
                        ).delete()
                        total_removed_links += 1
                db.commit()
                total_cleaned += 1

            if idx % 500 == 0 and idx > 0:
                logger.info(f"Progress: {idx}/{len(campaigns)} campaigns scanned.")

    logger.info(f"--- 🏁 CLEANUP COMPLETE ---")
    logger.info(f"Campaigns Cleaned: {total_cleaned}")
    logger.info(f"Brand Links Removed: {total_removed_links}")

if __name__ == "__main__":
    run_production_clean()
