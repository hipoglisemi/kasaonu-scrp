import os
import sys
import uuid
from sqlalchemy.orm import joinedload
from src.database import SessionLocal
from src.models import Brand, Campaign, CampaignBrand

# Brands that represent distinct business segments with different sectors
SEGMENTS_TO_UNMERGE = [
    {"name": "Amazon Prime", "parent": "Amazon", "keywords": ["Amazon Prime", "Prime Video", "Amazon Music"]},
    {"name": "Youtube Music", "parent": "Youtube", "keywords": ["Youtube Music"]},
    {"name": "Youtube Premium", "parent": "Youtube", "keywords": ["Youtube Premium"]},
    {"name": "Migros Yemek", "parent": "Migros", "keywords": ["Migros Yemek"]},
    {"name": "Migros Hemen", "parent": "Migros", "keywords": ["Migros Hemen"]},
    {"name": "Getir Yemek", "parent": "Getir", "keywords": ["Getir Yemek"]},
    {"name": "Trendyol Yemek", "parent": "Trendyol", "keywords": ["Trendyol Yemek", "TrendyolYemek"]},
    {"name": "Trendyol Go", "parent": "Trendyol", "keywords": ["Trendyol Go"]},
    {"name": "Apple Music", "parent": "Apple", "keywords": ["Apple Music"]},
    {"name": "Apple TV", "parent": "Apple", "keywords": ["Apple TV", "Apple TV+"]},
    {"name": "Google Cloud", "parent": "Google", "keywords": ["Google Cloud"]},
    {"name": "Google Ads", "parent": "Google", "keywords": ["Google Ads", "Adwords"]},
    {"name": "Google Play", "parent": "Google", "keywords": ["Google Play", "Play Store"]},
    {"name": "Vodafone Yanımda", "parent": "Vodafone", "keywords": ["Vodafone Yanımda"]},
    {"name": "Exxen Spor", "parent": "Exxen", "keywords": ["Exxenspor", "Exxen Spor"]}
]

def run_unmerge():
    db = SessionLocal()
    print("🧹 Starting Brand Segment Un-merging Operation...")
    
    for segment in SEGMENTS_TO_UNMERGE:
        seg_name = segment["name"]
        parent_name = segment["parent"]
        keywords = segment["keywords"]
        
        # 1. Find Parent
        parent = db.query(Brand).filter(Brand.name == parent_name).first()
        if not parent:
            print(f"   ⚠️ Parent '{parent_name}' not found. Skipping {seg_name}.")
            continue
            
        # 2. Check if segment is in parent's aliases
        modified_aliases = [a for a in parent.aliases if a not in keywords and a != seg_name]
        if len(modified_aliases) != len(parent.aliases):
            print(f"   ✂️ Removing {keywords} from '{parent_name}' aliases...")
            parent.aliases = modified_aliases
            db.commit()

        # 3. Create or Find Segment Brand
        seg_brand = db.query(Brand).filter(Brand.name == seg_name).first()
        if not seg_brand:
            print(f"   ➕ Creating new brand: '{seg_name}'")
            slug = seg_name.lower().replace(" ", "-").replace("&", "").replace("+", "plus")
            seg_brand = Brand(
                id=uuid.uuid4(),
                name=seg_name,
                slug=slug,
                is_active=True,
                aliases=keywords
            )
            db.add(seg_brand)
            db.commit()
            db.refresh(seg_brand)
        else:
            print(f"   ℹ️ Segment brand '{seg_name}' already exists.")

        # 4. Campaign Relinking (Find campaigns mentioning the segment and relink to new ID)
        print(f"   🔗 Relinking campaigns for '{seg_name}'...")
        # We need to find campaigns linked to PARENT but mentioning SEGMENT
        campaigns_to_relink = db.query(Campaign).join(CampaignBrand).filter(
            CampaignBrand.brand_id == parent.id
        ).all()
        
        relined_count = 0
        for c in campaigns_to_relink:
            full_text = f"{(c.title or '')} {(c.description or '')} {(c.conditions or '')}".lower()
            if any(k.lower() in full_text for k in keywords):
                # Switch the mapping
                assoc = db.query(CampaignBrand).filter(
                    CampaignBrand.campaign_id == c.id,
                    CampaignBrand.brand_id == parent.id
                ).first()
                if assoc:
                    # Delete old, add new (to avoid PK conflicts if multiple subs)
                    db.delete(assoc)
                    db.flush()
                    
                    new_assoc = CampaignBrand(campaign_id=c.id, brand_id=seg_brand.id)
                    db.add(new_assoc)
                    relined_count += 1
        
        db.commit()
        if relined_count > 0:
            print(f"   ✅ Successfully relinked {relined_count} campaigns to '{seg_name}'.")

    print("\n✨ Brand Segment Un-merging complete.")

if __name__ == "__main__":
    run_unmerge()
