import sys
import os
# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
import random  # type: ignore # pyre-ignore[21]
from typing import List, Dict, Optional, Any  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]

from src.models import Campaign, CampaignBrand, Sector, Card, Brand  # type: ignore # pyre-ignore[21]
from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.utils.slug_generator import generate_slug  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import parse_api_campaign  # type: ignore # pyre-ignore[21]
from src.services.brand_normalizer import normalize_brand_name  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import should_skip_campaign  # type: ignore # pyre-ignore[21]
from src.services.brand_matcher import get_or_create_brands_list  # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore # pyre-ignore[21]

# PostgreSQL fix for modern SQLAlchemy
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    os.environ["DATABASE_URL"] = DATABASE_URL

class AkbankBaseScraper:
    """
    Base scraper for Akbank brands (Axess, Free, Wings, Ticari).
    Handles:
    - AJAX list fetching
    - HTML detail parsing
    - AI content extraction
    - Database saving
    """
    
    def __init__(self, 
                 card_name: str, 
                 base_url: str, 
                 list_url: str, 
                 referer_url: str,
                 list_params: Optional[Dict[str, Any]] = None):  # type: ignore # pyre-ignore[16,6]
        self.card_name = card_name
        self.base_url = base_url
        self.list_url = list_url
        self.referer_url = referer_url
        self.list_params = list_params or {'checkBox': '[0]', 'searchWord': '""'}  # type: ignore # pyre-ignore[16,6]
        
        self.session = requests.Session()
        self.session.headers.update({
             'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
             'Accept': 'application/json, text/plain, */*',
             'Referer': self.referer_url
        })
        
        # Helper to find card_id
        with get_db_session() as db:
            from src.models import Card  # type: ignore # pyre-ignore[21]
            card = db.query(Card).filter(Card.name == self.card_name).first()  # type: ignore # pyre-ignore[16]
            if not card:
                raise ValueError(f"Card '{self.card_name}' not found in DB. Please run seed_sectors.py first.")
            self.card = card
            self.card_id = card.id  # type: ignore # pyre-ignore[16]

    def _fetch_campaign_list(self) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        """Iterate through AJAX pages to get all campaign URLs"""
        print(f"📥 Fetching campaign list for {self.card_name}...")
        campaign_urls = []
        page = 1
        
        while True:
            params = dict(self.list_params)
            params['page'] = str(page)
            
            try:
                print(f"   Scanning page {page}...")
                response = self.session.get(self.list_url, params=params, timeout=20)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                links = soup.select('.campaingBox a.dLink')
                
                if not links:
                    print(f"   No links found on page {page}. Stopping.")
                    break
                    
                new_found = False
                for link in links:
                    href = link.get('href')
                    if href:
                        full_url = urljoin(self.base_url, href)
                        if full_url not in campaign_urls:
                            campaign_urls.append(str(full_url))  # type: ignore
                            new_found = True
                            
                if not new_found:
                    print("   No new campaigns found. Stopping.")
                    break
                    
                page = page + 1
                time.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                print(f"❌ Error fetching page {page}: {e}")
                break
                
        print(f"✅ Found {len(campaign_urls)} campaigns for {self.card_name}")
        return campaign_urls  # type: ignore # pyre-ignore[7]

    def _process_campaign(self, url: str, force: bool = False) -> str:
        """Process a single campaign URL"""
        print(f"🔍 Processing: {url}")
        try:
            # Note: Early DB check moved to run() method to handle sub-class overrides automatically.
            
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # --- 1. Raw HTML Extraction ---
            title_elm = soup.select_one('h2.pageTitle')
            title = title_elm.get_text(strip=True) if title_elm else "Kampanya"
            
            # Extract og:title for better cleaning anchors
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            img_elm = soup.select_one('.campaingDetailImage img')
            image_url = None
            if img_elm:
                src = img_elm.get('src')
                if src:
                    image_url = urljoin(self.base_url, src)
            
            # Extract FULL BODY for Autofix-standard global cleaning
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else str(soup)
                
            # --- 2. AI Parsing (Using Global Cache) ---
            ai_data = parse_api_campaign(
                title=title,
                short_description=title, 
                content_html=raw_html,
                bank_name="Akbank",
                scraper_sector=None,
                tracking_url=url,
                force=force,
                og_title=og_title
            )
            
            # --- 3. Save to DB ---
            return self._save_campaign(title, image_url, ai_data, url)  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"❌ Failed to process {url}: {e}")
            return "error"  # type: ignore # pyre-ignore[7]

    def _save_campaign(self, title, image_url, ai_data, source_url) -> str:
        with get_db_session() as db:
            from src.models import Sector  # type: ignore # pyre-ignore[21]
            from src.utils.slug_generator import get_unique_slug  # type: ignore # pyre-ignore[21]
            
            # Use specific title from AI if available, otherwise fallback
            final_title = ai_data.get('short_title') or ai_data.get('title') or title
            
            # Map sector from AI data
            sector_name = ai_data.get('sector', 'Diğer')
            sector = db.query(Sector).filter((Sector.slug == sector_name) | (Sector.name.ilike(sector_name))).first()  # type: ignore # pyre-ignore[16]
            if not sector:
                sector = db.query(Sector).filter(Sector.slug == 'diger').first()  # type: ignore # pyre-ignore[16]

            # Dates
            start_date = None
            if ai_data.get('start_date'):
               try:
                   start_date = datetime.strptime(ai_data['start_date'], '%Y-%m-%d')
               except: pass
               
            if not start_date:
                start_date = datetime.now() # Fallback for active campaigns

            end_date = None
            if ai_data.get('end_date'):
                try:
                    end_date = datetime.strptime(ai_data['end_date'], '%Y-%m-%d')
                except: pass

            # Build conditions text with participation and eligible cards
            conditions_lines = []
            participation = ai_data.get('participation')
            if participation and participation != "Detayları İnceleyin":
                pass  # participation field written separately to DB
                
            eligible_cards_list = ai_data.get('cards', [])
            if ai_data.get('conditions'):
                conditions_lines.extend(ai_data.get('conditions'))
            
            conditions_text = "\n".join(conditions_lines)
            eligible_cards_str = ", ".join(eligible_cards_list) if eligible_cards_list else None
            
            # Check for existing campaign to handle revival
            existing = db.query(Campaign).filter(Campaign.tracking_url == source_url, Campaign.card_id == self.card_id).first()
            
            campaign = Campaign(  # type: ignore
                card_id=self.card_id,  # type: ignore
                sector_id=sector.id if sector else None,  # type: ignore
                slug=get_unique_slug(
                    title=final_title,
                    db_session=db,
                    campaign_model=Campaign,
                    tracking_url=source_url,
                    card_name=self.card_name,
                    bank_name="Akbank"
                ),  # type: ignore
                title=final_title,  # type: ignore
                description=ai_data.get('description') or title,  # type: ignore
                ai_marketing_text=ai_data.get('ai_marketing_text'),  # type: ignore
                reward_text=ai_data.get('reward_text'),  # type: ignore
                reward_value=ai_data.get('reward_value'),  # type: ignore
                reward_type=ai_data.get('reward_type'),  # type: ignore
                conditions=conditions_text,  # type: ignore
                eligible_cards=eligible_cards_str,
                participation=participation,  # type: ignore
                image_url=image_url,  # type: ignore
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
                is_active=True,  # type: ignore
                created_at=datetime.utcnow(),  # type: ignore
                updated_at=datetime.utcnow(),  # type: ignore
                tracking_url=source_url,  # type: ignore
                clean_text=ai_data.get('_clean_text') or ai_data.get('clean_text')
            )

            from src.utils.scraper_utils import upsert_campaign
            campaign, op_status = upsert_campaign(db, campaign)
            db.commit()
            
            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title}")
            elif op_status == "saved":
                print(f"   ✅ Saved New: {campaign.title}")
            
            db.refresh(campaign)

            db.commit()  # type: ignore # pyre-ignore[16]


            
            # Brands via brand_matcher
            brand_ids = get_or_create_brands_list(
                db=db,
                names=ai_data.get("brands", []),
                brand_cache=getattr(self, 'brand_cache', {}),
                sector_id=sector.id if sector else None
            )
            for bid in brand_ids:
                try:
                    link = db.query(CampaignBrand).filter(
                        CampaignBrand.campaign_id == campaign.id,
                        CampaignBrand.brand_id == bid
                    ).first()
                    if not link:
                        db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                        db.commit()
                except Exception as e:
                    db.rollback()
                    print(f"   ⚠️ CampaignBrand link failed: {e}")
            return op_status

    def run(self, limit: Optional[int] = None, urls: Optional[List[str]] = None, force: bool = False):  # type: ignore # pyre-ignore[16,6]
        print(f"🚀 Starting {self.card_name} Scraper...")
        from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
        
        process_urls: List[str] = []  # type: ignore # pyre-ignore[16,6]
        if urls:
            process_urls = urls
        else:
            process_urls = self._fetch_campaign_list()
            if limit and isinstance(process_urls, list):
                process_urls = process_urls[:limit]  # type: ignore # pyre-ignore[16,6]
        
        total_found = len(process_urls)
        total_saved = 0
        total_revived = 0
        total_skipped = 0
        total_failed = 0
        error_details = []

        for i, url in enumerate(process_urls):
            print(f"[{i+1}/{len(process_urls)}]", end=" ")
            try:
                # --- Early DB Check (Moved here to handle sub-class overrides) ---
                if not force:
                    with get_db_session() as db:
                        from src.utils.scraper_utils import is_url_blocked
                        
                        if is_url_blocked(db, url):
                            print(f"⏭️  Skipped (Blocked): {url}")
                            total_skipped += 1
                            continue
                        
                        # Extract the slug from the URL to handle URL structure migrations (kampanyadetay -> kampanyalar)
                        url_slug = url.strip('/').split('/')[-1]
                        
                        existing = db.query(Campaign).filter(
                            Campaign.card_id == self.card_id,
                            Campaign.tracking_url.like(f"%/{url_slug}%")
                        ).first()
                        
                        if existing and existing.is_active:
                            # 🔄 MIGRATION FIX: If the URL prefix changed, update it in the DB silently!
                            if existing.tracking_url != url:
                                existing.tracking_url = url
                                db.commit()
                                
                            print(f"⏭️  Skipped (Already exists & active under card {existing.card_id}): {existing.title}")
                            total_skipped += 1
                            continue
                            
                # Process (Sub-classes may override this)
                # If we found an existing but passive campaign, force a re-parse to get fresh data
                current_force = force
                with get_db_session() as db:
                    url_slug = url.strip('/').split('/')[-1]
                    existing = db.query(Campaign).filter(
                        Campaign.card_id == self.card_id,
                        Campaign.tracking_url.like(f"%/{url_slug}%")
                    ).first()
                    # ♻️ Force re-parse if campaign is passive
                    if existing and not existing.is_active:
                        current_force = True
                
                res = self._process_campaign(url, force=current_force)
                
                # Sub-classes might return None but be successful if they didn't throw
                if res in ["saved", "updated"] or res is None:
                    total_saved += 1  # type: ignore # pyre-ignore[58]
                elif res == "revived":
                    total_revived += 1
                elif res == "skipped":
                    total_skipped += 1  # type: ignore # pyre-ignore[58]
                else:
                    total_failed += 1  # type: ignore # pyre-ignore[58]
            except Exception as e:
                print(f"❌ Error in loop: {e}")
                total_failed += 1  # type: ignore # pyre-ignore[58]
                error_details.append({"url": url, "error": str(e)})
            time.sleep(1) # Polite delay
            
        print(f"🏁 Scraping finished. Found: {total_found}, Saved: {total_saved}, Skipped: {total_skipped}, Failed: {total_failed}")
        
        # Determine status
        status = "SUCCESS"
        if total_failed > 0:  # type: ignore # pyre-ignore[58]
            status = "PARTIAL" if (total_saved > 0 or total_skipped > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
            
        # Log to database
        with get_db_session() as db:
            scraper_id = f"akbank_{self.card_name.lower()}"
            log_scraper_execution(
                db=db,
                scraper_name=scraper_id,
                status=status,
                total_found=total_found,
                total_saved=total_saved,
                total_skipped=total_skipped,
                total_failed=total_failed,
                total_revived=total_revived,
                error_details={"errors": error_details} if error_details else None
            )
