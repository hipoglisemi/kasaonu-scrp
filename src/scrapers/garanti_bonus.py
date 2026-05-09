


import sys
import os

# Dynamic path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from typing import Dict, Any, List, Optional  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import Session  # type: ignore # pyre-ignore[21]

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import parse_api_campaign  # type: ignore # pyre-ignore[21]
from src.utils.slug_generator import get_unique_slug  # type: ignore # pyre-ignore[21]
from src.utils.cache_manager import clear_cache  # type: ignore # pyre-ignore[21]
from src.services.brand_normalizer import cleanup_brands  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore


class GarantiBonusScraper:
    """Scraper for Garanti Bonus campaigns using HTML parsing + Gemini AI.
    
    Unlike Yapı Kredi which has APIs, Garanti uses Server-Side Rendering.
    All 200+ campaigns are delivered in the initial HTML response.
    """
    
    BASE_URL = 'https://www.bonus.com.tr'
    CAMPAIGN_LIST_URL = 'https://www.bonus.com.tr/kampanyalar'
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache',
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.bank = None
        self.card = None
        
        # Initialize bank and card from DB
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == "garanti-bbva").first()  # type: ignore # pyre-ignore[16]
            if not bank:
                bank = Bank(name="Garanti BBVA", slug="garanti-bbva", is_active=True)
                db.add(bank)  # type: ignore # pyre-ignore[16]
                db.commit()  # type: ignore # pyre-ignore[16]
                db.refresh(bank)
                print(f"✅ Created bank: Garanti BBVA")
            self.bank = bank
            
            card = db.query(Card).filter(  # type: ignore # pyre-ignore[16]
                Card.bank_id == self.bank.id,  # type: ignore # pyre-ignore[16]
                Card.slug == "garanti-bonus"
            ).first()
            if not card:
                card = Card(bank_id=self.bank.id, name="Garanti Bonus", slug="garanti-bonus", is_active=True)  # type: ignore # pyre-ignore[16]
                db.add(card)  # type: ignore # pyre-ignore[16]
                db.commit()  # type: ignore # pyre-ignore[16]
                db.refresh(card)
                print(f"✅ Created card: Garanti Bonus")
            self.card = card
    
    def _get_or_create_bank(self):
        """Get or create Garanti BBVA bank"""
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == "garanti-bbva").first()  # type: ignore # pyre-ignore[16]
            if not bank:
                bank = Bank(
                    name="Garanti BBVA",
                    slug="garanti-bbva",
                    is_active=True
                )
                db.add(bank)  # type: ignore # pyre-ignore[16]
                db.commit()  # type: ignore # pyre-ignore[16]
                db.refresh(bank)
                print(f"✅ Created bank: Garanti BBVA")
            self.bank = bank
            return bank  # type: ignore # pyre-ignore[7]
    
    def _get_or_create_card(self):
        """Get or create Garanti Bonus card"""
        with get_db_session() as db:
            card = db.query(Card).filter(  # type: ignore # pyre-ignore[16]
                Card.bank_id == self.bank.id,  # type: ignore # pyre-ignore[16]
                Card.slug == "garanti-bonus"
            ).first()
            
            if not card:
                card = Card(
                    bank_id=self.bank.id,  # type: ignore # pyre-ignore[16]
                    name="Garanti Bonus",
                    slug="garanti-bonus",
                    is_active=True
                )
                db.add(card)  # type: ignore # pyre-ignore[16]
                db.commit()  # type: ignore # pyre-ignore[16]
                db.refresh(card)
                print(f"✅ Created card: Garanti Bonus")
            
            self.card = card
            return card  # type: ignore # pyre-ignore[7]
    
    def _fetch_campaign_list(self) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        """Fetch all campaign URLs from the main listing page.
        
        Returns:
            List of campaign URLs
        """
        print(f"📥 Fetching campaign list from {self.CAMPAIGN_LIST_URL}")
        
        try:
            response = self.session.get(
                self.CAMPAIGN_LIST_URL,
                headers=self.HEADERS,
                timeout=20
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all campaign links (a.direct elements)
            campaign_links = []
            for link in soup.find_all('a', class_='direct', href=True):
                href = link['href']
                # Filter out non-campaign pages
                if '/kampanyalar/' in href and len(href.split('/')) > 2:
                    if not any(x in href for x in ['sektor', 'kategori', 'marka', '#', 'javascript']):  # type: ignore # pyre-ignore[16,6]
                        full_url = urljoin(self.BASE_URL, href)
                        if full_url not in campaign_links:
                            campaign_links.append(full_url)
            
            print(f"✅ Found {len(campaign_links)} campaigns")
            return campaign_links  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"❌ Error fetching campaign list: {e}")
            return []  # type: ignore # pyre-ignore[7]
    
    def _process_campaign(self, url: str) -> str:
        """Process a single campaign page.
        
        Args:
            url: Campaign detail page URL
            
        Returns:
            True if successful, False otherwise
        """
        # Database Pre-check (Skip Logic)
        try:
            with get_db_session() as db:
                if is_url_blocked(db, url):
                    print(f"   🚫 Skipped (Blocklisted): {url}")
                    return "skipped"  # type: ignore # pyre-ignore[7]

                existing = db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
                if existing and existing.is_active and existing.is_approved:
                    print(f"   ⏭️ Skipped (Already exists and active): {url}")
                    return "skipped"  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   ⚠️ DB Pre-check error: {e}")

        try:
            # Fetch campaign detail page
            response = self.session.get(url, headers=self.HEADERS, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # ✅ DIRECT HTML EXTRACTION (No AI needed)
            # Title - Try multiple common selectors
            title_elm = soup.select_one('.campaign-detail-title h1, .campaign-detail__title h1, .campaign-detail h1')
            title = title_elm.get_text().strip() if title_elm else "Başlık Bulunamadı"
            
            # Image
            img_elm = soup.select_one('.campaign-detail__image img')
            image_url = None
            if img_elm:
                image_url = img_elm.get('data-src') or img_elm.get('src')
                if image_url:
                    image_url = urljoin(self.BASE_URL, image_url)
            
            # Dates - Try multiple selectors as structure is changing
            date_elm = soup.select_one('.campaign-date, .campaign-detail__date, .date-info')
            start_date = None
            end_date = None
            
            if date_elm:
                date_text = date_elm.get_text().strip()
                if '-' in date_text:
                    parts = date_text.split('-')
                    if len(parts) >= 2:
                        # Try to parse end date first to get month/year context
                        end_part = parts[1].strip()
                        end_date = self._parse_turkish_date(end_part)
                        
                        start_part = parts[0].strip()
                        # specific handling for "1 - 28 Şubat 2026" where start is just a day
                        # Check if start part is just digits
                        if start_part.isdigit() and end_date:
                            try:
                                day = int(start_part)
                                start_date = datetime(end_date.year, end_date.month, day)
                            except:
                                start_date = self._parse_turkish_date(start_part)
                        else:
                            # Full date parse attempt
                           start_date = self._parse_turkish_date(start_part)
                else:
                    # Single date? unlikely but possible
                    pass
            
            # Description
            description = title
            how_win_header = soup.find('h2', string=lambda x: x and 'NASIL KAZANIRIM' in x.upper())
            if how_win_header:
                desc_p = how_win_header.find_next_sibling('p')
                if desc_p:
                    description = desc_p.get_text().strip()
            
            print(f"   📄 {title[:60]}...")  # type: ignore # pyre-ignore[16,6]
            
            # Extract og:title for better cleaning anchors
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            # Extract FULL BODY for Autofix-standard global cleaning
            # This ensures we don't miss any detail boxes or card lists
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else str(soup)
            
            import re
            
            # AI parses only: reward_text, reward_value, reward_type, brands, sector, conditions, dates
            ai_data = parse_api_campaign(
                title=title,
                short_description=description,
                content_html=raw_html,
                bank_name="Garanti BBVA",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )
            
            # Fallback for dates if HTML parsing failed
            if not start_date and ai_data.get('start_date'):
                try:
                    start_date = datetime.strptime(ai_data['start_date'], "%Y-%m-%d")
                except:
                    pass
            
            if not end_date and ai_data.get('end_date'):
                try:
                    end_date = datetime.strptime(ai_data['end_date'], "%Y-%m-%d")
                except:
                    pass
            
            # Save campaign
            result = self._save_campaign(
                title=title,
                details_text=description,
                image_url=image_url,
                tracking_url=url,
                start_date=start_date,
                end_date=end_date,
                ai_data=ai_data
            )
            
            return result  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"   ❌ Error processing campaign {url}: {e}")
            return f"error: {str(e)}"  # type: ignore # pyre-ignore[7]
    
    def _save_campaign(self, title: str, details_text: str, image_url: Optional[str],  # type: ignore # pyre-ignore[16,6]
                       tracking_url: str, start_date, end_date, ai_data: Dict[str, Any]):  # type: ignore # pyre-ignore[16,6]
        """Save campaign to database"""
        with get_db_session() as db:
            # Check if campaign already exists
            # Check if campaign already exists or is blocked
            if is_url_blocked(db, tracking_url):
                print(f"   🚫 Skipped (Safety Check: Blocklisted): {title[:50]}...")
                return "skipped"  # type: ignore # pyre-ignore[7]

            # Early skip removed to allow upsert_campaign to handle revival logic

            # Generate unique slug
            slug = get_unique_slug(title, db, Campaign)
            
            # Get sector
            sector_id = None
            if ai_data.get('sector'):
                sector = db.query(Sector).filter(Sector.slug == ai_data.get('sector', 'diger')).first()  # type: ignore # pyre-ignore[16]
                if sector:
                    sector_id = sector.id  # type: ignore # pyre-ignore[16]
            
            # Prepare conditions text
            conditions_list = ai_data.get('conditions', [])
            conditions_text = '\n'.join(conditions_list)
            
            # Add participation info to conditions if available
            participation = ai_data.get('participation')
            if participation and participation != "Otomatik katılım":
            
                pass  # participation field written separately to DB
            # Prepare eligible cards
            eligible_cards_str = None
            cards_list = ai_data.get('cards', [])
            if cards_list:
                eligible_cards_str = ', '.join(cards_list)
                # Ensure it fits in DB column if limited (String usually 255 but let's be safe)
            # Ensure eligible_cards fits in DB column if limited (String usually 255 but let's be safe)
            if eligible_cards_str and len(eligible_cards_str) > 255:
                eligible_cards_str = eligible_cards_str[:255]  # type: ignore # pyre-ignore[16,6]

            # Fallback for start_date if missing but end_date exists
            # Fallback for start_date if missing but end_date exists
            if not start_date and end_date:
                # Set start date to today (scrape date) as requested
                # This handles long-running campaigns correctly (start date = scrape date)
                try:
                    start_today = datetime.utcnow().date()
                    # Only set if today is before or equal to end_date
                    if start_today <= end_date:
                        start_date = start_today
                    else:
                        # If today is after end_date (shouldn't happen for active campaigns), use end_date
                        start_date = end_date
                except Exception:
                    pass

            # Create campaign
            campaign = Campaign(  # type: ignore
                card_id=self.card.id,  # type: ignore
                sector_id=sector_id,  # type: ignore
                slug=slug,  # type: ignore
                title=ai_data.get('short_title') or ai_data.get('title') or title,  # type: ignore
                reward_text=ai_data.get('reward_text'),  # type: ignore
                clean_text=ai_data.get('_clean_text'),  # type: ignore
                reward_value=ai_data.get('reward_value'),  # type: ignore
                reward_type=ai_data.get('reward_type'),  # type: ignore
                description=ai_data.get('description') or details_text,  # type: ignore
                ai_marketing_text=ai_data.get('ai_marketing_text'),  # type: ignore
                conditions=conditions_text,  # type: ignore
                eligible_cards=eligible_cards_str,
                participation=participation,  # type: ignore
                image_url=image_url,  # type: ignore
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
                tracking_url=tracking_url,  # type: ignore
                is_active=True,  # type: ignore
                created_at=datetime.utcnow(),  # type: ignore
                updated_at=datetime.utcnow()  # type: ignore
            )
            
            # Use centralized upsert_campaign for revival and quality control
            campaign, op_status = upsert_campaign(db, campaign)
            db.commit()
            
            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title[:50]}... (Reward: {campaign.reward_text})")
            
            # Link brands
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
    
    def _generate_slug(self, title: str) -> str:
        """Generate URL-friendly slug from title"""
        import re  # type: ignore # pyre-ignore[21]
        import unicodedata  # type: ignore # pyre-ignore[21]
        
        # Normalize unicode characters
        title = unicodedata.normalize('NFKD', title)
        # Convert to lowercase
        title = title.lower()
        # Replace Turkish characters
        replacements = {
            'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c'
        }
        for tr_char, en_char in replacements.items():
            title = title.replace(tr_char, en_char)
        # Remove non-alphanumeric characters
        title = re.sub(r'[^a-z0-9\s-]', '', title)
        # Replace spaces with hyphens
        title = re.sub(r'[\s]+', '-', title)
        # Remove consecutive hyphens
        title = re.sub(r'-+', '-', title)
        # Trim hyphens from ends
        return title.strip('-')[:100]  # type: ignore # pyre-ignore[16,7,6]
    
    def _parse_turkish_date(self, date_str: str) -> Optional[datetime]:  # type: ignore # pyre-ignore[16,6]
        """Parse Turkish date string (e.g., '1 Ocak 2026')"""
        if not date_str:
            return None  # type: ignore # pyre-ignore[7]
        
        months = {
            'ocak': 1, 'şubat': 2, 'mart': 3, 'nisan': 4,
            'mayıs': 5, 'haziran': 6, 'temmuz': 7, 'ağustos': 8,
            'eylül': 9, 'ekim': 10, 'kasım': 11, 'aralık': 12
        }
        
        try:
            import re  # type: ignore # pyre-ignore[21]
            # Extract day, month, year
            parts = date_str.lower().strip().split()
            day = int(re.sub(r'\D', '', parts[0]))
            month_name = next((m for m in months if m in date_str.lower()), None)
            if not month_name:
                return None  # type: ignore # pyre-ignore[7]
            month = months[month_name]
            
            # Find year (4-digit number)
            year = datetime.now().year
            for part in parts:
                if part.isdigit() and len(part) == 4:
                    year = int(part)
                    break
            
            return datetime(year, month, day)  # type: ignore # pyre-ignore[7]
        except:
            return None  # type: ignore # pyre-ignore[7]
    
    def run(self):
        """Main execution flow"""
        print("🚀 Garanti Bonus Scraper - HTML + Gemini AI Edition")
        print("=" * 60)
        
        try:
            from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
            
            # Fetch campaign list
            campaign_urls = self._fetch_campaign_list()
            
            total_found = len(campaign_urls)
            success_count = 0
            total_revived = 0
            skipped_count = 0
            failed_count = 0
            error_details = []
            
            if not campaign_urls:
                print("❌ No campaigns found!")
                
                with get_db_session() as db:
                    log_scraper_execution(
                        db=db,
                        scraper_name="garanti_bonus",
                        status="FAILED",
                        total_found=0,
                        total_saved=0,
                        total_skipped=0,
                        total_failed=0,
                        error_details={"error": "No campaigns found"}
                    )
                return
            
            # Process campaigns
            for i, url in enumerate(campaign_urls, 1):
                print(f"\n[{i}/{len(campaign_urls)}] Processing: {url}")  # type: ignore # pyre-ignore[16,6]
                
                try:
                    result = self._process_campaign(url)
                    if result == "saved":
                        success_count += 1  # type: ignore # pyre-ignore[58]
                    elif result == "revived":
                        total_revived += 1
                    elif result == "skipped":
                        skipped_count += 1  # type: ignore # pyre-ignore[58]
                    else:
                        failed_count += 1  # type: ignore # pyre-ignore[58]
                        error_details.append({"url": url, "error": f"Process returned {result}"})
                except Exception as e:
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": url, "error": str(e)})
                    print(f"❌ Failed processing {url}: {e}")
                
                # Rate limiting
                time.sleep(0.8)
            
            print(f"\n{'=' * 60}")
            print(f"✅ Scraping complete!")
            print(f"✅ Özet: {total_found} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
            
            # Determine status
            status = "SUCCESS"
            if failed_count > 0:  # type: ignore # pyre-ignore[58]
                status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
                
            # Log to DB
            with get_db_session() as db:
                log_scraper_execution(
                    db=db,
                    scraper_name="garanti_bonus",
                    status=status,
                    total_found=total_found,
                    total_saved=success_count,
                    total_skipped=skipped_count,
                    total_failed=failed_count,
                    total_revived=total_revived,
                    error_details={"errors": error_details} if error_details else None
                )
            
            # Clear cache
            clear_cache()
            
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            
            with get_db_session() as db:
                from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
                log_scraper_execution(
                    db=db,
                    scraper_name="garanti_bonus",
                    status="FAILED",
                    total_found=0,
                    total_saved=0,
                    total_skipped=0,
                    total_failed=1,
                    error_details={"error": str(e)}
                )
                
            raise


if __name__ == "__main__":
    scraper = GarantiBonusScraper()
    scraper.run()
