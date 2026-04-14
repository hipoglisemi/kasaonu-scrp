import json
import os
import sys
import logging
from src.database import get_db_session
from src.models import Campaign, Brand, CampaignBrand

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# IDs to EXCLUDE from cleanup as they were verified as valid (False Positives)
EXCLUSION_IDS = [8452, 12460, 16902]

def execute_cleanup():
    logger.info("--- 🚀 FINAL BRAND INTEGRITY CLEANUP STARTED ---")
    
    report_file = "brand_scan_report_v4_5.json"
    if not os.path.exists(report_file):
        logger.error(f"{report_file} not found. Operation aborted.")
        return

    with open(report_file, "r") as f:
        scan_data = json.load(f)

    total_unlinked = 0
    with get_db_session() as db:
        for item in scan_data:
            cid = item["id"]
            if cid in EXCLUSION_IDS:
                logger.info(f"   ⏩ Skipping ID {cid} (Verified Valid/False Positive)")
                continue
                
            bad_brands = item.get("removals_negation", []) + item.get("removals_noise", [])
            if not bad_brands: continue
            
            logger.info(f"   🧹 Cleaning ID {cid}: {item['title'][:50]}...")
            
            # Find and remove CampaignBrand links for these bad brands
            for brand_name in bad_brands:
                # Find the brand ID
                brand = db.query(Brand).filter(Brand.name == brand_name).first()
                if not brand: continue
                
                # Find the relation
                relation = db.query(CampaignBrand).filter(
                    CampaignBrand.campaign_id == cid,
                    CampaignBrand.brand_id == brand.id
                ).first()
                
                if relation:
                    db.delete(relation)
                    total_unlinked += 1
                    logger.info(f"      🗑️ Un-tagged: {brand_name}")
        
        db.commit()
    
    logger.info(f"--- ✅ CLEANUP COMPLETE. Total brands un-tagged: {total_unlinked} ---")

if __name__ == "__main__":
    execute_cleanup()
