import sys
import os
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

class HayhayScraper:
    """
    Scraper for Hayhay campaigns.
    Extracts campaigns from the SSR list page, then fetches details from each campaign page.
    """
    
    BASE_URL = 'https://www.hayhay.com'
    BANK_NAME = 'Hayhay'
    CARD_NAME = 'Hayhay'
    
    def __init__(self):
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == "hayhay").first()
            if not bank:
                print(f"Creating bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="hayhay", logo_url="/logos/banks/hayhay.png", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            self.bank_id = bank.id
            self.bank_name = bank.name
            
            card = db.query(Card).filter(Card.slug == "hayhay", Card.bank_id == self.bank_id).first()
            if not card:
                print(f"Creating card: {self.CARD_NAME}")
                card = Card(name=self.CARD_NAME, bank_id=self.bank_id, slug="hayhay", card_type="prepaid", logo_url="/logos/cards/hayhay.png", is_active=True)
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
            print("Fetching campaign list from Hayhay...")
            res = requests.get(f"{self.BASE_URL}/kampanyalar", headers=headers, timeout=15)
            res.encoding = 'utf-8'
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, 'html.parser')
            camps = soup.find_all('a', href=lambda h: h and '/kampanyalar/' in h)
            
            items = []
            seen_urls = set()
            
            for a in camps:
                href = a.get('href')
                if not href or href in seen_urls:
                    continue
                seen_urls.add(href)
                
                title_el = a.find('div', class_=lambda c: c and 'campaign-card__title' in c)
                title = title_el.get_text(separator=' ', strip=True) if title_el else a.get_text(separator=' ', strip=True)
                
                img_el = a.find('img')
                img_src = img_el.get('src') if img_el else None
                
                if img_src and not img_src.startswith('http'):
                    img_src = f"{self.BASE_URL}{img_src}"
                    
                items.append({
                    'url': f"{self.BASE_URL}{href}" if not href.startswith('http') else href,
                    'title': title,
                    'image_url': img_src
                })
                
            print(f"Found {len(items)} campaigns.")
            return items
            
        except Exception as e:
            print(f"Failed to fetch campaign list: {e}")
            return []

    def _fetch_detail(self, url: str) -> Optional[str]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            time.sleep(1)
            res = requests.get(url, headers=headers, timeout=15)
            res.encoding = 'utf-8'
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, 'html.parser')
            content_div = soup.find('div', class_=lambda c: c and 'campaign-detail' in c)
            if content_div:
                for script in content_div(["script", "style"]):
                    script.extract()
                return content_div.get_text(separator='\n', strip=True)
                
            return soup.get_text(separator='\n', strip=True)
            
        except Exception as e:
            print(f"Failed to fetch detail for {url}: {e}")
            return None

    def run(self):
        print(f"🚀 Starting {self.BANK_NAME} Scraper...")
        items = self._fetch_list()
        
        for idx, item in enumerate(items, 1):
            url = item.get('url')
            if not url:
                continue
            
            print(f"\n[{idx}/{len(items)}] Processing: {item.get('title')}")
            
            with get_db_session() as db:
                if is_url_blocked(db, url):
                    print(f"URL is manually blocked: {url}")
                    continue
                
            content = self._fetch_detail(url)
            if not content:
                print(f"Failed to get content for {url}")
                continue
                
            try:
                print("Parsing with AI...")
                parsed = parse_api_campaign(
                    title=item.get('title', ''),
                    short_description='',
                    content_html=content,
                    bank_name=self.bank_name,
                    scraper_sector=None
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
                            image_url=item.get('image_url'),
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
    scraper = HayhayScraper()
    scraper.run()
