
from typing import Any, Tuple
from sqlalchemy.orm import Session
from src.models import CampaignBlocklist, Campaign
from datetime import datetime, timezone

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

def upsert_campaign(db: Session, campaign: Campaign) -> Tuple[Campaign, str]:
    """
    Saves or updates a campaign. 
    If it was passive (is_active=False), it revives it and requires re-approval.
    Returns (campaign, status) where status is "saved" or "revived".
    """
    from sqlalchemy import func
    
    # 1. Match by EXACT tracking_url across ANY card ID to prevent duplication of the unique bank page
    existing = db.query(Campaign).filter(
        Campaign.tracking_url == campaign.tracking_url
    ).first()
    
    # 2. Fallback: match by Title + Card ID (handles cases where URL changed but title/card remains same)
    if not existing:
        existing = db.query(Campaign).filter(
            func.lower(Campaign.title) == campaign.title.lower(),
            Campaign.card_id == campaign.card_id
        ).first()
    
    if existing:
        status = "saved"
        if existing.is_active is False:
            print(f"   🔄 Reviving passive campaign: {existing.title[:40]}...")
            existing.is_active = True
            existing.is_approved = False  # Require admin re-approval
            existing.cards_audited_at = None
            status = "revived"
            
        # Update fields
        existing.title = campaign.title
        existing.tracking_url = campaign.tracking_url  # Update tracking_url to handle migrations
        existing.slug = campaign.slug                  # Update slug just in case
        existing.reward_text = campaign.reward_text
        existing.reward_value = campaign.reward_value
        existing.reward_type = campaign.reward_type
        existing.description = campaign.description
        existing.conditions = campaign.conditions
        existing.participation = campaign.participation
        existing.eligible_cards = campaign.eligible_cards
        existing.image_url = campaign.image_url
        existing.start_date = campaign.start_date
        existing.end_date = campaign.end_date
        existing.clean_text = campaign.clean_text
        existing.ai_marketing_text = campaign.ai_marketing_text
        existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        
        return existing, status
    else:
        db.add(campaign)
        return campaign, "saved"
