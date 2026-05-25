import os
import sys
import re
from dotenv import load_dotenv
from sqlalchemy import text

# Setup paths and environment
sys.path.append("/Users/hipoglisemi/Desktop/kartavantaj-scraper")
load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")

from src.database import get_db

def main():
    report_path = "/Users/hipoglisemi/Desktop/kartavantaj/yapi_kredi_precision_mismatch_report.md"
    
    if not os.path.exists(report_path):
        print(f"Error: Mismatch report not found at {report_path}")
        return
        
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    sections = content.split("### 🏷️ Kampanya #")
    reverts = []
    
    for section in sections[1:]:
        lines = section.split("\n")
        if not lines:
            continue
            
        first_line = lines[0]
        m = re.match(r"^(\d+)", first_line)
        if not m:
            continue
            
        camp_id = int(m.group(1))
        
        db_cards_val = None
        for line in lines:
            if "Veri Tabanındaki Mevcut Kartlar" in line:
                match = re.search(r"`([^`]+)`", line)
                if match:
                    db_cards_val = match.group(1).strip()
                    if db_cards_val == "Boş":
                        db_cards_val = None
                break
                
        reverts.append((camp_id, db_cards_val))
        
    total_reverts = len(reverts)
    print(f"Successfully parsed {total_reverts} original card lists from the report for reversion.")
    
    db = next(get_db())
    
    success_count = 0
    try:
        # 1. Revert the eligible_cards values and clear audit flags for modified campaigns
        for camp_id, original_cards in reverts:
            query = text("""
                UPDATE campaigns 
                SET eligible_cards = :eligible_cards, 
                    is_audited = false, 
                    cards_audited_at = NULL,
                    updated_at = NOW()
                WHERE id = :id
            """)
            
            db.execute(query, {
                "eligible_cards": original_cards,
                "id": camp_id
            })
            success_count += 1
            
            if success_count % 20 == 0 or success_count == total_reverts:
                print(f"Reverted {success_count}/{total_reverts} campaigns...")
                
        # 2. Also ensure all Yapı Kredi active campaigns are completely reset in terms of audit flags
        reset_flags_query = text("""
            UPDATE campaigns 
            SET is_audited = false, 
                cards_audited_at = NULL 
            WHERE is_active = true 
              AND card_id IN (SELECT id FROM cards WHERE bank_id = (SELECT id FROM banks WHERE slug = 'yapi-kredi'))
        """)
        db.execute(reset_flags_query)
        
        db.commit()
        print(f"\n🎉 SUCCESS: Successfully reverted all {success_count} Yapı Kredi campaigns in the database back to their original states!")
        print("All audit flags (is_audited, cards_audited_at) for Yapı Kredi have been completely cleared and reset!")
    except Exception as e:
        db.rollback()
        print(f"Error reverting database: {e}")
        
if __name__ == "__main__":
    main()
