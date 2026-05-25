import os
import sys
import re
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import text

# Setup paths and environment
sys.path.append("/Users/hipoglisemi/Desktop/kartavantaj-scraper")
load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")

from src.database import get_db

def main():
    report_path = "/Users/hipoglisemi/Desktop/kartavantaj/yapi_kredi_world_precision_mismatch_report.md"
    
    if not os.path.exists(report_path):
        print(f"Error: Mismatch report not found at {report_path}")
        return
        
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    sections = content.split("### 🏷️ Kampanya #")
    updates = []
    
    for section in sections[1:]:
        lines = section.split("\n")
        if not lines:
            continue
            
        first_line = lines[0]
        m = re.match(r"^(\d+)", first_line)
        if not m:
            continue
            
        camp_id = int(m.group(1))
        
        proposed_str = None
        for line in lines:
            if "AI Önerilen Sıralı Liste" in line:
                match = re.search(r"`([^`]+)`", line)
                if match:
                    proposed_str = match.group(1).strip()
                    if proposed_str == "Boş":
                        proposed_str = ""
                break
                
        if proposed_str is not None:
            updates.append((camp_id, proposed_str))
            
    total_parsed = len(updates)
    print(f"Successfully parsed {total_parsed} World campaign updates from the report.")
    
    if total_parsed == 0:
        print("No updates to apply.")
        return
        
    print(f"Sample update: Campaign #{updates[0][0]} -> '{updates[0][1]}'")
    
    db = next(get_db())
    
    success_count = 0
    try:
        for camp_id, eligible_cards in updates:
            # We execute a raw SQL update to ensure columns are written directly and fast
            query = text("""
                UPDATE campaigns 
                SET eligible_cards = :eligible_cards, 
                    cards_audited_at = :now,
                    updated_at = :now
                WHERE id = :id
            """)
            
            db.execute(query, {
                "eligible_cards": eligible_cards,
                "now": datetime.utcnow(),
                "id": camp_id
            })
            success_count += 1
            
            if success_count % 10 == 0 or success_count == total_parsed:
                print(f"Applied {success_count}/{total_parsed} database updates...")
                
        db.commit()
        print(f"\n🎉 SUCCESS: Successfully updated {success_count} World campaigns in the database!")
        print("All audited World campaigns have been updated with verified card lists and cards_audited_at timestamp!")
    except Exception as e:
        db.rollback()
        print(f"Error applying database updates: {e}")
        
if __name__ == "__main__":
    main()
