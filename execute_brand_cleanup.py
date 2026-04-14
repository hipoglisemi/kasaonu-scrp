import os
import sys
import json
import logging
from src.database import get_db_session
from src.models import Campaign, CampaignBrand, Brand
from src.services.ai_parser import AIParser

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def execute_cleanup():
    logger.info("--- 🚀 STARTING LIVE BRAND CLEANUP (WRITE ENABLED) ---")
    parser = AIParser()
    
    report_file = "brand_scan_report_v4_5.json"
    if not os.path.exists(report_file):
        logger.error(f"{report_file} not found. Scan first.")
        return
        
    with open(report_file, "r") as f:
        scan_data = json.load(f)

    total_deleted = 0
    
    with get_db_session() as db:
        for item in scan_data:
            c = db.query(Campaign).get(item["id"])
            if not c: continue
            
            logger.info(f"Processing ID {c.id}: {c.title[:50]}...")
            
            current_brands = [cb.brand.name for cb in c.brands]
            validated_brands = parser._validate_brands_against_text(
                brands=current_brands,
                clean_text=c.clean_text,
                title=c.title
            )
            
            # Find brands to remove (those in DB but rejected by V4.7 parser)
            to_remove = [b for b in current_brands if b not in validated_brands]
            
            if to_remove:
                logger.info(f"   ❌ Removing: {to_remove}")
                # Surgical deletion from campaign_brands
                for brand_name in to_remove:
                    # Find Brand ID
                    brand_obj = db.query(Brand).filter(Brand.name == brand_name).first()
                    if brand_obj:
                        db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == c.id,
                            CampaignBrand.brand_id == brand_obj.id
                        ).delete()
                        total_deleted += 1
                db.commit()
            else:
                logger.info("   ✅ All validated. No changes needed.")

    logger.info(f"--- 🏁 CLEANUP COMPLETE. Total brand links removed: {total_deleted} ---")

if __name__ == "__main__":
    execute_cleanup()
