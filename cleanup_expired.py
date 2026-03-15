import os # type: ignore
import sys # type: ignore
import json # type: ignore
import hashlib # type: ignore
from datetime import datetime, timedelta
import sqlalchemy  # type: ignore
from sqlalchemy import text # type: ignore
from dotenv import sqlalchemy  # type: ignore # pyre-ignore[21]
import dotenv  # type: ignore # pyre-ignore[21]
import google.oauth2  # type: ignore # pyre-ignore[21]
import googleapiclient.discovery  # type: ignore # pyre-ignore[21]
from googleapiclient.discovery import build # type: ignore
from google.oauth2 import service_account # pyre-ignore[21]

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))
try:
    from src.database import get_db_session # type: ignore # pyre-ignore[21]
    from src.models import Campaign # type: ignore # pyre-ignore[21]
except ImportError:
    from database import get_db_session # type: ignore # pyre-ignore[21]
    from models import Campaign # type: ignore # pyre-ignore[21]

dotenv.load_dotenv('.env') # pyre-ignore[16]

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
