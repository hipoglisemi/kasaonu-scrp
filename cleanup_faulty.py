import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")
db_url = os.getenv("DATABASE_URL")

engine = create_engine(db_url)
with engine.begin() as conn:
    res = conn.execute(text("DELETE FROM campaigns WHERE title ILIKE '%bulunamadı%' OR title ILIKE '%sayfa bulunamadı%';"))
    print(f"✅ Deleted {res.rowcount} faulty campaign records.")
