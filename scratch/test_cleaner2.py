import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.services.text_cleaner import clean_campaign_text

with open("scratch/deniz_agent_html.txt", "r") as f:
    raw_html = f.read()

# DB'deki tam baslikla test edelim
cleaned = clean_campaign_text(raw_html, "İnternet Alışverişlerinize 2.000 TL’ye Varan Bonus!", "İnternet Alışverişlerinize 2.000 TL’ye Varan Bonus!")
print("--- TEST CLEANER WITH FULL TITLE ---")
print("ECOM VAR MI:", "ECOM" in cleaned)
print(cleaned[:300])

