import os
import sys
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

def debug_db():
    with engine.connect() as conn:
        # Total campaigns
        total = conn.execute(text("SELECT count(*) FROM campaigns")).scalar()
        print(f"Total Campaigns: {total}")
        
        # Campaigns with tracking_url
        with_url = conn.execute(text("SELECT count(*) FROM campaigns WHERE tracking_url IS NOT NULL")).scalar()
        print(f"Campaigns with URL: {with_url}")
        
        # Sample per bank
        per_bank = conn.execute(text("""
            SELECT b.name, count(c.id) 
            FROM cards b 
            LEFT JOIN campaigns c ON c.card_id = b.id 
            GROUP BY b.name 
            ORDER BY count(c.id) DESC 
            LIMIT 10
        """)).all()
        print("\nTop 10 Banks by Campaign Count:")
        for row in per_bank:
            print(f"- {row[0]}: {row[1]}")

if __name__ == "__main__":
    debug_db()
