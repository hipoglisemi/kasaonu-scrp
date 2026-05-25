import os # type: ignore
import sys # type: ignore
import json # type: ignore
import hashlib # type: ignore
from datetime import datetime, timedelta, timezone
import sqlalchemy  # type: ignore
from sqlalchemy import text # type: ignore
import google.oauth2  # type: ignore # pyre-ignore[21]
import googleapiclient.discovery  # type: ignore # pyre-ignore[21]
from googleapiclient.discovery import build # type: ignore
from google.oauth2 import service_account # pyre-ignore[21]

# Setup path to include project root for src.* imports
project_root = os.getcwd()
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session # type: ignore # pyre-ignore[21]
from src.models import Campaign # type: ignore # pyre-ignore[21]

from dotenv import load_dotenv # type: ignore
load_dotenv('.env') 

def notify_google_deleted(slugs: list[str]):
    """Silinen kampanyaları Google'a bildir."""
    key_raw = os.getenv("SEARCH_CONSOLE_KEY")
    if not key_raw:
        print("⚠️  SEARCH_CONSOLE_KEY bulunamadı, Google bildirimi atlandı.")
        return False
    try:
        # JSON verisindeki olası ekstra tırnakları veya boşlukları temizle
        key_raw = str(key_raw).strip()
        if key_raw.startswith("'") and key_raw.endswith("'"):
            key_raw = key_raw[1:-1] # type: ignore
        if key_raw.startswith('"') and key_raw.endswith('"'):
            key_raw = key_raw[1:-1] # type: ignore
            
        key_data = json.loads(key_raw)
        credentials = service_account.Credentials.from_service_account_info(
            key_data,
            scopes=["https://www.googleapis.com/auth/indexing"]
        )
        service = build("indexing", "v3", credentials=credentials)
        for slug in slugs:
            url = f"https://kartavantaj.com/kampanya/{slug}"
            try:
                service.urlNotifications().publish(
                    body={"url": url, "type": "URL_DELETED"}
                ).execute()
                print(f"🗑️  Google'a silindi bildirimi gönderildi: {url}")
                return True
            except Exception as e:
                print(f"  ❌  Google bildirim hatası ({url}): {e}")
                return False
    except Exception as e:
        print(f"⚠️  Google servis hatası: {e}")
        return False

import requests # type: ignore
import urllib3 # type: ignore
from concurrent.futures import ThreadPoolExecutor, as_completed # type: ignore
import time # type: ignore

urllib3.disable_warnings()

def is_link_dead(url: str) -> bool:
    """
    Safely pings a tracking URL. Returns True ONLY if we are 100% sure it's dead.
    Tolerates slow banks (retries) and prevents false-positives on 403 Forbidden.
    """
    if not url: return False
    
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'})
    
    for attempt in range(3):
        try:
            resp = session.get(url, allow_redirects=True, timeout=15, verify=False)
            
            # Explicit 404 means the campaign is definitely gone
            if resp.status_code == 404:
                return True
                
            final_url = resp.url.lower()
            
            # AKBANK / WINGS RULE: If it redirects to the generic list, it's silently removed
            if 'axess.com.tr' in url or 'wingscard.com.tr' in url:
                if final_url.endswith('/kampanyalar') or final_url.endswith('/kampanyalar/'):
                    return True
            
            # If it's a 200 OK or 403 Forbidden (Anti-Bot), we MUST assume it's alive to be safe.
            return False
            
        except requests.exceptions.Timeout:
            if attempt == 2: return False # Never delete just because a bank is slow
            time.sleep(2)
        except Exception:
            if attempt == 2: return False # Network error, play it safe
            time.sleep(2)
            
    return False

def cleanup_campaigns():
    """
    Cleans up expired campaigns with a 90-day retention policy for SEO:
    0. Mark as inactive if bank removed the URL (Dead Link).
    1. Mark as inactive (isActive=False) if end_date is in the past.
    2. Permanently delete ONLY if end_date is older than 90 days.
    """
    print(f"🧹 Starting SEO-Friendly Campaign Cleanup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    RETENTION_DAYS = 90
    # Calculate today's date in Turkey Timezone (UTC+3) to avoid runner timezone discrepancy
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
    retention_cutoff = today - timedelta(days=RETENTION_DAYS)
    
    # --- STAGE 0: Fetch URLs to Check (Short DB Session) ---
    print("🔍 Stage 0: Fetching active campaigns for dead link detection...")
    campaigns_to_check = []
    with get_db_session() as db:
        active_campaigns = db.query(Campaign.id, Campaign.tracking_url, Campaign.title).filter(
            Campaign.is_active == True,
            Campaign.tracking_url.isnot(None)
        ).all()
        # Copy to python list to release DB session
        campaigns_to_check = [{"id": c.id, "url": c.tracking_url, "title": c.title} for c in active_campaigns]
        
    # --- STAGE 0.5: Concurrent HTTP Checks (Outside DB Session to prevent connection drops) ---
    dead_campaign_ids = []
    if campaigns_to_check:
        print(f"🌐 Checking {len(campaigns_to_check)} URLs for 404/removal...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(is_link_dead, c["url"]): c for c in campaigns_to_check}
            for future in as_completed(futures):
                c = futures[future]
                try:
                    if future.result() == True:
                        print(f"   👻 Dead link detected: {c['title']}")
                        dead_campaign_ids.append(c["id"])
                except Exception as e:
                    pass

    # --- STAGE 1 & 2: Database Updates (New DB Session) ---
    with get_db_session() as db:
        if dead_campaign_ids:
            print(f"💾 Marking {len(dead_campaign_ids)} dead campaigns as passive...")
            for dead_id in dead_campaign_ids:
                camp = db.query(Campaign).filter(Campaign.id == dead_id).first()
                if camp:
                    camp.is_active = False
            db.flush()
            print(f"✅ Successfully deactivated {len(dead_campaign_ids)} dead/removed campaigns.")
        else:
            print("✅ All active campaign links are healthy.")
            
        # --- STAGE 1: Deactivate (Soft-Delete) ---
        to_deactivate = db.query(Campaign).filter(
            Campaign.end_date < today,
            Campaign.is_active == True
        ).all()
        
        if to_deactivate:
            print(f"💤 Deactivating {len(to_deactivate)} expired campaigns (Soft-Delete for SEO).")
            for c in to_deactivate:
                c.is_active = False
            db.flush()
        
        # --- STAGE 2: Permanent Delete (After Retention) ---
        to_delete = db.query(Campaign).filter(
            Campaign.end_date < retention_cutoff
        ).all()
        
        if to_delete:
            count = len(to_delete)
            print(f"🗑️ Found {count} old campaigns past {RETENTION_DAYS} days retention. Deleting permanently.")
            
            slugs_to_delete = [c.slug for c in to_delete]
            
            for c in to_delete:
                db.delete(c)
            
            db.commit()
            print(f"✅ Successfully deleted {count} campaigns from DB.")
            
            # Notify Google ONLY for permanent deletions
            notify_google_deleted(slugs_to_delete)
        else:
            if not to_deactivate:
                print("✅ No campaigns to deactivate or delete.")
            else:
                db.commit()
                print("✅ Deactivation complete. No old campaigns to delete yet.")
            
    print("🏁 Cleanup completed!")

if __name__ == "__main__":
    cleanup_campaigns()
