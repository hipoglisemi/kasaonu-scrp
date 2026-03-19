"""
Brand Merger Service
====================
Utility for merging duplicate brands. Moves all associated campaigns from a
source brand to a target brand, adds the source brand's name to the target's
aliases, and deletes the source brand.
"""

from sqlalchemy.orm import Session
from src.models import Brand, CampaignBrand
import logging

logger = logging.getLogger(__name__)

def merge_brands(db: Session, source_brand_id: str, target_brand_id: str) -> bool:
    """
    Merges source_brand into target_brand.
    """
    if source_brand_id == target_brand_id:
        return False

    source_brand = db.query(Brand).filter(Brand.id == source_brand_id).first()
    target_brand = db.query(Brand).filter(Brand.id == target_brand_id).first()

    if not source_brand or not target_brand:
        logger.error(f"Merge failed: Brand not found. Source: {source_brand_id}, Target: {target_brand_id}")
        return False

    logger.info(f"Merging Brand '{source_brand.name}' ({source_brand.id}) INTO '{target_brand.name}' ({target_brand.id})")

    # 1. Update CampaignBrand relationships
    # Find campaigns that are in source but NOT in target
    source_campaign_ids = [cb.campaign_id for cb in source_brand.campaigns]
    target_campaign_ids = set(cb.campaign_id for cb in target_brand.campaigns)

    for campaign_id in source_campaign_ids:
        if campaign_id not in target_campaign_ids:
            # Move relationship to target
            cb = db.query(CampaignBrand).filter(
                CampaignBrand.brand_id == source_brand_id,
                CampaignBrand.campaign_id == campaign_id
            ).first()
            if cb:
                cb.brand_id = target_brand_id
        else:
            # Campaign already exists in target, just delete the relationship from source
            cb = db.query(CampaignBrand).filter(
                CampaignBrand.brand_id == source_brand_id,
                CampaignBrand.campaign_id == campaign_id
            ).first()
            if cb:
                db.delete(cb)

    # 2. Add source name and aliases to target aliases
    new_aliases = set(target_brand.aliases or [])
    new_aliases.add(source_brand.name)
    if source_brand.aliases:
        for alias in source_brand.aliases:
            new_aliases.add(alias)
    
    target_brand.aliases = list(new_aliases)

    # 3. Delete source brand
    db.delete(source_brand)

    try:
        db.commit()
        logger.info(f"Successfully merged '{source_brand.name}' into '{target_brand.name}'")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to commit merge: {e}")
        return False
