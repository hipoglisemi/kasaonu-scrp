import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load env from kartavantaj-scraper
load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")
db_url = os.getenv("DATABASE_URL")

if not db_url:
    print("❌ DATABASE_URL not found!")
    exit(1)

engine = create_engine(db_url)

commands = [
    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE;",
    "UPDATE campaigns SET is_approved = TRUE;",
    "ALTER TABLE campaigns ALTER COLUMN is_approved SET NOT NULL;",
    "ALTER TABLE test_campaigns ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE;",
    "UPDATE test_campaigns SET is_approved = TRUE;",
    "ALTER TABLE test_campaigns ALTER COLUMN is_approved SET NOT NULL;"
]

with engine.connect() as conn:
    for cmd in commands:
        try:
            conn.execute(text(cmd))
            conn.commit()
            print(f"✅ Executed: {cmd[:50]}...")
        except Exception as e:
            print(f"⚠️ Error executing {cmd[:30]}: {e}")

print("🚀 DB Migration finished!")
