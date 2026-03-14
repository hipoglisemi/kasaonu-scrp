import os
import sys
import json
from datetime import datetime, timedelta
from sqlalchemy import text
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))
from database import get_db_session
from models import Campaign

load_dotenv('.env')

def notify_google_deleted(slugs: list[str]):
    """Silinen kampanyaları Google'a bildir."""
    key_raw = os.getenv("SEARCH_CONSOLE_KEY")
    if not key_raw:
        print("⚠️  SEARCH_CONSOLE_KEY bulunamadı, Google bildirimi atlandı.")
        return
    try:
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
            except Exception as e:
                print(f"  ❌  Google bildirim hatası ({url}): {e}")
    except Exception as e:
        print(f"⚠️  Google servis hatası: {e}")

def cleanup_campaigns():
    """
    Cleans up expired campaigns:
    Immediately deletes campaigns where end_date is in the past.
    """
    print(f"🧹 Starting Campaign Cleanup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    with get_db_session() as db:
        today = datetime.now().date()
        
        # Immediate deletion of expired campaigns
        to_delete = db.query(Campaign).filter(
            Campaign.end_date < today
        ).all()
        
        if to_delete:
            count = len(to_delete)
            print(f"🗑️ Found {count} expired campaigns to delete (ended before {today}).")
            
            # Slug'ları topla
            slugs_to_delete = [c.slug for c in to_delete]
            
            for c in to_delete:
                db.delete(c)
            
            db.commit()
            print(f"✅ Successfully deleted {count} expired campaigns.")
            
            # Google'a bildir
            notify_google_deleted(slugs_to_delete)
        else:
            print("✅ No expired campaigns to delete.")
            
    print("🏁 Cleanup completed!")

if __name__ == "__main__":
    cleanup_campaigns()
