"""
Brand Matcher — shared utility for all scrapers
================================================
Before creating a new Brand record, this module tries to find an existing
one using alias / fuzzy matching so that "amazon.com.tr" resolves to the
existing "Amazon" brand rather than creating a duplicate.

Usage:
    from src.services.brand_matcher import get_or_create_brand
    brand = get_or_create_brand(db, "Amazon.com.tr", brand_cache)
"""

import re
import unicodedata
from typing import Optional

from src.services.brand_normalizer import normalize_brand_name  # type: ignore


def _simplify(name: str) -> str:
    """
    Returns a simplified, comparison-safe key for a brand name.
    Strips domain extensions, punctuation, and common noise words.
    Converts Turkish chars to ASCII equivalents.
    """
    s = name.strip().lower()

    # Remove domain extensions
    s = re.sub(r'\.(com|net|org|tr)(\.tr)?', '', s)

    # Remove common noise suffixes
    s = re.sub(
        r'\s+(market|marketleri|online|türkiye|turkiye|shop|store|tr|classic|classics|collection|collections|group|grubu)$',
        '', s
    )

    # Turkish → ASCII
    tr_map = str.maketrans('ıiğüşöç', 'iigusor c'[0:7])
    # More reliably:
    replacements = [
        ('ı', 'i'), ('İ', 'i'), ('ğ', 'g'), ('Ğ', 'g'),
        ('ü', 'u'), ('Ü', 'u'), ('ş', 's'), ('Ş', 's'),
        ('ö', 'o'), ('Ö', 'o'), ('ç', 'c'), ('Ç', 'c'),
    ]
    for old, new in replacements:
        s = s.replace(old, new)

    # Strip all non-alphanumeric chars for comparison
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


def find_existing_brand(db, name: str, brand_cache: dict) -> Optional[object]:
    """
    Try to find an existing brand that matches `name`.

    Strategy (in priority order):
    1. Direct cache hit (already loaded brands by lowercase name)
    2. Normalized name exact match (e.g. "Amazon.com.tr" → "Amazon")
    3. Simplified key match (e.g. strip domain / suffixes)
    4. Starts-with match (e.g. "Altınyıldız Classic" matches "Altınyıldız")
    5. Slug exact match against DB
    """
    from src.models import Brand  # type: ignore

    # 1. Direct cache hit
    if name.strip().lower() in brand_cache:
        return brand_cache[name.strip().lower()]

    # 2. Normalized name
    normalized = normalize_brand_name(name)
    if normalized.lower() in brand_cache:
        return brand_cache[normalized.lower()]

    # 3. Simplified key match against cache
    simplified_input = _simplify(name)
    if not simplified_input:
        return None

    for cached_name, cached_brand in brand_cache.items():
        if _simplify(cached_name) == simplified_input:
            return cached_brand

    # 4. Starts-with match: "Altınyıldız Classic" starts with "Altınyıldız"
    for cached_name, cached_brand in brand_cache.items():
        simplified_cached = _simplify(cached_name)
        if simplified_input.startswith(simplified_cached) or simplified_cached.startswith(simplified_input):
            if abs(len(simplified_input) - len(simplified_cached)) <= 15:
                return cached_brand

    # 5. DB slug exact match
    slug_to_try = normalized.lower().replace(' ', '-')
    slug_to_try = re.sub(r'[^a-z0-9-]', '', slug_to_try)
    existing = db.query(Brand).filter(Brand.slug == slug_to_try).first()
    if existing:
        brand_cache[existing.name.lower()] = existing
        return existing

    return None


def get_or_create_brand(db=None, name: str = "", brand_cache: dict = {}, sector_id=None, **kwargs) -> Optional[object]:
    """
    Main entry point for scrapers. Returns a Brand object for the given name,
    matching an existing one if possible, or creating a new one.
    """
    # Handle db_session alias
    if db is None:
        db = kwargs.get('db_session')
    
    if db is None:
        raise ValueError("Database session (db or db_session) must be provided")

    from src.models import Brand  # type: ignore
    from sqlalchemy.exc import IntegrityError  # type: ignore

    if not name or not name.strip():
        return None

    # Try matching existing brand first
    existing = find_existing_brand(db, name, brand_cache)
    if existing:
        if not getattr(existing, 'is_active', True):
            print(f"   🚫 Brand '{existing.name}' is blacklisted (is_active=False). Skipping.")
            return None
        return existing

    # None found — create new brand using the normalized name
    normalized = normalize_brand_name(name)
    if not normalized:
        return None

    slug_val = normalized.lower().replace(' ', '-')
    # Turkish char normalization for slug
    for old, new in [('ı', 'i'), ('ğ', 'g'), ('ü', 'u'), ('ş', 's'), ('ö', 'o'), ('ç', 'c')]:
        slug_val = slug_val.replace(old, new)
    slug_val = re.sub(r'[^a-z0-9-]', '-', slug_val)
    slug_val = re.sub(r'-+', '-', slug_val).strip('-')

    brand = Brand(name=normalized, slug=slug_val, is_active=True)
    
    # Use a subtransaction (savepoint) so that an IntegrityError here 
    # doesn't roll back the entire campaign transaction.
    try:
        with db.begin_nested():
            db.add(brand)
            db.flush()
        brand_cache[normalized.lower()] = brand
        print(f"   ➕ New brand: '{normalized}'")
        return brand
    except IntegrityError:
        # Another worker created it, or it was already in DB but missed by cache
        existing = db.query(Brand).filter(Brand.slug == slug_val).first()
        if existing:
            brand_cache[existing.name.lower()] = existing
            if not getattr(existing, 'is_active', True):
                print(f"   🚫 Brand '{existing.name}' is blacklisted (is_active=False). Skipping.")
                return None
        return existing


def get_or_create_brands_list(db=None, names: list = [], brand_cache: dict = {}, sector_id=None, **kwargs) -> list:
    """
    Process a list of brand name strings and return a list of Brand IDs.
    Merges duplicates and skips None results.
    """
    # Handle db_session alias and brand_names alias
    if db is None:
        db = kwargs.get('db_session')
    
    if not names:
        names = kwargs.get('brand_names', [])

    if db is None:
        raise ValueError("Database session (db or db_session) must be provided")

    ids = []
    seen_ids = set()
    for name in names:
        brand = get_or_create_brand(db, name, brand_cache, sector_id)
        if brand and brand.id not in seen_ids:
            ids.append(brand.id)
            seen_ids.add(brand.id)
    return ids
