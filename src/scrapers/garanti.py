import sys
import os
import time
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from sqlalchemy.orm import Session
from playwright.sync_api import sync_playwright

# Dynamic path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand
from src.services.ai_parser import parse_api_campaign
from src.utils.slug_generator import get_unique_slug
from src.utils.cache_manager import clear_cache
from src.utils.scraper_utils import is_url_blocked, upsert_campaign

class GarantiScraper:
    """Scraper for Garanti BBVA General campaigns using Playwright Firefox + Gemini AI.
    
    Loads active campaigns by clicking the 'Daha Fazla Gör' button and extracts details,
    filtering out campaigns that overlap with Garanti Bonus, Miles&Smiles, or Shop&Fly.
    """
    
    BASE_URL = 'https://www.garantibbva.com.tr'
    CAMPAIGN_LIST_URL = 'https://www.garantibbva.com.tr/kampanyalar'
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.8,en-US;q=0.5,en;q=0.3',
    }
    
    def __init__(self, limit: Optional[int] = None):
        self.limit = limit
        self.bank = None
        self.card = None
        self.playwright = None
        self.browser = None
        self.page = None
        
        # Initialize bank and card in DB
        with get_db_session() as db:
            # 1. Bank: Garanti BBVA
            bank = db.query(Bank).filter(Bank.slug == "garanti-bbva").first()
            if not bank:
                bank = Bank(name="Garanti BBVA", slug="garanti-bbva", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
                print(f"✅ Created Bank: Garanti BBVA")
            self.bank_id = bank.id
            
            # 2. Card: Garanti BBVA (General card for loans, new customer promos, etc.)
            card = db.query(Card).filter(
                Card.bank_id == self.bank_id,
                Card.slug == "garanti-bbva"
            ).first()
            if not card:
                card = Card(
                    bank_id=self.bank_id,
                    name="Garanti BBVA",
                    slug="garanti-bbva",
                    is_active=True
                )
                db.add(card)
                db.commit()
                db.refresh(card)
                print(f"✅ Created Card: Garanti BBVA")
            self.card_id = card.id



    def _init_browser(self):
        """Initialize playwright browser with retry mechanism"""
        for attempt in range(1, 4):
            try:
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.firefox.launch(
                    headless=True
                )
                self.page = self.browser.new_page()
                return
            except Exception as e:
                print(f"⚠️ Playwright initialization attempt {attempt} failed: {e}")
                if self.browser:
                    try: self.browser.close()
                    except: pass
                if self.playwright:
                    try: self.playwright.stop()
                    except: pass
                if attempt == 3:
                    raise e
                time.sleep(2)

    def _close_browser(self):
        """Safely close playwright browser"""
        if self.browser:
            try: self.browser.close()
            except: pass
        if self.playwright:
            try: self.playwright.stop()
            except: pass

    def _fetch_campaign_list(self) -> List[str]:
        """Fetch all active campaign URLs from the website by expanding the listing"""
        print(f"📥 Fetching campaign list from {self.CAMPAIGN_LIST_URL}...")
        
        self._init_browser()
        
        try:
            # Navigate to page with retry
            for attempt in range(1, 4):
                try:
                    self.page.goto(
                        self.CAMPAIGN_LIST_URL,
                        wait_until="domcontentloaded",
                        timeout=90000
                    )
                    break
                except Exception as e:
                    print(f"⚠️ Page load attempt {attempt} failed: {e}")
                    if attempt == 3:
                        raise e
                    time.sleep(3)

            # Wait for content to settle
            time.sleep(5)

            # Accept cookies if the overlay exists
            try:
                cookie_btn = self.page.query_selector("text=Kabul Et")
                if cookie_btn and cookie_btn.is_visible():
                    cookie_btn.click()
                    time.sleep(1)
            except:
                pass

            # Extract links function helper
            def extract_links(html_content):
                s = BeautifulSoup(html_content, 'html.parser')
                container = s.select_one(".js-campaignlisting--current")
                links = []
                if container:
                    cards = container.find_all('div', class_='card')
                    for card in cards:
                        a_tag = card.find('a', href=True)
                        if a_tag:
                            href = a_tag['href']
                            full_url = urljoin(self.BASE_URL, href)
                            if '/kampanyalar/' in full_url and len(full_url.split('/')) > 4:
                                if full_url not in links:
                                    links.append(full_url)
                return links

            # Click pagination button for active campaigns container (.js-campaignlisting--current)
            click_count = 0
            prev_card_count = 0
            
            # Get initial card count and links
            initial_content = self.page.content()
            soup = BeautifulSoup(initial_content, 'html.parser')
            active_container = soup.select_one(".js-campaignlisting--current")
            if active_container:
                prev_card_count = len(active_container.find_all('div', class_='card'))
            print(f"   📊 Initial active card count: {prev_card_count}")
            campaign_links = extract_links(initial_content)

            while click_count < 30:
                btn = self.page.query_selector(".js-campaignlisting--current button.js-show-more")
                if btn and btn.is_visible():
                    self.page.evaluate("element => element.click()", btn)
                    click_count += 1
                    print(f"   ⏬ Clicked active load button {click_count} times...")
                    time.sleep(2.5)  # Wait for AJAX append
                    
                    # Get new card count
                    current_content = self.page.content()
                    soup = BeautifulSoup(current_content, 'html.parser')
                    active_container = soup.select_one(".js-campaignlisting--current")
                    new_card_count = 0
                    if active_container:
                        new_card_count = len(active_container.find_all('div', class_='card'))
                    print(f"   📊 Active card count after click {click_count}: {new_card_count}")
                    
                    if new_card_count <= prev_card_count:
                        print("   ⏹️ Card count did not increase (or reset). Stopping pagination.")
                        break
                    
                    # Update active links and prev_card_count since it grew
                    campaign_links = extract_links(current_content)
                    prev_card_count = new_card_count
                else:
                    break

            print(f"✅ Found {len(campaign_links)} active general campaigns on page.")
            return campaign_links

        except Exception as e:
            print(f"❌ Error fetching campaign list: {e}")
            return []
        finally:
            self._close_browser()

    def _parse_turkish_date(self, date_str: str) -> Optional[datetime]:
        """Parse Turkish date string (e.g. '1 - 28 Şubat 2026' or '1 Ocak 2026 - 15 Mart 2026')"""
        if not date_str:
            return None
            
        months = {
            'ocak': 1, 'şubat': 2, 'mart': 3, 'nisan': 4,
            'mayıs': 5, 'haziran': 6, 'temmuz': 7, 'ağustos': 8,
            'eylül': 9, 'ekim': 10, 'kasım': 11, 'aralık': 12
        }
        
        try:
            date_str = date_str.lower().strip()
            parts = [p.strip() for p in date_str.split('-')]
            
            if len(parts) >= 2:
                # Range date: "1 Ocak 2026 - 15 Şubat 2026" or "1 - 28 Şubat 2026"
                end_part = parts[1]
                # Try parsing end date first
                end_date = self._parse_single_turkish_date(end_part, months)
                
                start_part = parts[0]
                if start_part.isdigit() and end_date:
                    # Specific handling for "1 - 28 Şubat 2026" where start is just a day
                    try:
                        start_date = datetime(end_date.year, end_date.month, int(start_part))
                        return start_date, end_date
                    except:
                        pass
                
                start_date = self._parse_single_turkish_date(start_part, months)
                return start_date, end_date
            else:
                # Single date
                single_date = self._parse_single_turkish_date(parts[0], months)
                return single_date, None
        except Exception as e:
            print(f"      ⚠️ Date parse failed '{date_str}': {e}")
            return None

    def _parse_single_turkish_date(self, date_str: str, months: Dict[str, int]) -> Optional[datetime]:
        try:
            tokens = date_str.split()
            day = int(re.sub(r'\D', '', tokens[0]))
            
            # Find month name token
            month_name = None
            for token in tokens:
                if token in months:
                    month_name = token
                    break
            
            if not month_name:
                return None
                
            month = months[month_name]
            
            # Find year (4-digit number)
            year = datetime.now().year
            for token in tokens:
                if token.isdigit() and len(token) == 4:
                    year = int(token)
                    break
                    
            return datetime(year, month, day)
        except:
            return None

    def _process_campaign(self, url: str) -> str:
        """Process a single campaign page details"""
        # Pre-check database
        try:
            with get_db_session() as db:
                if is_url_blocked(db, url):
                    print(f"   🚫 Skipped (Blocklisted): {url}")
                    return "skipped"

                existing = db.query(Campaign).filter(Campaign.tracking_url == url).first()
                if existing and existing.is_active and existing.is_approved:
                    print(f"   ⏭️ Skipped (Already exists and active): {url}")
                    return "skipped"
        except Exception as e:
            print(f"   ⚠️ DB Pre-check error: {e}")

        # Fetch and Parse page detail via Playwright Firefox (same as list fetcher)
        self._init_browser()
        soup = None
        try:
            for attempt in range(1, 4):
                try:
                    self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    break
                except Exception as e:
                    print(f"⚠️ Page detail load attempt {attempt} failed: {e}")
                    if attempt == 3:
                        raise e
                    time.sleep(3)

            self.page.wait_for_timeout(2000)
            soup = BeautifulSoup(self.page.content(), 'html.parser')
        except Exception as e:
            print(f"   ❌ Error loading campaign page {url}: {e}")
            return f"error: {str(e)}"
        finally:
            self._close_browser()

        if not soup:
            return "error: empty content"

        try:
            # Title
            title_elm = soup.select_one(".campaign-detail-title h1, .campaign-detail__title h1, .campaign-detail h1, h1")
            title = title_elm.get_text().strip() if title_elm else "Başlık Bulunamadı"
            
            # Image
            img_elm = soup.select_one("img.campaign__img, .campaign__imgwrapper img, .campaign-detail__image img, .campaign-detail img, img.campaign-image")
            image_url = None
            if img_elm:
                image_url = img_elm.get('data-src') or img_elm.get('src')
                if image_url:
                    image_url = urljoin(self.BASE_URL, image_url)
            
            # Dates
            date_elm = soup.select_one(".campaign-date, .campaign-detail__date, .date-info")
            start_date = None
            end_date = None
            
            if date_elm:
                parsed_dates = self._parse_turkish_date(date_elm.get_text().strip())
                if parsed_dates:
                    if isinstance(parsed_dates, tuple):
                        start_date, end_date = parsed_dates
                    else:
                        start_date = parsed_dates

            # Description/Content
            description = title
            # Search for detail paragraphs
            desc_div = soup.select_one(".campaign-detail__content, .campaign-detail-content")
            if desc_div:
                description = desc_div.get_text().strip()
                
            print(f"   📄 Processing details: {title[:50]}...")
            
            # Extract og:title
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            # Extract full HTML body
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else str(soup)

            # Run Golden AI Parser
            ai_data = parse_api_campaign(
                title=title,
                short_description=description[:250],
                content_html=raw_html,
                bank_name="Garanti BBVA",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )

            # AI date fallback
            if not start_date and ai_data.get('start_date'):
                try: start_date = datetime.strptime(ai_data['start_date'], "%Y-%m-%d")
                except: pass
            if not end_date and ai_data.get('end_date'):
                try: end_date = datetime.strptime(ai_data['end_date'], "%Y-%m-%d")
                except: pass

            # Default start date if missing but end date exists
            if not start_date and end_date:
                try:
                    start_today = datetime.utcnow().date()
                    if start_today <= end_date.date():
                        start_date = datetime(start_today.year, start_today.month, start_today.day)
                    else:
                        start_date = end_date
                except:
                    pass

            # Save campaign to DB
            result = self._save_campaign(
                title=title,
                details_text=description,
                image_url=image_url,
                tracking_url=url,
                start_date=start_date,
                end_date=end_date,
                ai_data=ai_data
            )
            return result

        except Exception as e:
            print(f"   ❌ Error extracting campaign details: {e}")
            return f"error: {str(e)}"

    def _save_campaign(self, title: str, details_text: str, image_url: Optional[str],
                       tracking_url: str, start_date: Optional[datetime], end_date: Optional[datetime],
                       ai_data: Dict[str, Any]) -> str:
        """Save campaign to database using central upsert_campaign helper"""
        with get_db_session() as db:
            if is_url_blocked(db, tracking_url):
                print(f"   🚫 Skipped (Safety Check: Blocklisted): {title[:50]}...")
                return "skipped"

            slug = get_unique_slug(title, db, Campaign)
            
            # Sector
            sector_id = None
            if ai_data.get('sector'):
                sector = db.query(Sector).filter(Sector.slug == ai_data.get('sector', 'diger')).first()
                if sector:
                    sector_id = sector.id
            
            # Conditions
            conditions_list = ai_data.get('conditions', [])
            conditions_text = '\n'.join(conditions_list)
            
            participation = ai_data.get('participation')
            eligible_cards_str = None
            cards_list = ai_data.get('cards', [])
            if cards_list:
                eligible_cards_str = ', '.join(cards_list)
                if len(eligible_cards_str) > 255:
                    eligible_cards_str = eligible_cards_str[:255]

            # Construct campaign record
            campaign = Campaign(
                card_id=self.card_id,
                sector_id=sector_id,
                slug=slug,
                title=ai_data.get('short_title') or ai_data.get('title') or title,
                reward_text=ai_data.get('reward_text'),
                clean_text=ai_data.get('_clean_text'),
                reward_value=ai_data.get('reward_value'),
                reward_type=ai_data.get('reward_type'),
                description=ai_data.get('description') or details_text,
                ai_marketing_text=ai_data.get('ai_marketing_text'),
                conditions=conditions_text,
                eligible_cards=eligible_cards_str,
                participation=participation,
                image_url=image_url,
                start_date=start_date,
                end_date=end_date,
                tracking_url=tracking_url,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            campaign, op_status = upsert_campaign(db, campaign)
            db.commit()
            
            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                print(f"   ✅ Saved: {campaign.title[:50]}... (Reward: {campaign.reward_text})")
                
            # Link Brands
            brand_names = ai_data.get('brands', [])
            if brand_names:
                from src.services.brand_matcher import get_or_create_brands_list
                brand_ids = get_or_create_brands_list(db, brand_names, {}, sector_id)
                for bid in brand_ids:
                    try:
                        link = db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == campaign.id,
                            CampaignBrand.brand_id == bid
                        ).first()
                        if not link:
                            db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                            db.commit()
                    except:
                        db.rollback()
                        
            return op_status

    def run(self):
        """Main execution flow"""
        print("🚀 Starting Garanti BBVA General Campaigns Scraper...")
        
        # Fetch active campaign URLs from listing page
        campaign_urls = self._fetch_campaign_list()
        
        if not campaign_urls:
            print("❌ No campaigns found on site!")
            from src.utils.logger_utils import log_scraper_execution
            with get_db_session() as db:
                log_scraper_execution(db, "garanti", "SUCCESS", 0, 0, 0, 0)
            return

        filtered_urls = campaign_urls
        print(f"Processing all {len(filtered_urls)} campaigns...")

        if self.limit:
            filtered_urls = filtered_urls[:self.limit]
            print(f"   Limit applied: Processing first {self.limit} campaigns.")

        total_found = len(campaign_urls)
        success_count = 0
        revived_count = 0
        skipped_count = 0
        failed_count = 0
        error_details = []

        for idx, url in enumerate(filtered_urls, 1):
            print(f"\n[{idx}/{len(filtered_urls)}] Processing: {url}")
            try:
                result = self._process_campaign(url)
                if result == "saved":
                    success_count += 1
                elif result == "revived":
                    revived_count += 1
                elif result == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1
                    error_details.append({"url": url, "error": f"Result: {result}"})
            except Exception as e:
                failed_count += 1
                error_details.append({"url": url, "error": str(e)})
                print(f"   ❌ Error: {e}")
                
            time.sleep(1.0)

        # Log results
        status = "SUCCESS"
        if failed_count > 0:
            status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"
            
        print(f"\n{'=' * 60}")
        print(f"✅ Scraping complete!")
        print(f"✅ Summary: Found {total_found}, Saved {success_count}, Revived {revived_count}, Skipped {skipped_count}, Failed {failed_count}.")
        
        from src.utils.logger_utils import log_scraper_execution
        with get_db_session() as db:
            log_scraper_execution(
                db=db,
                scraper_name="garanti",
                status=status,
                total_found=total_found,
                total_saved=success_count,
                total_skipped=skipped_count,
                total_failed=failed_count,
                total_revived=revived_count,
                error_details={"errors": error_details} if error_details else None
            )
            
        clear_cache()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Garanti BBVA General Campaigns Scraper")
    parser.add_argument("--limit", type=int, help="Limit the number of campaigns to scrape")
    args = parser.parse_args()
    
    scraper = GarantiScraper(limit=args.limit)
    scraper.run()
