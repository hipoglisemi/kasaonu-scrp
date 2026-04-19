import os
import sys
import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

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
import requests

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def get_html(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, verify=False)
        return r.text
    except: return None

def run_proof():
    db = Session()
    # Choose older campaigns (rn=20) likely from the old scraper versions
    query = text("""
        WITH RankedCampaigns AS (
            SELECT 
                c.*,
                b.name as bank_name,
                ROW_NUMBER() OVER(PARTITION BY b.id ORDER BY c.created_at DESC) as rn
            FROM campaigns c
            JOIN cards b ON c.card_id = b.id
            WHERE c.tracking_url IS NOT NULL
        )
        SELECT * FROM RankedCampaigns WHERE rn BETWEEN 20 AND 21 LIMIT 12
    """)
    
    results = db.execute(query).mappings().all()
    print(f"🕵️ Proof test starting with {len(results)} OLD campaigns...")
    
    comparison = []
    
    for row in results:
        print(f"🔍 Testing Old DB Record: {row['bank_name']} - {row['title'][:30]}")
        html = get_html(row['tracking_url'])
        if not html: continue
        
        # New parsing
        new = parse_api_campaign(
            title=row['title'],
            short_description=None, # MISSING ARGUMENT FIXED
            content_html=html,
            bank_name=row['bank_name'],
            tracking_url=row['tracking_url'],
            force=True # FORCE TO SHOW FRESH ACCURACY
        )
        
        if new:
            comparison.append({
                "bank": row['bank_name'],
                "title": row['title'],
                "URL": row['tracking_url'],
                "diff": {
                    "cards": {"DB (Eski)": row['eligible_cards'], "Yeni (Modern)": ", ".join(new.get('cards', []))},
                    "reward": {"DB (Eski)": row['reward_text'], "Yeni (Modern)": new.get('reward_text')},
                    "sector": {"DB (Eski)": row['sector_id'], "Yeni (Modern)": new.get('sector')}
                }
            })

    with open("scratch/proof_of_difference.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    
    db.close()
    print("\n✅ Proof generated: scratch/proof_of_difference.json")

if __name__ == "__main__":
    run_proof()
