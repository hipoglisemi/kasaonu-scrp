import os # type: ignore
import sys # type: ignore
import json # type: ignore
import hashlib # type: ignore
from datetime import datetime, timedelta
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

def cleanup_campaigns():
    """
    Cleans up expired campaigns with a 90-day retention policy for SEO:
    1. Mark as inactive (isActive=False) if end_date is in the past.
    2. Permanently delete ONLY if end_date is older than 90 days.
    """
    print(f"🧹 Starting SEO-Friendly Campaign Cleanup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    RETENTION_DAYS = 90
    
    with get_db_session() as db:
        today = datetime.now().date()
        retention_cutoff = today - timedelta(days=RETENTION_DAYS)
        
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
            
    print("🏁 Cleanup completed!")

if __name__ == "__main__":
    cleanup_campaigns()
