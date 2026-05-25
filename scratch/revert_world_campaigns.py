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
    report_path = "/Users/hipoglisemi/Desktop/kartavantaj/yapi_kredi_world_precision_mismatch_report.md"
    
    if not os.path.exists(report_path):
        print(f"Error: Mismatch report not found at {report_path}")
        return
        
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    sections = content.split("### 🏷️ Kampanya #")
    revert_data = []
    
    for section in sections[1:]:
        lines = section.split("\n")
        if not lines:
            continue
            
        first_line = lines[0]
        m = re.match(r"^(\d+)", first_line)
        if not m:
            continue
            
        camp_id = int(m.group(1))
        
        orig_str = None
        for line in lines:
            if "Veri Tabanındaki Mevcut Kartlar" in line:
                match = re.search(r"`([^`]+)`", line)
                if match:
                    orig_str = match.group(1).strip()
                    if orig_str == "Boş":
                        orig_str = ""
                break
                
        if orig_str is not None:
            revert_data.append((camp_id, orig_str))
            
    total_parsed = len(revert_data)
    print(f"Parsed {total_parsed} campaign revert values from the report.")
    
    if total_parsed == 0:
        print("No campaigns to revert.")
        return
        
    db = next(get_db())
    
    success_count = 0
    try:
        for camp_id, orig_cards in revert_data:
            query = text("""
                UPDATE campaigns 
                SET eligible_cards = :orig_cards, 
                    cards_audited_at = NULL,
                    updated_at = NOW()
                WHERE id = :id
            """)
            
            db.execute(query, {
                "orig_cards": orig_cards if orig_cards != "" else None,
                "id": camp_id
            })
            success_count += 1
            
        db.commit()
        print(f"🎉 SUCCESS: Fully reverted {success_count} campaigns back to their original database states!")
    except Exception as e:
        db.rollback()
        print(f"Error applying revert updates: {e}")

if __name__ == "__main__":
    main()
