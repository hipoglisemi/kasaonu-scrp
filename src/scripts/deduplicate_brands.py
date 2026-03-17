"""
Brand Deduplication Script
==========================
1. Tüm marka isimlerini küçük harfe çevirir
2. Normalize ederek duplicate markaları bulur (amazon / amazon.com.tr gibi)
3. Tekrar eden markaların kampanyalarını ana markaya taşır
4. Eski markayı siler (veya is_active=False yapar)

Kullanım: python -m src.scripts.deduplicate_brands [--dry-run]
"""

import sys
import os
import argparse
import re
from typing import List, Tuple, Dict, Optional

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session  # type: ignore
from src.models import Brand, CampaignBrand  # type: ignore
from src.services.brand_normalizer import normalize_brand_name  # type: ignore


def slugify(name: str) -> str:
    """Convert brand name to a slug for comparison."""
    s = name.strip().lower()
    # Remove domain extensions
    s = re.sub(r'\.(com|net|org|tr)(\.tr)?', '', s)
    # Remove common noise
    s = re.sub(r'\s+(market|online|türkiye|turkiye|shop|store|tr)$', '', s)
    # Remove punctuation
    s = re.sub(r'[^a-z0-9ıiğüşöç]', '', s)
    return s


def canonical_key(name: str) -> str:
    """Find the canonical/normalized version of a brand name."""
    normalized = normalize_brand_name(name)
    return slugify(normalized)


def find_duplicate_groups(brands: list) -> List[Tuple]:
    """
    Group brands that normalize to the same canonical key.
    Returns list of (canonical_key, [brand_objects]) tuples where list has > 1 entry.
    """
    groups: Dict[str, list] = {}
    for brand in brands:
        key = canonical_key(brand.name)
        if not key:
            continue
        if key not in groups:
            groups[key] = []
        groups[key].append(brand)

    # Return only groups with duplicates
    duplicates = [(k, v) for k, v in groups.items() if len(v) > 1]
    return duplicates


def pick_canonical_brand(group: list):
    """
    From a group of duplicate brands, pick the canonical one to keep.
    Prefer: 
    - Shortest name (usually the clean version e.g. "Amazon" over "Amazon.com.tr")
    - Most campaigns linked
    """
    # Sort by number of campaign links (desc), then by name length (asc)
    def sort_key(b):
        try:
            campaign_count = len(b.campaigns)
        except Exception:
            campaign_count = 0
        return (-campaign_count, len(b.name))

    sorted_group = sorted(group, key=sort_key)
    return sorted_group[0]


def merge_brands(db, canonical: "Brand", duplicate: "Brand", dry_run: bool = False):
    """
    Move all campaign links from `duplicate` to `canonical`, then delete duplicate.
    """
    # Find campaign_brand rows pointing to duplicate
    dupe_links = db.query(CampaignBrand).filter(
        CampaignBrand.brand_id == duplicate.id
    ).all()

    moved = 0
    skipped = 0
    for link in dupe_links:
        # Check if canonical already has this campaign to avoid duplicates
        existing = db.query(CampaignBrand).filter(
            CampaignBrand.campaign_id == link.campaign_id,
            CampaignBrand.brand_id == canonical.id
        ).first()

        if existing:
            # Just delete the duplicate link
            if not dry_run:
                db.delete(link)
            skipped += 1
        else:
            # Move link to canonical brand
            if not dry_run:
                link.brand_id = canonical.id
            moved += 1

    if not dry_run:
        db.flush()
        db.delete(duplicate)
        db.flush()

    return moved, skipped


def normalize_brand_names_in_db(db, dry_run: bool = False):
    """Lowercase all brand names and update slugs. Skips slugs that would cause collisions."""
    from sqlalchemy.exc import IntegrityError  # type: ignore
    brands = db.query(Brand).all()
    # Build a set of all current slugs (by id) to detect collisions without hitting DB
    existing_slugs: dict = {b.slug: b.id for b in brands}

    updated = 0
    for b in brands:
        # Normalize name using our normalizer
        new_name = normalize_brand_name(b.name)
        new_slug = new_name.lower().replace(' ', '-').replace('.', '-')
        new_slug = re.sub(r'-+', '-', new_slug).strip('-')
        new_slug = new_slug.replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c')
        # strip special chars that don't work in slugs
        new_slug = re.sub(r'[^a-z0-9-]', '-', new_slug)
        new_slug = re.sub(r'-+', '-', new_slug).strip('-')

        name_changed = b.name != new_name
        # Only update slug if new_slug doesn't already belong to a DIFFERENT brand
        slug_collision = new_slug in existing_slugs and existing_slugs[new_slug] != b.id
        slug_changed = b.slug != new_slug and not slug_collision

        if slug_collision:
            # Will be handled by the merge step later
            print(f"  ⚠️  Slug collision skip: '{b.name}' → '{new_name}' (slug '{new_slug}' already used by another brand)")

        if not name_changed and not slug_changed:
            continue

        print(f"  📝 Rename: '{b.name}' → '{new_name}' (slug: {new_slug if slug_changed else b.slug})")
        if not dry_run:
            if name_changed:
                b.name = new_name
            if slug_changed:
                old_slug = b.slug
                existing_slugs.pop(old_slug, None)
                b.slug = new_slug
                existing_slugs[new_slug] = b.id
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                print(f"  ⚠️  Flush failed for '{b.name}', rolling back this brand.")
                continue
        updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(description='Deduplicate Brands in DB')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no DB changes')
    args = parser.parse_args()
    dry_run = args.dry_run

    if dry_run:
        print("🔍 DRY RUN MODE — No changes will be made.\n")
    else:
        print("⚠️  LIVE MODE — Changes will be written to DB!\n")

    db = get_db_session()
    try:
        brands = db.query(Brand).order_by(Brand.name).all()
        print(f"📊 Total brands in DB: {len(brands)}\n")

        # Step 1: Normalize names
        print("╔══════════════════════════════════════╗")
        print("║  STEP 1: Normalizing brand names     ║")
        print("╚══════════════════════════════════════╝")
        updated = normalize_brand_names_in_db(db, dry_run=dry_run)
        if not dry_run:
            db.commit()
        print(f"✅ Normalized {updated} brand names.\n")

        # Re-fetch after normalization
        brands = db.query(Brand).order_by(Brand.name).all()

        # Step 2: Find duplicates
        print("╔══════════════════════════════════════╗")
        print("║  STEP 2: Finding duplicates          ║")
        print("╚══════════════════════════════════════╝")
        duplicate_groups = find_duplicate_groups(brands)
        print(f"Found {len(duplicate_groups)} duplicate groups.\n")

        total_merged = 0
        for canonical_key_str, group in duplicate_groups:
            canonical = pick_canonical_brand(group)
            duplicates = [b for b in group if b.id != canonical.id]

            try:
                campaign_counts = {b.id: len(b.campaigns) for b in group}
            except Exception:
                campaign_counts = {}

            print(f"  🔀 Group: '{canonical_key_str}'")
            print(f"     ✅ Keep   : '{canonical.name}' (id={canonical.id}, campaigns={campaign_counts.get(canonical.id, '?')})")
            for dup in duplicates:
                print(f"     ❌ Merge  : '{dup.name}' (id={dup.id}, campaigns={campaign_counts.get(dup.id, '?')}) → into '{canonical.name}'")
                moved, skipped = merge_brands(db, canonical, dup, dry_run=dry_run)
                print(f"        └→ {moved} campaigns moved, {skipped} already linked (skipped)")
                total_merged += 1

            if not dry_run:
                db.commit()

        print(f"\n✅ Summary:")
        print(f"   Names normalized : {updated}")
        print(f"   Brands merged    : {total_merged}")
        print(f"   DB written       : {'NO (dry-run)' if dry_run else 'YES'}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
