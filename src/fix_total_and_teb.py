import os
import re
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL').replace('postgres://', 'postgresql://')
engine = create_engine(db_url)

def fix_total_energies_cards():
    """Merges cards 147 and 148 into 145 and deletes duplicates."""
    with engine.begin() as conn:
        print("🚀 Starting TotalEnergies Card Merge...")
        
        # 1. Update campaigns belonging to 147 and 148 to 145
        res = conn.execute(text("""
            UPDATE campaigns 
            SET card_id = 145 
            WHERE card_id IN (147, 148)
        """))
        print(f"   ✅ Moved {res.rowcount} campaigns to Master Card (ID: 145)")
        
        # 2. Delete the redundant cards
        res = conn.execute(text("""
            DELETE FROM cards 
            WHERE id IN (147, 148)
        """))
        print(f"   ✅ Deleted {res.rowcount} duplicate cards (IDs: 147, 148)")

        # 3. Delete unapproved duplicates based on tracking_url
        # Keep the oldest one or the approved one
        print("🚀 Cleaning up unapproved TotalEnergies duplicates...")
        res = conn.execute(text("""
            DELETE FROM campaigns 
            WHERE id IN (
                SELECT c.id 
                FROM campaigns c
                JOIN cards card ON c.card_id = card.id
                JOIN banks b ON card.bank_id = b.id
                WHERE b.slug = 'totalenergies' 
                AND c.is_approved = false
                AND EXISTS (
                    SELECT 1 FROM campaigns c2 
                    WHERE c2.tracking_url = c.tracking_url 
                    AND c2.id != c.id
                    AND (c2.is_approved = true OR c2.created_at < c.created_at)
                )
            )
        """))
        print(f"   ✅ Deleted {res.rowcount} unapproved duplicate campaigns")

def cleanup_teb_conditions():
    """Removes 'GEÇERLİ KARTLAR' redundancy from TEB campaigns."""
    with engine.begin() as conn:
        print("\n🚀 Starting TEB Conditions Cleanup...")
        
        # Fetch all TEB campaigns with conditions containing the pattern
        result = conn.execute(text("""
            SELECT c.id, c.conditions 
            FROM campaigns c
            JOIN cards card ON c.card_id = card.id
            JOIN banks b ON card.bank_id = b.id
            WHERE b.slug = 'teb' AND c.conditions IS NOT NULL AND c.conditions LIKE '%GEÇERLİ KARTLAR:%'
        """))
        rows = result.fetchall()
        
        fixed_count = 0
        for row_id, conditions in rows:
            # Remove lines starting with GEÇERLİ KARTLAR
            # Matches "GEÇERLİ KARTLAR: ... \n" or at the end
            new_conditions = re.sub(r'GEÇERLİ KARTLAR:.*?\n', '', conditions, flags=re.IGNORECASE)
            new_conditions = re.sub(r'GEÇERLİ KARTLAR:.*$', '', new_conditions, flags=re.IGNORECASE).strip()
            
            if new_conditions != conditions.strip():
                conn.execute(text("UPDATE campaigns SET conditions = :cond WHERE id = :id"), {
                    "cond": new_conditions,
                    "id": row_id
                })
                fixed_count += 1
        
        print(f"   ✅ Cleaned up 'Geçerli Kartlar' patterns from {fixed_count} TEB campaigns")

if __name__ == "__main__":
    fix_total_energies_cards()
    cleanup_teb_conditions()
    print("\n🏁 Cleanup finished successfully.")
