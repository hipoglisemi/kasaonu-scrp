"""
merge_slug_duplicates.py
========================
After deduplicate_brands.py runs, some ALL-CAPS / .com.tr duplicates remain
because two brands would normalize to the same slug.

This script:
1. Finds all pairs of brands where one's normalized slug == another's slug
2. Keeps the brand with the MOST campaigns (or whose name has no special chars)
3. Moves all CampaignBrand rows to the winner and deletes the loser

Run: python3 -m src.scripts.merge_slug_duplicates [--dry-run]
"""

import sys
import os
import re
import argparse

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session  # type: ignore
from src.models import Brand, CampaignBrand  # type: ignore
from src.services.brand_normalizer import normalize_brand_name  # type: ignore


def to_target_slug(name: str) -> str:
    """Compute what slug a brand name WOULD have after normalization."""
    normalized = normalize_brand_name(name)
    slug = normalized.lower().replace(' ', '-').replace('.', '-')
    # Turkish char normalization
    for old, new in [('ı', 'i'), ('ğ', 'g'), ('ü', 'u'), ('ş', 's'), ('ö', 'o'), ('ç', 'c')]:
        slug = slug.replace(old, new)
    slug = re.sub(r'[^a-z0-9-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug


def campaign_count(db, brand) -> int:
    return db.query(CampaignBrand).filter(CampaignBrand.brand_id == brand.id).count()


def pick_winner(db, a, b):
    """Return (winner, loser) — prefer more campaigns, then cleaner name."""
    ca = campaign_count(db, a)
    cb = campaign_count(db, b)
    if ca >= cb:
        return a, b
    return b, a


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    dry_run = args.dry_run

    if dry_run:
        print("🔍 DRY RUN — no changes written.\n")
    else:
        print("⚠️  LIVE MODE — writing to DB!\n")

    db = get_db_session()
    try:
        brands = db.query(Brand).order_by(Brand.name).all()
        print(f"📊 Total brands: {len(brands)}")

        # Group by target slug
        target_slug_map: dict = {}
        for b in brands:
            ts = to_target_slug(b.name)
            if not ts:
                continue
            if ts not in target_slug_map:
                target_slug_map[ts] = []
            target_slug_map[ts].append(b)

        # Find groups with more than one brand
        duplicates = {k: v for k, v in target_slug_map.items() if len(v) > 1}
        print(f"🔀 Found {len(duplicates)} slug groups with duplicates.\n")

        total_merged: int = 0
        total_campaigns_moved: int = 0

        for slug, group in duplicates.items():
            # Pick canonical (most campaigns)
            sorted_group = sorted(group, key=lambda b: (-campaign_count(db, b), len(b.name)))
            canonical = sorted_group[0]
            to_delete = sorted_group[1:]

            c_count = campaign_count(db, canonical)
            print(f"  🏷️  '{slug}' ({len(group)} brands)")
            print(f"     ✅ Keep  : '{canonical.name}' ({c_count} campaigns)")

            for dup in to_delete:
                d_count = campaign_count(db, dup)
                print(f"     ❌ Merge : '{dup.name}' ({d_count} campaigns) → '{canonical.name}'")

                if not dry_run:
                    # Move campaign links
                    links = db.query(CampaignBrand).filter(CampaignBrand.brand_id == dup.id).all()
                    moved: int = 0
                    for link in links:
                        exists = db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == link.campaign_id,
                            CampaignBrand.brand_id == canonical.id
                        ).first()
                        if exists:
                            db.delete(link)
                        else:
                            link.brand_id = canonical.id
                            moved = int(moved) + 1
                    db.flush()
                    db.delete(dup)
                    db.flush()
                    total_campaigns_moved = int(total_campaigns_moved) + moved
                    print(f"        └→ {moved} campaign links moved")

                total_merged = int(total_merged) + 1

        if not dry_run:
            db.commit()

        print(f"\n✅ Summary:")
        print(f"   Brands merged        : {total_merged}")
        print(f"   Campaign links moved : {total_campaigns_moved}")
        print(f"   DB written           : {'NO (dry-run)' if dry_run else 'YES'}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
