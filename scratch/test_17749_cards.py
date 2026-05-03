import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign
from src.services.ai_parser_golden import get_golden_parser

with get_db_session() as db:
    c = db.query(Campaign).filter(Campaign.id == 17749).first()
    text = c.title + " " + (c.description or "")
    
    parser = get_golden_parser()
    ai_cards = ["Axess Business"]
    
    validated = parser.card_validator.validate(ai_cards, text, "akbank")
    print(f"Validated from AI 'Axess Business': {validated}")
    
    validated_empty = parser.card_validator.validate([], text, "akbank")
    print(f"Validated from Empty: {validated_empty}")
