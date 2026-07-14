import sys
import os
import re
import time
import traceback
from typing import Dict, Optional, List, Any
from urllib.parse import urljoin
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
from bs4 import BeautifulSoup
from src.database import get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand
from src.utils.scraper_utils import is_url_blocked, upsert_campaign
from src.services.brand_matcher import get_or_create_brands_list

class VodafonePayScraper:
    BASE_URL = "https://www.vodafonepay.com.tr/kampanyalar"
    SOURCE_NAME = "vodafonepay"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        self.db = get_db_session()
        
        self.sector_cache: Dict[str, Sector] = {}
        self._load_cache()
        
        # Self-bootstrap Bank and Card
        self.bank = self.db.query(Bank).filter(Bank.slug == 'vodafone').first()
        if not self.bank:
            self.bank = Bank(
                name='Vodafone', 
                slug='vodafone', 
                logo_url='https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/Vodafone_2017_logo.svg/1200px-Vodafone_2017_logo.svg.png', 
                is_active=True
            )
            self.db.add(self.bank)
            self.db.commit()
            
        self.card = self.db.query(Card).filter(Card.slug == 'vodafone-pay').first()
        if not self.card:
             self.card = Card(
                  bank_id=self.bank.id, 
                  name='Vodafone Pay', 
                  slug='vodafone-pay', 
                  logo_url='https://cms.vodafone.com.tr/static/vpay/img/content/25-12/22/vpay-logo.svg',
                  is_active=True
             )
             self.db.add(self.card)
             self.db.commit()
        
        self.card_id = self.card.id

    def _fetch_campaign_list(self) -> List[Dict[str, Any]]:
        print(f"📄 Fetching Vodafone Pay campaigns list from {self.BASE_URL}...")
        campaigns = []
        seen = set()
        
        try:
            response = self.session.get(self.BASE_URL, timeout=30)
            if response.status_code != 200:
                print(f"   ⚠️ Listing page returned status code {response.status_code}")
                return campaigns
                
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.select("div.campaign-card")
            print(f"   Found {len(cards)} card elements on page...")
            
            for card in cards:
                link_el = card.select_one("a[href*='kampanyalar/']")
                if not link_el:
                    continue
                    
                href = link_el.get('href')
                if not href:
                    continue
                    
                full_url = urljoin("https://www.vodafonepay.com.tr", href).strip()
                
                # Image
                img_el = card.select_one("img")
                img_url = img_el.get("src") if img_el else None
                if img_url:
                    img_url = urljoin("https://www.vodafonepay.com.tr", img_url).strip()
                    
                # Title
                title_el = card.select_one("h3")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title and img_el:
                    title = img_el.get("alt", "").strip()
                
                if full_url not in seen:
                    seen.add(full_url)
                    campaigns.append({
                        'url': full_url,
                        'img_url': img_url,
                        'title': title
                    })
            print(f"   ✅ Total active campaigns found: {len(campaigns)}")
        except Exception as e:
            print(f"   ⚠️ List fetch failed: {e}")
            
        return campaigns

    def _process_campaign(self, campaign_data):
        url = campaign_data['url'].strip()
        list_img_url = campaign_data.get('img_url')
        list_title = campaign_data.get('title', 'Vodafone Pay Kampanyası')
        
        try:
            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()
            if existing and existing.is_active and existing.is_approved:
                print(f"   ⏭️ Skipped (Already exists and active): {existing.title[:40]}")
                return "skipped"
        except Exception:
            pass

        print(f"🔍 Processing (AI Enabled): {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                print(f"   ⚠️ Page returned status code {response.status_code}. Skipping.")
                return "error"
                
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            # Title: Prefer list card title as it is formatted better
            title = list_title
            h1_el = soup.find('h1')
            detail_title = h1_el.get_text(strip=True) if h1_el else ""
            
            if is_url_blocked(self.db, url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"

            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            # Content container
            body_el = soup.select_one('div.campaign-content') or soup.find("body")
            raw_html = str(body_el) if body_el else str(soup)

            # Dates
            start_date = None
            end_date = None
            date_slide = soup.find(lambda tag: tag.name == "div" and "campaign-info-slide" in tag.get("class", []) and "Kampanya Tarihi" in tag.text)
            if date_slide:
                date_text = date_slide.get_text(" ", strip=True).replace("Kampanya Tarihi", "").strip()
                parts = [p.strip() for p in date_text.split("-") if p.strip()]
                if len(parts) == 2:
                    try:
                        start_date = datetime.strptime(parts[0], "%d.%m.%Y")
                        end_date = datetime.strptime(parts[1], "%d.%m.%Y")
                    except Exception:
                        pass

            # Image: Prioritize list image as requested
            final_image = list_img_url
            if final_image and not any(final_image.lower().split('?')[0].endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg']):
                final_image = None

            if not final_image:
                # Fallback to detail images
                img_el = soup.select_one("img[alt*='Kazan!']") or soup.select_one("img[class*='w-full']") or soup.select_one("img[src*='cms.vodafone']") or soup.find("img")
                if img_el and img_el.get('src'):
                    final_image = img_el.get('src')
            
            if final_image:
                final_image = urljoin("https://www.vodafonepay.com.tr", final_image).strip()

            from src.services.ai_parser_golden import parse_api_campaign
            ai_data = parse_api_campaign(
                title=title,
                short_description=detail_title or title,
                content_html=raw_html,
                bank_name="Vodafone Pay",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )
            
            if not ai_data or ai_data.get("_ai_failed"):
                print("   ❌ AI Parsing failed.")
                return "error"

            title = ai_data.get("title", title)
            desc = ai_data.get("description", "")
            
            sector_slug = ai_data.get("sector")
            sector = self._get_sector(sector_slug)
            
            from src.utils.slug_generator import get_unique_slug
            slug = get_unique_slug(
                title=title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=url,
                card_name="Vodafone Pay",
                bank_name="Vodafone"
            )

            conds = ai_data.get("conditions", [])
            if isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
            part_method = ai_data.get("participation")
            final_conditions = "\n".join(conds)

            cards_raw = ai_data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]

            campaign = Campaign(
                card_id=self.card_id,
                sector_id=sector.id if sector else None,
                slug=slug,
                title=title,
                description=desc,
                ai_marketing_text=ai_data.get("ai_marketing_text"),
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                reward_type=ai_data.get("reward_type"),
                conditions=final_conditions,
                eligible_cards=", ".join(cards_raw) if cards_raw else "Vodafone Pay",
                participation=part_method,
                image_url=final_image,
                start_date=start_date,
                end_date=end_date,
                clean_text=ai_data.get("_clean_text"),
                is_active=True,
                tracking_url=url,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()
            
            if op_status == "revived":
                print(f"   ♻️  Revived: {campaign.title}")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title}")
            
            self.db.refresh(campaign)

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
            return op_status
            
        except Exception as e:
            print(f"   ❌ Error processing {url}: {e}")
            if self.db: self.db.rollback()
            traceback.print_exc()
            return "error"

    def run(self):
        print(f"🚀 Starting {self.SOURCE_NAME} Scraper...")
        campaigns = self._fetch_campaign_list()
        
        max_campaigns = os.environ.get("MAX_CAMPAIGNS_PER_RUN")
        limit = int(max_campaigns) if max_campaigns else 999
        
        count = 0
        success_count = 0
        total_revived = 0
        skipped_count = 0
        failed_count = 0
        error_details = []

        for camp in campaigns:
            if count >= limit:
                print(f"🛑 Reached MAX limit ({limit})")
                break
            
            try:
                res = self._process_campaign(camp)
                if res == "saved": success_count += 1
                elif res == "revived": total_revived += 1
                elif res == "skipped": skipped_count += 1
                else: 
                    failed_count += 1
                    error_details.append({"url": camp.get('url', 'unknown'), "error": f"Process returned {res}"})
            except Exception as e:
                failed_count += 1
                error_details.append({"url": camp.get('url', 'unknown'), "error": str(e)})
            
            count += 1
            time.sleep(1)
            
        print(f"✅ Özet: {len(campaigns)} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
        
        status = "SUCCESS"
        if failed_count > 0:
             status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"
             
        try:
            from src.utils.logger_utils import log_scraper_execution
            log_scraper_execution(
                 db=self.db,
                 scraper_name=self.SOURCE_NAME,
                 status=status,
                 total_found=len(campaigns),
                 total_saved=success_count,
                 total_skipped=skipped_count,
                 total_failed=failed_count,
                 total_revived=total_revived,
                 error_details={"errors": error_details} if error_details else None
            )
        except Exception as le:
             print(f"⚠️ Could not save scraper log: {le}")
             
        print("🏁 Finished.")

    def _load_cache(self):
        for s in self.db.query(Sector).all():
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s

    def _get_sector(self, slug: str) -> Optional[Sector]:
        if not slug:
            return self.sector_cache.get("diger")
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diger")

if __name__ == "__main__":
    try:
        scraper = VodafonePayScraper()
        scraper.run()
    finally:
        if hasattr(scraper, 'db') and scraper.db:
            scraper.db.close()
