import os
import sys
import logging
from src.database import get_db_session
from src.models import Campaign, Brand, CampaignBrand

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Brands to RESTORE (IDs that were correctly tagged but wrongfully removed)
RESTORE_DATA = [
    (10008, "Hotel Anatolia"), (9176, "Hotel Anatolia"), (9003, "Hotel Anatolia"), (8544, "Hotel Anatolia"),
    (8529, "Elifewellness"), (8477, "Cappadocia Cave Suites"), 
    (15314, "Deli2Go"), (12460, "Deli2Go"),
    (8476, "Sultan Cave Suites Kapadokya"),
    (15748, "Sgk"),
    (16542, "Xiaomi"),
    (14824, "Dijital Kod Market"),
    (11850, "App Store"),
    (15034, "Setur"),
    (15944, "Network"), (15944, "New Balance"),
    (16925, "N11"),
    (12107, "New Balance"), (12107, "Network"),
    (12104, "New Balance"), (12104, "Network"),
    (15689, "Fizy")
]

def rescue():
    logger.info("--- 🚑 BRAND RESCUE OPERATION STARTED ---")
    with get_db_session() as db:
        for cid, bname in RESTORE_DATA:
            # Find brand
            brand = db.query(Brand).filter(Brand.name == bname).first() # Case insensitive match?
            if not brand:
                # Try search with variations
                brand = db.query(Brand).filter(Brand.name.ilike(bname)).first()
            
            if not brand:
                logger.error(f"   ❌ Could not find brand: {bname}")
                continue
                
            # Check if relation already exists
            existing = db.query(CampaignBrand).filter(
                CampaignBrand.campaign_id == cid,
                CampaignBrand.brand_id == brand.id
            ).first()
            
            if not existing:
                new_rel = CampaignBrand(campaign_id=cid, brand_id=brand.id)
                db.add(new_rel)
                logger.info(f"   ✅ Restored: {bname} -> ID {cid}")
            else:
                logger.info(f"   ℹ️ Already exists: {bname} -> ID {cid}")
        
        db.commit()
    logger.info("--- 🏁 RESCUE COMPLETE ---")

if __name__ == "__main__":
    rescue()
