import os
import sys
import logging
import re

# Add current directory to path
sys.path.append(os.getcwd())

from src.database import get_db_session
from src.models import Campaign, CampaignBrand, Brand
from src.services.ai_parser import AIParser

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def global_sweep():
    logger.info("--- 🌊 GLOBAL SWEEP: Cleaning EVERYTHING detected by V4.7 ---")
    parser = AIParser()
    
    # We will identify all problematic campaigns again in real-time and clean them
    negation_keywords = ["dahil değildir", "hariçtir", "geçerli değildir", "kapsam dışıdır", "dahil edilmeyecektir", "sayılmamaktadır", "taksitlendirilmemektedir"]
    
    total_deleted = 0
    with get_db_session() as db:
        all_campaigns = db.query(Campaign).all()
        for c in all_campaigns:
            if not c.brands: continue
            
            current_brands = [cb.brand.name for cb in c.brands]
            validated_brands = parser._validate_brands_against_text(current_brands, c.clean_text, c.title)
            
            to_remove = [b for b in current_brands if b not in validated_brands]
            if to_remove:
                logger.info(f"Cleaning ID {c.id}: Removing {to_remove}")
                for b_name in to_remove:
                    b_obj = db.query(Brand).filter(Brand.name == b_name).first()
                    if b_obj:
                        db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == c.id,
                            CampaignBrand.brand_id == b_obj.id
                        ).delete()
                        total_deleted += 1
                db.commit()
                
    logger.info(f"Global Sweep Complete. Total links removed: {total_deleted}")

if __name__ == "__main__":
    global_sweep()
