import os
import re

scraper_dir = "/Users/hipoglisemi/Desktop/kartavantaj-scraper/src/scrapers"

for filename in os.listdir(scraper_dir):
    if not filename.endswith(".py"): continue
    if filename in ["__init__.py", "akbank_base.py"]: continue
    
    filepath = os.path.join(scraper_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 1. Clean up the messy indentation and duplicate elifs we just introduced
    # This is a brute-force fix for the counters and the loop logic
    
    # Let's fix the counters initialization first
    content = re.sub(r'(\s+)(?:saved|success|success_count).*?=.*?0\n\s+total_revived: int = 0', r'\1success_count = 0\n\1skipped_count = 0\n\1failed_count = 0\n\1total_revived = 0', content)
    
    # Now let's fix the loop logic. 
    # We'll search for the block that processes the result.
    pattern = r'if\s+([a-zA-Z0-9_]+)\s*==\s*["\']saved["\']:(.*?)(?:elif|else|except)'
    def fix_loop(match):
        res_var = match.group(1)
        indent = match.group(0).split('if')[0]
        return f'{indent}if {res_var} == "saved":\n{indent}    success_count += 1\n{indent}elif {res_var} == "revived":\n{indent}    total_revived += 1\n{indent}elif {res_var} == "skipped":\n{indent}    skipped_count += 1\n{indent}else:\n{indent}    failed_count += 1\n{indent}except'

    # This is too risky with regex. I will instead do a very specific replacement for the mess I made.
    
    # Fix the on_digital style mess:
    content = content.replace('total_revived: int = 0\n            for', 'total_revived = 0\n            for')
    content = content.replace('elif res == "revived":\n                    total_revived += 1\n                    elif res == "skipped":', 'elif res == "revived":\n                        total_revived += 1\n                    elif res == "skipped":')

    # General cleanup of double elifs or bad indentions
    # (Manually fixing the common patterns I see in the logs)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

print("Attempted cleanup. Now let's do a proper check.")
