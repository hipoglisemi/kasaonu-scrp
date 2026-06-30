import sys
import os
import json
import re
import requests
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign, Bank, Card, Sector, CampaignBrand
from src.services.ai_parser import parse_api_campaign
from src.utils.slug_generator import get_unique_slug
from src.utils.scraper_utils import is_url_blocked, upsert_campaign

class PokusScraper:
    """
    Scraper for Pokus campaigns.
    Extracts campaign list from inline JSON in HTML, then fetches details via requests.
    """
    
    BASE_URL = 'https://pokus.com.tr'
    BANK_NAME = 'Pokus'
    CARD_NAME = 'Pokus'
    
    def __init__(self):
        self.bank = None
        self.card = None
        
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == "pokus").first()
            if not bank:
                print(f"Creating bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="pokus", logo_url="/logos/banks/pokus.png", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            self.bank_id = bank.id
            self.bank_name = bank.name
            
            card = db.query(Card).filter(Card.slug == "pokus", Card.bank_id == self.bank_id).first()
            if not card:
                print(f"Creating card: {self.CARD_NAME}")
                card = Card(name=self.CARD_NAME, bank_id=self.bank_id, slug="pokus", card_type="prepaid", logo_url="/logos/cards/pokus.png", is_active=True)
                db.add(card)
                db.commit()
                db.refresh(card)
            self.card_id = card.id
            self.card_name = card.name

    def _fetch_list(self) -> List[Dict[str, Any]]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            print("Fetching campaign list from Pokus...")
            res = requests.get(f"{self.BASE_URL}/tum-kampanyalar", headers=headers, timeout=15)
            res.raise_for_status()
            
            match = re.search(r'initPagniation\(\[(.*?)\]\);', res.text, re.DOTALL)
            if not match:
                print("Could not find initPagniation JSON in page source.")
                return []
                
            raw_json = '[' + match.group(1) + ']'
            items = json.loads(raw_json)
            
            print(f"Found {len(items)} campaigns.")
            return items
            
        except Exception as e:
            print(f"Failed to fetch campaign list: {e}")
            return []

    def _fetch_detail(self, slug: str) -> Optional[str]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        url = f"{self.BASE_URL}/{slug}" if not slug.startswith('/') else f"{self.BASE_URL}{slug}"
        
        try:
            time.sleep(1)
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, 'html.parser')
            c4 = soup.find('div', class_='c-unit-04')
            if c4:
                # Keep basic html or just text? ai_parser can handle html
                # But it's better to provide clean text
                for script in c4(["script", "style"]):
                    script.extract()
                return c4.get_text(separator='\n', strip=True)
                
            return soup.get_text(separator='\n', strip=True)
            
        except Exception as e:
            print(f"Failed to fetch detail for {url}: {e}")
            return None

    def run(self):
        print(f"Starting {self.BANK_NAME} scraper...")
        items = self._fetch_list()
        
        for idx, item in enumerate(items, 1):
            slug = item.get('pageUrl')
            if not slug:
                continue
                
            url = f"{self.BASE_URL}/{slug}" if not slug.startswith('/') else f"{self.BASE_URL}{slug}"
            
            print(f"\n[{idx}/{len(items)}] Processing: {item.get('title')}")
            
            with get_db_session() as db:
                if is_url_blocked(db, url):
                    print(f"URL is manually blocked: {url}")
                    continue
                
            content = self._fetch_detail(slug)
            if not content:
                print(f"Failed to get content for {url}")
                continue
                
            image_url = item.get('bgImage')
            if image_url and not image_url.startswith('http'):
                image_url = f"{self.BASE_URL}{image_url}"
                
            try:
                # Prepare AI payload
                print("Parsing with AI...")
                parsed = parse_api_campaign(
                    title=item.get('title', ''),
                    short_description=item.get('discount', ''),
                    content_html=content,
                    bank_name=self.bank_name,
                    scraper_sector=item.get('kampanyaKategorisi', '').replace('#', '').strip()
                )
                
                if parsed:
                    with get_db_session() as db:
                        sector_name = parsed.get('sector', 'Diğer')
                        sector = db.query(Sector).filter((Sector.slug == sector_name) | (Sector.name.ilike(sector_name))).first()
                        if not sector:
                            sector = db.query(Sector).filter(Sector.slug == 'diger').first()
                        sector_id = sector.id if sector else None

                        seo_slug = parsed.get('title', item.get('title', ''))
                        slug = get_unique_slug(seo_slug, db, Campaign)
                        
                        display_title = parsed.get('title') or parsed.get('short_title') or item.get('title', '')
                        
                        campaign = Campaign(
                            slug=slug,
                            title=display_title,
                            card_id=self.card_id,
                            sector_id=sector_id,
                            reward_value=parsed.get('reward_value'),
                            reward_type=parsed.get('reward_type'),
                            reward_text=parsed.get('reward_text', 'Detayları İnceleyin'),
                            clean_text=parsed.get('_clean_text', ''),
                            description=parsed.get('description') or content,
                            ai_marketing_text=parsed.get('ai_marketing_text'),
                            conditions="\n".join(parsed.get('conditions', [])),
                            start_date=datetime.strptime(parsed.get('start_date'), "%Y-%m-%d") if parsed.get('start_date') else None,
                            end_date=datetime.strptime(parsed.get('end_date'), "%Y-%m-%d") if parsed.get('end_date') else None,
                            image_url=image_url,
                            tracking_url=url,
                            is_active=True,
                            participation=parsed.get('participation'),
                            eligible_cards=", ".join(parsed.get('cards', [])) if parsed.get('cards') else None,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        
                        campaign, op_status = upsert_campaign(db, campaign)
                        db.commit()
                        print(f"   [{op_status}] Saved: {campaign.title}")
                        
                        db.refresh(campaign)
                        
                        from src.services.brand_matcher import get_or_create_brands_list
                        brand_names = parsed.get("brands", [])
                        brand_ids = get_or_create_brands_list(
                            db=db,
                            names=brand_names,
                            brand_cache=getattr(self, 'brand_cache', {}),
                            sector_id=sector_id
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
                else:
                    print(f"AI parsing failed for {url}")
                    
            except Exception as e:
                print(f"Error processing {url}: {e}")

if __name__ == "__main__":
    scraper = PokusScraper()
    scraper.run()
