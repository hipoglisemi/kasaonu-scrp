import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE scraper_logs ADD COLUMN IF NOT EXISTS total_revived INTEGER DEFAULT 0"))
        conn.commit()
        print("✅ total_revived column added to scraper_logs table successfully!")
    except Exception as e:
        print(f"❌ Error adding column: {e}")
