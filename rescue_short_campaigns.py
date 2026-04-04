import os
import sys
from sqlalchemy import func
from datetime import datetime

# Ensure src in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Card, Bank
from src.scrapers.yapikredi_world import YapikrediWorldScraper
from src.scrapers.garanti_bonus import GarantiBonusScraper

def rescue_short_campaigns(limit=500):
    print(f"🚀 Starting Content Rescue for Short Campaigns (< {limit} chars)...")
    db = SessionLocal()
    
    # Pre-instantiate scrapers
    scrapers = {
        'Yapı Kredi': YapikrediWorldScraper(),
        'Garanti BBVA': GarantiBonusScraper()
    }

    try:
        # Find active campaigns with very short text
        candidates = db.query(Campaign).join(Card).join(Bank).filter(
            Campaign.is_active == True,
            func.length(Campaign.clean_text) < limit,
            Bank.name.in_(scrapers.keys())
        ).all()

        print(f"🔍 Found {len(candidates)} short-text campaigns in target banks.\n")

        for c in candidates:
            bank_name = c.card.bank.name
            scraper = scrapers.get(bank_name)
            
            if not scraper:
                continue

            print(f"🔄 Re-scraping [{c.id}] {c.title[:50]} (Bank: {bank_name})...")
            
            try:
                # Use the scraper's extraction logic to get full content from the URL
                # In our refined scrapers, we now have logic to fetch full HTML
                # We simulate a partial run for this specific URL
                
                # For Yapı Kredi and Garanti, we updated the processing logic.
                # Here we directly call the processing helper that fetches full text.
                if bank_name == 'Yapı Kredi':
                    # Yapı Kredi logic is now in _process_item or similar
                    # We can use a trick to re-trigger it. 
                    # For brevity in this script, we'll use requests + the selector we found.
                    import requests
                    from bs4 import BeautifulSoup
                    r = requests.get(c.tracking_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
                    soup = BeautifulSoup(r.text, 'html.parser')
                    content = soup.select_one('.campaign-detail-content, .campaign-detail, main')
                    if content:
                        full_text = content.get_text(separator="\n", strip=True)
                        if len(full_text) > len(c.clean_text):
                            c.clean_text = full_text
                            print(f"   ✅ SUCCESS! New Length: {len(full_text)}")
                            
                            # Re-parse if needed
                            from src.services.ai_parser import AIParser
                            parser = AIParser()
                            ai_data = parser.parse_campaign_data(full_text, title=c.title, force=True, campaign_id=c.id)
                            if ai_data:
                                c.conditions = "\n".join(ai_data.get('conditions', []))
                                c.eligible_cards = ", ".join(ai_data.get('cards', []))
                
                elif bank_name == 'Garanti BBVA':
                    import requests
                    from bs4 import BeautifulSoup
                    r = requests.get(c.tracking_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
                    soup = BeautifulSoup(r.text, 'html.parser')
                    # Use the improved Garanti selectors
                    parts = soup.select('.campaign-detail__info, .campaign-detail__others, .how-to-win, .campaign-detail-tab-content')
                    full_text = "\n".join([p.get_text(separator="\n", strip=True) for p in parts])
                    if len(full_text) > 100: # Found some content
                         c.clean_text = full_text
                         print(f"   ✅ SUCCESS! New Length: {len(full_text)}")
                         from src.services.ai_parser import AIParser
                         parser = AIParser()
                         ai_data = parser.parse_campaign_data(full_text, title=c.title, force=True, campaign_id=c.id)
                         if ai_data:
                             c.conditions = "\n".join(ai_data.get('conditions', []))
                             c.eligible_cards = ", ".join(ai_data.get('cards', []))

                db.commit()
            except Exception as e:
                print(f"   ❌ Error re-scraping {c.id}: {e}")
                db.rollback()

            print("-" * 40)

    except Exception as e:
        print(f"❌ Error during rescue: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    rescue_short_campaigns()
