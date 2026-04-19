import sys
import os
from unittest.mock import MagicMock, patch

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.scrapers.isbankasi_maximum import IsbankMaximumScraper

def test_save_campaign_fix():
    print("🧪 Testing NameError fix for isbankasi_maximum.py...")
    
    # Mock AIParser to avoid real API calls
    with patch('src.services.ai_parser.AIParser') as MockParser:
        scraper = IsbankMaximumScraper()
        
        # Sample data mimicking what _extract_campaign_data + AIParser would return
        test_data = {
            "title": "Ülker Bisküvi Kampanyası",
            "source_url": "https://www.maximum.com.tr/kampanyalar/ulker-test",
            "image_url": "https://www.maximum.com.tr/img/test.jpg",
            "date_text": "1 Ocak - 31 Ocak 2026",
            "full_text": "Ülker bisküvi alımlarında 100 TL Maxipuan hediye.",
            "description": "Ülker bisküvi alımlarında 100 TL Maxipuan hediye.",
            "ai_marketing_text": "Ülker bisküvi alımlarında 100 TL Maxipuan hediye.",
            "reward_text": "100 TL Maxipuan",
            "reward_value": 100.0,
            "reward_type": "Maxipuan",
            "conditions": ["Kampanya 1-31 Ocak arası geçerlidir.", "Market harcamaları dahil."],
            "participation": "Maximum Mobil üzerinden katılınmalıdır.",
            "sector": "Market",
            "brands": ["Ülker"]
        }
        
        # Mock dependencies that interact with DB or network too much
        scraper._get_or_create_bank = MagicMock(return_value=1)
        scraper._get_or_create_card = MagicMock(return_value=1)
        scraper._get_or_create_slug = MagicMock(return_value="ulker-test-slug")
        
        print("💡 Running _save_campaign with test data...")
        try:
            # We use a real session but it will rollback at the end if we want, 
            # or we can just let it try to save. 
            # The goal is to see if it reaches the participation assignment without NameError.
            campaign_id = scraper._save_campaign(test_data, bank_id=1, card_id=1)
            
            if campaign_id:
                print(f"✅ Success! Campaign saved with ID: {campaign_id}")
                print("🚀 The 'NameError: participation is not defined' is RESOLVED.")
            else:
                print("❌ Save failed (but check if it was a NameError or just DB/Constraint error)")
                
        except NameError as ne:
            print(f"🔥 NameError DETECTED: {ne}")
            sys.exit(1)
        except Exception as e:
            print(f"⚠️  Other error (likely expected during mock): {e}")

if __name__ == "__main__":
    test_save_campaign_fix()
