import os
import sys
import json
from datetime import datetime, timedelta, timezone
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

# Setup path to include project root for src.* imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign
from src.services.text_cleaner import clean_campaign_text
from dotenv import load_dotenv
load_dotenv('.env')

urllib3.disable_warnings()

import re
from google.genai import types # type: ignore
from src.utils.gemini_client import generate_with_rotation

def clean_html_to_text(html: str, title: str = "") -> str:
    """
    Properly cleans HTML using the centralized text_cleaner pipeline.
    Includes bank-specific noise removal, footer/nav stripping, boilerplate chopping.
    This replaces the old naive regex-based stripper.
    """
    if not html:
        return ""
    return clean_campaign_text(html, title=title or None)

# Türkçe ay isimleri (büyük harf başlangıç)
_TR_MONTHS = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
    5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
    9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}
_TR_MONTHS_LOWER = {v.lower(): k for k, v in _TR_MONTHS.items()}
# Türkçe ay + iyelik ekleri (Mayıs'a, Haziran'a, Temmuz'a vb.)
_TR_MONTH_VARIANTS = {
    "ocak": ["ocak", "ocakta", "ocağa", "ocağın"],
    "şubat": ["şubat", "şubatta", "şubata", "şubatın"],
    "mart": ["mart", "martta", "marta", "martın"],
    "nisan": ["nisan", "nisanda", "nisana", "nisanın", "nisanın"],
    "mayıs": ["mayıs", "mayısın", "mayısa", "mayıs'a", "mayıs'ın"],
    "haziran": ["haziran", "haziranın", "hazirana", "haziran'a", "haziran'ın"],
    "temmuz": ["temmuz", "temmuzun", "temmuza", "temmuz'a", "temmuz'un"],
    "ağustos": ["ağustos", "ağustosun", "ağustosa", "ağustos'a"],
    "eylül": ["eylül", "eylülün", "eylüle", "eylül'e", "eylül'ün"],
    "ekim": ["ekim", "ekimin", "ekime", "ekim'e"],
    "kasım": ["kasım", "kasımın", "kasıma", "kasım'a"],
    "aralık": ["aralık", "aralığın", "aralığa", "aralık'a"],
}

def update_dates_in_text(text: str, old_end_date, new_end_date) -> str:
    """
    Conditions gibi metinlerdeki eski bitiş tarihini yeni tarihle değiştirir.
    Desteklenen formatlar:
      - "8 Haziran 2026"  → "9 Temmuz 2026"
      - "08.06.2026"      → "09.07.2026"
      - "2026-06-08"      → "2026-07-09"
      - "Haziran 2026'ya kadar" → "Temmuz 2026'ya kadar"
    """
    if not text or not old_end_date or not new_end_date:
        return text

    old_day   = old_end_date.day
    old_month = old_end_date.month
    old_year  = old_end_date.year
    new_day   = new_end_date.day
    new_month = new_end_date.month
    new_year  = new_end_date.year

    old_month_tr = _TR_MONTHS[old_month]
    new_month_tr = _TR_MONTHS[new_month]

    result = text

    # 1. ISO format: 2026-06-08 → 2026-07-09
    result = result.replace(
        f"{old_year}-{old_month:02d}-{old_day:02d}",
        f"{new_year}-{new_month:02d}-{new_day:02d}"
    )

    # 2. Noktalı format: 08.06.2026 → 09.07.2026
    result = result.replace(
        f"{old_day:02d}.{old_month:02d}.{old_year}",
        f"{new_day:02d}.{new_month:02d}.{new_year}"
    )
    result = result.replace(
        f"{old_day}.{old_month}.{old_year}",
        f"{new_day}.{new_month}.{new_year}"
    )

    # 3. Türkçe format: "8 Haziran 2026" veya "8 Haziran" → "9 Temmuz 2026" / "9 Temmuz"
    if old_month_tr != new_month_tr or old_day != new_day or old_year != new_year:
        # Tam tarih: gün + ay + yıl
        result = re.sub(
            rf'\b{old_day}\s+{old_month_tr}\s+{old_year}\b',
            f"{new_day} {new_month_tr} {new_year}",
            result, flags=re.IGNORECASE
        )
        # Sadece gün + ay (yılsız)
        result = re.sub(
            rf'\b{old_day}\s+{old_month_tr}\b(?!\s+\d{{4}})',
            f"{new_day} {new_month_tr}",
            result, flags=re.IGNORECASE
        )
        # Sadece ay + yıl (günsüz, ör: "Haziran 2026'ya kadar")
        if old_month != new_month:
            result = re.sub(
                rf'\b{old_month_tr}\b',
                new_month_tr,
                result, flags=re.IGNORECASE
            )

    return result

def extract_dates_via_ai(title: str, clean_text: str, key_index: int = 1):
    """
    Extracts campaign start and end dates from the campaign HTML text using Gemini.
    Returns a dict with 'start_date' and 'end_date' keys, values are date strings in YYYY-MM-DD or None.
    key_index: 1-based API key index this worker should start from.
    """
    if not clean_text:
        return {"start_date": None, "end_date": None}
        
    system_instruction = (
        "Sen KartAvantaj projesinde kampanya başlangıç ve bitiş tarihlerini tespit eden uzman bir veri analistisin.\n"
        "Gönderilen metni analiz ederek kampanyanın başlangıç ve son geçerlilik (bitiş) tarihlerini bulmalısın.\n\n"
        "ÇOK ÖNEMLİ GÜVENLİK KURALLARI:\n"
        "1. Eğer metinde kampanyanın bittiğine, yayından kaldırıldığına dair bir ibare varsa ('Kampanya sona ermiştir', 'Süresi doldu', 'Sayfa bulunamadı', '404' vb.) KESİNLİKLE her iki tarihi de null döndür.\n"
        "2. Eğer metin tek bir kampanyayı değil, birçok farklı kampanyayı listeliyorsa (genel banka anasayfasına yönlendirilmişse) null döndür.\n"
        "3. Sadece ve sadece metin aktif bir kampanyadan bahsediyorsa tarihleri YYYY-MM-DD formatında döndür.\n"
        "4. Çıktıyı her zaman belirtilen JSON formatında ver.\n"
    )
    
    prompt = f"""
KAMPANYA BAŞLIĞI: {title}
KAMPANYA SAYFA METNİ:
---
{clean_text}
---

GÖREV: Sayfa metnini ve kampanya başlığını inceleyerek kampanyanın başlangıç ve bitiş tarihlerini tespit et. Çıktıyı kesinlikle aşağıdaki JSON şemasına göre üret:

```json
{{
  "start_date": "YYYY-MM-DD", // Tespit edilen başlangıç tarihi (örn. "2026-06-01"), eğer kesin olarak bulunamadıysa null.
  "end_date": "YYYY-MM-DD" // Tespit edilen bitiş tarihi (örn. "2026-06-30"), eğer kesin olarak bulunamadıysa null.
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
        result_str = generate_with_rotation(
            prompt=prompt,
            model="models/gemma-4-31b-it",
            config=config,
            key_indices=[key_index]  # Her işçi kendi anahtarından başlar
        )
        
        if not result_str:
            return {"start_date": None, "end_date": None}
            
        cleaned_result = result_str.strip()
        if cleaned_result.startswith("```"):
            lines = cleaned_result.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_result = "\n".join(lines).strip()
            
        # Clean any single-quote malformations directly on this quick response
        if "'" in cleaned_result:
            cleaned_result = cleaned_result.replace("'", '"')
            
        data = json.loads(cleaned_result)
        return {
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date")
        }
    except Exception as e:
        print(f"      ⚠️  Tarih çıkartma hatası: {e}")
        return {"start_date": None, "end_date": None}


def proactive_expiry_audit(max_audits=2000):
    """
    Checks campaigns expiring TODAY.
    Fetches their tracking URL and parses them with AI to get the actual end_date.
    If a date in the future (later than current end_date) is found, updates it.
    This prevents unnecessary deactivations and rescraping/AI parsing cost.
    """
    print("🕰️ Starting Proactive Expiry Audit (Grace Period check via AI)...")
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
    
    # Fetch campaigns expiring strictly today
    campaigns_to_audit = []
    try:
        with get_db_session() as db:
            soon_expiring = db.query(Campaign).filter(
                Campaign.is_active == True,
                Campaign.end_date >= today,                     # Bugün biten kampanyalar
                Campaign.end_date <= today + timedelta(days=1), # ve Yarın biten kampanyalar
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
    
    # Cap audits per run to protect API quotas (default 150)
    if len(campaigns_to_audit) > max_audits:
        print(f"⚡ Capping AI audits to the top {max_audits} soonest-expiring campaigns.")
        campaigns_to_audit = campaigns_to_audit[:max_audits]
        
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
                final_url = resp.url  # Redirect sonrası gerçek URL
                url_changed = final_url.rstrip("/") != c["url"].rstrip("/")
                if url_changed:
                    print(f"   🔗 [URL Redirect] #{c['id']} | {c['url']} → {final_url}")
                return {**c, "html": resp.text, "final_url": final_url, "url_changed": url_changed}
        except Exception:
            pass
        return None
        
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_html, c) for c in campaigns_to_audit]
        for future in as_completed(futures):
            res = future.result()
            if res:
                campaigns_with_html.append(res)
                 
    print(f"📥 Successfully fetched {len(campaigns_with_html)} pages. Starting AI parsing with 9 parallel workers...")

    extended_count = 0
    processed_count = 0
    lock = threading.Lock()
    total = len(campaigns_with_html)

    NUM_WORKERS = 8  # 8 işçi × 8 anahtar, her biri kendi key'ine kilitli

    def audit_one(args):
        """Audit a single campaign: sleep → AI parse → DB update. Thread-safe."""
        c, worker_idx = args
        # Her işçiye farklı anahtar: işçi 0→Key #1, işçi 1→Key #2, ..., işçi 8→Key #9
        key_index = (worker_idx % NUM_WORKERS) + 1
        current_end = c["end_date"]
        try:
            time.sleep(5.0)

            # ✅ Düzgün temizlenmiş metin: text_cleaner pipeline'ından geçir
            clean_text = clean_html_to_text(c["html"], title=c.get("title", ""))
            ai_dates = extract_dates_via_ai(c["title"], clean_text, key_index=key_index)

            ai_start_date_str = ai_dates.get("start_date")
            ai_end_date_str = ai_dates.get("end_date")

            if not ai_end_date_str:
                print(f"   ❌ No end date found | ID: #{c['id']} | {c['title'][:50]}")
                return False

            try:
                latest_date = datetime.strptime(ai_end_date_str, "%Y-%m-%d").date()
            except ValueError:
                print(f"   ❌ Malformed end date from AI: {ai_end_date_str} | ID: #{c['id']}")
                return False

            # Inferred start date fallback if none is provided
            latest_start_date = None
            if ai_start_date_str:
                try:
                    latest_start_date = datetime.strptime(ai_start_date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            
            if not latest_start_date:
                # Fallback: start date becomes today (similar to AI parser logic)
                latest_start_date = today

            # Safety: must be strictly later than current end, max 1 year ahead
            if latest_date > current_end and latest_date <= today + timedelta(days=365):
                print(f"   🎉 Extended! #{c['id']} | {current_end} ➔ {latest_date} (Start: {latest_start_date}) | {c['title'][:50]}")
                with get_db_session() as db:
                    db_camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                    if db_camp:
                        db_camp.start_date = latest_start_date
                        db_camp.end_date = latest_date
                        # ✅ Düzgün temizlenmiş metni kaydet (eski ham metin yerine)
                        if clean_text and len(clean_text) > 100:
                            db_camp.clean_text = clean_text
                        db_camp.date_extended = True
                        db_camp.is_approved = False
                        db_camp.updated_at = datetime.now()

                        # 📅 Conditions ve description metnindeki eski tarihleri güncelle
                        if db_camp.conditions:
                            updated_conditions = update_dates_in_text(
                                db_camp.conditions, current_end, latest_date
                            )
                            if updated_conditions != db_camp.conditions:
                                print(f"   📅 [Conditions Tarihi Güncellendi] #{c['id']}")
                                db_camp.conditions = updated_conditions
                        if db_camp.description:
                            updated_description = update_dates_in_text(
                                db_camp.description, current_end, latest_date
                            )
                            if updated_description != db_camp.description:
                                print(f"   📅 [Description Tarihi Güncellendi] #{c['id']}")
                                db_camp.description = updated_description

                        # 🔗 URL Redirect tespiti: tracking_url ve slug güncelle
                        final_url = c.get("final_url")
                        if final_url and c.get("url_changed"):
                            print(f"   🔗 [URL Güncelleme] #{c['id']} | tracking_url → {final_url}")
                            db_camp.tracking_url = final_url
                            # Slug'ı yeni URL'den üret
                            try:
                                new_slug_part = final_url.rstrip("/").split("/")[-1]
                                if new_slug_part and len(new_slug_part) > 3:
                                    # Mevcut slug'ın sadece son segmentini güncelle
                                    old_slug = db_camp.slug or ""
                                    slug_parts = old_slug.rsplit("/", 1)
                                    if len(slug_parts) == 2:
                                        db_camp.slug = slug_parts[0] + "/" + new_slug_part
                                    else:
                                        db_camp.slug = new_slug_part
                                    print(f"   🔗 [Slug Güncelleme] #{c['id']} | slug → {db_camp.slug}")
                            except Exception as slug_err:
                                print(f"   ⚠️ Slug güncelleme hatası: {slug_err}")

                        db.commit()
                return True
            else:
                # Tarih uzamadı ama URL değiştiyse yine de güncelle
                final_url = c.get("final_url")
                if final_url and c.get("url_changed"):
                    print(f"   🔗 [URL Redirect - Tarihsiz] #{c['id']} | tracking_url → {final_url}")
                    with get_db_session() as db:
                        db_camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                        if db_camp:
                            db_camp.tracking_url = final_url
                            try:
                                new_slug_part = final_url.rstrip("/").split("/")[-1]
                                if new_slug_part and len(new_slug_part) > 3:
                                    old_slug = db_camp.slug or ""
                                    slug_parts = old_slug.rsplit("/", 1)
                                    if len(slug_parts) == 2:
                                        db_camp.slug = slug_parts[0] + "/" + new_slug_part
                                    else:
                                        db_camp.slug = new_slug_part
                            except Exception:
                                pass
                            db_camp.updated_at = datetime.now()
                            db.commit()

                print(f"   ℹ️ Not extended | #{c['id']} | AI date: {latest_date} (current: {current_end})")
                return False

        except Exception as e:
            print(f"   ⚠️ Error | #{c['id']} | {c['title'][:50]} | {e}")
            return False

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Her kampanyaya (c, worker_idx) tuple geçiyoruz; worker_idx anahtar seçimini belirler
        futures = {executor.submit(audit_one, (c, i % NUM_WORKERS)): c for i, c in enumerate(campaigns_with_html)}
        for future in as_completed(futures):
            result = future.result()
            with lock:
                processed_count += 1
                if result:
                    extended_count += 1
                if processed_count % 25 == 0:
                    print(f"   📊 Progress: {processed_count}/{total} audited, {extended_count} extended so far...")

    print(f"✅ Proactive Expiry Audit complete. Extended {extended_count}/{total} campaigns.")

if __name__ == "__main__":
    max_audits = 2000
    if len(sys.argv) > 1:
        try:
            max_audits = int(sys.argv[1])
        except ValueError:
            pass
    proactive_expiry_audit(max_audits=max_audits)
