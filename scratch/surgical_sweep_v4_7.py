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

def surgical_sweep():
    logger.info("--- 🎯 SURGICAL SWEEP: Cleaning IDs from V4.7 Report ---")
    parser = AIParser()
    
    # Extract IDs from brand_tag_report.md
    report_file = "brand_tag_report.md"
    if not os.path.exists(report_file):
        logger.error("Report not found.")
        return
        
    with open(report_file, "r") as f:
        content = f.read()
    
    # Regex to find | **12345** |
    target_ids = [int(m) for m in re.findall(r"\|\s*\*\*(\d+)\*\*\s*\|", content)]
    logger.info(f"Targeting {len(target_ids)} unique IDs for cleanup.")
    
    total_removed = 0
    with get_db_session() as db:
        for cid in target_ids:
            c = db.query(Campaign).get(cid)
            if not c: continue
            
            logger.info(f"Cleaning ID {c.id}...")
            current_brands = [cb.brand.name for cb in c.brands]
            validated_brands = parser._validate_brands_against_text(current_brands, c.clean_text, c.title)
            
            to_remove = [b for b in current_brands if b not in validated_brands]
            if to_remove:
                logger.info(f"   ❌ Removing: {to_remove}")
                for b_name in to_remove:
                    b_obj = db.query(Brand).filter(Brand.name == b_name).first()
                    if b_obj:
                        db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == c.id,
                            CampaignBrand.brand_id == b_obj.id
                        ).delete()
                        total_removed += 1
                db.commit()

    logger.info(f"--- 🏁 Surgical Sweep Complete. Links removed: {total_removed} ---")

if __name__ == "__main__":
    surgical_sweep()
