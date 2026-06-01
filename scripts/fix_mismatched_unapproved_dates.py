import os
import sys
import re
from datetime import datetime, date

# Setup path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Campaign

def fix_unapproved_mismatched_dates():
    print("⏳ Starting fix for mismatched unapproved campaign dates...")
    db = get_db_session()
    
    # 1. Fetch unapproved campaigns updated today
    camps = db.query(Campaign).filter(
        Campaign.is_approved == False,
        Campaign.updated_at >= '2026-06-01 00:00:00'
    ).all()
    
    print(f"🔍 Scanned {len(camps)} unapproved campaigns updated today.")
    
    months = {
        'haziran': 6,
        'june': 6
    }
    
    fixed_count = 0
    for c in camps:
        text = (c.clean_text or '').lower()
        title = c.title.lower()
        combined_text = f"{title}\n{text}"
        
        # We only check if the current end_date is in July or August (month 7 or 8)
        if not c.end_date or c.end_date.month not in [7, 8]:
            continue
            
        # Look for explicit June dates in clean text
        # Pattern 1: DD.06.2026 or DD-06-2026
        dd_mm_yyyy = re.findall(r'(\d{1,2})[./-](06|6)[./-](2026|26)?', combined_text)
        
        # Pattern 2: DD haziran or DD june
        word_dates = re.findall(r'(\d{1,2})\s+(haziran|june)', combined_text)
        
        # Pattern 3: haziran sonuna kadar or haziran ayı boyunca
        has_june_end = "haziran sonu" in combined_text or "haziran sonuna" in combined_text or "haziran ayı boyunca" in combined_text or "haziran boyunca" in combined_text
        
        inferred_day = None
        
        # Determine the correct day
        if dd_mm_yyyy:
            inferred_day = int(dd_mm_yyyy[0][0])
        elif word_dates:
            inferred_day = int(word_dates[0][0])
        elif has_june_end:
            inferred_day = 30
            
        # Safety check: day must be valid for June (1 to 30)
        if inferred_day and 1 <= inferred_day <= 30:
            target_date = date(2026, 6, inferred_day)
            
            # If the current date is July/August but we found a valid June date
            if c.end_date != target_date:
                print(f"   ✨ Fix ID: #{c.id} | {c.title[:45]}...")
                print(f"      Old End Date: {c.end_date} ➔ New End Date: {target_date}")
                
                c.end_date = target_date
                c.date_extended = True
                c.updated_at = datetime.now()
                fixed_count += 1
                
    if fixed_count > 0:
        db.commit()
        print(f"✅ Successfully corrected {fixed_count} unapproved campaigns back to June!")
    else:
        print("ℹ️ No unapproved campaigns needed correction.")
        
    db.close()

if __name__ == "__main__":
    fix_unapproved_mismatched_dates()
