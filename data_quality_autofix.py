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

# Suppress noisy INFO logs from underlying AI libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)

from src.models import Campaign, Sector, Brand, CampaignBrand, Card, Bank # type: ignore
from src.database import get_db_session # type: ignore
from src.services.ai_parser_golden import AIParserGolden # type: ignore
from src.services.text_cleaner import clean_campaign_text # type: ignore
from src.services.point_blank_matcher import get_point_blank_matcher, _GLOBAL_BRAND_EXCLUSIONS # type: ignore
from sqlalchemy.orm import joinedload # type: ignore
from src.utils.gemini_client import generate_with_rotation # type: ignore
from google.genai import types # type: ignore

# Golden Parser AI Client Wrapper
class _AutofixGeminiClient:
    """Wraps generate_with_rotation for AIParserGolden compatibility."""
    def __init__(self, model=None, fallback_model=None):
        self.model = model or os.getenv("GEMINI_MODEL", "models/gemini-3.1-flash-lite-preview")
        self.fallback_model = fallback_model or os.getenv("FALLBACK_MODEL")
        
    def generate_content(self, prompt):
        config = types.GenerateContentConfig(
            temperature=0.0, top_p=0.1, top_k=1,
            response_mime_type="application/json",
            max_output_tokens=6000
        )
        result = generate_with_rotation(
            prompt=prompt, 
            model=self.model, 
            fallback_model=self.fallback_model,
            config=config
        )
        return str(result) if result else "{}"

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
    spa_domains = ["opet.com.tr", "naysapp.com.tr", "chippin.com", "axess.com.tr", "kartfree.com", "wingscard.com.tr", "bonus.com.tr", "denizbonus.com"]
    is_spa = any(domain in url for domain in spa_domains)

    if is_spa:
        print(f"   🚀 SPA/Tabbed Site Detected ({url}). Booting Headless Chrome...")
        import time
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--headless=new')
        
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
        
        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(30)
            driver.get(url)
            time.sleep(4) # Initial wait
            # Scroll to bottom to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            # Scroll slightly up as some lazy loaders need movement
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 500);")
            time.sleep(2)
            raw_html = driver.page_source

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
            return ""

    if not is_trafilatura_text:
        soup = BeautifulSoup(raw_html, 'html.parser')

        # 🛡️ NOISE REMOVAL (Global)
        for script in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            script.extract()
            
        # 🛡️ NOISE REMOVAL (Specific)
        noise_selectors = [
            '.other-campaigns', '.featured-campaigns', '.similar-campaigns', 
            '.campaign-recommendations', 'section.news-carousel', 
            '#related-campaigns', '.campaignDetail-others'
        ]
        for selector in noise_selectors:
            for element in soup.select(selector):
                element.extract()
        
        # 🎯 CONTENT TARGETING
        target_selectors = [
            '.sub-header', '.campaign-terms', '.campaign-detail-content', '.campaign-detail', 
            '.campaign-detail-tab-details', '.campaign-detail-box', 
            'article.campaign-detail', '.cmsContent',
            '.campaingDetail', '.campaing', '.textArea', '.campaingDetail-content',
            '.how-to-win-content', '.tab-content', '.campaign-detail-content', '.campaign-detail-text',
            '.campaign-detail-capsule', '.container-right', '.campaign-dates'
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
    print(f"🔍 DEBUG PROCESSED TEXT (Full): {text}")
    return text

def run_autofix(limit: int = 250, campaign_id: Optional[int] = None, force_all: bool = False, ids_file: Optional[str] = None, ui_mode: bool = False, pending: bool = False, model: Optional[str] = None, fallback_model: Optional[str] = None):
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
            elif pending:
                print("🔍 Focusing on PENDING (unapproved) campaigns...")
                query = query.filter(Campaign.is_approved == False)
            else:
                query = query.filter(Campaign.is_active == True)
            
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
                    "Kampanyaya katılmak için Mobil Şube üzerinden Kampanyaya Katıl butonuna tıklamanız yeterlidir."
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
                is_participation_bad = not c.participation or c.participation.strip() == "" or any(p in (c.participation or "") for p in useless_participations) or "Detayları İnceleyin" in (c.participation or "")
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
                    card_keywords = ["platinum", "gold", "business", "ticari", "troy", "amex", "business", "kurumsal", "sirket", "şahıs", "miles", "wings", "chip-para"]
                    found_cards = [k for k in card_keywords if k in clean_lower]
                    current_cards_lower = (c.eligible_cards or "").lower()
                    
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

                # FORCE REPAIR IF SPECIFIC ID IS PROVIDED OR IDS_FILE MODE IS ACTIVE (Bypass defect check)
                if (campaign_id or ids_file) and not is_defective:
                    is_defective = True
                    reasons.append(f"Manual Force Repair (List Mode)")

                if is_defective and c.tracking_url:
                    # COOLDOWN & PERMANENT SKIP LOGIC
                    # REPAIR COUNT & FORCE UPGRADE LOGIC
                    if c.repair_count >= 2 and not FORCE_ALL and not campaign_id:
                        stats["skipped_cooldown"] += 1
                        continue
                    
                    if c.auto_corrected or c.repair_count > 0:
                        # If already corrected once, ONLY retry if:
                        # 1. Severe text corruption
                        # 2. OR it STILL has an Invalid Bank Brand (New rules need to clean this up)
                        # 3. OR it has Incomplete Metadata (Cards/Participation missed by AI)
                        # 4. OR FORCE_ALL is active
                        has_bank_error = any("Invalid Bank Brand" in r for r in reasons)
                        has_metadata_error = any("Incomplete Cards" in r or "Incomplete Participation" in r for r in reasons)
                        
                        if not (is_corrupted or has_mojibake or has_bank_error or has_metadata_error) and not FORCE_ALL:
                            stats["skipped_cooldown"] += 1
                            continue
                            
                        # Cooldown check for retries
                        last_update = c.updated_at or c.created_at
                        if now - last_update < cooldown_period and not FORCE_ALL:
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
                print("✅ All active campaigns look healthy! Exiting.")
                return
                
        fixed_count = 0
            
        for c_id, tracking_url, reasons_list in to_fix_ids:
            summary_reasons = ", ".join(reasons_list)
            
            with get_db_session() as db:
                c = db.query(Campaign).options(
                    joinedload(Campaign.card).joinedload(Card.bank),
                    joinedload(Campaign.sector),
                    joinedload(Campaign.brands)
                ).filter(Campaign.id == c_id).first()
                if not c:
                    print(f"\n🛠️ Skipping: [{c_id}] (Campaign no longer in DB)")
                    continue
                    
                print(f"\n🛠️ Fixing: [{c.id}] {c.title[:40]}... (Reasons: {summary_reasons})")
                print(f"   🔗 URL: {c.tracking_url}")
                
                # Determine if we need a fresh fetch (Rescue)
                is_truncated = any("Short/Truncated Source Text" in r for r in reasons_list)
                text_to_parse = ""
                
                # Force rescue if campaign_id is specifically requested (UI Repair Button)
                force_rescue = True if campaign_id else FORCE_ALL
                
                if c.clean_text and len(c.clean_text) >= 600 and not is_truncated and not mojibake_pattern.search(c.clean_text) and not force_rescue:
                    print(f"   ⚡ Using pre-cleaned text from DB ({len(c.clean_text)} chars)")
                    text_to_parse = c.clean_text
                else:
                    # Fresh fetch required
                    print(f"   🌐 Logic: RESCUE! (Force mode or text issue). Fetching fresh HTML...")
                    
                    # Step 1: Fetch raw HTML to extract H1 title (before text cleaning strips HTML tags)
                    og_title = None
                    try:
                        import urllib3
                        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
                        }
                        _raw_resp = requests.get(c.tracking_url, headers=headers, timeout=15, verify=False)
                        _raw_resp.raise_for_status()
                        _raw_html = _raw_resp.text
                        from bs4 import BeautifulSoup as _BS
                        _raw_soup = _BS(_raw_html, "html.parser")
                        # Priority 1: H1 (most reliable on bank campaign pages like Yapı Kredi)
                        _h1 = _raw_soup.select_one('h1')
                        if _h1 and _h1.get_text(strip=True):
                            og_title = _h1.get_text(strip=True)
                            print(f"   🏷️ H1 title: {og_title}")
                        else:
                            # Priority 2: og:title (fallback for sites without H1)
                            _og = _raw_soup.find("meta", property="og:title")
                            if _og and _og.get("content"):
                                _og_content = _og["content"].strip()
                                # Only use og:title if it's specific (>2 words), not a generic site name
                                if len(_og_content.split()) > 2:
                                    og_title = _og_content
                                    print(f"   🏷️ og:title: {og_title}")
                    except Exception as _e:
                        print(f"   ⚠️ Raw HTML fetch for title failed: {_e}")
                    
                    # Step 2: Clean text via full pipeline (fetch_html does BeautifulSoup + text_cleaner)
                    html_text = fetch_html(c.tracking_url)
                    
                    if html_text and len(html_text) >= 50:
                        # Run text_cleaner again with the H1 title so the Header Sniper can cut menu noise correctly
                        text_to_parse = clean_campaign_text(html_text, og_title=og_title)
                        print(f"   ✅ URL fetch successful ({len(text_to_parse)} chars)")
                    else:
                        # SECOND FALLBACK: Use description and conditions if URL fetching fails (likely bot protection or dead link)
                        print(f"   ⚠️ URL fetch failed (possible bot-block or 404).")
                        
                        fallback_segments = []
                        if c.description: fallback_segments.append(c.description)
                        if c.conditions: fallback_segments.append(c.conditions)
                        
                        fallback_text = " ".join(fallback_segments)
                        if len(fallback_text) > 20: 
                            print(f"   🔄 Using secondary fallback: Existing Description/Conditions ({len(fallback_text)} chars)")
                            text_to_parse = fallback_text
                        else:
                            print(f"   ❌ Could not extract meaningful text from URL or DB fields. Skipping.")
                            continue

                # Determine bank name for AI parser (needed for Point-Blank & bank-specific rules)
                bank_name = None
                if c.card and c.card.bank:
                    bank_name = c.card.bank.name
                
                # ── HASH / CONTENT MATCHING (Adım 5) ──
                # If running automatically (no human 'Tamir Et' button clicked: not campaign_id and not FORCE_ALL)
                # and the text hasn't changed from what we already stored, DO NOT hit Gemini again. 
                # It will give the same defective result. Save API costs!
                if not FORCE_ALL and not campaign_id:
                    if c.clean_text and text_to_parse == c.clean_text:
                        print(f"   ⏸️ Banka metni değişmemiş. Boşuna AI çağrısı yapılmıyor (Hash Match). Atlandı.")
                        continue

                # Eğer DB'den gelen başlık çok uzunsa (Açıklama metni yanlışlıkla başlık olmuşsa), 
                # AI bu metne BAŞLIK KİLİDİ atmasın diye boş gönderiyoruz. AI metnin en üstündeki H1'i bularak kendisi atayacak.
                ai_title_pass = c.title or ''
                if len(ai_title_pass.split()) > 15:
                    print(f"   🔓 DB Title is too long ({len(ai_title_pass.split())} words) - Erasing lock to let AI find the real title from HTML.")
                    ai_title_pass = ''

                print(f"   🤖 [GOLDEN V3] Sending {len(text_to_parse)} characters to AI... (Bank: {bank_name or 'Unknown'})")
                parser = _get_golden_parser(model=model, fallback_model=fallback_model)

                ai_data = parser.parse_campaign(
                    raw_html=text_to_parse,
                    bank_name=bank_name or '',
                    title=ai_title_pass,
                    og_title=og_title if 'og_title' in dir() else None
                )
                
                if not ai_data:
                    print(f"   ❌ Gemini AI failed to return data. Skipping.")
                    continue

                # 🛡️ REJECT FAILED AI RESPONSES
                if ai_data.get("_ai_failed"):
                    print(f"   ❌ AI returned fallback/failed data (_ai_failed=True). Skipping.")
                    continue
                
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
                if not c.title or is_title_generic or FORCE_ALL:
                    if ai_data.get("title") and ai_data["title"] != c.title:
                        print(f"   ✨ Repaired Title: {c.title} -> {ai_data['title']}")
                        c.title = ai_data["title"]
                        updated = True

                # Update Description
                if not c.description or len(c.description.strip()) < 15 or FORCE_ALL:
                    if ai_data.get("description"):
                        print(f"   ✨ Repaired Description!")
                        c.description = ai_data["description"]
                        updated = True
                        
                # Update Reward Text
                is_reward_bad = not c.reward_text or c.reward_text.strip() == "" or "Detayları İnceleyin" in c.reward_text
                if is_reward_bad or FORCE_ALL:
                    if ai_data.get("reward_text"):
                        print(f"   ✨ Repaired Reward Text: {ai_data['reward_text']}")
                        c.reward_text = ai_data["reward_text"]
                        updated = True
                        
                if c.reward_value is None or FORCE_ALL:
                    if ai_data.get("reward_value") is not None:
                        print(f"   ✨ Repaired Reward Value: {ai_data['reward_value']}")
                        c.reward_value = ai_data["reward_value"]
                        updated = True
                        
                if not c.reward_type or c.reward_type.strip() == "" or FORCE_ALL:
                    if ai_data.get("reward_type"):
                        print(f"   ✨ Repaired Reward Type: {ai_data['reward_type']}")
                        c.reward_type = ai_data["reward_type"]
                        updated = True
                        
                # Update Eligible Cards if missing, corrupted, generic, OR incomplete
                is_cards_empty = not c.eligible_cards or c.eligible_cards.strip() == ""
                is_cards_corrupted = "Kampanyaya Dahil Kartlar" in (c.eligible_cards or "") or corrupted_regex.search(c.eligible_cards or "")
                is_cards_incomplete = any("Incomplete Cards" in r for r in reasons_list)
                
                if is_cards_empty or is_cards_corrupted or is_cards_incomplete or FORCE_ALL:
                    if ai_data.get("cards") is not None:
                        cards_str = ", ".join(ai_data["cards"]) if len(ai_data["cards"]) > 0 else "-"
                        if is_cards_incomplete:
                            print(f"   ✨ Upgraded Incomplete Cards: {c.eligible_cards} → {cards_str}")
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
                if not c.start_date or FORCE_ALL:
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
                if not c.end_date or FORCE_ALL:
                    new_end = None
                    if ai_data.get("end_date"):
                        try:
                            new_end = datetime.strptime(ai_data["end_date"], "%Y-%m-%d").date()
                        except: pass
                    
                    # Fallback if AI didn't find it
                    if not new_end:
                        # Baseline as end of the month of (start_date or created_at)
                        reference = c.start_date or baseline_date
                        new_end = get_last_day_of_month(reference)
                        print(f"   🔄 Falling back End Date to End of Month: {new_end}")

                    if new_end:
                        c.end_date = new_end
                        updated = True
                        print(f"   ✨ Repaired End Date: {c.end_date}")
                        
                # Update Conditions if missing, corrupted or FORCE_ALL
                if not c.conditions or c.conditions.strip() == "" or corrupted_regex.search(c.conditions) or FORCE_ALL:
                    if ai_data.get("conditions"):
                        print(f"   ✨ Repaired Conditions!")
                        c.conditions = "\n".join(cond for cond in ai_data.get("conditions", []))
                        updated = True


                # Clean and update Participation
                is_curr_p_bad = not c.participation or c.participation.strip() == "" or any(p in (c.participation or "") for p in useless_participations) or corrupted_regex.search(c.participation)
                if is_curr_p_bad or FORCE_ALL:
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
                        c.sector_id = sector.id
                        print(f"   ✨ Repaired Sector: {old_name} → {sector.name}")
                        updated = True

                # --- Marka tamiri (Safe-Update & Multi-Brand) ---
                needs_brand_fix = False
                if not c.brands or (campaign_id or ids_file):
                    needs_brand_fix = True
                elif reasons_list:
                    for r in reasons_list:
                        if "Invalid Bank Brand" in r:
                            needs_brand_fix = True
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
                    
                    # If we are in force/id-file mode, we PURGE all old brands to ensure clean slate
                    # Otherwise, we only purge the ones identified as bank brands
                    correct_brands_to_keep = []
                    if not (campaign_id or ids_file):
                        for b in c.brands:
                            if b.name not in wrong_bank_brands:
                                correct_brands_to_keep.append(b)
                    
                    # Kampanya bağlarını sıfırla
                    db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).delete()
                    db.flush()
                    
                    added_brand_ids = set()
                    
                    if correct_brands_to_keep:
                        for b in correct_brands_to_keep:
                            db.add(CampaignBrand(campaign_id=c.id, brand_id=b.id))
                            added_brand_ids.add(b.id)
                        print(f"   🛡️ Preserved Brands: {', '.join([b.name for b in correct_brands_to_keep])}")
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
                    ui_response["reward_value"] = c.reward_value
                    ui_response["reward_type"] = c.reward_type
                    ui_response["cards"] = c.eligible_cards.split(", ") if c.eligible_cards else []
                    ui_response["participation"] = c.participation
                    ui_response["conditions"] = c.conditions.split("\n") if c.conditions else []
                    ui_response["sector"] = final_sector_slug
                    ui_response["_clean_text"] = text_to_parse
                    print(json.dumps(ui_response, ensure_ascii=False))
                    print("---AIPARSER_JSON_END---")

                db.commit()
                fixed_count += 1
                
                if updated:
                    print(f"   ✅ Campaign successfully repaired and saved! (Marked as auto_corrected)")
                else:
                    print(f"   ⚠️ AI didn't find the missing data. Marked as auto_corrected to prevent loop. No new changes made.")

            # Be gentle to the API limits
            time.sleep(3)
            
        print(f"\n🏁 Auto-fixer complete. Successfully repaired {fixed_count}/{len(to_fix_ids)} campaigns.")
    except Exception as e:
        print(f"\n📛 CRITICAL ERROR during auto-fix: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=250, help="Max campaigns to fix in one run")
    parser.add_argument("--id", type=int, help="Fix a specific campaign ID")
    parser.add_argument("--ids-file", type=str, help="Fix a list of IDs from a text file")
    parser.add_argument("--force", action="store_true", help="Force AI re-parse even if data exists")
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
        fallback_model=args.fallback_model
    )
