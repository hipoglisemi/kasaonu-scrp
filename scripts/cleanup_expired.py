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

def is_link_dead(url: str, title: str = "") -> tuple:
    """
    Safely pings a tracking URL. Returns (is_dead, final_url).
    Tolerates slow banks (retries) and prevents false-positives on 403 Forbidden.
    Supports soft-redirect and soft 404 (generic listing redirect) detection.
    """
    if not url: return (False, url)
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
    })
    
    for attempt in range(3):
        try:
            resp = session.get(url, allow_redirects=True, timeout=15, verify=False)
            
            # 🔤 Encoding fix: charset belirtmeyen siteler için requests ISO-8859-1 varsayar
            if resp.encoding and resp.encoding.upper() in ('ISO-8859-1', 'LATIN-1', 'LATIN1'):
                resp.encoding = 'utf-8'
            
            # Explicit 404 means the campaign is definitely gone
            if resp.status_code in [404, 410]:
                return (True, resp.url)
                
            final_url = resp.url.lower()

            
            # 💡 CHIPPIN SPECIFIC CHECK: React/Next.js Client-Side Exception Detection
            # When a Chippin campaign is deactivated, it triggers a client-side crash
            # NOTE: DB'deki Chippin URL'leri chippin.com domain'inde (.com.tr değil)
            if 'chippin.com' in url:
                resp_text = resp.text
                # WAF bloğu: "Request Rejected" → bot engeli, kampanya ölü değil
                if "request rejected" in resp_text.lower():
                    return (False, resp.url)  # Güvenli taraf: alive say
                if "client-side exception" in resp_text or "Application error" in resp_text:
                    print(f"      🚨 [Chippin Kırık Link] Client-side exception detected on page! Marking as dead link.")
                    return (True, resp.url)
            
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
                            return (True, final_url)
                    # Check main campaign wrapper classes
                    for wrap in soup.select('.campaign-detail, .campaign-image, .detail-image, .campaign-detail-img'):
                        wrap_classes = " ".join(wrap.get('class', [])).lower()
                        if 'pasif' in wrap_classes or 'passive' in wrap_classes or 'opaque' in wrap_classes:
                            print(f"      🚨 [Albaraka Pasif Sınıfı] Expired wrapper class detected! Marking as dead link.")
                            return (True, final_url)
                except Exception:
                    pass
            
            # 5. HALK / PARAF RULE: Generic list / ana sayfa
            if 'paraf.com.tr' in final_url:
                if final_url.endswith('/kampanyalar') or final_url.endswith('/kampanyalar/') or final_url == 'https://www.paraf.com.tr/' or final_url == 'https://www.paraf.com.tr':
                    return (True, final_url)
                    
            # 6. YAPİKREDİ RULE
            if 'yapikredi.com.tr' in final_url or 'worldcard.com.tr' in final_url:
                if final_url.endswith('/kampanyalar') or final_url.endswith('/kampanyalar/') or final_url.endswith('/kampanya'):
                    return (True, final_url)
                    
            # Check for generic "Kampanya Sona Erdi" texts in HTML content
            if resp.status_code == 200:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    badge = soup.select_one('.campaign-item-box__badge')
                    if badge and 'arşiv' in badge.get_text(strip=True).lower():
                        print(f"      🚨 [Akbank Arşiv] Found 'Arşivden Gösterim' badge. Marking as dead link.")
                        return (True, final_url)
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
            if 'axess.com.tr' in url or 'wingscard.com.tr' in url or 'akbank.com' in url:
                if final_url.endswith('/kampanyalar') or final_url.endswith('/kampanyalar/'):
                    return (True, final_url)
                    
            # 2. TÜRK TELEKOM RULE: If it redirects to the listing or home/portal page
            if 'turktelekom.com.tr' in final_url:
                listing_endpoints = ('/prime-ayricaliklari', '/ayricaliklar', '/kampanyalar', '/firsatlar', '/bireysel')
                if path.endswith(listing_endpoints) or path == "":
                    return (True, final_url)
                    
            # 3. GENERIC LISTING PATH RULE
            generic_listing_paths = (
                '/kampanyalar', '/kampanyalar/', '/firsatlar', '/firsatlar/', 
                '/ayricaliklar', '/ayricaliklar/', '/indirimler', '/indirimler/',
                '/kampanya-listesi', '/kampanyalarimiz'
            )
            if path in generic_listing_paths:
                return (True, final_url)
                
            # 4. IF IT REDIRECTS TO HOMEPAGE (e.g. max 1 slash in path)
            if len(path) <= 1:
                return (True, final_url)

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
                                    return (True, final_url)
                            else:
                                return (True, final_url)
                except Exception:
                    pass
            
            # If it's a 200 OK or 403 Forbidden (Anti-Bot), we MUST assume it's alive to be safe.
            return (False, final_url)
            
        except requests.exceptions.Timeout:
            if attempt == 2: return (False, url)
            time.sleep(2)
        except Exception:
            if attempt == 2: return (False, url)
            time.sleep(2)
            
    return (False, url)

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
    
    print("🔍 Stage 0: Fetching active campaigns for dead link detection (older than 2 days)...")
    campaigns_to_check = []
    with get_db_session() as db:
        # Optimize: Only check campaigns that haven't been seen in the last 2 days.
        # Active campaigns that are found by daily scrapers have their last_seen_at updated daily.
        # We only need to check campaigns that the scrapers didn't find recently to see if their links are dead.
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
        active_campaigns = db.query(Campaign).filter(
            Campaign.is_active == True,
            Campaign.tracking_url.isnot(None),
            (Campaign.last_seen_at < cutoff) | (Campaign.last_seen_at.is_(None))
        ).all()
        # Copy to python list to release DB session
        campaigns_to_check = [{"id": c.id, "url": c.tracking_url, "title": c.title} for c in active_campaigns]
        
    # --- STAGE 0.5: Concurrent HTTP Checks (Outside DB Session to prevent connection drops) ---
    dead_campaign_ids = []
    alive_campaign_ids = []
    redirected_urls = {}
    if campaigns_to_check:
        print(f"🌐 Checking {len(campaigns_to_check)} URLs for 404/removal...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(is_link_dead, c["url"], c["title"]): c for c in campaigns_to_check}
            for future in as_completed(futures):
                c = futures[future]
                try:
                    is_dead, final_url = future.result()
                    if is_dead:
                        print(f"   👻 Dead link detected: '{c['title']}' | URL: {c['url']}")
                        dead_campaign_ids.append(c["id"])
                    else:
                        alive_campaign_ids.append(c["id"])
                        # Store the final resolved URL to check for duplicate redirects
                        from src.utils.scraper_utils import clean_url_for_matching
                        clean_orig = clean_url_for_matching(c["url"])
                        clean_final = clean_url_for_matching(final_url)
                        if clean_orig != clean_final:
                            redirected_urls[c["id"]] = clean_final
                except Exception as e:
                    pass

    # --- STAGE 1 & 2: Database Updates (New DB Session) ---
    with get_db_session() as db:
        # Check if any redirected URL points to an ALREADY EXISTING active campaign's URL
        # If so, the original campaign is a duplicate and should be killed.
        if redirected_urls:
            from src.utils.scraper_utils import clean_url_for_matching
            all_active_camps = db.query(Campaign).filter(Campaign.is_active == True, Campaign.tracking_url.isnot(None)).all()
            active_clean_urls = {c.id: clean_url_for_matching(c.tracking_url) for c in all_active_camps}
            
            for cid, r_url in redirected_urls.items():
                # Is this final URL the tracking URL of ANOTHER campaign?
                for target_id, target_url in active_clean_urls.items():
                    if target_id != cid and target_url == r_url:
                        print(f"   🔄 Redirect Duplicate Detected! ID {cid} redirects to ID {target_id}. Killing {cid}.")
                        dead_campaign_ids.append(cid)
                        break

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

        if alive_campaign_ids:
            print(f"♻️  Updating last_seen_at for {len(alive_campaign_ids)} alive campaigns...")
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            for alive_id in alive_campaign_ids:
                camp = db.query(Campaign).filter(Campaign.id == alive_id).first()
                if camp:
                    camp.last_seen_at = now_utc
            db.flush()
            print(f"✅ Successfully updated last_seen_at for {len(alive_campaign_ids)} campaigns.")
            
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
