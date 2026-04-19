import os
import sys
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load .env manually to avoid environment issues
def load_env():
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value.replace('"', "")

load_env()

from src.services.ai_parser_golden import parse_api_campaign
from playwright.sync_api import sync_playwright

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def get_live_html(url):
    """Fetch live HTML using Playwright for high integrity"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            # Find og:title
            og_title = page.eval_on_selector('meta[property="og:title"]', 'el => el.content', None)
            return page.content(), og_title
        except Exception as e:
            print(f"❌ Error fetching {url}: {e}")
            return None, None
        finally:
            browser.close()

def run_comparison():
    db = Session()
    # Fetch 2 campaigns for all distinct cards to cover all scrapers
    query = text("""
        WITH RankedCampaigns AS (
            SELECT 
                c.*,
                b.name as bank_internal_name,
                s.name as sector_name,
                ROW_NUMBER() OVER(PARTITION BY b.id ORDER BY c.created_at DESC) as rn
            FROM campaigns c
            LEFT JOIN cards b ON c.card_id = b.id
            LEFT JOIN sectors s ON c.sector_id = s.id
            WHERE c.tracking_url IS NOT NULL AND c.is_active = true
        )
        SELECT * FROM RankedCampaigns WHERE rn <= 2
    """)
    
    results = db.execute(query).mappings().all()
    print(f"📊 Found {len(results)} campaigns in DB to compare.")
    
    comparison_data = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        for row in results:
            url = row['tracking_url']
            print(f"🔄 Processing {row['bank_internal_name']} | URL: {url}")
            
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                # Small wait for dynamic content
                page.wait_for_timeout(2000)
                
                content = page.content()
                # Try to get og:title safely
                og_title = None
                try:
                    og_title = page.eval_on_selector('meta[property="og:title"]', 'el => el.content')
                except: pass
                
                page.close()
                
                # Run new pipeline
                new_res = parse_api_campaign(
                    title=row['title'],
                    short_description=None,
                    content_html=content,
                    bank_name=row['bank_internal_name'],
                    tracking_url=url,
                    og_title=og_title
                )
                
                if new_res:
                    comparison_data.append({
                        "bank": row['bank_internal_name'],
                        "url": url,
                        "db_data": {
                            "title": row['title'],
                            "eligible_cards": row['eligible_cards'],
                            "reward_text": row['reward_text'],
                            "reward_value": float(row['reward_value']) if row['reward_value'] else 0,
                            "sector": row['sector_name'],
                            "participation": row['participation'],
                            "conditions": row['conditions']
                        },
                        "new_system_data": {
                            "title": new_res.get('short_title') or new_res.get('title'),
                            "eligible_cards": ", ".join(new_res.get('cards', [])),
                            "reward_text": new_res.get('reward_text'),
                            "reward_value": new_res.get('reward_value'),
                            "sector": new_res.get('sector'),
                            "participation": new_res.get('participation'),
                            "conditions": "\n".join(new_res.get('conditions', []))
                        }
                    })
                    print(f"   ✅ Comparison done for {row['title']}")
                
            except Exception as e:
                print(f"   ❌ Error processing {url}: {e}")
                continue

        browser.close()

    # Save Results
    with open("scratch/db_comparison_detailed.json", "w", encoding="utf-8") as f:
        json.dump(comparison_data, f, ensure_ascii=False, indent=2)

    db.close()
    print(f"\n✅ Comparison completed for {len(comparison_data)} campaigns. Results in scratch/db_comparison_detailed.json")

if __name__ == "__main__":
    run_comparison()
