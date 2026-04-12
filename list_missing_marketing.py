import os
import json
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print("Error: DATABASE_URL not found")
    sys.exit(1)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
CHECKPOINT_FILE = "marketing_update_checkpoint.json"

def main():
    processed_ids = []
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                processed_ids = json.load(f).get("processed_ids", [])
        except:
            pass

    with engine.connect() as conn:
        query = text("""
            SELECT id, title, description, reward_text 
            FROM campaigns 
            WHERE is_active = true AND is_approved = true AND id < 14766
            ORDER BY id DESC
        """)
        rows = conn.execute(query).fetchall()
        
        todo = [
            {
                "id": r.id, 
                "title": r.title, 
                "description": r.description, 
                "reward_text": r.reward_text
            } 
            for r in rows if r.id not in processed_ids
        ]
        
        print(json.dumps(todo, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
