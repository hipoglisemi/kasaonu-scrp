


import os
import sys

# Path setup - reach project root (parent of src)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import uuid  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
import json  # type: ignore # pyre-ignore[21]
import traceback  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Date, Numeric, Text, ForeignKey  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import sessionmaker, relationship, declarative_base  # type: ignore # pyre-ignore[21]
from sqlalchemy.dialects.postgresql import UUID  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore

from src.services.brand_matcher import get_or_create_brands_list  # type: ignore
from src.services.ai_parser import AIParser  # type: ignore

# Load Env (for DB and API Key)
try:
    # Try loading from local kartavantaj .env first (if running from there)
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v.strip('"\'')
except: pass

# Also try loading from scraper project .env
try:
    with open(os.path.join(project_root, '.env'), 'r') as f:
        for line in f:
             if line.strip() and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                # Don't overwrite if already set
                if k not in os.environ:
                     os.environ[k] = v.strip('"\'')
except: pass

# --- CONFIGURATION ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

from src.database import SessionLocal  # type: ignore
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore

# --- SCRAPER ---
class VakifbankScraper:
    BASE_URL = "https://www.vakifkart.com.tr"
    LIST_URL_TEMPLATE = "https://www.vakifkart.com.tr/kampanyalar/sayfa/{}"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        self.db = SessionLocal()
        
        # Initialize AI Parser
        self.parser = AIParser() # Ensure GEMINI_API_KEY is in env
        
        # Ensure Bank
        bank_slug = 'vakifbank'
        self.bank = self.db.query(Bank).filter(Bank.slug == bank_slug).first()  # type: ignore # pyre-ignore[16]
        if not self.bank:
            self.bank = Bank(name='VakıfBank', slug=bank_slug)
            self.db.add(self.bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
            
        # Ensure Card
        card_slug = 'vakifworld'
        # Fallback Name: Since user renamed it VakıfWorld, default to VakıfWorld for new inserts, but search by slug always.
        self.card = self.db.query(Card).filter(Card.slug == card_slug).first()  # type: ignore # pyre-ignore[16]
        if not self.card:
             self.card = Card(bank_id=self.bank.id, name='VakıfWorld', slug=card_slug, is_active=True)  # type: ignore # pyre-ignore[16]
             self.db.add(self.card)  # type: ignore # pyre-ignore[16]
             self.db.commit()  # type: ignore # pyre-ignore[16]
        
        self.card_id = self.card.id  # type: ignore # pyre-ignore[16]

    def _fetch_campaign_list(self, limit_pages=None):
        campaign_urls = []
        page = 1
        while True:
            if limit_pages and page > limit_pages: break
            print(f"📄 Fetching page {page}...")
            url = self.LIST_URL_TEMPLATE.format(page)
            
            # Retry mechanism for network timeouts
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(url, timeout=60)
                    if response.status_code == 404: 
                        break
                    soup = BeautifulSoup(response.text, 'html.parser')
                    items = soup.select("div.mainKampanyalarDesktop:not(.eczk) .list a.item")
                    if not items: 
                        break
                    
                    new_found = False
                    for item in items:
                        href = item.get('href')
                        if href:
                            full_url = urljoin(self.BASE_URL, href)
                            if full_url not in campaign_urls:
                                campaign_urls.append(full_url)
                                new_found = True
                    print(f"   -> Found {len(items)} items.")
                    if not new_found: 
                        break
                        
                    page += 1
                    time.sleep(2)
                    break # Break retry loop on success
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"   ⚠️ Timeout/Error on page {page}, retrying in 5s (Attempt {attempt+1}/{max_retries})... Error: {e}")
                        time.sleep(5)
                    else:
                        print(f"   ❌ Final error fetching page {page} after {max_retries} attempts: {e}")
                        return campaign_urls
                        
            # If we broke out of the outer while loop (404 or no items), we should break completely
            if response.status_code == 404 or not items or not new_found: # type: ignore
                break
                
        return campaign_urls

    def _process_campaign(self, url):
        # Database Pre-check (Skip Logic)
        try:

            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
            if existing and existing.is_active and existing.is_approved:
                print(f"   ⏭️ Skipped (Already exists and active): {existing.title[:40]}")
                return "skipped"  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   ⚠️ DB Pre-check error: {e}")

        print(f"🔍 Processing (Via AI Parser): {url}")
        try:
            # Retry mechanism for campaign details
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(url, timeout=60)
                    html = response.text
                    break # Break retry loop on success
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"   ⚠️ Timeout/Error on details, retrying in 5s (Attempt {attempt+1}/{max_retries})... Error: {e}")
                        time.sleep(5)
                    else:
                        print(f"   ❌ Final error fetching details after {max_retries} attempts: {e}")
                        return "error"
            
            # --- Blocklist check ---
            if is_url_blocked(self.db, url):
                soup_temp = BeautifulSoup(html, 'html.parser')
                title_el = soup_temp.select_one('h1')
                title = title_el.get_text(strip=True) if title_el else url
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

            soup = BeautifulSoup(html, 'html.parser')
            title_el = soup.select_one('h1')

            # Extract og:title for better cleaning anchors
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            # Extract FULL BODY for Autofix-standard global cleaning
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else html
            
            # --- USE CENTRALIZED AI PARSER (Autofix-standard) ---
            from src.services.ai_parser import parse_api_campaign
            ai_data = parse_api_campaign(
                title=title_el.get_text(strip=True) if title_el else "Kampanya",
                short_description=None,
                content_html=raw_html,
                bank_name="VakıfBank",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )
            
            if not ai_data:
                print("   ❌ AI Parsing failed (Returned None). Skipping.")
                return "error"  # type: ignore # pyre-ignore[7]

            title = ai_data.get("title", "Kampanya")
            desc = ai_data.get("description", "")
            
            # Map Sector
            cat_map = {
                "Market & Gıda": "Market",
                "Giyim & Aksesuar": "Giyim",
                "Restoran & Kafe": "Restoran & Kafe",
                "Seyahat": "Seyahat",
                "Turizm & Konaklama": "Seyahat",
                "Elektronik": "Elektronik",
                "Mobilya & Dekorasyon": "Mobilya & Dekorasyon",
                "Kozmetik & Sağlık": "Kozmetik & Sağlık",
                "E-Ticaret": "E-Ticaret",
                "Otomotiv": "Otomotiv",
                "Sigorta": "Sigorta",
                "Diğer": "Diğer"
            }
            ai_cat = ai_data.get("sector", "Diğer")
            db_sector_name = cat_map.get(ai_cat, "Diğer")
            
            sector = self.db.query(Sector).filter(Sector.slug == db_sector_name).first()  # type: ignore # pyre-ignore[16]
            if not sector: sector = self.db.query(Sector).filter(Sector.slug == 'diger').first()  # type: ignore # pyre-ignore[16]
            
            # Generate Unique Slug
            from src.utils.slug_generator import get_unique_slug
            slug = get_unique_slug(
                title=title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=url,
                card_name="Vakıfworld",
                bank_name="Vakıfbank"
            )

            # Prepare Conditions
            conds = ai_data.get("conditions", [])
            if isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
            part_method = ai_data.get("participation")
            
            # Prepend participation if it exists and isn't generic
            if part_method and "Detayları İnceleyin" not in part_method:
                pass  # participation field written separately to DB
            final_conditions = "\n".join(conds)

            cards_raw = ai_data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]

            # Image URL extraction (Still manual as AI Parser doesn't do image extraction yet)
            soup = BeautifulSoup(html, 'html.parser')
            img_el = soup.select_one('.kampanyaDetay .coverSide img')
            image_url = urljoin(self.BASE_URL, img_el['src']) if img_el else None
            
            # Dates
            vf = None
            vu = None
            if ai_data.get("start_date"):
                try: vf = datetime.strptime(ai_data.get("start_date"), "%Y-%m-%d")
                except: pass
            if ai_data.get("end_date"):
                try: vu = datetime.strptime(ai_data.get("end_date"), "%Y-%m-%d")
                except: pass

            campaign = Campaign(
                card_id=self.card_id,
                sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
                slug=slug,
                title=title,
                description=desc,
                ai_marketing_text=ai_data.get("ai_marketing_text"),
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                reward_type=ai_data.get("reward_type"),
                conditions=final_conditions,
                eligible_cards=", ".join(cards_raw),
                participation=part_method,
                image_url=image_url,
                start_date=vf,
                end_date=vu,
                is_active=True,
                tracking_url=url,
                clean_text=ai_data.get("_clean_text"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            # Use centralized upsert_campaign for revival and quality control
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()

            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title[:50]}...")
            
            self.db.refresh(campaign)

            # BRANDS
            # Central parser returns list of strings
            # Brands via brand_matcher
            brand_ids = get_or_create_brands_list(
                db=self.db,
                names=ai_data.get("brands", []),
                brand_cache=getattr(self, 'brand_cache', {}),
                sector_id=sector.id if sector else None
            )
            for bid in brand_ids:
                try:
                    link = self.db.query(CampaignBrand).filter(
                        CampaignBrand.campaign_id == campaign.id,
                        CampaignBrand.brand_id == bid
                    ).first()
                    if not link:
                        self.db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                        self.db.commit()
                except Exception as e:
                    self.db.rollback()
                    print(f"   ⚠️ CampaignBrand link failed: {e}")
            return op_status
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            traceback.print_exc()
            return "error"  # type: ignore # pyre-ignore[7]

    def run(self, limit: int = 1000):
        print("🚀 Starting VakıfBank Scraper (Powered by Kartavantaj AI Parser)...")
        # limit here means limit_pages for simplicity in this scraper's architecture
        urls = self._fetch_campaign_list(limit_pages=max(1, limit // 8))
        
        success_count = 0
        total_revived = 0
        skipped_count = 0
        failed_count = 0
        error_details = []
        
        for i, url in enumerate(urls):
            try:
                res = self._process_campaign(url)
                if res == "saved":
                    success_count += 1  # type: ignore # pyre-ignore[58]
                elif res == "revived":
                    total_revived += 1
                elif res == "skipped":
                    skipped_count += 1  # type: ignore # pyre-ignore[58]
                else:
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": url, "error": f"Process returned {res}"})
            except Exception as e:
                failed_count += 1  # type: ignore # pyre-ignore[58]
                error_details.append({"url": url, "error": str(e)})
                
            time.sleep(2) # Rate limiting
            
        print(f"\n✅ Özet: {len(urls)} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
        
        status = "SUCCESS"
        if failed_count > 0:  # type: ignore # pyre-ignore[58]
             status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
             
        try:
            from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
            log_scraper_execution(
                 db=self.db,
                 scraper_name="vakifbank",
                 status=status,
                 total_found=len(urls),
                 total_saved=success_count,
                 total_skipped=skipped_count,
                 total_failed=failed_count,
                 total_revived=total_revived,
                 error_details={"errors": error_details} if error_details else None
            )
        except Exception as le:
             print(f"⚠️ Could not save scraper log: {le}")
        
        print("🏁 Finished.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    
    scraper = VakifbankScraper()
    scraper.run(limit=args.limit)
