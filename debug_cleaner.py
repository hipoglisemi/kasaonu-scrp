import re
import requests
from bs4 import BeautifulSoup
from src.services.text_cleaner import clean_campaign_text
# Copy paste the entire text_cleaner function but with prints
with open('src/services/text_cleaner.py', 'r') as f:
    code = f.read()

# Replace assignments to final_text with print statements
code = code.replace('final_text = final_text[target_match.start():].strip()', 'final_text = final_text[target_match.start():].strip()\n        print(f"TITLE CHOP! Length now: {len(final_text)}")')
code = code.replace('final_text = final_text[restart_pos:].strip()', 'final_text = final_text[restart_pos:].strip()\n                print(f"YAPI CHOP! Length now: {len(final_text)}")')
code = code.replace('final_text = final_text[:match.start()].strip()', 'final_text = final_text[:match.start()].strip()\n            print(f"NICHE NAV CHOP! Marker: {marker}, Length now: {len(final_text)}")')
code = code.replace('final_text = final_text[:legal_limit_idx].strip()', 'final_text = final_text[:legal_limit_idx].strip()\n        print(f"LEGAL CHOP! Length now: {len(final_text)}")')
code = code.replace('final_text = final_text[:earliest_noise_idx].strip()', 'final_text = final_text[:earliest_noise_idx].strip()\n        print(f"NOISE CHOP! Length now: {len(final_text)}")')

# Also print lengths after steps
code = code.replace('final_text = \'\\n\'.join(cleaned_lines)', 'final_text = \'\\n\'.join(cleaned_lines)\n    print(f"START Length: {len(final_text)}")')

with open('debug_cleaner_temp.py', 'w') as f:
    f.write(code)

