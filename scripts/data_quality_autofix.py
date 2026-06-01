"""
Data Quality Auto-Fixer

This script scans active campaigns in the database for missing vital information
(such as short/missing description, missing reward text, etc.). If it finds a
defective campaign, it attempts to fetch the HTML from its tracking_url and
passes it back through the Gemini AI parser to repair the missing fields.
"""

import os
import sys
import time
from typing import Optional
import requests # type: ignore
from bs4 import BeautifulSoup # type: ignore

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import uuid
import logging
import json
import threading
thread_local = threading.local()
chrome_semaphore = threading.Semaphore(2)

# Suppress noisy INFO logs from underlying AI libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)

from src.models import Campaign, Sector, Brand, CampaignBrand, Card, Bank # type: ignore
from src.database import get_db_session # type: ignore
from src.services.ai_parser_golden import AIParserGolden # type: ignore
from src.services.fact_checker import FactCheckerAgent # type: ignore
from src.services.text_cleaner import clean_campaign_text # type: ignore
from src.services.point_blank_matcher import get_point_blank_matcher, _GLOBAL_BRAND_EXCLUSIONS # type: ignore
from sqlalchemy.orm import joinedload # type: ignore
from sqlalchemy import func # type: ignore
from src.utils.gemini_client import generate_with_rotation # type: ignore
from google.genai import types # type: ignore

# Golden Parser AI Client Wrapper
class _AutofixGeminiClient:
    """Wraps generate_with_rotation for AIParserGolden compatibility."""
    def __init__(self, model=None, fallback_model=None):
        # Gece otomatik tamircisi (AutoFix) için Başdenetçi Model
        self.model = model or os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.1-flash-lite")
        self.fallback_model = fallback_model or os.getenv("FALLBACK_MODEL")
        
    def generate_content(self, prompt):
        config = types.GenerateContentConfig(
            temperature=0.0, top_p=0.1, top_k=1,
            response_mime_type="application/json",
            max_output_tokens=6000
        )
        kwargs = {
            "prompt": prompt,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "config": config
        }
        if getattr(thread_local, 'key_index', None) is not None:
            kwargs["key_indices"] = [thread_local.key_index]
        result = generate_with_rotation(**kwargs)
        return result if result else "{}"

def _get_golden_parser(model=None, fallback_model=None):
    return AIParserGolden(_AutofixGeminiClient(model=model, fallback_model=fallback_model))

SECTOR_MAP = {
    # Türkçe isim → slug
    "Market & Gıda": "market-gida",
    "Akaryakıt": "akaryakit",
    "Giyim & Aksesuar": "giyim-aksesuar",
    "Restoran & Kafe": "restoran-kafe",
    "Elektronik": "elektronik",
    "Mobilya, Dekorasyon & Yapı Market": "mobilya-dekorasyon",
    "Mobilya & Dekorasyon": "mobilya-dekorasyon",
    "Sağlık, Kozmetik & Kişisel Bakım": "kozmetik-saglik",
    "Kozmetik & Sağlık": "kozmetik-saglik",
    "E-Ticaret": "e-ticaret",
    "Ulaşım": "ulasim",
    "Dijital Platform & Oyun": "dijital-platform",
    "Dijital Platform": "dijital-platform",
    "Kültür, Sanat & Spor": "kultur-sanat-spor",
    "Kültür & Sanat": "kultur-sanat-spor",
    "Eğitim": "egitim",
    "Sigorta": "sigorta",
    "Otomotiv": "otomotiv",
    "Vergi & Kamu": "vergi-kamu",
    "Turizm, Konaklama & Seyahat": "turizm-konaklama",
    "Turizm & Konaklama": "turizm-konaklama",
    "Mücevherat, Optik & Saat": "mucevherat-optik-saat",
    "Fatura & Telekomünikasyon": "fatura-telekomunikasyon",
    "Anne, Bebek & Oyuncak": "anne-bebek-oyuncak",
    "Kitap, Kırtasiye & Ofis": "kitap-kirtasiye-ofis",
    "Evcil Hayvan & Petshop": "evcil-hayvan-petshop",
    "Hizmet & Bireysel Gelişim": "hizmet-bireysel-gelisim",
    "Finans & Yatırım": "finans-yatirim",
    "Diğer": "diger",
    # Slug → slug (AI bazen doğrudan slug dönüyor)
    "market-gida": "market-gida",
    "akaryakit": "akaryakit",
    "giyim-aksesuar": "giyim-aksesuar",
    "restoran-kafe": "restoran-kafe",
    "elektronik": "elektronik",
    "mobilya-dekorasyon": "mobilya-dekorasyon",
    "kozmetik-saglik": "kozmetik-saglik",
    "e-ticaret": "e-ticaret",
    "ulasim": "ulasim",
    "dijital-platform": "dijital-platform",
    "kultur-sanat": "kultur-sanat-spor",
    "kultur-sanat-spor": "kultur-sanat-spor",
    "egitim": "egitim",
    "sigorta": "sigorta",
    "otomotiv": "otomotiv",
    "vergi-kamu": "vergi-kamu",
    "turizm-konaklama": "turizm-konaklama",
    "kuyum-optik-ve-saat": "mucevherat-optik-saat",
    "mucevherat-optik-saat": "mucevherat-optik-saat",
    "fatura-telekomunikasyon": "fatura-telekomunikasyon",
    "anne-bebek-oyuncak": "anne-bebek-oyuncak",
    "kitap-kirtasiye-ofis": "kitap-kirtasiye-ofis",
    "evcil-hayvan-petshop": "evcil-hayvan-petshop",
    "hizmet-bireysel-gelisim": "hizmet-bireysel-gelisim",
    "finans-yatirim": "finans-yatirim",
    "diger": "diger",
}

def fetch_html(url: str) -> str:
    """Attempts to fetch the HTML content of a URL."""
    raw_html = ""
    spa_domains = ["dunyakatilim.com.tr", "paycell.com.tr", "opet.com.tr", "naysapp.com.tr", "chippin.com", "axess.com.tr", "kartfree.com", "wingscard.com.tr", "bonus.com.tr", "denizbonus.com"]
    is_spa = any(domain in url for domain in spa_domains)

    if is_spa:
        chrome_semaphore.acquire()
        print(f"   🚀 SPA/Tabbed Site Detected ({url}). Booting Headless Chrome...")
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
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            try:
                service = Service(executable_path=os.getenv("CHROMEDRIVER_PATH", "chromedriver"))
                driver = webdriver.Chrome(service=service, options=options)
            except:
                # Fallback to standard init if service/path fails (similar to scrapers)
                driver = webdriver.Chrome(options=options)

            driver.set_page_load_timeout(60) # Increased timeout
            driver.get(url)
            time.sleep(4) # Initial wait
            # Scroll to bottom to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            # Scroll slightly up as some lazy loaders need movement
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 500);")
            time.sleep(2)
            raw_html = driver.page_source

            # Dünya Katılım specific: Close cookie banner if present
            if "dunyakatilim.com.tr" in url:
                try:
                    cookie_btn = driver.find_element(By.ID, "cookie-all-apply")
                    if cookie_btn:
                        driver.execute_script("arguments[0].click();", cookie_btn)
                        time.sleep(2)
                except:
                    pass

            # Bonus.com.tr specific: Click on "DİĞER BİLGİLER" or "Nasıl Kazanırım" tabs to reveal cards
            if "bonus.com.tr" in url:
                try:
                    tabs = driver.find_elements(By.CSS_SELECTOR, ".tabs-list li, .how-to-win-tabs li, .tab-item, .nav-tabs li a")
                    for tab in tabs:
                        tab_text = tab.text.lower()
                        if any(txt in tab_text for txt in ["diğer bilgiler", "diger bilgiler", "nasıl kazanırım", "dahil kartlar"]):
                            driver.execute_script("arguments[0].scrollIntoView();", tab)
                            driver.execute_script("arguments[0].click();", tab)
                            time.sleep(2)
                except:
                    pass

            time.sleep(2) 
            raw_html = driver.page_source
            driver.quit()
        except Exception as e:
            print(f"   ⚠️ SPA fetch failed: {e}. Falling back to standard methods.")
            raw_html = ""
        finally:
            chrome_semaphore.release()
            
    is_trafilatura_text = False
    if not raw_html or len(raw_html) < 2000:
        # Final Fallback: Use Trafilatura (Our robust markdown engine)
        try:
            if "vakif" in url:
                raise Exception("Skip Trafilatura for Vakifbank due to noise issues")
            import trafilatura
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                # Extract with all options to get as much text as possible
                extracted_text = trafilatura.extract(downloaded, include_tables=True, include_links=True, include_comments=True)
                if extracted_text and len(extracted_text) > 500:
                    print(f"   ✨ Trafilatura successfully extracted {len(extracted_text)} chars.")
                    raw_html = extracted_text # Set as raw_html to be processed by clean_campaign_text below
                    is_trafilatura_text = True
        except Exception as te:
            print(f"   ⚠️ Trafilatura failed: {te}")

    if not raw_html:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            }
            import urllib3 # type: ignore
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status()
            
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding
            raw_html = response.text
        except Exception as e:
            print(f"   ⚠️ Request failed: {e}")
            status = "LIVE_FETCH_ERROR"
            if "403" in str(e) or "429" in str(e) or "forbidden" in str(e).lower():
                status = "BOT_BLOCKED"
            return "", status

    if not is_trafilatura_text:
        soup = BeautifulSoup(raw_html, 'html.parser')

        # 🛡️ NOISE REMOVAL (Global)
        for script in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            script.extract()
            
        # 🛡️ NOISE REMOVAL (Specific)
        noise_selectors = [
            '.other-campaigns', '.featured-campaigns', '.similar-campaigns', 
            '.campaign-recommendations', 'section.news-carousel', 
            '#related-campaigns', '.campaignDetail-others',
            '.footer-cookie-policy', '.cookie-banner', '.cookie-modal', 
            '#cookie-dialog-content', '.cookie-consent', '#cookie-all-apply'
        ]
        for selector in noise_selectors:
            for element in soup.select(selector):
                element.extract()
        
        # 🎯 CONTENT TARGETING
        target_selectors = [
            '.page-top-title', '.sub-header', '.campaign-terms', '.campaign-detail-content', '.campaign-detail', 
            '.campaign-detail-tab-details', '.campaign-detail-box', 
            'article.campaign-detail', '.cmsContent',
            '.campaingDetail', '.campaing', '.textArea', '.campaingDetail-content',
            '.how-to-win-content', '.tab-content', '.campaign-detail-content', '.campaign-detail-text',
            '.campaign-detail-capsule', '.container-right', '.campaign-dates',
            '.news-campaign-content', '.bt', '.richtext',
            '.offer-detail', '.terms-conditions'
        ]
        
        content_found = []
        for selector in target_selectors:
            elements = soup.select(selector)
            for el in elements:
                el_text_lower = el.get_text().lower()
                if any(x in el_text_lower for x in ["öne çıkan kampanyalar", "benzer kampanyalar"]):
                    continue
                content_found.append(el.get_text(separator=' ', strip=True))
        
        if content_found:
            text = " ".join(content_found)
        else:
            text = soup.get_text(separator=' ', strip=True)
    else:
        # Trafilatura already gave us the text in raw_html
        text = raw_html
        
    print(f"🔍 DEBUG RAW EXTRACTED TEXT: {text}")
    
    # 🛡️ Use Central Text Cleaner (Standard Scraper Logic)
    text = clean_campaign_text(text)
    
    # 🛡️ GENERIC CONTENT GUARD
    generic_keywords = ["çerez", "kişisel veriler", "aydınlatma metni", "hakkımızda", "içeriğe git", "menüye git", "gizlilik politikası"]
    campaign_keywords = ["kampanya", "indirim", "fırsat", "çekiliş", "kazan", "hediye", "puan", "iade", "tl", "bonus"]
    
    text_lower = text.lower()
    generic_count = sum(1 for k in generic_keywords if k in text_lower)
    campaign_count = sum(1 for k in campaign_keywords if k in text_lower)
    
    # If the text is overwhelmingly generic and missing campaign keywords, mark as empty
    if generic_count > 5 and campaign_count < 2 and len(text) < 3000:
        print(f"   🛡️ Generic Content Guard Triggered! (Generic: {generic_count}, Campaign: {campaign_count}). Rejecting text.")
        return "", "GENERIC_CONTENT_REJECTED"

    status_code = "LIVE_SUCCESS" if len(text) > 200 else "LIVE_EMPTY"
    return text, status_code

def run_autofix(limit: int = 250, campaign_id: Optional[int] = None, force_all: bool = False, ids_file: Optional[str] = None, ui_mode: bool = False, pending: bool = False, model: Optional[str] = None, fallback_model: Optional[str] = None, force_rescue: bool = False):
    print(f"🚀 Starting Data Quality Auto-Fixer (Limit: {limit})...")
    
    try:
        from datetime import datetime, timedelta
        now = datetime.now()
        cooldown_period = timedelta(hours=48)
        
        with get_db_session() as db:
            print("\n🔍 Scanning for defective campaigns...")

            query = db.query(Campaign).options(
                joinedload(Campaign.sector),
                joinedload(Campaign.brands)
            )
            
            if campaign_id:
                query = query.filter(Campaign.id == campaign_id)
            elif ids_file:
                # ids_file logic will filter the list later, but we can start with all active ones
                query = query.filter(Campaign.is_active == True)
            else:
                # DEFAULT BEHAVIOR: Focus ONLY on PENDING (unapproved) campaigns
                print("🔍 Focusing on PENDING (unapproved) campaigns...")
                query = query.filter(Campaign.is_approved == False)
            
            defective_campaigns = query.all()
            print(f"   📊 Checking {len(defective_campaigns)} active campaigns for defects.")
            
            FORCE_ALL = force_all or (ids_file is not None)
            to_fix_ids = []
            stats = {"new": 0, "retry": 0, "skipped_cooldown": 0}

            # --- MANUAL BATCH MODE (IDS FROM FILE) ---
            if ids_file and os.path.exists(ids_file):
                print(f"📖 Reading IDs from file: {ids_file}")
                with open(ids_file, "r") as f:
                    file_ids = [line.strip() for line in f if line.strip().isdigit()]
                
                # Filter campaigns based on these IDs
                defective_campaigns = [c for c in defective_campaigns if str(c.id) in file_ids]
                print(f"✅ Filtered {len(defective_campaigns)} campaigns matching IDs in file.")
            
            for c in defective_campaigns:
                is_defective = False
                updated = False
                wrong_bank_brands = set()
                reasons = []
                
                # New detection pattern: character-level corruption (e.g., 'P, a, r, a, f')
                corrupted_regex = re.compile(r'([a-zA-ZçğıüşöÇĞİÜŞÖ0-9], ){2,}')
                generic_participation = "Mobil uygulama üzerinden veya banka kanallarından kampanya detaylarındaki talimatları izleyerek katılabilirsiniz."
                useless_participations = [
                    generic_participation, 
                    "Hemen faydalanabilirsiniz.", 
                    "Hemen faydalanabilirsiniz", 
                    "Kampanya dahilinde.",
                    "Detayları İnceleyin",
                    "Detayları inceleyin",
                    "Hemen faydalanmaya başlayın.",
                    "Axess Mobil uygulama üzerinden katılabilirsiniz.",
                    "Harcamadan önce mobil uygulama üzerinden katılın.",
                    "Harcamadan önce Mobilden katılın.",
                    "Juzdan uygulama üzerinden katılabilirsiniz.",
                    "Juzdan üzerinden katılabilirsiniz.",
                    "Mobil Şube üzerinden Kampanyaya Katıl butonuna tıklayın",
                    "Kampanyaya katılmak için Mobil Şube üzerinden Kampanyaya Katıl butonuna tıklamanız yeterlidir.",
                    "Otomatik Katılım",
                    "Otomatik katılım",
                    "Katılım kanalı belirtilmediği için",  # AI'nin ürettiği genel/yanlış fallback
                ]
                
                is_corrupted = False
                if c.description and corrupted_regex.search(c.description): is_corrupted = True
                if c.conditions and corrupted_regex.search(c.conditions): is_corrupted = True
                if c.eligible_cards and corrupted_regex.search(c.eligible_cards): is_corrupted = True
                if c.ai_marketing_text and corrupted_regex.search(c.ai_marketing_text): is_corrupted = True
                
                mojibake_pattern = re.compile(r'[ÄÃÅ][\u0080-\u00bf]')
                has_mojibake = False
                if c.clean_text and mojibake_pattern.search(c.clean_text): has_mojibake = True
                if c.description and mojibake_pattern.search(c.description): has_mojibake = True

                if is_corrupted or has_mojibake:
                    is_defective = True
                    reasons.append("Character/Encoding Corruption")

                if not c.description or len(c.description.strip()) < 15:
                    is_defective = True
                    reasons.append("Missing/Short Description")
                
                # Check for Default Reward Text
                is_reward_bad = not c.reward_text or c.reward_text.strip() == "" or "Detayları İnceleyin" in (c.reward_text or "") or "Hemen Faydalanın" in (c.reward_text or "")
                if is_reward_bad:
                    is_defective = True
                    reasons.append("Missing/Default Reward Text")
                
                if c.reward_value is None:
                    is_defective = True
                    reasons.append("Missing Reward Value")
                if not c.reward_type or c.reward_type.strip() == "":
                    is_defective = True
                    reasons.append("Missing Reward Type")
                
                # Check for Missing/Corrupted/Generic Eligible Cards
                is_cards_bad = not c.eligible_cards or c.eligible_cards.strip() == "" or "Kampanyaya Dahil Kartlar" in (c.eligible_cards or "") or corrupted_regex.search(c.eligible_cards or "")
                if is_cards_bad:
                    is_defective = True
                    reasons.append("Missing/Corrupted/Generic Eligible Cards")
                
                if not c.start_date:
                    is_defective = True
                    reasons.append("Missing Start Date")
                if not c.end_date:
                    is_defective = True
                    reasons.append("Missing End Date")
                if not c.conditions or c.conditions.strip() == "" or len(c.conditions.strip()) < 200 or corrupted_regex.search(c.conditions or ""):
                    is_defective = True
                    if not c.conditions:
                        reasons.append("Missing Conditions")
                    elif len(c.conditions.strip()) < 200:
                        reasons.append("Short/Incomplete Conditions")
                    else:
                        reasons.append("Corrupted Conditions")
                
                # Check for Generic/Missing Participation
                is_participation_bad = not c.participation or c.participation.strip() == "" or any(p in (c.participation or "") for p in useless_participations) or "Detayları İnceleyin" in (c.participation or "") or "Otomatik Katılım" in (c.participation or "")
                if is_participation_bad:
                    is_defective = True
                    reasons.append("Missing/Generic Participation Text")
                
                if not c.ai_marketing_text or len(c.ai_marketing_text.strip()) < 10:
                    is_defective = True
                    reasons.append("Missing Marketing Summary")
                
                # Check for Truncated/Short Clean Text (New: Auto-Rescue Trigger)
                if not c.clean_text or len(c.clean_text.strip()) < 600:
                    is_defective = True
                    if not c.clean_text:
                        reasons.append("Missing Clean Text")
                    else:
                        reasons.append("Short/Truncated Source Text")
                else:
                    # SMART METADATA VERIFICATION (Comparing columns with Clean Text)
                    clean_lower = (c.clean_text or "").lower()
                    
                    # 1. Cards Smart Check
                    card_keywords = ["platinum", "gold", "business", "ticari", "troy", "amex", "kurumsal", "miles", "wings", "chip-para"]
                    found_cards = [k for k in card_keywords if k in clean_lower]
                    current_cards_lower = (c.eligible_cards or "").lower()
                    
                    # 🛡️ NEGATION CONTEXT FILTER: Skip keywords that only appear in exclusion sentences.
                    # e.g. "ticari kartlar ve Bankomat Kartlar ile yapılan işlemler dahil değildir"
                    # should NOT trigger "Incomplete Cards".
                    negation_markers = ["dahil değil", "dahil degil", "geçerli değil", "gecerli degil", "hariçtir", "harictir", "kapsam dışı", "kapsam disi", "geçersiz", "gecersiz"]
                    def _keyword_only_in_negation(kw, text):
                        import re as _re
                        for m in _re.finditer(rf'\b{_re.escape(kw)}\b', text, _re.IGNORECASE):
                            window = text[max(0,m.start()-200):m.end()+200]
                            if not any(n in window for n in negation_markers):
                                return False  # at least one non-negated occurrence
                            return True  # all occurrences are in negation context

                    found_cards = [k for k in found_cards if not _keyword_only_in_negation(k, clean_lower)]

                    if found_cards and not any(k in current_cards_lower for k in found_cards):
                        # If clean_text mentions specific cards but column is generic/missing
                        is_defective = True
                        reasons.append(f"Incomplete Cards (Found in text: {', '.join(found_cards)})")
                    
                    # 2. Participation Smart Check
                    part_keywords = ["sms", "gonder", "uygulama", "mobil", "katil", "mesaj", "bonusflas", "world mobil", "maximum mobil", "paraf mobil"]
                    found_parts = [k for k in part_keywords if k in clean_lower]
                    current_part_lower = (c.participation or "").lower()
                    
                    # Flag as incomplete if keywords found in text but column is very generic or short
                    if found_parts and (not current_part_lower or len(current_part_lower) < 20 or "detay" in current_part_lower):
                        is_defective = True
                        reasons.append(f"Incomplete Participation (Found in text: {', '.join(found_parts)})")

                # Sektör ve Marka Kontrolleri
                valid_slugs = set(SECTOR_MAP.values())
                if not c.sector_id or (c.sector and (c.sector.slug == "diger" or c.sector.slug not in valid_slugs)):
                    is_defective = True
                    reasons.append("Missing/Bad Sector")

                if not c.brands:
                    is_defective = True
                    reasons.append("Missing Brands")
                else:
                    wrong_bank_brands = [
                        "Garanti BBVA", "Garanti", "Garanti Bankası", "Bonus", "Akbank", "Axess",
                        "İş Bankası", "Türkiye İş Bankası", "Maximum", "Maximiles", "Yapı Kredi", "World", 
                        "Halkbank", "Paraf", "VakıfBank", "Kuveyt Türk", "Ziraat", "Ziraat Bankası", 
                        "Bankkart", "Enpara", "QNB", "Finansbank", "QNB Finansbank", "TEB", "DenizBank", "CEPTETEB",
                        "Miles&Smiles", "Shop&Fly", "Wings", "Ticari"
                    ]
                    # Combine with Global Exclusions (Mastercard, Visa, TROY etc.)
                    wrong_bank_brands.extend(list(_GLOBAL_BRAND_EXCLUSIONS))
                    for b in c.brands:
                        b_name = b.name if hasattr(b, 'name') else str(b)
                        b_name_strip = b_name.strip()
                        if b_name_strip in _GLOBAL_BRAND_EXCLUSIONS:
                            is_defective = True
                            reasons.append(f"Blacklisted Brand (Card Network): {b_name_strip}")
                            break
                        if b_name_strip in wrong_bank_brands:
                            is_defective = True
                            reasons.append(f"Invalid Bank Brand: {b_name_strip}")
                            break
                        if b_name_strip.lower() == "genel":
                            is_defective = True
                            reasons.append("Review 'Genel' Brand")
                            break

                # ---------------------------------------------------------------
                # 🔍 YENİ KONTROL 1: Duplicate Brand Pattern (Footer/Sidebar Scraping)
                # Aynı card_id'ye sahip kampanyalarda birebir aynı marka setinin
                # 3+ farklı kampanyada tekrarlanması → scraper footer'ı çekiyor demektir.
                # ---------------------------------------------------------------
                if c.brands and c.card_id and not is_defective:
                    try:
                        campaign_brand_ids = frozenset(b.brand_id for b in c.brands)
                        if len(campaign_brand_ids) >= 2:  # En az 2 marka varsa anlamlı
                            # Aynı card_id'li diğer kampanyaları ara
                            sibling_campaigns = db.query(Campaign).filter(
                                Campaign.card_id == c.card_id,
                                Campaign.id != c.id,
                                Campaign.is_active == True
                            ).options(joinedload(Campaign.brands)).limit(200).all()
                            
                            duplicate_count = 0
                            for sib in sibling_campaigns:
                                sib_brand_ids = frozenset(b.brand_id for b in sib.brands)
                                if sib_brand_ids == campaign_brand_ids:
                                    duplicate_count += 1
                                if duplicate_count >= 3:
                                    break
                            
                            if duplicate_count >= 3:
                                is_defective = True
                                reasons.append(f"Duplicate Brand Pattern ({duplicate_count} sibling campaigns share identical brand set)")
                    except Exception as _dbe:
                        pass  # Brand kontrol hatası asıl süreci engellemesin

                # ---------------------------------------------------------------
                # 🔍 YENİ KONTROL 2: Irrelevant Brand / Over-Tagging
                # Kampanya başlığında HİÇBİR marka adı geçmiyorsa
                # VE kampanyada 5+ marka etiketliyse
                # VE bu markalar aynı karta ait diğer kampanyalarda da aynıysa
                # → over-tagging şüphesi
                # ---------------------------------------------------------------
                if c.brands and c.card_id and not is_defective:
                    try:
                        brand_names_for_check = [b.name if hasattr(b, 'name') else str(b) for b in c.brands]
                        # brand_ids üzerinden erişimi dene (CampaignBrand ilişkisi)
                        brand_names_for_check = []
                        for cb in c.brands:
                            if hasattr(cb, 'brand') and cb.brand:
                                brand_names_for_check.append(cb.brand.name)
                            elif hasattr(cb, 'name'):
                                brand_names_for_check.append(cb.name)

                        if len(brand_names_for_check) >= 5:
                            title_lower = (c.title or "").lower()
                            # Başlıkta hiçbir marka adı geçmiyor mu?
                            title_has_any_brand = any(
                                brand_name.lower() in title_lower
                                for brand_name in brand_names_for_check
                                if len(brand_name) > 3
                            )

                            if not title_has_any_brand:
                                # Bu marka seti diğer kampanyalarda da var mı?
                                campaign_brand_ids = frozenset(b.brand_id for b in c.brands)
                                sibling_campaigns = db.query(Campaign).filter(
                                    Campaign.card_id == c.card_id,
                                    Campaign.id != c.id,
                                    Campaign.is_active == True
                                ).options(joinedload(Campaign.brands)).limit(200).all()

                                overlap_count = 0
                                for sib in sibling_campaigns:
                                    sib_brand_ids = frozenset(b.brand_id for b in sib.brands)
                                    # En az %60 örtüşme → şüpheli
                                    if campaign_brand_ids and sib_brand_ids:
                                        intersection = len(campaign_brand_ids & sib_brand_ids)
                                        union = len(campaign_brand_ids | sib_brand_ids)
                                        overlap_ratio = intersection / union if union > 0 else 0
                                        if overlap_ratio >= 0.6:
                                            overlap_count += 1
                                    if overlap_count >= 2:
                                        break

                                if overlap_count >= 2:
                                    is_defective = True
                                    reasons.append(
                                        f"Irrelevant Brand / Over-Tagging Suspected "
                                        f"({len(brand_names_for_check)} brands, none in title, "
                                        f"{overlap_count} siblings with ≥60% overlap)"
                                    )
                    except Exception as _obe:
                        pass  # Over-tagging kontrol hatası asıl süreci engellemesin

                # Onay bekleyen (unapproved) kampanyalar için bekleme süresi ve deneme sınırlarını kaldırarak
                # her zaman en taze ve en kaliteli AI onarımını (tıpkı paneldeki 'Tamir Et' gibi) zorla!
                force_campaign = FORCE_ALL or (not c.is_approved)

                # FORCE REPAIR IF:
                # 1. SPECIFIC ID IS PROVIDED
                # 2. IDS_FILE MODE IS ACTIVE
                # 3. IT'S A PENDING CAMPAIGN (Always run force repair for unapproved campaigns to maximize quality)
                if (campaign_id or ids_file or not c.is_approved) and not is_defective:
                    is_defective = True
                    if not c.is_approved:
                        reasons.append("Force Repair for Pending Approval")
                    else:
                        reasons.append(f"Manual Force Repair (List Mode)")

                if is_defective and c.tracking_url:
                    # COOLDOWN & PERMANENT SKIP LOGIC
                    # REPAIR COUNT & FORCE UPGRADE LOGIC
                    max_repairs = 4 if (c.quality_score is None or c.quality_score < 70) else 2
                    if c.repair_count >= max_repairs and not force_campaign and not campaign_id:
                        stats["skipped_cooldown"] += 1
                        continue
                    
                    # Cooldown check for retries (if repair_count > 0)
                    if c.repair_count > 0 and not force_campaign and not campaign_id:
                        last_update = c.updated_at or c.created_at
                        if now - last_update < cooldown_period:
                            stats["skipped_cooldown"] += 1
                            continue
                    
                    if (c.auto_corrected or c.repair_count > 0) and (c.quality_score is not None and c.quality_score >= 70):
                        # If already corrected once and has a passing score, ONLY retry if:
                        # 1. Severe text corruption
                        # 2. OR it STILL has an Invalid Bank Brand (New rules need to clean this up)
                        # 3. OR it has Incomplete Metadata (Cards/Participation missed by AI)
                        # 4. OR force_campaign is active
                        has_bank_error = any("Invalid Bank Brand" in r for r in reasons)
                        has_metadata_error = any("Incomplete Cards" in r or "Incomplete Participation" in r for r in reasons)
                        
                        if not (is_corrupted or has_mojibake or has_bank_error or has_metadata_error) and not force_campaign:
                            stats["skipped_cooldown"] += 1
                            continue
                        stats["retry"] += 1
                    else:
                        stats["new"] += 1
                    
                    to_fix_ids.append((c.id, c.tracking_url, reasons))
                    if len(to_fix_ids) >= limit:
                        print(f"   ⚠️ Reached limit of {limit} campaigns. Stopping search.")
                        break
            
            print(f"   📊 Found defects: {stats['new']} new, {stats['retry']} retries. (Skipped permanently or by cooldown: {stats['skipped_cooldown']})")

            print(f"⚠️ Total campaigns to process in this run: {len(to_fix_ids)} (FORCE_ALL={FORCE_ALL})")
            
            if not to_fix_ids:
                print("✅ All active campaigns look healthy!")
                if not ui_mode:
                    audit_approved_campaign_cards()
                return
                
        fixed_count = 0
            
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        lock = threading.Lock()
        fixed_count_arr = [0]

        def process_campaign(args):
                item, worker_idx = args
                c_id, tracking_url, reasons_list = item
                thread_local.key_index = (worker_idx % 8) + 1
                summary_reasons = ", ".join(reasons_list)
                
                with get_db_session() as db:
                    c = db.query(Campaign).options(
                        joinedload(Campaign.card).joinedload(Card.bank),
                        joinedload(Campaign.sector),
                        joinedload(Campaign.brands)
                    ).filter(Campaign.id == c_id).first()
                    if not c:
                        print(f"\n🛠️ Skipping: [{c_id}] (Campaign no longer in DB)")
                        return False
                    
                    # Onay bekleyen kampanyalar için en yüksek kaliteyi sağlamak adına force modunu aç!
                    force_campaign = FORCE_ALL or (not c.is_approved)
                        
                    print(f"\n🛠️ Fixing: [{c.id}] {c.title[:40]}... (Reasons: {summary_reasons})")
                    print(f"   🔗 URL: {c.tracking_url}")
                    
                    # Determine if we need a fresh fetch (Rescue)
                    is_truncated = any("Short/Truncated Source Text" in r for r in reasons_list)
                    text_to_parse = ""
                    
                    # Force rescue if campaign_id is specifically requested (UI Repair Button)
                    # 🛑 EXCEPTION: SPA domains (maximum.com.tr etc.) must NEVER force live fetch
                    # because requests-based fetching returns broken/partial JS content.
                    spa_domains_block = ["maximum.com.tr", "maximiles.com.tr", "privia.com.tr", "worldcard.com.tr"]
                    is_spa_url = any(spa in (c.tracking_url or "") for spa in spa_domains_block)
                    db_text_len = len(c.clean_text) if c.clean_text else 0
                    
                    is_rescue_active = force_rescue
                    
                    # Eğer kampanya 3. denemeden sonra da düzeltilemediyse (yani repair_count >= 3 ise, 4. deneme ve sonrası),
                    # veritabanındaki yetersiz/eksik clean_text'i baypas edip siteden sıfırdan canlı HTML çekiyoruz (rescue).
                    if (c.repair_count or 0) >= 3:
                        is_rescue_active = True
                        print(f"   💡 Defective after {c.repair_count} attempts: Forcing live rescue fetch from scratch.")

                    if is_spa_url and db_text_len > 600:
                        is_rescue_active = False  # Never force-fetch SPAs with good DB data
                        print(f"   🔒 SPA domain detected. Force-rescue disabled. Using DB text ({db_text_len} chars).")
                    
                    # Initialize repair metadata
                    repair_meta = {"source": "DB", "status": "CLEAN_TEXT_USED"}
                    og_title = None
                    
                    if c.clean_text and len(c.clean_text) >= 600 and not is_truncated and not mojibake_pattern.search(c.clean_text) and not is_rescue_active and not force_campaign:
                        print(f"   ⚡ Using pre-cleaned text from DB ({len(c.clean_text)} chars)")
                        text_to_parse = c.clean_text
                    else:
                        print(f"   🌐 Logic: RESCUE! (Force mode or text issue). Fetching fresh HTML...")
                        
                        # Step 1: Fetch raw HTML for title
                        try:
                            import urllib3
                            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                            headers = {
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                            }
                            _raw_resp = requests.get(c.tracking_url, headers=headers, timeout=15, verify=False)
                            _raw_resp.raise_for_status()
                            from bs4 import BeautifulSoup as _BS
                            _raw_soup = _BS(_raw_resp.text, "html.parser")
                            # 🛡️ Skip H1 title extraction for Opet as it's usually generic "Kampanyalar"
                            if "opet" not in (c.tracking_url or "").lower():
                                _h1s = _raw_soup.find_all('h1')
                                _h1 = None
                                for h in _h1s:
                                    h_text = h.get_text(strip=True)
                                    if h_text and not any(kw in h_text.lower() for kw in ["çerez", "cookie", "aydınlatma metni"]):
                                        _h1 = h
                                        break
                                
                                if _h1:
                                    og_title = _h1.get_text(strip=True)
                                    print(f"   🏷️ Valid H1 title found: {og_title}")
                        except Exception as _e:
                            print(f"   ⚠️ Raw title fetch failed: {_e}")
                        
                        # Step 2: Full HTML Fetch
                        html_text, live_status = fetch_html(c.tracking_url)
                        
                        if html_text and len(html_text) >= 150:
                            fetched_cleaned = clean_campaign_text(html_text, og_title=og_title, title=c.title)
                            # 🛡️ DB TEXT PROTECTION: Never overwrite longer DB text with shorter live content UNLESS live content is already long enough and clean (350+ chars)
                            is_live_trustworthy = len(fetched_cleaned) >= 350 or (campaign_id is not None)
                            if db_text_len > 0 and len(fetched_cleaned) < db_text_len * 0.7 and not is_live_trustworthy:
                                print(f"   ⚠️ URL fetch returned significantly less/no data ({len(fetched_cleaned)} vs {db_text_len} DB chars). Falling back to DB content.")
                                text_to_parse = c.clean_text
                                repair_meta["source"] = "DB"
                                repair_meta["status"] = "DB_FALLBACK_LIVE_TOO_SHORT"
                            else:
                                text_to_parse = fetched_cleaned
                                repair_meta["source"] = "LIVE"
                                repair_meta["status"] = live_status
                                print(f"   ✅ URL fetch successful ({len(text_to_parse)} chars)")
                        else:
                            print(f"   ⚠️ [CODE: {live_status}] URL fetch failed. Falling back to DB content.")
                            fallback_segments = []
                            if c.description: fallback_segments.append(c.description)
                            if c.conditions: fallback_segments.append(c.conditions)
                            fallback_text = " ".join(fallback_segments)
                            
                            if len(fallback_text) > 20:
                                text_to_parse = fallback_text
                                repair_meta["source"] = "DB_FALLBACK"
                                repair_meta["status"] = live_status
                            else:
                                print(f"   ❌ [ERR_CODE: CONTENT_NOT_FOUND] Could not extract meaningful text.")
                                return False

                    # Determine bank name for AI parser
                    bank_name = c.card.bank.name if c.card and c.card.bank else None
                    
                    # Title fix logic
                    ai_title_pass = c.title or ''
                    if len(ai_title_pass.split()) > 15:
                        print(f"   🔓 DB Title is too long - Erasing lock for AI.")
                        ai_title_pass = ''
                    elif any(delim in ai_title_pass for delim in ["|", " - ", " – "]) and "vodafone" in ai_title_pass.lower():
                        print(f"   🔓 DB Title contains Vodafone suffix - Erasing lock for AI to allow clean H1/AI extraction.")
                        ai_title_pass = ''

                    # AI Parsing
                    print(f"   🤖 [GOLDEN V3] Sending {len(text_to_parse)} chars to AI... (Bank: {bank_name or 'Unknown'})")
                    print(f"   🔍 DEBUG: Context snippet: {text_to_parse[:200].replace(chr(10), ' ')}...")
                    
                    parser = _get_golden_parser(model=model, fallback_model=fallback_model)
                    ai_data = parser.parse_campaign(
                        raw_html=text_to_parse,
                        bank_name=bank_name or '',
                        title=ai_title_pass,
                        og_title=og_title,
                        scraper_sector=None,
                        is_already_clean=True
                    )
                    
                    if ai_data:
                        print(f"   🤖 AI EXTRACTION: {ai_data.get('cards')}")
                        if ai_data.get('brands'):
                            print(f"   🏷️ BRANDS: {ai_data.get('brands')}")
                    
                    if ai_data:
                        ai_data["repair_metadata"] = {
                            "source": repair_meta["source"],
                            "status": repair_meta["status"],
                            "reasons": reasons_list,
                            "campaign_id": c.id
                        }
                    
                    if not ai_data:
                        print(f"   ❌ Gemini AI failed to return data. Skipping.")
                        return False

                    # 🛡️ REJECT FAILED AI RESPONSES
                    if ai_data.get("_ai_failed"):
                        print(f"   ❌ AI returned fallback/failed data (_ai_failed=True). Skipping.")
                        return False
                    
                    # 🛡️ SANITIZE PLACEHOLDERS — AI bazen tembel cevap veriyor, DB'ye yazılmasını engelle
                    _placeholders = ["detayları inceleyin", "hemen faydalanın", "kampanya dahilinde", "detayları aşağıda"]
                    for field in ["reward_text", "participation"]:
                        val = (ai_data.get(field) or "").strip()
                        if val.lower() in _placeholders or len(val) < 3:
                            ai_data[field] = None  # None = "güncelleme yapma, mevcut değeri koru"
                            print(f"   🛡️ Placeholder rejected for '{field}': '{val}'")
                        
                    # Update logic
                    updated = False
                    
                    generic_titles = ["nays'ın kazandıran özellikleri", "opet kampanyası", "ayrıcalıklar", "kampanyalar", "fırsatlar", "akaryakıt standartları bilgilendirmesi"]
                    is_title_generic = c.title and c.title.lower().strip() in generic_titles
                    
                    # Update Title
                    if not c.title or is_title_generic or force_campaign:
                        if ai_data.get("title") and ai_data["title"] != c.title:
                            ai_title = ai_data["title"]
                            if any(kw in ai_title.lower() for kw in ["çerez", "cookie", "aydınlatma metni"]):
                                print(f"   🛡️ AI returned a cookie-related title: '{ai_title}'. Ignoring.")
                            else:
                                print(f"   ✨ Repaired Title: {c.title} -> {ai_title}")
                                c.title = ai_title
                                updated = True

                    # Update Description
                    if not c.description or len(c.description.strip()) < 15 or force_campaign:
                        if ai_data.get("description"):
                            print(f"   ✨ Repaired Description!")
                            c.description = ai_data["description"]
                            updated = True
                            
                    # Update Reward Text
                    is_reward_bad = not c.reward_text or c.reward_text.strip() == "" or "Detayları İnceleyin" in c.reward_text
                    if is_reward_bad or force_campaign:
                        if ai_data.get("reward_text"):
                            print(f"   ✨ Repaired Reward Text: {ai_data['reward_text']}")
                            c.reward_text = ai_data["reward_text"]
                            updated = True
                            
                    if c.reward_value is None or force_campaign:
                        if ai_data.get("reward_value") is not None:
                            print(f"   ✨ Repaired Reward Value: {ai_data['reward_value']}")
                            c.reward_value = ai_data["reward_value"]
                            updated = True
                            
                    if not c.reward_type or c.reward_type.strip() == "" or force_campaign:
                        if ai_data.get("reward_type"):
                            print(f"   ✨ Repaired Reward Type: {ai_data['reward_type']}")
                            c.reward_type = ai_data["reward_type"]
                            updated = True
                            
                    # Update Eligible Cards if missing, corrupted, generic, OR incomplete
                    is_cards_empty = not c.eligible_cards or c.eligible_cards.strip() == ""
                    is_cards_corrupted = "Kampanyaya Dahil Kartlar" in (c.eligible_cards or "") or corrupted_regex.search(c.eligible_cards or "")
                    is_cards_incomplete = any("Incomplete Cards" in r for r in reasons_list)
                    
                    # 🆕 WRONG CARDS CHECK: If AI produces a DIFFERENT (cleaner) set of cards, always update.
                    # This catches cases where AI correctly removes excluded cards (Bankomat, Platinum, etc.)
                    # even when the defect reason is something else (e.g. "Missing Brands").
                    ai_cards_set = set(ai_data.get("cards") or [])
                    current_cards_set = set((c.eligible_cards or "").split(", ")) if c.eligible_cards else set()
                    is_cards_wrong = bool(ai_cards_set) and ai_cards_set != current_cards_set

                    if is_cards_empty or is_cards_corrupted or is_cards_incomplete or is_cards_wrong or force_campaign:
                        if ai_data.get("cards") is not None:
                            ai_cards = ai_data.get("cards") or []
                            cards_str = ", ".join(ai_cards) if len(ai_cards) > 0 else "-"

                            if is_cards_incomplete:
                                print(f"   ✨ Upgraded Incomplete Cards: {c.eligible_cards} → {cards_str}")
                            elif is_cards_wrong:
                                print(f"   ✨ Corrected Wrong Cards: {c.eligible_cards} → {cards_str}")
                            else:
                                print(f"   ✨ Repaired Eligible Cards: {cards_str}")
                            c.eligible_cards = cards_str
                            updated = True

                    def get_last_day_of_month(date_obj):
                        import calendar
                        last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
                        res = date_obj.replace(day=last_day)
                        # If it's a datetime object, convert to date. If it's already a date, just return it.
                        return res.date() if hasattr(res, 'date') else res

                    baseline_date = c.created_at or datetime.now()

                    # Start Date Repair
                    if not c.start_date or force_campaign:
                        new_start = None
                        if ai_data.get("start_date"):
                            try:
                                new_start = datetime.strptime(ai_data["start_date"], "%Y-%m-%d").date()
                            except: pass
                        
                        # Fallback if AI didn't find it
                        if not new_start:
                            print(f"   🔄 Falling back Start Date to Created At: {baseline_date.date()}")
                            new_start = baseline_date.date()
                        
                        if new_start:
                            c.start_date = new_start
                            updated = True
                            print(f"   ✨ Repaired Start Date: {c.start_date}")

                    # End Date Repair
                    if not c.end_date or force_campaign:
                        new_end = None
                        if ai_data.get("end_date"):
                            try:
                                new_end = datetime.strptime(ai_data["end_date"], "%Y-%m-%d").date()
                            except: pass
                        
                        # Fallback if AI didn't find it
                        if not new_end:
                            # For continuous campaigns, fallback to 3 months ahead of start_date/reference to keep it active
                            reference = c.start_date or baseline_date.date()
                            # Add approx 90 days to reference date
                            import datetime
                            future_date = reference + datetime.timedelta(days=90)
                            new_end = get_last_day_of_month(future_date)
                            print(f"   🔄 Falling back End Date to Continuous Mode (3 Months Ahead): {new_end}")

                        if new_end:
                            c.end_date = new_end
                            updated = True
                            print(f"   ✨ Repaired End Date: {c.end_date}")
                            
                    # Update Conditions if missing, corrupted or force_campaign
                    if not c.conditions or c.conditions.strip() == "" or corrupted_regex.search(c.conditions) or force_campaign:
                        if ai_data.get("conditions"):
                            print(f"   ✨ Repaired Conditions!")
                            c.conditions = "\n".join(cond for cond in ai_data.get("conditions", []))
                            updated = True


                    # Clean and update Participation
                    is_curr_p_bad = not c.participation or c.participation.strip() == "" or any(p in (c.participation or "") for p in useless_participations) or corrupted_regex.search(c.participation) or "Otomatik Katılım" in (c.participation or "")
                    if is_curr_p_bad or force_campaign:
                        if ai_data.get("participation"):
                            print(f"   ✨ Repaired Participation: {ai_data['participation'][:50]}...")
                            c.participation = ai_data["participation"]
                            updated = True

                    # --- AI Marketing Text (Marketing Summary) update ---
                    if ai_data.get("ai_marketing_text"):
                        # We always update this to get fresh summaries
                        print(f"   ✨ Repaired Marketing Summary!")
                        c.ai_marketing_text = ai_data["ai_marketing_text"]
                        updated = True

                    # --- Clean Text Update ---
                    # Update if missing, too short, or has mojibake
                    if not c.clean_text or len(c.clean_text.strip()) < 50 or mojibake_pattern.search(c.clean_text or ""):
                        if text_to_parse:
                            c.clean_text = text_to_parse
                            updated = True

                    # --- Sektör tamiri ---
                    ai_sector_raw = ai_data.get("sector", "diger")
                    if isinstance(ai_sector_raw, list):
                        ai_sector_raw = ai_sector_raw[0] if len(ai_sector_raw) > 0 else "diger"
                    
                    final_sector_slug = SECTOR_MAP.get(ai_sector_raw, ai_sector_raw)
                    if final_sector_slug not in SECTOR_MAP.values():
                        final_sector_slug = "diger"
                    
                    # 🎯 PBE SEKTÖR OVERRIDE — PBE doğrulanmış veri, AI tahmininden üstündür.
                    # Ancak Opet, Shell, Vodafone gibi "Host" markaların sektörünün, iş ortağı markanın sektörünü ezmesini engelliyoruz.
                    pb_matcher = get_point_blank_matcher(db)
                    pb_matches = pb_matcher.match_campaign(c.title, text_to_parse or "")
                    
                    if pb_matches:
                        # 🛡️ HOST PROTECTION: Eğer birden fazla eşleşme varsa ve biri partner (Guest) ise ona öncelik ver.
                        host_slugs = {'turk-telekom', 'vodafone', 'turkcell', 'shell', 'opet', 'petrol-ofisi', 'totalenergies'}
                        guest_matches = [m for m in pb_matches if m.get('sector') not in ['fatura-telekomunikasyon', 'akaryakit']]
                        if guest_matches:
                            pb_matches = guest_matches + [m for m in pb_matches if m not in guest_matches]

                    pb_sector_candidates = [m.get("sector") for m in pb_matches if m.get("sector") and m.get("brand")]
                    if pb_sector_candidates:
                        pb_sector = pb_sector_candidates[0]  # Önceliklendirilmiş ilk marka eşleşmesinin sektörü
                        if pb_sector != final_sector_slug and pb_sector != "diger":
                            print(f"   🎯 PBE Override (Partner Priority): AI said '{final_sector_slug}', PBE says '{pb_sector}' → using PBE")
                            final_sector_slug = pb_sector
                        
                    current_sector_slug = c.sector.slug if c.sector else None
                    
                    # --- Sektör Güncelleme Kararı ---
                    # 1. Mevcut "diger" ise → AI'nın spesifik sektörünü kabul et (upgrade)
                    # 2. Mevcut spesifik ama bilinen çelişki varsa → düzelt
                    # 3. Mevcut zaten spesifik ve çelişki yoksa → koru
                    
                    is_current_diger = not current_sector_slug or current_sector_slug == "diger"
                    
                    # Bilinen çelişki: Kültür Sanat ama seyahat/ulaşım kelimeleri var
                    travel_keywords = ['uçak', 'bilet', 'feribot', 'otel', 'hotel', 'konaklama', 'turizm', 'otobüs', 'seyahat']
                    title_lower = (c.title or "").lower()
                    text_lower = (text_to_parse or "").lower()[:300]
                    has_travel_conflict = (
                        current_sector_slug == "kultur-sanat" and 
                        any(k in title_lower or k in text_lower for k in travel_keywords)
                    )
                    
                    has_pb_override = pb_sector_candidates and pb_sector_candidates[0] == final_sector_slug and final_sector_slug != "diger"

                    should_update_sector = False
                    if final_sector_slug == "diger":
                        # AI "diger" diyorsa hiçbir zaman güncelleme (downgrade etme)
                        if not is_current_diger:
                            print(f"   🛡️ Sector '{current_sector_slug}' preserved (AI said 'diger', keeping specific).")
                    elif final_sector_slug == current_sector_slug:
                        pass  # Aynı sektör, güncelleme gerekmez
                    elif is_current_diger:
                        should_update_sector = True  # Upgrade: diger → spesifik
                    elif has_pb_override or FORCE_ALL:
                        should_update_sector = True  # PBE kuralı her zaman AI'ı ve mevcut sektörü ezer
                        print(f"   🎯 Forcing Sector Update: PBE or FORCE flag is active!")
                    elif has_travel_conflict:
                        should_update_sector = True  # Bilinen çelişki düzeltmesi
                        print(f"   🔧 Sector conflict detected: travel keywords + kultur-sanat")
                    else:
                        # Mevcut spesifik, AI farklı spesifik diyor → mevcut korunur
                        print(f"   🛡️ Sector '{current_sector_slug}' preserved (AI suggested '{final_sector_slug}', but existing is already specific).")
                    
                    if should_update_sector:
                        sector = db.query(Sector).filter(Sector.slug == final_sector_slug).first()
                        if sector:
                            old_name = c.sector.name if c.sector else 'Yok'
                            c.sector_id = int(sector.id)
                            print(f"   ✨ Repaired Sector: {old_name} → {sector.name}")
                            updated = True

                    # --- Marka tamiri (Safe-Update & Multi-Brand) ---
                    added_brand_ids = set()
                    needs_brand_fix = False
                    is_brand_consistency_fix = False  # Duplicate/Over-Tagging düzeltmesi işareti
                    if not c.brands or (campaign_id or ids_file):
                        needs_brand_fix = True
                    elif reasons_list:
                        for r in reasons_list:
                            if "Invalid Bank Brand" in r:
                                needs_brand_fix = True
                                break
                            if "Duplicate Brand Pattern" in r or "Over-Tagging Suspected" in r:
                                needs_brand_fix = True
                                is_brand_consistency_fix = True
                                break

                    if needs_brand_fix and "brands" in ai_data:
                        from src.services.brand_matcher import get_or_create_brand  # type: ignore
                        brand_cache = {} 
                        
                        # Mevcut markaları analiz et (Nokta Atışı ile eşleşenleri korumak için)
                        existing_brand_ids = {getattr(b, 'id', None) for b in c.brands}
                        existing_brand_ids = {bid for bid in existing_brand_ids if bid is not None}
                        new_brand_names = ai_data["brands"]
                        if not isinstance(new_brand_names, list):
                            new_brand_names = [new_brand_names] if new_brand_names else []
                            
                        # 🎯 AI-FIRST BRAND STRATEGY (GOLDEN PARSER = SOURCE OF TRUTH)
                        # We no longer manually merge PointBlank brands here because AIParserGolden 
                        # natively integrates PBE rules, validates them, and strictly filters out
                        # illusions and self-brands (like Opet, Apple, Google).
                        
                        validated_brands = list(new_brand_names)
                        new_brand_names = []
                        for b_name in validated_brands:
                            if b_name and b_name != "Genel":
                                new_brand_names.append(b_name)
                        
                        # If we are in force/id-file mode OR brand consistency fix → PURGE all brands for a clean slate
                        # Otherwise, we only purge the ones identified as bank brands
                        correct_brand_ids_to_keep = []
                        if is_brand_consistency_fix:
                            # Duplicate Pattern veya Over-Tagging durumunda tüm markalar temizlenir,
                            # sadece AI'ın yeniden ürettiği markalar yazılır.
                            print(f"   🧹 [Brand Consistency Fix] Purging ALL brands for clean re-tagging.")
                        elif not (campaign_id or ids_file):
                            for cb in db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).all():
                                b_obj = db.query(Brand).filter(Brand.id == cb.brand_id).first()
                                if b_obj and b_obj.name not in wrong_bank_brands:
                                    correct_brand_ids_to_keep.append(cb.brand_id)
                        # is_brand_consistency_fix=True durumunda correct_brand_ids_to_keep [] kalır (full purge)
                        
                        # Kampanya bağlarını sıfırla
                        db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).delete()
                        db.flush()
                        
                        added_brand_ids = set()
                        
                        if correct_brand_ids_to_keep:
                            for bid in correct_brand_ids_to_keep:
                                db.add(CampaignBrand(campaign_id=c.id, brand_id=bid))
                                added_brand_ids.add(bid)
                            
                            preserved_names = []
                            for bid in correct_brand_ids_to_keep:
                                b_obj = db.query(Brand).filter(Brand.id == bid).first()
                                if b_obj: preserved_names.append(b_obj.name)
                            print(f"   🛡️ Preserved Brands: {', '.join(preserved_names)}")
                        else:
                            print(f"   🧹 Purged all existing brands for fresh repair.")

                        # AI'dan gelen yeni markaları ekle
                        for b_name in new_brand_names:
                            if not isinstance(b_name, str) or len(b_name) < 2:
                                continue
                            if b_name in wrong_bank_brands:
                                continue
                                
                            try:
                                brand = get_or_create_brand(db, b_name, brand_cache)
                                if brand:
                                    if brand.id not in added_brand_ids:
                                        db.add(CampaignBrand(campaign_id=c.id, brand_id=brand.id))
                                        added_brand_ids.add(brand.id)
                                        print(f"   ✨ Added Brand: {brand.name}")
                                        updated = True
                            except Exception as be:
                                print(f"   ⚠️ Brand fix failed for {b_name}: {be}")
                        db.flush()
                        db.refresh(c)

                    # -------------------------------------------------------------
                    # 📊 DYNAMIC QUALITY SCORE CALCULATION & PEER-REVIEW FACT-CHECKER
                    # -------------------------------------------------------------
                    score = 0
                    
                    # 1. Title Validation (20 pts)
                    has_valid_title = c.title and len(c.title.strip()) > 5 and not any(gt in c.title.lower() for gt in ["çerez", "cookie", "aydınlatma", "nays'ın kazandıran", "opet kampanyası", "ayrıcalıklar", "kampanyalar", "fırsatlar", "akaryakıt standartları"])
                    if has_valid_title:
                        score += 20
                    
                    # 2. Description Validation (20 pts)
                    has_valid_desc = c.description and len(c.description.strip()) > 20 and not corrupted_regex.search(c.description)
                    if has_valid_desc:
                        score += 20
                    
                    # 3. Eligible Cards Validation (15 pts)
                    has_valid_cards = c.eligible_cards and c.eligible_cards.strip() != "" and c.eligible_cards.strip() != "-" and "Kampanyaya Dahil Kartlar" not in c.eligible_cards and not corrupted_regex.search(c.eligible_cards)
                    if has_valid_cards:
                        score += 15
                    
                    # 4. Reward Text Validation (15 pts)
                    has_valid_reward = c.reward_text and c.reward_text.strip() != "" and not any(p in c.reward_text for p in ["Detayları İnceleyin", "Hemen Faydalanın", "Harcamadan Önce"])
                    if has_valid_reward:
                        score += 15
                    
                    # 5. Participation Validation (10 pts)
                    has_valid_part = c.participation and c.participation.strip() != "" and not any(p in c.participation for p in useless_participations)
                    if has_valid_part:
                        score += 10
                    
                    # 6. Sector Validation (10 pts)
                    has_valid_sector = c.sector_id and final_sector_slug != "diger"
                    if has_valid_sector:
                        score += 10
                    
                    # 7. Brands Validation (10 pts)
                    has_valid_brands = len(added_brand_ids) > 0 or len([b for b in c.brands if b.brand.name not in wrong_bank_brands]) > 0
                    if has_valid_brands:
                        score += 10

                    c.quality_score = score
                    print(f"   📊 Computed Base Quality Score: {score}/100")

                    # Run Peer-Review Fact-Checker if score is promising (>= 70) and NOT in UI mode (manual repair)
                    fact_checker_passed = False
                    if score >= 70 and text_to_parse and not ui_mode:
                        print("   🔬 [Fact-Checker] Initiating Peer-Review NLI Verification...")
                        try:
                            checker = FactCheckerAgent(model=model or "models/gemini-3.1-flash-lite")
                            candidate = {
                                "reward_text": c.reward_text,
                                "reward_value": float(c.reward_value) if c.reward_value is not None else None,
                                "reward_type": c.reward_type,
                                "cards": c.eligible_cards.split(", ") if c.eligible_cards else [],
                                "participation": c.participation,
                                "sector": c.sector.name if c.sector else "Diğer",
                                "brands": [db.query(Brand).filter(Brand.id == cb.brand_id).first().name for cb in db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).all() if db.query(Brand).filter(Brand.id == cb.brand_id).first()]
                            }
                            verification = checker.verify_campaign(text_to_parse, candidate)
                            
                            if verification.get("is_grounded") is True:
                                fact_checker_passed = True
                                c.quality_score = max(c.quality_score, 95) # Boost score to at least 95 if fact-checker completely validates it!
                                print(f"   🏆 [Fact-Checker] 100% Grounded! Score boosted to: {c.quality_score}/100")
                            else:
                                # Check if we can heal simple card or brand errors (Self-healing)
                                verifications = verification.get("verifications", {})
                                
                                cards_verification = verifications.get("eligible_cards", {})
                                unsupported_cards = cards_verification.get("unsupported_cards", [])
                                
                                brands_verification = verifications.get("brands", {})
                                unsupported_brands = brands_verification.get("unsupported_brands", [])
                                
                                if (unsupported_cards and cards_verification.get("status") in ["NO", "CONTRADICTION"]) or \
                                   (unsupported_brands and brands_verification.get("status") in ["NO", "CONTRADICTION"]):
                                    
                                    remaining_cards = candidate["cards"]
                                    if unsupported_cards:
                                        print(f"   🩹 [Fact-Checker] Self-Healing Triggered! Removing unsupported cards: {unsupported_cards}")
                                        current_cards = [card.strip() for card in c.eligible_cards.split(", ") if card.strip()]
                                        remaining_cards = [card for card in current_cards if card not in unsupported_cards]
                                        c.eligible_cards = ", ".join(remaining_cards) if remaining_cards else "-"
                                        updated = True
                                        
                                    remaining_brands = candidate["brands"]
                                    if unsupported_brands:
                                        print(f"   🩹 [Fact-Checker] Self-Healing Triggered! Removing unsupported brands: {unsupported_brands}")
                                        # Purge from campaign brands join table
                                        for cb in db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).all():
                                            b_obj = db.query(Brand).filter(Brand.id == cb.brand_id).first()
                                            if b_obj and b_obj.name in unsupported_brands:
                                                db.delete(cb)
                                        db.flush()
                                        remaining_brands = [bname for bname in candidate["brands"] if bname not in unsupported_brands]
                                        updated = True
                                    
                                    # Re-verify with remaining items
                                    print("   🔬 [Fact-Checker] Re-running NLI Verification after self-healing...")
                                    candidate["cards"] = remaining_cards
                                    candidate["brands"] = remaining_brands
                                    re_verification = checker.verify_campaign(text_to_parse, candidate)
                                    if re_verification.get("is_grounded") is True:
                                        fact_checker_passed = True
                                        c.quality_score = max(c.quality_score, 95)
                                        print(f"   🏆 [Fact-Checker] Grounded after Self-Healing! Score: {c.quality_score}/100")
                                    else:
                                        c.quality_score = min(c.quality_score, 60) # Downgrade score since it failed twice
                                        print(f"   ❌ [Fact-Checker] Grounding Failed after Self-Healing. Score downgraded to: {c.quality_score}/100")
                                else:
                                    c.quality_score = min(c.quality_score, 60) # Downgrade score
                                    print(f"   ❌ [Fact-Checker] Hallucination/Grounding Error Detected! Score downgraded to: {c.quality_score}/100")
                                    if verification.get("reason"):
                                        print(f"      Reason: {verification.get('reason')}")
                        except Exception as fe:
                            print(f"   ⚠️ Fact-Checker execution failed: {fe}")

                    # Gated Approval logic (Shadow Mode canary stage)
                    # Keep is_approved = False for all campaigns as requested,
                    # but print a very prominent dry-run notice if it would have been approved.
                    c.is_approved = False  # Strict request: stays manual for now!
                    
                    if c.quality_score >= 95 and fact_checker_passed:
                        print(f"   ✨ 🚀 [SHADOW MODE] Campaign WOULD HAVE BEEN AUTO-APPROVED! Score: {c.quality_score}/100 (Fact-Checker Verified)")
                    else:
                        print(f"   ⚠️ [QUEUE] Campaign will remain in manual approval queue. Score: {c.quality_score}/100")

                    # ALWAYS mark as auto_corrected so we don't try again forever (even if Gemini failed to find missing data)
                    c.auto_corrected = True
                    c.repair_count = (c.repair_count or 0) + 1
                    
                    # --- UI MODE JSON OUTPUT (FINAL STATE) ---
                    if ui_mode:
                        print("\n---AIPARSER_JSON_START---")
                        # We send back the full ai_data but ensured it has the final state from DB fields if they were updated
                        ui_response = dict(ai_data)
                        ui_response["title"] = c.title
                        ui_response["description"] = c.description
                        ui_response["reward_text"] = c.reward_text
                        ui_response["reward_value"] = float(c.reward_value) if c.reward_value is not None else None
                        ui_response["reward_type"] = c.reward_type
                        ui_response["cards"] = c.eligible_cards.split(", ") if c.eligible_cards else []
                        ui_response["participation"] = c.participation
                        ui_response["conditions"] = c.conditions.split("\n") if c.conditions else []
                        ui_response["sector"] = final_sector_slug
                        ui_response["_clean_text"] = text_to_parse
                        print(json.dumps(ui_response, ensure_ascii=False))
                        print("---AIPARSER_JSON_END---")

                    db.commit()
                with lock:
                    fixed_count_arr[0] += 1
                    
                    if updated:
                        print(f"   ✅ Campaign successfully repaired and saved! (Marked as auto_corrected)")
                    else:
                        print(f"   ⚠️ AI didn't find the missing data. Marked as auto_corrected to prevent loop. No new changes made.")

                # Be gentle to the API limits
                time.sleep(5.0) # Her isci kendine ayrilan 5 saniyeyi bekler
                
                return True

        NUM_WORKERS = 8
        print(f"⚡ Starting {NUM_WORKERS} parallel workers for Autofix...")
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {executor.submit(process_campaign, (item, i)): item for i, item in enumerate(to_fix_ids)}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"   💥 Worker Error: {e}")

        fixed_count = fixed_count_arr[0]
        print(f"\n🏁 Auto-fixer complete. Successfully repaired {fixed_count}/{len(to_fix_ids)} campaigns.")
        
        if not ui_mode:
            audit_approved_campaign_cards()
    except Exception as e:
        print(f"\n📛 CRITICAL ERROR during auto-fix: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def audit_approved_campaign_cards():
    """
    Gece taranan onaylı/aktif kampanyaların kartlarını denetler ve eksik olanları zenginleştirir.
    cards_audited_at alanı None olanları hedefler.
    """
    print("\n------------------------------------------------------------")
    print("🔍 Starting Campaign Cards Audit for APPROVED Campaigns...")
    print("------------------------------------------------------------")
    
    from src.database import SessionLocal
    from src.models import Campaign, Card
    from audit_eligible_cards import extract_cards_via_ai, normalize_card_name
    from sqlalchemy.orm import joinedload
    from datetime import datetime, timezone
    import trafilatura
    import time
    
    db = SessionLocal()
    try:
        # Sorgu: is_active=True, is_approved=True, cards_audited_at=None
        query = db.query(Campaign).options(
            joinedload(Campaign.card).joinedload(Card.bank)
        ).filter(
            Campaign.is_active == True,
            Campaign.is_approved == True,
            Campaign.cards_audited_at == None,
            Campaign.tracking_url != None
        ).order_by(Campaign.id.desc()).limit(250)
        
        campaigns = query.all()
        print(f"📋 Found {len(campaigns)} approved campaigns to audit.")
        
        if not campaigns:
            print("✅ No approved campaigns to audit.")
            return
            
        updated_count = 0
        
        for idx, camp in enumerate(campaigns):
            print(f"\n[{idx+1}/{len(campaigns)}] Auditing Approved ID: {camp.id} - {camp.title[:50]}...")
            
            # Bank adını bul
            bank_name = "Bilinmeyen Banka"
            if camp.card and camp.card.bank:
                bank_name = camp.card.bank.name
                
            url = camp.tracking_url
            if not url or len(url) < 10:
                print("   ⚠️ Invalid tracking URL. Skipping.")
                camp.cards_audited_at = datetime.now(timezone.utc)
                db.commit()
                continue
                
            # 1. Fetch text via our robust fetch_html function (handles SPA, headless Chrome, trafilatura fallbacks)
            clean_text = None
            try:
                fetched_text, status = fetch_html(url)
                if fetched_text and len(fetched_text) >= 100:
                    clean_text = fetched_text
            except Exception as fe:
                print(f"   ⚠️ fetch_html failed: {fe}")
                
            if not clean_text or len(clean_text) < 50:
                # Fallback to campaign description/clean_text if we failed to fetch
                clean_text = camp.clean_text or camp.description or ""
                print("   ⚠️ Could not fetch body text via live fetch. Using description/clean_text fallback.")
                
            if len(clean_text) < 30:
                print("   ⚠️ Text content too short to analyze. Skipping.")
                camp.cards_audited_at = datetime.now(timezone.utc)
                db.commit()
                continue
                
            # 2. Extract cards via AI (uses extract_cards_via_ai from audit_eligible_cards with key rotation)
            ai_cards, card_section = extract_cards_via_ai(clean_text, bank_name)
            
            # 3. Merge logic
            if ai_cards:
                current_cards_str = camp.eligible_cards or ""
                current_cards = [x.strip() for x in current_cards_str.split(",") if x.strip() and x.strip() != "-"]
                normalized_current = {normalize_card_name(x) for x in current_cards if x}
                
                added_cards = []
                for ac in ai_cards:
                    if ac and normalize_card_name(ac) not in normalized_current:
                        current_cards.append(ac)
                        added_cards.append(ac)
                        
                if added_cards:
                    cards_str = ", ".join(current_cards)
                    print(f"   ✨ Added Missing Cards: {added_cards}")
                    print(f"     Old: {camp.eligible_cards}")
                    print(f"     New: {cards_str}")
                    camp.eligible_cards = cards_str
                    updated_count += 1
                else:
                    print("   ✅ Cards match existing database entry.")
            else:
                print("   ℹ️ AI returned empty card list or rate-limited.")
                
            # 4. Mark audited date to avoid scanning again
            camp.cards_audited_at = datetime.now(timezone.utc)
            db.commit()
            
            # API cooldown delay
            time.sleep(1.0)
            
        print(f"\n🏁 Approved Campaigns Audit Complete. Enriched {updated_count} campaigns.")
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=250, help="Max campaigns to fix in one run")
    parser.add_argument("--id", type=int, help="Fix a specific campaign ID")
    parser.add_argument("--ids-file", type=str, help="Fix a list of IDs from a text file")
    parser.add_argument("--force", action="store_true", help="Force AI re-parse even if data exists")
    parser.add_argument("--force-rescue", action="store_true", help="Force fetching fresh HTML from bank site")
    parser.add_argument("--ui-mode", action="store_true", help="Output JSON for UI bridge")
    parser.add_argument("--pending", action="store_true", help="Process only unapproved (pending) campaigns")
    parser.add_argument("--model", type=str, help="Primary AI model to use")
    parser.add_argument("--fallback-model", type=str, help="Fallback AI model to use on failure")
    args = parser.parse_args()
    
    # In UI mode, we don't want sleep and we want a limit of 1
    limit = args.limit
    if args.ui_mode:
        limit = 1
    run_autofix(
        limit=limit, 
        campaign_id=args.id, 
        force_all=args.force, 
        ids_file=args.ids_file, 
        ui_mode=args.ui_mode, 
        pending=args.pending,
        model=args.model,
        fallback_model=args.fallback_model,
        force_rescue=args.force_rescue
    )
