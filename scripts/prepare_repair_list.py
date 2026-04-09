import os
import sys
from sqlalchemy.orm import joinedload
from src.database import SessionLocal
from src.models import Campaign, CampaignBrand, Brand, Sector
from src.services.point_blank_matcher import get_point_blank_matcher

def main():
    db = SessionLocal()
    matcher = get_point_blank_matcher(db)
    
    print("🔍 Scanning active campaigns for repair needs...")
    # Eager load relationships for speed
    active_campaigns = db.query(Campaign).options(
        joinedload(Campaign.brands).joinedload(CampaignBrand.brand),
        joinedload(Campaign.sector)
    ).filter(Campaign.is_active == True).all()
    
    to_fix = set()
    total = len(active_campaigns)
    
    for i, c in enumerate(active_campaigns):
        if i % 500 == 0: print(f"   ... checked {i}/{total}")

        title = (c.title or "").lower()
        desc = (c.description or "").lower()
        clean = (c.clean_text or "").lower()
        cond = (c.conditions or "").lower()
        full_text = f"{title} {desc} {clean} {cond}"
        
        db_brands = [cb.brand.name.lower() for cb in c.brands if cb.brand]
        db_sector = c.sector.slug if c.sector else "diger"
        
        # 1. Amazon Prime / Amazon logic
        if "prime" in full_text and "amazon" in full_text:
            if "amazon prime" not in db_brands:
                to_fix.add(c.id)
                continue
        elif "amazon" in full_text:
            if "amazon" not in db_brands and "amazon prime" not in db_brands:
                to_fix.add(c.id)
                continue
                
        # 2. Sector Gaps (diger)
        if db_sector == "diger":
            to_fix.add(c.id)
            continue
            
        # 3. Sector Conflicts (Detected by PBE)
        pbe_matches = matcher.match_campaign(c.title or "", f"{(c.description or '')} {(c.clean_text or '')}")
        pbe_sectors = set(m["sector"] for m in pbe_matches if m.get("sector"))
        if pbe_sectors and db_sector not in pbe_sectors:
            to_fix.add(c.id)
            continue

    print(f"✅ Scanning complete. Found {len(to_fix)} campaigns that need repair.")
    
    # Save to file
    with open("scripts/repair_ids.txt", "w") as f:
        for cid in sorted(list(to_fix)):
            f.write(f"{cid}\n")
    print(f"📝 Sorted IDs saved to scripts/repair_ids.txt")

if __name__ == "__main__":
    main()
