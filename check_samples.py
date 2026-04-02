import os
import sys
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv(os.path.join(project_root, ".env"))

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not found")
    sys.exit(1)

# Strip quotes if present
DATABASE_URL = DATABASE_URL.strip("'").strip('"')

engine = create_engine(DATABASE_URL)

def check_campaigns(card_name_filter):
    query = text("""
        SELECT c.id, c.title, c.eligible_cards, c.conditions, c.clean_text, cr.name as card_name
        FROM campaigns c
        JOIN cards cr ON c.card_id = cr.id
        WHERE cr.name ILIKE :card_name
        ORDER BY c.id DESC
        LIMIT 3
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"card_name": f"%{card_name_filter}%"})
        print(f"\n--- Checking campaigns for: {card_name_filter} ---")
        for row in result:
            print(f"ID: {row.id}")
            print(f"Title: {row.title}")
            print(f"Eligible Cards (stored): {row.eligible_cards}")
            print(f"Conditions (stored): {row.conditions[:200]}...")
            print(f"Clean Text (sample): {row.clean_text[:500] if row.clean_text else 'N/A'}...")
            print("-" * 30)

cards_to_check = [
    "Paraf", "Vodafone", "Türk Telekom", "Adios", "Crystal", "Happy", "Play", "Sağlam", "World"
]

for card in cards_to_check:
    check_campaigns(card)
