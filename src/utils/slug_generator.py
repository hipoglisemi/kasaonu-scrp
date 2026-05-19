"""
SEO-friendly slug generator with Turkish character support.
Used to generate URL-safe slugs from campaign titles.
"""
import re
from urllib.parse import urlparse
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


def extract_slug_from_url(url: str) -> str:
    """
    Extract slug from a bank tracking URL path.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        if not path:
            return ""
        last_part = path.split('/')[-1]
        last_part = re.sub(r'\.(html|htm|aspx|php|jsp)$', '', last_part)
        return generate_slug(last_part)
    except Exception:
        return ""


def get_unique_slug(
    title: str, 
    db_session, 
    campaign_model,
    tracking_url: Optional[str] = None,
    card_name: Optional[str] = None,
    bank_name: Optional[str] = None
) -> str:
    """
    Generate a unique slug following the hierarchy to resolve conflicts.
    1. tracking_url path slugify
    2. url path + card name
    3. url path + card name + bank name
    4. url path + card name + bank name + counter
    """
    # 1. Start with URL path or base title slug
    base_slug = ""
    if tracking_url:
        base_slug = extract_slug_from_url(tracking_url)
    
    if not base_slug:
        base_slug = generate_slug(title)
        
    slug = base_slug
    
    # Check if slug exists in database
    exists = lambda s: db_session.query(campaign_model).filter(campaign_model.slug == s).first() is not None
    
    if not exists(slug):
        return slug
        
    # 2. Append card name
    if card_name:
        slug = generate_slug(f"{base_slug}-{card_name}")
        if not exists(slug):
            return slug
            
    # 3. Append bank name
    if bank_name:
        base_with_card = generate_slug(f"{base_slug}-{card_name}") if card_name else base_slug
        slug = generate_slug(f"{base_with_card}-{bank_name}")
        if not exists(slug):
            return slug
            
    # 4. Append counter suffix
    base_for_counter = slug
    counter = 2
    slug = f"{base_for_counter}-{counter}"
    while exists(slug):
        counter += 1
        slug = f"{base_for_counter}-{counter}"
        
    return slug
