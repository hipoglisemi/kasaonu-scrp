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
from src.utils.gemini_client import generate_with_rotation, generate_with_rotation_tracked
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

from src.utils.date_utils import update_dates_in_text

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
        "Sen Kasaonu projesinde kampanya tarihlerini ve durumunu tespit eden uzman bir veri analistisin.\n"
        "Gönderilen metni analiz ederek kampanyanın durumunu ve başlangıç/bitiş tarihlerini bulmalısın.\n\n"
        "ÇOK ÖNEMLİ KURALLAR:\n"
        "1. Eğer metinde kampanyanın bittiğine, süresinin dolduğuna veya yayından kaldırıldığına dair bir ibare varsa ('Kampanya sona ermiştir', 'Süresi doldu', 'Sayfa bulunamadı', '404' vb.) veya tarihler geçmişte kalmışsa 'is_expired' alanını true yap.\n"
        "2. Eğer metin tek bir kampanyayı değil, many farklı kampanyayı listeliyorsa (genel banka anasayfasına yönlendirilmişse) 'is_expired' alanını true yap.\n"
        "3. Kampanya aktif olmasına rağmen metinde herhangi bir bitiş tarihi belirtilmemişse 'is_indefinite' alanını true yap.\n"
        "4. Sadece kampanya aktifse ve bitiş tarihi varsa 'end_date' alanını YYYY-MM-DD formatında doldur, aksi halde null bırak.\n"
        "5. Çıktıyı her zaman belirtilen JSON formatında ver.\n"
        "6. Kart başvurusu, kampanyaya katılım (Juzdan/SMS katılım süresi) veya ana promosyonun (örn. indirim/chip-para kazanma) bitiş tarihi ile son harcama/ödül kullanım süresi farklı ise, her zaman KATILIM / BAŞVURU / ANA PROMOSYONUN son gününü kampanya bitiş tarihi (end_date) olarak seç. Harcama veya puan son kullanım tarihini bitiş tarihi olarak alma. Örn: '1-30 Haziran arasında başvuranlar 15 Temmuz'a kadar harcayabilir' veya '1-30 Haziran tarihleri arasında başvurulabilir' ifadesinde bitiş tarihi 2026-06-30 olmalıdır.\n"
        "7. ÇOK ÖNEMLİ: Eğer sayfa metni, sana verilen KAMPANYA BAŞLIĞI ile tamamen ilgisizse (örneğin başlık 'Felix' ama metin tamamen 'Opet Pay Nakit İade' veya genel kredi kartı özelliklerini anlatıyorsa), bankanın sayfayı sildiğini ve seni alakasız bir sayfaya yönlendirdiğini anla ve KESİNLİKLE 'is_expired' alanını true yap.\n"
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
    
    # Paid tier: tek key yeterli, rotation sadece fallback için
    NUM_WORKERS = 8
    key_indices = [1]  # Paid tier: sadece KEY_1 kullan, 429 alırsa rotation devreye girer

    try:
        result_str, usage = generate_with_rotation_tracked(
            prompt=prompt,
            model="gemini-3.5-flash-lite",
            fallback_model="models/gemma-4-31b-it",
            config=config,
            key_indices=key_indices
        )
        
        if not result_str:
            return {"start_date": None, "end_date": None, "is_expired": False, "is_indefinite": False, "_usage": {"input_tokens": 0, "output_tokens": 0}}
            
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
            "is_indefinite": data.get("is_indefinite", False),
            "_usage": usage
        }
    except Exception as e:
        print(f"      ⚠️  Tarih çıkartma hatası: {e}")
        return {"start_date": None, "end_date": None, "is_expired": False, "is_indefinite": False, "_usage": {"input_tokens": 0, "output_tokens": 0}}


chrome_lock = threading.Lock()

def _needs_selenium(raw_html: str, url: str) -> bool:
    """Hızlı içerik kalite kontrolü — sayfanın JS render gerektirip gerektirmediğini tespit eder."""
    return False


def _run_selenium(url: str) -> str:
    """Playwright ile sayfayı açar ve HTML döner. (Fonksiyon adı uyumluluk için aynı bırakıldı)"""
    return ""


def proactive_expiry_audit(max_audits=2500, specific_ids=None):
    """
    Checks campaigns expiring TODAY.
    Fetches their tracking URL and parses them with AI to get the actual end_date.
    If a date in the future (later than current end_date) is found, updates it.
    This prevents unnecessary deactivations and rescraping/AI parsing cost.
    """
    print("🕰️ Starting Proactive Expiry Audit (Grace Period check via AI)...")
    run_start_time = time.time()
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
    
    # Auditing campaigns expiring in the last 1 day and next 3 days
    start_date = today - timedelta(days=1)
    end_date = today + timedelta(days=3)
    print(f"📅 Auditing campaigns expiring in date range: {start_date} to {end_date}")

    # Fetch campaigns expiring soon
    campaigns_to_audit = []
    try:
        with get_db_session() as db:
            if specific_ids:
                soon_expiring = db.query(Campaign).filter(
                    Campaign.id.in_(specific_ids),
                    Campaign.tracking_url.isnot(None)
                ).all()
            else:
                soon_expiring = db.query(Campaign).filter(
                    Campaign.end_date >= start_date,
                    Campaign.end_date <= end_date,
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
        print("✅ No campaigns expiring today or tomorrow.")
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
                    # Fast check: If it redirects to homepage or generic listing page, it's a dead campaign link
                    try:
                        from urllib.parse import urlparse
                        path = urlparse(final_url.lower()).path.rstrip('/')
                    except Exception:
                        path = ""
                    generic_listing_paths = (
                        'kampanyalar', 'firsatlar', 'ayricaliklar', 'indirimler',
                        'kampanya-listesi', 'kampanyalarimiz'
                    )
                    if any(gl in path for gl in generic_listing_paths) or len(path) <= 1:
                        print(f"   👻 [Soft 404 / Listing Redirect] #{c['id']} redirected to listing/homepage. Marking as 404.")
                        return {**c, "html": "", "final_url": final_url, "url_changed": url_changed, "is_404": True}
                
                # 🔤 Encoding fix: charset belirtmeyen siteler (Amex vb.) için requests
                # ISO-8859-1 varsayar ama içerik UTF-8'dir. Zorla UTF-8 set et.
                if resp.encoding and resp.encoding.upper() in ('ISO-8859-1', 'LATIN-1', 'LATIN1'):
                    resp.encoding = 'utf-8'
                html_content = resp.text
                if _needs_selenium(html_content, c["url"]):
                    print(f"   🔍 [JS Render Gerekli] #{c['id']} için Selenium başlatılıyor...")
                    rendered_html = _run_selenium(c["url"])
                    if rendered_html and len(rendered_html) > len(html_content):
                        html_content = rendered_html
                        print(f"   ✅ [Selenium Başarılı] #{c['id']} için {len(html_content)} karakter çekildi.")
                        
                return {**c, "html": html_content, "final_url": final_url, "url_changed": url_changed, "is_404": False}
            elif resp.status_code == 404 or resp.status_code == 410:
                print(f"   💀 [404 Not Found] #{c['id']} | {c['url']}")
                return {**c, "html": "", "final_url": c["url"], "url_changed": False, "is_404": True}
        except Exception as e:
            print(f"   ⚠️ fetch_html error for #{c['id']}: {e}. Escalating to Playwright...")
            try:
                rendered_html = _run_selenium(c["url"])
                if rendered_html:
                    return {**c, "html": rendered_html, "final_url": c["url"], "url_changed": False}
            except Exception as pe:
                print(f"   ⚠️ Playwright fallback also failed for #{c['id']}: {pe}")
        return None
        
    with ThreadPoolExecutor(max_workers=20) as executor:  # 20 workers for HTML fetching (network bottleneck)
        futures = [executor.submit(fetch_html, c) for c in campaigns_to_audit]
        for future in as_completed(futures):
            res = future.result()
            if res:
                campaigns_with_html.append(res)
                 
    print(f"📥 Successfully fetched {len(campaigns_with_html)} pages. Starting AI parsing with 8 parallel workers...")

    extended_count = 0
    processed_count = 0
    lock = threading.Lock()
    total = len(campaigns_with_html)
    
    # 📊 Token ve maliyet takibi
    total_input_tokens = 0
    total_output_tokens = 0
    token_lock = threading.Lock()
    
    # Gemini 3.1 Flash-Lite fiyatları (resmi)
    PRICE_INPUT_PER_M = 0.25   # $0.25 per 1M input tokens
    PRICE_OUTPUT_PER_M = 1.50  # $1.50 per 1M output tokens
    USD_TO_TRY = 47.0          # Güncel kur

    NUM_WORKERS = 8  # 8 işçi × 8 anahtar, her biri kendi key'ine kilitli

    def audit_one(args):
        """Audit a single campaign: AI parse → DB update. Thread-safe."""
        nonlocal total_input_tokens, total_output_tokens
        c, worker_idx = args
        key_index = (worker_idx % NUM_WORKERS) + 1
        current_end = c["end_date"]
        try:
            if c.get("is_404"):
                print(f"   💀 [404 Doğrudan Kapatma] #{c['id']} | Sayfa bulunamadı (404/Soft 404).")
                with get_db_session() as db:
                    camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                    if camp:
                        camp.is_active = False
                        db.commit()
                return

            # ✅ Düzgün temizlenmiş metin: text_cleaner pipeline'ından geçir
            clean_text = clean_html_to_text(c["html"], title=c.get("title", ""))
            
            # 🛡️ BOT/ENGEL KALKANI & SOFT 404 TESPİTİ:
            # If the clean_text is suspiciously short or contains typical WAF/Bot block phrases,
            # we should SKIP rather than letting AI hallucinate or falsely mark as expired.
            lower_text = clean_text.lower()
            block_phrases = ["access denied", "cloudflare", "security check", "güvenlik kontrolü", "are you human", "robot olmadığınızı", "sayfa bulunamadı", "aradığınız sayfa"]
            
            # Soft 404 check: If the original title has specific words, and the page text doesn't contain ANY of them, it's a soft 404
            orig_title = c.get("title", "").lower()
            title_words = [w for w in re.split(r'\W+', orig_title) if len(w) > 4 and w not in ('kampanyası', 'fırsatı', 'taksit', 'indirimi')]
            if title_words and len(lower_text) > 50:
                match_count = sum(1 for w in title_words if w in lower_text)
                if match_count == 0:
                    print(f"   💀 [Soft 404 - Başlık Eşleşmiyor] #{c['id']} | Sayfada '{title_words[0]}' bile geçmiyor.")
                    with get_db_session() as db:
                        camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                        if camp:
                            camp.is_active = False
                            db.commit()
                    return
            
            if len(clean_text) < 200 or any(bp in lower_text for bp in block_phrases):
                print(f"   🛡️ [Bot Engeli/Eksik İçerik] #{c['id']} için içerik şüpheli veya bloke edilmiş. Pas geçiliyor.")
                return False

            ai_dates = extract_dates_via_ai(c["title"], clean_text, key_index=key_index, today_date=today)
            
            # Token kullanımını kaydet
            usage = ai_dates.get("_usage", {})
            with token_lock:
                total_input_tokens += usage.get("input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)

            ai_start_date_str = ai_dates.get("start_date")
            ai_end_date_str = ai_dates.get("end_date")
            is_expired = ai_dates.get("is_expired", False)
            is_indefinite = ai_dates.get("is_indefinite", False)

            if is_expired:
                # Kullanıcı talebi: Banka kampanyayı kaldırdıysa veya sayfa "süresi doldu" diyorsa anında pasife al.
                print(f"   💀 [AI Expired] AI kampanya bitmiş/kaldırılmış dedi, pasife alınıyor | ID: #{c['id']} | {c['title'][:50]}")
                with get_db_session() as db:
                    camp = db.query(Campaign).filter(Campaign.id == c["id"]).first()
                    if camp:
                        camp.is_active = False
                        db.commit()
                return True

            if not ai_end_date_str:
                if is_indefinite:
                    # 🛡️ GEÇMİŞE SAYGI (Respect History) KURALI
                    # Eğer sistemde halihazırda belli bir bitiş tarihi varsa, AI bot engeli veya sayfa eksikliği yüzünden
                    # tarihi bulamayıp "Süresiz" sanmış olabilir. Bu durumda eski tarihi ezme!
                    if c["end_date"]:
                        print(f"   🛡️ [Geçmişe Saygı] AI 'Süresiz' dedi ancak sistemde eski tarih ({c['end_date']}) var. Orijinal tarih korunuyor! | ID: #{c['id']} | {c['title'][:50]}")
                        return False

                    # Gerçek Süresiz kampanya (Eskiden de tarihi yoktu)
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
                            db_camp.is_active = True  # Reactivate if it was inactive
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
                        db_camp.is_active = True  # Reactivate if it was inactive
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
                            try:
                                new_slug_part = final_url.rstrip("/").split("/")[-1]
                                if new_slug_part and len(new_slug_part) > 3:
                                    # Mevcut slug'ın sadece son segmentini güncelle
                                    old_slug = db_camp.slug or ""
                                    slug_parts = old_slug.rsplit("/", 1)
                                    proposed_slug = slug_parts[0] + "/" + new_slug_part if len(slug_parts) == 2 else new_slug_part
                                    
                                    existing = db.query(Campaign).filter(Campaign.slug == proposed_slug).first()
                                    if existing and existing.id != db_camp.id:
                                        print(f"   ⚠️ [Slug Çakışması] '{proposed_slug}' zaten var (#{existing.id}). Eski kampanya pasife alınıyor.")
                                        db_camp.is_active = False
                                    else:
                                        db_camp.slug = proposed_slug
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
                                    proposed_slug = slug_parts[0] + "/" + new_slug_part if len(slug_parts) == 2 else new_slug_part
                                    
                                    existing = db.query(Campaign).filter(Campaign.slug == proposed_slug).first()
                                    if existing and existing.id != db_camp.id:
                                        print(f"   ⚠️ [Slug Çakışması] '{proposed_slug}' zaten var (#{existing.id}). Eski kampanya pasife alınıyor.")
                                        db_camp.is_active = False
                                    else:
                                        db_camp.slug = proposed_slug
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

    run_end_time = time.time()
    run_duration = run_end_time - run_start_time
    run_minutes = int(run_duration // 60)
    run_seconds = int(run_duration % 60)
    
    # 💰 Maliyet hesabı
    cost_input = (total_input_tokens / 1_000_000) * PRICE_INPUT_PER_M
    cost_output = (total_output_tokens / 1_000_000) * PRICE_OUTPUT_PER_M
    cost_total_usd = cost_input + cost_output
    cost_total_try = cost_total_usd * USD_TO_TRY
    
    print(f"")
    print(f"{'='*60}")
    print(f"✅ Proactive Expiry Audit Tamamlandı!")
    print(f"{'='*60}")
    print(f"  ⏱  Süre           : {run_minutes} dakika {run_seconds} saniye")
    print(f"  📊 Taranan Kampanya: {total} adet")
    print(f"  📅 Uzatılan        : {extended_count} adet")
    print(f"  🔵 Giren Token     : {total_input_tokens:,}")
    print(f"  🟠 Çıkan Token      : {total_output_tokens:,}")
    print(f"  💵 Maliyet (USD)  : ${cost_total_usd:.4f}")
    print(f"  💸 Maliyet (TL)   : {cost_total_try:.2f} TL")
    print(f"{'='*60}")

if __name__ == "__main__":
    max_audits = 2500
    if len(sys.argv) > 1:
        try:
            max_audits = int(sys.argv[1])
        except ValueError:
            pass
    proactive_expiry_audit(max_audits=max_audits)
