
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

def clean_url_for_matching(url: str) -> str:
    """
    Cleans a URL for robust comparison by stripping query parameters,
    trailing slashes, protocols (http/https), and subdomains (www).
    """
    if not url:
        return ""
    # Strip query parameters
    url = url.split("?")[0]
    # Strip trailing slashes
    url = url.rstrip("/")
    # Strip protocols and www
    url = url.replace("https://", "").replace("http://", "")
    url = url.replace("www.", "")
    return url.strip().lower()

def clean_title_for_matching(title: str) -> str:
    """
    Cleans a title for robust comparison by converting to lowercase
    and keeping only alphanumeric characters to ignore minor punctuation differences.
    """
    if not title:
        return ""
    return "".join(c for c in title.lower() if c.isalnum())

def should_skip_campaign(db: Session, url: str, card_id: Any = None) -> bool:
    """
    Check if a campaign should be skipped because:
    1. It's in the blocklist
    2. It already exists in the campaigns table (for the given card_id if provided)
    """
    # 1. Blocklist check
    if is_url_blocked(db, url):
        return True
        
    # 2. Existence check (robust clean URL comparison)
    if url:
        clean_target = clean_url_for_matching(url)
        all_camps = db.query(Campaign).filter(Campaign.tracking_url.isnot(None))
        if card_id:
            all_camps = all_camps.filter(Campaign.card_id == card_id)
        
        for camp in all_camps.all():
            if clean_url_for_matching(camp.tracking_url) == clean_target:
                return True
                
    return False

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
    
    # 1b. Robust Fallback: Match by cleaned tracking_url across ANY card ID
    if not existing and campaign.tracking_url:
        clean_target = clean_url_for_matching(campaign.tracking_url)
        all_camps = db.query(Campaign).filter(Campaign.tracking_url.isnot(None)).all()
        for camp in all_camps:
            if clean_url_for_matching(camp.tracking_url) == clean_target:
                existing = camp
                break
    
    # 2. Match by EXACT Title + Card ID (handles cases where URL changed but title/card remains same)
    if not existing:
        existing = db.query(Campaign).filter(
            func.lower(Campaign.title) == campaign.title.lower(),
            Campaign.card_id == campaign.card_id
        ).first()
        
    # 2b. Robust Fallback: Match by cleaned alphanumeric Title + Card ID
    if not existing:
        clean_target_title = clean_title_for_matching(campaign.title)
        all_card_camps = db.query(Campaign).filter(Campaign.card_id == campaign.card_id).all()
        for camp in all_card_camps:
            if clean_title_for_matching(camp.title) == clean_target_title:
                existing = camp
                break
    
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
