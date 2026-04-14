import os
import sys
import logging

# Add current directory to path
sys.path.append(os.getcwd())

from src.database import get_db_session
from src.models import Campaign, CampaignBrand, Brand
from src.services.ai_parser import AIParser

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def sweep():
    logger.info("--- 🧹 FINAL SWEEP: Cleaning 6 Hidden IDs found by V4.7 ---")
    parser = AIParser()
    target_ids = [15684, 12104, 15654, 16215, 15555, 15856]
    
    total_deleted = 0
    with get_db_session() as db:
        for cid in target_ids:
            c = db.query(Campaign).get(cid)
            if not c: continue
            
            logger.info(f"Sweeping ID {c.id}...")
            current_brands = [cb.brand.name for cb in c.brands]
            validated_brands = parser._validate_brands_against_text(current_brands, c.clean_text, c.title)
            
            to_remove = [b for b in current_brands if b not in validated_brands]
            if to_remove:
                logger.info(f"   ❌ Removing hidden noise: {to_remove}")
                for b_name in to_remove:
                    b_obj = db.query(Brand).filter(Brand.name == b_name).first()
                    if b_obj:
                        db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == c.id,
                            CampaignBrand.brand_id == b_obj.id
                        ).delete()
                        total_deleted += 1
                db.commit()
    logger.info(f"Sweep complete. {total_deleted} links removed.")

if __name__ == "__main__":
    sweep()
