import sys
import os
import requests
import time
from datetime import datetime
from typing import Dict, Any, List
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

class RubikparaScraper:
    """
    Scraper for Rubikpara campaigns.
    Extracts campaigns directly from the single campaigns page (they are rendered as buttons).
    """
    
    BASE_URL = 'https://rubikpara.com'
    CAMPAIGNS_URL = 'https://rubikpara.com/kampanyalar'
    BANK_NAME = 'Rubikpara'
    CARD_NAME = 'Rubikpara Cüzdan'
    
    def __init__(self):
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == "rubikpara").first()
            if not bank:
                print(f"Creating bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="rubikpara", logo_url="/logos/banks/rubikpara.png", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            self.bank_id = bank.id
            self.bank_name = bank.name
            
            card = db.query(Card).filter(Card.slug == "rubikpara-cuzdan", Card.bank_id == self.bank_id).first()
            if not card:
                print(f"Creating card: {self.CARD_NAME}")
                card = Card(name=self.CARD_NAME, bank_id=self.bank_id, slug="rubikpara-cuzdan", card_type="prepaid", logo_url="/logos/cards/rubikpara.png", is_active=True)
                db.add(card)
                db.commit()
                db.refresh(card)
            self.card_id = card.id
            self.card_name = card.name

    def _fetch_list(self) -> List[Dict[str, Any]]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        try:
            print(f"Fetching campaigns from {self.CAMPAIGNS_URL}...")
            res = requests.get(self.CAMPAIGNS_URL, headers=headers, timeout=15)
            res.encoding = 'utf-8'
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, 'html.parser')
            # The campaigns are inside <button class="... flex flex-col ..."> elements
            buttons = soup.find_all('button', class_=lambda c: c and 'flex-col' in c)
            
            items = []
            
            for b in buttons:
                h3 = b.find('h3')
                if not h3:
                    continue
                    
                brand_title = h3.get_text(strip=True)
                
                p = b.find('p', class_=lambda c: c and 'text-sm' in c)
                desc = p.get_text(strip=True) if p else f"{brand_title} kampanyası"
                
                img = b.find('img')
                img_src = img.get('src') if img else None
                if img_src and not img_src.startswith('http'):
                    img_src = f"{self.BASE_URL}{img_src}"
                    
                items.append({
                    'title': brand_title,
                    'description': desc,
                    'image_url': img_src
                })
                
            print(f"Found {len(items)} campaigns on the page.")
            return items
            
        except Exception as e:
            print(f"Failed to fetch campaign list: {e}")
            return []

    def run(self):
        print(f"🚀 Starting {self.BANK_NAME} Scraper...")
        items = self._fetch_list()
        
        for idx, item in enumerate(items, 1):
            title = item.get('title')
            desc = item.get('description')
            image_url = item.get('image_url')
            
            # Since all campaigns are on the same page, we use a single URL
            # but append an anchor or parameter to make it slightly distinguishable for logging (optional)
            url = f"{self.CAMPAIGNS_URL}#{title.replace(' ', '-').lower()}"
            
            print(f"\n[{idx}/{len(items)}] Processing: {desc}")
            
            with get_db_session() as db:
                if is_url_blocked(db, url):
                    print(f"URL is manually blocked: {url}")
                    continue
                
            try:
                print("Parsing with AI...")
                parsed = parse_api_campaign(
                    title=desc, # Use desc as the main title for AI since it has "Anında %8 Cashback"
                    short_description='',
                    content_html=f"Rubikpara Cüzdan ile {title} alışverişlerinde geçerlidir. {desc}",
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

                        seo_slug = parsed.get('title', desc)
                        slug = get_unique_slug(seo_slug, db, Campaign)
                        
                        display_title = parsed.get('title') or parsed.get('short_title') or desc
                        
                        start_d = datetime.strptime(parsed.get('start_date'), "%Y-%m-%d") if parsed.get('start_date') else None
                        end_d = datetime.strptime(parsed.get('end_date'), "%Y-%m-%d") if parsed.get('end_date') else None
                        
                        campaign = Campaign(
                            slug=slug,
                            title=display_title,
                            card_id=self.card_id,
                            sector_id=sector_id,
                            reward_value=parsed.get('reward_value'),
                            reward_type=parsed.get('reward_type'),
                            reward_text=parsed.get('reward_text', 'Detayları İnceleyin'),
                            clean_text=parsed.get('_clean_text', ''),
                            description=parsed.get('description') or desc,
                            ai_marketing_text=parsed.get('ai_marketing_text'),
                            conditions="\n".join(parsed.get('conditions', [])),
                            start_date=start_d,
                            end_date=end_d,
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
                        
                        # Add CampaignBrand links
                        from src.services.brand_matcher import get_or_create_brands_list
                        brand_names = parsed.get("brands", [title]) # Fallback to the brand title we extracted
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
    scraper = RubikparaScraper()
    scraper.run()
