import sys
import os
import time
from bs4 import BeautifulSoup
import requests

# Find project root
current_dir = os.path.dirname(os.path.abspath(__file__)) # scripts
project_root = os.path.dirname(current_dir) # /Users/.../kartavantaj-scraper
if project_root not in sys.path:
    sys.path.append(project_root)

# Import models and services
try:
    from src.models import Campaign, CampaignBrand
    from src.services.ai_parser import AIParser
    from src.services.brand_matcher import get_or_create_brands_list
    from src.database import SessionLocal
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def repair_vakifbank_campaigns():
    db = SessionLocal()
    parser = AIParser()
    
    # VakıfBank Card ID is 50 (VakıfWorld)
    # We target active Vakıfbank campaigns.
    campaigns = db.query(Campaign).filter(Campaign.card_id == 50, Campaign.is_active == True).all()
    print(f"🚀 Found {len(campaigns)} VakıfBank campaigns to repair.")
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    success_count = 0
    failed_count = 0
    
    for camp in campaigns:
        print(f"\n🔍 [ID: {camp.id}] Repairing: {camp.title}")
        print(f"   URL: {camp.tracking_url}")
        try:
            # 1. Fetch HTML
            response = session.get(camp.tracking_url, timeout=30)
            if response.status_code != 200:
                print(f"   ❌ HTTP Error {response.status_code}. Skipping.")
                failed_count += 1
                continue
                
            html = response.text
            
            # 2. Isolate core content (Same logic as refined scraper)
            soup = BeautifulSoup(html, 'html.parser')
            detail_container = soup.select_one('.kampanyaDetay')
            if detail_container:
                # Remove Similar Campaigns section
                for other in detail_container.select('.otherCampaigns'):
                    other.decompose()
                processed_html = str(detail_container)
                print("   ✨ Content isolated successfully (.kampanyaDetay found)")
            else:
                processed_html = html
                print("   ⚠️ Warning: .kampanyaDetay not found, using full HTML.")
                
            # 3. Re-parse with AI (FORCE skip cache)
            ai_data = parser.parse_campaign_data(
                raw_text=processed_html,
                bank_name="VakıfBank",
                force=True # MANDATORY: We want a clean parse!
            )
            
            if not ai_data or ai_data.get("_ai_failed"):
                print(f"   ❌ AI Parsing failed for {camp.id}. Skipping.")
                failed_count += 1
                continue
            
            # 4. Success — Update brands
            new_brands = ai_data.get("brands", [])
            print(f"   🎯 AI Found Brands: {new_brands}")
            
            # Remove OLD brands for this campaign
            db.query(CampaignBrand).filter(CampaignBrand.campaign_id == camp.id).delete()
            
            # Link NEW brands
            brand_ids = get_or_create_brands_list(
                db,
                new_brands,
                {}, # No cache for repair session
                camp.sector_id
            )
            for bid in brand_ids:
                db.add(CampaignBrand(campaign_id=camp.id, brand_id=bid))
            
            # 5. Update Marketing Text and Description if needed
            if ai_data.get("ai_marketing_text"):
                camp.ai_marketing_text = ai_data["ai_marketing_text"]
            
            # If description was empty or too short, update it
            if ai_data.get("description") and (not camp.description or len(camp.description) < 50):
                camp.description = ai_data["description"]

            # Save changes
            db.commit()
            print(f"   ✅ Repaired successfully.")
            success_count += 1
            
        except Exception as e:
            print(f"   ❌ Error repairing {camp.id}: {e}")
            db.rollback()
            failed_count += 1
        
        # Rate limiting (Gemini is fast but let's be careful)
        time.sleep(1.5)
        
    print(f"\n🏁 Finished Processing VakıfBank Campaigns.")
    print(f"📊 Summary: {len(campaigns)} total, {success_count} repaired, {failed_count} failed/skipped.")
    db.close()

if __name__ == "__main__":
    repair_vakifbank_campaigns()
