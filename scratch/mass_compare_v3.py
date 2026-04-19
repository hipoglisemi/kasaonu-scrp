import os
import sys
import json
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from playwright.sync_api import sync_playwright

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load .env manually
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

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def get_live_html_safe(url):
    """Fetch live HTML using a fresh Playwright session for each URL to avoid crashes"""
    print(f"   📥 Fetching HTML: {url}")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000) # Wait for JS dynamic elements
            
            content = page.content()
            og_title = None
            try:
                og_title = page.eval_on_selector('meta[property="og:title"]', 'el => el.content')
            except: pass
            
            browser.close()
            return content, og_title
        except Exception as e:
            print(f"   ❌ Browser Error for {url}: {e}")
            return None, None

def run_comparison():
    db = Session()
    # Fetch 2 campaigns for all distinct cards (scrapers)
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
            WHERE c.tracking_url IS NOT NULL
        )
        SELECT * FROM RankedCampaigns WHERE rn <= 2
    """)
    
    results = db.execute(query).mappings().all()
    print(f"📊 Found {len(results)} campaigns in DB to compare.")
    
    comparison_data = []
    
    for row in results:
        url = row['tracking_url']
        print(f"🔄 Comparing {row['bank_internal_name']} | Title: {row['title']}")
        
        live_html, og_title = get_live_html_safe(url)
        if not live_html:
            continue
            
        # Run new pipeline
        try:
            new_res = parse_api_campaign(
                title=row['title'],
                short_description=None,
                content_html=live_html,
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
                print(f"   ✅ Comparison ready for {row['title']}")
        except Exception as e:
            print(f"   ❌ AI Parsing Error: {e}")

    # Save Results
    with open("scratch/db_vs_new_system_results.json", "w", encoding="utf-8") as f:
        json.dump(comparison_data, f, ensure_ascii=False, indent=2)

    db.close()
    print(f"\n✅ All comparisons complete. Results: scratch/db_vs_new_system_results.json")

if __name__ == "__main__":
    run_comparison()
