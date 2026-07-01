import os
import sys

project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)
from src.database import get_db_session
from src.models import Campaign, Brand, CampaignBrand
from sqlalchemy.orm import joinedload

with get_db_session() as db:
    camps = db.query(Campaign).options(joinedload(Campaign.brands).joinedload(CampaignBrand.brand)).filter(
        Campaign.is_active == True, 
        Campaign.is_approved == False
    ).all()
    
    found = 0
    for c in camps:
        if c.brands:
            gib_brands = [cb for cb in c.brands if cb.brand and "gib.gov.tr" in cb.brand.name.lower()]
            if gib_brands:
                print(f"ID {c.id}: {c.title}")
                print(f"  Mevcut markalar: {[cb.brand.name for cb in c.brands]}")
                for cb in gib_brands:
                    db.delete(cb)
                found += 1
                
    if found > 0:
        db.commit()
    print(f"Toplam {found} kampanyadan gib.gov.tr silindi.")
