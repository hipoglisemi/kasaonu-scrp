import os
import sys
import json
from sqlalchemy import create_engine, text

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

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def run_minimal_check():
    query = text("""
        SELECT 
            c.id, 
            c.title, 
            c.tracking_url, 
            b.name as bank_name 
        FROM campaigns c 
        JOIN cards b ON c.card_id = b.id 
        WHERE c.tracking_url IS NOT NULL 
        LIMIT 5
    """)
    
    with engine.connect() as conn:
        results = conn.execute(query).mappings().all()
        print(f"DEBUG: Found {len(results)} rows.")
        for r in results:
            print(f"- Bank: {r['bank_name']} | Title: {r['title']} | URL: {r['tracking_url']}")

if __name__ == "__main__":
    run_minimal_check()
