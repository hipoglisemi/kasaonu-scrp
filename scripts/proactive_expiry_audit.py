import os
import sys
import json
from datetime import datetime, timedelta, timezone
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import calendar

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
from bs4 import BeautifulSoup

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

def extract_dates_via_ai(title: str, clean_text: str, key_index: int = 1, today_date = None):
    """
    Extracts campaign start and end dates from the campaign HTML text using Gemini.
    Returns a dict with 'start_date', 'end_date', 'is_expired', and 'is_indefinite'.
    key_index: 1-based API key index this worker should start from.
    """
    if not clean_text:
        return {"start_date": None, "end_date": None, "is_expired": True, "is_indefinite": False}

    if not today_date:
        today_date = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
        
    system_instruction = (
        "Sen KartAvantaj projesinde kampanya tarihlerini ve durumunu tespit eden uzman bir veri analistisin.\n"
        "Gönderilen metni analiz ederek kampanyanın durumunu ve başlangıç/bitiş tarihlerini bulmalısın.\n\n"
        "ÇOK ÖNEMLİ KURALLAR:\n"
        "1. Eğer metinde kampanyanın bittiğine, süresinin dolduğuna veya yayından kaldırıldığına dair bir ibare varsa ('Kampanya sona ermiştir', 'Süresi doldu', 'Sayfa bulunamadı', '404' vb.) veya tarihler geçmişte kalmışsa 'is_expired' alanını true yap.\n"
        "2. Eğer metin tek bir kampanyayı değil, many farklı kampanyayı listeliyorsa (genel banka anasayfasına yönlendirilmişse) 'is_expired' alanını true yap.\n"
        "3. Kampanya aktif olmasına rağmen metinde herhangi bir bitiş tarihi belirtilmemişse 'is_indefinite' alanını true yap.\n"
        "4. Sadece kampanya aktifse ve bitiş tarihi varsa 'end_date' alanını YYYY-MM-DD formatında doldur, aksi halde null bırak.\n"
        "5. Çıktıyı her zaman belirtilen JSON formatında ver.\n"
        "6. Kart başvurusu, kampanyaya katılım (Juzdan/SMS katılım süresi) veya ana promosyonun (örn. indirim/chip-para kazanma) bitiş tarihi ile son harcama/ödül kullanım süresi farklı ise, her zaman KATILIM / BAŞVURU / ANA PROMOSYONUN son gününü kampanya bitiş tarihi (end_date) olarak seç. Harcama veya puan son kullanım tarihini bitiş tarihi olarak alma. Örn: '1-30 Haziran arasında başvuranlar 15 Temmuz'a kadar harcayabilir' veya '1-30 Haziran tarihleri arasında başvurulabilir' ifadesinde bitiş tarihi 2026-06-30 olmalıdır.\n"
    )
    
    prompt = f"""
BUGÜNÜN TARİHİ: {today_date.strftime('%Y-%m-%d')}

KAMPANYA BAŞLIĞI: {title}
KAMPANYA SAYFA METNİ:
---
{clean_text}
---

GÖREV: Sayfa metnini ve kampanya başlığını inceleyerek kampanyanın başlangıç/bitiş tarihlerini ve durumunu tespit et. Çıktıyı kesinlikle aşağıdaki JSON şemasına göre üret:

```json
{{
  "start_date": "YYYY-MM-DD", // Tespit edilen başlangıç tarihi (örn. "2026-06-01"), bulunamadıysa null.
  "end_date": "YYYY-MM-DD", // Tespit edilen bitiş tarihi (örn. "2026-06-30"), bulunamadıysa null.
  "is_expired": false, // Kampanya sona ermişse, süresi dolmuşsa veya sayfa yönlendirilmiş/hata veriyorsa true, aksi halde false.
  "is_indefinite": false // Kampanya aktif fakat metinde herhangi bir bitiş tarihi bulunmuyorsa true, aksi halde false.
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
    
    # Generate the rotated list of keys starting from key_index to allow fallbacks
    NUM_WORKERS = 8
    key_indices = [((key_index - 1 + offset) % NUM_WORKERS) + 1 for offset in range(NUM_WORKERS)]

    try:
        result_str = generate_with_rotation(
            prompt=prompt,
            model="gemini-3.1-flash-lite",
            fallback_model="models/gemma-4-31b-it",
            config=config,
            key_indices=key_indices
        )
        
        if not result_str:
            return {"start_date": None, "end_date": None, "is_expired": False, "is_indefinite": False}
            
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
            "end_date": data.get("end_date"),
            "is_expired": data.get("is_expired", False),
            "is_indefinite": data.get("is_indefinite", False)
        }
    except Exception as e:
        print(f"      ⚠️  Tarih çıkartma hatası: {e}")
        return {"start_date": None, "end_date": None, "is_expired": False, "is_indefinite": False}


chrome_semaphore = threading.Semaphore(2)

def _needs_selenium(raw_html: str, url: str) -> bool:
    """Hızlı içerik kalite kontrolü — sayfanın JS render gerektirip gerektirmediğini tespit eder."""
    if not raw_html or len(raw_html) < 1500:
        return True  # Neredeyse hiç içerik yok

    force_selenium_domains = [
        "ziraatkatilim.com.tr",
        "bankkart.com.tr",
        "ziraatbank.com.tr",
        "dunyakatilim.com.tr",
        "turkiyefinans.com.tr",
        "opet.com.tr",
    ]
    if any(d in url for d in force_selenium_domains):
        return True

    soup = BeautifulSoup(raw_html, 'html.parser')
    visible_text = soup.get_text(separator=' ', strip=True)
    visible_lower = visible_text.lower()

    # 🚨 Captcha / güvenlik kodu formu tespiti
    captcha_signals = [
        "güvenlik kodu", "security code", "enter the characters",
        "yenile güvenlik", "kvkk ve kampanya koşullarını okudum",
        "cep telefon numaranız", "kartınızın son 6 hanesi",
    ]
    if sum(1 for s in captcha_signals if s in visible_lower) >= 2:
        return True  # Captcha/form sayfası — Selenium ile gerçek içeriği al

    # Kampanya anahtar kelimeleri bulunamıyorsa sayfa render olmamıştır
    campaign_keywords = ["kampanya", "indirim", "kazan", "puan", "iade", "tl", "hediye", "fırsat"]
    if len(visible_text) < 400 or not any(k in visible_lower for k in campaign_keywords):
        return True

    # React/Next.js SPA sinyalleri — içerik boş root div veya __NEXT_DATA__ ile yükleniyorsa
    root_div = soup.find("div", id="root") or soup.find("div", id="__next")
    if root_div and len(root_div.get_text(strip=True)) < 100:
        return True

    # Noscript içinde anlamlı içerik varsa → JS olmadan sayfa çalışmıyor
    noscript = soup.find("noscript")
    if noscript and len(noscript.get_text(strip=True)) > 50:
        return True

    return False


def _run_selenium(url: str) -> str:
    """Headless Chrome/Selenium ile sayfayı açar ve HTML döner."""
    chrome_semaphore.acquire()
    print(f"   🚀 Escalating to Headless Chrome for: {url}")
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service

        options = webdriver.ChromeOptions()
        if os.getenv("CHROME_BIN"):
            options.binary_location = os.getenv("CHROME_BIN")
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--headless=new')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        try:
            service = Service(executable_path=os.getenv("CHROMEDRIVER_PATH", "chromedriver"))
            driver = webdriver.Chrome(service=service, options=options)
        except Exception:
            driver = webdriver.Chrome(options=options)

        driver.set_page_load_timeout(60)
        driver.get(url)
        time.sleep(4)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 500);")
        time.sleep(2)

        # Site bazlı özel aksiyonlar
        if "dunyakatilim.com.tr" in url:
            try:
                cookie_btn = driver.find_element(By.ID, "cookie-all-apply")
                driver.execute_script("arguments[0].click();", cookie_btn)
                time.sleep(2)
            except Exception:
                pass

        if "bonus.com.tr" in url:
            try:
                tabs = driver.find_elements(By.CSS_SELECTOR, ".tabs-list li, .how-to-win-tabs li, .tab-item, .nav-tabs li a")
                for tab in tabs:
                    if any(t in tab.text.lower() for t in ["diğer bilgiler", "diger bilgiler", "nasıl kazanırım", "dahil kartlar"]):
                        driver.execute_script("arguments[0].scrollIntoView();", tab)
                        driver.execute_script("arguments[0].click();", tab)
                        time.sleep(2)
            except Exception:
                pass

        html = driver.page_source
        driver.quit()
        return html
    except Exception as e:
        print(f"   ⚠️ Selenium failed: {e}")
        return ""
    finally:
        chrome_semaphore.release()


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
                Campaign.end_date <= today + timedelta(days=5), # ve 5 gün içinde biten kampanyalar
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
                
                html_content = resp.text
                if _needs_selenium(html_content, c["url"]):
                    print(f"   🔍 [JS Render Gerekli] #{c['id']} için Selenium başlatılıyor...")
                    rendered_html = _run_selenium(c["url"])
                    if rendered_html and len(rendered_html) > len(html_content):
                        html_content = rendered_html
                        print(f"   ✅ [Selenium Başarılı] #{c['id']} için {len(html_content)} karakter çekildi.")
                        
                return {**c, "html": html_content, "final_url": final_url, "url_changed": url_changed}
        except Exception as e:
            print(f"   ⚠️ fetch_html error for #{c['id']}: {e}")
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
            # Stagger requests to prevent concurrent bursts
            time.sleep(1.0 + worker_idx * 2.0)

            # ✅ Düzgün temizlenmiş metin: text_cleaner pipeline'ından geçir
            clean_text = clean_html_to_text(c["html"], title=c.get("title", ""))
            ai_dates = extract_dates_via_ai(c["title"], clean_text, key_index=key_index, today_date=today)

            ai_start_date_str = ai_dates.get("start_date")
            ai_end_date_str = ai_dates.get("end_date")
            is_expired = ai_dates.get("is_expired", False)
            is_indefinite = ai_dates.get("is_indefinite", False)

            if is_expired:
                print(f"   🛑 [Kampanya Bitti] Sayfada kampanya sona ermiş görünüyor → Pasife alınıyor | ID: #{c['id']} | {c['title'][:50]}")
                with get_db_session() as db:
                    db_camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                    if db_camp:
                        db_camp.is_active = False
                        db_camp.updated_at = datetime.now()
                        db.commit()
                return False

            if not ai_end_date_str:
                if is_indefinite:
                    # Süresiz kampanya
                    # Ay sonuna kadar uzat. Eğer ay sonuna 5 günden az kaldıysa bir sonraki ayın sonuna uzat.
                    last_day_current = calendar.monthrange(today.year, today.month)[1]
                    if (last_day_current - today.day) > 5:
                        indefinite_date = datetime(today.year, today.month, last_day_current).date()
                    else:
                        if today.month == 12:
                            next_month_num, next_year_num = 1, today.year + 1
                        else:
                            next_month_num, next_year_num = today.month + 1, today.year
                        last_day_next = calendar.monthrange(next_year_num, next_month_num)[1]
                        indefinite_date = datetime(next_year_num, next_month_num, last_day_next).date()

                    print(f"   📅 [Süresiz Kampanya] Bitiş tarihi yok (aktif) → {indefinite_date} tarihine uzatılıyor | ID: #{c['id']} | {c['title'][:50]}")
                    with get_db_session() as db:
                        db_camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                        if db_camp:
                            db_camp.end_date = indefinite_date
                            db_camp.date_extended = True
                            db_camp.updated_at = datetime.now()
                            db.commit()
                    return True
                else:
                    print(f"   ❌ No end date found and not marked indefinite | ID: #{c['id']} | {c['title'][:50]}")
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
                        if hasattr(db_camp, 'ai_marketing_text') and db_camp.ai_marketing_text:
                            updated_marketing = update_dates_in_text(
                                db_camp.ai_marketing_text, current_end, latest_date
                            )
                            if updated_marketing != db_camp.ai_marketing_text:
                                print(f"   📅 [Marketing Text Tarihi Güncellendi] #{c['id']}")
                                db_camp.ai_marketing_text = updated_marketing

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
