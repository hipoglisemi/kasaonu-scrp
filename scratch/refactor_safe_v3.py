import os
import re

scraper_dir = "/Users/hipoglisemi/Desktop/kartavantaj-scraper/src/scrapers"

for filename in os.listdir(scraper_dir):
    if not filename.endswith(".py"): continue
    if filename in ["__init__.py", "akbank_base.py"]: continue
    
    filepath = os.path.join(scraper_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    original_content = content
    
    # 2. Add total_revived initialization safely
    match_init = re.search(r'^(\s*)(total_saved|success_count|saved_count)\s*=\s*0', content, re.MULTILINE)
    if match_init and "total_revived = 0" not in content:
        indent = match_init.group(1)
        var_name = match_init.group(2)
        content = content.replace(f"{indent}{var_name} = 0", f"{indent}{var_name} = 0\n{indent}total_revived = 0")

    # 3. Add total_revived check in the loop safely
    match_skipped = re.search(r'^(\s*)elif\s+([a-zA-Z0-9_]+)\s*==\s*["\']skipped["\']:', content, re.MULTILINE)
    if match_skipped and "elif" not in content.split("total_revived += 1")[-1]: # rough check
        indent = match_skipped.group(1)
        var_name = match_skipped.group(2)
        if "total_revived = 0" in content:
            new_block = f'{indent}elif {var_name} == "revived":\n{indent}    total_revived += 1  # type: ignore\n{match_skipped.group(0)}'
            content = content.replace(match_skipped.group(0), new_block)

    # 4. Update the final print statement safely
    if "Revived" not in content and "Scraping finished" in content:
        content = re.sub(
            r'(print\(f"🏁 Scraping finished.*?Failed: \{[a-zA-Z0-9_]+\})(".*?)\)',
            r'\1, Revived: {total_revived}\2)',
            content
        )

    # 5. Replace self.db.add(campaign) and db.add(campaign)
    if "upsert_campaign" not in content or "db.add(campaign)" in content:
        content = re.sub(
            r'^(\s*)self\.db\.add\(campaign\)(.*)$',
            r'\1from src.utils.scraper_utils import upsert_campaign\n\1campaign, _op_status = upsert_campaign(self.db, campaign)',
            content,
            flags=re.MULTILINE
        )
        content = re.sub(
            r'^(\s*)db\.add\(campaign\)(.*)$',
            r'\1from src.utils.scraper_utils import upsert_campaign\n\1campaign, _op_status = upsert_campaign(db, campaign)',
            content,
            flags=re.MULTILINE
        )
        
        # 6. Safe return replacement
        content = re.sub(
            r'^(\s*)return\s+"saved"(.*)$',
            r'\1return locals().get("_op_status", "saved")\2',
            content,
            flags=re.MULTILINE
        )

    if content != original_content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Refactored cleanly: {filename}")

print("Done refactoring scrapers V3 safely!")
