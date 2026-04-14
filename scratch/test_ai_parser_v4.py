import os
import sys
import json
from datetime import datetime

# Adjust path to import src
sys.path.append(os.getcwd())

from src.database import get_db_session
from src.models import Campaign
from src.services.ai_parser import AIParser

def test_us_polo():
    print("--- 🧪 AIParser V4 Hardening Test (ID 15489) ---")
    parser = AIParser()
    
    with get_db_session() as db:
        c = db.query(Campaign).get(15489)
        if not c:
            print("Error: Campaign 15489 not found.")
            return

        # Note: We are testing how the parser handles the RAW text now.
        # The illusion brands were previously accepted because the footer wasn't truncated
        # and validation was weak.
        
        # In a real run, the scraper sends the RAW HTML or text.
        # We will use the c.clean_text (which contains the footer in the DB) to test truncation logic.
        
        print(f"Original Brands in DB: {[cb.brand.name for cb in c.brands]}")
        
        # Force re-parse
        # We pass the clean_text which still has 'İLGİNİZİ ÇEKEBİLECEK DİĞER KAMPANYALAR' in it.
        result = parser.parse_campaign_data(
            raw_text=c.clean_text,
            title=c.title,
            bank_name=c.card.bank.name if c.card and c.card.bank else "Garanti",
            force=True
        )
        
        print("\n--- 🏁 PARSE RESULT ---")
        print(f"Detected Brands: {result.get('brands')}")
        
        illusions = ["Beymen", "Avva", "Jumbo"]
        found_illusions = [b for b in result.get('brands', []) if b in illusions]
        
        if not found_illusions:
            print("\n✅ SUCCESS: Illusion brands were correctly ignored!")
        else:
            print(f"\n❌ FAILURE: Some illusion brands still found: {found_illusions}")

if __name__ == "__main__":
    test_us_polo()
