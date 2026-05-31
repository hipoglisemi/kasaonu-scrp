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
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        key_raw = key_raw.strip()
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
            if attempt == 2: return False # Never delete just because a bank is slow
            time.sleep(2)
        except Exception:
            if attempt == 2: return False # Network error, play it safe
            time.sleep(2)
            
    return False

import re
from google.genai import types # type: ignore
from src.utils.gemini_client import generate_with_rotation # type: ignore

def clean_html_to_text(html: str) -> str:
    """Removes script, style, nav, and other HTML tags to produce clean text."""
    if not html:
        return ""
    # remove script, style, head, nav, footer, etc.
    text = re.sub(r'<(script|style|head|nav|footer)[^>]*>([\s\S]*?)<\/\1>', ' ', html)
    # strip other HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # compress whitespaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:8000] # Limit to 8000 characters to keep prompt/tokens tiny

def extract_end_date_via_ai(title: str, html: str) -> str | None:
    """
    Extracts only the campaign end date from the campaign HTML text using Gemini.
    Returns date string in YYYY-MM-DD format, or None if not found/error.
    """
    clean_text = clean_html_to_text(html)
    if not clean_text:
        return None
        
    system_instruction = (
        "Sen KartAvantaj projesinde sadece kampanya bitiş tarihlerini tespit eden uzman bir veri analistisin.\n"
        "Gönderilen metni analiz ederek kampanyanın son geçerlilik tarihini (bitiş tarihini) bulmalısın.\n\n"
        "Kurallar:\n"
        "1. Tarihi YYYY-MM-DD formatında döndür.\n"
        "2. Metinde açıkça yazan kampanya bitiş tarihini tespit et. (Örnek: '30 Haziran 2026', '31.12.2026' vb.)\n"
        "3. Çıktıyı her zaman belirtilen JSON formatında ver.\n"
    )
    
    prompt = f"""
KAMPANYA BAŞLIĞI: {title}
KAMPANYA SAYFA METNİ:
---
{clean_text}
---

GÖREV: Sayfa metnini ve kampanya başlığını inceleyerek kampanyanın son geçerlilik tarihini tespit et. Çıktıyı kesinlikle aşağıdaki JSON şemasına göre üret:

```json
{{
  "end_date": "YYYY-MM-DD" // Tespit edilen tarih (örn. "2026-06-30"), eğer kesin olarak bulunamadıysa null.
}}
```
"""
    config = types.GenerateContentConfig(
        temperature=0.0,
        top_p=0.1,
        top_k=1,
        response_mime_type="application/json",
        system_instruction=system_instruction
    )
    
    try:
        # We reuse the robust key-rotating Gemini client here
        result_str = generate_with_rotation(
            prompt=prompt,
            model="models/gemini-3.1-flash-lite",
            config=config
        )
        
        if not result_str:
            return None
            
        cleaned_result = result_str.strip()
        if cleaned_result.startswith("```"):
            lines = cleaned_result.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_result = "\n".join(lines).strip()
            
        data = json.loads(cleaned_result)
        return data.get("end_date")
    except Exception as e:
        print(f"      ⚠️  Tarih çıkartma hatası: {e}")
        return None

def proactive_expiry_audit():
    """
    Checks campaigns expiring soon (within next 3 days or today).
    Fetches their tracking URL and parses them with AI to get the actual end_date.
    If a date in the future (later than current end_date) is found, updates it.
    This prevents unnecessary deactivations and rescraping/AI parsing cost.
    """
    print("🕰️ Stage -1: Starting Proactive Expiry Audit (Grace Period check via AI)...")
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
    audit_end = today + timedelta(days=3)
    
    # Fetch campaigns expiring soon
    campaigns_to_audit = []
    try:
        with get_db_session() as db:
            soon_expiring = db.query(Campaign).filter(
                Campaign.is_active == True,
                Campaign.end_date >= today,
                Campaign.end_date <= audit_end,
                Campaign.tracking_url.isnot(None)
            ).all()
            
            campaigns_to_audit = [
                {
                    "id": c.id,
                    "url": c.tracking_url,
                    "title": c.title,
                    "end_date": c.end_date
                }
                for c in soon_expiring
            ]
    except Exception as e:
        print(f"   ⚠️ Error fetching soon expiring campaigns: {e}")
        return
        
    if not campaigns_to_audit:
        print("✅ No campaigns expiring within the next 3 days.")
        return
        
    print(f"🔍 Found {len(campaigns_to_audit)} campaigns expiring soon. Checking for extension using AI...")
    
    # Sort campaigns to prioritize those expiring earliest
    campaigns_to_audit.sort(key=lambda x: x["end_date"])
    
    # Capping AI audits per run to prevent 6-hour GitHub Actions timeout
    # Increased to 2000 because we process AI parsing in parallel now!
    MAX_AUDITS_PER_RUN = 2000
    if len(campaigns_to_audit) > MAX_AUDITS_PER_RUN:
        print(f"⚡ Capping AI audits to the top {MAX_AUDITS_PER_RUN} soonest-expiring campaigns to prevent workflow timeout.")
        campaigns_to_audit = campaigns_to_audit[:MAX_AUDITS_PER_RUN]
    extended_count = 0
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'})
    
    # Fetch HTML pages in parallel first to speed up the network bottleneck
    print(f"🌐 Fetching {len(campaigns_to_audit)} campaign pages in parallel...")
    campaigns_with_html = []
    
    def fetch_html(c):
        try:
            resp = session.get(c["url"], allow_redirects=True, timeout=15, verify=False)
            if resp.status_code == 200:
                return {**c, "html": resp.text}
        except Exception:
            pass
        return None
        
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_html, c) for c in campaigns_to_audit]
        for future in as_completed(futures):
            res = future.result()
            if res:
                campaigns_with_html.append(res)
                
    print(f"📥 Successfully fetched {len(campaigns_with_html)} pages. Starting AI parsing in parallel...")
    
    import threading
    extended_lock = threading.Lock()
    
    def audit_single_campaign(c):
        nonlocal extended_count
        url = c["url"]
        current_end = c["end_date"]
        html = c["html"]
        try:
            # 🕰️ Rate Limit Staggering: Introduce a small safe random delay (1.0 to 4.0 seconds) 
            # to make sure parallel threads don't make concurrent Gemini requests at the exact same millisecond!
            import random
            import time
            time.sleep(random.uniform(1.0, 4.0))
            
            # Call dedicated lightweight AI date extractor helper
            ai_end_date_str = extract_end_date_via_ai(c["title"], html)
            if not ai_end_date_str:
                return False
                
            try:
                latest_date = datetime.strptime(ai_end_date_str, "%Y-%m-%d").date()
            except ValueError:
                return False
            
            # Safety range: must be strictly later than current_end and no more than 1 year in the future
            if latest_date > current_end and latest_date <= today + timedelta(days=365):
                print(f"   🎉 Campaign Extended via AI! '{c['title']}'")
                print(f"      Old End Date: {current_end} ➔ New End Date: {latest_date}")
                
                # Update in DB
                with get_db_session() as db:
                    db_camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                    if db_camp:
                        db_camp.end_date = latest_date
                        db_camp.updated_at = datetime.now()
                        db.commit()
                        with extended_lock:
                            extended_count += 1
                        return True
        except Exception as e:
            print(f"   ⚠️ Error auditing {c['title']} with AI: {e}")
        return False
        
    # Parallel AI Parsing using ThreadPoolExecutor with 3 workers.
    # Staggered with random delays inside the thread function to stay strictly under the 15 RPM limit.
    with ThreadPoolExecutor(max_workers=3) as executor:
        ai_futures = [executor.submit(audit_single_campaign, c) for c in campaigns_with_html]
        for future in as_completed(ai_futures):
            pass
            
    print(f"✅ Proactive Expiry Audit complete. Extended {extended_count} campaigns.")

def cleanup_campaigns():
    """
    Cleans up expired campaigns with a 90-day retention policy for SEO:
    -1. Run Proactive Grace Period Expiry Audit to catch and extend campaigns before they expire.
    0. Mark as inactive if bank removed the URL (Dead Link).
    1. Mark as inactive (isActive=False) if end_date is in the past.
    2. Permanently delete ONLY if end_date is older than 90 days.
    """
    print(f"🧹 Starting SEO-Friendly Campaign Cleanup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run proactive grace period audit first
    proactive_expiry_audit()
    
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
