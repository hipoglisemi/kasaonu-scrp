import re
import sys
from src.database import get_db
from src.models import Campaign

def capitalize_first_letter(text: str) -> str:
    if not text:
        return ""
    # Ensure first character is upper case (handling Turkish characters)
    first_char = text[0]
    if first_char == 'ı':
        first_char = 'I'
    elif first_char == 'i':
        first_char = 'İ'
    else:
        first_char = first_char.upper()
    return first_char + text[1:]

def main():
    report_path = "/Users/hipoglisemi/Desktop/kartavantaj/yapi_kredi_world_participation_mismatch_report.md"
    
    print("Reading mismatch report...")
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    matches = re.findall(r"### 🏷️ Kampanya #(\d+).*?AI Önerilen Gerçek Katılım Şekli:\*\* `🔴 (.+?)`", content, re.DOTALL)
    print(f"Parsed {len(matches)} mismatch records from report.")
    
    if not matches:
        print("No matches found to update.")
        return
        
    db = next(get_db())
    updated_count = 0
    
    for camp_id, proposed_val in matches:
        camp_id = int(camp_id)
        proposed_val = proposed_val.strip()
        
        # Standardize capitalization
        proposed_val = capitalize_first_letter(proposed_val)
        
        # Fetch campaign from DB
        camp = db.query(Campaign).filter(Campaign.id == camp_id).first()
        if camp:
            print(f"Updating Campaign #{camp_id}:")
            print(f"  Old: {camp.participation}")
            print(f"  New: {proposed_val}")
            
            camp.participation = proposed_val
            updated_count += 1
            
    if updated_count > 0:
        db.commit()
        print(f"\nSuccessfully updated {updated_count} campaigns in the database!")
    else:
        print("\nNo campaigns were updated.")

if __name__ == "__main__":
    main()
