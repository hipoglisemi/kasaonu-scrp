import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Add current dir to path for imports
sys.path.append(os.getcwd())
from src.models import Campaign, Brand, CampaignBrand, Sector
from src.services.point_blank_matcher import PointBlankMatcher

load_dotenv()

def repair_campaigns():
    # TEST_MODE=0 to actually save changes, otherwise just simulation
    TEST_MODE = os.getenv('TEST_MODE', '1') == '1'
    
    engine = create_engine(os.getenv('DATABASE_URL'))
    Session = sessionmaker(bind=engine)
    session = Session()

    matcher = PointBlankMatcher(session)
    
    # Get total count first for progress bar logic
    total_campaigns = session.query(Campaign.id).count()
    all_campaign_ids = [c.id for c in session.query(Campaign.id).order_by(Campaign.id).all()]
    
    print(f"{'🧪 TEST MODE (DRY RUN)' if TEST_MODE else '🚀 PRODUCTION MODE (LIVE UPDATES)'}")
    print(f"🛠️ Starting Bulk Repair for {len(all_campaign_ids)} campaigns using Point-Blank Engine...")
    
    repaired_count = 0
    brand_updates = 0
    sector_updates = 0
    processed_count = 0
    
    # Process in batches of 100 IDs
    BATCH_SIZE = 100
    try:
        for i in range(0, len(all_campaign_ids), BATCH_SIZE):
            batch_ids = all_campaign_ids[i:i+BATCH_SIZE]
            
            # Fetch objects for this batch
            campaigns = session.query(Campaign).filter(Campaign.id.in_(batch_ids)).all()
            
            for campaign in campaigns:
                processed_count += 1
                
                try:
                    # Match using Point-Blank (Now returns a List)
                    pb_matches = matcher.match_campaign(campaign.title, campaign.description or "")
                    
                    is_changed = False
                    verified_brand_names = [m["brand"] for m in pb_matches if m.get("brand")]
                    
                    with session.no_autoflush:
                        # 1. Sector Update (Use the first match's sector as primary)
                        if pb_matches and pb_matches[0].get("sector"):
                            target_sector = session.query(Sector).filter(Sector.slug == pb_matches[0]["sector"]).first()
                            if target_sector and campaign.sector_id != target_sector.id:
                                campaign.sector_id = target_sector.id
                                sector_updates += 1
                                is_changed = True
                        
                        # 2. Brand Updates (Multi-Brand & Brand Protector Logic)
                        current_links = session.query(CampaignBrand).filter(CampaignBrand.campaign_id == campaign.id).all()
                        current_brand_ids = [l.brand_id for l in current_links]
                        
                        # A. Add Verified Point-Blank Brands
                        for b_name in verified_brand_names:
                            target_brand = session.query(Brand).filter(Brand.name == b_name).first()
                            if target_brand and target_brand.id not in current_brand_ids:
                                new_link = CampaignBrand(campaign_id=campaign.id, brand_id=target_brand.id)
                                session.add(new_link)
                                brand_updates += 1
                                is_changed = True

                        # B. Remove Hallucinated Brands (Bank/Card names)
                        # We only remove if Point-Blank doesn't explicitly confirm it as a brand
                        BLACKLIST = ["Akbank", "Axess", "Wings", "Garanti", "Bonus", "Maximum", "Yapı Kredi", "World", 
                                     "İş Bankası", "Ziraat", "Halkbank", "Paraf", "Vakıfbank", "QNB", "Finansbank", 
                                     "Enpara", "TEB", "Denizbank", "Kuveyt Türk", "Sağlam Kart", "Banka"]
                        
                        for link in current_links:
                            brand = session.query(Brand).get(link.brand_id)
                            if brand:
                                # If brand name is in blacklist AND not confirmed by Point-Blank rules
                                is_bad = any(bad.lower() in brand.name.lower() for bad in BLACKLIST)
                                if is_bad and brand.name not in verified_brand_names:
                                    session.delete(link)
                                    brand_updates += 1
                                    is_changed = True

                        if is_changed:
                            repaired_count += 1
                
                except Exception as inner_e:
                    session.rollback()
                    print(f"   ⚠️ Kampanya {campaign.id} işlenirken hata oluştu: {inner_e}")
                    continue
            
            # Commit after each batch in Production
            if not TEST_MODE:
                try:
                    session.commit()
                    print(f"   🚀 Grup İşlendi: {processed_count}/{len(all_campaign_ids)} ({(processed_count/len(all_campaign_ids))*100:.1f}%)")
                except Exception as commit_e:
                    session.rollback()
                    print(f"   ❌ Grup kaydedilirken hata: {commit_e}")
            else:
                if processed_count % 100 == 0 or processed_count == len(all_campaign_ids):
                    print(f"   📊 Deneme Sürüşü İlerleme: {processed_count}/{len(all_campaign_ids)} ({(processed_count/len(all_campaign_ids))*100:.1f}%)")

        if not TEST_MODE:
            print(f"🏆 Üretim ortamı onarımı tamamlandı!")
        else:
            print(f"🧪 Deneme sürüşü (Dry Run) tamamlandı! DB üzerinde değişiklik yapılmadı.")

        print(f"   - Total Campaigns Processed: {processed_count}")
        print(f"   - Campaigns Needing Repair: {repaired_count}")
        print(f"   - Brand Links Adjusted: {brand_updates}")
        print(f"   - Sectors Realigned: {sector_updates}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Operation failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    repair_campaigns()
