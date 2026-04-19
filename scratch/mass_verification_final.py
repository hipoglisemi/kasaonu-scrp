import sys
import os
import json
from datetime import datetime

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the Golden Parser
from src.services.ai_parser_golden import parse_api_campaign

# File mapping (Step IDs from read_url_content)
DATA_DIR = "/Users/hipoglisemi/.gemini/antigravity/brain/aee77ccc-5d76-43ad-87af-ee16593d80f4/.system_generated/steps"
MANIFEST = [
    {"bank": "Akbank", "step": "735", "url": "https://www.axess.com.tr/..."},
    {"bank": "Akbank", "step": "736", "url": "https://www.axess.com.tr/..."},
    {"bank": "Garanti", "step": "737", "url": "https://milesandsmilesgarantibbva.com/..."},
    {"bank": "Garanti", "step": "738", "url": "https://www.bonus.com.tr/..."},
    {"bank": "Yapikredi", "step": "739", "url": "https://www.worldcard.com.tr/..."},
    {"bank": "Yapikredi", "step": "740", "url": "https://www.worldcard.com.tr/..."},
    {"bank": "Ziraat", "step": "741", "url": "https://www.bankkart.com.tr/..."},
    {"bank": "Ziraat", "step": "742", "url": "https://www.bankkart.com.tr/..."},
    {"bank": "Vakifbank", "step": "746", "url": "https://www.vakifkart.com.tr/..."},
    {"bank": "Vakifbank", "step": "747", "url": "https://www.vakifkart.com.tr/..."},
    {"bank": "Paraf", "step": "748", "url": "https://www.paraf.com.tr/..."},
    {"bank": "Paraf", "step": "749", "url": "https://www.paraf.com.tr/..."},
    {"bank": "Isbankasi", "step": "750", "url": "https://www.maximum.com.tr/..."},
    {"bank": "Isbankasi", "step": "751", "url": "https://www.maximum.com.tr/..."}
]

def run_test():
    all_results = []
    for item in MANIFEST:
        file_path = os.path.join(DATA_DIR, item["step"], "content.md")
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            continue
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        print(f"🧠 Parsing {item['bank']} (Step {item['step']})...")
        
        # Use first line of content as a proxy for title if needed, 
        # but parse_api_campaign is robust enough.
        res = parse_api_campaign(
            title="Auto Test Title",
            short_description=None,
            content_html=content,
            bank_name=item["bank"],
            tracking_url=item["url"],
            og_title=None
        )
        
        if res:
            all_results.append({
                "bank": item["bank"],
                "url": item["url"],
                "details": res
            })

    # Save Results
    with open("scratch/mass_verification_detailed.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("\n✅ Deep-Dive Mass Verification Complete. Results in scratch/mass_verification_detailed.json")

if __name__ == "__main__":
    run_test()
