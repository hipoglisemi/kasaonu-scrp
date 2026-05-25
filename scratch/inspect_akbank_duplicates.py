import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db_session
from src.models import Campaign, Card, Bank

def inspect_akbank_duplicates():
    with get_db_session() as db:
        # Find Akbank ID
        akbank = db.query(Bank).filter(Bank.slug == 'akbank').first()
        if not akbank:
            print("❌ Akbank not found!")
            return
            
        akbank_card_ids = [c.id for c in db.query(Card).filter(Card.bank_id == akbank.id).all()]
        
        # Query active campaigns
        campaigns = db.query(Campaign).filter(
            Campaign.card_id.in_(akbank_card_ids),
            Campaign.is_active == True
        ).all()
        
        print(f"🏦 Total active Akbank campaigns: {len(campaigns)}")
        
        # Find duplicates by Title + Card ID
        title_groups = {}
        url_groups = {}
        
        for c in campaigns:
            title_key = f"{c.title.strip().lower()}-{c.card_id}"
            if title_key not in title_groups:
                title_groups[title_key] = []
            title_groups[title_key].append(c)
            
            if c.tracking_url:
                url_key = c.tracking_url
                if url_key not in url_groups:
                    url_groups[url_key] = []
                url_groups[url_key].append(c)
                
        # Print title duplicates
        print("\n🚨 --- DUPLICATES BY TITLE & CARD ---")
        title_dup_count = 0
        for key, group in title_groups.items():
            if len(group) > 1:
                title_dup_count += 1
                card_name = db.query(Card).filter(Card.id == group[0].card_id).first().name
                print(f"🔑 Key: {key} | Card: {card_name}")
                for idx, c in enumerate(group):
                    print(f"   [{idx+1}] ID: {c.id} | Slug: {c.slug} | Created: {c.created_at} | URL: {c.tracking_url}")
                print("-" * 80)
                
        # Print URL duplicates
        print("\n🚨 --- DUPLICATES BY TRACKING URL ---")
        url_dup_count = 0
        for key, group in url_groups.items():
            if len(group) > 1:
                url_dup_count += 1
                print(f"🔑 URL: {key}")
                for idx, c in enumerate(group):
                    card_name = db.query(Card).filter(Card.id == c.card_id).first().name
                    print(f"   [{idx+1}] ID: {c.id} | Title: {c.title} | Card: {card_name} | Created: {c.created_at}")
                print("-" * 80)
                
        print(f"🏁 Summary: {title_dup_count} title-card dup groups, {url_dup_count} URL dup groups.")

if __name__ == "__main__":
    inspect_akbank_duplicates()
