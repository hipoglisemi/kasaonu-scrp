"""
SEO-friendly slug generator with Turkish character support.
Used to generate URL-safe slugs from campaign titles.
"""
import re
from typing import Optional

# Turkish character mapping
TURKISH_MAP = {
    'ş': 's', 'Ş': 's',
    'ğ': 'g', 'Ğ': 'g',
    'ü': 'u', 'Ü': 'u',
    'ö': 'o', 'Ö': 'o',
    'ç': 'c', 'Ç': 'c',
    'ı': 'i', 'İ': 'i',
}


def generate_slug(title: str) -> str:
    """
    Generate SEO-friendly slug from a Turkish title.
    
    Example:
        "Play ile Market Alışverişine 300 TL'ye Varan Worldpuan!"
        → "play-ile-market-alisverisine-300-tlye-varan-worldpuan"
    """
    if not title:
        return "kampanya"
        
    slug = title
    
    # Replace Turkish characters BEFORE lowering (İ.lower() = i̇, not i)
    for tr_char, en_char in TURKISH_MAP.items():
        slug = slug.replace(tr_char, en_char)
    
    slug = slug.lower()
    
    # Remove apostrophes, quotes, and percent signs
    slug = re.sub(r"['''\"%]", '', slug)
    
    # Replace non-alphanumeric characters with dashes
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    
    # Remove leading/trailing dashes and collapse multiple dashes
    slug = re.sub(r'-+', '-', slug).strip('-')
    
    return slug


def get_unique_slug(title: str, db_session, campaign_model) -> str:
    """
    Generate a unique slug, appending -2, -3, etc. if collision exists.
    """
    base_slug = generate_slug(title)
    slug = base_slug
    counter = 2
    
    while db_session.query(campaign_model).filter(campaign_model.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    
    return slug
