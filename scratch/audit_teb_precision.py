import os
import sys
import urllib.request
import re
from bs4 import BeautifulSoup

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db_session
from src.models import Campaign, Bank, Card
from src.services.text_cleaner import clean_campaign_text

def get_html_content(url: str) -> str:
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        # print(f"⚠️ Failed to fetch {url}: {e}")
        return ""

def audit_teb_precision():
    with get_db_session() as db:
        teb = db.query(Bank).filter(Bank.slug.in_(['teb', 'türk-ekonomi-bankasi'])).first()
        if not teb:
            print("❌ TEB Bank not found!")
            return
            
        teb_card_ids = [c.id for c in db.query(Card).filter(Card.bank_id == teb.id).all()]
        if not teb_card_ids:
            print("❌ No TEB cards found in database!")
            return
            
        # Get active TEB campaigns, limited to 15 to be fast
        campaigns = db.query(Campaign).filter(
            Campaign.card_id.in_(teb_card_ids),
            Campaign.is_active == True
        ).limit(15).all()
        
        print(f"📊 Auditing {len(campaigns)} active TEB campaigns by fetching & cleaning live HTML:")
        print("=" * 100)
        
        mismatch_count = 0
        matches_count = 0
        
        for c in campaigns:
            # Fetch live HTML
            html = get_html_content(c.tracking_url)
            if not html:
                # Fallback to local clean_text if fetch fails
                print(f"⚠️ ID {c.id} ({c.title[:30]}...): Fetch failed, skipping...")
                continue
                
            # Apply our newly added, perfect BS4 clean logic!
            cleaned_text = clean_campaign_text(html, title=c.title)
            text_lower = cleaned_text.lower()
            title_lower = c.title.lower()
            
            db_cards = [x.strip() for x in c.eligible_cards.split(",")] if c.eligible_cards else []
            
            actual_mentions = []
            
            # CEPTETEB Checks
            if "cepteteb" in text_lower or "cepteteb" in title_lower:
                if "cepteteb kredi" in text_lower:
                    actual_mentions.append("CEPTETEB Kredi Kartı")
                elif "cepteteb banka" in text_lower:
                    actual_mentions.append("CEPTETEB Banka Kartı")
                else:
                    actual_mentions.append("CEPTETEB")
            
            # Emekli Kart Checks
            if "emekli" in text_lower or "emekli" in title_lower:
                actual_mentions.append("TEB Emekli Kartı")
                
            # She Card Checks
            if "she card" in text_lower or "she kart" in text_lower or "teb she" in text_lower:
                actual_mentions.append("TEB She Card")
                
            # Sade Kart Checks
            if "sade kart" in text_lower:
                actual_mentions.append("TEB Sade Kart")
                
            # Mastercard logo check
            if "mastercard logolu" in text_lower:
                actual_mentions.append("Mastercard logolu TEB Kredi Kartı")
                
            # TROY logo check
            if "troy logolu" in text_lower:
                actual_mentions.append("TROY logolu TEB Kartı")
                
            # Generic Credit Card / Bonus Checks
            if "bonus" in text_lower or "bonus" in title_lower:
                actual_mentions.append("TEB Bonus Card")
            
            if "bireysel kredi kart" in text_lower:
                if "TEB Bonus Card" not in actual_mentions and "TEB She Card" not in actual_mentions:
                    actual_mentions.append("TEB Bireysel Kredi Kartı")
                    
            if not actual_mentions:
                actual_mentions.append("TEB Kredi Kartı")
                
            # Standardize for comparison
            db_cards_norm = {x.lower().replace("card", "").replace("kartı", "").replace("kart", "").strip() for x in db_cards}
            actual_norm = {x.lower().replace("card", "").replace("kartı", "").replace("kart", "").strip() for x in actual_mentions}
            
            # Allow lenient match if CEPTETEB vs CEPTETEB Kart
            is_mismatch = False
            for act in actual_norm:
                # If an actual card mention is completely missing from db_cards_norm
                found = False
                for db_c in db_cards_norm:
                    if act in db_c or db_c in act:
                        found = True
                        break
                if not found:
                    is_mismatch = True
                    break
                    
            # Check vice-versa
            for db_c in db_cards_norm:
                found = False
                for act in actual_norm:
                    if act in db_c or db_c in act:
                        found = True
                        break
                if not found:
                    is_mismatch = True
                    break
            
            print(f"🆔 ID: {c.id} | Title: {c.title}")
            print(f"🔗 URL: {c.tracking_url}")
            print(f"💾 Stored in DB (eligible_cards): {c.eligible_cards}")
            print(f"🔍 Actual Mentions (Cleaned HTML): {', '.join(actual_mentions)}")
            
            if is_mismatch:
                mismatch_count += 1
                print("🚨 STATUS: MISMATCH")
            else:
                matches_count += 1
                print("✅ STATUS: MATCH (PRECISION VERIFIED)")
            print("-" * 100)
            
        print(f"🏁 TEB Audit Complete. Total Verified Matches: {matches_count} | Mismatches: {mismatch_count}")

if __name__ == "__main__":
    audit_teb_precision()
