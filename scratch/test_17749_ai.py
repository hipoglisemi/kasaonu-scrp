import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign, Card
from src.services.ai_parser_golden import get_golden_parser
import json

with get_db_session() as db:
    c = db.query(Campaign).filter(Campaign.id == 17749).first()
    card = db.query(Card).filter(Card.id == c.card_id).first()
    bank_name = card.name if card else ''
    
    text = c.title + " \n " + (c.description or "")
    
    parser = get_golden_parser()
    
    print(f"Sending to AI with Bank: {bank_name}...")
    ai_data = parser.parse_campaign(raw_html=text, bank_name=bank_name, title=c.title)
    
    print(json.dumps(ai_data.get('cards', []), ensure_ascii=False, indent=2))
