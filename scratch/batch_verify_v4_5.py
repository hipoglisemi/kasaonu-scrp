import os
import sys
import json
import re

# Adjust path to import src
sys.path.append(os.getcwd())

from src.database import get_db_session
from src.models import Campaign
from src.services.ai_parser import AIParser

def verify_batch():
    print("--- 🔬 AIParser V4.5 Logic Logic Verification (Batch 30) ---")
    parser = AIParser()
    
    # Load the 30 IDs from the latest report
    report_file = "brand_scan_report_v4_5.json"
    if not os.path.exists(report_file):
        print(f"Error: {report_file} not found.")
        return
        
    with open(report_file, "r") as f:
        scan_data = json.load(f)

    results = []
    
    with get_db_session() as db:
        for item in scan_data:
            c = db.query(Campaign).get(item["id"])
            if not c: continue
            
            # The brands that SHOULD be removed (identified by script)
            bad_brands = item.get("removals_negation", []) + item.get("removals_noise", [])
            
            # Brands currently in DB for this campaign
            current_brands = [cb.brand.name for cb in c.brands]
            
            # Run AIParser's Logic (Mirror of parse_campaign_data inner)
            # We want to see if the parser effectively REJECTS these brands
            # We feed the parser ALL current brands and see which ones it lets pass
            validated_brands = parser._validate_brands_against_text(
                brands=current_brands,
                clean_text=c.clean_text,
                title=c.title
            )
            
            # Evaluation: Did the parser reject ALL bad brands?
            missed_removals = [b for b in bad_brands if b in validated_brands]
            
            status = "✅ PASS" if not missed_removals else "❌ FAIL"
            
            results.append({
                "id": c.id,
                "status": status,
                "failed_to_reject": missed_removals,
                "title": c.title[:50] + "..."
            })

    # Print Results Table
    print("\n| ID | Status | Failed to Reject | Title |")
    print("|---|---|---|---|")
    for r in results:
        print(f"| {r['id']} | {r['status']} | {r['failed_to_reject']} | {r['title']} |")

    success_count = sum(1 for r in results if r["status"] == "✅ PASS")
    print(f"\nSummary: {success_count}/{len(results)} Passed.")

if __name__ == "__main__":
    verify_batch()
