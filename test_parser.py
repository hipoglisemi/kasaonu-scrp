import sys
import os
import json

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.services.ai_parser_golden import AIParserGolden
from src.database import get_db_session
from src.models import Campaign

with get_db_session() as db:
    c = db.query(Campaign).filter(Campaign.id == 17215).first()
    title = c.title
    text = c.clean_text

parser = AIParserGolden()
bank_name = "Garanti BBVA"
bank_key = parser._resolve_bank_key(bank_name)
print(f"Bank Key: {bank_key}")

brand_norm = parser._tr_lower("Türk Hava Yolları")
from src.services.ai_parser_golden import BANK_SELF_NAMES
self_names = {parser._tr_lower(n) for n in BANK_SELF_NAMES[bank_key]}
print(f"Self names for '{bank_key}': {self_names}")
print(f"Brand norm '{brand_norm}' in self names? {brand_norm in self_names}")

# Let's see what PBE returns
from src.services.point_blank_matcher import get_point_blank_matcher
pb_matcher = get_point_blank_matcher(db)
pb_matches = pb_matcher.match_campaign(title, text or "")
print(f"PBE Matches: {pb_matches}")
