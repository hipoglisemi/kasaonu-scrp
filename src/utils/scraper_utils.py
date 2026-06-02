
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
            
            # Resurrected campaigns always go to approval queue
            existing.is_approved = False
            existing.cards_audited_at = None
            status = "revived"
            
        # Check if only the date was extended (Fuzzy similarity of text >= 92%)
        import re as _re
        import difflib
        
        def normalize_text_for_comparison(text: str) -> str:
            if not text:
                return ""
            # Turkish lowercasing and normalising character differences
            t = text.replace("İ", "i").replace("I", "ı").lower()
            # Remove all digits
            t = _re.sub(r'\d+', '', t)
            # Remove Turkish month names
            months = ["ocak", "şubat", "subat", "mart", "nisan", "mayıs", "mayis", "haziran", 
                      "temmuz", "ağustos", "agustos", "eylül", "eylul", "ekim", "kasım", "kasim", "aralık", "aralik"]
            for m in months:
                t = _re.sub(rf'\b{m}\b', '', t)
            # Remove punctuation and spaces
            t = _re.sub(r'[^a-zıişğüç]', '', t)
            return t

        old_text = existing.clean_text or existing.description
        new_text = campaign.clean_text or campaign.description
        
        # 🛡️ AI FAILURE GUARD: If the scraper payload has zero content (AI failed due to 429),
        # DO NOT update or overwrite the existing database record! Keep the healthy DB data.
        if old_text and not new_text:
            print(f"      🛡️ [AI Kalkanı] AI parsing failed for incoming payload (possibly 429). Shielding database record '{existing.title[:30]}' from being wiped!")
            return existing, "skipped"
            
        is_date_only_ext = False
        if old_text and new_text:
            t1_norm = normalize_text_for_comparison(new_text)
            t2_norm = normalize_text_for_comparison(old_text)
            similarity = 0.0
            if t1_norm and t2_norm:
                similarity = difflib.SequenceMatcher(None, t1_norm, t2_norm).ratio()
            
            if similarity >= 0.92:
                is_date_only_ext = True
                print(f"      🎉 [Date-Only Extension] Similarity is {similarity:.1%}, marking date_extended=True")
        
        existing.date_extended = is_date_only_ext
        
        # 🛡️ STRICT APPROVAL LOCK: ALL campaign updates, including date extensions and revivals,
        # must go to the approval queue for manual editor verification. NO auto-approvals!
        existing.is_approved = False

        existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if is_date_only_ext:
            # 🔒 MEASURE A (Tarih Kilidi): If only the date has changed, STRICTLY update only date-related fields!
            print(f"      🔒 [Tarih Kilidi] Campaign '{existing.title[:30]}' is a date-only extension. Content fields and URL are STRICTLY locked!")
            existing.start_date = campaign.start_date
            existing.end_date = campaign.end_date
            # 🔗 URL Slug Fix: If the bank changed the URL slug (e.g. TEB /akaryakit-iade/ → /akaryakit-kampanyasi/),
            # update tracking_url even in date-lock mode — otherwise the "Katıl" button breaks.
            if campaign.tracking_url and existing.tracking_url != campaign.tracking_url:
                print(f"      🔗 [URL Güncelleme] tracking_url changed even in date-lock: {existing.tracking_url} → {campaign.tracking_url}")
                existing.tracking_url = campaign.tracking_url
        else:
            # Update URLs and Slug ONLY when it's a completely new/modified campaign
            existing.tracking_url = campaign.tracking_url  
            existing.slug = campaign.slug                  
            existing.start_date = campaign.start_date
            existing.end_date = campaign.end_date
            
            def _update_if_better(field_name: str, new_val: Any):
                old_val = getattr(existing, field_name)
                # Convert string values to stripped versions for checking
                old_str = str(old_val).strip() if old_val is not None else ""
                new_str = str(new_val).strip() if new_val is not None else ""
                
                # If existing is populated, but new is empty/junk, reject the new value!
                if old_str and not new_str:
                    print(f"         🛡️ [Kalkan] Rejection: '{field_name}' is already populated in DB. Shielding from empty override.")
                    return
                # Also prevent description/conditions from shrinking to less than 10 chars if old was long
                if field_name in ["description", "conditions"] and len(old_str) > 20 and len(new_str) < 10:
                    print(f"         🛡️ [Kalkan] Rejection: '{field_name}' would shrink from {len(old_str)} to {len(new_str)} chars. Shielding.")
                    return
                    
                setattr(existing, field_name, new_val)

            existing.title = campaign.title
            _update_if_better("reward_text", campaign.reward_text)
            _update_if_better("reward_value", campaign.reward_value)
            _update_if_better("reward_type", campaign.reward_type)
            _update_if_better("description", campaign.description)
            _update_if_better("conditions", campaign.conditions)
            _update_if_better("participation", campaign.participation)
            _update_if_better("eligible_cards", campaign.eligible_cards)
            _update_if_better("image_url", campaign.image_url)
            _update_if_better("clean_text", campaign.clean_text)
            _update_if_better("ai_marketing_text", campaign.ai_marketing_text)
        
        return existing, status
    else:
        # New campaigns are strictly NOT approved by default
        campaign.is_approved = False
        db.add(campaign)
        return campaign, "saved"
