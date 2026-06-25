
from typing import Any, Tuple
from sqlalchemy.orm import Session
from src.models import CampaignBlocklist, Campaign
from datetime import datetime, timezone
from src.utils.date_utils import update_dates_in_text

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

def normalize_text_for_comparison(text: str) -> str:
    """
    Normalizes HTML content or description text by aggressively removing
    punctuation, numbers, months, and making it lowercase to allow
    for highly accurate fuzzy matching.
    """
    if not text:
        return ""
    import re as _re
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

def have_different_critical_numbers(title1: str, title2: str) -> bool:
    """
    Check if two campaign titles contain different critical numbers (like 1.75 vs 2 vs 2.5),
    excluding calendar year numbers (2020-2030). If they differ in these numbers, they
    are likely different campaigns and should not be merged under fallback matching.
    """
    if not title1 or not title2:
        return False
    import re
    # Normalize commas to dots for decimal comparison
    t1 = title1.replace(',', '.')
    t2 = title2.replace(',', '.')
    
    # Find all numbers (integers or decimals)
    nums1 = set(re.findall(r'\b\d+(?:\.\d+)?\b', t1))
    nums2 = set(re.findall(r'\b\d+(?:\.\d+)?\b', t2))
    
    # Filter out calendar years (2020 to 2030)
    years = {str(y) for y in range(2020, 2031)}
    nums1 = {n for n in nums1 if n not in years}
    nums2 = {n for n in nums2 if n not in years}
    
    if nums1 and nums2 and nums1 != nums2:
        return True
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
        
    # 2b. Month-Aware Fallback: Match by normalized title (strips month names like mayis/haziran)
    # This catches cases like "Tatilsepeti Mayıs Kampanyası" vs "Tatilsepeti Haziran Kampanyası"
    # which are the SAME campaign but with a monthly URL/title rotation.
    if not existing:
        norm_target_title = normalize_text_for_comparison(campaign.title)
        if norm_target_title and len(norm_target_title) > 10:
            all_card_camps = db.query(Campaign).filter(Campaign.card_id == campaign.card_id).all()
            for camp in all_card_camps:
                norm_camp_title = normalize_text_for_comparison(camp.title)
                if norm_camp_title and norm_camp_title == norm_target_title:
                    # Prevent matching if titles contain different reward numbers/multipliers
                    if have_different_critical_numbers(camp.title, campaign.title):
                        continue
                    existing = camp
                    print(f"      🗓️  [Month-Aware Title Match] Found duplicate via normalized title: ID {existing.id} - '{camp.title}' ≈ '{campaign.title}'")
                    break

    # 2c. Robust Fallback: Match by cleaned alphanumeric Title + Card ID
    if not existing:
        clean_target_title = clean_title_for_matching(campaign.title)
        all_card_camps = db.query(Campaign).filter(Campaign.card_id == campaign.card_id).all()
        for camp in all_card_camps:
            if clean_title_for_matching(camp.title) == clean_target_title:
                existing = camp
                break
                
    # 2c. Ultimate Fallback: Match by URL Substring + High Content Similarity
    # This prevents duplicates when the bank completely changes the URL slug (e.g. from -nisan to -mayis)
    # but the campaign title in the DB was manually changed by the user so title checks fail.
    if not existing and campaign.tracking_url and campaign.card_id:
        clean_target_url = clean_url_for_matching(campaign.tracking_url)
        # Avoid running expensive diffs on very short, generic URLs like "kampanyalar"
        if len(clean_target_url) > 20:
            import difflib
            new_text = normalize_text_for_comparison(campaign.clean_text or campaign.description)
            
            # Only proceed if we have enough content to confidently fuzzy match
            if new_text and len(new_text) > 50:
                all_card_camps = db.query(Campaign).filter(
                    Campaign.card_id == campaign.card_id,
                    Campaign.tracking_url.isnot(None)
                ).all()
                
                for camp in all_card_camps:
                    clean_camp_url = clean_url_for_matching(camp.tracking_url)
                    if not clean_camp_url or len(clean_camp_url) <= 20: 
                        continue
                        
                    # If URLs share a significant common prefix or suffix (e.g. -nisan added/removed)
                    if clean_target_url.startswith(clean_camp_url) or clean_camp_url.startswith(clean_target_url):
                        
                        old_text = normalize_text_for_comparison(camp.clean_text or camp.description)
                        if old_text and len(old_text) > 50:
                            sim = difflib.SequenceMatcher(None, new_text, old_text).ratio()
                            if sim >= 0.90:
                                existing = camp
                                print(f"      🎯 [Fuzzy URL+Content Match] Found duplicate via similarity ({sim:.1%}): ID {existing.id} - URL changed to {campaign.tracking_url}")
                                break
    
    if existing:
        status = "saved"
        if existing.is_active is False:
            today_date = datetime.now(timezone.utc).date()
            new_end_date = campaign.end_date
            if isinstance(new_end_date, str):
                try:
                    new_end_date = datetime.strptime(new_end_date.split()[0], "%Y-%m-%d").date()
                except Exception:
                    new_end_date = None
            elif hasattr(new_end_date, 'date'):
                new_end_date = new_end_date.date()

            # 🛡️ AKILLI REVIVE KONTROLÜ:
            # AI kesin bir geçmiş tarih döndürdüyse → banka tarihi güncellememiş, pasif bırak.
            # AI null döndürdüyse (tarih bulunamadı) → belirsiz durum, revive et (benefit of doubt).
            if new_end_date is not None and new_end_date < today_date:
                print(f"   ⏭️ [Akıllı Revive] Kampanya tarihi geçmişte ({new_end_date}) ve AI kesin tarih döndürdü → canlandırılmıyor, döngü engellendi: {existing.title[:40]}")
                return existing, "skipped"

            print(f"   🔄 Reviving passive campaign: {existing.title[:40]}...")
            existing.is_active = True
            
            # Keep track of original approval state so we can restore it if it's just a false alarm
            was_approved_before = existing.is_approved
            
            # Resurrected campaigns temporarily go to approval queue
            existing.is_approved = False
            existing.cards_audited_at = None
            status = "revived"
        else:
            was_approved_before = existing.is_approved
            
        # Check if only the date was extended (Fuzzy similarity of text >= 92%)
        import difflib

        old_text = existing.clean_text or existing.description
        new_text = campaign.clean_text or campaign.description
        
        # 🛡️ AI FAILURE GUARD: If the scraper payload has zero content (AI failed due to 429),
        # DO NOT update or overwrite the existing database record! Keep the healthy DB data.
        if old_text and not new_text:
            print(f"      🛡️ [AI Kalkanı] AI parsing failed for incoming payload (possibly 429). Shielding database record '{existing.title[:30]}' from being wiped!")
            # If we revived it, revert the revive effects
            if status == "revived":
                existing.is_active = False
                existing.is_approved = was_approved_before
            return existing, "skipped"
            
        is_date_only_ext = False
        is_exact_match = False # Content is same, date is same
        
        if old_text and new_text:
            t1_norm = normalize_text_for_comparison(new_text)
            t2_norm = normalize_text_for_comparison(old_text)
            similarity = 0.0
            if t1_norm and t2_norm:
                similarity = difflib.SequenceMatcher(None, t1_norm, t2_norm).ratio()
            
            if similarity >= 0.92:
                if campaign.end_date != existing.end_date:
                    is_date_only_ext = True
                    print(f"      🎉 [Date-Only Extension] Similarity is {similarity:.1%}, date changed. Marking date_extended=True")
                else:
                    is_exact_match = True
                    print(f"      ✅ [Exact Match] Similarity is {similarity:.1%}, but date is exactly same. Not an extension.")
            else:
                # Fallback multi-layered check to prevent false positives from AI/Scraper variations
                cond_desc_old = (existing.conditions or "") + "\n" + (existing.description or "")
                cond_desc_new = (campaign.conditions or "") + "\n" + (campaign.description or "")
                cd_old_norm = normalize_text_for_comparison(cond_desc_old)
                cd_new_norm = normalize_text_for_comparison(cond_desc_new)
                cd_similarity = 0.0
                if cd_old_norm and cd_new_norm:
                    cd_similarity = difflib.SequenceMatcher(None, cd_old_norm, cd_new_norm).ratio()
                
                # Check for matches in reward details
                reward_val_match = (existing.reward_value == campaign.reward_value)
                reward_type_match = (existing.reward_type == campaign.reward_type)
                
                if cd_similarity >= 0.50 and reward_val_match and reward_type_match:
                    if campaign.end_date != existing.end_date:
                        is_date_only_ext = True
                        print(f"      🎉 [Date-Only Extension Fallback] AI conditions similarity is {cd_similarity:.1%}, reward values/types match. Marking date_extended=True")
                    else:
                        is_exact_match = True
                        print(f"      ✅ [Exact Match Fallback] Conditions similarity is {cd_similarity:.1%}, but date is exactly same. Not an extension.")
        
        # Only mark date_extended if the date ACTUALLY changed
        existing.date_extended = is_date_only_ext
        
        # 🔒 APPROVAL LOGIC:
        if is_date_only_ext or is_exact_match:
            # Sadece tarih uzaması veya birebir aynı içerik → onay durumunu eski haline döndür / koru
            existing.is_approved = was_approved_before
            reason = "tarih uzaması" if is_date_only_ext else "birebir aynı içerik"
            print(f"      ✅ [Onay Korundu] {reason} → is_approved={existing.is_approved} korundu.")
            
            # Treat exact matches as date-only extensions for the locking logic (to prevent overwriting columns)
            is_date_only_ext = True 
        else:
            # İçerik gerçekten değiştiyse (date_extended=False ve exact match değilse) → onaya düşür.
            existing.is_approved = False
            print(f"      🔒 [Onay Kilidi] İçerik değişti → onaya düşürüldü.")

        existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if is_date_only_ext:
            # 🔒 MEASURE A (Tarih Kilidi): If only the date has changed, STRICTLY update only date-related fields!
            print(f"      🔒 [Tarih Kilidi] Campaign '{existing.title[:30]}' is a date-only extension. Content fields and URL are STRICTLY locked!")
            
            # 📅 YENİ: Metin içindeki tarihleri otomatik güncelle (Proactive mantığı)
            old_end_date_for_text = existing.end_date
            
            existing.start_date = campaign.start_date
            existing.end_date = campaign.end_date
            
            if old_end_date_for_text and campaign.end_date and old_end_date_for_text != campaign.end_date:
                if existing.conditions:
                    existing.conditions = update_dates_in_text(existing.conditions, old_end_date_for_text, campaign.end_date)
                if existing.description:
                    existing.description = update_dates_in_text(existing.description, old_end_date_for_text, campaign.end_date)
                if existing.participation:
                    existing.participation = update_dates_in_text(existing.participation, old_end_date_for_text, campaign.end_date)
                if existing.ai_marketing_text:
                    existing.ai_marketing_text = update_dates_in_text(existing.ai_marketing_text, old_end_date_for_text, campaign.end_date)
                if existing.clean_text:
                    existing.clean_text = update_dates_in_text(existing.clean_text, old_end_date_for_text, campaign.end_date)
                    
            # 🔗 URL Slug Fix: If the bank changed the URL slug (e.g. TEB /akaryakit-iade/ → /akaryakit-kampanyasi/),
            # update tracking_url even in date-lock mode — otherwise the "Katıl" button breaks.
            if campaign.tracking_url and existing.tracking_url != campaign.tracking_url:
                print(f"      🔗 [URL Güncelleme] tracking_url changed even in date-lock: {existing.tracking_url} → {campaign.tracking_url}")
                existing.tracking_url = campaign.tracking_url
            # 🖼️ Image URL Update: If the bank changed the image URL (or to fix broken extensions),
            # update image_url even in date-lock mode.
            if campaign.image_url and existing.image_url != campaign.image_url:
                print(f"      🖼️ [Görsel Güncelleme] image_url changed even in date-lock: {existing.image_url} → {campaign.image_url}")
                existing.image_url = campaign.image_url
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
        
        # 🛡️ EXPIRY SHIELD FOR NEW CAMPAIGNS:
        # If a completely new campaign is scraped but its end_date is in the past,
        # save it as inactive (is_active = False) by default to keep the database and approval queue clean.
        today_date = datetime.now(timezone.utc).date()
        new_end_date = campaign.end_date
        if isinstance(new_end_date, str):
            try:
                new_end_date = datetime.strptime(new_end_date.split()[0], "%Y-%m-%d").date()
            except Exception:
                new_end_date = None
        elif hasattr(new_end_date, 'date'):
            new_end_date = new_end_date.date()
            
        if new_end_date is not None and new_end_date < today_date:
            print(f"      🛡️ [Tarih Kilidi] Yeni kampanya tarihi geçmişte ({new_end_date}) → pasif olarak kaydediliyor: {campaign.title[:40]}")
            campaign.is_active = False
            
        db.add(campaign)
        return campaign, "saved"
