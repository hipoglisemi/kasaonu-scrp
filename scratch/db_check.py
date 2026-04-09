import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found!")
    exit(1)

# Fix for postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

query = text("""
SELECT c.id, c.title, s.name as sector_name, string_agg(b.name, ', ') as brands
FROM campaigns c
JOIN sectors s ON c.sector_id = s.id 
LEFT JOIN campaign_brands cb ON c.id = cb.campaign_id
LEFT JOIN brands b ON cb.brand_id = b.id
WHERE c.id IN (8049, 8558, 10469, 14546, 8578, 8647)
GROUP BY c.id, c.title, s.name;
""")

with engine.connect() as conn:
    result = conn.execute(query)
    print("\n--- 🔍 CAMPAIGN DATA CHECK ---")
    print(f"{'ID':<6} {'Sector':<25} {'Brands':<30} {'Title'}")
    print("-" * 100)
    for row in result:
        print(f"{row.id:<6} {row.sector_name:<25} {str(row.brands):<30} {row.title[:40]}")
    print("--- END CHECK ---\n")

    # Check ALL sector names to ensure rebranding applied
    result_sectors = conn.execute(text("SELECT id, name, slug FROM sectors;"))
    print("--- 📑 SECTOR LIST ---")
    for row in result_sectors:
        print(f"{row.id}: {row.name} ({row.slug})")
