
from typing import Any
from sqlalchemy.orm import Session
from src.models import CampaignBlocklist, Campaign

def is_url_blocked(db: Session, url: str) -> bool:
    """Check if a URL is in the blocklist."""
    try:
        return db.query(CampaignBlocklist).filter(CampaignBlocklist.url == url).first() is not None
    except Exception as e:
        print(f"   ⚠️ Blocklist check error: {e}")
        return False

def should_skip_campaign(db: Session, url: str, card_id: Any = None) -> bool:
    """
    Check if a campaign should be skipped because:
    1. It's in the blocklist
    2. It already exists in the campaigns table (for the given card_id if provided)
    """
    # 1. Blocklist check
    if is_url_blocked(db, url):
        return True
        
    # 2. Existence check
    query = db.query(Campaign).filter(Campaign.tracking_url == url)
    if card_id:
        query = query.filter(Campaign.card_id == card_id)
        
    return query.first() is not None
