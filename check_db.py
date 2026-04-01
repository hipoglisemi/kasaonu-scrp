import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")
db_url = os.getenv("DATABASE_URL")

engine = create_engine(db_url)
with engine.connect() as conn:
    res = conn.execute(text("SELECT is_approved, count(*) FROM campaigns GROUP BY is_approved;"))
    for row in res:
        print(f"Approval: {row[0]} | Count: {row[1]}")
