import os
import sys
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db_session
from src.models import ScraperLog

def inspect_turktelekom_logs():
    with get_db_session() as db:
        latest_log = db.query(ScraperLog).filter(
            ScraperLog.scraper_name == "turktelekom"
        ).order_by(ScraperLog.created_at.desc()).first()
        
        if not latest_log:
            print("❌ No Turk Telekom logs found!")
            return
            
        print(f"==================== TURK TELEKOM LATEST LOG ====================")
        print(f"Created At:    {latest_log.created_at}")
        print(f"Status:        {latest_log.status}")
        print(f"Total Found:   {latest_log.total_found}")
        print(f"Total Saved:   {latest_log.total_saved}")
        print(f"Total Skipped: {latest_log.total_skipped}")
        print(f"Total Failed:  {latest_log.total_failed}")
        print(f"Total Revived: {latest_log.total_revived}")
        print("-" * 80)
        
        if latest_log.error_log:
            errors = latest_log.error_log.get("errors", [])
            print(f"🚨 Found {len(errors)} error records in the log:")
            # Group errors by message to see the common causes
            summary = {}
            for err in errors:
                url = err.get("url", "unknown")
                msg = err.get("error", "unknown")
                summary[msg] = summary.get(msg, [])
                summary[msg].append(url)
                
            for msg, urls in summary.items():
                print(f"\n🔴 Error: {msg}")
                print(f"   Count: {len(urls)}")
                print(f"   Sample URLs (up to 5):")
                for u in urls[:5]:
                    print(f"   - {u}")
        else:
            print("ℹ️ No error_log JSON present in the DB row.")
        print("=================================================================")

if __name__ == "__main__":
    inspect_turktelekom_logs()
