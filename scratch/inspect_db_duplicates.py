import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db_session
from src.models import Campaign

def inspect_exact_duplicates():
    pairs = [
        (19205, 17754),
        (19013, 11049),
        (18985, 17760)
    ]
    
    with get_db_session() as db:
        for id1, id2 in pairs:
            c1 = db.query(Campaign).filter(Campaign.id == id1).first()
            c2 = db.query(Campaign).filter(Campaign.id == id2).first()
            
            print(f"==================== COMPARE ID {id1} VS ID {id2} ====================")
            if not c1 or not c2:
                print("❌ One of the campaigns not found!")
                continue
                
            print(f"👉 Campaign 1 (ID: {c1.id})")
            print(f"   Title:       '{c1.title}'")
            print(f"   Slug:        '{c1.slug}'")
            print(f"   Card ID:     {c1.card_id}")
            print(f"   TrackingURL: '{c1.tracking_url}'")
            print(f"   Created At:  {c1.created_at}")
            print(f"   Is Active:   {c1.is_active}")
            print(f"   Is Approved: {c1.is_approved}")
            
            print(f"\n👉 Campaign 2 (ID: {c2.id})")
            print(f"   Title:       '{c2.title}'")
            print(f"   Slug:        '{c2.slug}'")
            print(f"   Card ID:     {c2.card_id}")
            print(f"   TrackingURL: '{c2.tracking_url}'")
            print(f"   Created At:  {c2.created_at}")
            print(f"   Is Active:   {c2.is_active}")
            print(f"   Is Approved: {c2.is_approved}")
            print("-" * 100)

if __name__ == "__main__":
    inspect_exact_duplicates()
