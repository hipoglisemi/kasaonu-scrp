
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    print("DATABASE_URL not found")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(text("SELECT id, title, description, conditions, eligible_cards, tracking_url, clean_text FROM campaigns WHERE id = 15380")).fetchone()
    if result:
        print(f"ID: {result.id}")
        print(f"TITLE: {result.title}")
        print(f"DESC: {result.description}")
        print(f"CONDS: {result.conditions}")
        print(f"CARDS: {result.eligible_cards}")
        print(f"URL: {result.tracking_url}")
        print(f"CLEAN_TEXT: {result.clean_text}")
    else:
        print("Campaign not found")
