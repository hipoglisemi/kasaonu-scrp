import os
import sys
import json
from datetime import datetime, timedelta, timezone
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Setup path to include project root for src.* imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign
from dotenv import load_dotenv
load_dotenv('.env')

def notify_google_deleted(slugs: list[str]):
    """Silinen kampanyaları Google'a bildir."""
    key_raw = os.getenv("SEARCH_CONSOLE_KEY")
    if not key_raw:
        print("⚠️  SEARCH_CONSOLE_KEY bulunamadı, Google bildirimi atlandı.")
        return False
    try:
        from google.oauth2 import service_account
        key_raw = key_raw.strip()
        if key_raw.startswith("'") and key_raw.endswith("'"):
            key_raw = key_raw[1:-1]
        if key_raw.startswith('"') and key_raw.endswith('"'):
            key_raw = key_raw[1:-1]
            
        key_data = json.loads(key_raw)
        credentials = service_account.Credentials.from_service_account_info(
            key_data,
            scopes=["https://www.googleapis.com/auth/indexing"]
        )
        from googleapiclient.discovery import build
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
        return True
    except Exception as e:
        print(f"⚠️  Google servis hatası: {e}")
        return False

urllib3.disable_warnings()

def is_link_dead(url: str, title: str = "") -> bool:
    """
    Safely pings a tracking URL. Returns True ONLY if we are 100% sure it's dead.
    Tolerates slow banks (retries) and prevents false-positives on 403 Forbidden.
    Supports soft-redirect and soft 404 (generic listing redirect) detection.
    """
    if not url: return False
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
    })
    
    for attempt in range(3):
        try:
            resp = session.get(url, allow_redirects=True, timeout=15, verify=False)
            
            # Explicit 404 means the campaign is definitely gone
            if resp.status_code in [404, 410]:
                return True
                
            final_url = resp.url.lower()
            
            # 💡 CHIPPIN SPECIFIC CHECK: React/Next.js Client-Side Exception Detection
            # When a Chippin campaign is deactivated, it triggers a client-side crash
            if 'chippin.com.tr' in url:
                resp_text = resp.text
                if "client-side exception" in resp_text or "Application error" in resp_text:
                    print(f"      🚨 [Chippin Kırık Link] Client-side exception detected on page! Marking as dead link.")
                    return True
            
            # 💡 ALBARAKA SPECIFIC CHECK: Expired Opaque Images / Status Check
            if 'albaraka.com.tr' in url:
                resp_text = resp.text.lower()
                # 1. Text indicators
                if "sona ermiştir" in resp_text or "sona eren" in resp_text or "süresi dolmuştur" in resp_text or "kampanya-pasif" in resp_text:
                    print(f"      🚨 [Albaraka Pasif] Expired text indicator found on page! Marking as dead link.")
                    return True
                # 2. Image Opacity / Expired class indicator
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for img in soup.find_all('img'):
                        img_classes = " ".join(img.get('class', [])).lower()
                        img_style = (img.get('style') or "").lower()
                        if 'opacity' in img_classes or 'opacity' in img_style or 'pasif' in img_classes or 'passive' in img_classes or 'sona-eren' in img_classes:
                            print(f"      🚨 [Albaraka Opak Görsel] Expired visual style detected! Marking as dead link.")
                            return True
                    # Check main campaign wrapper classes
                    for wrap in soup.select('.campaign-detail, .campaign-image, .detail-image, .campaign-detail-img'):
                        wrap_classes = " ".join(wrap.get('class', [])).lower()
                        if 'pasif' in wrap_classes or 'passive' in wrap_classes or 'opaque' in wrap_classes:
                            print(f"      🚨 [Albaraka Pasif Sınıfı] Expired wrapper class detected! Marking as dead link.")
                            return True
                except Exception:
                    pass
            
            # Extract path without query parameters or trailing slash
            path = ""
            try:
                from urllib.parse import urlparse
                path = urlparse(resp.url.lower()).path.rstrip('/')
            except Exception:
                pass
            
            # 1. AKBANK / WINGS RULE: If it redirects to the generic list, it's silently removed
            if 'axess.com.tr' in url or 'wingscard.com.tr' in url:
                if final_url.endswith('/kampanyalar') or final_url.endswith('/kampanyalar/'):
                    return True
                    
            # 2. TÜRK TELEKOM RULE: If it redirects to the listing or home/portal page
            if 'turktelekom.com.tr' in final_url:
                listing_endpoints = ('/prime-ayricaliklari', '/ayricaliklar', '/kampanyalar', '/firsatlar', '/bireysel')
                if path.endswith(listing_endpoints) or path == "":
                    return True
                    
            # 3. GENERIC LISTING PATH RULE
            generic_listing_paths = (
                '/kampanyalar', '/kampanyalar/', '/firsatlar', '/firsatlar/', 
                '/ayricaliklar', '/ayricaliklar/', '/indirimler', '/indirimler/',
                '/kampanya-listesi', '/kampanyalarimiz'
            )
            if any(final_url.endswith(p) for p in generic_listing_paths):
                return True
                
            # 4. SOFT 404 TITLE HEURISTICS
            # Alternatif Bank uses a generic title tag for all detail pages, which causes false-positives
            if 'alternatifbank.com.tr' in url.lower():
                pass
            else:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    if soup.title and soup.title.string:
                        page_title = soup.title.string.strip().lower()
                        generic_titles = [
                            "kampanyalar", "prime ayrıcalıkları", "tüm kampanyalar", 
                            "fırsatlar", "ayrıcalıklar", "kampanyaları", "axess kampanyalar",
                            "hata", "sayfa bulunamadı", "404", "arama sonuçları"
                        ]
                        if any(gt in page_title for gt in generic_titles) and len(page_title) < 45:
                            if title:
                                # Verify if any specific content words from original title are in the page title
                                words = [w.strip(".,!?\"'") for w in title.lower().split() if len(w) > 3]
                                matches = [w for w in words if w in page_title]
                                if not matches:
                                    return True
                            else:
                                return True
                except Exception:
                    pass
            
            # If it's a 200 OK or 403 Forbidden (Anti-Bot), we MUST assume it's alive to be safe.
            return False
            
        except requests.exceptions.Timeout:
            if attempt == 2: return False
            time.sleep(2)
        except Exception:
            if attempt == 2: return False
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
        active_campaigns = db.query(Campaign).filter(
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
            futures = {executor.submit(is_link_dead, c["url"], c["title"]): c for c in campaigns_to_check}
            for future in as_completed(futures):
                c = futures[future]
                try:
                    if future.result() == True:
                        print(f"   👻 Dead link detected: '{c['title']}' | URL: {c['url']}")
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
                    print(f"   ➔ Deactivated (Dead Link): '{camp.title}' | URL: {camp.tracking_url}")
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
            print(f"💤 Deactivating {len(to_deactivate)} expired campaigns (Soft-Delete for SEO)...")
            for c in to_deactivate:
                c.is_active = False
                print(f"   ➔ Deactivated (Expired): '{c.title}' | End Date: {c.end_date} | URL: {c.tracking_url}")
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
