import sys
import json
import argparse
import os

# Ensure the root of scraper is in sys.path so we can import src.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from src.services.ai_parser import AIParser
from dotenv import load_dotenv

load_dotenv()
# Fallback hardcoded for safety if .env misses it locally in this context
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def main():
    parser = argparse.ArgumentParser(description="CLI Bridge for Next.js AI Repair")
    parser.add_argument('--id', type=int, required=True, help="Campaign ID to repair")
    args = parser.parse_args()

    try:
        with engine.connect() as conn:
            row = conn.execute(text('SELECT id, clean_text, title, tracking_url FROM campaigns WHERE id = :id'), {'id': args.id}).fetchone()
            if not row:
                raise ValueError(f"Campaign {args.id} not found in database.")
            
            clean_text = row.clean_text or ""
            title = row.title or "Başlık Yok"
            
            # Since tracking_url is available, let's try to extract bank name from it, or just use Genel
            # Actually, let's join with banks table if there is a bank_id.
            row_with_bank = conn.execute(text('''
                SELECT c.id, c.clean_text, c.title, b.name as bank_name 
                FROM campaigns c 
                LEFT JOIN cards card ON c.card_id = card.id
                LEFT JOIN banks b ON card.bank_id = b.id
                WHERE c.id = :id
            '''), {'id': args.id}).fetchone()

            bank_name = "Genel"
            if row_with_bank and row_with_bank.bank_name:
                bank_name = row_with_bank.bank_name

            ai_parser = AIParser()
            res = ai_parser.parse_campaign_data(
                raw_text=clean_text,
                title=title,
                bank_name=bank_name,
                force=True, # bypass cache
                campaign_id=args.id
            )

            print("\n---AIPARSER_JSON_START---")
            print(json.dumps(res, ensure_ascii=False))
            print("---AIPARSER_JSON_END---")

    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print("\n---AIPARSER_JSON_START---")
        print(json.dumps({"error": str(e)}))
        print("---AIPARSER_JSON_END---")
        sys.exit(1)

if __name__ == '__main__':
    main()
