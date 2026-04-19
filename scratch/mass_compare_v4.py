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

OUTPUT_FILE = "scratch/db_vs_new_system_detailed_analysis.json"

def get_live_html_safe(url):
    """Fetch live HTML using a fresh Playwright session for each URL"""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
            
            content = page.content()
            og_title = None
            try:
                og_title = page.eval_on_selector('meta[property="og:title"]', 'el => el.content')
            except: pass
            
            browser.close()
            return content, og_title
        except Exception as e:
            print(f"   ❌ Browser Error: {e}")
            return None, None

def run_comparison():
    db = Session()
    # Fetch 2 campaigns for EACH card/bank group
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
    print(f"📊 Targets: {len(results)} campaigns (2 per scraper/card).")
    
    final_comparisons = []
    
    # Pre-clear file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

    for i, row in enumerate(results):
        url = row['tracking_url']
        print(f"[{i+1}/{len(results)}] 🔄 Processing: {row['bank_internal_name']} -> {row['title'][:30]}...")
        
        live_html, og_title = get_live_html_safe(url)
        if not live_html:
            continue
            
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
                entry = {
                    "bank": row['bank_internal_name'],
                    "url": url,
                    "db": {
                        "title": row['title'],
                        "cards": row['eligible_cards'],
                        "reward": row['reward_text'],
                        "reward_value": float(row['reward_value']) if row['reward_value'] else 0,
                        "sector": row['sector_name'],
                        "participation": row['participation'],
                        "conditions": row['conditions']
                    },
                    "modern": {
                        "title": new_res.get('short_title') or new_res.get('title'),
                        "cards": ", ".join(new_res.get('cards', [])),
                        "reward": new_res.get('reward_text'),
                        "reward_value": new_res.get('reward_value'),
                        "sector": new_res.get('sector'),
                        "participation": new_res.get('participation'),
                        "conditions": "\n".join(new_res.get('conditions', []))
                    }
                }
                final_comparisons.append(entry)
                # Incremental save
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(final_comparisons, f, ensure_ascii=False, indent=2)
                print(f"   ✅ Compared & Saved.")
        except Exception as e:
            print(f"   ❌ Processing Error: {e}")

    db.close()
    print(f"\n🏆 Task Complete. Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    run_comparison()
