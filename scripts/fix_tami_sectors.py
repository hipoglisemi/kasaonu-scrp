
import os
import sys
import time
import logging

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Campaign, Bank, Sector
from src.database import get_db_session
from src.services.ai_parser import parse_api_campaign

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_tami_sectors():
    print("🚀 Starting Tami Sector Fix Script...")
    
    with get_db_session() as db:
        # Find Tami bank
        tami_bank = db.query(Bank).filter(Bank.slug == "tami").first()
        if not tami_bank:
            print("❌ Tami bank not found in database.")
            return

        # Find Tami cards
        tami_cards = db.query(Card).filter(Card.bank_id == tami_bank.id).all()
        tami_card_ids = [c.id for c in tami_cards]
        
        if not tami_card_ids:
            # Fallback: find by card slug if card table is used differently
            tami_card = db.query(Card).filter(Card.slug == "tami-kart").first()
            if tami_card:
                tami_card_ids = [tami_card.id]
            else:
                print("❌ Tami cards not found.")
                return

        # Query Tami campaigns
        # We target all active Tami campaigns to ensure sectors are correct based on new rules
        campaigns = db.query(Campaign).filter(
            Campaign.card_id.in_(tami_card_ids),
            Campaign.is_active == True
        ).all()

        print(f"📊 Found {len(campaigns)} active Tami campaigns to check.")

        fixed_count = 0
        for i, c in enumerate(campaigns, 1):
            print(f"[{i}/{len(campaigns)}] Checking: {c.title}")
            
            # Get content from clean_text or description/conditions
            content = c.clean_text or f"{c.description}\n{c.conditions}"
            
            if not content or len(content) < 20:
                print(f"   ⚠️ Skipping: Minimal content available.")
                continue

            try:
                print(f"   🤖 Re-parsing with Gemini...")
                # Force re-parse using the updated AI rules in ai_parser.py
                ai_data = parse_api_campaign(
                    title=c.title,
                    short_description=c.title,
                    content_html=content,
                    bank_name="Tami",
                    tracking_url=c.tracking_url,
                    force=True # Force AI call to use new rules
                )

                if not ai_data:
                    print("   ❌ AI parsing failed.")
                    continue

                # Check sector
                sector_slug = ai_data.get("sector", "diger")
                if isinstance(sector_slug, list):
                    sector_slug = sector_slug[0] if sector_slug else "diger"
                
                sector = db.query(Sector).filter(Sector.slug == sector_slug).first()
                if not sector:
                    sector = db.query(Sector).filter(Sector.slug == "diger").first()

                updated = False
                if sector and c.sector_id != sector.id:
                    print(f"   ✨ Updating Sector: {c.sector.name if c.sector else 'None'} -> {sector.name}")
                    c.sector_id = sector.id
                    updated = True
                
                # Also update brands if they changed
                if ai_data.get("brands"):
                    from src.models import Brand, CampaignBrand
                    import re
                    
                    # Clear existing brands for this campaign if we're re-fixing
                    db.query(CampaignBrand).filter(CampaignBrand.campaign_id == c.id).delete()
                    
                    for b_name in ai_data["brands"]:
                        b_slug = re.sub(r'[^a-z0-9]+', '-', b_name.lower()).strip('-')
                        brand = db.query(Brand).filter((Brand.slug == b_slug) | (Brand.name.ilike(b_name))).first()
                        if not brand:
                            brand = Brand(name=b_name, slug=b_slug, is_active=True)
                            db.add(brand)
                            db.commit()
                            db.refresh(brand)
                        
                        cb = CampaignBrand(campaign_id=c.id, brand_id=brand.id)
                        db.add(cb)
                    updated = True

                if updated:
                    db.commit()
                    fixed_count += 1
                    print("   ✅ Fixed!")
                else:
                    print("   ℹ️ No changes needed.")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                db.rollback()

            # Rate limiting
            time.sleep(2)

    print(f"🏁 Tami Sector Fix finished. Updated {fixed_count} campaigns.")

if __name__ == "__main__":
    from src.models import Card # Import here to be safe
    fix_tami_sectors()
